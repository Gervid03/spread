"""Cycle desk (`spread_lab.policies.cycles:Desk`): closed 2-4 car tours as one gig, on top of the tour desks.

The user's idea, Sat 14 Nov: a driver who lives anywhere on a closed cycle of jobs (A->B, B->C, C->A) can drive all of
it and end at home, so the trip home (most of a single car's fee) is paid once for the whole cycle. tas-routes measured
on forks that closed 2-4 car tours book at 0.31-0.43x the summed typical fee, against ~0.8x for single cars.

What this desk adds to `sunday_tours` (all off by default, so it plays as its parent):
  - `cyc`: a won one-car order with slack is HELD off the board (its single post is taken back out of the outbox) for
    up to `cyc_hold_min` daytime minutes, so a cycle can form before a driver books the car alone (singles book in
    5-15 minutes; the return request comes 30-120 minutes later);
  - whenever the pool changes (held cars and open, unbooked single gigs), it searches the closed cycles of 2 to
    `cyc_max_cars` cars, picks the best by saving, and posts each as one flat gig at `cyc_mult_<n>` x the summed
    typical fee, from the feasible rotation whose start town has the most drivers;
  - `cyc_quote`: a request that would close a cycle with the pool is quoted to win (slow options at most
    `cyc_quote_mult` x list, never under the tour's fee share), also when the parent desk declined it.
Held cars go to the board alone after the hold, or 5 h before their last pickup. Tours that nobody books are stepped
up and split back to single cars by the tour desk (`tour_step_interval_min`, `tour_max_wait_min`).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from spread.client import World
from spread.types import DeskEvent, DeskSnapshot, DriverProfile, Order, PriceRequest

from ..geo import Geo
from ..lab import champion
from ..notes import parse_note_v2
from ..policy import DAY, daytime_minutes_between, order_ids_of, undelivered
from .sunday_tours import Desk as SundayDesk, Params as SundayParams
from .tas_routes import Desk as TasRoutesDesk

KM = 30.0


@dataclass
class Params(SundayParams):
    cyc: bool = False                 # master switch; False = the parent desk exactly
    cyc_hold_min: int = 120           # daytime minutes a won car waits off the board for cycle partners
    cyc_hold_slack_min: int = 480     # hold only when lastPickupAt - now >= this
    cyc_max_cars: int = 4             # longest cycle searched
    cyc_same_day: bool = False        # also hold and cycle same_day cars
    cyc_mult_2: float = 0.60          # flat opening fee of a closed 2-car tour, x the summed typical fee
    cyc_mult_3: float = 0.55
    cyc_mult_4: float = 0.52
    cyc_min_supply: int = 15          # the start town of a posted cycle needs at least this many drivers near it
    cyc_quote: bool = False           # quote requests that close a cycle with the pool to win
    cyc_quote_mult: float = 1.20      # at most this x list on a cycle-closing quote
    cyc_search_every_min: int = 5     # search at most this often (game minutes), and when the pool changed
    cyc_km: float = 30.0              # a car's delivery this close (straight line) to the next pickup, and back home

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Params":
        base = dict(champion().get("params", {}))
        base.update(raw)
        return super().from_dict(base)


class Desk(SundayDesk):
    Params = Params

    def __init__(self, world: World, params: Params, level: int, geo: Geo, roster: list[DriverProfile], now: int):
        super().__init__(world, params, level, geo, roster, now)
        self.cyc_held: dict[str, int] = {}       # oid -> minute it was held
        self.cyc_done: set[str] = set()          # held once already, or in a cycle: never held again
        self.cyc_dirty = False
        self.cyc_last_search = -10**9

    # --- the pool -----------------------------------------------------------------------------------
    def _ends(self, x: str) -> tuple[str, str]:
        r = self.orders.get(x) or self.requests[x]
        return r["legs"][0]["pickup"]["placeId"], r["legs"][0]["delivery"]["placeId"]

    def _clean(self, oid: str) -> bool:
        o = self.orders.get(oid)
        if o is None or len(o["legs"]) != 1 or undelivered(o) != [0] or oid in self.urgent or oid in self.lost:
            return False
        if o["option"] == "same_day" and not self.p.cyc_same_day:
            return False
        req = self.requests.get(oid)
        return not (req and req.get("note") and parse_note_v2(req["note"], req["arrivedAt"]).unsure)

    def _pool(self) -> list[str]:
        pool = [oid for oid in self.cyc_held if self._clean(oid)]
        for gid, post in self.posts.items():
            if gid in self.booked or gid in getattr(self, "tour_gigs", {}):
                continue
            oids = order_ids_of(post)
            if len(oids) == 1 and oids[0] not in self.cyc_held and self._clean(oids[0]) and self.leg_gigs.get(oids[0], {}).get(0) == gid:
                pool.append(oids[0])
        return pool

    def _cycles(self, ids: list[str], must: Optional[str] = None) -> list[list[str]]:
        P = {x: self._ends(x)[0] for x in ids}
        D = {x: self._ends(x)[1] for x in ids}
        near = lambda a, b: a == b or self.geo.line_km(a, b) <= self.p.cyc_km
        nxt = {a: [b for b in ids if b != a and near(D[a], P[b])] for a in ids}
        pos = {x: i for i, x in enumerate(ids)}
        out: list[list[str]] = []

        def dfs(start, path):
            if len(path) >= 2 and near(D[path[-1]], P[start]) and (must is None or must in path):
                out.append(list(path))
            if len(path) < self.p.cyc_max_cars:
                for b in nxt[path[-1]]:
                    if pos[b] > pos[start] and b not in path:
                        dfs(start, path + [b])

        for s in ids:
            dfs(s, [s])
        return out

    def _mult(self, n: int) -> float:
        return self.p.cyc_mult_2 if n == 2 else self.p.cyc_mult_3 if n == 3 else self.p.cyc_mult_4

    # --- posting cycles -------------------------------------------------------------------------------
    def _post_cycle(self, rot: list[str]) -> bool:
        for oid in rot:
            for gid, post in list(self.posts.items()):
                if gid in self.booked:
                    continue
                held = set(order_ids_of(post))
                if oid in held:
                    if held - set(rot):
                        return False
                    self.outbox.append({"type": "withdraw", "gigId": gid})
                    for s in post["stops"]:
                        self.leg_gigs.get(s["orderId"], {}).pop(s["leg"], None)
        self.outbox[:] = [a for a in self.outbox if not (a["type"] == "post" and set(order_ids_of(a)) & set(rot))]
        mult = self._mult(len(rot))
        self.tour_open_mult = lambda *a, **k: mult
        try:
            ok = self.post_tour_orders(rot, tid="cyc")
        finally:
            del self.tour_open_mult
        for oid in rot:
            self.cyc_held.pop(oid, None)
            self.staged_orders.pop(oid, None)
            self.cyc_done.add(oid)
        if ok:
            self.stats[f"cyc_posted_{len(rot)}"] += 1
        else:
            self.stats["cyc_post_refused"] += 1
            for oid in rot:
                o = self.orders.get(oid)
                if o and undelivered(o) and not self.gigs_of(oid):
                    super(TasRoutesDesk, self).post(o, undelivered(o))
        return ok

    def _search(self) -> None:
        pool = self._pool()
        if len(pool) < 2:
            return
        cands = []
        for c in self._cycles(pool):
            ref = sum(self.requests[x]["referenceFeeCents"] for x in c)
            best = None
            for i in range(len(c)):
                rot = c[i:] + c[:i]
                start = self._ends(rot[0])[0]
                sup = self.supply.get(start, 0)
                if sup < self.p.cyc_min_supply:
                    continue
                if self.can_chain_orders_live(rot) is None:
                    continue
                if best is None or sup > best[0]:
                    best = (sup, rot)
            if best:
                saving = ref * (0.85 - self._mult(len(c)))
                cands.append((saving, len(c), best[1]))
        used: set[str] = set()
        for saving, n, rot in sorted(cands, key=lambda t: (-t[0], -t[1])):
            if used & set(rot):
                continue
            if self._post_cycle(rot):
                used |= set(rot)

    # --- holding ------------------------------------------------------------------------------------
    def _hold_fresh_posts(self) -> None:
        keep = []
        for a in self.outbox:
            if a["type"] == "post":
                oids = order_ids_of(a)
                if len(oids) == 1:
                    oid = oids[0]
                    o = self.orders.get(oid)
                    if (oid not in self.cyc_done and oid not in self.cyc_held and self._clean(oid)
                            and o["lastPickupAt"] - self.now >= self.p.cyc_hold_slack_min):
                        self.cyc_held[oid] = self.now
                        self.stats["cyc_held"] += 1
                        self.cyc_dirty = True
                        continue
                    if oid in self.cyc_held:   # the parent desk reposted a car we hold
                        continue
            keep.append(a)
        self.outbox[:] = keep

    def _release(self) -> None:
        for oid, at in list(self.cyc_held.items()):
            o = self.orders.get(oid)
            if o is None or not undelivered(o) or oid in self.lost:
                self.cyc_held.pop(oid, None)
                continue
            waited = daytime_minutes_between(at, self.now, self.p.day_start, self.p.day_end)
            if oid in self.urgent or waited >= self.p.cyc_hold_min or o["lastPickupAt"] - self.now <= self.p.tour_hold_guard_min:
                self.cyc_held.pop(oid, None)
                self.cyc_done.add(oid)
                self.stats["cyc_released_solo"] += 1
                super(TasRoutesDesk, self).post(o, undelivered(o))

    # --- the desk's hooks -----------------------------------------------------------------------------
    def tick(self) -> None:
        super().tick()
        if not self.p.cyc:
            return
        self._hold_fresh_posts()
        if self.cyc_dirty or self.now - self.cyc_last_search >= self.p.cyc_search_every_min:
            self.cyc_dirty = False
            self.cyc_last_search = self.now
            self._search()
        self._release()

    def win(self, order: Order) -> None:
        super().win(order)
        if self.p.cyc:
            self.cyc_dirty = True

    def price(self, request: PriceRequest) -> tuple[dict[str, int], str]:
        prices, decision = super().price(request)
        if not (self.p.cyc and self.p.cyc_quote) or len(request["legs"]) != 1 or self.level < 4:
            return prices, decision
        if request.get("note") and parse_note_v2(request["note"], request["arrivedAt"]).unsure:
            return prices, decision
        pool = self._pool()
        if not pool or not self._cycles(pool + [request["id"]], must=request["id"]):
            return prices, decision
        floor = request["referenceFeeCents"] * (self.p.cyc_mult_3 + 0.10) / max(0.01, 1 - self.p.min_margin_frac)
        out: dict[str, int] = {}
        for opt in request["options"]:
            if opt["kind"] == "same_day" and not self.p.cyc_same_day:
                continue
            cap = opt["listPriceCents"] * self.p.cyc_quote_mult
            cur = prices.get(opt["kind"]) if decision != "decline" else None
            out[opt["kind"]] = int(max(floor, min(cur, cap) if cur else cap) + 0.5)
        if not out:
            return prices, decision
        self.stats["cyc_quoted"] += 1
        return out, "quote"

    def rejoin(self, snapshot: DeskSnapshot, history: list[DeskEvent]) -> None:
        super().rejoin(snapshot, history)
        self.cyc_held.clear()
