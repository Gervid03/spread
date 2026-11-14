"""Inspect 25 completed gigs in reveal-w20775676a400fbd09ee0 to understand exact pickup/finish timing."""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

DAY = 1440
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def fmt(m: int) -> str:
    return f"{WEEKDAYS[(m // DAY) % 7]} {m % DAY // 60:02d}:{m % 60:02d} ({m})"


def main() -> None:
    folder = Path("/tmp/reveals-v3/reveal-w20775676a400fbd09ee0")
    roads = {(r["from"], r["to"]): int(r["minutes"]) for r in csv.DictReader(open(folder / "roads.csv"))}
    drivers = {r["id"]: r for r in csv.DictReader(open(folder / "drivers.csv"))}
    legs = defaultdict(dict)
    for r in csv.DictReader(open(folder / "legs.csv")):
        legs[r["requestId"]][int(r["leg"])] = r
    reqs = {r["id"]: r for r in csv.DictReader(open(folder / "requests.csv"))}
    gigs = {r["id"]: r for r in csv.DictReader(open(folder / "gigs.csv"))}
    events = list(csv.DictReader(open(folder / "events.csv")))

    booked, started, picked, deliv, late = {}, {}, {}, {}, {}
    for e in events:
        k, gid = e["kind"], e["gigId"]
        if k == "gig_booked":
            booked[gid] = (int(e["at"]), e["driverId"])
        elif k == "gig_started":
            started[gid] = int(e["at"])
        elif k == "driver_late":
            late[gid] = int(e["pickupAt"])
        elif k == "picked_up":
            picked.setdefault(gid, []).append(int(e["at"]))
        elif k == "delivered":
            deliv.setdefault(gid, []).append(int(e["at"]))

    for gid in list(gigs)[:25]:
        g = gigs[gid]
        if g["status"] != "done" or gid not in booked or gid not in picked:
            continue
        b_at, did = booked[gid]
        stops = json.loads(g["stops"])
        oid = stops[0]["orderId"]
        lg = legs[oid][stops[0]["leg"]]
        req = reqs[oid]
        p_pl, d_pl = lg["pickup.placeId"], lg["delivery.placeId"]
        home = drivers[did]["homePlaceId"]
        wf = int(lg["pickup.window.from"])
        wt = int(lg["pickup.window.to"])
        st_at = started.get(gid, -1)
        pk_at = picked[gid][0]
        dl_at = deliv[gid][-1]
        rd = roads[(p_pl, d_pl)]
        home_to_p = roads[(home, p_pl)]
        print(
            f"{gid:4s} {req['option']:13s} home={home:9s} {p_pl:9s}->{d_pl:9s} rd={rd:3d}m (h->p={home_to_p:3d}m) | "
            f"book={fmt(b_at)} | win_from={fmt(wf)} | start={fmt(st_at)} | pick={fmt(pk_at)} | deliv={fmt(dl_at)} (pick+rd={pk_at+rd})"
        )


if __name__ == "__main__":
    main()
