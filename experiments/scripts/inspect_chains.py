"""Check organic driver gig chains in /tmp/reveals-v3: same-day vs next-day, fees, distances."""
from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from pathlib import Path

DAY = 1440


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (lat1, lon1, lat2, lon2))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(h))


def main() -> None:
    same_day_far_chains = 0
    next_day_far_chains = 0
    fee_ratios_same_day_far = []
    fee_ratios_home_bound = []

    for folder in sorted(Path("/tmp/reveals-v3").glob("reveal-*")):
        places = {r["id"]: (float(r["lat"]), float(r["lon"])) for r in csv.DictReader(open(folder / "places.csv"))}
        line = {(a, b): haversine_km(*places[a], *places[b]) for a in places for b in places}
        drivers = {r["id"]: r for r in csv.DictReader(open(folder / "drivers.csv"))}
        reqs = {r["id"]: r for r in csv.DictReader(open(folder / "requests.csv"))}
        gigs = {r["id"]: r for r in csv.DictReader(open(folder / "gigs.csv"))}
        events = list(csv.DictReader(open(folder / "events.csv")))

        picked, deliv, booked_fee = {}, {}, {}
        for e in events:
            gid = e["gigId"]
            if e["kind"] == "gig_booked":
                booked_fee[gid] = int(e["feeCents"])
            elif e["kind"] == "picked_up":
                picked.setdefault(gid, []).append((int(e["at"]), e["placeId"]))
            elif e["kind"] == "delivered":
                deliv.setdefault(gid, []).append((int(e["at"]), e["placeId"]))

        by_driver = defaultdict(list)
        for gid, g in gigs.items():
            if g["status"] == "done" and gid in picked and gid in deliv:
                did = g["driverId"]
                stops = json.loads(g["stops"])
                oids = list(dict.fromkeys(s["orderId"] for s in stops))
                ref_fee = sum(int(reqs[o]["referenceFeeCents"]) for o in oids)
                by_driver[did].append((
                    picked[gid][0][0], picked[gid][0][1],
                    deliv[gid][-1][0], deliv[gid][-1][1],
                    int(g["feeCents"]) / ref_fee if ref_fee else 1.0,
                    gid,
                ))

        driver_days_2plus = 0
        for did, lst in by_driver.items():
            lst.sort()
            by_day = defaultdict(int)
            for p_at, _, _, _, _, _ in lst:
                by_day[p_at // DAY] += 1
            driver_days_2plus += sum(1 for c in by_day.values() if c >= 2)
            home = drivers[did]["homePlaceId"]
            for a, b in zip(lst, lst[1:]):
                p1_at, p1_pl, d1_at, d1_pl, r1, _ = a
                p2_at, p2_pl, d2_at, d2_pl, r2, _ = b
                if line[(d1_pl, p2_pl)] <= 30.0 and line[(p2_pl, home)] > 30.0:
                    if d1_at // DAY == p2_at // DAY:
                        same_day_far_chains += 1
                        fee_ratios_same_day_far.append(r2)
                        if line[(d2_pl, home)] <= 30.0:
                            fee_ratios_home_bound.append(r2)
                    elif p2_at // DAY == d1_at // DAY + 1:
                        next_day_far_chains += 1
        print(f"{folder.name}: driver_days_2plus={driver_days_2plus}")

    print(f"Total far-from-home chains (d1->p2 <=30km, p2 >30km from home): same_day={same_day_far_chains}, next_day={next_day_far_chains}")
    if fee_ratios_same_day_far:
        print(f"  same_day far chain r2 (fee/ref): min={min(fee_ratios_same_day_far):.2f}, med={sorted(fee_ratios_same_day_far)[len(fee_ratios_same_day_far)//2]:.2f}, n={len(fee_ratios_same_day_far)}")
    if fee_ratios_home_bound:
        print(f"  home-bound chain r2 (fee/ref):   min={min(fee_ratios_home_bound):.2f}, med={sorted(fee_ratios_home_bound)[len(fee_ratios_home_bound)//2]:.2f}, n={len(fee_ratios_home_bound)}")


if __name__ == "__main__":
    main()
