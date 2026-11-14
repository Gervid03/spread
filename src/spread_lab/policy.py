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
    Action, ActionResult, Audience, DeskEvent, DeskSnapshot, DriverProfile, FeeStep, Gig, OpeningHours, Order,
    PostAction, PriceRequest, StopRef, TimeWindow,
)

from .geo import Geo
from .notes import note_flags, parse_note_v2, shift_business_days, window_from_note

HOUR, DAY = 60, 24 * 60


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
    hub_multiday_fee_open: float = 0.0  # if > 0, opening fee for non-same_day in supply >= 150 with >= 6h to warning
    thin_sameday_fee_open: float = 0.0  # if > 0, opening fee for same_day in supply < 65
    fee_warn: float = 1.60            # fee reached at the deadline warning (lastPickupAt - 3 h)
    fee_step_min: int = 30            # minutes between steps of the rising schedule
    day_start: int = 7 * 60           # raises only between these minutes of the day
    day_end: int = 22 * 60
    steep_open: float = 1.80          # after the deadline warning
    steep_step: float = 0.25          # added every half hour
    steep_max: float = 3.00
    drop_urgent_margin_min: int = 0   # if > 0, gig_dropped/no_show within this many min of lastPickupAt triggers raise_fees
    late_fee_open: float = 0.0        # if > 0, lost orders open at this x typical fee and climb to late_fee_max
    late_fee_max: float = 1.3         # fee ceiling for lost orders at the next refund-tier boundary minus drive
    late_repost: bool = False         # withdraw and repost without windows when an unstaffed order passes lastPickupAt
    # --- direct offers after the deadline warning ---------------------------------------------------
    offers_per_warning: int = 0       # at most 3 open offers per gig, 3 per driver per day (rules) (v2: was 3; 3 of 218 offers were accepted)
    offer_mult: float = 2.20          # offer fee, times the typical fee of the cars
    offer_recent_view_min: int = 240  # drivers who viewed one of our gigs this recently go first
    # --- lead-car multi-car gig pairing -------------------------------------------------------------
    lead_car: bool = False
    lead_car_max_gap_km: float = 0.0
    lead_car_max_deliv_gap_km: float = 25.0
    lead_car_fee_mult: float = 1.00
    # --- return offers to our own finishing drivers (idea 26) ---------------------------------------
    return_offer_km: float = 0.0          # 0 = off; quote thin slow requests within this km of our booked deliveries
    return_markup: float = 0.0            # price = tracker price * (1 + return_markup)
    return_cap_day: int = 8               # max return-offer wins per day
    return_fee_open: float = 0.75         # opening board fee x typical fee for return-offer gigs
    return_offer_mult: float = 0.90       # direct offer fee x typical fee sent to the outbound driver
    return_offer_lead_min: int = 45       # send offer this many min before planned outbound delivery
    return_offer_on_win: bool = False     # also send a daytime offer on order_won while driver holds outbound gig
    return_toward_home: bool = False      # only match outbound drivers for whom delivery moves closer to home (or <=30km)
    return_max_wait_min: int = 0          # if > 0, max wait minutes from planned outbound delivery to return pickup
    # --- handling rules -----------------------------------------------------------------------------
    charge_min_km: float = 200.0      # rule 3: an EV under 30% charge needs a charging stop on a route over this
    notes_v2: bool = False            # v2 note reader + delivery hours / note deadlines shorten option slack
    note_unsure: str = "quote"        # "quote" or "decline" when a note has a time the reader cannot place
    # --- trust --------------------------------------------------------------------------------------
    trust_gain: float = 0.0           # multiply dealer's quote by 1 + trust_gain * count/100
    trust_invest: float = 0.0         # discount on safe requests for top 3 dealers, Mon-Wed
    trust_guard: bool = False         # decline same_day thin town or >300min if count >= 13
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
        self.lost: set[str] = set()                  # orders that can no longer be on time
        self.late_reposted: set[str] = set()         # orders already reposted in tick() upon becoming lost
        self.ends_at: int = 14280                    # second Wednesday 22:00
        self.gig_driver: dict[str, str] = {}
        self.gig_booked_at: dict[str, int] = {}
        self.gig_started_at: dict[str, int] = {}
        self.gig_late_pickup: dict[str, int] = {}
        self.gig_picked_up: dict[tuple[str, str, int], tuple[int, str]] = {}
        self.gig_delivered_legs: dict[tuple[str, str, int], tuple[int, str]] = {}
        self.gig_completed_at: dict[str, int] = {}
        self.booked_deliveries: dict[str, list[dict[str, Any]]] = {}
        self.open_gig_offers: dict[str, set[str]] = defaultdict(set)
        self.return_reqs: set[str] = set()
        self.return_targets: dict[str, tuple[str, str]] = {}
        self.return_wins_by_day: Counter = Counter()
        self.return_offer_gigs: dict[str, str] = {}
        self.return_offered_orders: set[str] = set()
        self.return_sent_stage: set[tuple[str, str, str]] = set()
        self.return_declined_orders: set[tuple[str, str]] = set()
        self.return_gone_home_counted: set[str] = set()

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
        elif kind == "order_cancelled":
            self.orders.pop(event["orderId"], None)
            if self.p.lead_car:
                self.withdraw(event["orderId"])
            self.leg_gigs.pop(event["orderId"], None)
            for cg in event["gigs"]:
                gid = cg["gigId"]
                if cg["outcome"] in ("withdrawn", "released"):
                    self.booked.discard(gid)
                    self.clear_gig_tracking(gid)
                elif cg["outcome"] == "shortened" and gid in self.booked:
                    self.update_gig_deliveries(gid)
        elif kind == "visit_failed":
            self.stats["visit_failed"] += 1
            self.stats[f"visit_failed_{event['reason']}"] += 1
            self.retry(event["orderId"], event["leg"], event["reason"])
        elif kind == "gig_expired":
            self.stats["gig_expired"] += 1
            self.open_gig_offers.pop(event["gigId"], None)
            post = self.posts.get(event["gigId"])
            if post:
                for s in post["stops"]:
                    self.lost.add(s["orderId"])
            self.repost(event["gigId"])
        elif kind == "deadline_close":
            self.stats["deadline_close"] += 1
            self.raise_fees(event["orderId"])
        elif kind == "gig_booked":
            gid = event["gigId"]
            self.booked.add(gid)
            self.gig_driver[gid] = event["driverId"]
            self.gig_booked_at[gid] = event["at"]
            self.open_gig_offers.pop(gid, None)
            self.update_gig_deliveries(gid)
            self.stats["booked"] += 1
            if gid in self.posts and len(order_ids_of(self.posts[gid])) > 1:
                self.stats["lead_car_booked"] += 1
            post = self.posts.get(gid)
            if post:
                order_ids = list(dict.fromkeys(s["orderId"] for s in post["stops"]))
                if self.p.return_offer_km > 0 and any(oid in self.return_reqs for oid in order_ids):
                    self.stats["ret_booked"] += 1
                    self.stats["ret_booked_fee_cents"] += event["feeCents"]
                for order_id in order_ids:
                    order = self.orders.get(order_id)
                    if order and self.now > order["lastPickupAt"]:
                        self.lost.add(order_id)
                if any(oid in self.lost for oid in order_ids):
                    self.stats["fee_lost_cents"] += event["feeCents"]
                    self.stats["fee_lost_n"] += 1
                elif any(oid in self.urgent for oid in order_ids):
                    self.stats["fee_warned_cents"] += event["feeCents"]
                    self.stats["fee_warned_n"] += 1
        elif kind in ("gig_dropped", "no_show"):
            gid = event["gigId"]
            self.booked.discard(gid)
            self.clear_gig_tracking(gid)
            self.stats[kind] += 1
            post = self.posts.get(gid)
            if post:
                for order_id in dict.fromkeys(s["orderId"] for s in post["stops"]):
                    order = self.orders.get(order_id)
                    if order and undelivered(order) and self.now > order["lastPickupAt"]:
                        self.lost.add(order_id)
            if self.p.drop_urgent_margin_min > 0:
                if post:
                    for order_id in dict.fromkeys(s["orderId"] for s in post["stops"]):
                        if (
                            order_id in self.orders
                            and undelivered(self.orders[order_id])
                            and self.orders[order_id]["lastPickupAt"] - self.now <= self.p.drop_urgent_margin_min
                        ):
                            self.stats["drop_rescued"] += 1
                            self.raise_fees(order_id)
        elif kind == "gig_started":
            self.gig_started_at[event["gigId"]] = event["at"]
            if event["gigId"] in self.booked:
                self.update_gig_deliveries(event["gigId"])
        elif kind == "driver_late":
            self.gig_late_pickup[event["gigId"]] = event["pickupAt"]
            if event["gigId"] in self.booked:
                self.update_gig_deliveries(event["gigId"])
        elif kind == "picked_up":
            self.gig_picked_up[(event["gigId"], event["orderId"], event["leg"])] = (event["at"], event["placeId"])
            if event["gigId"] in self.booked:
                self.update_gig_deliveries(event["gigId"])
        elif kind == "gig_viewed":
            self.last_view[event["driverId"]] = event["at"]
        elif kind == "ledger":
            line = event["line"]
            oid = line.get("orderId")
            order = self.orders.get(oid, None) if oid else None
            dealer = self.requests[oid]["dealerId"] if oid and oid in self.requests else None
            is_ring = order and self.supply.get(order["legs"][0]["pickup"]["placeId"], 0) < self.p.min_supply
            is_ret = self.p.return_offer_km > 0 and bool(oid and oid in self.return_reqs)
            is_ext_ring = order and not is_ret and self.gate_supply.get(order["legs"][0]["pickup"]["placeId"], 0) < self.p.min_supply
            if is_ring:
                self.stats["margin_ring_cents"] += line["cents"]
            if is_ext_ring:
                self.stats["margin_ext_ring_cents"] += line["cents"]
            if is_ret:
                self.stats["ret_margin_cents"] += line["cents"]
                self.stats[f"ret_{line['kind']}_cents"] += line["cents"]
            if line["kind"] in ("late_refund", "undelivered_penalty") and oid:
                if oid not in self.late:
                    if is_ring:
                        self.stats["late_ring"] += 1
                    if order and order["option"] == "same_day" and oid in self.ring_hub_same_day:
                        self.stats["late_ring_hub_same_day"] += 1
                    if is_ext_ring:
                        self.stats["late_ext_ring"] += 1
                    if is_ret:
                        self.stats["ret_late"] += 1
                self.late.add(oid)
                if dealer:
                    self.dealer_trust[dealer] //= 2
            elif line["kind"] == "revenue" and oid:
                if dealer and oid not in self.late:
                    if order and self.now <= order["deadline"]:
                        self.dealer_trust[dealer] = min(25, self.dealer_trust[dealer] + 1)
        elif kind == "offer_answered":
            self.open_gig_offers[event["gigId"]].discard(event["driverId"])
            self.stats[f"offer_{event['answer']}"] += 1
            if self.p.return_offer_km > 0 and event["gigId"] in self.return_offer_gigs:
                ret_oid = self.return_offer_gigs[event["gigId"]]
                self.stats[f"ret_{event['answer']}"] += 1
                if event["answer"] == "declined":
                    self.return_declined_orders.add((ret_oid, event["driverId"]))
        elif kind == "delivered":
            self.leg_gigs.get(event["orderId"], {}).pop(event["leg"], None)
            self.gig_delivered_legs[(event["gigId"], event["orderId"], event["leg"])] = (event["at"], event["placeId"])
            if event["gigId"] in self.booked:
                self.update_gig_deliveries(event["gigId"])
            if event["orderId"] in self.orders:
                order = self.orders[event["orderId"]]
                order["deliveredAt"][event["leg"]] = event["at"]
                if not undelivered(order):
                    delivered_at = max(d for d in order["deliveredAt"] if d is not None)
                    if delivered_at > order["deadline"]:
                        lateness = delivered_at - order["deadline"]
                        if lateness <= 2 * HOUR:
                            self.stats["late_le_2h"] += 1
                        elif lateness <= 24 * HOUR:
                            self.stats["late_le_24h"] += 1
                        else:
                            self.stats["late_more"] += 1

    def tick(self) -> None:
        """Called after every step (practice) or event (live)."""
        day = self.now // DAY
        if not hasattr(self, "_last_day"):
            self._last_day = day
        elif day > self._last_day:
            if self.dealer_trust:
                self.stats[f"top_dealer_trust_d{self._last_day}"] = max(self.dealer_trust.values())
            self._last_day = day
        for order_id, order in list(self.orders.items()):
            if undelivered(order) and not self.staffed(order) and self.now > order["lastPickupAt"]:
                self.lost.add(order_id)
                if self.p.late_repost and order_id not in self.late_reposted:
                    self.send_post_of(order_id)
                    gigs = self.gigs_of(order_id)
                    if gigs and all(gig_id not in self.booked for gig_id in gigs):
                        self.late_reposted.add(order_id)
                        self.stats["late_reposts"] += 1
                        self.leg_gigs.pop(order_id, None)
                        for gig_id in gigs:
                            self.outbox.append({"type": "withdraw", "gigId": gig_id})
                            action = self.posts.get(gig_id)
                            if action is not None:
                                stops = without_windows(action["stops"], float("inf"))
                                self.outbox.append({**action, "stops": stops, "schedule": self.fees_for(order, pickups(action), action)})
        if self.p.return_offer_km > 0:
            self.send_return_offers()

    # --- quoting --------------------------------------------------------------------------------------
    def quote(self, request: PriceRequest) -> None:
        self.requests[request["id"]] = request
        self.dealer_request_count[request["dealerId"]] += 1
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
        pass_ext_ring = False
        pass_return_hub = False
        pass_return_offer = False
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
                if p.return_offer_km > 0 and self.return_wins_by_day[self.now // DAY] < p.return_cap_day:
                    pass_return_offer = bool(self.booked_deliveries)
                if not pass_return_offer:
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
        best_return_target: Optional[tuple[str, str]] = None
        for option in request["options"]:
            ring_hub_sd = False
            if (pass_ext_ring or pass_return_hub or pass_return_offer) and option["kind"] == "same_day":
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
            if pass_return_offer:
                ret_cands = self.find_return_drivers_for_option(request, ready, drive, deadline, for_quote=True)
                if not ret_cands:
                    continue
                if best_return_target is None:
                    best_return_target = (ret_cands[0][0], ret_cands[0][1])
            if ring_hub_sd:
                self.stats["quoted_ring_hub_same_day"] += 1
                self.ring_hub_same_day.add(request["id"])

            option_mult = mult
            if is_invest and slack >= 360:
                option_mult *= (1 - p.trust_invest)
            if p.return_hub_discount > 0 and pass_return_hub and not pass_ext_ring:
                option_mult *= (1.0 - p.return_hub_discount)
            if pass_return_offer:
                option_mult *= (1.0 + p.return_markup)

            price = option["listPriceCents"] * option_mult * (1 + p.same_day_markup if option["kind"] == "same_day" else 1)
            floor = fee / (1 - p.min_margin_frac)
            if price < floor:
                price, floored = floor, True
            prices[option["kind"]] = int(price + 0.5)
        if not prices:
            return {}, "decline"
        if pass_return_offer and best_return_target is not None:
            self.return_reqs.add(request["id"])
            self.return_targets[request["id"]] = best_return_target
            self.stats["ret_quoted"] += 1
        elif pass_ext_ring or pass_return_hub:
            self.ext_ring_reqs.add(request["id"])
            self.stats["quoted_ext_ring"] += 1
            if pass_return_hub:
                self.stats["quoted_return_hub"] += 1
        return prices, "floor" if floored else "quote"

    def learn(self, request_id: str, won: bool) -> None:
        """Moves the multiplier towards the price that wins `price_target_win` of the normal quotes."""
        if self.p.return_offer_km > 0 and request_id in self.return_reqs:
            self.stats["ret_skipped_learn"] += 1
            return
        if self.decided.get(request_id) != "quote":
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
            if self.p.return_offer_km > 0 and order["id"] in self.return_reqs:
                self.stats["ret_won"] += 1
                self.return_wins_by_day[self.now // DAY] += 1
                target = self.return_targets.get(order["id"])
                if target is not None:
                    _, out_gid = target
                    if out_gid in self.gig_completed_at and self.gig_completed_at[out_gid] <= self.now:
                        self.stats["ret_gone_home"] += 1
                        self.stats["ret_gone_home_at_win"] += 1
                        self.return_gone_home_counted.add(order["id"])
                    elif out_gid not in self.booked:
                        self.stats["ret_outbound_dropped"] += 1
            elif self.gate_supply.get(pickup, 0) < self.p.min_supply:
                self.stats["won_ext_ring"] += 1
                if self.p.return_hub_min_supply > 0 and self.supply.get(order["legs"][-1]["delivery"]["placeId"], 0) >= self.p.return_hub_min_supply:
                    self.stats["won_return_hub"] += 1
            self.stats[f"won_{order['option']}"] += 1
            self.post(order, undelivered(order))

    def change(self, order: Order) -> None:
        if order["id"] in self.orders:
            self.orders[order["id"]] = order
            if self.withdraw(order["id"]):
                self.post(order, undelivered(order))
            else:
                for gid in self.gigs_of(order["id"]):
                    if gid in self.booked:
                        self.update_gig_deliveries(gid)

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
        open_slots = max(0, 3 - len(self.open_gig_offers[gig_id]))
        for _, _, driver_id in candidates:
            if open_slots <= 0 or open_slots <= 3 - min(3, p.offers_per_warning):
                break
            if driver_id in self.open_gig_offers[gig_id]:
                continue
            self.outbox.append({"type": "offer", "gigId": gig_id, "driverId": driver_id, "feeCents": fee})
            self.offers_sent[(driver_id, day)] += 1
            self.open_gig_offers[gig_id].add(driver_id)
            self.stats["offers"] += 1
            open_slots -= 1

    def fees_for(self, order: Order, cars: int, action: Optional[PostAction] = None) -> list[FeeStep]:
        p = self.p
        if action is not None:
            oids = order_ids_of(action)
            if len(oids) > 1:
                base = sum(self.requests[oid]["referenceFeeCents"] for oid in oids if oid in self.requests) * p.lead_car_fee_mult
                if self.level == 1:
                    return [{"at": self.now, "feeCents": max(1, int(base * p.fee_open + 0.5))}]
                if any(oid in self.urgent for oid in oids):
                    return self.steep(base)
                until = min((self.orders[oid]["lastPickupAt"] for oid in oids if oid in self.orders), default=order["lastPickupAt"]) - 3 * HOUR
                return self.rising(base, until)
        base = self.requests[order["id"]]["referenceFeeCents"] * cars / len(order["legs"])
        if self.level == 1:
            return [{"at": self.now, "feeCents": max(1, int(base * p.fee_open + 0.5))}]
        if p.late_fee_open > 0:
            if undelivered(order) and not self.staffed(order) and self.now > order["lastPickupAt"]:
                self.lost.add(order["id"])
            if order["id"] in self.lost:
                if self.ends_at - self.now <= 36 * HOUR:
                    return self.rising(base, self.ends_at - 12 * HOUR, fee_open_override=p.late_fee_open, fee_warn_override=p.steep_max)
                open_legs = undelivered(order) or list(range(len(order["legs"])))
                drive = sum(self.geo.minutes(order["legs"][i]["pickup"]["placeId"], order["legs"][i]["delivery"]["placeId"]) for i in open_legs)
                if len(open_legs) == 2:
                    drive += self.geo.minutes(order["legs"][open_legs[0]]["delivery"]["placeId"], order["legs"][open_legs[1]]["pickup"]["placeId"])
                t24 = order["deadline"] + 24 * HOUR - drive
                t2b = add_business_days(order["deadline"], 2) - drive
                until = t24 if self.now < t24 else (t2b if self.now < t2b else self.ends_at - drive)
                return self.rising(base, until, fee_open_override=p.late_fee_open, fee_warn_override=p.late_fee_max)
        if order["id"] in self.urgent:
            return self.steep(base)
        until = order["lastPickupAt"] - 3 * HOUR
        supply = self.supply.get(order["legs"][0]["pickup"]["placeId"], 0)
        fee_open_override: Optional[float] = None
        if p.return_offer_km > 0 and order["id"] in self.return_reqs and p.return_fee_open > 0:
            fee_open_override = p.return_fee_open
        elif p.hub_multiday_fee_open > 0 and order["option"] != "same_day" and supply >= 150 and until - self.now >= 6 * HOUR:
            fee_open_override = p.hub_multiday_fee_open
            self.stats["hub_multiday_posts"] += 1
        elif p.thin_sameday_fee_open > 0 and order["option"] == "same_day" and supply < 65:
            fee_open_override = p.thin_sameday_fee_open
            self.stats["thin_sameday_posts"] += 1
        return self.rising(base, until, fee_open_override=fee_open_override)

    def rising(
        self,
        base: float,
        until: int,
        fee_open_override: Optional[float] = None,
        fee_warn_override: Optional[float] = None,
    ) -> list[FeeStep]:
        """From `fee_open` now to `fee_warn` at `until`, in daytime steps only, at most 48 steps."""
        p = self.p
        fee_open = fee_open_override if fee_open_override is not None else p.fee_open
        fee_warn = fee_warn_override if fee_warn_override is not None else p.fee_warn
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
        return [{"at": at, "feeCents": max(1, int(base * (fee_open + (fee_warn - fee_open) * (i / (n - 1) if n > 1 else 0)) + 0.5))}
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
        if p.return_offer_km > 0 and order["id"] in self.return_reqs:
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
                    and (p.return_offer_km <= 0 or oid not in self.return_reqs)
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
            if p.return_offer_km > 0 and other_id in self.return_reqs:
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
            else:
                self.stats[f"refused_{action['type']}"] += 1

    # --- booked-gig delivery tracking & return offers -------------------------------------------------
    def clear_gig_tracking(self, gig_id: str) -> None:
        self.booked_deliveries.pop(gig_id, None)
        self.gig_driver.pop(gig_id, None)
        self.gig_booked_at.pop(gig_id, None)
        self.gig_started_at.pop(gig_id, None)
        self.gig_late_pickup.pop(gig_id, None)
        self.open_gig_offers.pop(gig_id, None)
        for k in [k for k in self.gig_picked_up if k[0] == gig_id]:
            self.gig_picked_up.pop(k, None)
        for k in [k for k in self.gig_delivered_legs if k[0] == gig_id]:
            self.gig_delivered_legs.pop(k, None)

    def update_gig_deliveries(self, gig_id: str) -> None:
        """Computes planned delivery minute and place for each car of a booked gig."""
        if gig_id not in self.booked:
            self.booked_deliveries.pop(gig_id, None)
            return
        driver_id = self.gig_driver.get(gig_id)
        post = self.posts.get(gig_id)
        if not driver_id or post is None:
            return
        booked_at = self.gig_booked_at.get(gig_id, self.now)
        drv = self.drivers.get(driver_id)
        cur_place: Optional[str] = drv["homePlaceId"] if drv else None
        t = booked_at
        for other_gid, other_entries in self.booked_deliveries.items():
            if other_gid == gig_id or not other_entries or other_entries[-1]["driver_id"] != driver_id:
                continue
            if self.gig_booked_at.get(other_gid, 0) < booked_at and not other_entries[-1]["delivered"]:
                if other_entries[-1]["planned_at"] // DAY == booked_at // DAY and other_entries[-1]["planned_at"] >= t:
                    t = other_entries[-1]["planned_at"]
                    cur_place = other_entries[-1]["place_id"]
        if gig_id in self.gig_started_at:
            t = self.gig_started_at[gig_id]

        charging_extra: dict[tuple[str, int], int] = {}
        entries: list[dict[str, Any]] = []
        for idx, s in enumerate(post["stops"]):
            oid, leg = s["orderId"], s["leg"]
            src = self.orders.get(oid) or self.requests.get(oid)
            if src is None or leg >= len(src["legs"]):
                continue
            leg_obj = src["legs"][leg]
            stop_info = leg_obj["pickup"] if s["kind"] == "pickup" else leg_obj["delivery"]
            place_id = stop_info["placeId"]
            if s["kind"] == "pickup":
                pkey = (gig_id, oid, leg)
                if pkey in self.gig_picked_up:
                    t, place_id = self.gig_picked_up[pkey]
                else:
                    if idx == 0 and gig_id in self.gig_late_pickup:
                        t = self.gig_late_pickup[gig_id]
                    else:
                        if cur_place is not None:
                            t += self.geo.minutes(cur_place, place_id)
                        t = max(t, stop_info["window"]["from"])
                        if "window" in s:
                            t = max(t, s["window"]["from"])
                        if not stop_info["privateAddress"] and stop_info.get("hours"):
                            t = next_open_minute(t, stop_info["hours"])
                if s.get("withCharging"):
                    charging_extra[(oid, leg)] = 30
                cur_place = place_id
            else:
                dkey = (gig_id, oid, leg)
                if dkey in self.gig_delivered_legs:
                    dat, dplace = self.gig_delivered_legs[dkey]
                    t, cur_place = dat, dplace
                    entries.append({
                        "gig_id": gig_id,
                        "driver_id": driver_id,
                        "order_id": oid,
                        "leg": leg,
                        "place_id": dplace,
                        "planned_at": dat,
                        "delivered": True,
                    })
                else:
                    if cur_place is not None:
                        t += self.geo.minutes(cur_place, place_id)
                    t += charging_extra.get((oid, leg), 0)
                    t = max(t, stop_info["window"]["from"])
                    if "window" in s:
                        t = max(t, s["window"]["from"])
                    if not stop_info["privateAddress"] and stop_info.get("hours"):
                        t = next_open_minute(t, stop_info["hours"])
                    cur_place = place_id
                    entries.append({
                        "gig_id": gig_id,
                        "driver_id": driver_id,
                        "order_id": oid,
                        "leg": leg,
                        "place_id": place_id,
                        "planned_at": t,
                        "delivered": False,
                    })
        if entries and all(e["delivered"] for e in entries):
            self.gig_completed_at[gig_id] = max(e["planned_at"] for e in entries)
            self.booked_deliveries.pop(gig_id, None)
        elif entries:
            self.booked_deliveries[gig_id] = entries

    def driver_has_later_gig(self, driver_id: str, out_gid: str, planned_at: int) -> bool:
        for other_gid, entries in self.booked_deliveries.items():
            if other_gid == out_gid or not entries or entries[-1]["driver_id"] != driver_id:
                continue
            if entries[-1]["planned_at"] > planned_at and entries[-1]["planned_at"] // DAY == planned_at // DAY:
                return True
        return False

    def outbound_gig_committed(self, out_gid: str) -> bool:
        inflight = 0
        for oid in self.return_reqs:
            if self.return_targets.get(oid, ("", ""))[1] != out_gid:
                continue
            if oid in self.orders:
                order = self.orders[oid]
                if undelivered(order) and not self.staffed(order):
                    return True
            elif oid not in self.lost_requests and oid in self.requests and self.now <= self.requests[oid]["respondBy"]:
                inflight += 1
                if inflight >= 2:
                    return True
        return False

    def is_toward_home(self, driver_id: str, pickup: str, delivery: str) -> bool:
        drv = self.drivers.get(driver_id)
        if not drv:
            return False
        home = drv["homePlaceId"]
        if self.geo.line_km(home, delivery) <= 30.0:
            return True
        return self.geo.minutes(delivery, home) <= self.geo.minutes(pickup, home) - 20

    def find_return_drivers_for_option(
        self,
        request: PriceRequest,
        ready: int,
        drive: int,
        deadline: int,
        for_quote: bool = True,
    ) -> list[tuple[str, str, int, float]]:
        p, legs = self.p, request["legs"]
        pickup = legs[0]["pickup"]["placeId"]
        deliv_place = legs[-1]["delivery"]["placeId"]
        need_exp = any(leg["car"]["premium"] for leg in legs)
        flags = note_flags(request["note"], v2=p.notes_v2)
        need_manual = flags.manual
        leg0_pick = legs[0]["pickup"]
        base_p_win = window_from_note(
            request["note"],
            leg0_pick["window"],
            "pickup",
            v2=p.notes_v2,
            arrived_at=request["arrivedAt"],
            private_address=leg0_pick["privateAddress"],
            stated_hours=leg0_pick["hours"],
        )
        pickup_close = base_p_win["to"] if leg0_pick["privateAddress"] else min(base_p_win["to"], deadline)

        ranked: list[tuple[int, float, int, str, str]] = []
        for out_gid in sorted(self.booked_deliveries):
            entries = self.booked_deliveries[out_gid]
            if not entries:
                continue
            last_d = entries[-1]
            if last_d["delivered"]:
                continue
            drv_id = last_d["driver_id"]
            d_place = last_d["place_id"]
            planned_at = last_d["planned_at"]
            dist_km = self.geo.line_km(d_place, pickup)
            if dist_km > p.return_offer_km:
                continue
            drv = self.drivers.get(drv_id)
            if not drv:
                continue
            if need_exp and not (drv["rating"] >= 4.8 and drv["completedGigs"] >= 50):
                continue
            if need_manual and drv["licence"] != "manual":
                continue
            if self.driver_has_later_gig(drv_id, out_gid, planned_at):
                continue
            if for_quote and self.outbound_gig_committed(out_gid):
                continue
            if p.return_toward_home and not self.is_toward_home(drv_id, pickup, deliv_place):
                continue
            if planned_at > pickup_close:
                continue
            reach_pickup = max(self.now, ready, planned_at + self.geo.minutes(d_place, pickup))
            if not leg0_pick["privateAddress"] and leg0_pick.get("hours"):
                reach_pickup = next_open_minute(reach_pickup, leg0_pick["hours"])
            if reach_pickup > pickup_close:
                continue
            if p.return_max_wait_min > 0 and reach_pickup - planned_at > p.return_max_wait_min:
                continue
            if deadline - reach_pickup - drive < p.min_slack_min:
                continue
            home_prio = 0 if self.geo.line_km(drv["homePlaceId"], deliv_place) <= 30.0 else 1
            ranked.append((home_prio, dist_km, planned_at, drv_id, out_gid))
        ranked.sort()
        return [(drv_id, out_gid, planned_at, dist_km) for _, dist_km, planned_at, drv_id, out_gid in ranked]

    def send_return_offers(self) -> None:
        p = self.p
        if p.return_offer_km <= 0 or self.level < 3:
            return
        for order_id in sorted(self.return_reqs):
            order = self.orders.get(order_id)
            if order is None or not undelivered(order) or self.staffed(order):
                continue
            if order_id not in self.return_offered_orders and order_id not in self.return_gone_home_counted:
                target = self.return_targets.get(order_id)
                if target is not None:
                    _, out_gid = target
                    if out_gid in self.gig_completed_at and self.gig_completed_at[out_gid] <= self.now:
                        self.stats["ret_gone_home"] += 1
                        self.return_gone_home_counted.add(order_id)

        if not (7 * HOUR <= self.now % DAY < 22 * HOUR + 30):
            return
        day = self.now // DAY
        for order_id in sorted(self.return_reqs):
            order = self.orders.get(order_id)
            if order is None or not undelivered(order) or self.staffed(order):
                continue
            req = self.requests.get(order_id)
            if req is None:
                continue
            legs = order["legs"]
            drive = sum(self.geo.minutes(leg["pickup"]["placeId"], leg["delivery"]["placeId"]) for leg in legs)
            if len(legs) == 2:
                drive += self.geo.minutes(legs[0]["delivery"]["placeId"], legs[1]["pickup"]["placeId"])
            ready = max(
                [self.now]
                + [
                    window_from_note(
                        req["note"],
                        leg["pickup"]["window"],
                        "pickup",
                        v2=p.notes_v2,
                        arrived_at=req["arrivedAt"],
                        private_address=leg["pickup"]["privateAddress"],
                    )["from"]
                    for leg in legs
                ]
            )
            cands = self.find_return_drivers_for_option(req, ready, drive, order["deadline"], for_quote=False)
            if not cands:
                continue
            target_drv = self.return_targets.get(order_id, ("", ""))[0]
            due_cands: list[tuple[int, float, int, str, str]] = []
            for drv_id, out_gid, planned_at, dist_km in cands:
                if (order_id, drv_id) in self.return_declined_orders:
                    continue
                due_lead = self.now >= planned_at - p.return_offer_lead_min
                due_win = p.return_offer_on_win and (order_id, drv_id, "win") not in self.return_sent_stage and planned_at // DAY == day
                if due_lead and (order_id, drv_id, "lead") not in self.return_sent_stage:
                    due_cands.append((0 if drv_id == target_drv else 1, dist_km, planned_at, drv_id, "lead"))
                elif due_win:
                    due_cands.append((0 if drv_id == target_drv else 1, dist_km, planned_at, drv_id, "win"))
            if not due_cands:
                continue
            due_cands.sort()
            self.send_post_of(order_id)
            open_gigs = [g for g in self.gigs_of(order_id) if g not in self.booked and g in self.posts]
            if not open_gigs:
                continue
            gig_id = open_gigs[0]
            post = self.posts[gig_id]
            audience = post["audience"]
            fee = max(1, int(req["referenceFeeCents"] * pickups(post) / len(order["legs"]) * p.return_offer_mult + 0.5))
            seen_drv: set[str] = set()
            for _, _, _, drv_id, stage in due_cands:
                if drv_id in seen_drv or drv_id in self.open_gig_offers[gig_id]:
                    continue
                seen_drv.add(drv_id)
                drv = self.drivers.get(drv_id)
                if not drv:
                    continue
                if audience["experienced"] and not (drv["rating"] >= 4.8 and drv["completedGigs"] >= 50):
                    continue
                if audience["manualLicence"] and drv["licence"] != "manual":
                    continue
                if len(self.open_gig_offers[gig_id]) >= 3:
                    self.stats["ret_limit_gig"] += 1
                    break
                if self.offers_sent[(drv_id, day)] >= 3:
                    self.stats["ret_limit_driver"] += 1
                    continue
                self.outbox.append({"type": "offer", "gigId": gig_id, "driverId": drv_id, "feeCents": fee})
                self.offers_sent[(drv_id, day)] += 1
                self.open_gig_offers[gig_id].add(drv_id)
                self.return_offer_gigs[gig_id] = order_id
                if order_id not in self.return_offered_orders:
                    self.return_offered_orders.add(order_id)
                    self.stats["ret_offered_orders"] += 1
                self.return_sent_stage.add((order_id, drv_id, stage))
                self.stats["offers"] += 1
                self.stats["ret_offered"] += 1
                if drv_id == target_drv:
                    break  # offer the matched outbound driver; others remain fallback if declined/expired

    # --- restart (live mode) --------------------------------------------------------------------------
    def rejoin(self, snapshot: DeskSnapshot, history: list[DeskEvent]) -> None:
        """Rebuilds the books from the world after a (re)start, then answers what it missed."""
        self.ends_at = snapshot.get("endsAt", 14280)
        posted: dict[str, list[Gig]] = {}
        gigs_by_id = {g["id"]: g for g in snapshot["gigs"]}
        self.booked = {g["id"] for g in snapshot["gigs"] if g["status"] in ("booked", "working", "done")}
        for gig in snapshot["gigs"]:
            for oid in order_ids_of(gig):
                posted.setdefault(oid, []).append(gig)
            if gig["status"] in ("open", "booked", "working"):
                self.carry({"type": "post", "stops": gig["stops"], "audience": gig["audience"], "schedule": gig["schedule"]}, gig["id"])
        self.requests = {e["request"]["id"]: e["request"] for e in history if e["kind"] == "price_request"}
        for req in self.requests.values():
            self.dealer_request_count[req["dealerId"]] += 1
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
                            
        self.late = set(_late_replay)
        for req_id, req in self.requests.items():
            pickup = req["legs"][0]["pickup"]["placeId"]
            drive = sum(self.geo.minutes(leg["pickup"]["placeId"], leg["delivery"]["placeId"]) for leg in req["legs"])
            if len(req["legs"]) == 2:
                drive += self.geo.minutes(req["legs"][0]["delivery"]["placeId"], req["legs"][1]["pickup"]["placeId"])
            if self.gate_supply.get(pickup, 0) < self.p.min_supply:
                pass_ext = self.p.ext_ring_min_supply > 0 and self.ext_supply.get(pickup, 0) >= self.p.ext_ring_min_supply and drive <= self.p.ext_ring_max_drive_min
                pass_hub = self.p.return_hub_min_supply > 0 and self.supply.get(req["legs"][-1]["delivery"]["placeId"], 0) >= self.p.return_hub_min_supply and drive <= self.p.return_hub_max_drive_min
                if pass_ext or pass_hub or self.p.return_offer_km <= 0:
                    self.ext_ring_reqs.add(req_id)
                else:
                    self.return_reqs.add(req_id)
            elif self.supply.get(pickup, 0) < self.p.min_supply and self.p.ring_to_hub_same_day_min > 0:
                if self.supply.get(req["legs"][-1]["delivery"]["placeId"], 0) >= 200 and drive <= self.p.ring_to_hub_same_day_min:
                    self.ring_hub_same_day.add(req_id)

        for e in history:
            if e["kind"] == "gig_viewed":
                self.last_view[e["driverId"]] = e["at"]
            elif e["kind"] == "offer_answered":
                self.offers_sent[(e["driverId"], e["at"] // DAY)] += 1
            elif e["kind"] == "gig_booked":
                self.gig_driver[e["gigId"]] = e["driverId"]
                self.gig_booked_at[e["gigId"]] = e["at"]
            elif e["kind"] in ("gig_dropped", "no_show"):
                self.clear_gig_tracking(e["gigId"])
            elif e["kind"] == "gig_started":
                self.gig_started_at[e["gigId"]] = e["at"]
            elif e["kind"] == "driver_late":
                self.gig_late_pickup[e["gigId"]] = e["pickupAt"]
            elif e["kind"] == "picked_up":
                self.gig_picked_up[(e["gigId"], e["orderId"], e["leg"])] = (e["at"], e["placeId"])
            elif e["kind"] == "delivered":
                self.gig_delivered_legs[(e["gigId"], e["orderId"], e["leg"])] = (e["at"], e["placeId"])
        self.orders = {o["id"]: o for o in snapshot["orders"] if o["id"] in self.requests and o["status"] != "cancelled"}
        for gig in sorted(snapshot["gigs"], key=lambda g: self.gig_booked_at.get(g["id"], g["postedAt"])):
            if gig["status"] in ("booked", "working") and gig["driverId"]:
                self.gig_driver[gig["id"]] = gig["driverId"]
                self.gig_booked_at.setdefault(gig["id"], gig["postedAt"])
                self.update_gig_deliveries(gig["id"])
            elif gig["status"] == "done":
                self.gig_completed_at.setdefault(gig["id"], gig["postedAt"])
        if self.p.return_offer_km > 0:
            for oid in self.return_reqs:
                if oid in self.orders:
                    self.return_wins_by_day[self.requests[oid]["respondBy"] // DAY] += 1
                    for gid in self.gigs_of(oid):
                        self.return_offer_gigs[gid] = oid
        for e in history:
            if e["kind"] == "gig_expired":
                g = gigs_by_id.get(e["gigId"])
                if g:
                    for s in g["stops"]:
                        self.lost.add(s["orderId"])
        for order_id, order in self.orders.items():
            if undelivered(order) and not self.staffed(order) and self.now > order["lastPickupAt"]:
                self.lost.add(order_id)
        for order_id, g_list in posted.items():
            if any(g["status"] == "withdrawn" for g in g_list):
                self.late_reposted.add(order_id)
        if self.p.drop_urgent_margin_min > 0:
            for e in history:
                if e["kind"] in ("gig_dropped", "no_show"):
                    post = self.posts.get(e["gigId"])
                    if post:
                        for order_id in dict.fromkeys(s["orderId"] for s in post["stops"]):
                            order = self.orders.get(order_id)
                            if order and order["lastPickupAt"] - e["at"] <= self.p.drop_urgent_margin_min:
                                self.urgent.add(order_id)
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
def next_open_minute(t: int, hours: Optional[OpeningHours]) -> int:
    if hours is None:
        return t
    cur = t
    for _ in range(10):
        day_start = (cur // DAY) * DAY
        wd = (cur // DAY) % 7
        tod = cur % DAY
        if wd in hours["weekdays"]:
            op, cl = hours["opens"], hours["closes"]
        elif wd == 5 and hours.get("saturday"):
            sat = hours["saturday"]
            op, cl = sat["opens"], sat["closes"]
        else:
            cur = day_start + DAY
            continue
        if tod < op:
            return day_start + op
        if tod <= cl:
            return cur
        cur = day_start + DAY
    return t


def add_business_days(t: int, days: int) -> int:
    d = t // DAY
    tod = t % DAY
    for _ in range(days):
        d += 1
        while d % 7 in (5, 6):
            d += 1
    return d * DAY + tod


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
