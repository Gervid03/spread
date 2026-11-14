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
    Action, ActionResult, Audience, DeskEvent, DeskSnapshot, DriverProfile, FeeStep, Gig, Order,
    OrderCancelledEvent, PostAction, PriceRequest, StopPlace, StopRef, TimeWindow,
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
    # --- hitch multi-car chain pairing & volume -----------------------------------------------------
    hitch: bool = False
    hitch_after_min: int = 20
    hitch_km: float = 15.0
    hitch_fee: float = 0.85
    hitch_patience_min: int = 30
    hitch_quote: bool = False
    hitch_cap_day: int = 6
    hitch_max_b_supply: int = 0       # 0 = any B pickup supply; > 0 restricts B pickup supply <= this
    hitch_min_saving_floor: bool = False  # if True, pair open fee >= max(open_A, open_B)
    hitch_max_splits: int = 2         # 0 = unlimited; > 0 caps failed pair splits per order
    hitch_homeward: bool = True       # avoid diverging chains that end much further from A's pickup than A's delivery
    hitch_preserve_age: bool = True   # resume rising schedule at car's first-posting age after a hitch split
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


class CarSpec(NamedTuple):
    """Timing and routing profile of a single-car candidate for hitch chain feasibility."""
    place_p: str
    place_d: str
    stop_p: StopPlace
    stop_d: StopPlace
    pick_from: int
    pick_to: int
    del_from: int
    del_to: int
    deadline: int
    drive_min: int
    extra_min: int
    supply_p: int


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
        self.single_open_since: dict[str, int] = {}  # open single-car gig id -> world minute it opened/reopened
        self.hitch_gigs: dict[str, dict[str, Any]] = {}  # hitch pair gig id -> metadata
        self.hitch_split_pairs: set[tuple[str, str]] = set()
        self.hitch_ever_paired: set[str] = set()
        self.hitch_booked_orders: set[str] = set()
        self.saved_retry: dict[tuple[str, int], Retry] = {}
        self.hitch_quote_reqs: set[str] = set()
        self.hitch_quote_partner: dict[str, str] = {}
        self.hitch_won_day: Counter = Counter()
        self.newly_won_hitch: list[str] = []
        self.hitch_order_splits: Counter = Counter()
        self.first_posted_at: dict[str, int] = {}
        self.lost: set[str] = set()                  # orders that can no longer be on time
        self.late_reposted: set[str] = set()         # orders already reposted in tick() upon becoming lost
        self.ends_at: int = 14280                    # second Wednesday 22:00

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
            if self.p.hitch:
                self.handle_cancelled_hitch(event)
            else:
                if self.p.lead_car:
                    self.withdraw(event["orderId"])
                self.leg_gigs.pop(event["orderId"], None)
        elif kind == "visit_failed":
            self.stats["visit_failed"] += 1
            self.stats[f"visit_failed_{event['reason']}"] += 1
            if self.p.hitch:
                gid = event["gigId"]
                if gid in self.hitch_gigs:
                    self.stats["hitch_visit_failed"] += 1
                    self.hitch_gigs.pop(gid, None)
                if gid in self.posts and len(order_ids_of(self.posts[gid])) > 1:
                    rem = [s for s in self.posts[gid]["stops"] if not (s["orderId"] == event["orderId"] and s["leg"] == event["leg"])]
                    if rem:
                        self.posts[gid] = {**self.posts[gid], "stops": rem}
                    else:
                        self.posts.pop(gid, None)
                        self.booked.discard(gid)
            self.retry(event["orderId"], event["leg"], event["reason"])
        elif kind == "gig_expired":
            self.stats["gig_expired"] += 1
            if self.p.hitch:
                self.single_open_since.pop(event["gigId"], None)
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
            self.stats["booked"] += 1
            if self.p.hitch:
                self.single_open_since.pop(gid, None)
                if gid in self.hitch_gigs:
                    info = self.hitch_gigs[gid]
                    self.stats["hitch_booked"] += 1
                    if info["thin_b"]:
                        self.stats["hitch_booked_thin_b"] += 1
                    if info["round_trip"]:
                        self.stats["hitch_booked_rt"] += 1
                    self.stats["hitch_booked_fee_cents"] += event["feeCents"]
                    self.stats["hitch_booked_single_open_cents"] += info["single_open_sum"]
                    self.stats["hitch_booked_single_ref_cents"] += info["single_ref_sum"]
                    self.hitch_booked_orders.update(info["orders"])
                elif gid in self.posts and len(order_ids_of(self.posts[gid])) > 1:
                    self.stats["lead_car_booked"] += 1
            else:
                if gid in self.posts and len(order_ids_of(self.posts[gid])) > 1:
                    self.stats["lead_car_booked"] += 1
            post = self.posts.get(event["gigId"])
            if post:
                order_ids = list(dict.fromkeys(s["orderId"] for s in post["stops"]))
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
            self.stats[kind] += 1
            if self.p.hitch:
                if gid in self.hitch_gigs:
                    self.stats["hitch_dropped"] += 1
                    info = self.hitch_gigs[gid]
                    info["unbooked_since"] = event["at"]
                    oids = info["orders"]
                    ok = all(oid in self.orders and oid not in self.urgent and undelivered(self.orders[oid]) == [0] for oid in oids)
                    if ok:
                        spec_a = self.car_spec_for_order(self.orders[oids[0]])
                        spec_b = self.car_spec_for_order(self.orders[oids[1]])
                        ok = spec_a is not None and spec_b is not None and self.chain_feasible(spec_a, spec_b, self.p.min_slack_min, self.now) is not None
                    if not ok:
                        self.split_hitch_gig(gid, reason="drop")
                elif gid in self.posts and len(self.posts[gid]["stops"]) == 2 and len(order_ids_of(self.posts[gid])) == 1:
                    self.single_open_since[gid] = event["at"]
            post = self.posts.get(event["gigId"])
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
            if self.p.hitch or self.p.hitch_quote:
                if line["kind"] == "driver_fee" and line.get("gigId") in self.hitch_gigs:
                    info = self.hitch_gigs[line["gigId"]]
                    self.stats["hitch_paid_gigs"] += 1
                    self.stats["hitch_paid_fee_cents"] += -line["cents"]
                    self.stats["hitch_paid_single_open_cents"] += info["single_open_sum"]
                    self.stats["hitch_paid_single_ref_cents"] += info["single_ref_sum"]
                if line.get("orderId") and line["orderId"] in self.hitch_quote_reqs:
                    self.stats["hitch_quote_margin_cents"] += line["cents"]
            if line["kind"] in ("late_refund", "undelivered_penalty") and line["orderId"]:
                if line["orderId"] not in self.late:
                    if is_ring:
                        self.stats["late_ring"] += 1
                    if order and order["option"] == "same_day" and line["orderId"] in self.ring_hub_same_day:
                        self.stats["late_ring_hub_same_day"] += 1
                    if is_ext_ring:
                        self.stats["late_ext_ring"] += 1
                    if self.p.hitch or self.p.hitch_quote:
                        if line["orderId"] in self.hitch_ever_paired:
                            self.stats["hitch_late"] += 1
                        if line["orderId"] in self.hitch_booked_orders:
                            self.stats["hitch_late_booked"] += 1
                        if line["orderId"] in self.hitch_quote_reqs:
                            self.stats["hitch_quote_late"] += 1
                self.late.add(line["orderId"])
                if dealer:
                    self.dealer_trust[dealer] //= 2
            elif line["kind"] == "revenue" and line["orderId"]:
                if dealer and line["orderId"] not in self.late:
                    if order and self.now <= order["deadline"]:
                        self.dealer_trust[dealer] = min(25, self.dealer_trust[dealer] + 1)
        elif kind == "offer_answered":
            self.stats[f"offer_{event['answer']}"] += 1
        elif kind == "delivered":
            self.leg_gigs.get(event["orderId"], {}).pop(event["leg"], None)
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
        if self.p.hitch and self.level >= 3:
            self.tick_hitch()

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
        pass_hitch = False
        hitch_partner_oid: Optional[str] = None
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
                if p.hitch_quote and self.level >= 3 and len(legs) == 1:
                    if self.hitch_won_day[self.now // DAY] < p.hitch_cap_day and self.hitch_cap_available():
                        pass_hitch = True
                    else:
                        self.stats["hitch_cap_blocked"] += 1
                if not pass_hitch:
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
        for option in request["options"]:
            ring_hub_sd = False
            if (pass_ext_ring or pass_return_hub or pass_hitch) and option["kind"] == "same_day":
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
            if pass_hitch:
                matched_oid = self.find_waiting_partner_for_request(request, option["deadline"], extra_days)
                if matched_oid is None:
                    continue
                hitch_partner_oid = matched_oid
            if ring_hub_sd:
                self.stats["quoted_ring_hub_same_day"] += 1
                self.ring_hub_same_day.add(request["id"])

            option_mult = mult
            if is_invest and slack >= 360:
                option_mult *= (1 - p.trust_invest)
            if p.return_hub_discount > 0 and pass_return_hub and not pass_ext_ring:
                option_mult *= (1.0 - p.return_hub_discount)

            price = option["listPriceCents"] * option_mult * (1 + p.same_day_markup if option["kind"] == "same_day" else 1)
            floor = fee / (1 - p.min_margin_frac)
            if price < floor:
                price, floored = floor, True
            prices[option["kind"]] = int(price + 0.5)
        if not prices:
            return {}, "decline"
        if pass_hitch:
            self.hitch_quote_reqs.add(request["id"])
            if hitch_partner_oid is not None:
                self.hitch_quote_partner[request["id"]] = hitch_partner_oid
            self.stats["hitch_quote_quoted"] += 1
        elif pass_ext_ring or pass_return_hub:
            self.ext_ring_reqs.add(request["id"])
            self.stats["quoted_ext_ring"] += 1
            if pass_return_hub:
                self.stats["quoted_return_hub"] += 1
        return prices, "floor" if floored else "quote"

    def learn(self, request_id: str, won: bool) -> None:
        """Moves the multiplier towards the price that wins `price_target_win` of the normal quotes."""
        if self.decided.get(request_id) != "quote":
            return
        if self.p.ext_ring_neutral_learn and (request_id in self.ext_ring_reqs or request_id in self.hitch_quote_reqs):
            if request_id in self.hitch_quote_reqs:
                self.stats["hitch_skipped_learn"] += 1
            else:
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
            if order["id"] in self.hitch_quote_reqs:
                self.hitch_won_day[self.now // DAY] += 1
                self.stats["hitch_quote_won"] += 1
            elif self.gate_supply.get(pickup, 0) < self.p.min_supply:
                self.stats["won_ext_ring"] += 1
                if self.p.return_hub_min_supply > 0 and self.supply.get(order["legs"][-1]["delivery"]["placeId"], 0) >= self.p.return_hub_min_supply:
                    self.stats["won_return_hub"] += 1
            self.stats[f"won_{order['option']}"] += 1
            if self.p.hitch:
                self.newly_won_hitch.append(order["id"])
            self.post(order, undelivered(order))

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
        if self.p.hitch and gig_id in self.hitch_gigs:
            info = self.hitch_gigs.pop(gig_id)
            if len(info["orders"]) == 2:
                a_id, b_id = info["orders"]
                self.hitch_split_pairs.add((min(a_id, b_id), max(a_id, b_id)))
            self.stats["hitch_split"] += 1
            self.stats["hitch_split_expired"] += 1
            if info["thin_b"]:
                self.stats["hitch_split_thin_b"] += 1
            for oid in oids:
                if oid in self.orders and undelivered(self.orders[oid]):
                    self.post_single_no_windows(self.orders[oid], undelivered(self.orders[oid]))
            return
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
                if self.p.hitch and gig_id in self.hitch_gigs:
                    self.split_hitch_gig(gig_id, reason="warn")
                else:
                    self.stats["lead_car_split"] += 1
                    self.outbox.append({"type": "withdraw", "gigId": gig_id})
                    self.single_open_since.pop(gig_id, None)
                    oids = order_ids_of(self.posts[gig_id])
                    for stop in self.posts[gig_id]["stops"]:
                        self.leg_gigs.get(stop["orderId"], {}).pop(stop["leg"], None)
                    for oid in oids:
                        if oid in self.orders and undelivered(self.orders[oid]):
                            self.post(self.orders[oid], undelivered(self.orders[oid]), self.saved_retry.get((oid, 0), Retry()) if self.p.hitch else Retry(), allow_pair=False)
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
        first_ord = self.orders.get(first["orderId"], order)
        pickup = first_ord["legs"][first["leg"]]["pickup"]["placeId"]
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
        oids = order_ids_of(post)
        if p.hitch and len(oids) > 1:
            ref_sum = sum(self.requests[oid]["referenceFeeCents"] for oid in oids if oid in self.requests)
            fee = int(ref_sum * p.offer_mult + 0.5)
        else:
            fee = int(self.requests[order["id"]]["referenceFeeCents"] * pickups(post) / len(order["legs"]) * p.offer_mult + 0.5)
        for _, _, driver_id in candidates[: min(3, p.offers_per_warning)]:
            self.outbox.append({"type": "offer", "gigId": gig_id, "driverId": driver_id, "feeCents": fee})
            self.offers_sent[(driver_id, day)] += 1
            self.stats["offers"] += 1

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
        if p.hub_multiday_fee_open > 0 and order["option"] != "same_day" and supply >= 150 and until - self.now >= 6 * HOUR:
            fee_open_override = p.hub_multiday_fee_open
            self.stats["hub_multiday_posts"] += 1
        elif p.thin_sameday_fee_open > 0 and order["option"] == "same_day" and supply < 65:
            fee_open_override = p.thin_sameday_fee_open
            self.stats["thin_sameday_posts"] += 1
        if (
            self.p.hitch
            and self.p.hitch_preserve_age
            and cars == 1
            and self.hitch_order_splits[order["id"]] > 0
            and order["id"] in self.first_posted_at
            and self.first_posted_at[order["id"]] < self.now
        ):
            return self.rising(base, until, fee_open_override=fee_open_override, first_at=self.first_posted_at[order["id"]])
        return self.rising(base, until, fee_open_override=fee_open_override)

    def rising(
        self,
        base: float,
        until: int,
        fee_open_override: Optional[float] = None,
        fee_warn_override: Optional[float] = None,
        first_at: Optional[int] = None,
    ) -> list[FeeStep]:
        """From `fee_open` now to `fee_warn` at `until`, in daytime steps only, at most 48 steps."""
        p = self.p
        fee_open = fee_open_override if fee_open_override is not None else p.fee_open
        fee_warn = fee_warn_override if fee_warn_override is not None else p.fee_warn
        if first_at is not None and first_at < self.now:
            tot_dt = max(1, daytime_minutes(first_at, until, p.day_start, p.day_end))
            elap_dt = clamp(daytime_minutes(first_at, self.now, p.day_start, p.day_end) / tot_dt, 0.0, 1.0)
            fee_open = fee_open + (fee_warn - fee_open) * elap_dt
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
            r = Retry(pickup_from, manual_licence=reason == "licence", plates=reason == "no_plates")
            if self.p.hitch:
                prev = self.saved_retry.get((order_id, leg), Retry())
                r = Retry(max(prev.pickup_from, r.pickup_from), prev.manual_licence or r.manual_licence, prev.plates or r.plates)
                self.saved_retry[(order_id, leg)] = r
                self.post(order, [leg], r, allow_pair=False)
                return
            self.post(order, [leg], r)

    # --- hitch chain pairing & volume -----------------------------------------------------------------
    def hitch_cap_available(self) -> bool:
        """Guards daily cap including a fraction of unanswered in-flight hitch quotes."""
        in_flight = sum(
            1
            for rid in self.hitch_quote_reqs
            if rid not in self.orders and rid not in self.lost_requests and self.now <= self.requests[rid]["respondBy"]
        )
        return self.hitch_won_day[self.now // DAY] + self.p.price_target_win * in_flight < self.p.hitch_cap_day + 0.35

    def car_spec_for_order(self, order: Order, retry: Optional[Retry] = None) -> Optional[CarSpec]:
        if len(order["legs"]) != 1 or undelivered(order) != [0]:
            return None
        req = self.requests.get(order["id"])
        if req is None:
            return None
        r = retry if retry is not None else self.saved_retry.get((order["id"], 0), Retry())
        flags = note_flags(req["note"], v2=self.p.notes_v2)
        r = r._replace(plates=r.plates or flags.plates)
        stops = stops_for(order, [0], req["note"], r, self.geo, self.p.charge_min_km, self.p.notes_v2, req["arrivedAt"])
        leg0 = order["legs"][0]
        pk_place = leg0["pickup"]["placeId"]
        dl_place = leg0["delivery"]["placeId"]
        pk_win = stops[0].get("window", leg0["pickup"]["window"])
        dl_base_to = max(leg0["delivery"]["window"]["from"], order["deadline"])
        dl_win = stops[1].get("window", {"from": leg0["delivery"]["window"]["from"], "to": dl_base_to})
        extra = (30 if stops[0].get("withPlates") else 0) + (40 if stops[0].get("withCharging") else 0)
        return CarSpec(
            place_p=pk_place,
            place_d=dl_place,
            stop_p=leg0["pickup"],
            stop_d=leg0["delivery"],
            pick_from=pk_win["from"],
            pick_to=pk_win["to"],
            del_from=dl_win["from"],
            del_to=dl_win["to"],
            deadline=order["deadline"],
            drive_min=self.geo.minutes(pk_place, dl_place),
            extra_min=extra,
            supply_p=self.supply.get(pk_place, 0),
        )

    def car_spec_for_request_option(self, request: PriceRequest, option_deadline: int, extra_days: int) -> Optional[CarSpec]:
        if len(request["legs"]) != 1:
            return None
        leg0 = request["legs"][0]
        pk_place = leg0["pickup"]["placeId"]
        dl_place = leg0["delivery"]["placeId"]
        pk_win = window_from_note(
            request["note"],
            leg0["pickup"]["window"],
            "pickup",
            v2=self.p.notes_v2,
            arrived_at=request["arrivedAt"],
            private_address=leg0["pickup"]["privateAddress"],
            stated_hours=leg0["pickup"]["hours"],
        )
        eff_dl = shift_business_days(option_deadline, extra_days) if self.p.notes_v2 else option_deadline
        dl_base: TimeWindow = {"from": leg0["delivery"]["window"]["from"], "to": max(leg0["delivery"]["window"]["from"], eff_dl)}
        dl_win = window_from_note(
            request["note"],
            dl_base,
            "delivery",
            v2=self.p.notes_v2,
            arrived_at=request["arrivedAt"],
            private_address=leg0["delivery"]["privateAddress"],
            stated_hours=leg0["delivery"]["hours"],
        )
        flags = note_flags(request["note"], v2=self.p.notes_v2)
        car = leg0["car"]
        low_battery = (
            car["electric"]
            and car["chargePercent"] is not None
            and car["chargePercent"] < 30
            and self.geo.road_km(pk_place, dl_place) > self.p.charge_min_km
        )
        extra = (30 if flags.plates else 0) + (40 if low_battery else 0)
        return CarSpec(
            place_p=pk_place,
            place_d=dl_place,
            stop_p=leg0["pickup"],
            stop_d=leg0["delivery"],
            pick_from=pk_win["from"],
            pick_to=max(pk_win["from"], pk_win["to"]),
            del_from=dl_win["from"],
            del_to=max(dl_win["from"], dl_win["to"]),
            deadline=eff_dl,
            drive_min=self.geo.minutes(pk_place, dl_place),
            extra_min=extra,
            supply_p=self.supply.get(pk_place, 0),
        )

    def chain_feasible(self, a: CarSpec, b: CarSpec, min_slack: int, now_at: int) -> Optional[tuple[int, int]]:
        """Checks A -> B chain: first pickup at >= supply end, B pickup <= hitch_km of A delivery,
        <= 12h road drive, B site open on arrival, and both A & B on time with `min_slack` to spare."""
        if a.supply_p < b.supply_p:
            return None
        if self.p.hitch_max_b_supply > 0 and b.supply_p > self.p.hitch_max_b_supply:
            return None
        if self.geo.line_km(a.place_d, b.place_p) > self.p.hitch_km:
            return None
        if self.p.hitch_homeward and self.geo.line_km(b.place_d, a.place_p) > max(60.0, self.geo.line_km(a.place_d, a.place_p) + 25.0):
            return None
        deadhead = self.geo.minutes(a.place_d, b.place_p)
        total_drive = a.drive_min + deadhead + b.drive_min
        if total_drive > 12 * HOUR:
            return None
        a_lim = min(a.deadline, a.del_to)
        b_lim = min(b.deadline, b.del_to)
        start_lo = max(now_at, a.pick_from)
        start_hi = min(
            a.pick_to,
            a_lim - a.drive_min - a.extra_min,
            b_lim - a.drive_min - a.extra_min - deadhead - b.drive_min - b.extra_min,
        )
        if start_hi < now_at + min_slack or start_hi < start_lo:
            return None

        t_last: Optional[int] = None
        valid_min = 0
        for d in range(start_hi // DAY, start_lo // DAY - 1, -1):
            if a.stop_p["privateAddress"] or a.stop_p["hours"] is None:
                d_lo = max(start_lo, d * DAY)
                d_hi = min(start_hi, (d + 1) * DAY - 1)
            else:
                h = a.stop_p["hours"]
                dow = d % 7
                if dow == 6:
                    continue
                if dow == 5:
                    sat = h["saturday"]
                    if sat is None:
                        continue
                    op, cl = sat["opens"], sat["closes"]
                elif dow in h["weekdays"]:
                    op, cl = h["opens"], h["closes"]
                else:
                    continue
                d_lo = max(start_lo, d * DAY + op)
                d_hi = min(start_hi, d * DAY + cl - 1)
            if d_hi < d_lo:
                continue

            t = d_hi
            while t >= d_lo:
                t_arr_da = t + a.drive_min + a.extra_min
                ok = t_arr_da <= a.del_to
                if ok:
                    if a.stop_d["privateAddress"] or a.stop_d["hours"] is None:
                        t_del_a = max(t_arr_da, a.del_from)
                        ok = t_del_a <= a_lim
                        t_leave_da = t_del_a
                    else:
                        t_del_a_opt = next_dealer_open_at(a.stop_d, t_arr_da, a_lim)
                        ok = t_del_a_opt is not None
                        t_leave_da = t_arr_da
                if ok:
                    t_arr_pb = t_leave_da + deadhead
                    ok = b.pick_from <= t_arr_pb <= b.pick_to and site_open_at(b.stop_p, t_arr_pb)
                if ok:
                    t_arr_db = t_arr_pb + b.drive_min + b.extra_min
                    ok = t_arr_db <= b.del_to
                    if ok:
                        if b.stop_d["privateAddress"] or b.stop_d["hours"] is None:
                            t_del_b = max(t_arr_db, b.del_from)
                            ok = t_del_b <= b_lim
                        else:
                            ok = next_dealer_open_at(b.stop_d, t_arr_db, b_lim) is not None
                if ok:
                    if t_last is None:
                        t_last = t
                        if t_last < now_at + min_slack:
                            return None
                    valid_min += min(5, t - d_lo + 1)
                    if valid_min >= min_slack:
                        return (t_last, total_drive)
                if t == d_lo:
                    break
                t = max(d_lo, t - 5)
        return None

    def waiting_single_orders(self) -> list[tuple[str, Optional[str]]]:
        """Open, unbooked single-car orders (order_id, gig_id or None if still in outbox)."""
        found: dict[str, Optional[str]] = {}
        for gig_id, action in self.posts.items():
            if gig_id in self.booked or len(action["stops"]) != 2:
                continue
            oid = action["stops"][0]["orderId"]
            if oid in self.urgent or self.leg_gigs.get(oid, {}).get(0) != gig_id:
                continue
            ord_obj = self.orders.get(oid)
            if ord_obj is not None and len(ord_obj["legs"]) == 1 and undelivered(ord_obj) == [0]:
                found[oid] = gig_id
        for action in self.outbox:
            if action["type"] == "post" and len(action["stops"]) == 2:
                oid = action["stops"][0]["orderId"]
                if oid not in found and oid not in self.urgent:
                    ord_obj = self.orders.get(oid)
                    if ord_obj is not None and len(ord_obj["legs"]) == 1 and undelivered(ord_obj) == [0]:
                        found[oid] = None
        return [(oid, found[oid]) for oid in sorted(found.keys())]

    def find_waiting_partner_for_request(self, request: PriceRequest, option_deadline: int, extra_days: int) -> Optional[str]:
        spec_r = self.car_spec_for_request_option(request, option_deadline, extra_days)
        if spec_r is None:
            return None
        eval_at = max(self.now, request["respondBy"])
        partner_loads: Counter = Counter()
        for rid, pid in self.hitch_quote_partner.items():
            if rid not in self.orders and rid not in self.lost_requests and self.now <= self.requests[rid]["respondBy"]:
                partner_loads[pid] += 1

        best: Optional[tuple[tuple[int, float, int, str], str]] = None
        for oid, _ in self.waiting_single_orders():
            if partner_loads[oid] >= 3:
                continue
            spec_o = self.car_spec_for_order(self.orders[oid])
            if spec_o is None:
                continue
            for a_spec, b_spec in ((spec_o, spec_r), (spec_r, spec_o)):
                res = self.chain_feasible(a_spec, b_spec, self.p.min_slack_min, eval_at)
                if res is not None:
                    _, tot_drv = res
                    rt = 0 if self.geo.line_km(b_spec.place_d, a_spec.place_p) <= 30.0 else 1
                    gap = self.geo.line_km(a_spec.place_d, b_spec.place_p)
                    key = (rt, gap, tot_drv, oid)
                    if best is None or key < best[0]:
                        best = (key, oid)
        return best[1] if best is not None else None

    def hitch_schedule(self, order_a: Order, order_b: Order) -> tuple[list[FeeStep], int, int]:
        ra = self.requests[order_a["id"]]["referenceFeeCents"]
        rb = self.requests[order_b["id"]]["referenceFeeCents"]
        open_a = max(1, int(ra * self.p.fee_open + 0.5))
        open_b = max(1, int(rb * self.p.fee_open + 0.5))
        single_open_sum = open_a + open_b
        ref_sum = ra + rb
        pair_open = max(1, int(self.p.hitch_fee * single_open_sum + 0.5))
        if self.p.hitch_min_saving_floor:
            pair_open = max(pair_open, open_a, open_b)
        if self.level == 1:
            return [{"at": self.now, "feeCents": pair_open}], single_open_sum, ref_sum
        until = min(order_a["lastPickupAt"], order_b["lastPickupAt"]) - 3 * HOUR
        sched = self.rising(ref_sum * self.p.hitch_fee, until)
        sched[0]["feeCents"] = pair_open
        for i in range(1, len(sched)):
            if sched[i]["feeCents"] < sched[i - 1]["feeCents"]:
                sched[i]["feeCents"] = sched[i - 1]["feeCents"]
        return sched, single_open_sum, ref_sum

    def stops_and_audience_for_single(self, order: Order, retry: Optional[Retry] = None) -> tuple[list[StopRef], Audience]:
        req = self.requests[order["id"]]
        note = req["note"]
        r = retry if retry is not None else self.saved_retry.get((order["id"], 0), Retry())
        flags = note_flags(note, v2=self.p.notes_v2)
        aud: Audience = {
            "experienced": any(leg["car"]["premium"] for leg in order["legs"]),
            "manualLicence": r.manual_licence or flags.manual,
        }
        r = r._replace(plates=r.plates or flags.plates)
        stops = without_windows(
            stops_for(order, [0], note, r, self.geo, self.p.charge_min_km, self.p.notes_v2, req["arrivedAt"]),
            self.now,
        )
        return stops, aud

    def post_single_no_windows(self, order: Order, legs: list[int]) -> None:
        stops, aud = self.stops_and_audience_for_single(order)
        stops = without_windows(stops, float("inf"))
        self.outbox.append({"type": "post", "stops": stops, "audience": aud, "schedule": self.fees_for(order, len(legs))})
        self.stats["posts"] += 1

    def rank_hitch_candidate(self, order_a: Order, spec_a: CarSpec, order_b: Order, spec_b: CarSpec, total_drive: int) -> tuple:
        id_a, id_b = order_a["id"], order_b["id"]
        pref = 0 if (self.hitch_quote_partner.get(id_b) == id_a or self.hitch_quote_partner.get(id_a) == id_b) else 1
        b_quote = 0 if id_b in self.hitch_quote_reqs else 1
        b_thin = 0 if spec_b.supply_p < self.p.min_supply else (1 if spec_b.supply_p < self.p.same_day_min_supply else 2)
        rt = 0 if self.geo.line_km(spec_b.place_d, spec_a.place_p) <= 30.0 else 1
        gap = round(self.geo.line_km(spec_a.place_d, spec_b.place_p), 3)
        return (pref, b_quote, b_thin, rt, gap, total_drive, id_a, id_b)

    def record_hitch_gig(self, gig_id: str, order_a: Order, spec_a: CarSpec, order_b: Order, spec_b: CarSpec,
                         single_open_sum: int, ref_sum: int, posted_at: Optional[int] = None,
                         unbooked_since: Optional[int] = None, count_stats: bool = True) -> None:
        t_post = self.now if posted_at is None else posted_at
        t_unb = t_post if unbooked_since is None else unbooked_since
        thin_b = spec_b.supply_p < self.p.min_supply
        rt = self.geo.line_km(spec_b.place_d, spec_a.place_p) <= 30.0
        self.hitch_gigs[gig_id] = {
            "posted_at": t_post,
            "unbooked_since": t_unb,
            "orders": [order_a["id"], order_b["id"]],
            "single_open_sum": single_open_sum,
            "single_ref_sum": ref_sum,
            "thin_b": thin_b,
            "round_trip": rt,
        }
        self.hitch_ever_paired.update([order_a["id"], order_b["id"]])
        if count_stats:
            self.stats["hitch_posted"] += 1
            if thin_b:
                self.stats["hitch_posted_thin_b"] += 1
            if rt:
                self.stats["hitch_posted_rt"] += 1
            if order_a["id"] in self.hitch_quote_reqs or order_b["id"] in self.hitch_quote_reqs:
                self.stats["hitch_quote_paired"] += 1

    def split_hitch_gig(self, gig_id: str, reason: str) -> None:
        info = self.hitch_gigs.pop(gig_id, None)
        if info is None or gig_id in self.booked:
            return
        oids = info["orders"]
        if len(oids) == 2:
            self.hitch_split_pairs.add((min(oids[0], oids[1]), max(oids[0], oids[1])))
        for oid in oids:
            self.hitch_order_splits[oid] += 1
        self.stats["hitch_split"] += 1
        self.stats[f"hitch_split_{reason}"] += 1
        if info["thin_b"]:
            self.stats["hitch_split_thin_b"] += 1
        self.outbox.append({"type": "withdraw", "gigId": gig_id})
        post = self.posts.get(gig_id)
        if post is not None:
            for stop in post["stops"]:
                if self.leg_gigs.get(stop["orderId"], {}).get(stop["leg"]) == gig_id:
                    self.leg_gigs[stop["orderId"]].pop(stop["leg"], None)
        for oid in oids:
            if oid in self.orders and undelivered(self.orders[oid]) and not self.gigs_of(oid):
                self.post(self.orders[oid], undelivered(self.orders[oid]), self.saved_retry.get((oid, 0), Retry()), allow_pair=False)

    def can_order_hitch(self, oid: str) -> bool:
        if oid in self.urgent or oid not in self.orders:
            return False
        if self.p.hitch_max_splits > 0 and self.hitch_order_splits[oid] >= self.p.hitch_max_splits:
            return False
        ord_obj = self.orders[oid]
        return len(ord_obj["legs"]) == 1 and undelivered(ord_obj) == [0]

    def tick_hitch(self) -> None:
        p = self.p
        newly_won = list(dict.fromkeys(self.newly_won_hitch))
        self.newly_won_hitch.clear()

        # 1. Split unbooked hitch pairs past hitch_patience_min daytime minutes
        for gig_id in sorted(list(self.hitch_gigs.keys())):
            if gig_id in self.booked:
                continue
            info = self.hitch_gigs.get(gig_id)
            if info is not None and daytime_minutes(info["unbooked_since"], self.now, p.day_start, p.day_end) >= p.hitch_patience_min:
                self.split_hitch_gig(gig_id, reason="patience")

        # 2. Build open single-car pool (both already-posted unbooked single gigs and unsent single posts in outbox)
        open_pool: dict[str, Optional[str]] = {}
        for gig_id in sorted(self.posts.keys()):
            action = self.posts[gig_id]
            if gig_id in self.booked or len(action["stops"]) != 2:
                continue
            oid = action["stops"][0]["orderId"]
            if self.leg_gigs.get(oid, {}).get(0) == gig_id and self.can_order_hitch(oid):
                open_pool[oid] = gig_id
        for a in self.outbox:
            if a["type"] == "post" and len(a["stops"]) == 2 and len(order_ids_of(a)) == 1:
                oid = a["stops"][0]["orderId"]
                if oid not in open_pool and self.can_order_hitch(oid):
                    open_pool[oid] = None

        if len(open_pool) < 2:
            return

        aged_oids = [
            self.posts[gid]["stops"][0]["orderId"]
            for gid, since in sorted(self.single_open_since.items())
            if gid not in self.booked
            and gid in self.posts
            and len(self.posts[gid]["stops"]) == 2
            and daytime_minutes(since, self.now, p.day_start, p.day_end) >= p.hitch_after_min
        ]
        triggers_raw = [oid for oid in newly_won + aged_oids if oid in open_pool]
        if not triggers_raw:
            return
        triggers = sorted(dict.fromkeys(triggers_raw), key=lambda oid: (0 if oid in self.hitch_quote_reqs else 1, oid))

        specs: dict[str, CarSpec] = {}
        for oid in list(open_pool.keys()):
            sp = self.car_spec_for_order(self.orders[oid])
            if sp is None:
                open_pool.pop(oid, None)
            else:
                specs[oid] = sp

        pending_pairs: list[tuple[Order, CarSpec, Order, CarSpec, int, int]] = []
        removed_unsent_oids: set[str] = set()

        for oid1 in triggers:
            if oid1 not in open_pool:
                continue
            ord1, spec1 = self.orders[oid1], specs[oid1]
            best: Optional[tuple[tuple, str, Order, CarSpec, Order, CarSpec]] = None
            for oid2 in sorted(open_pool.keys()):
                if oid2 == oid1:
                    continue
                if (min(oid1, oid2), max(oid1, oid2)) in self.hitch_split_pairs:
                    continue
                ord2, spec2 = self.orders[oid2], specs[oid2]
                for ord_a, sp_a, ord_b, sp_b in ((ord1, spec1, ord2, spec2), (ord2, spec2, ord1, spec1)):
                    res = self.chain_feasible(sp_a, sp_b, p.min_slack_min, self.now)
                    if res is not None:
                        _, tot_drv = res
                        rk = self.rank_hitch_candidate(ord_a, sp_a, ord_b, sp_b, tot_drv)
                        if best is None or rk < best[0]:
                            best = (rk, oid2, ord_a, sp_a, ord_b, sp_b)

            if best is None:
                continue
            _, oid2, ord_a, sp_a, ord_b, sp_b = best
            gid1 = open_pool.pop(oid1)
            gid2 = open_pool.pop(oid2)
            for x_oid, x_gid in ((oid1, gid1), (oid2, gid2)):
                if x_gid is not None:
                    self.single_open_since.pop(x_gid, None)
                    self.leg_gigs.get(x_oid, {}).pop(0, None)
                    self.outbox.append({"type": "withdraw", "gigId": x_gid})
                else:
                    removed_unsent_oids.add(x_oid)

            stops_a, aud_a = self.stops_and_audience_for_single(ord_a)
            stops_b, aud_b = self.stops_and_audience_for_single(ord_b)
            audience: Audience = {
                "experienced": aud_a["experienced"] or aud_b["experienced"],
                "manualLicence": aud_a["manualLicence"] or aud_b["manualLicence"],
            }
            sched, single_open_sum, ref_sum = self.hitch_schedule(ord_a, ord_b)
            post_action: PostAction = {"type": "post", "stops": stops_a + stops_b, "audience": audience, "schedule": sched}
            self.outbox.append(post_action)
            self.stats["posts"] += 1
            pending_pairs.append((ord_a, sp_a, ord_b, sp_b, single_open_sum, ref_sum))

        if removed_unsent_oids:
            filtered: list[Action] = []
            for a in self.outbox:
                if a["type"] == "post" and len(a["stops"]) == 2 and len(order_ids_of(a)) == 1 and a["stops"][0]["orderId"] in removed_unsent_oids:
                    self.stats["posts"] -= 1
                else:
                    filtered.append(a)
            self.outbox = filtered

        if pending_pairs:
            self.send()
            for ord_a, sp_a, ord_b, sp_b, single_open_sum, ref_sum in pending_pairs:
                pair_gids = self.gigs_of(ord_a["id"])
                if not pair_gids:
                    self.hitch_split_pairs.add((min(ord_a["id"], ord_b["id"]), max(ord_a["id"], ord_b["id"])))
                    self.post(ord_a, undelivered(ord_a), self.saved_retry.get((ord_a["id"], 0), Retry()), allow_pair=False)
                    self.post(ord_b, undelivered(ord_b), self.saved_retry.get((ord_b["id"], 0), Retry()), allow_pair=False)
                else:
                    self.record_hitch_gig(pair_gids[0], ord_a, sp_a, ord_b, sp_b, single_open_sum, ref_sum)

    def handle_cancelled_hitch(self, event: OrderCancelledEvent) -> None:
        oid = event["orderId"]
        # Remove any unsent post in outbox referencing the cancelled order
        kept_outbox: list[Action] = []
        orphan_oids: list[str] = []
        for a in self.outbox:
            if a["type"] == "post" and any(s["orderId"] == oid for s in a["stops"]):
                for other_id in order_ids_of(a):
                    if other_id != oid:
                        orphan_oids.append(other_id)
            else:
                kept_outbox.append(a)
        self.outbox = kept_outbox
        self.leg_gigs.pop(oid, None)

        for cg in event["gigs"]:
            gid = cg["gigId"]
            outcome = cg["outcome"]
            post = self.posts.get(gid)
            was_hitch = gid in self.hitch_gigs
            if outcome == "withdrawn":
                self.booked.discard(gid)
                self.single_open_since.pop(gid, None)
                self.hitch_gigs.pop(gid, None)
                if was_hitch:
                    self.stats["hitch_cancelled_withdrawn"] += 1
                if post is not None:
                    other_oids = [x for x in order_ids_of(post) if x != oid]
                    self.posts.pop(gid, None)
                    for other_id in other_oids:
                        for lk, gv in list(self.leg_gigs.get(other_id, {}).items()):
                            if gv == gid:
                                self.leg_gigs[other_id].pop(lk, None)
                        orphan_oids.append(other_id)
            elif outcome == "released":
                self.booked.discard(gid)
                self.single_open_since.pop(gid, None)
                self.hitch_gigs.pop(gid, None)
                self.posts.pop(gid, None)
            elif outcome in ("shortened", "continues"):
                if was_hitch:
                    self.stats[f"hitch_cancelled_{outcome}"] += 1
                self.hitch_gigs.pop(gid, None)
                if post is not None:
                    rem_stops = [s for s in post["stops"] if s["orderId"] != oid]
                    self.posts[gid] = {**post, "stops": rem_stops}
                    if gid not in self.booked and len(rem_stops) == 2 and len(order_ids_of(self.posts[gid])) == 1:
                        self.single_open_since[gid] = event["at"]

        for other_id in dict.fromkeys(orphan_oids):
            if other_id in self.orders and undelivered(self.orders[other_id]) and not self.gigs_of(other_id):
                self.post(self.orders[other_id], undelivered(self.orders[other_id]), self.saved_retry.get((other_id, 0), Retry()), allow_pair=False)

    def rejoin_hitch(self, snapshot: DeskSnapshot, history: list[DeskEvent]) -> None:
        p = self.p
        drop_times: dict[str, int] = {}
        booked_ever: set[str] = set()
        for e in history:
            if e["kind"] in ("gig_dropped", "no_show"):
                drop_times[e["gigId"]] = e["at"]
            elif e["kind"] == "gig_booked":
                booked_ever.add(e["gigId"])
            elif e["kind"] == "visit_failed":
                prev = self.saved_retry.get((e["orderId"], e["leg"]), Retry())
                ord_obj = self.orders.get(e["orderId"])
                req_obj = self.requests.get(e["orderId"])
                p_from = retry_from(ord_obj, req_obj, e["leg"], e["at"]) if (ord_obj and req_obj and e["reason"] in ("not_ready", "closed")) else 0
                self.saved_retry[(e["orderId"], e["leg"])] = Retry(
                    max(prev.pickup_from, p_from),
                    prev.manual_licence or (e["reason"] == "licence"),
                    prev.plates or (e["reason"] == "no_plates"),
                )

        if p.hitch_quote:
            for e in history:
                if e["kind"] == "order_won":
                    oid = e["order"]["id"]
                    req = self.requests.get(oid)
                    if req is not None and len(req["legs"]) == 1:
                        pk = req["legs"][0]["pickup"]["placeId"]
                        dlv = req["legs"][-1]["delivery"]["placeId"]
                        drv = self.geo.minutes(pk, dlv)
                        if self.gate_supply.get(pk, 0) < p.min_supply:
                            ext_ok = p.ext_ring_min_supply > 0 and self.ext_supply.get(pk, 0) >= p.ext_ring_min_supply and drv <= p.ext_ring_max_drive_min
                            ret_ok = p.return_hub_min_supply > 0 and self.supply.get(dlv, 0) >= p.return_hub_min_supply and drv <= p.return_hub_max_drive_min
                            if not (ext_ok or ret_ok):
                                self.hitch_quote_reqs.add(oid)
                                self.hitch_won_day[e["at"] // DAY] += 1

        if not p.hitch:
            return

        self.single_open_since.clear()
        for gig in snapshot["gigs"]:
            gid = gig["id"]
            oids = order_ids_of(gig)
            for oid in oids:
                if oid not in self.first_posted_at or gig["postedAt"] < self.first_posted_at[oid]:
                    self.first_posted_at[oid] = gig["postedAt"]
            last_open = max(gig["postedAt"], drop_times.get(gid, gig["postedAt"]))
            if len(oids) == 1 and len(gig["stops"]) == 2 and gig["status"] == "open":
                self.single_open_since[gid] = last_open
            elif len(oids) == 2:
                oa = self.orders.get(oids[0])
                ob = self.orders.get(oids[1])
                ra = self.requests.get(oids[0])
                rb = self.requests.get(oids[1])
                if ra is None or rb is None:
                    continue
                da = ra["legs"][-1]["delivery"]["placeId"]
                pb = rb["legs"][0]["pickup"]["placeId"]
                is_hitch_pair = self.geo.line_km(da, pb) <= p.hitch_km
                if p.lead_car and gig["schedule"]:
                    ref_sum = ra["referenceFeeCents"] + rb["referenceFeeCents"]
                    lead_open = int(ref_sum * p.lead_car_fee_mult * p.fee_open + 0.5)
                    hitch_open = int(ref_sum * p.hitch_fee * p.fee_open + 0.5)
                    if abs(gig["schedule"][0]["feeCents"] - hitch_open) < abs(gig["schedule"][0]["feeCents"] - lead_open):
                        is_hitch_pair = True
                    elif abs(gig["schedule"][0]["feeCents"] - hitch_open) > abs(gig["schedule"][0]["feeCents"] - lead_open):
                        is_hitch_pair = False
                if not is_hitch_pair:
                    continue
                self.hitch_ever_paired.update(oids)
                if gid in booked_ever:
                    self.hitch_booked_orders.update(oids)
                if gig["status"] == "withdrawn":
                    self.hitch_split_pairs.add((min(oids[0], oids[1]), max(oids[0], oids[1])))
                    for oid in oids:
                        self.hitch_order_splits[oid] += 1
                elif gig["status"] in ("open", "booked", "working") and oa is not None and ob is not None:
                    single_open_sum = int(ra["referenceFeeCents"] * p.fee_open + 0.5) + int(rb["referenceFeeCents"] * p.fee_open + 0.5)
                    ref_sum = ra["referenceFeeCents"] + rb["referenceFeeCents"]
                    thin_b = self.supply.get(pb, 0) < p.min_supply
                    rt = self.geo.line_km(rb["legs"][-1]["delivery"]["placeId"], ra["legs"][0]["pickup"]["placeId"]) <= 30.0
                    self.hitch_gigs[gid] = {
                        "posted_at": gig["postedAt"],
                        "unbooked_since": last_open,
                        "orders": oids,
                        "single_open_sum": single_open_sum,
                        "single_ref_sum": ref_sum,
                        "thin_b": thin_b,
                        "round_trip": rt,
                    }

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
        self.single_open_since.pop(gig_id, None)
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
        if allow_pair and self.p.lead_car and order["id"] not in self.hitch_quote_reqs and self.try_pair_lead_car(order, legs, retry):
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
            if self.p.hitch and stop["orderId"] not in self.first_posted_at:
                self.first_posted_at[stop["orderId"]] = self.now
        self.posts[gig_id] = action
        if self.p.hitch and gig_id not in self.booked and len(action["stops"]) == 2 and len(order_ids_of(action)) == 1:
            self.single_open_since[gig_id] = self.now

    def withdraw(self, order_id: str) -> bool:
        self.send_post_of(order_id)
        gigs = self.gigs_of(order_id)
        if any(gig_id in self.booked for gig_id in gigs):
            return False
        self.leg_gigs.pop(order_id, None)
        self.outbox += [{"type": "withdraw", "gigId": gig_id} for gig_id in gigs]
        for gig_id in gigs:
            self.single_open_since.pop(gig_id, None)
            if gig_id in self.posts and len(order_ids_of(self.posts[gig_id])) > 1:
                if self.p.hitch and gig_id in self.hitch_gigs:
                    info = self.hitch_gigs.pop(gig_id)
                    if len(info["orders"]) == 2:
                        self.hitch_split_pairs.add((min(info["orders"][0], info["orders"][1]), max(info["orders"][0], info["orders"][1])))
                    self.stats["hitch_split"] += 1
                    self.stats["hitch_split_change"] += 1
                    if info["thin_b"]:
                        self.stats["hitch_split_thin_b"] += 1
                else:
                    self.stats["lead_car_split"] += 1
                for oid in order_ids_of(self.posts[gig_id]):
                    if oid != order_id and oid in self.orders:
                        self.leg_gigs.pop(oid, None)
                        if undelivered(self.orders[oid]):
                            self.post(self.orders[oid], undelivered(self.orders[oid]), self.saved_retry.get((oid, 0), Retry()) if self.p.hitch else Retry(), allow_pair=False)
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
            if self.gate_supply.get(pickup, 0) < self.p.min_supply:
                self.ext_ring_reqs.add(req_id)
            elif self.supply.get(pickup, 0) < self.p.min_supply and self.p.ring_to_hub_same_day_min > 0:
                drive = sum(self.geo.minutes(leg["pickup"]["placeId"], leg["delivery"]["placeId"]) for leg in req["legs"])
                if len(req["legs"]) == 2:
                    drive += self.geo.minutes(req["legs"][0]["delivery"]["placeId"], req["legs"][1]["pickup"]["placeId"])
                if self.supply.get(req["legs"][-1]["delivery"]["placeId"], 0) >= 200 and drive <= self.p.ring_to_hub_same_day_min:
                    self.ring_hub_same_day.add(req_id)

        for e in history:
            if e["kind"] == "gig_viewed":
                self.last_view[e["driverId"]] = e["at"]
            elif e["kind"] == "offer_answered":
                self.offers_sent[(e["driverId"], e["at"] // DAY)] += 1
        self.orders = {o["id"]: o for o in snapshot["orders"] if o["id"] in self.requests and o["status"] != "cancelled"}
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
        if self.p.hitch or self.p.hitch_quote:
            self.rejoin_hitch(snapshot, history)
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
def daytime_minutes(t0: int, t1: int, day_start: int, day_end: int) -> int:
    if t1 <= t0:
        return 0
    total = 0
    for d in range(t0 // DAY, t1 // DAY + 1):
        a = max(t0, d * DAY + day_start)
        b = min(t1, d * DAY + day_end)
        if b > a:
            total += b - a
    return total


def site_open_at(stop_place: StopPlace, t: int) -> bool:
    if stop_place["privateAddress"] or stop_place["hours"] is None:
        w = stop_place["window"]
        return w["from"] <= t <= w["to"]
    h = stop_place["hours"]
    dow = (t // DAY) % 7
    tod = t % DAY
    if dow == 6:
        return False
    if dow == 5:
        sat = h["saturday"]
        return sat is not None and sat["opens"] <= tod < sat["closes"]
    return dow in h["weekdays"] and h["opens"] <= tod < h["closes"]


def next_dealer_open_at(stop_place: StopPlace, t: int, limit_t: int) -> Optional[int]:
    if site_open_at(stop_place, t):
        return t
    if stop_place["privateAddress"] or stop_place["hours"] is None:
        w = stop_place["window"]
        return w["from"] if t < w["from"] <= limit_t else None
    h = stop_place["hours"]
    for d in range(t // DAY, limit_t // DAY + 1):
        dow = d % 7
        if dow == 6:
            continue
        if dow == 5:
            sat = h["saturday"]
            if sat is None:
                continue
            op, cl = sat["opens"], sat["closes"]
        elif dow in h["weekdays"]:
            op, cl = h["opens"], h["closes"]
        else:
            continue
        cand = d * DAY + op
        if cand <= t:
            if t < d * DAY + cl:
                return t if t <= limit_t else None
            continue
        return cand if cand <= limit_t else None
    return None
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
