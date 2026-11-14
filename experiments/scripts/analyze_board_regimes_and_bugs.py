#!/usr/bin/env python3
"""Exact ledger impact of Friday->Monday >480m next_day bug and 2-leg trade-ins on Round 7 Board + Dev-16, plus sd-share root cause."""
from __future__ import annotations

import json
from pathlib import Path
from statistics import mean

from spread.client import Client
from spread_lab.env import load_dotenv
from spread_lab.geo import Geo, load_map
from analyze_board_vs_dev import ROUND7_WORLDS, fetch_all_events

DAY = 1440


def check_worlds(label: str, wids: list[str], client: Client, geo: Geo) -> None:
    fri_nd_cents = 0.0
    fri_nd_won = 0
    fri_nd_late = 0
    ti_cents = 0.0
    ti_won = 0
    ti_late = 0
    fut_ready_shares = []
    sd_shares = []

    for wid in wids:
        w = client.world(wid)
        events = fetch_all_events(w)
        reqs = {e["request"]["id"]: e["request"] for e in events if e["kind"] == "price_request"}
        wons = {e["order"]["id"]: e["order"] for e in events if e["kind"] == "order_won"}
        cancels = {e["orderId"] for e in events if e["kind"] == "order_cancelled"}

        fut_ready = sum(1 for r in reqs.values() if r["legs"][0]["pickup"]["window"]["from"] // DAY > r["arrivedAt"] // DAY)
        sd_cnt = sum(1 for r in reqs.values() if any(o["kind"] == "same_day" for o in r["options"]))
        fut_ready_shares.append(fut_ready / len(reqs))
        sd_shares.append(sd_cnt / len(reqs))

        # Map gigId -> orderIds for driver_fee attribution
        gig_orders: dict[str, list[str]] = {}
        for e in events:
            if e["kind"] == "delivered" and e.get("gigId"):
                gig_orders.setdefault(e["gigId"], [])
                if e["orderId"] not in gig_orders[e["gigId"]]:
                    gig_orders[e["gigId"]].append(e["orderId"])

        order_net: dict[str, float] = {}
        late_oids: set[str] = set()
        for e in events:
            if e["kind"] == "ledger":
                line = e["line"]
                oid = line.get("orderId")
                if oid:
                    order_net[oid] = order_net.get(oid, 0.0) + line["cents"]
                    if line["kind"] in ("late_refund", "undelivered_penalty"):
                        late_oids.add(oid)
                elif line["kind"] == "driver_fee" and line.get("gigId") in gig_orders:
                    oids = gig_orders[line["gigId"]]
                    for o in oids:
                        order_net[o] = order_net.get(o, 0.0) + line["cents"] / len(oids)

        for oid, o in wons.items():
            if oid in cancels:
                continue
            r = reqs[oid]
            legs = r["legs"]
            drv = sum(geo.minutes(leg["pickup"]["placeId"], leg["delivery"]["placeId"]) for leg in legs)
            if len(legs) == 2:
                drv += geo.minutes(legs[0]["delivery"]["placeId"], legs[1]["pickup"]["placeId"])
                ti_won += 1
                ti_cents += order_net.get(oid, 0.0)
                if oid in late_oids:
                    ti_late += 1
            ready_day = max(r["arrivedAt"], legs[0]["pickup"]["window"]["from"]) // DAY
            if o["option"] == "next_day" and drv > 480 and (o["deadline"] // DAY) > ready_day + 1:
                fri_nd_won += 1
                fri_nd_cents += order_net.get(oid, 0.0)
                if oid in late_oids:
                    fri_nd_late += 1

    n = len(wids)
    print(f"=== {label} ({n} worlds) ===")
    print(f"  future_ready_day share: {mean(fut_ready_shares):.1%} ({min(fut_ready_shares):.1%}..{max(fut_ready_shares):.1%}) | same_day opt share: {mean(sd_shares):.1%} ({min(sd_shares):.1%}..{max(sd_shares):.1%})")
    print(f"  Fri->Mon >480m next_day: won={fri_nd_won} ({fri_nd_won/n:.2f}/wk), late={fri_nd_late} ({fri_nd_late/max(1,fri_nd_won):.1%}), direct net=€{fri_nd_cents/100:,.2f} (€{fri_nd_cents/100/max(1,fri_nd_won):.2f}/car, excl. trust halving!)")
    print(f"  2-leg trade-ins:         won={ti_won} ({ti_won/n:.2f}/wk), late={ti_late} ({ti_late/max(1,ti_won):.1%}), direct net=€{ti_cents/100:,.2f} (€{ti_cents/100/max(1,ti_won):.2f}/car, excl. trust halving!)")


def main() -> None:
    load_dotenv()
    client = Client()
    geo = Geo(load_map(client))
    dev_rows = [json.loads(line) for line in Path("champion/results/dev-L8.jsonl").read_text().splitlines() if line.strip()]
    dev_wids = [r["world"] for r in sorted(dev_rows, key=lambda x: x["seed"])]
    check_worlds("ROUND 7 BOARD", ROUND7_WORLDS, client, geo)
    check_worlds("DEV-16", dev_wids, client, geo)


if __name__ == "__main__":
    main()
