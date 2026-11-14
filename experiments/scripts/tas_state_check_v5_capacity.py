"""Check actual solo staffing capacity, option mix, fee multiples, and late rates in reveal-v5.json across the 4 TAS seeds."""
from __future__ import annotations

import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from spread_lab.geo import Geo

DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri")


def main() -> None:
    home = Path.home() / ".spread-lab"
    geo = Geo(json.loads((home / "map.json").read_text(encoding="utf-8")))

    for seed in ("dev-12", "dev-01", "dev-08", "dev-07"):
        tape = json.loads((home / "tas" / seed / "tape.json").read_text(encoding="utf-8"))
        rev = json.loads((home / "tas" / seed / "reveal-v5.json").read_text(encoding="utf-8"))
        reqs = {r["id"]: r for r in tape["requests"]}
        s30 = geo.supply(tape["roster"], 30.0)
        s55 = geo.supply(tape["roster"], 55.0)

        by_opt = Counter()
        by_day = Counter()
        by_dlr_day = Counter()
        dlr_tot_day = Counter()
        for r in tape["requests"]:
            dlr_tot_day[(r["dealerId"], r["arrivedAt"] // 1440)] += 1

        opt_fees = defaultdict(list)
        for rr in rev["requests"]:
            rid = rr["request"]["id"]
            if rr.get("outcome") == "won":
                opt = rr.get("option", "?")
                d = reqs[rid]["arrivedAt"] // 1440
                by_opt[opt] += 1
                by_day[d] += 1
                by_dlr_day[(reqs[rid]["dealerId"], d)] += 1

        # Booked fee / ref by option from reveal views/gigs if available
        print(f"=== {seed}: v5 won={sum(by_opt.values())} ===")
        print("  v5 by day:", {DAYS[d]: by_day[d] for d in range(5)})
        print("  v5 by opt:", dict(by_opt))
        for dlr in ("D01", "D02", "D03"):
            tots = [dlr_tot_day[(dlr, d)] for d in range(5)]
            if sum(tots) >= 40:
                s_str = "  ".join(
                    f"{DAYS[d]}:{by_dlr_day[(dlr, d)]}/{tots[d]}({by_dlr_day[(dlr, d)]/max(1,tots[d])*100:.0f}%)"
                    for d in range(5)
                )
                print(f"    v5 {dlr}: {s_str}")


if __name__ == "__main__":
    main()
