"""Check net_seed request counts on /tmp/reveals-v3 (all deliveries vs outbound to <100 supply)."""
from __future__ import annotations

import csv
import math
from collections import Counter, defaultdict
from pathlib import Path


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (lat1, lon1, lat2, lon2))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(h))


def main() -> None:
    for folder in sorted(Path("/tmp/reveals-v3").glob("reveal-*")):
        places = {r["id"]: (float(r["lat"]), float(r["lon"])) for r in csv.DictReader(open(folder / "places.csv"))}
        line = {(a, b): haversine_km(*places[a], *places[b]) for a in places for b in places}
        drivers = {r["id"]: r for r in csv.DictReader(open(folder / "drivers.csv"))}
        sup30 = {p: sum(1 for d in drivers.values() if line[(p, d["homePlaceId"])] <= 30.0) for p in places}
        legs = defaultdict(dict)
        for r in csv.DictReader(open(folder / "legs.csv")):
            legs[r["requestId"]][int(r["leg"])] = r
        reqs = sorted(csv.DictReader(open(folder / "requests.csv")), key=lambda r: int(r["arrivedAt"]))

        cnt_all = Counter()
        cnt_from_noon = Counter()
        total_quoted = 0
        seed_literal_all = 0
        seed_literal_from_noon = 0
        seed_outbound_thin = 0
        for r in reqs:
            rid = r["id"]
            at = int(r["arrivedAt"])
            p_pl = legs[rid][0]["pickup.placeId"]
            d_pl = legs[rid][max(legs[rid])]["delivery.placeId"]
            cnt_all[p_pl] += 1
            if at >= 720:
                cnt_from_noon[p_pl] += 1
            # was it quoted (not 4x decline)?
            q_sd = r["same_day.quoteCents"]
            l_sd = r["same_day.listPriceCents"]
            declined = q_sd and l_sd and abs(int(q_sd) - 4 * int(l_sd)) <= 2 and not r["next_day.quoteCents"]
            if not declined:
                total_quoted += 1
                if at >= 720 and sup30[p_pl] >= 100:
                    if any(cnt_all[t] >= 6 for t in places if line[(d_pl, t)] <= 30.0):
                        seed_literal_all += 1
                        if sup30[d_pl] < 100:
                            seed_outbound_thin += 1
                    if any(cnt_from_noon[t] >= 6 for t in places if line[(d_pl, t)] <= 30.0):
                        seed_literal_from_noon += 1
        print(
            f"{folder.name}: total_quoted={total_quoted}, "
            f"seed_all_week={seed_literal_all} ({seed_literal_all/total_quoted:.0%}), "
            f"seed_counted_from_noon={seed_literal_from_noon} ({seed_literal_from_noon/total_quoted:.0%}), "
            f"seed_outbound_deliv<100={seed_outbound_thin} ({seed_outbound_thin/total_quoted:.0%})"
        )


if __name__ == "__main__":
    main()
