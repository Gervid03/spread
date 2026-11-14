"""Quantify exact fee savings opportunities across the 4 pillars on dev-09 reveal."""
from __future__ import annotations

import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
REV = REPO / "runs" / "reveal-dev09"


def main() -> None:
    reqs = {r["id"]: r for r in csv.DictReader((REV / "requests.csv").open())}
    gigs = {g["id"]: g for g in csv.DictReader((REV / "gigs.csv").open())}
    events = list(csv.DictReader((REV / "events.csv").open()))
    views = list(csv.DictReader((REV / "views.csv").open()))
    drivers = {d["id"]: d for d in csv.DictReader((REV / "drivers.csv").open())}
    coords = {p["id"]: (float(p["lat"]), float(p["lon"])) for p in csv.DictReader((REV / "places.csv").open())}
    legs_by_req = defaultdict(list)
    for l in csv.DictReader((REV / "legs.csv").open()):
        legs_by_req[l["requestId"]].append(l)

    def line_km(a: str, b: str) -> float:
        lat1, lon1 = coords[a]
        lat2, lon2 = coords[b]
        dx = (lon2 - lon1) * math.cos(math.radians((lat1 + lat2) / 2)) * 111.32
        dy = (lat2 - lat1) * 110.574
        return math.hypot(dx, dy)

    # 1. Dropped gigs: booked_1 vs schedule at drop vs booked_2
    ev_by_gig = defaultdict(list)
    for e in events:
        if e.get("gigId"):
            ev_by_gig[e["gigId"]].append(e)

    def sched_fee_at(sched: list[dict], minute: int) -> int:
        cur = sched[0]["feeCents"]
        for s in sched:
            if s["at"] <= minute:
                cur = s["feeCents"]
            else:
                break
        return cur

    drop_jumps = []
    for gid, g in gigs.items():
        if g["status"] != "done":
            continue
        evs = ev_by_gig[gid]
        drops = [e for e in evs if e["kind"] == "gig_dropped"]
        if not drops:
            continue
        stops = json.loads(g["stops"])
        oids = list(dict.fromkeys(s["orderId"] for s in stops))
        ref = sum(int(reqs[o]["referenceFeeCents"]) for o in oids)
        sched = json.loads(g["schedule"])
        bks = [e for e in evs if e["kind"] == "gig_booked"]
        b1 = int(bks[0]["feeCents"]) / ref
        d_at = int(drops[-1]["at"])
        at_drop = sched_fee_at(sched, d_at) / ref
        b_final = int(g["feeCents"]) / ref
        drop_jumps.append((b1, at_drop, b_final, (b_final - b1) * ref / 100, d_at - int(bks[0]["at"])))

    print(f"=== 1. DROPPED & REBOOKED DONE GIGS (n={len(drop_jumps)}) ===")
    print(f"  mean first_book={sum(x[0] for x in drop_jumps)/len(drop_jumps):.3f}x -> sched_at_drop={sum(x[1] for x in drop_jumps)/len(drop_jumps):.3f}x -> final_book={sum(x[2] for x in drop_jumps)/len(drop_jumps):.3f}x")
    print(f"  total extra € paid above first_book: €{sum(x[3] for x in drop_jumps):,.1f}")
    for x in sorted(drop_jumps, key=lambda t: -t[3])[:8]:
        print(f"    b1={x[0]:.2f}x -> at_drop={x[1]:.2f}x -> final={x[2]:.2f}x (+€{x[3]:.0f}, held {x[4]}m)")

    # 2. Short-horizon rising() schedules (<= 4 steps, jumping straight to 1.60x)
    short_scheds = []
    for gid, g in gigs.items():
        if g["status"] != "done":
            continue
        sched = json.loads(g["schedule"])
        stops = json.loads(g["stops"])
        oids = list(dict.fromkeys(s["orderId"] for s in stops))
        ref = sum(int(reqs[o]["referenceFeeCents"]) for o in oids)
        if 2 <= len(sched) <= 5 and sched[0]["feeCents"] / ref < 1.0 and sched[-1]["feeCents"] / ref > 1.5:
            span = sched[-1]["at"] - sched[0]["at"]
            short_scheds.append((gid, len(sched), span, int(g["feeCents"]) / ref, int(g["feeCents"]) / 100, ref / 100))
    print()
    print(f"=== 2. SHORT RISING SCHEDULES (2-5 steps jumping 0.85->1.60x): n={len(short_scheds)} ===")
    for x in short_scheds:
        print(f"  {x[0]} steps={x[1]} span={x[2]}m booked={x[3]:.2f}x (€{x[4]:.0f} vs ref €{x[5]:.0f})")

    # 3. Viewer geography & hold-out analysis
    views_by_gig = defaultdict(list)
    for v in views:
        views_by_gig[v["gigId"]].append((int(v["at"]), v["driverId"], int(v["feeCents"])))

    booker_loc = Counter()
    viewer_loc = Counter()
    repeat_booker_loc = Counter()
    early_local_viewers_on_expensive_gigs = 0
    expensive_gigs_n = 0

    for gid, g in gigs.items():
        if g["status"] != "done":
            continue
        stops = json.loads(g["stops"])
        oids = list(dict.fromkeys(s["orderId"] for s in stops))
        ref = sum(int(reqs[o]["referenceFeeCents"]) for o in oids)
        fee = int(g["feeCents"])
        mult = fee / ref
        ls0 = legs_by_req[oids[0]][0]
        pick, dest = ls0["pickup.placeId"], legs_by_req[oids[-1]][-1]["delivery.placeId"]
        booker = g["driverId"]
        bh = drivers[booker]["homePlaceId"]
        dp = line_km(bh, pick)
        dd = line_km(bh, dest)
        loc = "near_pick<=30" if dp <= 30 else ("near_dest<=30" if dd <= 30 else ("mid_30_60" if min(dp, dd) <= 60 else "far>60"))
        booker_loc[loc] += 1

        vs = views_by_gig[gid]
        b_views = [v for v in vs if v[1] == booker]
        if len(b_views) >= 2:
            repeat_booker_loc[loc] += 1

        for at, did, fc in vs:
            dh = drivers[did]["homePlaceId"]
            vdp, vdd = line_km(dh, pick), line_km(dh, dest)
            vloc = "near_pick<=30" if vdp <= 30 else ("near_dest<=30" if vdd <= 30 else ("mid_30_60" if min(vdp, vdd) <= 60 else "far>60"))
            viewer_loc[vloc] += 1

        if 1.00 < mult < 1.65:
            expensive_gigs_n += 1
            p_at = int(g["postedAt"])
            early_local = {did for at, did, fc in vs if at - p_at <= 30 and (line_km(drivers[did]["homePlaceId"], pick) <= 35 or line_km(drivers[did]["homePlaceId"], dest) <= 35)}
            if early_local:
                early_local_viewers_on_expensive_gigs += 1

    print()
    print("=== 3. VIEWER VS BOOKER GEOGRAPHY ===")
    print("  All views (8712):", dict(viewer_loc))
    print("  Done gig bookers (287):", dict(booker_loc))
    print("  Repeat-viewer bookers (hold-outs):", dict(repeat_booker_loc))
    print(f"  Gigs booked at 1.00..1.65x: {expensive_gigs_n}, of which {early_local_viewers_on_expensive_gigs} had >=1 local/dest viewer in first 30m!")

    # 4. Learned raise ratio taught to viewers over the week!
    # In HANDBOOK: booked_fee / first_viewed_fee_of_order!
    first_view_fee_order = {}
    views_per_order = defaultdict(set)
    order_of_gig = {}
    for gid, g in gigs.items():
        stops = json.loads(g["stops"])
        oids = list(dict.fromkeys(s["orderId"] for s in stops))
        order_of_gig[gid] = oids[0]
    for v in sorted(views, key=lambda x: int(x["at"])):
        oid = order_of_gig.get(v["gigId"])
        if not oid:
            continue
        if oid not in first_view_fee_order:
            first_view_fee_order[oid] = int(v["feeCents"])
        views_per_order[oid].add(v["driverId"])

    taught = []
    for gid, g in gigs.items():
        if g["status"] != "done":
            continue
        oid = order_of_gig[gid]
        if oid in first_view_fee_order:
            ratio = int(g["feeCents"]) / first_view_fee_order[oid]
            taught.append((ratio, len(views_per_order[oid]), oid, gid))
    taught.sort(reverse=True)
    print()
    print("=== 4. DRIVER LEARNING EXPOSURE (booked_fee / first_viewed_fee * viewers) ===")
    total_vw = sum(vw for _, vw, _, _ in taught)
    w_mean = sum(r * vw for r, vw, _, _ in taught) / max(1, total_vw)
    print(f"  Viewer-weighted mean booked/first_viewed taught across week: {w_mean:.3f}x across {total_vw} order-viewer exposures!")
    for r, vw, oid, gid in taught[:12]:
        print(f"    {gid:<5} ({oid}) taught ratio={r:.2f}x to {vw:>3} unique viewers")


if __name__ == "__main__":
    main()
