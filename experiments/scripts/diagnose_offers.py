"""Diagnose every offer_answered event in a revealed world: timing, gig booking race, fee vs eventual booked fee, driver state."""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path


def main(folder_str: str) -> None:
    folder = Path(folder_str)
    reqs = {r["id"]: r for r in csv.DictReader(open(folder / "requests.csv"))}
    legs = defaultdict(dict)
    for r in csv.DictReader(open(folder / "legs.csv")):
        legs[r["requestId"]][int(r["leg"])] = r
    drivers = {r["id"]: r for r in csv.DictReader(open(folder / "drivers.csv"))}
    gigs = {r["id"]: r for r in csv.DictReader(open(folder / "gigs.csv"))}
    events = list(csv.DictReader(open(folder / "events.csv")))

    # Find offer_answered column name!
    print("Event columns:", list(events[0].keys()))
    booked_at, booked_by, booked_fee = {}, {}, {}
    driver_gigs = defaultdict(list)  # driverId -> list of (booked_at, start_at, pick_at, deliv_at, gigId)
    start_at, pick_at, deliv_at = {}, {}, {}
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

    for gid, g in gigs.items():
        if gid in booked_by:
            driver_gigs[booked_by[gid]].append((booked_at[gid], start_at.get(gid, -1), pick_at.get(gid, -1), deliv_at.get(gid, -1), gid))

    offers = [e for e in events if e["kind"] == "offer_answered"]
    print(f"Total offer_answered: {len(offers)}")
    if offers:
        print("Sample offer_answered row:", {k: v for k, v in offers[0].items() if v})

    reasons = Counter()
    eventual_ratios_declined = []
    for e in offers:
        ans = e.get("answer") or e.get("reason") or ""
        gid = e["gigId"]
        did = e["driverId"]
        ans_at = int(e["at"])
        sent_at = ans_at - 10
        g = gigs[gid]
        stops = json.loads(g["stops"])
        oids = list(dict.fromkeys(s["orderId"] for s in stops))
        ref_fee = sum(int(reqs[o]["referenceFeeCents"]) for o in oids)
        b_at = booked_at.get(gid, 10**9)

        # What was driver doing at sent_at?
        d_state = "idle"
        for gb, gs, gp, gd, ogid in driver_gigs[did]:
            if ogid == gid:
                continue
            if gp != -1 and gd != -1 and gp <= sent_at <= gd:
                d_state = f"driving(rem={gd-sent_at<=60})"
                break
            elif gb <= sent_at < (gp if gp != -1 else 10**9):
                d_state = "holding_unstarted"
            elif gd != -1 and 0 <= sent_at - gd <= 180:
                d_state = "just_delivered"

        gig_race = "gig_booked_during_10m" if b_at < ans_at and booked_by.get(gid) != did else "gig_still_open_at_ans"
        reasons[(ans, gig_race, d_state)] += 1
        if ans == "declined" and gid in booked_fee and ref_fee > 0:
            eventual_ratios_declined.append(booked_fee[gid] / ref_fee)

    print("=== Breakdown of (answer, gig_race, driver_state_at_send) ===")
    for k, c in reasons.most_common():
        print(f"  {k}: {c}")
    if eventual_ratios_declined:
        eventual_ratios_declined.sort()
        n = len(eventual_ratios_declined)
        print(f"Eventual app booked fee/ref on gigs where offer was DECLINED (n={n}): p10={eventual_ratios_declined[n//10]:.2f}, med={eventual_ratios_declined[n//2]:.2f}, p90={eventual_ratios_declined[9*n//10]:.2f}")

    # Also print all ACCEPTED offers!
    for e in offers:
        ans = e.get("answer") or e.get("reason") or ""
        if ans == "accepted":
            gid, did, at = e["gigId"], e["driverId"], int(e["at"])
            print(f"  ACCEPTED: at={at} gig={gid} driver={did} (booked_at={booked_at.get(gid)}, g.feeCents={gigs[gid]['feeCents']})")


if __name__ == "__main__":
    main(sys.argv[1])
