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


V6_BASE_PARAMS: dict[str, Any] = {
    "backlog_ratio": 0.06,
    "price_target_win": 0.4,
    "min_supply": 22,
    "gate_radius_km": 55.0,
    "far_options": "slow",
    "same_day_min_supply": 50,
    "slack_per_drive": 0.75,
    "long_drive_min": 300,
    "fee_open": 0.85,
    "price_lr": 0.05,
    "offers_per_warning": 0,
    "min_slack_min": 150,
    "trust_invest": 0.05,
    "notes_v2": True,
    "note_unsure": "decline",
    "max_next_day_drive_min": 480,
    "fri_same_day_max_drive": 100,
    "thin_long_next_day_supply": 50,
    "ring_to_hub_same_day_min": 60,
    "backlog_multiday_weight": 0.25,
    "backlog_in_flight_weight": 0.35,
    "dealer_lr": 0.01,
    "ext_ring_min_supply": 30,
    "ext_ring_max_drive_min": 220,
    "return_hub_min_supply": 200,
    "return_hub_max_drive_min": 180,
    "ext_ring_neutral_learn": True,
    "lead_car": True,
    "lead_car_max_gap_km": 0.0,
    "lead_car_max_deliv_gap_km": 25.0,
    "lead_car_fee_mult": 1.0,
    "late_fee_open": 1.0,
    "urgent_hygiene": True,
    "late_reprice_grace_min": 60,
    "drop_reprice_bump": 0.03,
    "steep_open": 1.65,
    "steep_step": 0.2,
    "steep_max": 2.25,
    "view_offer_mult": 1.03,
    "view_offer_cap": 1.15,
    "supervisor": True,
    "sup_stress_sd_supply": 0,
    "sup_stress_slack_add": 0,
    "sup_fri_slow_min_supply": 3,
    "sup_fri_sd_max_drive": 180,
}


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
    cyc_rotate_min: int = 0           # an unbooked cycle is reposted from its next town after this many daytime minutes
                                      # (a car can be in one live gig only, so the rotations take turns; 0 = off)
    cyc_min_on_time: float = 0.0      # hold cars only while the projected on-time share is at least this (0 = always)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Params":
        base = dict(V6_BASE_PARAMS)
        base.update(champion().get("params", {}))
        base.update(raw)
        return super(SundayParams, cls).from_dict(base)


class Desk(SundayDesk):
    Params = Params

    def __init__(self, world: World, params: Params, level: int, geo: Geo, roster: list[DriverProfile], now: int):
        super().__init__(world, params, level, geo, roster, now)
        self.cyc_held: dict[str, int] = {}       # oid -> minute it was held
        self.cyc_done: set[str] = set()          # held once already, or in a cycle: never held again
        self.cyc_dirty = False
        self.cyc_last_search = -10**9
        self.cyc_rots: dict[frozenset, dict[str, Any]] = {}   # a posted cycle's feasible rotations and whose turn it is

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
    def _post_cycle(self, rot: list[str], rots: Optional[list[list[str]]] = None) -> bool:
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
            self.cyc_rots[frozenset(rot)] = {"rots": rots or [rot], "i": 0, "last": self.now}
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
            feas = []
            for i in range(len(c)):
                rot = c[i:] + c[:i]
                sup = self.supply.get(self._ends(rot[0])[0], 0)
                if sup < self.p.cyc_min_supply or self.can_chain_orders_live(rot) is None:
                    continue
                feas.append((sup, rot))
            if feas:
                feas.sort(key=lambda t: -t[0])
                saving = ref * (0.85 - self._mult(len(c)))
                cands.append((saving, len(c), [r for _, r in feas]))
        used: set[str] = set()
        for saving, n, rots in sorted(cands, key=lambda t: (-t[0], -t[1])):
            if used & set(rots[0]):
                continue
            if self._post_cycle(rots[0], rots):
                used |= set(rots[0])

    def _rotate(self) -> None:
        """An unbooked cycle takes turns in the app from each town on it: a car can be in one live gig only, and a
        post notifies the drivers near its first pickup. The patience clock and the fee step carry over."""
        for gid, tinfo in list(self.tour_gigs.items()):
            if gid in self.booked:
                continue
            post = self.posts.get(gid)
            if post is None:
                continue
            oids = order_ids_of(post)
            st = self.cyc_rots.get(frozenset(oids))
            if not st or len(st["rots"]) < 2:
                continue
            if not all(self.leg_gigs.get(o, {}).get(0) == gid for o in oids):
                continue
            if daytime_minutes_between(st["last"], self.now, self.p.day_start, self.p.day_end) < self.p.cyc_rotate_min:
                continue
            st["last"] = self.now
            j = (st["i"] + 1) % len(st["rots"])
            rot = st["rots"][j]
            if self.can_chain_orders_live(rot) is None:
                continue
            self.outbox.append({"type": "withdraw", "gigId": gid})
            for s in post["stops"]:
                self.leg_gigs.get(s["orderId"], {}).pop(s["leg"], None)
            self.tour_gigs.pop(gid, None)
            mult = tinfo["mult"]
            self.tour_open_mult = lambda *a, **k: mult
            try:
                ok = self.post_tour_orders(rot, tid="cycrot")
            finally:
                del self.tour_open_mult
            if ok:
                meta = self._pending_tour_meta.get(tuple(rot))
                if meta:
                    meta["posted_at"], meta["last_step_at"] = tinfo["posted_at"], tinfo["last_step_at"]
                st["i"] = j
                self.stats["cyc_rotated"] += 1
            else:
                for oid in oids:
                    o = self.orders.get(oid)
                    if o and undelivered(o) and not self.gigs_of(oid):
                        super(TasRoutesDesk, self).post(o, undelivered(o))

    # --- holding ------------------------------------------------------------------------------------
    def _hold_fresh_posts(self) -> None:
        keep = []
        tight: Optional[bool] = None
        for a in self.outbox:
            if a["type"] == "post":
                oids = order_ids_of(a)
                if len(oids) == 1:
                    oid = oids[0]
                    o = self.orders.get(oid)
                    if (oid not in self.cyc_done and oid not in self.cyc_held and self._clean(oid)
                            and o["lastPickupAt"] - self.now >= self.p.cyc_hold_slack_min):
                        if tight is None:
                            tight = bool(self.p.cyc_min_on_time) and self.projected_on_time() < self.p.cyc_min_on_time
                        if tight:
                            self.stats["cyc_not_held_tight"] += 1
                            self.cyc_done.add(oid)
                            keep.append(a)
                            continue
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
        if self.p.cyc_rotate_min > 0:
            self._rotate()
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
