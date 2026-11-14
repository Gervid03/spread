"""Slot-free inspection of cached reveals (/tmp/reveals-v3 and /tmp/reveals-n14-01)
to verify event sequences and finish-time estimation for Idea 31 (route network)."""
from __future__ import annotations

import csv
import glob
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

DAY = 1440


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (lat1, lon1, lat2, lon2))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(h))


def check_offers() -> None:
    print("=== Checking offer_answered events across all /tmp reveals ===")
    for path in sorted(glob.glob("/tmp/*reveal*/*/events.csv") + glob.glob("/tmp/*reveal*/events.csv")):
        with open(path, encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        kinds = Counter(r["kind"] for r in rows)
        if kinds["offer_answered"]:
            print(f"{path}: {dict(kinds)}")
            for i, r in enumerate(rows):
                if r["kind"] == "offer_answered":
                    ctx = rows[max(0, i - 2) : min(len(rows), i + 4)]
                    print("  offer_answered context:", [(x["seq"], x["at"], x["kind"], x["gigId"], x["driverId"], x.get("answer", "")) for x in ctx])
                    break


def inspect_v3_world(folder: Path) -> None:
    places = {}
    with open(folder / "places.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            places[r["id"]] = (float(r["lat"]), float(r["lon"]))
    roads = {}
    with open(folder / "roads.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            roads[(r["from"], r["to"])] = int(r["minutes"])
    line_km = {
        (a, b): haversine_km(places[a][0], places[a][1], places[b][0], places[b][1])
        for a in places for b in places
    }
    drivers = {}
    with open(folder / "drivers.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            drivers[r["id"]] = r
    supply30 = Counter()
    for p in places:
        supply30[p] = sum(1 for d in drivers.values() if line_km[(p, d["homePlaceId"])] <= 30.0)

    legs_by_req = defaultdict(dict)
    with open(folder / "legs.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            legs_by_req[r["requestId"]][int(r["leg"])] = r

    requests = {}
    with open(folder / "requests.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            requests[r["id"]] = r

    gigs = {}
    with open(folder / "gigs.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            gigs[r["id"]] = r

    events = []
    with open(folder / "events.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            events.append(r)

    booked_at = {}
    started_at = {}
    late_pickup_at = {}
    picked_up_at = {}
    delivered_at = {}
    for e in events:
        k = e["kind"]
        at = int(e["at"])
        gid = e["gigId"]
        if k == "gig_booked":
            booked_at[gid] = (at, e["driverId"])
        elif k == "gig_started":
            started_at[gid] = at
        elif k == "driver_late":
            late_pickup_at[gid] = int(e["pickupAt"])
        elif k == "picked_up":
            picked_up_at.setdefault(gid, []).append((at, e["orderId"], int(e["leg"]), e["placeId"]))
        elif k == "delivered":
            delivered_at.setdefault(gid, []).append((at, e["orderId"], int(e["leg"]), e["placeId"]))

    diffs_simple = []
    diffs_hours = []
    finishes = []
    for gid, g in gigs.items():
        if g["status"] != "done" or gid not in booked_at or gid not in delivered_at:
            continue
        b_at, did = booked_at[gid]
        stops = json.loads(g["stops"])
        s0 = stops[0]
        leg0 = legs_by_req[s0["orderId"]][s0["leg"]]
        win_from = s0["window"]["from"] if "window" in s0 else int(leg0["pickup.window.from"])
        start_simple = max(b_at, win_from)
        if gid in late_pickup_at:
            start_simple = late_pickup_at[gid]

        # Open-hours adjusted planned pickup
        start_h = max(b_at, win_from)
        if leg0["pickup.privateAddress"] != "true" and leg0["pickup.hours.opens"]:
            opens = int(leg0["pickup.hours.opens"])
            closes = int(leg0["pickup.hours.closes"])
            tod = start_h % DAY
            if tod < opens:
                start_h = (start_h // DAY) * DAY + opens
            elif tod >= closes:
                start_h = (start_h // DAY + 1) * DAY + opens
        if gid in late_pickup_at:
            start_h = late_pickup_at[gid]

        # Road + plates + charging
        dur = 0
        prev_place = None
        for st in stops:
            lg = legs_by_req[st["orderId"]][st["leg"]]
            place = lg["pickup.placeId"] if st["kind"] == "pickup" else lg["delivery.placeId"]
            if prev_place is not None:
                dur += roads[(prev_place, place)]
            if st["kind"] == "pickup":
                if st.get("withPlates"):
                    dur += 30
                if st.get("withCharging"):
                    dur += 40
            prev_place = place

        actual_finish = delivered_at[gid][-1][0]
        actual_place = delivered_at[gid][-1][3]
        diffs_simple.append(actual_finish - (start_simple + dur))
        diffs_hours.append(actual_finish - (start_h + dur))
        finishes.append((actual_finish, actual_place, did, drivers[did]["homePlaceId"]))

    diffs_simple.sort()
    diffs_hours.sort()
    n = len(diffs_simple)
    print(f"=== {folder.name}: {n} completed gigs ===")
    print(f"  actual - (max(booked, win_from) + dur): p10={diffs_simple[n//10]}, med={diffs_simple[n//2]}, p90={diffs_simple[9*n//10]}")
    print(f"  actual - (hours_adj + dur):             p10={diffs_hours[n//10]}, med={diffs_hours[n//2]}, p90={diffs_hours[9*n//10]}")

    # Check continuations within 30 km
    far_from_home = sum(1 for _, pl, _, home in finishes if line_km[(pl, home)] > 30.0)
    print(f"  finishes >30km from driver home: {far_from_home}/{len(finishes)}")

    cont_reqs = 0
    cont_won = 0
    cont_thin = 0
    cand_hist = Counter()
    home_bound_reqs = 0
    for req_id, req in requests.items():
        lg0 = legs_by_req[req_id][0]
        lg_last = legs_by_req[req_id][max(legs_by_req[req_id])]
        p_place = lg0["pickup.placeId"]
        d_place = lg_last["delivery.placeId"]
        ready = max(int(req["arrivedAt"]), int(lg0["pickup.window.from"]))
        drive = roads[(p_place, d_place)]
        # latest deadline
        dl = 0
        for opt in ("within_3_days", "next_day", "same_day"):
            if req[f"{opt}.deadline"]:
                dl = max(dl, int(req[f"{opt}.deadline"]))
                break
        cands = []
        for fin_at, fin_pl, did, home in finishes:
            if line_km[(fin_pl, p_place)] <= 30.0:
                if ready - 180 <= fin_at <= ready + 60:
                    dep = max(ready, fin_at + roads[(fin_pl, p_place)])
                    if dl - dep - drive >= 150:
                        cands.append((did, line_km[(d_place, home)] <= 30.0))
        if cands:
            cont_reqs += 1
            if req["outcome"] == "won":
                cont_won += 1
            if supply30[p_place] < 22:
                cont_thin += 1
            cand_hist[min(3, len(cands))] += 1
            if any(hb for _, hb in cands):
                home_bound_reqs += 1
    print(f"  on-network requests (ready-3h..ready+1h, <=30km): {cont_reqs} (already won={cont_won}, thin30={cont_thin}, w/ home-bound cand={home_bound_reqs})")
    print(f"  candidate count dist (1, 2, 3+): {dict(cand_hist)}")


if __name__ == "__main__":
    check_offers()
    for p in sorted(Path("/tmp/reveals-v3").glob("reveal-*")):
        inspect_v3_world(p)
