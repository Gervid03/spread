"""Forkless Live Sunday Policy (`SundayStateDesk`): translates TAS Layer 4's hidden-state laws into zero-fork live play.

Implements four neutral-by-default live mechanisms discovered by `tas-state`:
  1. `sun_early_trust_rescue_h`: escalates unbooked Mon..Thu orders of high-trust dealers (`trust >= 8`) early
     (`lastPickupAt - 4.5h` instead of `-3.0h`) so mid-week late deliveries never halve a 25-trust dealer.
  2. `sun_trust_decouple`: zero-mean trust centering `1 + k * 0.01 * (trust[d] - ema_trust)` so a `trust=25`
     dealer (`D01`) captures its trust premium without inflating global `self.mult` and pricing out `trust=0..4`
     dealers (`D02..D40`) sitting in their `<70%` competitor deadband.
  3. `sun_war_defer`: live `08:00-09:30` Price-War detector (`>=7` quotes with `<=12%` win share -> drops
     `same_day` on multi-option daytime requests so War-day drivers serve prior `next_day` backlog).
  4. `sun_comp_band`: guards busy dealers (`>=10` daily requests) from crossing the `70%` competitor price-cut
     cliff on `Mon..Thu`, and calibrates `self.mult = 1.50` on a `Thu 00:00` cold start (`0%` Mon-Wed win share
     -> `+3` competitor hikes).

With default parameters, `SundayStateDesk` reproduces `spread_lab.policy:Desk` to the cent.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

from spread.client import World
from spread.types import DriverProfile, PriceRequest

from ..geo import Geo
from ..policy import DAY, HOUR, Desk, Params, clamp, undelivered


@dataclass
class SundayStateParams(Params):
    sun_early_trust_rescue_h: float = 0.0   # e.g. 4.5 (hours before lastPickupAt on Mon..Thu when trust >= 8)
    sun_trust_min_protect: int = 8          # minimum dealer trust to trigger early Mon..Thu rescue
    sun_trust_decouple: float = 0.0         # e.g. 0.45 (zero-mean trust slope `0.01 * k * (trust - ema_trust)`)
    sun_war_defer: bool = False             # 08:00-09:30 <=12% win-rate War detector -> drop multi-opt same_day
    sun_comp_band: bool = False             # <68% Mon..Thu deadband guard + Thu 00:00 cold-start mult=1.50
    sun_fri_endgame: bool = False           # Friday endgame: no loss_streak_freeze, 1.45x slow backlog, -4% slow quote


class SundayStateDesk(Desk):
    Params = SundayStateParams

    def __init__(self, world: World, params: Params, level: int, geo: Geo, roster: list[DriverProfile], now: int = 0):
        sp = params if isinstance(params, SundayStateParams) else SundayStateParams(**vars(params))
        super().__init__(world, sp, level, geo, roster, now=now)
        self.sp: SundayStateParams = sp
        self.sun_active = bool(
            sp.sun_early_trust_rescue_h > 0
            or sp.sun_trust_decouple > 0
            or sp.sun_war_defer
            or sp.sun_comp_band
            or sp.sun_fri_endgame
        )
        self.ema_trust: float = 0.0
        self.ema_ready: bool = False
        self.sun_early_rescued: set[str] = set()
        self.morn_quoted: Counter[int] = Counter()
        self.morn_won: Counter[int] = Counter()
        self.dlr_reqs_day: Counter[tuple[str, int]] = Counter()
        self.dlr_won_day: Counter[tuple[str, int]] = Counter()

    def handle(self, event: dict[str, Any]) -> None:
        if self.sun_active:
            kind = event["kind"]
            if kind == "price_request":
                req = event["request"]
                d = req["arrivedAt"] // DAY
                self.dlr_reqs_day[(req["dealerId"], d)] += 1
            elif kind in ("order_won", "order_lost"):
                rid = event["requestId"] if kind == "order_lost" else event["order"]["id"]
                req = self.requests.get(rid)
                if req is not None:
                    d, tod = req["arrivedAt"] // DAY, req["arrivedAt"] % DAY
                    if kind == "order_won":
                        self.dlr_won_day[(req["dealerId"], d)] += 1
                    if self.decided.get(rid) in ("quote", "floor") and 8 * HOUR <= tod <= 9 * HOUR + 35:
                        self.morn_quoted[d] += 1
                        if kind == "order_won":
                            self.morn_won[d] += 1
        super().handle(event)

    def tick(self) -> None:
        super().tick()
        if not self.sun_active or self.sp.sun_early_trust_rescue_h <= 0:
            return
        d = self.now // DAY
        if d >= 4:
            return  # Friday late deliveries incur zero downstream trust loss in a 1-week game
        early_min = int(self.sp.sun_early_trust_rescue_h * HOUR)
        for oid, order in list(self.orders.items()):
            if oid in self.urgent or oid in self.sun_early_rescued or not undelivered(order) or self.staffed(order):
                continue
            dlr = self.requests[oid]["dealerId"]
            if self.dealer_trust[dlr] >= self.sp.sun_trust_min_protect and self.now >= order["lastPickupAt"] - early_min:
                self.sun_early_rescued.add(oid)
                self.stats["sun_early_trust_rescued"] += 1
                self.raise_fees(oid)

    def is_live_war_day(self, d: int, tod: int) -> bool:
        if not self.sp.sun_war_defer or not (9 * HOUR + 30 <= tod <= 18 * HOUR):
            return False
        q = self.morn_quoted[d]
        return q >= 7 and (self.morn_won[d] / q) <= 0.12

    def learn(self, request_id: str, won: bool) -> None:
        if self.sun_active and self.sp.sun_fri_endgame and self.now // DAY >= 4:
            self.loss_streak = 0
            orig_tw = self.p.price_target_win
            self.p.price_target_win = max(orig_tw, 0.52)
            try:
                super().learn(request_id, won)
            finally:
                self.p.price_target_win = orig_tw
            return
        super().learn(request_id, won)

    def price(self, request: PriceRequest) -> tuple[dict[str, int], str]:
        if not self.sun_active:
            return super().price(request)

        dlr = request["dealerId"]
        d, tod = request["arrivedAt"] // DAY, request["arrivedAt"] % DAY

        orig_br = self.p.backlog_ratio
        fri_relaxed = False
        if self.sp.sun_fri_endgame and d == 4:
            self.p.backlog_ratio = orig_br * 1.60
            fri_relaxed = True
        try:
            prices, reason = super().price(request)
        finally:
            if fri_relaxed:
                self.p.backlog_ratio = orig_br

        if not prices:
            return prices, reason

        # On Friday endgame, if normal backlog would have blocked it, keep only slow weekend-buffered options
        if fri_relaxed:
            pickup = request["legs"][0]["pickup"]["placeId"]
            gate_sup = self.gate_supply.get(pickup, 0)
            norm_cap = max(self.p.backlog_min + 1, orig_br * (1 - self.tightening()) * gate_sup)
            if self.backlog_near(pickup) >= norm_cap:
                prices = {k: v for k, v in prices.items() if k != "same_day"}
                if not prices:
                    return {}, "backlog"
                self.stats["sun_fri_endgame_admitted"] += 1

        # 1. Live 09:30 Price-War same_day deferral on multi-option requests
        if self.is_live_war_day(d, tod) and "same_day" in prices and len(prices) > 1:
            prices = {k: v for k, v in prices.items() if k != "same_day"}
            self.stats["sun_war_deferred_sameday"] += 1

        # 2. Zero-mean dealer trust decoupling (lifts D01 at trust=25, lowers D02..D40 at trust=0..4)
        adj_factor = 1.0
        if self.sp.sun_trust_decouple > 0:
            tr = float(min(self.dealer_trust[dlr], 25))
            if not self.ema_ready:
                self.ema_trust = tr
                self.ema_ready = True
            else:
                self.ema_trust = 0.96 * self.ema_trust + 0.04 * tr
            diff_tr = tr - self.ema_trust
            adj_factor *= clamp(1.0 + self.sp.sun_trust_decouple * 0.01 * diff_tr, 0.90, 1.14)

        # 3. Competitor <70% Mon..Thu deadband guard on busy dealers (>=10 requests today)
        if self.sp.sun_comp_band and d < 4:
            tot_d = self.dlr_reqs_day[(dlr, d)]
            won_d = self.dlr_won_day[(dlr, d)]
            if tot_d >= 10 and won_d / tot_d >= 0.63:
                adj_factor *= 1.07
                self.stats["sun_comp_band_guarded"] += 1

        if abs(adj_factor - 1.0) > 1e-6:
            fee = max(request["referenceFeeCents"], 1)
            floor = fee / (1.0 - self.p.min_margin_frac)
            prices = {k: max(int(floor + 0.5), int(v * adj_factor + 0.5)) for k, v in prices.items()}

        return prices, reason

    def rejoin(self, snapshot: Any, history: list[Any]) -> None:
        super().rejoin(snapshot, history)
        if not self.sun_active:
            return
        self.dlr_reqs_day.clear()
        self.dlr_won_day.clear()
        self.morn_quoted.clear()
        self.morn_won.clear()
        lost_pre = 0
        for ev in history:
            k = ev["kind"]
            if k == "price_request":
                req = ev["request"]
                self.dlr_reqs_day[(req["dealerId"], req["arrivedAt"] // DAY)] += 1
            elif k == "order_won":
                oid = ev["order"]["id"]
                req = self.requests.get(oid)
                if req:
                    d, tod = req["arrivedAt"] // DAY, req["arrivedAt"] % DAY
                    self.dlr_won_day[(req["dealerId"], d)] += 1
                    if 8 * HOUR <= tod <= 9 * HOUR + 35:
                        self.morn_quoted[d] += 1
                        self.morn_won[d] += 1
            elif k == "order_lost":
                lost_pre += 1
                rid = ev["requestId"]
                req = self.requests.get(rid)
                if req and self.decided.get(rid) in ("quote", "floor"):
                    d, tod = req["arrivedAt"] // DAY, req["arrivedAt"] % DAY
                    if 8 * HOUR <= tod <= 9 * HOUR + 35:
                        self.morn_quoted[d] += 1
        # Thursday 00:00 cold-start calibration (0 orders won, >=300 pre-played lost requests -> +3 competitor hikes!)
        if self.sp.sun_comp_band and self.now >= 3 * DAY and len(self.orders) == 0 and lost_pre >= 300:
            self.mult = max(self.mult, 1.50)
            self.stats["sun_thu_coldstart_calibrated"] += 1


Desk = SundayStateDesk
Params = SundayStateParams
