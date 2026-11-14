"""Slot-free analysis of Idea 26 (hitch-pairs) on Champion v3 reveals (/tmp/reveals-v3).

Measures:
1. Open (unbooked) lifetimes of single-car gigs on v3 by pickup supply pool and option.
2. How often won orders can pair with currently open, unbooked single-car gigs (at win time or after 20 daytime min).
3. How often declined thin-gate requests have a matching open, unbooked single-car gig at request arrival time `t`,
   both for `A (waiting) -> B (request)` and `B (request) -> A (waiting)`, and what happens when B wins 15 min later.
4. Opening-hours behavior and stated hours distributions in v3 reveals.
"""
from __future__ import annotations

import collections
import csv
import json
import math
import statistics as st
import sys
from pathlib import Path

csv.field_size_limit(10**9)

HOUR = 60
DAY = 24 * 60


def read_csv(folder: Path, name: str) -> list[dict[str, str]]:
    with open(folder / f"{name}.csv", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(h))


def daytime_minutes_between(t0: int, t1: int, day_start: int = 7 * 60, day_end: int = 22 * 60) -> int:
    if t1 <= t0:
        return 0
    total = 0
    d0, d1 = t0 // DAY, t1 // DAY
    for d in range(d0, d1 + 1):
        a = max(t0, d * DAY + day_start)
        b = min(t1, d * DAY + day_end)
        if b > a:
            total += b - a
    return total


