"""Summarize shared TAS findings (`tas-state-mechanics-probe.json` and `limits-won-apply.jsonl`) for planner calibration."""
from __future__ import annotations

import json
import statistics
from collections import defaultdict
from spread_lab.env import lab_home
from experiments.scripts.tas_routes_census import load_geo, load_tape


def main() -> None:
    p = lab_home() / "tas" / "dev-12" / "tas-state-mechanics-probe.json"
    if p.exists():
        data = json.loads(p.read_text(encoding="utf-8"))
        print("=== tas-state-mechanics-probe.json arms ===")
        arms = list(data.keys())
        for arm in arms:
            a = data[arm]
            probed = a.get("probed", {})
            xs = [v["lo"] / v["list"] for v in probed.values() if v.get("lo") and v.get("list")]
            print(f"  {arm:<24} probe_day={a.get('probe_day')} won_by_dlr={a.get('won_by_dlr')} n_probed={len(xs)} med_x={statistics.median(xs) if xs else None}")
        # Compare exact same rid across arms!
        if len(arms) >= 2:
            base = data[arms[0]]["probed"]
            print("  Per-request comparison across arms:")
            for rid in sorted(base)[:12]:
                vals = []
                for arm in arms:
                    pr = data[arm].get("probed", {}).get(rid)
                    if pr and pr.get("lo"):
                        vals.append(f"{arm}={pr['lo']/pr['list']:.3f}(tr={pr.get('trust')})")
                print(f"    {rid} ({base[rid]['dealer']}): " + ", ".join(vals))

    # Summarize limits-won-apply.jsonl across seeds where available
    geo = load_geo()
    for seed in ("dev-12", "dev-01", "dev-08", "dev-07"):
        lp = lab_home() / "tas" / seed / "limits-won-apply.jsonl"
        if not lp.exists():
            continue
        tape = load_tape(seed)
        supply30 = geo.supply(tape["roster"], 30.0)
        rows = [json.loads(line) for line in lp.read_text(encoding="utf-8").splitlines() if line.strip()]
        by_day = defaultdict(list)
        by_sup = defaultdict(list)
        for r in rows:
            if r.get("lo") and r.get("list"):
                x = r["lo"] / r["list"]
                by_day[r["day"]].append(x)
                s_bin = "hub>=100" if supply30.get(r["pickup"], 0) >= 100 else ("med22-99" if supply30.get(r["pickup"], 0) >= 22 else "thin<22")
                by_sup[s_bin].append(x)
        print(f"=== {seed} limits-won-apply ({len(rows)} won orders) ===")
        print("  By day: " + " | ".join(f"d{d}: n={len(v)} med={statistics.median(v):.3f}" for d, v in sorted(by_day.items())))
        print("  By pickup supply: " + " | ".join(f"{k}: n={len(v)} med={statistics.median(v):.3f}" for k, v in sorted(by_sup.items())))


if __name__ == "__main__":
    main()
