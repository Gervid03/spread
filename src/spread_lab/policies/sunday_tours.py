"""Forkless Sunday Rule Policy (`spread_lab.policies.sunday_tours:Desk`).

Translates the TAS Routes discoveries into a 100% live-compatible, zero-fork, zero-foresight policy:
  1) Corridor Staging (`sunday_stage_min`): holds non-urgent (`next_day` / `within_3_days`) orders on the
     high-return Southern Triangle corridors (`Capital <-> Hyvinkää / Tampere / Turku / Lahti`, where Step 5
     measured 46%-84% 4-hour return arrival rates) for up to `sunday_stage_min` daytime minutes so Capital's
     350 drivers don't snatch the outbound leg solo at `0.85x ref` before the return leg arrives!
  2) Closed 2- & 3-Car Tour Bundling (`sunday_tours`): bundles staged + open unbooked orders into closed
     2-car round trips (`0.58x sum(ref)` flat) and 3-car closed triangles (`0.52x sum(ref)` flat), stepping
     flat once (`+0.12x`) at +50m and splitting cleanly to solo at +100m or `lastPickupAt - 330m`.
  3) 1-to-1 Sponsored Thin-Town Return Quoting (`sunday_tour_quote`): quotes slow options on declined thin-town
     requests (`supply < min_supply`) when they close an outbound hub order already in hand.

With defaults (`sunday_tours=False`), reproduces Champion (`spread_lab.policy:Desk`) to the cent (`Δ = €0.00`).
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Optional

from spread.client import World
from spread.types import DeskEvent, DeskSnapshot, DriverProfile, Order, PriceRequest

from ..geo import Geo
from ..lab import champion
from ..notes import parse_note_v2, shift_business_days, window_from_note
from ..policy import DAY, HOUR, daytime_minutes_between, order_ids_of, undelivered
from .tas_routes import Desk as TasRoutesDesk, Params as TasRoutesParams

HIGH_RETURN_PLACES = {"vantaa", "helsinki", "espoo", "hyvinkaa", "tampere", "lempaala", "turku", "raisio", "salo", "lahti"}


def _corridor_cluster(place: str) -> str:
    if place in ("vantaa", "helsinki", "espoo"):
        return "cap"
    if place in ("tampere", "lempaala"):
        return "tre"
    if place in ("turku", "raisio", "salo"):
        return "tku"
    return place


@dataclass
class Params(TasRoutesParams):
    sunday_tours: bool = False          # master switch; False = exact BaseDesk noop
    sunday_stage_min: int = 0           # daytime minutes to stage high-return corridor slow orders (e.g. 90)
    sunday_stage_min_slack: int = 480   # require lastPickupAt - now >= this to stage an order
    sunday_tour_quote: bool = False     # quote declined thin-town slow requests when they close an in-hand hub car
    sunday_quote_cap_day: int = 8       # max thin-town return wins per day

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Params":
        base = dict(champion().get("params", {}))
        base.update(raw)
        return super().from_dict(base)


class Desk(TasRoutesDesk):
    Params = Params

    def __init__(self, world: World, params: Params, level: int, geo: Geo, roster: list[DriverProfile], now: int):
        super().__init__(world, params, level, geo, roster, now)
        self.staged_orders: dict[str, int] = {}          # oid -> staged_at minute
        self.sponsored_req_to_hub: dict[str, str] = {}   # thin request_id -> sponsoring hub oid
        self.used_sponsors: set[str] = set()             # hub oids currently sponsoring an in-flight quote
        self.sunday_quote_wins_day: Counter = Counter()

    def _is_high_return_corridor(self, order: Order) -> bool:
        if len(order["legs"]) != 1 or order["option"] == "same_day":
            return False
        p = order["legs"][0]["pickup"]["placeId"]
        d = order["legs"][0]["delivery"]["placeId"]
        return p in HIGH_RETURN_PLACES and d in HIGH_RETURN_PLACES and _corridor_cluster(p) != _corridor_cluster(d)

    def _candidate_pool_oids(self) -> list[str]:
        """All clean 1-leg won orders currently either in `staged_orders` or in an open unbooked 1/2-car gig."""
        if any(a["type"] == "post" for a in self.outbox) and not any(a["type"] == "quote" for a in self.outbox):
            self.send()
        pool: list[str] = []
        for oid in sorted(self.staged_orders):
            if oid in self.orders and len(self.orders[oid]["legs"]) == 1 and undelivered(self.orders[oid]) == [0] and oid not in self.urgent and oid not in self.lost:
                pool.append(oid)
        for gid, post in self.posts.items():
            if gid in self.booked or gid in self.tour_gigs:
                continue
            oids = order_ids_of(post)
            if len(oids) == 1:
                oid = oids[0]
                if (
                    oid not in self.staged_orders
                    and oid in self.orders
                    and len(self.orders[oid]["legs"]) == 1
                    and self.leg_gigs.get(oid, {}).get(0) == gid
                    and oid not in self.urgent
                    and oid not in self.lost
                ):
                    pool.append(oid)
        return pool

    def _try_bundle_with_pool(self, new_oid: str) -> bool:
        """Tries to form the highest-saving closed 2-car or 3-car tour involving `new_oid` and `_candidate_pool_oids`."""
        pool = [x for x in self._candidate_pool_oids() if x != new_oid]
        if not pool:
            return False
        best: Optional[tuple[float, list[str]]] = None

        # 1. Check 2-car closed tours
        for other in pool:
            for seq in ([other, new_oid], [new_oid, other]):
                p0 = self.orders[seq[0]]["legs"][0]["pickup"]["placeId"]
                if self.supply.get(p0, 0) < 22:
                    continue
                da = self.orders[seq[0]]["legs"][0]["delivery"]["placeId"]
                pb = self.orders[seq[1]]["legs"][0]["pickup"]["placeId"]
                dk = self.orders[seq[1]]["legs"][0]["delivery"]["placeId"]
                if self.geo.line_km(da, pb) > self.p.tour_deadhead_km or self.geo.line_km(dk, p0) > self.p.tour_close_km:
                    continue
                if min(self.orders[x]["lastPickupAt"] for x in seq) - self.now <= self.p.tour_split_guard_min + 90:
                    continue
                info = self.can_chain_orders_live(seq, slack_override=135)
                if info and info["closed"]:
                    ref_sum = sum(self.requests[x]["referenceFeeCents"] for x in seq)
                    sav = ref_sum * 0.36 - 15.0 * (info["road_min"] / 60.0)
                    if best is None or sav > best[0]:
                        best = (sav, seq)

        # 2. Check 3-car closed triangles if pool <= 25
        if len(pool) <= 25 and self.p.tour_max_cars >= 3:
            for i in range(len(pool)):
                a_id = pool[i]
                for j in range(len(pool)):
                    if i == j:
                        continue
                    b_id = pool[j]
                    for seq in ([a_id, b_id, new_oid], [a_id, new_oid, b_id], [new_oid, a_id, b_id]):
                        p0 = self.orders[seq[0]]["legs"][0]["pickup"]["placeId"]
                        if self.supply.get(p0, 0) < 25:
                            continue
                        if (
                            self.geo.line_km(self.orders[seq[0]]["legs"][0]["delivery"]["placeId"], self.orders[seq[1]]["legs"][0]["pickup"]["placeId"]) > self.p.tour_deadhead_km
                            or self.geo.line_km(self.orders[seq[1]]["legs"][0]["delivery"]["placeId"], self.orders[seq[2]]["legs"][0]["pickup"]["placeId"]) > self.p.tour_deadhead_km
                            or self.geo.line_km(self.orders[seq[2]]["legs"][0]["delivery"]["placeId"], p0) > self.p.tour_close_km
                        ):
                            continue
                        if min(self.orders[x]["lastPickupAt"] for x in seq) - self.now <= self.p.tour_split_guard_min + 120:
                            continue
                        info3 = self.can_chain_orders_live(seq, slack_override=150)
                        if info3 and info3["closed"]:
                            ref_sum = sum(self.requests[x]["referenceFeeCents"] for x in seq)
                            sav3 = ref_sum * 0.44 - 15.0 * (info3["road_min"] / 60.0)
                            if best is None or sav3 > best[0]:
                                best = (sav3, seq)

        if best is None:
            return False

        _, chosen_seq = best
        # Withdraw any solo gigs currently holding orders in chosen_seq
        withdrawn_oids: list[str] = []
        for x in chosen_seq:
            self.staged_orders.pop(x, None)
            self.used_sponsors.discard(x)
            for gid in list(self.gigs_of(x)):
                if gid not in self.booked:
                    self.outbox.append({"type": "withdraw", "gigId": gid})
                    self.leg_gigs.get(x, {}).pop(0, None)
                    withdrawn_oids.append(x)
        if self.post_tour_orders(chosen_seq, tid="sunday"):
            self.stats["sunday_tour_posted"] += 1
            return True
        for x in chosen_seq:
            if x in self.orders and undelivered(self.orders[x]) and not self.gigs_of(x):
                super(TasRoutesDesk, self).post(self.orders[x], undelivered(self.orders[x]), allow_pair=False)
        return False

    def _find_sponsor_for_thin_request(self, request: PriceRequest) -> Optional[str]:
        if len(request["legs"]) != 1:
            return None
        if request.get("note") and parse_note_v2(request["note"], request["arrivedAt"]).unsure:
            return None
        rp = request["legs"][0]["pickup"]["placeId"]
        rd = request["legs"][0]["delivery"]["placeId"]
        r_drv = self.geo.minutes(rp, rd)
        for hub_oid in self._candidate_pool_oids():
            if hub_oid in self.used_sponsors:
                continue
            ho = self.orders[hub_oid]
            hp = ho["legs"][0]["pickup"]["placeId"]
            hd = ho["legs"][0]["delivery"]["placeId"]
            if self.supply.get(hp, 0) < 25:
                continue
            if self.geo.line_km(hd, rp) > self.p.tour_deadhead_km or self.geo.line_km(rd, hp) > self.p.tour_close_km:
                continue
            tot_road = self.geo.minutes(hp, hd) + self.geo.minutes(hd, rp) + r_drv
            if tot_road > min(680, self.p.tour_max_road_min):
                continue
            if ho["lastPickupAt"] - self.now <= 360:
                continue
            return hub_oid
        return None

    def pair_base_cents(self, oids: list[str]) -> float:
        if not self.p.sunday_tours:
            return super(TasRoutesDesk, self).pair_base_cents(oids)
        return super().pair_base_cents(oids)

    def price(self, request: PriceRequest) -> tuple[dict[str, int], str]:
        if not self.p.sunday_tours:
            return super(TasRoutesDesk, self).price(request)
        prices, decision = super(TasRoutesDesk, self).price(request)
        if prices or not self.p.sunday_tour_quote:
            return prices, decision

        day = self.now // DAY
        if self.sunday_quote_wins_day[day] >= self.p.sunday_quote_cap_day:
            return prices, decision
        sponsor = self._find_sponsor_for_thin_request(request)
        if sponsor is None:
            return prices, decision

        # Quote slow options (`next_day`, `within_3_days`) with closed-tour marginal cost floor (`0.65x ref`)
        leg0 = request["legs"][0]
        pn = parse_note_v2(request["note"], request["arrivedAt"]) if request.get("note") else parse_note_v2(None)
        extra_days = max(0, pn.ready_at // DAY - leg0["pickup"]["window"]["from"] // DAY) if (pn.ready_at is not None and not leg0["pickup"]["privateAddress"]) else 0
        mult = self.mult * self.dealer_adj[request["dealerId"]]
        if self.p.trust_gain > 0:
            mult *= (1 + self.p.trust_gain * self.dealer_trust[request["dealerId"]] / 100.0)
        min_price = request["referenceFeeCents"] * 0.68 / max(0.01, 1 - self.p.min_margin_frac)

        sponsored_prices: dict[str, int] = {}
        for opt in request["options"]:
            if opt["kind"] == "same_day":
                continue
            base_dl = shift_business_days(opt["deadline"], extra_days)
            dl = window_from_note(
                request["note"],
                {"from": leg0["delivery"]["window"]["from"], "to": max(leg0["delivery"]["window"]["from"], base_dl)},
                "delivery", v2=True, arrived_at=request["arrivedAt"], private_address=leg0["delivery"]["privateAddress"],
            )["to"]
            if dl - self.now - self.geo.minutes(leg0["pickup"]["placeId"], leg0["delivery"]["placeId"]) < 240:
                continue
            sponsored_prices[opt["kind"]] = max(100, int(max(opt["listPriceCents"] * mult, min_price) + 0.5))

        if not sponsored_prices:
            return {}, "decline"
        self.used_sponsors.add(sponsor)
        self.sponsored_req_to_hub[request["id"]] = sponsor
        self.stats["sunday_thin_quoted"] += 1
        return sponsored_prices, "quote"

    def handle(self, event: DeskEvent) -> None:
        if not self.p.sunday_tours:
            super(TasRoutesDesk, self).handle(event)
            return
        kind = event["kind"]
        if kind == "order_lost":
            hub_oid = self.sponsored_req_to_hub.pop(event["requestId"], None)
            if hub_oid:
                self.used_sponsors.discard(hub_oid)
        elif kind == "order_cancelled":
            self.staged_orders.pop(event["orderId"], None)
            self.used_sponsors.discard(event["orderId"])
        super().handle(event)

    def win(self, order: Order) -> None:
        if not self.p.sunday_tours:
            super(TasRoutesDesk, self).win(order)
            return
        oid = order["id"]
        if oid in self.sponsored_req_to_hub:
            hub_oid = self.sponsored_req_to_hub.pop(oid)
            self.used_sponsors.discard(hub_oid)
            self.sunday_quote_wins_day[self.now // DAY] += 1
            self.stats["sunday_thin_won"] += 1

        if oid not in self.requests or oid in self.orders:
            return
        self.orders[oid] = order
        if self.p.urgent_hygiene and self.cannot_be_on_time(order):
            self.lost.add(oid)
        self.stats["won"] += 1
        pickup = order["legs"][0]["pickup"]["placeId"]
        if self.supply.get(pickup, 0) < self.p.min_supply:
            self.stats["won_ring"] += 1
        if self.gate_supply.get(pickup, 0) < self.p.min_supply:
            self.stats["won_ext_ring"] += 1
        self.stats[f"won_{order['option']}"] += 1

        if len(order["legs"]) == 1 and not (self.requests[oid].get("note") and parse_note_v2(self.requests[oid]["note"], self.requests[oid]["arrivedAt"]).unsure):
            if self._try_bundle_with_pool(oid):
                return
            if (
                self.p.sunday_stage_min > 0
                and self._is_high_return_corridor(order)
                and order["lastPickupAt"] - self.now >= self.p.sunday_stage_min_slack
            ):
                self.staged_orders[oid] = self.now
                self.stats["sunday_staged"] += 1
                return

        super(TasRoutesDesk, self).post(order, undelivered(order))

    def tick(self) -> None:
        if not self.p.sunday_tours:
            super(TasRoutesDesk, self).tick()
            return
        for oid, st_at in list(self.staged_orders.items()):
            o = self.orders.get(oid)
            if o is None or not undelivered(o):
                self.staged_orders.pop(oid, None)
                self.used_sponsors.discard(oid)
                continue
            dt = daytime_minutes_between(st_at, self.now, self.p.day_start, self.p.day_end)
            if oid in self.urgent or o["lastPickupAt"] - self.now <= self.p.tour_hold_guard_min or dt >= self.p.sunday_stage_min:
                self.staged_orders.pop(oid, None)
                self.used_sponsors.discard(oid)
                if not self._try_bundle_with_pool(oid):
                    self.stats["sunday_stage_released_solo"] += 1
                    super(TasRoutesDesk, self).post(o, undelivered(o))
        super().tick()

    def rejoin(self, snapshot: DeskSnapshot, history: list[DeskEvent]) -> None:
        super().rejoin(snapshot, history)
        self.staged_orders.clear()
