"""Deep causal decomposition of driver fees, driver expectation poisoning, drops, and batching on dev-09."""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
REV = REPO / "runs" / "reveal-dev09"


def main() -> None:
    reqs = {r["id"]: r for r in csv.DictReader((REV / "requests.csv").open())}
    gigs = {g["id"]: g for g in csv.DictReader((REV / "gigs.csv").open())}
    events = list(csv.DictReader((REV / "events.csv").open()))
    views = list(csv.DictReader((REV / "views.csv").open()))
    places = {p["id"]: p["name"] for p in csv.DictReader((REV / "places.csv").open())}
    drivers = {d["id"]: d for d in csv.DictReader((REV / "drivers.csv").open())}
    legs_by_req = defaultdict(list)
    for l in csv.DictReader((REV / "legs.csv").open()):
        legs_by_req[l["requestId"]].append(l)

    # Check what happened around g61, g256, g227 withdrawals
    for oid in ["R00212", "R00698", "R00625", "R00833"]:
        evs = [e for e in events if e.get("orderId") == oid or e.get("gigId") in ("g56", "g61", "g229", "g256", "g203", "g227", "g276") and oid in gigs.get(e.get("gigId", ""), {}).get("stops", "")]
        print(f"Order {oid} trace:")
        for e in evs:
            if e["kind"] != "gig_viewed":
                print(f"  at={e['at']} kind={e['kind']} gig={e.get('gigId','')} fee={e.get('feeCents','')} reason={e.get('reason','')}")

    # Check ALL done gigs by pickup supply class, delivery supply class, option, drive length
    # Compute 30km supply from places + drivers
    import math
    coords = {p["id"]: (float(p["lat"]), float(p["lon"])) for p in csv.DictReader((REV / "places.csv").open())}
    def line_km(a: str, b: str) -> float:
        lat1, lon1 = coords[a]
        lat2, lon2 = coords[b]
        dx = (lon2 - lon1) * math.cos(math.radians((lat1 + lat2) / 2)) * 111.32
        dy = (lat2 - lat1) * 110.574
        return math.hypot(dx, dy)

    supply30 = Counter()
    for p in coords:
        supply30[p] = sum(1 for d in drivers.values() if line_km(p, d["homePlaceId"]) <= 30.0)

    roads = {(r["from"], r["to"]): int(r["minutes"]) for r in csv.DictReader((REV / "roads.csv").open())}

    won_opt = {}
    dropped_gigs = set()
    warned_orders = set()
    changed_orders = set()
    for e in events:
        if e["kind"] == "order_won":
            won_opt[e["orderId"]] = e.get("option", "")
        elif e["kind"] == "gig_dropped":
            dropped_gigs.add(e["gigId"])
        elif e["kind"] == "deadline_close":
            warned_orders.add(e["orderId"])
        elif e["kind"] == "order_changed":
            changed_orders.add(e["orderId"])

    print()
    print("=== DONE GIGS BY SUPPLY & ROUTE CLASS ===")
    cls_stats = defaultdict(lambda: [0, 0.0, 0.0, 0, 0])  # n, fee, ref, n_at_open, n_dropped
    for g in gigs.values():
        if g["status"] != "done":
            continue
        stops = json.loads(g["stops"])
        oids = list(dict.fromkeys(s["orderId"] for s in stops))
        ref = sum(int(reqs[o]["referenceFeeCents"]) for o in oids)
        fee = int(g["feeCents"])
        mult = fee / ref
        r0 = reqs[oids[0]]
        ls = legs_by_req[oids[0]]
        pick, dest = ls[0]["pickup.placeId"], ls[-1]["delivery.placeId"]
        sp = supply30[pick]
        sd = supply30[dest]
        drv = roads.get((pick, dest), 0)
        p_cls = "hub>=150" if sp >= 150 else ("mid50-149" if sp >= 50 else "thin<50")
        d_cls = "to_hub" if sd >= 150 else "to_nonhub"
        opt = won_opt.get(oids[0]) or r0.get("option", "?")
        key = f"{p_cls:<10} {d_cls:<10} {opt:<13}"
        st = cls_stats[key]
        st[0] += 1
        st[1] += fee / 100
        st[2] += ref / 100
        if mult <= 0.86:
            st[3] += 1
        if g["id"] in dropped_gigs:
            st[4] += 1

    for k, (n, fe, re_, n_open, n_drp) in sorted(cls_stats.items(), key=lambda kv: -(kv[1][1] - 0.85 * kv[1][2])):
        print(f"  {k} n={n:>3} mult={fe/re_:.3f}x at_0.85={n_open:>2}/{n:<3} drops={n_drp:>2} fee=€{fe:>7,.0f} excess085=€{fe-0.85*re_:>6,.0f}")

    # How much excess came from: (a) gigs that were dropped at least once, (b) warned orders, (c) multi-gig orders, (d) clean never-dropped never-warned gigs?
    mut_buckets = defaultdict(lambda: [0, 0.0, 0.0])
    gigs_per_order = Counter()
    for g in gigs.values():
        for s in json.loads(g["stops"]):
            if s["kind"] == "pickup":
                gigs_per_order[s["orderId"]] += 1

    for g in gigs.values():
        if g["status"] != "done":
            continue
        stops = json.loads(g["stops"])
        oids = list(dict.fromkeys(s["orderId"] for s in stops))
        ref = sum(int(reqs[o]["referenceFeeCents"]) for o in oids)
        fee = int(g["feeCents"])
        if len(oids) > 1:
            b = "1_lead_car_pair"
        elif any(o in warned_orders for o in oids):
            b = "2_warned_order"
        elif g["id"] in dropped_gigs:
            b = "3_dropped_and_rebooked"
        elif any(gigs_per_order[o] > 1 for o in oids):
            b = "4_reposted_order"
        else:
            b = "5_clean_first_gig"
        mut_buckets[b][0] += 1
        mut_buckets[b][1] += fee / 100
        mut_buckets[b][2] += ref / 100

    print()
    print("=== MUTUALLY EXCLUSIVE CAUSAL DECOMPOSITION OF DONE GIGS ===")
    for b, (n, fe, re_) in sorted(mut_buckets.items()):
        print(f"  {b:<26} n={n:>3} fee=€{fe:>8,.1f} ref=€{re_:>8,.1f} mult={fe/re_:.3f}x excess085=€{fe-0.85*re_:>7,.1f}")


if __name__ == "__main__":
    main()
