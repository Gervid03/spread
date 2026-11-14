"""Unit verification of Desk route-network methods (a)-(d) and rejoin() without touching practice slots."""
from __future__ import annotations

import csv
from pathlib import Path

from spread_lab.geo import Geo
from spread_lab.policy import Desk, Params


class DummyWorld:
    def __init__(self) -> None:
        self._gid = 0

    def act(self, actions):
        out = []
        for a in actions:
            if a["type"] == "post":
                self._gid += 1
                out.append({"ok": True, "id": f"g{self._gid}"})
            else:
                out.append({"ok": True, "id": a.get("gigId", "x")})
        return out


def load_local_geo_and_roster():
    folder = Path("/tmp/reveals-v3/reveal-w20775676a400fbd09ee0")
    places = [
        {"id": r["id"], "name": r["name"], "lat": float(r["lat"]), "lon": float(r["lon"])}
        for r in csv.DictReader(open(folder / "places.csv"))
    ]
    roads = [
        {"from": r["from"], "to": r["to"], "km": float(r["km"]), "minutes": int(r["minutes"])}
        for r in csv.DictReader(open(folder / "roads.csv"))
    ]
    roster = [
        {
            "id": r["id"],
            "homePlaceId": r["homePlaceId"],
            "rating": float(r["rating"]),
            "licence": r["licence"],
            "completedGigs": int(r["completedGigs"]),
            "drops": int(r["drops"]),
        }
        for r in csv.DictReader(open(folder / "drivers.csv"))
    ]
    return Geo({"places": places, "roads": roads}), roster


def make_leg(p_id: str, d_id: str, wf: int, wt: int, df: int, dt: int):
    hours = {"opens": 480, "closes": 1140, "weekdays": [0, 1, 2, 3, 4], "saturday": {"opens": 540, "closes": 840}}
    return {
        "car": {"premium": False, "electric": False, "chargePercent": None},
        "pickup": {"placeId": p_id, "privateAddress": False, "window": {"from": wf, "to": wt}, "hours": hours},
        "delivery": {"placeId": d_id, "privateAddress": False, "window": {"from": df, "to": dt}, "hours": hours},
    }


