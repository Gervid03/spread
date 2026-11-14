"""Compare tour_booked and lead_car_booked in dev1 vs dev2."""
from __future__ import annotations

import json
from pathlib import Path


def main() -> None:
    dev1 = {json.loads(l)["seed"]: json.loads(l) for l in Path("runs/20261114-150812-r4-volume-dev1/results.jsonl").read_text().splitlines() if l.strip()}
    dev2 = {json.loads(l)["seed"]: json.loads(l) for l in Path("runs/20261114-153045-r4-volume-dev2/results.jsonl").read_text().splitlines() if l.strip()}
    for s in sorted(dev1):
        s1, s2 = dev1[s]["stats"], dev2[s]["stats"]
        print(
            f"{s}: dMargin(d2-d1)={dev2[s]['margin']-dev1[s]['margin']:+7.1f} | "
            f"staged={s1.get('r4v_staged',0):2d}->{s2.get('r4v_staged',0):2d} | "
            f"tBook={s1.get('r4v_tour_booked',0):2d}->{s2.get('r4v_tour_booked',0):2d} | "
            f"lcBook={s1.get('lead_car_booked',0):2d}->{s2.get('lead_car_booked',0):2d} | "
            f"tiWon={s1.get('r4v_tradein_won',0):2d}->{s2.get('r4v_tradein_won',0):2d}"
        )


if __name__ == "__main__":
    main()
