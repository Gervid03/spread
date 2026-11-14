"""Slot-free X-ray of dev-12 (runs/reveal-dev12-v4) for Route Network (Idea 31):
1. Driver supply by place (30km, 55km, 70km) and exact won / competitively-lost / declined request counts.
2. Breakdown of all declined requests on dev-12: which have an active BOOKED outbound car vs OPEN unbooked outbound car delivering within 15km / 30km, and destination supply class.
3. Open-gig waiting duration & homeward 2-car relay pairs among already-won orders on dev-12.
4. Organic multi-gig driver-days, post-booking app browsing, and 2nd-gig fee multiples.
"""
from __future__ import annotations

import csv
import json
import math
import statistics as st
import sys
from collections import Counter, defaultdict
from pathlib import Path

csv.field_size_limit(10**9)
OPTS = ("same_day", "next_day", "within_3_days")


def hav(a: tuple[float, float], b: tuple[float, float]) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(h))


def rd(d: Path, name: str) -> list[dict[str, str]]:
    with open(d / f"{name}.csv", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def is_declined(r: dict[str, str]) -> bool:
    quoted = []
    for k in OPTS:
        qc = r.get(f"{k}.quoteCents", "")
        lc = r.get(f"{k}.listPriceCents", "")
        if qc and lc:
            quoted.append(int(qc) / max(1, int(lc)))
    return bool(quoted) and min(quoted) >= 3.9


def has_slow_opt(r: dict[str, str]) -> bool:
    return bool(r.get("next_day.deadline") or r.get("within_3_days.deadline"))


def max_slow_dl(r: dict[str, str]) -> int:
    vals = [int(r[f"{k}.deadline"]) for k in ("next_day", "within_3_days") if r.get(f"{k}.deadline")]
    return max(vals) if vals else 0


def main(reveal_dir: str) -> None:
    d = Path(reveal_dir)
    places = {p["id"]: (float(p["lat"]), float(p["lon"])) for p in rd(d, "places")}
    line = {(a, b): hav(places[a], places[b]) for a in places for b in places}
    roads = {(r["from"], r["to"]): (float(r["km"]), int(r["minutes"])) for r in rd(d, "roads")}
    drivers = {x["id"]: x for x in rd(d, "drivers")}
    reqs = {r["id"]: r for r in rd(d, "requests")}
    legs_by_req = defaultdict(list)
    for l in rd(d, "legs"):
        legs_by_req[l["requestId"]].append(l)
    for ls in legs_by_req.values():
        ls.sort(key=lambda x: int(x["leg"]))
    gigs = {g["id"]: g for g in rd(d, "gigs")}
    events = rd(d, "events")

    homes = Counter(drv["homePlaceId"] for drv in drivers.values())
    sup30 = {p: sum(n for h, n in homes.items() if line[(p, h)] <= 30.0) for p in places}
    sup55 = {p: sum(n for h, n in homes.items() if line[(p, h)] <= 55.0) for p in places}
    sup70 = {p: sum(n for h, n in homes.items() if line[(p, h)] <= 70.0) for p in places}

    print(f"=== 1. DEV-12 REQUEST OUTCOMES BY PICKUP (total reqs={len(reqs)}, drivers={len(drivers)}) ===")
    tot_won = tot_clost = tot_decl = 0
    for p, cnt in sorted(sup30.items(), key=lambda kv: (-kv[1], -sup55[kv[0]])):
        r_all = [r for rid, r in reqs.items() if legs_by_req[rid][0]["pickup.placeId"] == p]
        won = sum(1 for r in r_all if r["outcome"] == "won")
        decl = sum(1 for r in r_all if r["outcome"] == "lost" and is_declined(r))
        clost = len(r_all) - won - decl
        tot_won += won
        tot_clost += clost
        tot_decl += decl
        print(
            f"  {p:<14} s30={cnt:>3} s55={sup55[p]:>3} s70={sup70[p]:>3} | "
            f"reqs={len(r_all):>3} won={won:>3} comp_lost={clost:>3} decl={decl:>3}"
        )
    print(f"  TOTAL: reqs={len(reqs)} won={tot_won} comp_lost={tot_clost} decl={tot_decl}")

    # Reconstruct gig intervals: posted_at, booked_at, done_at, withdrawn/dropped
    gig_stops = {gid: json.loads(g["stops"]) for gid, g in gigs.items()}
    gig_posted = {gid: int(g["postedAt"]) for gid, g in gigs.items()}
    gig_booked_at: dict[str, tuple[str, int, int]] = {}
    gig_closed_at: dict[str, int] = {}
    gig_done_at: dict[str, int] = {}
    active_book: dict[str, tuple[str, int, int]] = {}

    for e in events:
        at = int(e["at"])
        k = e["kind"]
        if k == "gig_booked":
            gid = e["gigId"]
            gig_booked_at[gid] = (e["driverId"], at, int(e["feeCents"]))
            active_book[gid] = (e["driverId"], at, int(e["feeCents"]))
        elif k in ("gig_dropped", "no_show", "gig_expired"):
            gid = e["gigId"]
            active_book.pop(gid, None)
            gig_closed_at.setdefault(gid, at)
        elif k == "delivered":
            oid, leg_i = e["orderId"], int(e["leg"])
            for gid, _ in list(active_book.items()):
                st_list = gig_stops[gid]
                last_s = st_list[-1]
                if last_s["orderId"] == oid and int(last_s["leg"]) == leg_i and last_s["kind"] == "delivery":
                    gig_done_at[gid] = at
                    active_book.pop(gid, None)

    # Check open-board wait times for single-car gigs
    waits_slow = []
    waits_sd = []
    for gid, g in gigs.items():
        st_list = gig_stops[gid]
        oids = list(dict.fromkeys(s["orderId"] for s in st_list))
        if len(oids) == 1 and gid in gig_booked_at:
            w = gig_booked_at[gid][1] - gig_posted[gid]
            opt = reqs[oids[0]]["option"]
            if opt == "same_day":
                waits_sd.append(w)
            else:
                waits_slow.append(w)
    print("=== 2. SINGLE-CAR GIG WAIT TIME BEFORE BOOKING ===")
    print(f"  slow (n={len(waits_slow)}): median={st.median(waits_slow):.0f}m, >=20m: {sum(w>=20 for w in waits_slow)} ({100*sum(w>=20 for w in waits_slow)/max(1,len(waits_slow)):.1f}%)")
    print(f"  same_day (n={len(waits_sd)}): median={st.median(waits_sd):.0f}m, >=20m: {sum(w>=20 for w in waits_sd)} ({100*sum(w>=20 for w in waits_sd)/max(1,len(waits_sd)):.1f}%)")

    # Build gig summary records for sponsor checks at request arrival time
    gig_info = []
    for gid, g in gigs.items():
        st_list = gig_stops[gid]
        if not st_list:
            continue
        p0 = legs_by_req[st_list[0]["orderId"]][int(st_list[0]["leg"])]["pickup.placeId"]
        dN = legs_by_req[st_list[-1]["orderId"]][int(st_list[-1]["leg"])]["delivery.placeId"]
        wfrom = int(legs_by_req[st_list[0]["orderId"]][int(st_list[0]["leg"])]["pickup.window.from"])
        # road dur
        pls = [
            legs_by_req[s["orderId"]][int(s["leg"])]["pickup.placeId" if s["kind"] == "pickup" else "delivery.placeId"]
            for s in st_list
        ]
        dur = sum(roads[(pls[i], pls[i + 1])][1] for i in range(len(pls) - 1))
        pat = gig_posted[gid]
        bat = gig_booked_at[gid][1] if gid in gig_booked_at else None
        did = gig_booked_at[gid][0] if gid in gig_booked_at else None
        home = drivers[did]["homePlaceId"] if did else None
        done = gig_done_at.get(gid)
        closed = gig_closed_at.get(gid, 999999)
        gig_info.append({
            "gid": gid, "p0": p0, "dN": dN, "wfrom": wfrom, "dur": dur,
            "pat": pat, "bat": bat, "did": did, "home": home, "done": done, "closed": closed,
        })

    # Inspect declined slow requests at arrival time `at`
    decl_slow = [
        r for r in reqs.values()
        if r["outcome"] == "lost" and is_declined(r) and has_slow_opt(r)
    ]
    print(f"=== 3. DECLINED SLOW REQUESTS ON DEV-12 (n={len(decl_slow)} of {tot_decl} total declines) ===")
    for km_lim in (15.0, 30.0):
        c_booked = c_open = c_either = c_repat_s30 = c_repat_s55 = 0
        lanes = Counter()
        for r in decl_slow:
            rid = r["id"]
            at = int(r["arrivedAt"])
            ls = legs_by_req[rid]
            pick = ls[0]["pickup.placeId"]
            dest = ls[-1]["delivery.placeId"]
            drv = sum(roads[(x["pickup.placeId"], x["delivery.placeId"])][1] for x in ls)
            dl = max_slow_dl(r)
            ready = max(at, int(ls[0]["pickup.window.from"]))
            if dl - ready - drv < 150 + int(0.75 * drv):
                continue

            has_b = False
            has_o = False
            has_hb = False
            for gi in gig_info:
                if line[(gi["dN"], pick)] > km_lim:
                    continue
                # Check if gi is BOOKED and not yet finished at `at`
                if gi["bat"] is not None and gi["bat"] <= at and (gi["done"] is None or gi["done"] >= at - 30) and gi["closed"] > at:
                    p_fin = max(gi["bat"], gi["wfrom"]) + gi["dur"]
                    reach = max(at, p_fin) + roads[(gi["dN"], pick)][1]
                    if max(reach, ready) + drv + 150 <= dl:
                        has_b = True
                        if gi["home"] and line[(gi["home"], dest)] <= 30.0:
                            has_hb = True
                # Check if gi is OPEN unbooked at `at`
                elif gi["pat"] <= at and (gi["bat"] is None or gi["bat"] > at) and gi["closed"] > at:
                    p_fin = max(at, gi["wfrom"]) + gi["dur"]
                    reach = p_fin + roads[(gi["dN"], pick)][1]
                    if max(reach, ready) + drv + 150 <= dl and sup30[gi["p0"]] >= 22:
                        has_o = True
                        if line[(gi["p0"], dest)] <= 55.0:
                            has_hb = True

            if has_b:
                c_booked += 1
            if has_o:
                c_open += 1
            if has_b or has_o:
                c_either += 1
                if sup30[dest] >= 30 or has_hb:
                    c_repat_s30 += 1
                    lanes[f"{pick}[{sup30[pick]}]->{dest}[{sup30[dest]}] ({drv}m)"] += 1
                if sup55[dest] >= 30 or has_hb:
                    c_repat_s55 += 1
        print(
            f"  within {km_lim:.0f}km: booked_sponsor={c_booked}, open_sponsor={c_open}, "
            f"either={c_either} | repat(dest_s30>=30 or HB)={c_repat_s30}, repat(dest_s55>=30 or HB)={c_repat_s55}"
        )
        if km_lim == 25.0 or km_lim == 30.0:
            print("    Top repatriating declined lanes:", lanes.most_common(12))


if __name__ == "__main__":
    main(sys.argv[1])