def main() -> None:
    geo, roster = load_local_geo_and_roster()
    # Pick a Vantaa manual experienced driver
    drv = next(d for d in roster if d["homePlaceId"] == "vantaa" and d["licence"] == "manual" and d["rating"] >= 4.8 and d["completedGigs"] >= 50)
    did = drv["id"]

    w = DummyWorld()
    p = Params(net_offer=True, net_quote=True, net_seed=0.05, seed_min=2)
    desk = Desk(w, p, 8, geo, roster, now=540)

    # 1. Quote & win outbound car Vantaa -> Kuopio (233m)
    req1 = {
        "id": "R1", "dealerId": "D01", "batchId": None, "arrivedAt": 540, "respondBy": 555,
        "referenceFeeCents": 9000, "note": None, "language": None,
        "legs": [make_leg("vantaa", "kuopio", 540, 1080, 540, 2640)],
        "options": [{"kind": "next_day", "deadline": 2640, "listPriceCents": 11000}],
    }
    desk.handle({"seq": 1, "at": 540, "kind": "price_request", "request": req1})
    acts = desk.take_outbox()
    desk.read_results(acts, w.act(acts))

    ord1 = {
        "id": "R1", "dealerId": "D01", "option": "next_day", "priceCents": 14850,
        "deadline": 2640, "lastPickupAt": 2100, "status": "waiting",
        "legs": req1["legs"], "deliveredAt": [None],
    }
    desk.now = 555
    desk.handle({"seq": 2, "at": 555, "kind": "order_won", "order": ord1})
    acts = desk.take_outbox()
    desk.read_results(acts, w.act(acts))
    assert "g1" in desk.posts

    # Book g1 by Vantaa driver at 560, pick up at 600 -> finish in Kuopio around 600 + 230
    desk.now = 560
    desk.handle({"seq": 3, "at": 560, "kind": "gig_booked", "gigId": "g1", "driverId": did, "feeCents": 7650})
    assert "g1" in desk.pos_ledger
    desk.now = 600
    desk.handle({"seq": 4, "at": 600, "kind": "picked_up", "gigId": "g1", "orderId": "R1", "leg": 0, "placeId": "vantaa"})
    fin_at = desk.pos_ledger["g1"].finish_at
    print("Booked & picked up g1, planned Kuopio finish_at:", fin_at)

    # 2. Thin request in Kuopio -> Vantaa ready around fin_at!
    desk.now = fin_at - 70
    req2 = {
        "id": "R2", "dealerId": "D02", "batchId": None, "arrivedAt": desk.now, "respondBy": desk.now + 15,
        "referenceFeeCents": 9000, "note": None, "language": None,
        "legs": [make_leg("kuopio", "vantaa", fin_at - 30, fin_at + 180, fin_at - 30, 2640)],
        "options": [
            {"kind": "same_day", "deadline": 1200, "listPriceCents": 12000},
            {"kind": "next_day", "deadline": 2640, "listPriceCents": 11000},
        ],
    }
    desk.handle({"seq": 5, "at": desk.now, "kind": "price_request", "request": req2})
    acts = desk.take_outbox()
    print("R2 quote actions:", acts, "stats net_quoted:", desk.stats["net_quoted"], "thin:", desk.stats["net_quoted_thin"])
    assert desk.stats["net_quoted"] == 1
    assert "next_day" in acts[0]["prices"] and "same_day" not in acts[0]["prices"]

    # Win R2 at fin_at - 55 -> within net_lead_min=60! Should send home-bound offer (0.65x) IMMEDIATELY in tick()!
    desk.now = fin_at - 55
    ord2 = {
        "id": "R2", "dealerId": "D02", "option": "next_day", "priceCents": acts[0]["prices"]["next_day"],
        "deadline": 2640, "lastPickupAt": 2100, "status": "waiting",
        "legs": req2["legs"], "deliveredAt": [None],
    }
    desk.handle({"seq": 6, "at": desk.now, "kind": "order_won", "order": ord2})
    desk.tick()
    acts = desk.take_outbox()
    print("After R2 order_won + tick() actions:", acts)
    assert any(a["type"] == "offer" and a["driverId"] == did and a["feeCents"] == int(9000 * 0.65 + 0.5) for a in acts)
    assert desk.stats["net_offers"] == 1 and desk.stats["net_offers_home"] == 1

    # Simulate offer_answered accepted!
    desk.now += 4
    desk.handle({"seq": 7, "at": desk.now, "kind": "offer_answered", "gigId": "g2", "driverId": did, "answer": "accepted"})
    assert "g2" in desk.booked and "g2" in desk.pos_ledger
    assert desk.stats["net_accepted"] == 1 and desk.stats["net_accepted_home"] == 1

    # Deliver g1 then g2 on same day -> check driver_days_2plus!
    desk.now = fin_at
    desk.handle({"seq": 8, "at": desk.now, "kind": "delivered", "gigId": "g1", "orderId": "R1", "leg": 0, "placeId": "kuopio"})
    ord1["deliveredAt"] = [fin_at]
    desk.now = fin_at + 260
    desk.handle({"seq": 9, "at": desk.now, "kind": "delivered", "gigId": "g2", "orderId": "R2", "leg": 0, "placeId": "vantaa"})
    ord2["deliveredAt"] = [desk.now]
    assert desk.stats["driver_days_2plus"] == 1

    # Test rejoin() rebuilds pos_ledger cleanly
    desk2 = Desk(w, p, 8, geo, roster, now=desk.now)
    snap = {
        "now": desk.now,
        "orders": [ord1, ord2],
        "gigs": [
            {"id": "g1", "stops": desk.posts["g1"]["stops"], "audience": desk.posts["g1"]["audience"], "schedule": [], "status": "done", "postedAt": 555, "feeCents": 7650, "driverId": did},
            {"id": "g2", "stops": desk.posts["g2"]["stops"], "audience": desk.posts["g2"]["audience"], "schedule": [], "status": "done", "postedAt": fin_at - 55, "feeCents": 5850, "driverId": did},
        ],
        "openRequests": [],
        "driverPositions": [],
    }
    hist = [
        {"seq": 1, "at": 540, "kind": "price_request", "request": req1},
        {"seq": 3, "at": 560, "kind": "gig_booked", "gigId": "g1", "driverId": did, "feeCents": 7650},
        {"seq": 4, "at": 600, "kind": "picked_up", "gigId": "g1", "orderId": "R1", "leg": 0, "placeId": "vantaa"},
        {"seq": 8, "at": fin_at, "kind": "delivered", "gigId": "g1", "orderId": "R1", "leg": 0, "placeId": "kuopio"},
        {"seq": 9, "at": desk.now, "kind": "delivered", "gigId": "g2", "orderId": "R2", "leg": 0, "placeId": "vantaa"},
    ]
    desk2.rejoin(snap, hist)
    assert len(desk2.pos_ledger) == 2 and desk2.stats["driver_days_2plus"] == 1
    print("ALL UNIT ASSERTIONS PASSED!", dict(desk.stats))


if __name__ == "__main__":
    main()
