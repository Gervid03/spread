"""Inspect counters and cycle counts across our smoke runs."""
from __future__ import annotations

import json
from pathlib import Path

RUNS = [
    "runs/20261114-162357-tas-price-v7-fixed-noop",
    "runs/20261114-162515-tas-price-smoke-dest",
    "runs/20261114-162949-tas-price-smoke-menu-closer",
    "runs/20261114-163419-tas-price-smoke-comb",
]


def main() -> None:
    for r in RUNS:
        p = Path(r) / "results.jsonl"
        rows = [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
        rows.sort(key=lambda x: x["seed"])
        print(f"=== {r.split('-', 2)[-1]} ===")
        for x in rows:
            s = x.get("stats", {})
            cyc2 = s.get("cyc_posted_2", 0)
            cyc3 = s.get("cyc_posted_3", 0)
            cyc4 = s.get("cyc_posted_4", 0)
            st2 = s.get("sunday_bundled_2", 0) + s.get("tour_posted_2", 0)
            print(
                f"  {x['seed']} margin={x['margin']:8.2f} won={x['won']:3d} ot={x['on_time']:.3f} "
                f"floor={s.get('quote_floor',0):3d} cyc=({cyc2},{cyc3},{cyc4}) "
                f"thin={s.get('tas_dest_thin_n',0):3d} hub={s.get('tas_dest_hub_slow_n',0):3d} "
                f"sdm={s.get('tas_sd_menu_slow_n',0):3d} cls={s.get('tas_closer_disc_n',0):3d}"
            )


if __name__ == "__main__":
    main()
