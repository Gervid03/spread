"""Check r4v_seed_quoted and ext_ring_skipped_learn in r4-volume-dev2 vs dev1."""
from __future__ import annotations

import json
from pathlib import Path


def main() -> None:
    champ = {json.loads(l)["seed"]: json.loads(l) for l in Path("champion/results/dev-L8.jsonl").read_text().splitlines() if l.strip()}
    dev1 = {json.loads(l)["seed"]: json.loads(l) for l in Path("runs/20261114-150812-r4-volume-dev1/results.jsonl").read_text().splitlines() if l.strip()}
    dev2 = {json.loads(l)["seed"]: json.loads(l) for l in Path("runs/20261114-153045-r4-volume-dev2/results.jsonl").read_text().splitlines() if l.strip()}
    for s in sorted(champ):
        c, d1, d2 = champ[s], dev1[s], dev2[s]
        print(
            f"{s}: champ={c['margin']:8.1f}({c['won']:3d}) | dev1={d1['margin']:8.1f}({d1['won']:3d}, {d1['margin']-c['margin']:+6.1f}) | "
            f"dev2={d2['margin']:8.1f}({d2['won']:3d}, {d2['margin']-c['margin']:+6.1f}) | "
            f"seed_q={d2['stats'].get('r4v_seed_quoted',0):3d} seed_w={d2['stats'].get('r4v_seed_won',0):2d} skip_lrn={c['stats'].get('ext_ring_skipped_learn',0)}->{d2['stats'].get('ext_ring_skipped_learn',0)}"
        )


if __name__ == "__main__":
    main()
