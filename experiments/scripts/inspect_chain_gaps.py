"""Check exact (book2_at - deliv1_at) and (pick2_at - deliv1_at) on organic chains in /tmp/reveals-v3."""
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
    rows = []
    for folder in sorted(Path("/tmp/reveals-v3").glob("reveal-*")):
        places = {r["id"]: (float(r["lat"]), float(r["lon"])) for r in csv.DictReader(open(folder / "places.csv"))}
        line = {(a, b): haversine_km(*places[a], *places[b]) for a in places for b in places}
        drivers = {r["id"]: r for r in csv.DictReader(open(folder / "drivers.csv"))}
        gigs = {r["id"]: r for r in csv.DictReader(open(folder / "gigs.csv"))}
        events = list(csv.DictReader(open(folder / "events.csv")))
        booked, started, picked, deliv = {}, {}, {}, {}
        for e in events:
            gid = e["gigId"]
            if e["kind"] == "gig_booked":
                booked[gid] = int(e["at"])
            elif e["kind"] == "gig_started":
                started[gid] = int(e["at"])
            elif e["kind"] == "picked_up":
                picked.setdefault(gid, []).append((int(e["at"]), e["placeId"]))
            elif e["kind"] == "delivered":
                deliv.setdefault(gid, []).append((int(e["at"]), e["placeId"]))
        by_d = defaultdict(list)
        for gid, g in gigs.items():
            if g["status"] == "done" and gid in booked and gid in picked and gid in deliv:
                by_d[g["driverId"]].append((
                    picked[gid][0][0], picked[gid][0][1],
                    deliv[gid][-1][0], deliv[gid][-1][1],
                    booked[gid], started.get(gid, -1), gid,
                ))
        for did, lst in by_d.items():
            lst.sort()
            home = drivers[did]["homePlaceId"]
            for a, b in zip(lst, lst[1:]):
                p1_at, p1_pl, d1_at, d1_pl, b1_at, s1_at, g1 = a
                p2_at, p2_pl, d2_at, d2_pl, b2_at, s2_at, g2 = b
                if line[(d1_pl, p2_pl)] <= 30.0 and line[(p2_pl, home)] > 30.0:
                    rows.append((b2_at - d1_at, p2_at - d1_at, s2_at - d1_at, home, d1_pl, p2_pl, d2_pl))
    for b_diff, p_diff, s_diff, home, d1_pl, p2_pl, d2_pl in sorted(rows):
        print(f"book2-deliv1={b_diff:+5d}m  start2-deliv1={s_diff:+5d}m  pick2-deliv1={p_diff:+5d}m | home={home:9s} {d1_pl}->{p2_pl}->{d2_pl}")


if __name__ == "__main__":
    main()
