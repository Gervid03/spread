"""The baseline dispatcher ("desk").

The mechanics (rejoin after a restart, reposting after expiry or a failed visit, changes of plan,
cancellations, trade-in splitting) are the kit starter's, which handle the rules correctly. The
economics are ours:

* **Selection.** Decline (quote far above list: a losing quote costs nothing, no quote costs
  goodwill) when few drivers live near the pickup, when the deadline leaves too little slack, when
  the expected fee eats the margin, or when too many unstaffed orders already wait near the pickup.
* **Pricing.** Each option at its list price times a multiplier. The multiplier starts from a prior
  for the level and tracks a target win rate online, globally and per dealer (which also picks up
  level-8 dealer trust and the competitor's per-dealer reaction). A long losing streak freezes the
  downward move until the next day, so the level-8 price war is sat out instead of chased.
* **Fees.** A schedule that rises over daytime half-hours from `fee_open` to `fee_warn` times the
  typical fee, reached at the deadline warning; nothing rises at night, when nobody reads the app.
  At the warning: a steep schedule plus direct offers to drivers near the pickup, preferring drivers
  who recently viewed one of our gigs (they are working today).

Every number is a field of `Params`, so most ideas are a parameter change, and a new mechanism is a
new field that defaults to the old behaviour. Subclass `Desk` (and `Params`) for bigger changes.
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass, fields
from statistics import median
from typing import Any, NamedTuple, Optional

from spread.client import World
from spread.types import (
    Action, ActionResult, Audience, DeskEvent, DeskSnapshot, DriverPosition, DriverProfile, FeeStep, Gig, Leg, Order,
    PostAction, PriceRequest, StopPlace, StopRef, TimeWindow,
)

from .geo import Geo
from .notes import note_flags, parse_note_v2, shift_business_days, window_from_note

HOUR, DAY = 60, 24 * 60


@dataclass
class PosEntry:
    """Tracked position and finish time for one booked/completed gig of ours."""
    gig_id: str
    driver_id: str
    home_place: str
    finish_place: str
    pickup_at: int
    finish_at: int
    drive_min: int
    started: bool = False
    picked_up: bool = False
    delivered: bool = False


@dataclass
class Params:
    # --- pricing: option list price x multiplier, learned online -------------------------------------
    price_mult_l8: float = 1.35       # prior at level 8 (competitor's world level is 1.26-1.54 x list)
    price_mult_l7: float = 1.22       # prior at level 7 (1.12-1.38 x list)
    price_mult_low: float = 1.00      # prior at levels 4-6
    price_mult_min: float = 1.05
    price_mult_max: float = 1.80
    price_lr: float = 0.05            # log-step of the global multiplier per quote outcome (v2: was 0.02)
    price_target_win: float = 0.35    # the win rate that the multiplier tracks (dev sweep 13.11: 0.35 > 0.45 > 0.55 on safety)
    dealer_lr: float = 0.02           # log-step of the per-dealer factor
    dealer_adj_min: float = 0.85
    dealer_adj_max: float = 1.30
    loss_streak_freeze: int = 12      # this many losses in a row stop downward moves until the next day
    same_day_markup: float = 0.05     # extra on same_day prices (tight deadline, more risk)
    # --- selection: when to decline -----------------------------------------------------------------
    supply_radius_km: float = 30.0    # the app notifies drivers whose home is this close to the pickup
    gate_radius_km: float = 55.0      # radius of the supply count the decline gate uses (v1; 0 = supply_radius_km, as v0)
    far_options: str = "slow"         # "slow": quote next_day and within_3_days only for ring pickups (v1; v0 = "all")
    min_supply: int = 30              # decline below this many drivers near the pickup (6 missed 90% on 3/5 worlds; 20 on 1/32)
    expected_fee_mult: float = 1.25   # expected fee as a multiple of the typical fee
    min_margin_frac: float = 0.08     # price is raised to keep (price - expected fee) / price at least this
    min_slack_min: int = 180          # an option needs deadline - max(now, ready) - drive minutes >= this (v2: was 120)
    slack_per_drive: float = 0.5      # an option needs slack of at least min_slack_min + slack_per_drive * drive (v1; v0 = 0)
    long_drive_min: int = 300         # if drive > this (and > 0), quote only options with deadline on a later day than ready (v1; v0 = 0)
    max_next_day_drive_min: int = 0   # if > 0 and drive > this, drop options with deadline <= ready day + 1
    thin_long_next_day_supply: int = 0  # if > 0, non-ring pickup with supply < this and drive > long_drive_min drops next_day
    fri_same_day_max_drive: int = 0   # if > 0, on Friday (ready // DAY >= 4), drop same_day with drive >= this
    ring_to_hub_same_day_min: int = 0  # if > 0, allow ring same_day into dense hub (supply >= 200) when drive <= this
    same_day_min_supply: int = 100    # quote same_day only where at least this many drivers live within supply_radius_km (v1; v0 = 0)
    backlog_ratio: float = 0.06       # unstaffed orders near a pickup may be at most max(backlog_min, ratio * supply)
    backlog_min: int = 2
    backlog_multiday_weight: float = 1.0  # weight in backlog_near for unurgent orders due on a future day
    backlog_in_flight_weight: float = 0.0  # weight in backlog_near for open unanswered non-declined quotes
    decline_mult: float = 4.0         # a decline quotes this times the list price
    ext_ring_radius_km: float = 70.0  # extended ring radius for slow short/medium-drive orders
    ext_ring_min_supply: int = 0      # 0 = off; min drivers within ext_ring_radius_km to admit slow orders
    ext_ring_max_drive_min: int = 240 # max drive minutes for orders admitted via ext_ring_min_supply
    return_hub_min_supply: int = 0    # 0 = off; min 30km supply at delivery hub to admit thin-to-hub return orders
    return_hub_max_drive_min: int = 200  # max drive minutes for thin-to-capital return orders
    ext_ring_no_learn: bool = False   # if True, lost ext_ring/return_hub quotes do not step mult/dealer_adj down
    ext_ring_neutral_learn: bool = False  # if True, both won and lost ext_ring/return_hub quotes skip learn()
    return_hub_discount: float = 0.0  # discount on option_mult when admitted via pass_return_hub (and not pass_ext_ring)
    # --- on-time guard: tighten intake when the projected on-time share falls -----------------------
    guard_target: float = 0.0         # 0 = off; else the projected on-time share to defend (e.g. 0.95)
    guard_band: float = 0.04          # tightening is full this far under the target
    guard_min_orders: int = 30        # denominator floor, so the first late car doesn't shut the desk
    guard_risk_weight: float = 0.5    # an unstaffed order past its deadline warning counts this much as late
    guard_supply_mult: float = 3.0    # at full tightening min_supply is this many times higher, backlog limit 0
    # --- fees ---------------------------------------------------------------------------------------
    fee_open: float = 0.85            # opening fee, times the typical fee (v2: was 1.00)
    fee_warn: float = 1.60            # fee reached at the deadline warning (lastPickupAt - 3 h)
    fee_step_min: int = 30            # minutes between steps of the rising schedule
    day_start: int = 7 * 60           # raises only between these minutes of the day
    day_end: int = 22 * 60
    steep_open: float = 1.80          # after the deadline warning
    steep_step: float = 0.25          # added every half hour
    steep_max: float = 3.00
    # --- direct offers after the deadline warning ---------------------------------------------------
    offers_per_warning: int = 0       # at most 3 open offers per gig, 3 per driver per day (rules) (v2: was 3; 3 of 218 offers were accepted)
    offer_mult: float = 2.20          # offer fee, times the typical fee of the cars
    offer_recent_view_min: int = 240  # drivers who viewed one of our gigs this recently go first
    # --- lead-car multi-car gig pairing -------------------------------------------------------------
    lead_car: bool = False
    lead_car_max_gap_km: float = 0.0
    lead_car_max_deliv_gap_km: float = 25.0
    lead_car_fee_mult: float = 1.00
    # --- handling rules -----------------------------------------------------------------------------
    charge_min_km: float = 200.0      # rule 3: an EV under 30% charge needs a charging stop on a route over this
    notes_v2: bool = False            # v2 note reader + delivery hours / note deadlines shorten option slack
    note_unsure: str = "quote"        # "quote" or "decline" when a note has a time the reader cannot place
    # --- trust --------------------------------------------------------------------------------------
    trust_gain: float = 0.0           # multiply dealer's quote by 1 + trust_gain * count/100
    trust_invest: float = 0.0         # discount on safe requests for top 3 dealers, Mon-Wed
    trust_guard: bool = False         # decline same_day thin town or >300min if count >= 13
    # --- route network (idea 31) --------------------------------------------------------------------
    net_offer: bool = False
    net_km: float = 30.0
    net_fanout: int = 3
    net_offer_mult: float = 0.80
    net_home_mult: float = 0.65
    net_lead_min: int = 60
    net_quote: bool = False
    net_discount: float = 0.05
    net_cap_day: int = 8
    net_seed: float = 0.0
    seed_min: int = 6
    # --- practice runner ----------------------------------------------------------------------------
    step_min: int = 10                # practice clock step in business hours (<= 14 keeps every quote in time)

    @classmethod
    def from_dict(cls, values: dict[str, Any]) -> "Params":
        known = {f.name for f in fields(cls)}
        unknown = set(values) - known
        if unknown:
            raise ValueError(f"Unknown parameter(s) for {cls.__name__}: {', '.join(sorted(unknown))}")
        return cls(**values)


class Retry(NamedTuple):
    """How to post a leg again after a failed visit."""
    pickup_from: int = 0
    manual_licence: bool = False
    plates: bool = False


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


class Desk:
    """What the desk remembers and its answer to each event. Answers wait in `outbox` until the
    runner sends them; the world applies them at the current minute."""

    Params = Params

    def __init__(self, world: World, params: Params, level: int, geo: Geo, roster: list[DriverProfile], now: int):
        self.world, self.p, self.level, self.geo, self.now = world, params, level, geo, now
        self.outbox: list[Action] = []
        self.requests: dict[str, PriceRequest] = {}
        self.orders: dict[str, Order] = {}           # won and not cancelled; order id == request id
        self.leg_gigs: dict[str, dict[int, str]] = {}  # order id -> leg -> the gig that carries it
        self.booked: set[str] = set()                # gigs a driver holds now
        self.posts: dict[str, PostAction] = {}       # gig id -> the post that made it
        self.urgent: set[str] = set()                # orders whose deadline warning has come
        self.decided: dict[str, str] = {}            # request id -> "quote" | "floor" | "decline"
        self.lost_requests: set[str] = set()         # request ids where order_lost was received
        self.mult = {8: params.price_mult_l8, 7: params.price_mult_l7}.get(level, params.price_mult_low)
        self.dealer_adj: dict[str, float] = defaultdict(lambda: 1.0)
        self.dealer_trust: dict[str, int] = defaultdict(int)
        self.dealer_request_count: dict[str, int] = defaultdict(int)
        self.loss_streak, self.streak_day = 0, -1
        self.drivers = {d["id"]: d for d in roster}
        self.supply = geo.supply(roster, params.supply_radius_km)
        r = params.gate_radius_km if params.gate_radius_km > 0 else params.supply_radius_km
        self.gate_supply = geo.supply(roster, r)
        self.ext_supply = geo.supply(roster, params.ext_ring_radius_km) if params.ext_ring_min_supply > 0 else {}
        self.last_view: dict[str, int] = {}          # driver id -> minute of their last view of our gigs
        self.offers_sent: Counter = Counter()        # (driver id, day) -> direct offers sent
        self.stats: Counter = Counter()
        self.late: set[str] = set()                  # orders known late: a late refund, a penalty, or past deadline
        self.ring_hub_same_day: set[str] = set()     # request/order ids where ring_to_hub_same_day_min allowed same_day
        self.ext_ring_reqs: set[str] = set()         # request/order ids admitted via pass_ext_ring or pass_return_hub
        # --- route network state --------------------------------------------------------------------
        self.pos_ledger: dict[str, PosEntry] = {}
        self.open_offers: dict[str, set[str]] = defaultdict(set)
        self.offered_pairs: set[tuple[str, str]] = set()
        self.net_offer_meta: dict[tuple[str, str], tuple[int, float, bool]] = {}
        self.gig_seen_net_cands: Counter = Counter()
        self.net_cand_counted: set[str] = set()
        self.net_offered_counted: set[str] = set()
        self.net_quoted_reqs: set[str] = set()
        self.net_thin_reqs: set[str] = set()
        self.net_thin_wins_day: Counter = Counter()
        self.seed_quoted_reqs: set[str] = set()
        self.pickup_req_count: Counter = Counter()
        self.driver_day_gigs: dict[tuple[str, int], set[str]] = defaultdict(set)
        self._rejoin_orders: dict[str, Order] = {}
        self._last_net_tick: int = -10 ** 9
        self._net_dirty: bool = False

    # --- events ---------------------------------------------------------------------------------------
    def handle(self, event: DeskEvent) -> None:
        kind = event["kind"]
        if kind == "price_request":
            self.quote(event["request"])
        elif kind == "order_won":
            self.learn(event["order"]["id"], won=True)
            self.win(event["order"])
        elif kind == "order_lost":
            self.lost_requests.add(event["requestId"])
            self.learn(event["requestId"], won=False)
        elif kind == "order_changed":
            self.change(event["order"])
            self._on_order_changed_pos(event["order"])
        elif kind == "order_cancelled":
            self.orders.pop(event["orderId"], None)
            if self.p.lead_car:
                self.withdraw(event["orderId"])
            self.leg_gigs.pop(event["orderId"], None)
            self._on_order_cancelled_pos(event["orderId"], event.get("gigs", []))
        elif kind == "visit_failed":
            self.stats["visit_failed"] += 1
            self.stats[f"visit_failed_{event['reason']}"] += 1
            self._on_visit_failed_pos(event["gigId"], event["orderId"], event["leg"])
            self.retry(event["orderId"], event["leg"], event["reason"])
        elif kind == "gig_expired":
            self.stats["gig_expired"] += 1
            self._finalize_gig_cands(event["gigId"])
            self.open_offers.pop(event["gigId"], None)
            self.repost(event["gigId"])
        elif kind == "deadline_close":
            self.stats["deadline_close"] += 1
            self.raise_fees(event["orderId"])
        elif kind == "gig_booked":
            self.booked.add(event["gigId"])
            self.stats["booked"] += 1
            if event["gigId"] in self.posts and len(order_ids_of(self.posts[event["gigId"]])) > 1:
                self.stats["lead_car_booked"] += 1
            self._finalize_gig_cands(event["gigId"])
            self._record_booking(event["gigId"], event["driverId"], event["at"])
            self._net_dirty = True
        elif kind in ("gig_dropped", "no_show"):
            self.booked.discard(event["gigId"])
            self.pos_ledger.pop(event["gigId"], None)
            self.stats[kind] += 1
            self._net_dirty = True
        elif kind == "driver_late":
            self._on_driver_late(event["gigId"], event["pickupAt"])
            self._net_dirty = True
        elif kind == "gig_started":
            if event["gigId"] in self.pos_ledger:
                self.pos_ledger[event["gigId"]].started = True
                self._net_dirty = True
        elif kind == "picked_up":
            self._on_picked_up(event["gigId"], event["orderId"], event["leg"], event["at"])
            self._net_dirty = True
        elif kind == "gig_viewed":
            self.last_view[event["driverId"]] = event["at"]
        elif kind == "ledger":
            line = event["line"]
            order = self.orders.get(line.get("orderId", "")) if line.get("orderId") else None
            dealer = self.requests[line["orderId"]]["dealerId"] if line.get("orderId") and line["orderId"] in self.requests else None
            is_ring = order and self.supply.get(order["legs"][0]["pickup"]["placeId"], 0) < self.p.min_supply
            is_ext_ring = order and self.gate_supply.get(order["legs"][0]["pickup"]["placeId"], 0) < self.p.min_supply
            if is_ring:
                self.stats["margin_ring_cents"] += line["cents"]
            if is_ext_ring:
                self.stats["margin_ext_ring_cents"] += line["cents"]
            attributed_oids: list[str] = []
            if line.get("orderId"):
                attributed_oids = [line["orderId"]]
            elif line.get("gigId") and line["gigId"] in self.posts:
                attributed_oids = order_ids_of(self.posts[line["gigId"]])
            if attributed_oids:
                share = line["cents"] / len(attributed_oids)
                for aoid in attributed_oids:
                    if aoid in self.net_quoted_reqs:
                        self.stats["margin_net_cents"] += share
                    if aoid in self.net_thin_reqs:
                        self.stats["margin_net_thin_cents"] += share
                    if aoid in self.seed_quoted_reqs:
                        self.stats["margin_seed_cents"] += share
            if line["kind"] in ("late_refund", "undelivered_penalty") and line["orderId"]:
                if line["orderId"] not in self.late:
                    if is_ring:
                        self.stats["late_ring"] += 1
                    if order and order["option"] == "same_day" and line["orderId"] in self.ring_hub_same_day:
                        self.stats["late_ring_hub_same_day"] += 1
                    if is_ext_ring:
                        self.stats["late_ext_ring"] += 1
                    if line["orderId"] in self.net_quoted_reqs:
                        self.stats["net_late"] += 1
                    if line["orderId"] in self.net_thin_reqs:
                        self.stats["net_late_thin"] += 1
                    if line["orderId"] in self.seed_quoted_reqs:
                        self.stats["seed_late"] += 1
                self.late.add(line["orderId"])
                if dealer:
                    self.dealer_trust[dealer] //= 2
            elif line["kind"] == "revenue" and line["orderId"]:
                if dealer and line["orderId"] not in self.late:
                    if order and self.now <= order["deadline"]:
                        self.dealer_trust[dealer] = min(25, self.dealer_trust[dealer] + 1)
        elif kind == "offer_answered":
            self.stats[f"offer_{event['answer']}"] += 1
            gid, did, ans = event["gigId"], event["driverId"], event["answer"]
            self.open_offers[gid].discard(did)
            if (gid, did) in self.net_offer_meta:
                fee_cents, ref_fee, is_hb = self.net_offer_meta[(gid, did)]
                self.stats[f"net_{ans}"] += 1
                if is_hb:
                    self.stats[f"net_{ans}_home"] += 1
                if ans == "accepted":
                    self.booked.add(gid)
                    self._finalize_gig_cands(gid)
                    if gid not in self.pos_ledger:
                        self._record_booking(gid, did, event["at"])
                    if ref_fee > 0:
                        self.stats["net_acc_fee_ratio_sum"] += fee_cents / ref_fee
                        self.stats["net_acc_fee_ratio_count"] += 1
                self._net_dirty = True
        elif kind == "delivered":
            self.leg_gigs.get(event["orderId"], {}).pop(event["leg"], None)
            if event["orderId"] in self.orders:
                self.orders[event["orderId"]]["deliveredAt"][event["leg"]] = event["at"]
            self._on_delivered(event["gigId"], event["orderId"], event["leg"], event["placeId"], event["at"])
            self._net_dirty = True

    def tick(self) -> None:
        """Called after every step (practice) or event (live)."""
        day = self.now // DAY
        if not hasattr(self, "_last_day"):
            self._last_day = day
        elif day > self._last_day:
            if self.dealer_trust:
                self.stats[f"top_dealer_trust_d{self._last_day}"] = max(self.dealer_trust.values())
            self._last_day = day
        if self.p.net_offer and self.level >= 3 and 7 * HOUR <= self.now % DAY < 21 * HOUR:
            if self._net_dirty or self.now >= self._last_net_tick + 5:
                self._run_net_offers()
                self._last_net_tick = self.now
                self._net_dirty = False

    # --- quoting --------------------------------------------------------------------------------------
    def quote(self, request: PriceRequest) -> None:
        self.requests[request["id"]] = request
        self.dealer_request_count[request["dealerId"]] += 1
        self.pickup_req_count[request["legs"][0]["pickup"]["placeId"]] += 1
        prices, decision = self.price(request)
        self.stats[f"quote_{decision}"] += 1
        if self.level <= 3:  # every quote wins at its list price: send one only for what we take
            if prices:
                first = request["options"][0]
                self.outbox.append({"type": "quote", "requestId": request["id"], "prices": {first["kind"]: first["listPriceCents"]}})
            return
        self.decided[request["id"]] = decision
        if prices:
            quoted_kind = next(iter(prices))
            quoted_option = next(o for o in request["options"] if o["kind"] == quoted_kind)
            ratio = prices[quoted_kind] / quoted_option["listPriceCents"]
            day = self.now // DAY
            self.stats[f"price_list_sum_d{day}"] += ratio
            self.stats[f"price_list_count_d{day}"] += 1
        if not prices:  # decline: a quote that loses costs nothing, a missing one costs goodwill
            first = request["options"][0]
            prices = {first["kind"]: int(first["listPriceCents"] * self.p.decline_mult)}
        self.outbox.append({"type": "quote", "requestId": request["id"], "prices": prices})

    def price(self, request: PriceRequest) -> tuple[dict[str, int], str]:
        """The prices to quote, and "quote", "floor" (a price raised to keep the margin) or "decline"."""
        p, legs = self.p, request["legs"]
        extra_days = 0
        if p.notes_v2 and request["note"]:
            pn = parse_note_v2(request["note"], request["arrivedAt"])
            if pn.has_info:
                self.stats["notes_read"] += 1
            if pn.unsure:
                self.stats["notes_unsure"] += 1
                if p.note_unsure == "decline":
                    return {}, "decline"
            if pn.ready_at is not None:
                extra_days = max(
                    (max(0, pn.ready_at // DAY - leg["pickup"]["window"]["from"] // DAY) for leg in legs if not leg["pickup"]["privateAddress"]),
                    default=0,
                )
        pickup = legs[0]["pickup"]["placeId"]
        supply = self.supply.get(pickup, 0)
        gate_supply = self.gate_supply.get(pickup, 0)
        tight = self.tightening()
        gate_min = p.min_supply * (1 + (p.guard_supply_mult - 1) * tight)
        drive = sum(self.geo.minutes(leg["pickup"]["placeId"], leg["delivery"]["placeId"]) for leg in legs)
        if len(legs) == 2:
            drive += self.geo.minutes(legs[0]["delivery"]["placeId"], legs[1]["pickup"]["placeId"])
        ready = max(
            [self.now]
            + [
                window_from_note(
                    request["note"],
                    leg["pickup"]["window"],
                    "pickup",
                    v2=p.notes_v2,
                    arrived_at=request["arrivedAt"],
                    private_address=leg["pickup"]["privateAddress"],
                )["from"]
                for leg in legs
            ]
        )
        net_opts: set[str] = self._request_network_options(request, ready, drive, extra_days) if p.net_quote else set()
        pass_ext_ring = False
        pass_return_hub = False
        pass_net_thin = False
        if gate_supply < gate_min:
            pass_ext_ring = (
                p.ext_ring_min_supply > 0
                and self.ext_supply.get(pickup, 0) >= p.ext_ring_min_supply
                and drive <= p.ext_ring_max_drive_min
            )
            pass_return_hub = (
                p.return_hub_min_supply > 0
                and self.supply.get(legs[-1]["delivery"]["placeId"], 0) >= p.return_hub_min_supply
                and drive <= p.return_hub_max_drive_min
            )
            if not (pass_ext_ring or pass_return_hub):
                slow_net_opts = {k for k in net_opts if k != "same_day"}
                if p.net_quote and slow_net_opts and drive <= 300 and self.net_thin_wins_day[self.now // DAY] < p.net_cap_day:
                    pass_net_thin = True
                else:
                    return {}, "decline"
            if self.backlog_near(pickup) + 1e-9 >= p.backlog_min:
                self.stats["declined_backlog"] += 1
                if p.backlog_in_flight_weight > 0 and self.backlog_near(pickup, include_in_flight=False) + 1e-9 < p.backlog_min:
                    self.stats["in_flight_blocked"] += 1
                return {}, "decline"
        else:
            backlog_cap = max(p.backlog_min, p.backlog_ratio * gate_supply) * (1 - tight)
            if self.backlog_near(pickup) + 1e-9 >= backlog_cap:
                self.stats["declined_backlog"] += 1
                if p.backlog_in_flight_weight > 0 and self.backlog_near(pickup, include_in_flight=False) + 1e-9 < backlog_cap:
                    self.stats["in_flight_blocked"] += 1
                return {}, "decline"
        is_ring = supply < gate_min

        if p.trust_guard and self.dealer_trust[request["dealerId"]] >= 13:
            has_same_day = any(o["kind"] == "same_day" for o in request["options"])
            if (has_same_day and supply < p.min_supply) or drive > 300:
                self.stats["dropped_trust_guard"] += 1
                return {}, "decline"

        is_on_net_pass = bool(p.net_quote and p.net_discount > 0 and supply < 100 and net_opts and not pass_net_thin)
        last_deliv = legs[-1]["delivery"]["placeId"]
        is_seed = bool(
            p.net_seed > 0
            and self.now >= 12 * HOUR
            and drive <= 220
            and supply >= 100
            and self.supply.get(last_deliv, 0) < 100
            and any(self.pickup_req_count[t] >= p.seed_min for t in self.geo.within(last_deliv, 30.0))
        )

        fee = request["referenceFeeCents"] * p.expected_fee_mult
        mult = self.mult * self.dealer_adj[request["dealerId"]]
        if p.trust_gain > 0:
            count = self.dealer_trust[request["dealerId"]]
            mult *= (1 + p.trust_gain * count / 100.0)

        is_invest = False
        if p.trust_invest > 0 and (self.now // DAY) <= 2 and self.dealer_trust[request["dealerId"]] < 25 and supply >= 100 and not request.get("note"):
            top3 = sorted(self.dealer_request_count.keys(), key=lambda d: self.dealer_request_count[d], reverse=True)[:3]
            is_invest = request["dealerId"] in top3

        prices: dict[str, int] = {}
        floored = False
        for option in request["options"]:
            ring_hub_sd = False
            if (pass_ext_ring or pass_return_hub or pass_net_thin) and option["kind"] == "same_day":
                continue
            if pass_net_thin and option["kind"] not in net_opts:
                continue
            if is_ring and p.far_options == "slow" and option["kind"] == "same_day":
                if p.ring_to_hub_same_day_min > 0 and self.supply.get(legs[-1]["delivery"]["placeId"], 0) >= 200 and drive <= p.ring_to_hub_same_day_min:
                    ring_hub_sd = True
                else:
                    continue
            deadline = option["deadline"]
            if p.notes_v2:
                base_dl = shift_business_days(deadline, extra_days)
                deadline = min(
                    window_from_note(
                        request["note"],
                        {"from": leg["delivery"]["window"]["from"], "to": max(leg["delivery"]["window"]["from"], base_dl)},
                        "delivery",
                        v2=True,
                        arrived_at=request["arrivedAt"],
                        private_address=leg["delivery"]["privateAddress"],
                    )["to"]
                    for leg in legs
                )
            if p.max_next_day_drive_min > 0 and drive > p.max_next_day_drive_min:
                if deadline // DAY <= ready // DAY + 1:
                    self.stats["dropped_next_day_long"] += 1
                    continue
            if p.thin_long_next_day_supply > 0 and not is_ring and supply < p.thin_long_next_day_supply and drive > p.long_drive_min:
                if deadline // DAY <= ready // DAY + 1:
                    self.stats["dropped_thin_long_next_day"] += 1
                    continue
            if p.fri_same_day_max_drive > 0 and ready // DAY >= 4 and option["kind"] == "same_day" and drive >= p.fri_same_day_max_drive:
                self.stats["dropped_fri_same_day"] += 1
                continue
            if p.long_drive_min > 0 and drive > p.long_drive_min:
                if deadline // DAY <= ready // DAY:
                    self.stats["dropped_long_drive"] += 1
                    continue
            if option["kind"] == "same_day" and p.same_day_min_supply > 0 and supply < p.same_day_min_supply and not ring_hub_sd:
                self.stats["dropped_same_day_supply"] += 1
                continue
            slack = deadline - ready - drive
            if slack < p.min_slack_min + p.slack_per_drive * drive:
                self.stats["dropped_slack"] += 1
                continue
            if ring_hub_sd:
                self.stats["quoted_ring_hub_same_day"] += 1
                self.ring_hub_same_day.add(request["id"])

            option_mult = mult
            if is_on_net_pass or is_seed:
                disc = max(
                    p.trust_invest if (is_invest and slack >= 360) else 0.0,
                    p.net_discount if is_on_net_pass else 0.0,
                    p.net_seed if is_seed else 0.0,
                )
                if disc > 0:
                    option_mult *= (1.0 - disc)
            elif is_invest and slack >= 360:
                option_mult *= (1 - p.trust_invest)
            if p.return_hub_discount > 0 and pass_return_hub and not pass_ext_ring and not is_on_net_pass:
                option_mult *= (1.0 - p.return_hub_discount)

            price = option["listPriceCents"] * option_mult * (1 + p.same_day_markup if option["kind"] == "same_day" else 1)
            floor = fee / (1 - p.min_margin_frac)
            if price < floor:
                price, floored = floor, True
            prices[option["kind"]] = int(price + 0.5)
        if not prices:
            return {}, "decline"
        if pass_ext_ring or pass_return_hub:
            self.ext_ring_reqs.add(request["id"])
            self.stats["quoted_ext_ring"] += 1
            if pass_return_hub:
                self.stats["quoted_return_hub"] += 1
        if is_on_net_pass or pass_net_thin:
            self.net_quoted_reqs.add(request["id"])
            self.stats["net_quoted"] += 1
            if pass_net_thin:
                self.net_thin_reqs.add(request["id"])
                self.stats["net_quoted_thin"] += 1
        if is_seed:
            self.seed_quoted_reqs.add(request["id"])
            self.stats["seed_quoted"] += 1
        return prices, "floor" if floored else "quote"

    def learn(self, request_id: str, won: bool) -> None:
        """Moves the multiplier towards the price that wins `price_target_win` of the normal quotes."""
        if self.decided.get(request_id) != "quote":
            return
        if request_id in self.net_quoted_reqs or request_id in self.seed_quoted_reqs:
            self.stats["net_skipped_learn"] += 1
            return
        if self.p.ext_ring_neutral_learn and request_id in self.ext_ring_reqs:
            self.stats["ext_ring_skipped_learn"] += 1
            return
        if self.p.ext_ring_no_learn and not won and request_id in self.ext_ring_reqs:
            return
        p, day = self.p, self.now // DAY
        if day != self.streak_day:
            self.loss_streak, self.streak_day = 0, day
        self.loss_streak = 0 if won else self.loss_streak + 1
        step = (1 - p.price_target_win) if won else -p.price_target_win
        if not won and self.loss_streak > p.loss_streak_freeze:
            return  # a price war or an outage elsewhere: sit it out rather than chase it down
        self.mult = clamp(self.mult * math.exp(p.price_lr * step), p.price_mult_min, p.price_mult_max)
        dealer = self.requests[request_id]["dealerId"]
        self.dealer_adj[dealer] = clamp(self.dealer_adj[dealer] * math.exp(p.dealer_lr * step), p.dealer_adj_min, p.dealer_adj_max)

    def backlog_near(self, place: str, include_in_flight: bool = True) -> float:
        """Won orders without a driver for every undelivered car, picked up within the radius of `place`."""
        p, radius, n = self.p, self.p.supply_radius_km, 0.0
        for order in self.orders.values():
            if self.geo.line_km(order["legs"][0]["pickup"]["placeId"], place) <= radius and not self.staffed(order):
                if p.backlog_multiday_weight != 1.0 and order["deadline"] // DAY > self.now // DAY and order["id"] not in self.urgent:
                    n += p.backlog_multiday_weight
                else:
                    n += 1.0
        if include_in_flight and p.backlog_in_flight_weight > 0:
            for req_id, req in self.requests.items():
                if (
                    req_id not in self.orders
                    and req_id not in self.lost_requests
                    and self.decided.get(req_id) in ("quote", "floor")
                    and self.now <= req["respondBy"]
                    and self.geo.line_km(req["legs"][0]["pickup"]["placeId"], place) <= radius
                ):
                    n += p.backlog_in_flight_weight
        return n

    def projected_on_time(self) -> float:
        """On-time share if every order known late stays late and each unstaffed order past its deadline
        warning is late with probability `guard_risk_weight`."""
        p, late, risk = self.p, 0, 0
        for order_id, order in self.orders.items():
            open_legs = undelivered(order)
            if order_id in self.late or (open_legs and self.now > order["deadline"]):
                late += 1
            elif open_legs and order_id in self.urgent and not self.staffed(order):
                risk += 1
        return 1 - (late + p.guard_risk_weight * risk) / max(len(self.orders), p.guard_min_orders)

    def tightening(self) -> float:
        """0 (normal intake) to 1 (only the safest requests), from how far the projection is under target."""
        p = self.p
        if p.guard_target <= 0:
            return 0.0
        return clamp((p.guard_target - self.projected_on_time()) / p.guard_band, 0.0, 1.0)

    def staffed(self, order: Order) -> bool:
        legs = undelivered(order)
        gigs = self.leg_gigs.get(order["id"], {})
        return all(gigs.get(leg) in self.booked for leg in legs)

    # --- orders and gigs (the starter's mechanics) ----------------------------------------------------
    def win(self, order: Order) -> None:
        if order["id"] in self.requests and order["id"] not in self.orders:
            self.orders[order["id"]] = order
            self.stats["won"] += 1
            pickup = order["legs"][0]["pickup"]["placeId"]
            if self.supply.get(pickup, 0) < self.p.min_supply:
                self.stats["won_ring"] += 1
            if order["option"] == "same_day" and order["id"] in self.ring_hub_same_day:
                self.stats["won_ring_hub_same_day"] += 1
            if self.gate_supply.get(pickup, 0) < self.p.min_supply:
                self.stats["won_ext_ring"] += 1
                if self.p.return_hub_min_supply > 0 and self.supply.get(order["legs"][-1]["delivery"]["placeId"], 0) >= self.p.return_hub_min_supply:
                    self.stats["won_return_hub"] += 1
            if order["id"] in self.net_quoted_reqs:
                self.stats["net_won"] += 1
                if order["id"] in self.net_thin_reqs:
                    self.stats["net_won_thin"] += 1
                    self.net_thin_wins_day[self.now // DAY] += 1
            if order["id"] in self.seed_quoted_reqs:
                self.stats["seed_won"] += 1
            self.stats[f"won_{order['option']}"] += 1
            self.post(order, undelivered(order))
            self._net_dirty = True

    def change(self, order: Order) -> None:
        if order["id"] in self.orders:
            self.orders[order["id"]] = order
            if self.withdraw(order["id"]):
                self.post(order, undelivered(order))

    def repost(self, gig_id: str) -> None:
        action = self.posts.get(gig_id)
        if action is None or not any(self.leg_gigs.get(s["orderId"], {}).get(s["leg"]) == gig_id for s in action["stops"]):
            return
        for stop in action["stops"]:
            self.leg_gigs.get(stop["orderId"], {}).pop(stop["leg"], None)
        oids = order_ids_of(action)
        if len(oids) > 1:
            if any(oid not in self.orders or oid in self.urgent or not undelivered(self.orders[oid]) for oid in oids):
                self.stats["lead_car_split"] += 1
                for oid in oids:
                    if oid in self.orders and undelivered(self.orders[oid]):
                        self.post(self.orders[oid], undelivered(self.orders[oid]), Retry(), allow_pair=False)
                return
        order = self.orders.get(action["stops"][0]["orderId"])
        if order is None:
            return
        stops = without_windows(action["stops"], float("inf"))
        self.outbox.append({**action, "stops": stops, "schedule": self.fees_for(order, pickups(action), action)})

    def raise_fees(self, order_id: str) -> None:
        order = self.orders.get(order_id)
        if order is None:
            return
        self.urgent.add(order_id)
        self.send_post_of(order_id)
        for gig_id in list(self.gigs_of(order_id)):
            if gig_id not in self.booked and gig_id in self.posts and len(order_ids_of(self.posts[gig_id])) > 1:
                self.stats["lead_car_split"] += 1
                self._finalize_gig_cands(gig_id)
                self.open_offers.pop(gig_id, None)
                self.outbox.append({"type": "withdraw", "gigId": gig_id})
                oids = order_ids_of(self.posts[gig_id])
                for stop in self.posts[gig_id]["stops"]:
                    self.leg_gigs.get(stop["orderId"], {}).pop(stop["leg"], None)
                for oid in oids:
                    if oid in self.orders and undelivered(self.orders[oid]):
                        self.post(self.orders[oid], undelivered(self.orders[oid]), Retry(), allow_pair=False)
                self.send_post_of(order_id)
        for gig_id in self.gigs_of(order_id):
            if gig_id not in self.booked:
                self.outbox.append({"type": "reprice", "gigId": gig_id, "schedule": self.fees_for(order, pickups(self.posts[gig_id]), self.posts[gig_id])})
                self.offer(gig_id, order)

    def offer(self, gig_id: str, order: Order) -> None:
        """Direct offers to the drivers most likely to take the gig now: who viewed our gigs lately, then
        who lives closest to the first pickup. A driver may get 3 offers a day, a gig 3 open offers."""
        p, post = self.p, self.posts[gig_id]
        if p.offers_per_warning <= 0 or self.level < 3:
            return
        audience, day = post["audience"], self.now // DAY
        first = post["stops"][0]
        pickup = order["legs"][first["leg"]]["pickup"]["placeId"]
        candidates = []
        for d in self.drivers.values():
            if audience["experienced"] and not (d["rating"] >= 4.8 and d["completedGigs"] >= 50):
                continue
            if audience["manualLicence"] and d["licence"] != "manual":
                continue
            if self.offers_sent[(d["id"], day)] >= 3:
                continue
            recent = self.now - self.last_view.get(d["id"], -10 ** 9) <= p.offer_recent_view_min
            candidates.append((0 if recent else 1, self.geo.minutes(d["homePlaceId"], pickup), d["id"]))
        candidates.sort()
        fee = int(self.requests[order["id"]]["referenceFeeCents"] * pickups(post) / len(order["legs"]) * p.offer_mult + 0.5)
        for _, _, driver_id in candidates[: min(3, p.offers_per_warning)]:
            self.outbox.append({"type": "offer", "gigId": gig_id, "driverId": driver_id, "feeCents": fee})
            self.offers_sent[(driver_id, day)] += 1
            self.stats["offers"] += 1

    def fees_for(self, order: Order, cars: int, action: Optional[PostAction] = None) -> list[FeeStep]:
        if action is not None:
            oids = order_ids_of(action)
            if len(oids) > 1:
                base = sum(self.requests[oid]["referenceFeeCents"] for oid in oids if oid in self.requests) * self.p.lead_car_fee_mult
                if self.level == 1:
                    return [{"at": self.now, "feeCents": max(1, int(base * self.p.fee_open + 0.5))}]
                if any(oid in self.urgent for oid in oids):
                    return self.steep(base)
                until = min((self.orders[oid]["lastPickupAt"] for oid in oids if oid in self.orders), default=order["lastPickupAt"]) - 3 * HOUR
                return self.rising(base, until)
        base = self.requests[order["id"]]["referenceFeeCents"] * cars / len(order["legs"])
        if self.level == 1:
            return [{"at": self.now, "feeCents": max(1, int(base * self.p.fee_open + 0.5))}]
        if order["id"] in self.urgent:
            return self.steep(base)
        return self.rising(base, order["lastPickupAt"] - 3 * HOUR)

    def rising(self, base: float, until: int) -> list[FeeStep]:
        """From `fee_open` now to `fee_warn` at `until`, in daytime steps only, at most 48 steps."""
        p = self.p
        times = [self.now]
        t = (self.now // p.fee_step_min + 1) * p.fee_step_min
        while t <= until:
            if p.day_start <= t % DAY < p.day_end:
                times.append(t)
            t += p.fee_step_min
        if len(times) > 48:  # keep the first and the last, thin the middle evenly
            k = len(times) - 1
            times = [times[round(i * k / 47)] for i in range(48)]
        n = len(times)
        return [{"at": at, "feeCents": max(1, int(base * (p.fee_open + (p.fee_warn - p.fee_open) * (i / (n - 1) if n > 1 else 0)) + 0.5))}
                for i, at in enumerate(times)]

    def steep(self, base: float) -> list[FeeStep]:
        p = self.p
        steps, k = [], 0
        while True:
            mult = p.steep_open + k * p.steep_step
            if mult > p.steep_max + 1e-9 or k >= 48:
                break
            steps.append({"at": self.now + k * 30, "feeCents": max(1, int(base * mult + 0.5))})
            k += 1
            if p.steep_step <= 0:
                break
        return steps

    def retry(self, order_id: str, leg: int, reason: str) -> None:
        if order_id in self.orders:
            order = self.orders[order_id]
            self.leg_gigs.get(order_id, {}).pop(leg, None)
            car_not_there = reason in ("not_ready", "closed")
            pickup_from = retry_from(order, self.requests[order_id], leg, self.now) if car_not_there else 0
            self.post(order, [leg], Retry(pickup_from, manual_licence=reason == "licence", plates=reason == "no_plates"))

    def try_pair_lead_car(self, order: Order, legs: list[int], retry: Retry) -> bool:
        p = self.p
        if not p.lead_car or self.level < 3:
            return False
        if len(legs) != 1 or len(order["legs"]) != 1 or retry != Retry():
            return False
        if order["option"] == "same_day" or order["id"] in self.urgent:
            return False
        req = self.requests.get(order["id"])
        if req is None or req.get("note"):
            return False
        stops_b = without_windows(
            stops_for(order, legs, req["note"], retry, self.geo, p.charge_min_km, p.notes_v2, req["arrivedAt"]),
            self.now,
        )
        if any(s.get("withCharging") for s in stops_b):
            return False
        pb = order["legs"][0]["pickup"]["placeId"]
        db = order["legs"][0]["delivery"]["placeId"]
        drive_b = self.geo.minutes(pb, db)
        # Flush any matching single-car slow post still sitting in outbox from the current step (e.g. same batch)
        for a in self.outbox:
            if a["type"] == "post" and len(a["stops"]) == 2:
                oid = a["stops"][0]["orderId"]
                other = self.orders.get(oid)
                if (
                    other is not None
                    and oid != order["id"]
                    and other["option"] != "same_day"
                    and oid not in self.urgent
                    and other["deadline"] // DAY == order["deadline"] // DAY
                    and not self.requests.get(oid, {}).get("note")
                ):
                    pa = other["legs"][0]["pickup"]["placeId"]
                    da = other["legs"][0]["delivery"]["placeId"]
                    if self.geo.line_km(pa, pb) <= p.lead_car_max_gap_km and self.geo.line_km(da, db) <= p.lead_car_max_deliv_gap_km:
                        self.send()
                        break

        best: Optional[tuple[float, int, str, Order, PostAction]] = None
        for gig_id, action in list(self.posts.items()):
            if gig_id in self.booked or len(action["stops"]) != 2:
                continue
            other_id = action["stops"][0]["orderId"]
            if other_id == order["id"] or other_id in self.urgent:
                continue
            if self.leg_gigs.get(other_id, {}).get(action["stops"][0]["leg"]) != gig_id:
                continue
            other_order = self.orders.get(other_id)
            if other_order is None or len(other_order["legs"]) != 1 or undelivered(other_order) != [0]:
                continue
            if other_order["option"] == "same_day" or other_order["deadline"] // DAY != order["deadline"] // DAY:
                continue
            other_req = self.requests.get(other_id)
            if other_req is None or other_req.get("note"):
                continue
            if any(s.get("withCharging") for s in action["stops"]):
                continue
            pa = other_order["legs"][0]["pickup"]["placeId"]
            da = other_order["legs"][0]["delivery"]["placeId"]
            gap_p = self.geo.line_km(pa, pb)
            gap_d = self.geo.line_km(da, db)
            if gap_p > p.lead_car_max_gap_km or gap_d > p.lead_car_max_deliv_gap_km:
                continue
            drive_a = self.geo.minutes(pa, da)
            deadhead_da_to_pb = self.geo.minutes(da, pb)
            total_min = drive_a + deadhead_da_to_pb + drive_b + 4 * 15
            if total_min > 540:
                continue
            start_at = max(
                self.now,
                other_order["legs"][0]["pickup"]["window"]["from"],
                order["legs"][0]["pickup"]["window"]["from"],
            )
            if start_at + total_min + 240 > min(order["deadline"], other_order["deadline"]):
                continue
            score = (gap_p + gap_d, total_min)
            if best is None or score < (best[0], best[1]):
                best = (gap_p + gap_d, total_min, gig_id, other_order, action)

        if best is None:
            return False
        _, _, gig_id, other_order, action = best
        self.leg_gigs.get(other_order["id"], {}).pop(0, None)
        self._finalize_gig_cands(gig_id)
        self.open_offers.pop(gig_id, None)
        self.outbox.append({"type": "withdraw", "gigId": gig_id})
        stops_a = without_windows(action["stops"], self.now)
        stops = stops_a + stops_b
        audience: Audience = {
            "experienced": action["audience"]["experienced"] or any(leg["car"]["premium"] for leg in order["legs"]),
            "manualLicence": action["audience"]["manualLicence"],
        }
        post_action: PostAction = {"type": "post", "stops": stops, "audience": audience, "schedule": []}
        post_action["schedule"] = self.fees_for(other_order, 2, post_action)
        self.outbox.append(post_action)
        self.stats["posts"] += 1
        self.send()
        if not self.gigs_of(order["id"]):
            self.post(other_order, undelivered(other_order), Retry(), allow_pair=False)
            return False
        self.stats["lead_car_paired"] += 1
        return True

    def post(self, order: Order, legs: list[int], retry: Retry = Retry(), allow_pair: bool = True) -> None:
        if allow_pair and self.p.lead_car and self.try_pair_lead_car(order, legs, retry):
            return
        req = self.requests[order["id"]]
        note = req["note"]
        flags = note_flags(note, v2=self.p.notes_v2)
        audience: Audience = {
            "experienced": any(leg["car"]["premium"] for leg in order["legs"]),  # rule 1: €150 fine otherwise
            "manualLicence": retry.manual_licence or flags.manual,
        }
        retry = retry._replace(plates=retry.plates or flags.plates)
        stops = without_windows(
            stops_for(order, legs, note, retry, self.geo, self.p.charge_min_km, self.p.notes_v2, req["arrivedAt"]),
            self.now,
        )
        self.outbox.append({"type": "post", "stops": stops, "audience": audience, "schedule": self.fees_for(order, len(legs))})
        self.stats["posts"] += 1
        if len(legs) == 1:
            return
        self.send()  # a trade-in over the 12-hour limit for one gig goes as one gig per car
        if not self.gigs_of(order["id"]):
            for leg in legs:
                self.post(order, [leg], retry, allow_pair=False)

    def gigs_of(self, order_id: str) -> list[str]:
        return list(dict.fromkeys(self.leg_gigs.get(order_id, {}).values()))

    def carry(self, action: PostAction, gig_id: str) -> None:
        for stop in action["stops"]:
            self.leg_gigs.setdefault(stop["orderId"], {})[stop["leg"]] = gig_id
        self.posts[gig_id] = action

    def withdraw(self, order_id: str) -> bool:
        self.send_post_of(order_id)
        gigs = self.gigs_of(order_id)
        if any(gig_id in self.booked for gig_id in gigs):
            return False
        self.leg_gigs.pop(order_id, None)
        for gig_id in gigs:
            self._finalize_gig_cands(gig_id)
            self.open_offers.pop(gig_id, None)
        self.outbox += [{"type": "withdraw", "gigId": gig_id} for gig_id in gigs]
        for gig_id in gigs:
            if gig_id in self.posts and len(order_ids_of(self.posts[gig_id])) > 1:
                self.stats["lead_car_split"] += 1
                for oid in order_ids_of(self.posts[gig_id]):
                    if oid != order_id and oid in self.orders:
                        self.leg_gigs.pop(oid, None)
                        if undelivered(self.orders[oid]):
                            self.post(self.orders[oid], undelivered(self.orders[oid]), Retry(), allow_pair=False)
        return True

    def send_post_of(self, order_id: str) -> None:
        if any(a["type"] == "post" and any(s["orderId"] == order_id for s in a["stops"]) for a in self.outbox):
            self.send()

    def send(self) -> None:
        """Sends the outbox now (live mode always; practice only when the desk needs a gig id at once)."""
        actions, self.outbox = self.outbox, []
        if actions:
            self.read_results(actions, self.world.act(actions))

    def take_outbox(self) -> list[Action]:
        actions, self.outbox = self.outbox, []
        return actions

    def read_results(self, actions: list[Action], results: list[ActionResult]) -> None:
        for action, result in zip(actions, results):
            if result["ok"] is True:
                if action["type"] == "post":
                    self.carry(action, result["id"])
                    self._net_dirty = True
            else:
                self.stats[f"refused_{action['type']}"] += 1
                if action["type"] == "offer":
                    self.open_offers[action["gigId"]].discard(action["driverId"])

    # --- route network & position ledger (idea 31) ----------------------------------------------------
    def leg_of(self, order_id: str, leg: int) -> Optional[Leg]:
        for src in (self.orders, self._rejoin_orders, self.requests):
            obj = src.get(order_id)
            if obj is not None and 0 <= leg < len(obj["legs"]):
                return obj["legs"][leg]
        return None

    def effective_finish_at(self, entry: PosEntry) -> int:
        if entry.delivered or entry.picked_up or self.now <= entry.pickup_at:
            return entry.finish_at
        return max(entry.finish_at, self.now + entry.drive_min)

    def _plan_stops(
        self,
        stops: list[StopRef],
        start_from: int,
        late_pickup_at: Optional[int] = None,
        driver_id: Optional[str] = None,
        exclude_gig: Optional[str] = None,
    ) -> Optional[tuple[str, str, int, int, int]]:
        if not stops:
            return None
        s0 = stops[0]
        leg0 = self.leg_of(s0["orderId"], s0["leg"])
        if leg0 is None:
            return None
        first_place = leg0["pickup"]["placeId"] if s0["kind"] == "pickup" else leg0["delivery"]["placeId"]
        if late_pickup_at is not None:
            pickup_at = late_pickup_at
        else:
            win_from = s0["window"]["from"] if "window" in s0 else leg0["pickup"]["window"]["from"]
            pickup_at = max(start_from, win_from)
            if driver_id is not None:
                for prev in self.pos_ledger.values():
                    if prev.driver_id == driver_id and prev.gig_id != exclude_gig and prev.pickup_at <= pickup_at:
                        p_fin = self.effective_finish_at(prev)
                        if p_fin // DAY == pickup_at // DAY:
                            arr = p_fin + self.geo.minutes(prev.finish_place, first_place) + (30 if s0.get("withPlates") else 0)
                            if arr > pickup_at:
                                pickup_at = arr
            if s0["kind"] == "pickup":
                pickup_at = next_open_minute(pickup_at, leg0["pickup"])

        t = pickup_at
        dur = 0
        prev_place: Optional[str] = None
        for idx, st in enumerate(stops):
            lg = self.leg_of(st["orderId"], st["leg"])
            if lg is None:
                return None
            place = lg["pickup"]["placeId"] if st["kind"] == "pickup" else lg["delivery"]["placeId"]
            if prev_place is not None:
                rd = self.geo.minutes(prev_place, place)
                t += rd
                dur += rd
            if st["kind"] == "pickup":
                if idx > 0:
                    wf = st["window"]["from"] if "window" in st else lg["pickup"]["window"]["from"]
                    if wf > t:
                        dur += wf - t
                        t = wf
                    if st.get("withPlates"):
                        t += 30
                        dur += 30
                elif late_pickup_at is None and st.get("withPlates"):
                    t += 30
                    dur += 30
                if st.get("withCharging"):
                    t += 40
                    dur += 40
            prev_place = place
        assert prev_place is not None
        return first_place, prev_place, pickup_at, t, dur

    def _rem_duration_from(self, stops: list[StopRef], idx: int, include_current_charging: bool) -> int:
        lg_cur = self.leg_of(stops[idx]["orderId"], stops[idx]["leg"])
        if lg_cur is None:
            return 0
        prev_place = lg_cur["pickup"]["placeId"] if stops[idx]["kind"] == "pickup" else lg_cur["delivery"]["placeId"]
        dur = 40 if (include_current_charging and stops[idx]["kind"] == "pickup" and stops[idx].get("withCharging")) else 0
        for st in stops[idx + 1:]:
            lg = self.leg_of(st["orderId"], st["leg"])
            if lg is None:
                continue
            pl = lg["pickup"]["placeId"] if st["kind"] == "pickup" else lg["delivery"]["placeId"]
            dur += self.geo.minutes(prev_place, pl)
            if st["kind"] == "pickup":
                if st.get("withPlates"):
                    dur += 30
                if st.get("withCharging"):
                    dur += 40
            prev_place = pl
        return dur

    def _record_booking(self, gig_id: str, driver_id: str, booked_at: int, stops_override: Optional[list[StopRef]] = None) -> None:
        stops = stops_override if stops_override is not None else self.posts.get(gig_id, {}).get("stops")
        if not stops:
            return
        d = self.drivers.get(driver_id)
        home = d["homePlaceId"] if d else ""
        planned = self._plan_stops(stops, booked_at, driver_id=driver_id, exclude_gig=gig_id)
        if planned is None:
            return
        _, finish_place, pickup_at, finish_at, drive_min = planned
        self.pos_ledger[gig_id] = PosEntry(
            gig_id=gig_id,
            driver_id=driver_id,
            home_place=home,
            finish_place=finish_place,
            pickup_at=pickup_at,
            finish_at=finish_at,
            drive_min=drive_min,
        )

    def _on_driver_late(self, gig_id: str, pickup_at: int, stops_override: Optional[list[StopRef]] = None) -> None:
        entry = self.pos_ledger.get(gig_id)
        stops = stops_override if stops_override is not None else self.posts.get(gig_id, {}).get("stops")
        if entry is None or not stops or entry.delivered:
            return
        planned = self._plan_stops(stops, pickup_at, late_pickup_at=pickup_at, exclude_gig=gig_id)
        if planned is not None:
            _, entry.finish_place, entry.pickup_at, entry.finish_at, entry.drive_min = planned

    def _on_picked_up(self, gig_id: str, order_id: str, leg: int, at: int, stops_override: Optional[list[StopRef]] = None) -> None:
        entry = self.pos_ledger.get(gig_id)
        stops = stops_override if stops_override is not None else self.posts.get(gig_id, {}).get("stops")
        if entry is None or not stops or entry.delivered:
            return
        entry.started = True
        if not entry.picked_up:
            entry.pickup_at = at
            entry.picked_up = True
        for idx, st in enumerate(stops):
            if st["kind"] == "pickup" and st["orderId"] == order_id and st["leg"] == leg:
                entry.finish_at = at + self._rem_duration_from(stops, idx, include_current_charging=True)
                break

    def _on_delivered(self, gig_id: str, order_id: str, leg: int, place_id: str, at: int, stops_override: Optional[list[StopRef]] = None) -> None:
        entry = self.pos_ledger.get(gig_id)
        if entry is None:
            return
        stops = stops_override if stops_override is not None else self.posts.get(gig_id, {}).get("stops")
        all_done = True
        if stops:
            for st in stops:
                if st["kind"] == "delivery":
                    oid, lg = st["orderId"], st["leg"]
                    if oid == order_id and lg == leg:
                        continue
                    ord_obj = self.orders.get(oid) or self._rejoin_orders.get(oid)
                    if ord_obj is not None and ord_obj["deliveredAt"][lg] is None:
                        all_done = False
                        break
        if all_done:
            was_delivered = entry.delivered
            entry.finish_place = place_id
            entry.finish_at = at
            entry.started = True
            entry.picked_up = True
            entry.delivered = True
            if not was_delivered:
                gset = self.driver_day_gigs[(entry.driver_id, entry.pickup_at // DAY)]
                if gig_id not in gset:
                    gset.add(gig_id)
                    if len(gset) == 2:
                        self.stats["driver_days_2plus"] += 1
        elif stops:
            for idx, st in enumerate(stops):
                if st["kind"] == "delivery" and st["orderId"] == order_id and st["leg"] == leg:
                    entry.finish_at = at + self._rem_duration_from(stops, idx, include_current_charging=False)
                    break

    def _on_order_changed_pos(self, order: Order) -> None:
        for gig_id in self.gigs_of(order["id"]):
            entry = self.pos_ledger.get(gig_id)
            stops = self.posts.get(gig_id, {}).get("stops")
            if entry is not None and stops and not entry.delivered:
                planned = self._plan_stops(stops, entry.pickup_at, late_pickup_at=entry.pickup_at if entry.picked_up else None, exclude_gig=gig_id)
                if planned is not None:
                    _, entry.finish_place, _, entry.finish_at, entry.drive_min = planned
                    self._net_dirty = True

    def _on_order_cancelled_pos(self, order_id: str, cancelled_gigs: list[Any]) -> None:
        for cg in cancelled_gigs:
            gid = cg["gigId"]
            self.open_offers.pop(gid, None)
            if cg["outcome"] in ("withdrawn", "released"):
                self._finalize_gig_cands(gid)
                self.pos_ledger.pop(gid, None)
            elif gid in self.pos_ledger:
                rem = [s for s in self.posts.get(gid, {}).get("stops", []) if s["orderId"] != order_id and s["orderId"] in self.orders]
                if not rem:
                    self.pos_ledger.pop(gid, None)
                else:
                    entry = self.pos_ledger[gid]
                    planned = self._plan_stops(rem, entry.pickup_at, late_pickup_at=entry.pickup_at if entry.picked_up else None, exclude_gig=gid)
                    if planned is not None:
                        _, entry.finish_place, _, entry.finish_at, entry.drive_min = planned
        self._net_dirty = True

    def _on_visit_failed_pos(self, gig_id: str, order_id: str, leg: int) -> None:
        entry = self.pos_ledger.get(gig_id)
        stops = self.posts.get(gig_id, {}).get("stops")
        if entry is None or not stops:
            return
        rem = [s for s in stops if not (s["orderId"] == order_id and s["leg"] == leg)]
        if not rem:
            self.pos_ledger.pop(gig_id, None)
        else:
            planned = self._plan_stops(rem, max(self.now, entry.pickup_at), exclude_gig=gig_id)
            if planned is not None:
                _, entry.finish_place, _, entry.finish_at, entry.drive_min = planned

    def sync_driver_positions(self, positions: list[DriverPosition], now: int) -> None:
        for dp in positions:
            entry = self.pos_ledger.get(dp["gigId"])
            stops = self.posts.get(dp["gigId"], {}).get("stops")
            if entry is None or entry.delivered or not stops:
                continue
            if entry.picked_up:
                entry.finish_at = max(entry.finish_at, now + self.geo.minutes(dp["placeId"], entry.finish_place))
            else:
                lg0 = self.leg_of(stops[0]["orderId"], stops[0]["leg"])
                if lg0 is not None:
                    p0 = lg0["pickup"]["placeId"]
                    entry.finish_at = max(entry.finish_at, now + self.geo.minutes(dp["placeId"], p0) + entry.drive_min)

    def _finalize_gig_cands(self, gig_id: str) -> None:
        if not self.p.net_offer or gig_id in self.net_cand_counted or gig_id not in self.posts:
            return
        self.net_cand_counted.add(gig_id)
        mx = self.gig_seen_net_cands.get(gig_id, 0)
        if mx == 0:
            self.stats["net_cands_0"] += 1
        else:
            self.stats["net_cands_3plus" if mx >= 3 else f"net_cands_{mx}"] += 1

    def _typical_fee(self, action: PostAction) -> float:
        oids = order_ids_of(action)
        if len(oids) > 1:
            return float(sum(self.requests[oid]["referenceFeeCents"] for oid in oids if oid in self.requests))
        oid = oids[0]
        order = self.orders.get(oid)
        req = self.requests.get(oid)
        if order is None or req is None:
            return 0.0
        return req["referenceFeeCents"] * pickups(action) / len(order["legs"])

    def _driver_conflict(self, entry: PosEntry, start_t: int, end_t: int) -> bool:
        e_fin = self.effective_finish_at(entry)
        for other in self.pos_ledger.values():
            if other.driver_id != entry.driver_id or other.gig_id == entry.gig_id:
                continue
            o_fin = self.effective_finish_at(other)
            if o_fin // DAY == e_fin // DAY and o_fin > e_fin and (other.started or other.picked_up or other.delivered):
                return True
            if not other.delivered:
                o_start = other.pickup_at - 30
                o_end = o_fin + 30
                if start_t <= o_end and end_t >= o_start:
                    return True
        return False

    def _eligible_net_candidates(self, action: PostAction) -> list[tuple[float, float, str, PosEntry]]:
        stops = action["stops"]
        if not stops:
            return []
        s0, s_last = stops[0], stops[-1]
        order0 = self.orders.get(s0["orderId"])
        order_last = self.orders.get(s_last["orderId"])
        if order0 is None or order_last is None:
            return []
        leg0 = order0["legs"][s0["leg"]]
        leg_last = order_last["legs"][s_last["leg"]]
        first_pickup = leg0["pickup"]["placeId"]
        last_delivery = leg_last["delivery"]["placeId"]
        base_win = s0["window"] if "window" in s0 else leg0["pickup"]["window"]
        p_from, p_to = base_win["from"], base_win["to"]
        gig_deadline = min(
            (st["window"]["to"] if "window" in st else self.orders[st["orderId"]]["deadline"])
            for st in stops
            if st["kind"] == "delivery" and st["orderId"] in self.orders
        )
        rem_dur = self._rem_duration_from(stops, 0, include_current_charging=True)
        aud = action["audience"]

        best_by_driver: dict[str, tuple[float, float, str, PosEntry]] = {}
        for entry in self.pos_ledger.values():
            if not entry.home_place:
                continue
            if entry.delivered and (entry.finish_at // DAY < self.now // DAY or self.now - entry.finish_at > 3 * HOUR):
                continue
            d = self.drivers.get(entry.driver_id)
            if d is None:
                continue
            if aud["experienced"] and not (d["rating"] >= 4.8 and d["completedGigs"] >= 50):
                continue
            if aud["manualLicence"] and d["licence"] != "manual":
                continue
            fin_km = self.geo.line_km(entry.finish_place, first_pickup)
            if fin_km > self.p.net_km or self.geo.line_km(entry.home_place, first_pickup) <= 30.0:
                continue
            fin_at = self.effective_finish_at(entry)
            arr0 = max(self.now, fin_at) + self.geo.minutes(entry.finish_place, first_pickup) + (30 if s0.get("withPlates") else 0)
            pick0 = max(arr0, p_from)
            if pick0 > p_to:
                continue
            pick0_open = next_open_minute(pick0, leg0["pickup"])
            if pick0_open > p_to or pick0_open // DAY != fin_at // DAY:
                continue
            deliv_at = pick0_open + rem_dur
            if gig_deadline - deliv_at < self.p.min_slack_min:
                continue
            if self._driver_conflict(entry, pick0_open, deliv_at):
                continue
            home_km = self.geo.line_km(entry.home_place, last_delivery)
            cand = (home_km, fin_km, entry.driver_id, entry)
            prev = best_by_driver.get(entry.driver_id)
            if prev is None or cand[:3] < prev[:3]:
                best_by_driver[entry.driver_id] = cand
        return sorted(best_by_driver.values(), key=lambda c: c[:3])

    def _post_has_ready_net_candidate(self, action: PostAction) -> bool:
        day = self.now // DAY
        for _, _, d_id, entry in self._eligible_net_candidates(action):
            if (
                (entry.started or entry.picked_up or entry.delivered)
                and self.offers_sent[(d_id, day)] < 3
                and self.now >= self.effective_finish_at(entry) - self.p.net_lead_min
            ):
                return True
        return False

    def _run_net_offers(self) -> None:
        if any(a["type"] == "post" and self._post_has_ready_net_candidate(a) for a in self.outbox):
            self.send()
        pending_withdraws = {a["gigId"] for a in self.outbox if a["type"] == "withdraw"}
        day = self.now // DAY
        for gig_id, action in list(self.posts.items()):
            if gig_id in self.booked or gig_id in pending_withdraws:
                continue
            if not any(self.leg_gigs.get(s["orderId"], {}).get(s["leg"]) == gig_id for s in action["stops"]):
                continue
            cands = self._eligible_net_candidates(action)
            if len(cands) > self.gig_seen_net_cands[gig_id]:
                self.gig_seen_net_cands[gig_id] = len(cands)
            slots = min(3, self.p.net_fanout) - len(self.open_offers[gig_id])
            if slots <= 0 or not cands:
                continue
            ready = [
                (home_km, fin_km, d_id, entry)
                for home_km, fin_km, d_id, entry in cands
                if (entry.started or entry.picked_up or entry.delivered)
                and (gig_id, d_id) not in self.offered_pairs
                and self.offers_sent[(d_id, day)] < 3
                and self.now >= self.effective_finish_at(entry) - self.p.net_lead_min
            ]
            if not ready:
                continue
            nc = len(cands)
            if gig_id not in self.net_offered_counted:
                self.net_offered_counted.add(gig_id)
                self.stats["net_offered_gigs"] += 1
                self.stats["net_offered_cands_3plus" if nc >= 3 else f"net_offered_cands_{nc}"] += 1
            if gig_id not in self.net_cand_counted:
                self.net_cand_counted.add(gig_id)
                self.stats["net_cands_3plus" if nc >= 3 else f"net_cands_{nc}"] += 1
            ref_fee = self._typical_fee(action)
            if ref_fee <= 0:
                continue
            for home_km, _, d_id, _ in ready[:slots]:
                is_home = home_km <= 30.0
                mult = self.p.net_home_mult if is_home else self.p.net_offer_mult
                fee_cents = max(1, int(ref_fee * mult + 0.5))
                self.outbox.append({"type": "offer", "gigId": gig_id, "driverId": d_id, "feeCents": fee_cents})
                self.offers_sent[(d_id, day)] += 1
                self.open_offers[gig_id].add(d_id)
                self.offered_pairs.add((gig_id, d_id))
                self.net_offer_meta[(gig_id, d_id)] = (fee_cents, ref_fee, is_home)
                self.stats["net_offers"] += 1
                if is_home:
                    self.stats["net_offers_home"] += 1

    def _request_network_options(self, request: PriceRequest, ready: int, drive: int, extra_days: int) -> set[str]:
        p, legs = self.p, request["legs"]
        pickup = legs[0]["pickup"]["placeId"]
        flags = note_flags(request["note"], v2=p.notes_v2)
        need_exp = any(leg["car"]["premium"] for leg in legs)
        need_man = flags.manual
        p_win = window_from_note(
            request["note"],
            legs[0]["pickup"]["window"],
            "pickup",
            v2=p.notes_v2,
            arrived_at=request["arrivedAt"],
            private_address=legs[0]["pickup"]["privateAddress"],
        )
        p_to = p_win["to"]
        extra_dur = (30 if flags.plates else 0) + sum(
            40
            for leg in legs
            if leg["car"]["electric"]
            and (leg["car"]["chargePercent"] or 0) < 30
            and p.charge_min_km > 0
            and self.geo.road_km(leg["pickup"]["placeId"], leg["delivery"]["placeId"]) >= p.charge_min_km
        )
        opt_deadlines: dict[str, int] = {}
        for opt in request["options"]:
            dl = opt["deadline"]
            if p.notes_v2:
                base_dl = shift_business_days(dl, extra_days)
                dl = min(
                    window_from_note(
                        request["note"],
                        {"from": leg["delivery"]["window"]["from"], "to": max(leg["delivery"]["window"]["from"], base_dl)},
                        "delivery",
                        v2=True,
                        arrived_at=request["arrivedAt"],
                        private_address=leg["delivery"]["privateAddress"],
                    )["to"]
                    for leg in legs
                )
            opt_deadlines[opt["kind"]] = dl

        unstaffed_here = sum(
            1
            for o in self.orders.values()
            if self.geo.line_km(o["legs"][0]["pickup"]["placeId"], pickup) <= p.net_km and not self.staffed(o)
        )
        matched_by_opt: dict[str, set[str]] = defaultdict(set)
        for entry in self.pos_ledger.values():
            if not entry.home_place:
                continue
            if entry.delivered and (entry.finish_at // DAY < self.now // DAY or self.now - entry.finish_at > 3 * HOUR):
                continue
            d = self.drivers.get(entry.driver_id)
            if d is None:
                continue
            if need_exp and not (d["rating"] >= 4.8 and d["completedGigs"] >= 50):
                continue
            if need_man and d["licence"] != "manual":
                continue
            if self.geo.line_km(entry.finish_place, pickup) > p.net_km or self.geo.line_km(entry.home_place, pickup) <= 30.0:
                continue
            fin_at = self.effective_finish_at(entry)
            if not (ready - 3 * HOUR <= fin_at <= ready + HOUR):
                continue
            arr = max(self.now, fin_at) + self.geo.minutes(entry.finish_place, pickup) + (30 if flags.plates else 0)
            dep = max(arr, ready)
            if dep > p_to:
                continue
            dep_open = next_open_minute(dep, legs[0]["pickup"])
            if dep_open > p_to or dep_open // DAY != fin_at // DAY:
                continue
            deliv_at = dep_open + drive + extra_dur - (30 if flags.plates else 0)
            if self._driver_conflict(entry, dep_open, deliv_at):
                continue
            for kind_name, dl in opt_deadlines.items():
                if dl - deliv_at >= p.min_slack_min:
                    matched_by_opt[kind_name].add(entry.driver_id)
        return {k for k, drvs in matched_by_opt.items() if len(drvs) > unstaffed_here}

    # --- restart (live mode) --------------------------------------------------------------------------
    def rejoin(self, snapshot: DeskSnapshot, history: list[DeskEvent]) -> None:
        """Rebuilds the books from the world after a (re)start, then answers what it missed."""
        posted: dict[str, list[Gig]] = {}
        self.booked = {g["id"] for g in snapshot["gigs"] if g["status"] in ("booked", "working", "done")}
        for gig in snapshot["gigs"]:
            for oid in order_ids_of(gig):
                posted.setdefault(oid, []).append(gig)
            if gig["status"] in ("open", "booked", "working"):
                self.carry({"type": "post", "stops": gig["stops"], "audience": gig["audience"], "schedule": gig["schedule"]}, gig["id"])
        self.requests = {e["request"]["id"]: e["request"] for e in history if e["kind"] == "price_request"}
        for req in self.requests.values():
            self.dealer_request_count[req["dealerId"]] += 1
            self.pickup_req_count[req["legs"][0]["pickup"]["placeId"]] += 1
        self.urgent = {e["orderId"] for e in history if e["kind"] == "deadline_close"}
        self.lost_requests = {e["requestId"] for e in history if e["kind"] == "order_lost"}
        
        # replay ledger to build trust exactly as handle() does
        _late_replay = set()
        for e in history:
            if e["kind"] == "ledger":
                line = e["line"]
                dealer = self.requests[line["orderId"]]["dealerId"] if line.get("orderId") and line["orderId"] in self.requests else None
                if line["kind"] in ("late_refund", "undelivered_penalty") and line.get("orderId"):
                    _late_replay.add(line["orderId"])
                    if dealer:
                        self.dealer_trust[dealer] //= 2
                elif line["kind"] == "revenue" and line.get("orderId"):
                    if dealer and line["orderId"] not in _late_replay:
                        order = next((o for o in snapshot["orders"] if o["id"] == line["orderId"]), None)
                        if order:
                            delivered = [d for d in order["deliveredAt"] if d is not None]
                            if len(delivered) == len(order["legs"]) and max(delivered) <= order["deadline"]:
                                self.dealer_trust[dealer] = min(25, self.dealer_trust[dealer] + 1)
                            
        for e in history:
            if e["kind"] == "gig_viewed":
                self.last_view[e["driverId"]] = e["at"]
            elif e["kind"] == "offer_answered":
                self.offers_sent[(e["driverId"], e["at"] // DAY)] += 1
                self.offered_pairs.add((e["gigId"], e["driverId"]))
        self.orders = {o["id"]: o for o in snapshot["orders"] if o["id"] in self.requests and o["status"] != "cancelled"}
        self._rejoin_orders = {o["id"]: o for o in snapshot["orders"]}

        # rebuild position ledger from snapshot gigs, history events, and driverPositions
        booked_time: dict[str, int] = {}
        late_time: dict[str, int] = {}
        picked_ev: dict[str, list[DeskEvent]] = defaultdict(list)
        deliv_ev: dict[str, list[DeskEvent]] = defaultdict(list)
        for e in history:
            ek = e["kind"]
            if ek == "gig_booked":
                booked_time[e["gigId"]] = e["at"]
            elif ek == "driver_late":
                late_time[e["gigId"]] = e["pickupAt"]
            elif ek == "picked_up":
                picked_ev[e["gigId"]].append(e)
            elif ek == "delivered":
                deliv_ev[e["gigId"]].append(e)
        for gig in snapshot["gigs"]:
            gid = gig["id"]
            if gig["status"] in ("booked", "working", "done") and gig["driverId"]:
                self._record_booking(gid, gig["driverId"], booked_time.get(gid, gig["postedAt"]), stops_override=gig["stops"])
                if gig["status"] in ("working", "done") and gid in self.pos_ledger:
                    self.pos_ledger[gid].started = True
                if gid in late_time:
                    self._on_driver_late(gid, late_time[gid], stops_override=gig["stops"])
                for pe in picked_ev.get(gid, []):
                    self._on_picked_up(gid, pe["orderId"], pe["leg"], pe["at"], stops_override=gig["stops"])
                for de in deliv_ev.get(gid, []):
                    self._on_delivered(gid, de["orderId"], de["leg"], de["placeId"], de["at"], stops_override=gig["stops"])
        self.sync_driver_positions(snapshot.get("driverPositions", []), snapshot["now"])
        self._rejoin_orders = {}
        self._net_dirty = True
        ratios = []  # the price level of the latest wins, so a restarted desk does not relearn from the prior
        for order in sorted(self.orders.values(), key=lambda o: self.requests[o["id"]]["arrivedAt"])[-30:]:
            option = next((o for o in self.requests[order["id"]]["options"] if o["kind"] == order["option"]), None)
            if option:
                ratios.append(order["priceCents"] / option["listPriceCents"])
        if ratios:
            self.mult = clamp(median(ratios), self.p.price_mult_min, self.p.price_mult_max)
        for order in self.orders.values():
            if order["status"] == "waiting" and not self.gigs_of(order["id"]):
                self.post(order, undelivered(order))
        for event in history:
            order = self.orders.get(event.get("orderId", ""))
            if order is None:
                continue
            if event["kind"] == "visit_failed" and order["deliveredAt"][event["leg"]] is None:
                later = [g for g in posted.get(order["id"], []) if g["postedAt"] >= event["at"] and g["id"] != event["gigId"]]
                if not any(stop["leg"] == event["leg"] for gig in later for stop in gig["stops"]):
                    self.retry(order["id"], event["leg"], event["reason"])
        for request in snapshot["openRequests"]:
            self.quote(request)


# --- helpers (the starter's) --------------------------------------------------------------------------
def retry_from(order: Order, request: PriceRequest, leg: int, now: int) -> int:
    promised = next((o["deadline"] for o in request["options"] if o["kind"] == order["option"]), order["deadline"])
    delay = max(0, order["deadline"] - promised)
    return max(now + 2 * HOUR, order["legs"][leg]["pickup"]["window"]["from"] + delay)


def undelivered(order: Order) -> list[int]:
    return [leg for leg in range(len(order["legs"])) if order["deliveredAt"][leg] is None]


def pickups(action: PostAction) -> int:
    return sum(1 for stop in action["stops"] if stop["kind"] == "pickup")


def order_ids_of(action: PostAction | Gig) -> list[str]:
    return list(dict.fromkeys(stop["orderId"] for stop in action["stops"]))


def without_windows(stops: list[StopRef], before: float) -> list[StopRef]:
    return [{k: v for k, v in stop.items() if k != "window"} if "window" in stop and stop["window"]["to"] < before else stop for stop in stops]


def stops_for(
    order: Order,
    legs: list[int],
    note,
    retry: Retry,
    geo: Optional[Geo] = None,
    charge_min_km: float = 0.0,
    notes_v2: bool = False,
    arrived_at: Optional[int] = None,
) -> list[StopRef]:
    """A pickup and a delivery for each leg. A stop has its own window only when the note or the retry
    makes it narrower. Rule 3: an electric car under 30% on a route over 200 km needs a charging stop."""
    stops: list[StopRef] = []
    for leg in legs:
        car, pickup, delivery = order["legs"][leg]["car"], order["legs"][leg]["pickup"], order["legs"][leg]["delivery"]
        noted = window_from_note(
            note, pickup["window"], "pickup",
            v2=notes_v2, arrived_at=arrived_at, private_address=pickup["privateAddress"], stated_hours=pickup["hours"],
        )
        start = max(noted["from"], retry.pickup_from)
        pickup_window: TimeWindow = {"from": start, "to": max(noted["to"], start)}
        delivery_base: TimeWindow = {"from": delivery["window"]["from"], "to": max(delivery["window"]["from"], order["deadline"])}
        delivery_window = window_from_note(
            note, delivery_base, "delivery",
            v2=notes_v2, arrived_at=arrived_at, private_address=delivery["privateAddress"], stated_hours=delivery["hours"],
        )
        low_battery = car["electric"] and car["chargePercent"] is not None and car["chargePercent"] < 30
        if low_battery and geo is not None:
            low_battery = geo.road_km(pickup["placeId"], delivery["placeId"]) > charge_min_km
        first: StopRef = {"orderId": order["id"], "leg": leg, "kind": "pickup", "withPlates": retry.plates, "withCharging": low_battery}
        second: StopRef = {"orderId": order["id"], "leg": leg, "kind": "delivery"}
        stops += [narrower(first, pickup_window, pickup["window"]), narrower(second, delivery_window, delivery_base)]
    return stops


def narrower(stop: StopRef, window: TimeWindow, base: TimeWindow) -> StopRef:
    return {**stop, "window": window} if window["from"] <= window["to"] and (window["from"] > base["from"] or window["to"] < base["to"]) else stop


def next_open_minute(t: int, place_spec: StopPlace) -> int:
    """First minute >= t when a non-private stop's stated opening hours show it open."""
    if place_spec["privateAddress"] or not place_spec.get("hours"):
        return t
    hours = place_spec["hours"]
    assert hours is not None
    for offset in range(8):
        day_idx = (t // DAY) + offset
        wd = day_idx % 7
        if wd in hours["weekdays"]:
            opens, closes = hours["opens"], hours["closes"]
        elif wd == 5 and hours.get("saturday") is not None:
            sat = hours["saturday"]
            assert sat is not None
            opens, closes = sat["opens"], sat["closes"]
        else:
            continue
        cur = (t % DAY) if offset == 0 else 0
        if cur < opens:
            return day_idx * DAY + opens
        if cur < closes:
            return day_idx * DAY + cur
    return t

