"""Scout R7 (Snow & dev-07 drop spike) and R11 (Hitch & declined volume pairing).

Usage:
    python3 experiments/scripts/scout_snow.py [/tmp/reveals-v3] [/tmp/reveals-n14-01]
"""
from __future__ import annotations

import collections
import csv
import json
import math
import re
import statistics as st
import sys
from pathlib import Path

csv.field_size_limit(10**9)

HOUR = 60
DAY = 24 * 60
DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun", "Mon2")
OPTS = ("same_day", "next_day", "within_3_days")

SUMMER_RE = re.compile(
    r"kesärenka|kesarenka|kesäkum|kesakum|sommardäck|sommardack|summer\s+t[yi]res?|ei\s+talvirenk|inga\s+vinterd",
    re.IGNORECASE,
)

WORLD_TO_SEED = {
    # Champion v3 dev worlds
    "w9c4b06995c663e2f28a6": "dev-01",
    "w4b373e86f28e39fda4ea": "dev-02",
    "wd3130554016e7f89c2f0": "dev-03",
    "w01997cb44ec762059ef0": "dev-04",
    "w91857c5692d051ebfb9a": "dev-05",
    "w37a2860029b585619526": "dev-06",
    "w20775676a400fbd09ee0": "dev-07",
    "w3d37f4c04b88828587cd": "dev-08",
    "w41dbdefe5c71fdc4b68b": "dev-09",
    "wc8ea6594559554734eca": "dev-10",
    "wbf020a41636bdbee339a": "dev-11",
    "w0d8a15ec8b1b88119ad8": "dev-12",
    "w47fbc789c504e8ea9375": "dev-13",
    "w9df41319b01b5fbccf60": "dev-14",
    "w3926cb3171f857f0bebf": "dev-15",
    "w38a366237fd528864c72": "dev-16",
    # Champion v2 dev worlds (/tmp/reveals-n14-01)
    "w3cad448716a472226749": "dev-01",
    "w76b10c63d7bfa6d49da0": "dev-02",
    "w7f6e638d3418e6ed351d": "dev-03",
    "w97ea2b32b71ef8c90316": "dev-04",
    "wcd72324b68908e897d0d": "dev-05",
    "w9a9532e7be8f4171ae76": "dev-06",
    "wa5d0041ba245f34be266": "dev-07",
    "w0f0b80c2fc086a2bbc10": "dev-08",
    "w1a1b8cd847f90e0c613e": "dev-09",
    "wba9b3cf9c7db19c4b599": "dev-10",
    "w6bae56eda250a23a432a": "dev-11",
    "w5821d8a6f3fbe1f59c5b": "dev-12",
    "w0c23053fd89b352e58f7": "dev-13",
    "w671613ac1edbaca8b6f3": "dev-14",
    "w393dea939070ee045bbc": "dev-15",
    "wabc3b64955f4c84bd03b": "dev-16",
}


def read_csv(folder: Path, name: str) -> list[dict[str, str]]:
    with open(folder / f"{name}.csv", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(h))


def fmt_min(m: int) -> str:
    d = m // DAY
    h = (m % DAY) // HOUR
    mn = m % HOUR
    d_str = DAYS[d] if 0 <= d < len(DAYS) else f"D{d}"
    return f"{d_str} {h:02d}:{mn:02d} ({m})"


def next_bday(d: int) -> int:
    nd = d + 1
    while nd in (5, 6):
        nd += 1
    return nd


def load_world(folder: Path) -> dict:
    wid = folder.name.removeprefix("reveal-")
    seed = WORLD_TO_SEED.get(wid, wid)
    places = {p["id"]: (float(p["lat"]), float(p["lon"])) for p in read_csv(folder, "places")}
    line_km = {(a, b): haversine_km(places[a], places[b]) for a in places for b in places}
    roads = {(r["from"], r["to"]): (float(r["km"]), int(r["minutes"])) for r in read_csv(folder, "roads")}
    drivers = read_csv(folder, "drivers")
    homes = collections.Counter(d["homePlaceId"] for d in drivers)
    supply30 = {p: sum(n for h, n in homes.items() if line_km[(p, h)] <= 30.0) for p in places}
    supply55 = {p: sum(n for h, n in homes.items() if line_km[(p, h)] <= 55.0) for p in places}
    supply70 = {p: sum(n for h, n in homes.items() if line_km[(p, h)] <= 70.0) for p in places}

    requests = {r["id"]: r for r in read_csv(folder, "requests")}
    legs_list = read_csv(folder, "legs")
    legs_by_req: dict[str, list[dict[str, str]]] = collections.defaultdict(list)
    for l in legs_list:
        legs_by_req[l["requestId"]].append(l)
    for rid in legs_by_req:
        legs_by_req[rid].sort(key=lambda x: int(x["leg"]))

    gigs = {g["id"]: g for g in read_csv(folder, "gigs")}
    events = read_csv(folder, "events")
    return {
        "folder": folder,
        "wid": wid,
        "seed": seed,
        "places": places,
        "line_km": line_km,
        "roads": roads,
        "drivers": drivers,
        "supply30": supply30,
        "supply55": supply55,
        "supply70": supply70,
        "requests": requests,
        "legs_by_req": legs_by_req,
        "gigs": gigs,
        "events": events,
    }


