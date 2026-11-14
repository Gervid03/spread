"""Exact stats diff on dev-15, dev-11, dev-05, dev-12 between Champion v6 and r4-volume-dev1."""
from __future__ import annotations

import json
from pathlib import Path


def main() -> None:
    champ = {json.loads(l)["seed"]: json.loads(l) for l in Path("champion/results/dev-L8.jsonl").read_text().splitlines() if l.strip()}
    dev1 = {json.loads(l)["seed"]: json.loads(l) for l in Path("runs/20261114-150812-r4-volume-dev1/results.jsonl").read_text().splitlines() if l.strip()}
    for s in ["dev-15", "dev-11", "dev-12", "dev-05", "dev-06"]:
        c, n = champ[s], dev1[s]
        print(f"=== {s}: dMargin={n['margin']-c['margin']:+.2f}, dWon={n['won']-c['won']:+d} ===")
        all_k = sorted(set(c["stats"]) | set(n["stats"]))
        diffs = {k: (c["stats"].get(k, 0), n["stats"].get(k, 0)) for k in all_k if c["stats"].get(k, 0) != n["stats"].get(k, 0)}
        for k, (cv, nv) in diffs.items():
            if isinstance(cv, float) or isinstance(nv, float):
                if abs(nv - cv) > 0.05:
                    print(f"  {k:<30}: {cv:8.2f} -> {nv:8.2f}")
            else:
                print(f"  {k:<30}: {cv:8d} -> {nv:8d}")


if __name__ == "__main__":
    main()
