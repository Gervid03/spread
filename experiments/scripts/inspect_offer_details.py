"""Inspect exact details of accepted vs declined offers in reveal-w242e665a379704c1ada3."""
from __future__ import annotations

import csv
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

DAY = 1440


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (lat1, lon1, lat2, lon2))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(h))


def main(folder_str: str) -> None:
    folder = Path(folder_str)
    places = {r["id"]: (float(r["lat"]), float(r["lon"])) for r in csv.DictReader(open(folder / "places.csv"))}
    line = {(a, b): haversine_km(*places[a], *places[b]) for a in places for b in places}
    roads = {(r["from"], r["to"]): int(r["minutes"]) for r in csv.DictReader(open(folder / "roads.csv"))}
    reqs = {r["id"]: r for r in csv.DictReader(open(folder / "requests.csv"))}
    legs = defaultdict(dict)
    for r in csv.DictReader(open(folder / "legs.csv")):
        legs[r["requestId"]][int(r["leg"])] = r
    drivers = {r["id"]: r for r in csv.DictReader(open(folder / "drivers.csv"))}
    gigs = {r["id"]: r for r in csv.DictReader(open(folder / "gigs.csv"))}
    events = list(csv.DictReader(open(folder / "events.csv")))

    booked_at, booked_by, booked_fee, start_at, pick_at, deliv_at = {}, {}, {}, {}, {}, {}
    for e in events:
        k, gid = e["kind"], e["gigId"]
        at = int(e["at"])
        if k == "gig_booked":
            booked_at[gid] = at
            booked_by[gid] = e["driverId"]
            booked_fee[gid] = int(e["feeCents"])
        elif k == "gig_started":
            start_at[gid] = at
        elif k == "picked_up" and gid not in pick_at:
            pick_at[gid] = at
        elif k == "delivered":
            deliv_at[gid] = at

    driver_gigs = defaultdict(list)
    for gid, g in gigs.items():
        did = g["driverId"]
        if did:
            stops = json.loads(g["stops"])
            p0 = legs[stops[0]["orderId"]][stops[0]["leg"]]["pickup.placeId"]
            dl = legs[stops[-1]["orderId"]][stops[-1]["leg"]]["delivery.placeId"]
            driver_gigs[did].append((booked_at.get(gid, int(g["postedAt"])), pick_at.get(gid, -1), deliv_at.get(gid, -1), p0, dl, gid))

    print("=== ALL ACCEPTED OFFERS ===")
    for e in events:
        if e["kind"] == "offer_answered" and e["answer"] == "accepted":
            gid, did, at = e["gigId"], e["driverId"], int(e["at"])
            g = gigs[gid]
            stops = json.loads(g["stops"])
            oid = stops[0]["orderId"]
            p_pl = legs[oid][0]["pickup.placeId"]
            d_pl = legs[stops[-1]["orderId"]][stops[-1]["leg"]]["delivery.placeId"]
            ref = sum(int(reqs[o]["referenceFeeCents"]) for o in dict.fromkeys(s["orderId"] for s in stops))
            home = drivers[did]["homePlaceId"]
            print(f"  acc gig={gid} {p_pl}->{d_pl} (rd={roads[(p_pl,d_pl)]}m) home={home} fee={g['feeCents']}/ref={ref} ({int(g['feeCents'])/ref:.2f}) | driver_gigs={driver_gigs[did]}")

    print("=== SAMPLE 20 DECLINED OFFERS (driving or just_delivered) ===")
    shown = 0
    for e in events:
        if e["kind"] == "offer_answered" and e["answer"] == "declined":
            gid, did, ans_at = e["gigId"], e["driverId"], int(e["at"])
            sent_at = ans_at - 10
            g = gigs[gid]
            stops = json.loads(g["stops"])
            oid = stops[0]["orderId"]
            p_pl = legs[oid][0]["pickup.placeId"]
            d_pl = legs[stops[-1]["orderId"]][stops[-1]["leg"]]["delivery.placeId"]
            wf = int(legs[oid][0]["pickup.window.from"])
            ref = sum(int(reqs[o]["referenceFeeCents"]) for o in dict.fromkeys(s["orderId"] for s in stops))
            home = drivers[did]["homePlaceId"]
            ev_ratio = f"{booked_fee[gid]/ref:.2f}" if gid in booked_fee else "unbooked"
            for gb, gp, gd, gp_pl, gd_pl, ogid in driver_gigs[did]:
                if ogid != gid and gp != -1 and gd != -1 and gp <= sent_at <= gd + 120:
                    print(
                        f"  dec sent={sent_at} (d{sent_at//DAY} {sent_at%DAY//60:02d}:{sent_at%60:02d}) "
                        f"drv={did}(home={home}) prev={ogid}({gp_pl}->{gd_pl} pick={gp} deliv={gd}) | "
                        f"offer={gid}({p_pl}->{d_pl} rd={roads[(p_pl,d_pl)]}m wf={wf}[d{wf//DAY}] home_km={line[(home,d_pl)]:.0f}) "
                        f"eventual_app={ev_ratio}"
                    )
                    shown += 1
                    break
            if shown >= 20:
                break


if __name__ == "__main__":
    main(sys.argv[1])