def analyze_folder(folder: Path) -> None:
    wid = folder.name.removeprefix("reveal-")
    places = {p["id"]: (float(p["lat"]), float(p["lon"])) for p in read_csv(folder, "places")}
    line_km = {(a, b): haversine_km(places[a], places[b]) for a in places for b in places}
    roads = {(r["from"], r["to"]): (float(r["km"]), int(r["minutes"])) for r in read_csv(folder, "roads")}
    drivers = read_csv(folder, "drivers")
    homes = collections.Counter(d["homePlaceId"] for d in drivers)
    supply30 = {p: sum(n for h, n in homes.items() if line_km[(p, h)] <= 30.0) for p in places}
    supply55 = {p: sum(n for h, n in homes.items() if line_km[(p, h)] <= 55.0) for p in places}
    supply70 = {p: sum(n for h, n in homes.items() if line_km[(p, h)] <= 70.0) for p in places}

    requests = {r["id"]: r for r in read_csv(folder, "requests")}
    legs_by_req: dict[str, list[dict[str, str]]] = collections.defaultdict(list)
    for l in read_csv(folder, "legs"):
        legs_by_req[l["requestId"]].append(l)
    for rid in legs_by_req:
        legs_by_req[rid].sort(key=lambda x: int(x["leg"]))

    gigs = {g["id"]: g for g in read_csv(folder, "gigs")}
    events = read_csv(folder, "events")

    # Reconstruct exact open intervals [start, end) of every gig
    # A gig is posted at g["postedAt"]. When booked, it closes; if dropped/no_show, it reopens!
    # If withdrawn or expired, it closes permanently.
    gig_intervals: dict[str, list[tuple[int, int]]] = collections.defaultdict(list)
    open_since: dict[str, int] = {gid: int(g["postedAt"]) for gid, g in gigs.items()}
    first_book_wait: list[tuple[str, str, int]] = []
    seen_first_book: set[str] = set()

    won_orders: dict[str, dict] = {}
    for e in events:
        k = e["kind"]
        at = int(e["at"])
        if k == "order_won":
            oid = e["order.id"]
            lrows = legs_by_req[oid]
            won_orders[oid] = {
                "id": oid,
                "won_at": at,
                "option": e["order.option"],
                "deadline": int(e["order.deadline"]),
                "lastPickupAt": int(e["order.lastPickupAt"]),
                "legs": lrows,
                "pickup": lrows[0]["pickup.placeId"],
                "delivery": lrows[-1]["delivery.placeId"],
                "ready": max(at, int(lrows[0]["pickup.window.from"])),
                "drive": sum(roads[(l["pickup.placeId"], l["delivery.placeId"])][1] for l in lrows),
            }
        elif k == "gig_booked":
            gid = e["gigId"]
            if gid in open_since:
                t0 = open_since.pop(gid)
                gig_intervals[gid].append((t0, at))
                if gid not in seen_first_book:
                    seen_first_book.add(gid)
                    stops = json.loads(gigs[gid]["stops"])
                    oid0 = stops[0]["orderId"]
                    opt = won_orders.get(oid0, {}).get("option", "?")
                    pk = legs_by_req[oid0][0]["pickup.placeId"]
                    pool = "cap100+" if supply30[pk] >= 100 else ("mid30+" if supply30[pk] >= 30 else ("ring55" if supply55[pk] >= 22 else "ext/ret"))
                    first_book_wait.append((pool, opt, at - t0))
        elif k in ("gig_dropped", "no_show"):
            gid = e["gigId"]
            open_since[gid] = at
        elif k == "gig_expired":
            gid = e["gigId"]
            if gid in open_since:
                t0 = open_since.pop(gid)
                gig_intervals[gid].append((t0, at))

    for gid, t0 in open_since.items():
        # Check status in gigs.csv: if withdrawn, when was it withdrawn? Approximate with next gig of same order or end
        g = gigs[gid]
        stops = json.loads(g["stops"])
        oid0 = stops[0]["orderId"]
        later_posts = [
            int(g2["postedAt"])
            for gid2, g2 in gigs.items()
            if gid2 != gid and int(g2["postedAt"]) >= t0 and any(s["orderId"] == oid0 for s in json.loads(g2["stops"]))
        ]
        end_t = min(later_posts) if later_posts else (t0 + 60 if g["status"] == "withdrawn" else 10080)
        gig_intervals[gid].append((t0, end_t))

    print(f"==================== WORLD {wid} ====================")
    by_pool = collections.defaultdict(list)
    by_opt = collections.defaultdict(list)
    for pool, opt, w in first_book_wait:
        by_pool[pool].append(w)
        by_opt[opt].append(w)
    print("First-booking wait (min) by pool:")
    for pool, ws in sorted(by_pool.items()):
        gt20 = sum(1 for x in ws if x >= 20)
        gt60 = sum(1 for x in ws if x >= 60)
        print(f"  {pool:<10}: n={len(ws):>3} median={st.median(ws):>5.1f}m mean={st.mean(ws):>6.1f}m >=20m:{gt20:>3} ({gt20/len(ws):.1%}) >=60m:{gt60:>3}")
    print("First-booking wait (min) by option:")
    for opt, ws in sorted(by_opt.items()):
        gt20 = sum(1 for x in ws if x >= 20)
        print(f"  {opt:<14}: n={len(ws):>3} median={st.median(ws):>5.1f}m mean={st.mean(ws):>6.1f}m >=20m:{gt20:>3} ({gt20/len(ws):.1%})")

    # Build helper: single-car open gigs at time `t`
    single_gig_info = {}
    for gid, g in gigs.items():
        stops = json.loads(g["stops"])
        oids = list(dict.fromkeys(s["orderId"] for s in stops))
        if len(oids) == 1 and len(stops) == 2:
            oid = oids[0]
            if oid in won_orders:
                single_gig_info[gid] = won_orders[oid]

    def open_single_orders_at(t: int) -> list[tuple[str, dict, int]]:
        out = []
        seen_oids = set()
        for gid, wo in single_gig_info.items():
            for a, b in gig_intervals[gid]:
                if a <= t < b:
                    if wo["id"] not in seen_oids:
                        seen_oids.add(wo["id"])
                        out.append((gid, wo, a))
                    break
        return out

    # 1. Check (1) Pairing among already-won orders:
    # At each order_won (t = wo["won_at"]), or when a gig reaches 20 daytime min open, how many pairs exist?
    pairable_at_win = 0
    pairable_dir_ab = 0  # waiting A -> new B
    pairable_dir_ba = 0  # new B -> waiting A
    for oid, wo in sorted(won_orders.items(), key=lambda x: x[1]["won_at"]):
        if len(wo["legs"]) != 1:
            continue
        t = wo["won_at"]
        open_now = open_single_orders_at(t)
        matched_ab = False
        matched_ba = False
        for gid, other, posted_at in open_now:
            if other["id"] == oid:
                continue
            # Check A=other -> B=wo
            if line_km[(other["delivery"], wo["pickup"])] <= 15.0:
                dh = roads[(other["delivery"], wo["pickup"])][1]
                if other["drive"] + dh + wo["drive"] <= 12 * HOUR:
                    t_a_done = max(t, other["ready"]) + other["drive"]
                    if t_a_done + 150 <= other["deadline"]:
                        t_b_pick = max(wo["ready"], t_a_done + dh)
                        if t_b_pick + wo["drive"] + 150 <= wo["deadline"]:
                            matched_ab = True
            # Check A=wo -> B=other
            if line_km[(wo["delivery"], other["pickup"])] <= 15.0:
                dh = roads[(wo["delivery"], other["pickup"])][1]
                if wo["drive"] + dh + other["drive"] <= 12 * HOUR:
                    t_a_done = max(t, wo["ready"]) + wo["drive"]
                    if t_a_done + 150 <= wo["deadline"]:
                        t_b_pick = max(other["ready"], t_a_done + dh)
                        if t_b_pick + other["drive"] + 150 <= other["deadline"]:
                            matched_ba = True
        if matched_ab or matched_ba:
            pairable_at_win += 1
        if matched_ab:
            pairable_dir_ab += 1
        if matched_ba:
            pairable_dir_ba += 1
    print(f"(1) Won single-car orders with an open unbooked partner at win time: {pairable_at_win}/{len(won_orders)} (waiting->new: {pairable_dir_ab}, new->waiting: {pairable_dir_ba})")

    # 2. Check (2) Volume (`hitch_quote`):
    # Requests that fail the supply gate (gate_supply < 22 and not pass_ext_ring and not pass_return_hub)
    thin_reqs = 0
    thin_slow_reqs = 0
    match_open_at_arr = 0
    match_open_still_at_win = 0
    match_by_day = collections.Counter()
    for rid, req in sorted(requests.items(), key=lambda x: int(x[1]["arrivedAt"])):
        lrows = legs_by_req[rid]
        if len(lrows) != 1:
            continue
        pk = lrows[0]["pickup.placeId"]
        dlv = lrows[0]["delivery.placeId"]
        drv = roads[(pk, dlv)][1]
        if supply55[pk] >= 22:
            continue
        if supply70[pk] >= 30 and drv <= 220:
            continue
        if supply30[dlv] >= 200 and drv <= 180:
            continue
        thin_reqs += 1
        slow_opts = [(opt, int(req[f"{opt}.deadline"])) for opt in ("next_day", "within_3_days") if req.get(f"{opt}.deadline")]
        if not slow_opts:
            continue
        thin_slow_reqs += 1
        t_arr = int(req["arrivedAt"])
        t_win = int(req["respondBy"])
        ready_r = max(t_arr, int(lrows[0]["pickup.window.from"]))
        best_dl = max(dl for _, dl in slow_opts)
        if best_dl - ready_r - drv < 150 + 0.75 * drv:
            continue

        open_arr = open_single_orders_at(t_arr)
        open_win = {wo["id"] for _, wo, _ in open_single_orders_at(t_win)}
        matched_partners = []
        for gid, other, posted_at in open_arr:
            # Check A=other -> B=request (most common: dense A delivers near thin request pickup)
            ok = False
            if line_km[(other["delivery"], pk)] <= 15.0 and supply30[other["pickup"]] >= supply30[pk]:
                dh = roads[(other["delivery"], pk)][1]
                if other["drive"] + dh + drv <= 12 * HOUR:
                    t_a_done = max(t_arr, other["ready"]) + other["drive"]
                    if t_a_done + 150 <= other["deadline"]:
                        t_b_pick = max(ready_r, t_a_done + dh)
                        if t_b_pick + drv + 150 <= best_dl:
                            ok = True
            # Or A=request -> B=other (if request has more drivers, rare for thin)
            if not ok and line_km[(dlv, other["pickup"])] <= 15.0 and supply30[pk] >= supply30[other["pickup"]]:
                dh = roads[(dlv, other["pickup"])][1]
                if drv + dh + other["drive"] <= 12 * HOUR:
                    t_a_done = max(t_arr, ready_r) + drv
                    if t_a_done + 150 <= best_dl:
                        t_b_pick = max(other["ready"], t_a_done + dh)
                        if t_b_pick + other["drive"] + 150 <= other["deadline"]:
                            ok = True
            if ok:
                matched_partners.append(other["id"])
        if matched_partners:
            match_open_at_arr += 1
            match_by_day[t_arr // DAY] += 1
            if any(pid in open_win for pid in matched_partners):
                match_open_still_at_win += 1

    print(
        f"(2) Thin-gate 1-leg requests: {thin_reqs} (with slow opts: {thin_slow_reqs}) -> "
        f"match open unbooked gig at arrival: {match_open_at_arr} "
        f"(partner still unbooked 15m later at respondBy: {match_open_still_at_win}); by day={dict(sorted(match_by_day.items()))}"
    )

    # Also check: what do pickup.hours and delivery.hours look like in legs.csv?
    hours_samples = set()
    sat_open_cnt = 0
    tot_legs = 0
    for rid, lrows in legs_by_req.items():
        for l in lrows:
            tot_legs += 1
            for side in ("pickup", "delivery"):
                h_raw = l.get(f"{side}.hours", "")
                if h_raw:
                    h = json.loads(h_raw)
                    sat = h.get("saturday")
                    if sat and side == "pickup":
                        sat_open_cnt += 1
                    key = (h["opens"], h["closes"], tuple(h["weekdays"]), (sat["opens"], sat["closes"]) if sat else None)
                    hours_samples.add(key)
    print(f"Distinct stated OpeningHours patterns ({len(hours_samples)}), pickup saturday open={sat_open_cnt}/{tot_legs}:")
    for hs in sorted(hours_samples)[:10]:
        print(" ", hs)


def main() -> None:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/reveals-v3")
    for folder in sorted(root.iterdir()):
        if folder.is_dir() and folder.name.startswith("reveal-"):
            analyze_folder(folder)


if __name__ == "__main__":
    main()