def analyze_r7_world(w: dict) -> dict:
    events = w["events"]
    gigs = w["gigs"]
    requests = w["requests"]
    legs_by_req = w["legs_by_req"]
    roads = w["roads"]

    forecasts = []
    for e in events:
        if e["kind"] == "forecast":
            forecasts.append({
                "at": int(e["at"]),
                "from": int(e["from"]),
                "to": int(e["to"]),
                "places": set(json.loads(e["placeIds"])),
                "place_list": json.loads(e["placeIds"]),
                "text": e["text"],
            })

    def gig_places(gid: str) -> tuple[list[str], list[str], list[str]]:
        g = gigs.get(gid)
        if not g:
            return [], [], []
        stops = json.loads(g["stops"])
        p_places, d_places, oids = [], [], []
        for s in stops:
            oid = s["orderId"]
            if oid not in oids:
                oids.append(oid)
            leg_idx = int(s["leg"])
            leg_row = legs_by_req[oid][leg_idx]
            if s["kind"] == "pickup":
                p_places.append(leg_row["pickup.placeId"])
            else:
                d_places.append(leg_row["delivery.placeId"])
        return p_places, d_places, oids

    def in_forecast_at(t: int, place_set: set[str]) -> bool:
        return any(f["from"] <= t <= f["to"] and bool(f["places"] & place_set) for f in forecasts)

    def window_overlaps_forecast(t0: int, t1: int, place_set: set[str]) -> bool:
        return any(max(t0, f["from"]) < min(t1, f["to"]) and bool(f["places"] & place_set) for f in forecasts)

    active_booking: dict[str, tuple[int, int, str]] = {}
    drops = []
    drops_by_hour = collections.Counter()
    drops_snow_by_hour = collections.Counter()
    drops_snow_pk_by_hour = collections.Counter()

    visit_fails = []
    vf_by_reason = collections.Counter()
    vf_snow_by_reason = collections.Counter()

    won_orders = {}
    late_order_ids = set()
    expired_gigs = 0

    for e in events:
        k = e["kind"]
        if k == "order_won":
            won_orders[e["order.id"]] = {
                "id": e["order.id"],
                "at": int(e["at"]),
                "option": e["order.option"],
                "priceCents": int(e["order.priceCents"]),
                "deadline": int(e["order.deadline"]),
                "lastPickupAt": int(e["order.lastPickupAt"]),
            }
        elif k == "gig_booked":
            active_booking[e["gigId"]] = (int(e["at"]), int(e["feeCents"]), e["driverId"])
        elif k == "gig_expired":
            expired_gigs += 1
        elif k == "gig_dropped":
            at = int(e["at"])
            gid = e["gigId"]
            p_places, d_places, oids = gig_places(gid)
            all_places = set(p_places) | set(d_places)
            first_pickup = p_places[0] if p_places else "?"
            first_deliv = d_places[0] if d_places else "?"
            drive_min = roads[(first_pickup, first_deliv)][1] if (first_pickup, first_deliv) in roads else 0
            drive_km = roads[(first_pickup, first_deliv)][0] if (first_pickup, first_deliv) in roads else 0.0
            bk = active_booking.pop(gid, None)
            booked_at = bk[0] if bk else int(gigs[gid]["postedAt"])
            held_min = (at - booked_at)
            fee_cents = bk[1] if bk else int(gigs[gid]["feeCents"])
            ref_cents = sum(int(requests[oid]["referenceFeeCents"]) for oid in oids) if oids else 1
            fee_ratio = fee_cents / ref_cents
            opt = won_orders[oids[0]]["option"] if oids and oids[0] in won_orders else "?"

            in_snow_pickup_now = in_forecast_at(at, set(p_places))
            in_snow_any_now = in_forecast_at(at, all_places)
            ord_dl = min((won_orders[oid]["deadline"] for oid in oids if oid in won_orders), default=at + DAY)
            in_snow_window = window_overlaps_forecast(booked_at, ord_dl, all_places)

            hr = (at % DAY) // HOUR
            drops_by_hour[hr] += 1
            if in_snow_any_now:
                drops_snow_by_hour[hr] += 1
            if in_snow_pickup_now:
                drops_snow_pk_by_hour[hr] += 1

            drops.append({
                "at": at,
                "booked_at": booked_at,
                "day": at // DAY,
                "hour": hr,
                "gigId": gid,
                "driverId": e["driverId"],
                "oids": oids,
                "option": opt,
                "pickup": first_pickup,
                "delivery": first_deliv,
                "drive_min": drive_min,
                "drive_km": drive_km,
                "held_min": held_min,
                "fee_ratio": fee_ratio,
                "in_snow_pickup_now": in_snow_pickup_now,
                "in_snow_any_now": in_snow_any_now,
                "in_snow_window": in_snow_window,
            })
        elif k == "visit_failed":
            at = int(e["at"])
            reason = e["reason"]
            place = e["placeId"]
            oid = e["orderId"]
            leg_idx = int(e["leg"])
            leg_row = legs_by_req[oid][leg_idx]
            req = requests[oid]
            has_summer = leg_row.get("truth.summerTyres") == "true" or bool(SUMMER_RE.search(req.get("note", "")))
            in_snow_place = in_forecast_at(at, {place})
            p_places, d_places, _ = gig_places(e["gigId"])
            in_snow_gig = in_forecast_at(at, set(p_places) | set(d_places))
            vf_by_reason[reason] += 1
            if in_snow_gig:
                vf_snow_by_reason[reason] += 1
            visit_fails.append({
                "at": at,
                "hour": (at % DAY) // HOUR,
                "reason": reason,
                "place": place,
                "orderId": oid,
                "in_snow_place": in_snow_place,
                "in_snow_gig": in_snow_gig,
                "has_summer": has_summer,
            })
        elif k == "ledger":
            if e["line.kind"] in ("late_refund", "undelivered_penalty") and e["line.orderId"]:
                late_order_ids.add(e["line.orderId"])

    late_details = []
    summer_won = []
    won_by_day = collections.Counter()
    won_long_haul = 0
    for oid, wo in won_orders.items():
        won_by_day[wo["at"] // DAY] += 1
        req = requests[oid]
        lrows = legs_by_req[oid]
        p_set = {l["pickup.placeId"] for l in lrows}
        d_set = {l["delivery.placeId"] for l in lrows}
        all_set = p_set | d_set
        drive_min = sum(roads[(l["pickup.placeId"], l["delivery.placeId"])][1] for l in lrows)
        if drive_min > 300:
            won_long_haul += 1
        ready_at = max(int(req["arrivedAt"]), max(int(l["pickup.window.from"]) for l in lrows))
        dl = wo["deadline"]
        overlaps_snow = window_overlaps_forecast(ready_at, dl, all_set)
        overlaps_snow_pickup = window_overlaps_forecast(ready_at, dl, p_set)
        overlaps_snow_deliv = window_overlaps_forecast(ready_at, dl, d_set)
        has_summer_truth = any(l.get("truth.summerTyres") == "true" for l in lrows)
        has_summer_note = bool(SUMMER_RE.search(req.get("note", "")))
        has_summer = has_summer_truth or has_summer_note
        ord_drops = [d for d in drops if oid in d["oids"]]
        ord_vfs = [v for v in visit_fails if v["orderId"] == oid]

        info = {
            "oid": oid,
            "option": wo["option"],
            "pickup": lrows[0]["pickup.placeId"],
            "delivery": lrows[-1]["delivery.placeId"],
            "drive_min": drive_min,
            "ready_at": ready_at,
            "deadline": dl,
            "overlaps_snow": overlaps_snow,
            "overlaps_snow_pickup": overlaps_snow_pickup,
            "overlaps_snow_deliv": overlaps_snow_deliv,
            "has_summer": has_summer,
            "n_drops": len(ord_drops),
            "n_snow_drops": sum(1 for d in ord_drops if d["in_snow_any_now"]),
            "n_vfs": len(ord_vfs),
            "is_late": oid in late_order_ids,
        }
        if has_summer:
            summer_won.append(info)
        if oid in late_order_ids:
            late_details.append(info)

    return {
        "seed": w["seed"],
        "wid": w["wid"],
        "n_drivers": len(w["drivers"]),
        "cap_supply30": w["supply30"].get("helsinki", 0),
        "forecasts": forecasts,
        "n_won": len(won_orders),
        "won_by_day": won_by_day,
        "won_long_haul": won_long_haul,
        "expired_gigs": expired_gigs,
        "n_drops": len(drops),
        "drops": drops,
        "drops_by_hour": drops_by_hour,
        "drops_snow_by_hour": drops_snow_by_hour,
        "drops_snow_pk_by_hour": drops_snow_pk_by_hour,
        "visit_fails": visit_fails,
        "vf_by_reason": vf_by_reason,
        "vf_snow_by_reason": vf_snow_by_reason,
        "late_details": late_details,
        "summer_won": summer_won,
    }


def pool_class(w: dict, place: str) -> str:
    s30 = w["supply30"][place]
    s55 = w["supply55"][place]
    s70 = w["supply70"][place]
    if s30 >= 100:
        return "100+ within 30 km"
    if s30 >= 30:
        return "30-99 within 30 km"
    if s55 >= 30:
        return "ring 30+ within 55 km"
    if s70 >= 30:
        return "ext_ring 30+ within 70 km"
    return "<30 within 55 km (outside 70 km)"


def is_option_declined(req: dict[str, str], opt: str) -> bool:
    dl = req.get(f"{opt}.deadline", "")
    if not dl:
        return False
    qc = req.get(f"{opt}.quoteCents", "")
    lp = req.get(f"{opt}.listPriceCents", "")
    if not qc:
        return True
    return int(qc) / int(lp) >= 3.0


def is_request_fully_declined(req: dict[str, str]) -> bool:
    offered = [opt for opt in OPTS if req.get(f"{opt}.deadline", "")]
    return bool(offered) and all(is_option_declined(req, opt) for opt in offered)


def analyze_r11_world(w: dict) -> dict:
    requests = w["requests"]
    legs_by_req = w["legs_by_req"]
    roads = w["roads"]
    line_km = w["line_km"]
    events = w["events"]

    won_orders = []
    delivered_at: dict[tuple[str, int], int] = {}
    for e in events:
        if e["kind"] == "delivered":
            delivered_at[(e["orderId"], int(e["leg"]))] = int(e["at"])
    for e in events:
        if e["kind"] == "order_won":
            oid = e["order.id"]
            lrows = legs_by_req[oid]
            p_place = lrows[0]["pickup.placeId"]
            d_place = lrows[-1]["delivery.placeId"]
            drive_min = sum(roads[(l["pickup.placeId"], l["delivery.placeId"])][1] for l in lrows)
            if len(lrows) == 2:
                drive_min += roads[(lrows[0]["delivery.placeId"], lrows[1]["pickup.placeId"])][1]
            arr = int(requests[oid]["arrivedAt"])
            ready = max(arr, int(lrows[0]["pickup.window.from"]))
            dl = int(e["order.deadline"])
            act_deliv = delivered_at.get((oid, len(lrows) - 1))
            won_orders.append({
                "id": oid,
                "option": e["order.option"],
                "pickup": p_place,
                "delivery": d_place,
                "drive_min": drive_min,
                "ready": ready,
                "deadline": dl,
                "ready_day": ready // DAY,
                "dl_day": dl // DAY,
                "delivered_at": act_deliv,
                "deliv_day": (act_deliv // DAY) if act_deliv is not None else (dl // DAY),
            })

    req_declined_by_pool_opt = collections.Counter()
    opt_declined_by_pool_opt = collections.Counter()
    req_declined_counts_by_pool = collections.Counter()
    req_total_counts_by_pool = collections.Counter()

    declined_slow_reqs = []

    for rid, req in requests.items():
        lrows = legs_by_req[rid]
        p_place = lrows[0]["pickup.placeId"]
        d_place = lrows[-1]["delivery.placeId"]
        p_pool = pool_class(w, p_place)
        s55_lt30 = w["supply55"][p_place] < 30
        req_total_counts_by_pool[p_pool] += 1
        fully_decl = is_request_fully_declined(req)
        if fully_decl:
            req_declined_counts_by_pool[p_pool] += 1
            if s55_lt30:
                req_declined_counts_by_pool["ALL <30 within 55 km"] += 1
        if s55_lt30:
            req_total_counts_by_pool["ALL <30 within 55 km"] += 1

        drive_min = sum(roads[(l["pickup.placeId"], l["delivery.placeId"])][1] for l in lrows)
        if len(lrows) == 2:
            drive_min += roads[(lrows[0]["delivery.placeId"], lrows[1]["pickup.placeId"])][1]
        arr = int(req["arrivedAt"])
        ready = max(arr, int(lrows[0]["pickup.window.from"]))

        slow_deadlines = []
        for opt in OPTS:
            dl_str = req.get(f"{opt}.deadline", "")
            if not dl_str:
                continue
            decl = is_option_declined(req, opt)
            if decl:
                opt_declined_by_pool_opt[(p_pool, opt)] += 1
                if s55_lt30:
                    opt_declined_by_pool_opt[("ALL <30 within 55 km", opt)] += 1
            if fully_decl:
                req_declined_by_pool_opt[(p_pool, opt)] += 1
                if s55_lt30:
                    req_declined_by_pool_opt[("ALL <30 within 55 km", opt)] += 1
            if opt in ("next_day", "within_3_days") and decl:
                slow_deadlines.append((opt, int(dl_str)))

        if fully_decl and slow_deadlines:
            best_opt, best_dl = max(slow_deadlines, key=lambda x: x[1])
            declined_slow_reqs.append({
                "id": rid,
                "pickup": p_place,
                "delivery": d_place,
                "pool": p_pool,
                "s55_lt30": s55_lt30,
                "drive_min": drive_min,
                "ready": ready,
                "ready_day": ready // DAY,
                "deadline": best_dl,
                "dl_day": best_dl // DAY,
                "opt": best_opt,
            })

    # Upper bound (any won order matches) and 1-to-1 greedy matching (each won order used at most once)
    chained_with_won = 0
    chained_with_won_by_pool = collections.Counter()
    used_won_ids: set[str] = set()
    chained_1to1 = 0
    chained_1to1_by_pool = collections.Counter()

    for dreq in declined_slow_reqs:
        pb = dreq["pickup"]
        drive_b = dreq["drive_min"]
        day_b = dreq["ready_day"]
        dl_b = dreq["deadline"]
        matching_wos = []
        for wo in won_orders:
            da = wo["delivery"]
            if line_km[(da, pb)] > 15.0:
                continue
            deadhead = roads[(da, pb)][1]
            total_drive = wo["drive_min"] + deadhead + drive_b
            if total_drive > 12 * HOUR:
                continue
            wo_day = wo["deliv_day"]
            if not (wo_day == day_b or next_bday(wo_day) == day_b or wo["ready_day"] == day_b or next_bday(wo["ready_day"]) == day_b):
                continue
            earliest_finish_a = wo["ready"] + wo["drive_min"]
            start_b = max(dreq["ready"], earliest_finish_a + deadhead)
            if start_b + drive_b <= dl_b:
                matching_wos.append((line_km[(da, pb)], total_drive, wo["id"]))
        if matching_wos:
            chained_with_won += 1
            chained_with_won_by_pool[dreq["pool"]] += 1
            if dreq["s55_lt30"]:
                chained_with_won_by_pool["ALL <30 within 55 km"] += 1
            matching_wos.sort()
            for _, _, wid in matching_wos:
                if wid not in used_won_ids:
                    used_won_ids.add(wid)
                    chained_1to1 += 1
                    chained_1to1_by_pool[dreq["pool"]] += 1
                    if dreq["s55_lt30"]:
                        chained_1to1_by_pool["ALL <30 within 55 km"] += 1
                    break

    round_trip_15km = 0
    round_trip_30km = 0
    rt15_by_pool = collections.Counter()
    used_rt_ids: set[str] = set()
    rt15_disjoint_reqs = 0

    for a in declined_slow_reqs:
        has_15 = False
        has_30 = False
        partner_15 = None
        for b in declined_slow_reqs:
            if a["id"] == b["id"]:
                continue
            if abs(a["ready_day"] - b["ready_day"]) > 1 and next_bday(a["ready_day"]) != b["ready_day"] and next_bday(b["ready_day"]) != a["ready_day"]:
                continue
            for first, second in ((a, b), (b, a)):
                p1, d1 = first["pickup"], first["delivery"]
                p2, d2 = second["pickup"], second["delivery"]
                if line_km[(d1, p2)] <= 30.0 and line_km[(d2, p1)] <= 30.0:
                    dh = roads[(d1, p2)][1]
                    tot_drv = first["drive_min"] + dh + second["drive_min"]
                    if tot_drv <= 12 * HOUR:
                        t_arr_p2 = max(second["ready"], first["ready"] + first["drive_min"] + dh)
                        if first["ready"] + first["drive_min"] <= first["deadline"] and t_arr_p2 + second["drive_min"] <= second["deadline"]:
                            has_30 = True
                            if line_km[(d1, p2)] <= 15.0 and line_km[(d2, p1)] <= 15.0:
                                has_15 = True
                                if partner_15 is None and b["id"] not in used_rt_ids:
                                    partner_15 = b["id"]
        if has_15:
            round_trip_15km += 1
            rt15_by_pool[a["pool"]] += 1
            if a["s55_lt30"]:
                rt15_by_pool["ALL <30 within 55 km"] += 1
            if a["id"] not in used_rt_ids and partner_15 is not None:
                used_rt_ids.add(a["id"])
                used_rt_ids.add(partner_15)
                rt15_disjoint_reqs += 2
        if has_30:
            round_trip_30km += 1

    return {
        "seed": w["seed"],
        "wid": w["wid"],
        "req_total_counts_by_pool": req_total_counts_by_pool,
        "req_declined_counts_by_pool": req_declined_counts_by_pool,
        "req_declined_by_pool_opt": req_declined_by_pool_opt,
        "opt_declined_by_pool_opt": opt_declined_by_pool_opt,
        "n_declined_slow": len(declined_slow_reqs),
        "chained_with_won": chained_with_won,
        "chained_with_won_by_pool": chained_with_won_by_pool,
        "chained_1to1": chained_1to1,
        "chained_1to1_by_pool": chained_1to1_by_pool,
        "round_trip_15km": round_trip_15km,
        "round_trip_30km": round_trip_30km,
        "rt15_disjoint_reqs": rt15_disjoint_reqs,
        "rt15_by_pool": rt15_by_pool,
    }


def print_r7_report(label: str, worlds: list[dict], r7_list: list[dict]) -> None:
    print("=" * 100)
    print(f"R7 REPORT: {label} ({len(worlds)} worlds)")
    print("=" * 100)

    print()
    print("--- 1. All Forecast Events ---")
    for r7 in sorted(r7_list, key=lambda x: x["seed"]):
        for f in r7["forecasts"]:
            print(
                f"  {r7['seed']} ({r7['wid']}): at={fmt_min(f['at'])} "
                f"window=[{fmt_min(f['from'])} .. {fmt_min(f['to'])}] "
                f"places={f['place_list']} text={f['text']!r}"
            )

    print()
    print("--- 2. World Summary: Drops, Visit Fails, Late Orders, and Snow Overlap ---")
    hdr = (
        f"{'Seed':<8} {'Drv':>4} {'Cap30':>5} {'Won':>4} {'W>5h':>5} {'Drops':>6} {'DrpSnPk':>7} {'DrpSnAny':>8} {'DrpSnWin':>8} "
        f"{'VF_NR':>5} {'VF_CL':>5} {'VF_NP':>5} {'VF_Sn':>5} "
        f"{'Late':>5} {'Lt>5h':>5} {'LtSnow':>6} {'LtSumr':>6} {'SumrWon':>7}"
    )
    print(hdr)
    print("-" * len(hdr))
    for r7 in sorted(r7_list, key=lambda x: x["seed"]):
        n_drp_snow_pk = sum(1 for d in r7["drops"] if d["in_snow_pickup_now"])
        n_drp_snow_now = sum(1 for d in r7["drops"] if d["in_snow_any_now"])
        n_drp_snow_win = sum(1 for d in r7["drops"] if d["in_snow_window"])
        vf_nr = r7["vf_by_reason"]["not_ready"]
        vf_cl = r7["vf_by_reason"]["closed"]
        vf_np = r7["vf_by_reason"]["no_plates"]
        vf_sn = sum(r7["vf_snow_by_reason"].values())
        n_late = len(r7["late_details"])
        n_late_lh = sum(1 for l in r7["late_details"] if l["drive_min"] > 300)
        n_late_snow = sum(1 for l in r7["late_details"] if l["overlaps_snow"])
        n_late_sumr = sum(1 for l in r7["late_details"] if l["has_summer"])
        n_sumr_won = len(r7["summer_won"])
        print(
            f"{r7['seed']:<8} {r7['n_drivers']:>4} {r7['cap_supply30']:>5} {r7['n_won']:>4} {r7['won_long_haul']:>5} "
            f"{r7['n_drops']:>6} {n_drp_snow_pk:>7} {n_drp_snow_now:>8} {n_drp_snow_win:>8} "
            f"{vf_nr:>5} {vf_cl:>5} {vf_np:>5} {vf_sn:>5} "
            f"{n_late:>5} {n_late_lh:>5} {n_late_snow:>6} {n_late_sumr:>6} {n_sumr_won:>7}"
        )

    print()
    print("--- 3. Drops by Hour of Day (dev-07 vs other worlds mean) ---")
    dev07 = next((r for r in r7_list if r["seed"] == "dev-07"), None)
    others = [r for r in r7_list if r["seed"] != "dev-07"]
    if dev07 and others:
        hours = sorted(set(dev07["drops_by_hour"].keys()) | {h for r in others for h in r["drops_by_hour"].keys()})
        print(f"{'Hour':<6} {'dev-07 drops':>14} {'dev-07 in_snow':>15} {'Others mean':>14} {'Others median':>14}")
        for h in hours:
            d7 = dev07["drops_by_hour"][h]
            d7s = dev07["drops_snow_by_hour"][h]
            oth_vals = [r["drops_by_hour"][h] for r in others]
            print(f"{h:02d}:00  {d7:>14} {d7s:>15} {st.mean(oth_vals):>14.2f} {st.median(oth_vals):>14.1f}")

        print()
        print("--- 4. What Distinguishes dev-07's Drops vs Ordinary Worlds? ---")
        d7_by_day = collections.Counter(d["day"] for d in dev07["drops"])
        d7_mid_by_day = collections.Counter(d["day"] for d in dev07["drops"] if d["hour"] == 0)
        oth_by_day = {d: st.mean([sum(1 for x in r["drops"] if x["day"] == d) for r in others]) for d in range(8)}
        oth_mid_by_day = {d: st.mean([sum(1 for x in r["drops"] if x["day"] == d and x["hour"] == 0) for r in others]) for d in range(8)}
        print("Drops by day (total / at 00:00 midnight) and Won Orders by day:")
        for d in range(8):
            if d7_by_day[d] or oth_by_day[d] or dev07["won_by_day"][d]:
                oth_won = st.mean([r["won_by_day"][d] for r in others])
                print(
                    f"  {DAYS[d]:<5}: dev-07 drops={d7_by_day[d]:>2} (00:00={d7_mid_by_day[d]:>2}) | "
                    f"others drops={oth_by_day[d]:>5.2f} (00:00={oth_mid_by_day[d]:>4.2f}) | "
                    f"dev-07 won={dev07['won_by_day'][d]:>3} vs others won={oth_won:>5.1f}"
                )

        d7_pk = collections.Counter(d["pickup"] for d in dev07["drops"])
        oth_pk = collections.Counter(d["pickup"] for r in others for d in r["drops"])
        print("Top pickup towns for drops in dev-07 (vs mean across other worlds):")
        for town, cnt in d7_pk.most_common(12):
            print(f"  {town:<16}: dev-07={cnt:>3} ({cnt/len(dev07['drops']):.1%})  others_mean={oth_pk[town]/len(others):.2f}")

        d7_opt = collections.Counter(d["option"] for d in dev07["drops"])
        oth_opt = collections.Counter(d["option"] for r in others for d in r["drops"])
        print("Drops by option:")
        for opt in OPTS:
            print(f"  {opt:<15}: dev-07={d7_opt[opt]:>3} ({d7_opt[opt]/len(dev07['drops']):.1%})  others_mean={oth_opt[opt]/len(others):.2f}")

        d7_drv = [d["drive_min"] for d in dev07["drops"]]
        oth_drv = [d["drive_min"] for r in others for d in r["drops"]]
        print(
            f"Drive minutes of dropped gigs: dev-07 mean={st.mean(d7_drv):.1f}m median={st.median(d7_drv):.1f}m "
            f"(>300m: {sum(1 for x in d7_drv if x > 300)}/{len(d7_drv)} = {sum(1 for x in d7_drv if x > 300)/len(d7_drv):.1%}); "
            f"others mean={st.mean(oth_drv):.1f}m median={st.median(oth_drv):.1f}m "
            f"(>300m: {sum(1 for x in oth_drv if x > 300)}/{len(oth_drv)} = {sum(1 for x in oth_drv if x > 300)/len(oth_drv):.1%})"
        )

        d7_held = [d["held_min"] / 60.0 for d in dev07["drops"]]
        oth_held = [d["held_min"] / 60.0 for r in others for d in r["drops"]]
        print(
            f"Hours held before drop: dev-07 mean={st.mean(d7_held):.2f}h median={st.median(d7_held):.2f}h "
            f"(>6h: {sum(1 for x in d7_held if x > 6)}/{len(d7_held)}); "
            f"others mean={st.mean(oth_held):.2f}h median={st.median(oth_held):.2f}h "
            f"(>6h: {sum(1 for x in oth_held if x > 6)}/{len(oth_held)})"
        )

        d7_fr = [d["fee_ratio"] for d in dev07["drops"]]
        oth_fr = [d["fee_ratio"] for r in others for d in r["drops"]]
        print(
            f"Booked fee / typical fee on dropped gigs: dev-07 mean={st.mean(d7_fr):.3f} median={st.median(d7_fr):.3f} "
            f"(<=0.90: {sum(1 for x in d7_fr if x <= 0.90)}/{len(d7_fr)}); "
            f"others mean={st.mean(oth_fr):.3f} median={st.median(oth_fr):.3f} "
            f"(<=0.90: {sum(1 for x in oth_fr if x <= 0.90)}/{len(oth_fr)})"
        )

        print()
        print("--- 5. Late Orders in dev-07 Detail ---")
        for l in dev07["late_details"]:
            print(
                f"  {l['oid']} opt={l['option']:<13} {l['pickup']}->{l['delivery']} ({l['drive_min']}m) "
                f"ready={fmt_min(l['ready_at'])} dl={fmt_min(l['deadline'])} "
                f"snow_overlap={l['overlaps_snow']} (pk={l['overlaps_snow_pickup']}, dl={l['overlaps_snow_deliv']}) "
                f"summer={l['has_summer']} drops={l['n_drops']} (snow_drops={l['n_snow_drops']}) vfs={l['n_vfs']}"
            )


def print_r11_report(label: str, r11_list: list[dict]) -> None:
    n_w = len(r11_list)
    print()
    print("=" * 100)
    print(f"R11 REPORT: {label} ({n_w} worlds, mean per week)")
    print("=" * 100)

    pools = [
        "ALL <30 within 55 km",
        "<30 within 55 km (outside 70 km)",
        "ext_ring 30+ within 70 km",
        "ring 30+ within 55 km",
        "30-99 within 30 km",
        "100+ within 30 km",
    ]

    print()
    print("--- 1. Declined Requests & Options by Pickup Supply Pool (mean per week) ---")
    hdr = (
        f"{'Pickup Supply Pool':<34} {'TotReqs':>8} {'DeclReqs':>9} "
        f"{'Decl_SD (req/opt)':>18} {'Decl_ND (req/opt)':>18} {'Decl_W3D (req/opt)':>19}"
    )
    print(hdr)
    print("-" * len(hdr))
    for p in pools:
        tot_r = sum(r["req_total_counts_by_pool"][p] for r in r11_list) / n_w
        dec_r = sum(r["req_declined_counts_by_pool"][p] for r in r11_list) / n_w
        sd_r = sum(r["req_declined_by_pool_opt"][(p, "same_day")] for r in r11_list) / n_w
        sd_o = sum(r["opt_declined_by_pool_opt"][(p, "same_day")] for r in r11_list) / n_w
        nd_r = sum(r["req_declined_by_pool_opt"][(p, "next_day")] for r in r11_list) / n_w
        nd_o = sum(r["opt_declined_by_pool_opt"][(p, "next_day")] for r in r11_list) / n_w
        w3_r = sum(r["req_declined_by_pool_opt"][(p, "within_3_days")] for r in r11_list) / n_w
        w3_o = sum(r["opt_declined_by_pool_opt"][(p, "within_3_days")] for r in r11_list) / n_w
        print(
            f"{p:<34} {tot_r:>8.1f} {dec_r:>9.1f} "
            f"{f'{sd_r:.1f} / {sd_o:.1f}':>18} {f'{nd_r:.1f} / {nd_o:.1f}':>18} {f'{w3_r:.1f} / {w3_o:.1f}':>19}"
        )

    print()
    print("--- 2. Hitch & Round-Trip Pairing Potential for Declined Slow Requests (mean per week) ---")
    tot_slow = sum(r["n_declined_slow"] for r in r11_list) / n_w
    tot_won_chain = sum(r["chained_with_won"] for r in r11_list) / n_w
    tot_won_1to1 = sum(r["chained_1to1"] for r in r11_list) / n_w
    tot_rt15 = sum(r["round_trip_15km"] for r in r11_list) / n_w
    tot_rt15_disjoint = sum(r["rt15_disjoint_reqs"] for r in r11_list) / n_w
    tot_rt30 = sum(r["round_trip_30km"] for r in r11_list) / n_w
    print(f"Total fully-declined requests with slow option(s): {tot_slow:.1f} / week")
    print(
        f"  -> With >=1 WON order delivering <=15 km same/prev business day (<=12h drive): "
        f"{tot_won_chain:.1f} / week ({tot_won_chain/tot_slow:.1%}); 1-to-1 disjoint pairs: {tot_won_1to1:.1f} / week"
    )
    print(
        f"  -> With >=1 DECLINED slow partner as round trip (<=15 km ends, <=12h drive): "
        f"{tot_rt15:.1f} / week ({tot_rt15/tot_slow:.1%}); disjoint round-trip requests: {tot_rt15_disjoint:.1f} ({tot_rt15_disjoint/2:.1f} pairs) / week"
    )
    print(
        f"  -> With >=1 DECLINED slow partner as round trip (<=30 km ends, <=12h drive): "
        f"{tot_rt30:.1f} / week ({tot_rt30/tot_slow:.1%})"
    )

    print()
    print("Breakdown by Pickup Supply Pool (mean per week):")
    print(f"{'Pickup Supply Pool':<34} {'Won>=1 (<=15km)':>16} {'Won 1-to-1':>12} {'RT>=1 (<=15km)':>16}")
    print("-" * 82)
    for p in pools:
        wc = sum(r["chained_with_won_by_pool"][p] for r in r11_list) / n_w
        w1 = sum(r["chained_1to1_by_pool"][p] for r in r11_list) / n_w
        rt = sum(r["rt15_by_pool"][p] for r in r11_list) / n_w
        print(f"{p:<34} {wc:>16.1f} {w1:>12.1f} {rt:>16.1f}")


def main() -> None:
    paths = [Path(p) for p in sys.argv[1:]]
    if not paths:
        for p in ("/tmp/reveals-v3", "/tmp/reveals-n14-01"):
            if Path(p).exists():
                paths.append(Path(p))

    for root in paths:
        folders = sorted([d for d in root.iterdir() if d.is_dir() and d.name.startswith("reveal-")])
        worlds = [load_world(d) for d in folders]
        r7_list = [analyze_r7_world(w) for w in worlds]
        r11_list = [analyze_r11_world(w) for w in worlds]
        print_r7_report(str(root), worlds, r7_list)
        print_r11_report(str(root), r11_list)


if __name__ == "__main__":
    main()
