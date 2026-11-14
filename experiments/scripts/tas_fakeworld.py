"""A stand-in world for testing TAS plumbing with no key and no network. NOT the game.

It speaks the part of the kit's `World` that the lab uses (snapshot, roster, act, advance, fork, score, events,
reveal, delete) and is deterministic like a practice world: the same seed and actions give the same week, and a
fork has the same future. Its dealers and drivers are toys with hidden numbers that a test can read:

  * a dealer buys an option when its price is at most  list x `limit_x[request]` x (1 + 1% x the dealer's on-time
    orders, at most 25), and takes the fastest option that passes;
  * a gig is booked `delay[order]` minutes after it is posted, in the daytime, once its fee reaches the sum of
    `reserve[order]` over its cars (x 0.8 for a gig with more than one car); the driver then collects and delivers
    each car by the road minutes.

Use it to check that code runs and that an oracle finds the hidden numbers (experiments/scripts/tas_selftest.py),
and while practice is paused. Never read a margin off it.
"""
from __future__ import annotations

import copy
import itertools
import random

HOUR, DAY = 60, 24 * 60
OPTIONS = ["same_day", "next_day", "within_3_days"]
_ids = itertools.count(1)


def business_day_after(day: int, n: int) -> int:
    for _ in range(n):
        day += 1
        while day % 7 in (5, 6):
            day += 1
    return day


