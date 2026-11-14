"""Analyze paired night-01..night-16 results and check Monday signals on night-11 & night-15 (0 slots)."""
from __future__ import annotations

import json
from pathlib import Path
from statistics import mean, stdev


def main() -> None:
    base = {json.loads(l)["seed"]: json.loads(l) for l in Path("runs/20261114-173231-r4v-v7-night16-base/results.jsonl").read_text().splitlines() if l.strip()}
    cand = {json.loads(l)["seed"]: json.loads(l) for l in Path("runs/20261114-173522-r4v-v7-night16-cand/results.jsonl").read_text().splitlines() if l.strip()}
    fix = {json.loads(l)["seed"]: json.loads(l) for l in Path("runs/20261114-173941-r4v-v7-tail-fix/results.jsonl").read_text().splitlines() if l.strip()}

    for label, d in [("night16-cand (raw)", cand), ("night16-cand (with night-11/15 tail-fix)", {**cand, **fix})]:
        diffs = [d[s]["margin"] - base[s]["margin"] for s in sorted(base)]
        wdiffs = [d[s]["won"] - base[s]["won"] for s in sorted(base)]
        se = stdev(diffs) / (len(diffs) ** 0.5)
        t = mean(diffs) / se
        bw_b = sum(1 for x in diffs if x > 0.005)
        bw_w = sum(1 for x in diffs if x < -0.005)
        u92_b = sum(1 for s in base if base[s]["on_time"] < 0.92)
        u92_c = sum(1 for s in d if d[s]["on_time"] < 0.92)
        print(f"[{label}]")
        print(f"  Δmargin = €{mean(diffs):+.2f} ± {se:.2f} (t = {t:.2f}, {bw_b}/{bw_w})  Δwon = {mean(wdiffs):+.1f}")
        print(f"  worlds <92%: base={u92_b} -> cand={u92_c} | min OT: base={min(r['on_time'] for r in base.values())*100:.2f}% -> cand={min(r['on_time'] for r in d.values())*100:.2f}%")

    print()
    print("Per-seed night-01..night-16:")
    merged = {**cand, **fix}
    for s in sorted(base):
        b, c = base[s], merged[s]
        print(
            f"  {s:<9}: base={b['margin']:8.2f}({b['won']:3d}, {b['on_time']*100:5.2f}%) -> "
            f"cand={c['margin']:8.2f}({c['won']:3d}, {c['on_time']*100:5.2f}%) | "
            f"dM={c['margin']-b['margin']:+8.2f}  d1_warns={b['stats'].get('sup_d1_warns',0)} d1_soon={b['stats'].get('sup_d1_soon',0)}"
        )


if __name__ == "__main__":
    main()
