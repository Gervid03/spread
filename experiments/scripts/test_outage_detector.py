"""Test online 80km regional outage detector on all 16 revealed champion dev worlds."""
from __future__ import annotations

import csv
import json
import pathlib
from collections import defaultdict

from spread_lab.geo import Geo

DAY = 1440


def main() -> None:
    rev_root = pathlib.Path("/tmp/cp-wild-rev")
    champ_rows = {r["seed"]: r for r in (json.loads(l) for l in open("champion/results/dev-L8.jsonl"))}
    map_data = json.loads(pathlib.Path("/home/lab/.spread-lab/map.json").read_text())
    geo = Geo(map_data)

    for seed, rr in sorted(champ_rows.items(), key=lambda kv: kv[1]["margin"]):
        dd = rev_root / f"reveal-{rr['world']}"
        rqs = {row["id"]: row for row in csv.DictReader(open(dd / "requests.csv"))}
        lgs = defaultdict(list)
        for l in csv.DictReader(open(dd / "legs.csv")):
            lgs[l["requestId"]].append(l)

        # Simulate chronological arrival of quote outcomes at respondBy
        outcomes = []
        for rid, row in rqs.items():
            arr = int(row["arrivedAt"])
            resp = int(row["respondBy"])
            day, tod = arr // DAY, arr % DAY
            if day > 4 or not (480 <= tod <= 1080):
                continue
            opts = [
                (o, int(row[f"{o}.listPriceCents"]), int(row[f"{o}.quoteCents"]))
                for o in ("same_day", "next_day", "within_3_days")
                if row[f"{o}.quoteCents"]
            ]
            if not opts or min(qc / lc for _, lc, qc in opts) >= 3.5:
                continue
            pk = lgs[rid][0]["pickup.placeId"]
            outcomes.append((resp, day, pk, row["outcome"] == "won", opts[0][2] / opts[0][1]))
        outcomes.sort()

        # Check per-day whether a town c achieves >= min_n quotes inside 80km with high win rate AND outside win rate lower
        triggered = []
        by_day = defaultdict(list)
        for resp, day, pk, won, m in outcomes:
            by_day[day].append((resp, pk, won, m))
            cur = by_day[day]
            # Check best center c
            best_c = None
            for c in geo.places:
                inp = [w for _, p, w, _ in cur if geo.line_km(c, p) <= 80.0]
                if len(inp) < 8:
                    continue
                in_wr = sum(inp) / len(inp)
                if in_wr < 0.72:
                    continue
                outp = [w for _, p, w, _ in cur if geo.line_km(c, p) > 80.0]
                if len(outp) >= 5 and (sum(outp) / len(outp)) > in_wr - 0.22:
                    continue
                score = (sum(inp) - 0.40 * len(inp), in_wr, len(inp), c)
                if best_c is None or score > best_c:
                    best_c = score
            if best_c and not any(t[0] == day for t in triggered):
                rem_in = sum(1 for r2, d2, p2, _, _ in outcomes if r2 > resp and d2 == day and geo.line_km(best_c[3], p2) <= 80.0)
                rem_out = sum(1 for r2, d2, p2, _, _ in outcomes if r2 > resp and d2 == day and geo.line_km(best_c[3], p2) > 80.0)
                triggered.append((day, f"{(resp%DAY)//60:02d}:{(resp%DAY)%60:02d}", best_c[3], best_c[2], round(best_c[1], 2), rem_in, rem_out))
        print(f"  {seed:7s} m=€{rr['margin']:7.0f}: triggers={triggered}")


if __name__ == "__main__":
    main()
