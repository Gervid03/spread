"""Slot-free audit of all cached TAS runs, limits, bounds, and tas-state fork probes across the 4 TAS seeds."""
from __future__ import annotations

import json
import statistics
from spread_lab.env import lab_home

TAS_SEEDS = ("dev-12", "dev-01", "dev-08", "dev-07")


def main() -> None:
    tas_dir = lab_home() / "tas"

    print("=== 1. ALL RECORDED TAS RUNS (runs.jsonl) ===")
    for s in TAS_SEEDS:
        rp = tas_dir / s / "runs.jsonl"
        print()
        print(f"--- {s} ---")
        if rp.exists():
            for line in rp.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                r = json.loads(line)
                acc = r.get("account", {})
                print(
                    f"  {r['name']:<38} margin=€{r['margin']:>10,.2f}  won={r['won']:>3}  "
                    f"OT={r['on_time']*100:>5.2f}%  forks={r['forks']:>4}  "
                    f"rev=€{acc.get('revenue',0)/100:>9,.2f}  fee=€{acc.get('driver_fee',0)/100:>9,.2f}"
                )
        bp = tas_dir / s / "tas-routes-bound.json"
        if bp.exists():
            print("  tas-routes-bound:", bp.read_text(encoding="utf-8").strip())

    print()
    print("=== 2. PROBE 1 & PROBE 2 EXACT RESULTS ON dev-12 ===")
    p1 = json.loads((tas_dir / "dev-12" / "tas-state-mechanics-probe.json").read_text(encoding="utf-8"))
    p2 = json.loads((tas_dir / "dev-12" / "tas-state-mechanics-probe2.json").read_text(encoding="utf-8"))
    print("p1 keys:", list(p1.keys()))
    print("p2 keys:", list(p2.keys()))

    base_key = "decline_4x" if "decline_4x" in p1 else list(p1.keys())[0]
    base = p1[base_key]["probed"]
    for k, v in p1.items():
        if not isinstance(v, dict) or "probed" not in v:
            print(f"p1[{k}]:", v)
            continue
        pr = v["probed"]
        diffs = [abs((base[r]["lo"] or 0) - (pr[r]["lo"] or 0)) for r in base if base[r].get("lo") and pr.get(r, {}).get("lo")]
        print(f"  p1[{k}] max_diff vs {base_key}: {max(diffs) if diffs else None} cents")
        for dlr in ("D01", "D02", "D03", "D09", "D10"):
            rats = [
                pr[r]["lo"] / base[r]["lo"]
                for r in pr
                if pr[r]["dealer"] == dlr and pr[r].get("lo") and base.get(r, {}).get("lo")
            ]
            if rats:
                w, tot = v.get("mon_won", {}).get(dlr, 0), v.get("mon_tot", {}).get(dlr, 0)
                tr = v.get("tue_trust", {}).get(dlr, 0)
                print(f"    {dlr}: Mon {w:>2}/{tot:<2} ({w/max(1,tot)*100:5.1f}%) trust={tr:>2} -> n={len(rats):>2}, mean_vs_0%={statistics.mean(rats):.4f}")

    print()
    print("Probe 2 fine-grained D01 Monday share scan:")
    for k, r in p2["shares"].items():
        pr = r["probed"]
        rats = [pr[rid]["lo"] / base[rid]["lo"] for rid in pr if pr[rid].get("lo") and base.get(rid, {}).get("lo")]
        print(f"  target={k:<4} actual={r['won']:>2}/{r['tot']} ({r['won']/r['tot']*100:5.1f}%) -> mean_vs_0%={statistics.mean(rats):.4f} {[round(x,4) for x in rats]}")

    print()
    print("Probe 2 single-order satisfaction / trust / late timing on D01:")
    for mode, r in p2["satisfaction"].items():
        pr = r["probed"]
        rats = [pr[rid]["lo"] / base[rid]["lo"] for rid in pr if pr[rid].get("lo") and base.get(rid, {}).get("lo")]
        print(
            f"  {mode:<14}: deliv={r['deliveredAt']} dl={r['deadline']} trust_d01={r['trust_d01']} "
            f"ledger={r['ledger']} -> mean_vs_0%={statistics.mean(rats):.4f} {[round(x,4) for x in rats]}"
        )

    print()
    print("Probe 2 Mon..Thu 4-day cumulative competitor cap (Fri morning limits, trust=0):")
    f0, f1 = p2["fri_0"]["probed"], p2["fri_1"]["probed"]
    for dlr in ("D01", "D02", "D09"):
        rats = [
            f1[rid]["lo"] / f0[rid]["lo"]
            for rid in f0
            if f0[rid]["dealer"] == dlr and f0[rid].get("lo") and f1.get(rid, {}).get("lo")
        ]
        if rats:
            print(f"  {dlr}: n={len(rats)} Fri(100% Mon..Thu) / Fri(0% Mon..Thu) = {statistics.mean(rats):.4f} (inv={1/statistics.mean(rats):.4f})")


if __name__ == "__main__":
    main()