class FakeWorld:
    def __init__(self, seed: str, world_map: dict, n_requests: int = 150, _state: dict | None = None):
        self.id = f"fake{next(_ids):05d}"
        self.client = None
        self._last_seq = -1
        self.deleted = False
        if _state is not None:
            self.s = _state
            return
        rng = random.Random(f"fake-{seed}")
        places = [p["id"] for p in world_map["places"]]
        road = {(r["from"], r["to"]): (r["km"], int(r["minutes"])) for r in world_map["roads"]}
        dealers = [f"dealer{i:02d}" for i in range(12)]
        requests, limit_x, reserve, delay = [], {}, {}, {}
        for i in range(n_requests):
            day = rng.randrange(5)
            arrived = day * DAY + rng.randrange(9 * HOUR, 18 * HOUR)
            a, b = rng.sample(places[:12], 2)
            km, minutes = road[(a, b)]
            base = round(30 + 1.1 * km) * 100
            options = []
            if arrived % DAY <= 15 * HOUR and arrived + 30 + minutes <= day * DAY + 18 * HOUR:
                options.append({"kind": "same_day", "deadline": day * DAY + 20 * HOUR, "listPriceCents": base})
            options.append({"kind": "next_day", "deadline": business_day_after(day, 1) * DAY + 20 * HOUR, "listPriceCents": round(base * 0.93 / 100) * 100})
            if rng.random() < 0.3:
                options.append({"kind": "within_3_days", "deadline": min(7, business_day_after(day, 3)) * DAY + 20 * HOUR,
                                "listPriceCents": round(base * 0.86 / 100) * 100})
            last = max(o["deadline"] for o in options)
            hours = {"opens": 7 * HOUR, "closes": 20 * HOUR, "weekdays": [0, 1, 2, 3, 4], "saturday": None}
            rid = f"R{i:05d}"
            requests.append({
                "id": rid, "dealerId": rng.choice(dealers), "batchId": None, "arrivedAt": arrived, "respondBy": arrived + 15,
                "legs": [{"car": {"premium": False, "electric": False, "chargePercent": None},
                          "pickup": {"placeId": a, "privateAddress": False, "window": {"from": arrived + 30, "to": last}, "hours": hours},
                          "delivery": {"placeId": b, "privateAddress": False, "window": {"from": arrived + 30, "to": last}, "hours": hours}}],
                "options": options, "referenceFeeCents": int(base * rng.uniform(0.7, 1.0)), "note": None,
            })
            limit_x[rid] = round(rng.uniform(1.05, 1.9), 4)
            reserve[rid] = int(requests[-1]["referenceFeeCents"] * rng.uniform(0.6, 1.2))
            delay[rid] = rng.randrange(5, 90)
        requests.sort(key=lambda r: (r["arrivedAt"], r["id"]))
        roster = [{"id": f"d{p}-{k}", "homePlaceId": p, "rating": 4.9, "licence": "manual", "completedGigs": 80, "drops": 0}
                  for p in places for k in range(40)]
        self.s = {
            "now": 0, "ends_at": 14280, "seq": 0, "events": [], "requests": requests, "next": 0, "road": road, "roster": roster,
            "limit_x": limit_x, "reserve": reserve, "delay": delay, "quotes": {}, "open": {}, "orders": {}, "gigs": {}, "gig_n": 0,
            "trust": {}, "agenda": [], "late": [], "warned": [], "ended": False, "outcome": {}, "limit_cents": {},
        }

    # --- the kit's World surface ------------------------------------------------------------------------------
    def snapshot(self) -> dict:
        s = self.s
        return {"worldId": self.id, "now": s["now"], "endsAt": s["ends_at"], "openRequests": list(s["open"].values()),
                "orders": [self._public(o) for o in s["orders"].values()], "gigs": [dict(g) for g in s["gigs"].values()],
                "driverPositions": [], "score": self.score()}

    def roster(self) -> list:
        return copy.deepcopy(self.s["roster"])

    def events(self, after: int = -1, limit=None) -> list:
        return [e for e in self.s["events"] if e["seq"] > after]

    def fork(self) -> "FakeWorld":
        return FakeWorld("", {}, _state=copy.deepcopy(self.s))

    def delete(self) -> None:
        self.deleted = True

    def score(self) -> dict:
        s = self.s
        margin = sum(e["line"]["cents"] for e in s["events"] if e["kind"] == "ledger")
        revenue = sum(e["line"]["cents"] for e in s["events"] if e["kind"] == "ledger" and e["line"]["kind"] == "revenue")
        won = len(s["orders"])
        late = len({oid for oid in s["late"]} | {o["id"] for o in s["orders"].values() if None in o["deliveredAt"] and s["now"] > o["deadline"]})
        return {"marginCents": margin, "revenueCents": revenue, "marginShare": margin / revenue if revenue else 0.0, "wonOrders": won,
                "onTimeShare": 1 - late / won if won else 0.0, "undeliveredShare": 0.0, "ranked": won > 0 and 1 - late / won >= 0.9}

    def reveal(self) -> dict:
        s = self.s
        return {"requests": [{"request": r, "quote": s["quotes"].get(r["id"]), "outcome": s["outcome"].get(r["id"], ("unquoted", None))[0],
                              "option": s["outcome"].get(r["id"], (None, None))[1]} for r in s["requests"][:s["next"]]],
                "orders": [], "views": []}

    def act(self, actions) -> list:
        return [self._do(a) for a in actions]

    def advance(self, to=None, by=None, until=None, max=None, actions=()) -> dict:
        s = self.s
        results = self.act(actions)
        target = min(s["ends_at"], max if until is not None else (to if to is not None else s["now"] + by))
        while s["now"] < target:
            before = len(s["events"])
            self._minute()
            if until is not None and any(e["kind"] in until for e in s["events"][before:]):
                break
        events = [e for e in s["events"] if e["seq"] > self._last_seq]
        if events:
            self._last_seq = events[-1]["seq"]
        return {"now": s["now"], "events": copy.deepcopy(events), "results": results}

    # --- the toy world ----------------------------------------------------------------------------------------
    def _emit(self, kind: str, **fields) -> None:
        s = self.s
        s["events"].append({"seq": s["seq"], "at": s["now"], "kind": kind, **fields})
        s["seq"] += 1

    def _public(self, order: dict) -> dict:
        return copy.deepcopy({k: v for k, v in order.items() if not k.startswith("_")})

    def _fee(self, gig: dict) -> int:
        steps = [st for st in gig["schedule"] if st["at"] <= self.s["now"]]
        return (steps[-1] if steps else gig["schedule"][0])["feeCents"]

    def _do(self, a: dict) -> dict:
        s = self.s
        if a["type"] == "quote":
            r = s["open"].get(a["requestId"])
            if r is None or s["now"] >= r["respondBy"]:
                return {"ok": False, "reason": f"Request {a['requestId']} is not open"}
            if not a["prices"] or set(a["prices"]) - {o["kind"] for o in r["options"]}:
                return {"ok": False, "reason": "A quote prices options that the dealer accepts"}
            s["quotes"][r["id"]] = dict(a["prices"])
            return {"ok": True, "id": r["id"]}
        if a["type"] == "post":
            fees = [st["feeCents"] for st in a["schedule"]]
            if not a["stops"] or fees != sorted(fees) or any(st["orderId"] not in s["orders"] for st in a["stops"]):
                return {"ok": False, "reason": "A gig needs stops of won orders and fees that never fall"}
            s["gig_n"] += 1
            gid = f"g{s['gig_n']}"
            s["gigs"][gid] = {"id": gid, "stops": copy.deepcopy(a["stops"]), "audience": dict(a["audience"]), "schedule": copy.deepcopy(a["schedule"]),
                              "status": "open", "postedAt": s["now"], "feeCents": fees[0], "driverId": None}
            return {"ok": True, "id": gid}
        gig = s["gigs"].get(a.get("gigId"))
        if gig is None or gig["status"] != "open":
            return {"ok": False, "reason": f"Gig {a.get('gigId')} is not open"}
        if a["type"] == "reprice":
            gig["schedule"] = copy.deepcopy(a["schedule"])
        elif a["type"] == "withdraw":
            gig["status"] = "withdrawn"
        elif a["type"] == "offer":
            s["agenda"].append((s["now"] + 10, "offer_answered", {"gigId": gig["id"], "driverId": a["driverId"], "answer": "expired"}))
        else:
            return {"ok": False, "reason": "Not in the toy world"}
        return {"ok": True, "id": gig["id"]}

    def _minute(self) -> None:
        s = self.s
        s["now"] += 1
        t = s["now"]
        while s["next"] < len(s["requests"]) and s["requests"][s["next"]]["arrivedAt"] <= t:
            r = s["requests"][s["next"]]
            s["next"] += 1
            s["open"][r["id"]] = r
            self._emit("price_request", request=copy.deepcopy(r))
        for rid in [rid for rid, r in s["open"].items() if r["respondBy"] <= t]:
            r = s["open"].pop(rid)
            quote = s["quotes"].get(rid)
            if quote is None:
                continue
            trust = 1 + 0.01 * min(25, s["trust"].get(r["dealerId"], 0))
            s["limit_cents"][rid] = {o["kind"]: int(o["listPriceCents"] * s["limit_x"][rid] * trust) for o in r["options"]}   # for tests
            took = next((o for o in r["options"] if o["kind"] in quote and quote[o["kind"]] <= o["listPriceCents"] * s["limit_x"][rid] * trust), None)
            if took is None:
                s["outcome"][rid] = ("lost", None)
                self._emit("order_lost", requestId=rid)
                continue
            drive = s["road"][(r["legs"][0]["pickup"]["placeId"], r["legs"][0]["delivery"]["placeId"])][1]
            order = {"id": rid, "dealerId": r["dealerId"], "option": took["kind"], "priceCents": quote[took["kind"]], "deadline": took["deadline"],
                     "legs": copy.deepcopy(r["legs"]), "status": "waiting", "deliveredAt": [None], "lastPickupAt": took["deadline"] - drive}
            s["orders"][rid] = order
            s["outcome"][rid] = ("won", took["kind"])
            self._emit("order_won", order=self._public(order))
        daytime = 7 * HOUR <= t % DAY < 22 * HOUR
        for gig in list(s["gigs"].values()):
            if gig["status"] != "open":
                continue
            oids = list(dict.fromkeys(st["orderId"] for st in gig["stops"]))
            if t > min(s["orders"][o]["deadline"] for o in oids) and any("window" in st for st in gig["stops"]):
                gig["status"] = "withdrawn"
                self._emit("gig_expired", gigId=gig["id"])
                continue
            need = sum(s["reserve"][o] for o in oids) * (0.8 if len(oids) > 1 else 1.0)
            if daytime and t >= gig["postedAt"] + s["delay"][oids[0]] and self._fee(gig) >= need:
                gig.update(status="booked", driverId="d" + gig["id"], feeCents=self._fee(gig))
                self._emit("gig_booked", gigId=gig["id"], driverId=gig["driverId"], feeCents=gig["feeCents"])
                at, here = t + 20, None
                s["agenda"].append((at, "gig_started", {"gigId": gig["id"], "driverId": gig["driverId"]}))
                for st in gig["stops"]:
                    leg = s["orders"][st["orderId"]]["legs"][st["leg"]]
                    place = leg[st["kind"]]["placeId"]
                    at = max(at + (s["road"][(here, place)][1] if here else 0), leg["pickup"]["window"]["from"] if st["kind"] == "pickup" else 0)
                    here = place
                    s["agenda"].append((at, "picked_up" if st["kind"] == "pickup" else "delivered",
                                        {"gigId": gig["id"], "orderId": st["orderId"], "leg": st["leg"], "placeId": place}))
                s["agenda"].append((at, "_paid", {"gigId": gig["id"]}))
        for order in s["orders"].values():
            if order["id"] not in s["warned"] and t >= order["lastPickupAt"] - 3 * HOUR and order["status"] == "waiting" \
                    and not any(g["status"] in ("booked", "working") and any(st["orderId"] == order["id"] for st in g["stops"]) for g in s["gigs"].values()):
                s["warned"].append(order["id"])
                self._emit("deadline_close", orderId=order["id"], lastPickupAt=order["lastPickupAt"])
        due = sorted((x for x in s["agenda"] if x[0] <= t), key=lambda x: x[0])
        s["agenda"] = [x for x in s["agenda"] if x[0] > t]
        for _, kind, fields in due:
            if kind == "_paid":
                gig = s["gigs"][fields["gigId"]]
                gig["status"] = "done"
                oids = list(dict.fromkeys(st["orderId"] for st in gig["stops"]))
                self._emit("ledger", line={"at": t, "kind": "driver_fee", "cents": -gig["feeCents"], "orderId": oids[0] if len(oids) == 1 else None,
                                           "gigId": gig["id"], "detail": ""})
                continue
            self._emit(kind, **fields)
            if kind == "gig_started":
                s["gigs"][fields["gigId"]]["status"] = "working"
            if kind == "delivered":
                order = s["orders"][fields["orderId"]]
                order["deliveredAt"][fields["leg"]] = t
                order["status"] = "delivered"
                self._emit("ledger", line={"at": t, "kind": "revenue", "cents": order["priceCents"], "orderId": order["id"], "gigId": None, "detail": ""})
                if t > order["deadline"]:
                    s["late"].append(order["id"])
                    s["trust"][order["dealerId"]] = s["trust"].get(order["dealerId"], 0) // 2
                    share = 0.10 if t - order["deadline"] <= 2 * HOUR else 0.25
                    self._emit("ledger", line={"at": t, "kind": "late_refund", "cents": -int(order["priceCents"] * share), "orderId": order["id"],
                                               "gigId": None, "detail": ""})
                else:
                    s["trust"][order["dealerId"]] = s["trust"].get(order["dealerId"], 0) + 1
        if t >= s["ends_at"] and not s["ended"]:
            s["ended"] = True
            for order in s["orders"].values():
                if None in order["deliveredAt"]:
                    s["late"].append(order["id"])
                    self._emit("ledger", line={"at": t, "kind": "undelivered_penalty", "cents": -2 * order["priceCents"], "orderId": order["id"],
                                               "gigId": None, "detail": ""})
