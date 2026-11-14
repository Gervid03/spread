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
    fee_curve_power: float = 1.0      # 1.0 = linear rising(); > 1.0 = convex curve (gentle early, steep near warning)
    max_rise_per_step: float = 0.0    # if > 0, cap pre-warning rise per step so short spans do not jump straight to fee_warn
    inbound_hub_fee_open: float = 0.0 # if > 0, opening fee when delivery town has >= 150 drivers and >= 2h to warning
    urgent_hygiene: bool = False      # clear stale urgent on order_changed, daytime-only steep(), and in-place late reprice
    late_reprice_grace_min: int = 0   # extra minutes past nominal lastPickupAt before repricing unbooked gig to late_fee_open
    drop_reprice_bump: float = -1.0   # if >= 0, reprice non-urgent dropped gigs to last_booked_mult + bump instead of stale high schedule
    # --- direct offers after the deadline warning (and proactive viewer/homeward offers) ------------
    offers_per_warning: int = 0       # at most 3 open offers per gig, 3 per driver per day (rules) (v2: was 3; 3 of 218 offers were accepted)
    offer_mult: float = 2.20          # offer fee, times the typical fee of the cars
    offer_recent_view_min: int = 240  # drivers who viewed one of our gigs this recently go first
    dest_offer_mult: float = 0.0      # if > 0, direct offer mult to active drivers living within dest_offer_km of delivery
    dest_offer_delay_min: int = 10    # minutes unbooked before sending delivery-home direct offers
    dest_offer_km: float = 30.0       # max home-to-delivery straight-line km for delivery-home direct offers
    view_offer_mult: float = 0.0      # if > 0, direct offer mult (x current board fee) to local/dest viewers holding out
    view_offer_after_min: int = 15    # gig age in minutes before answering non-booking local/dest views with an offer
    view_offer_window_min: int = 15   # max minutes since gig_viewed to still answer with a direct offer
    view_offer_cap: float = 1.12      # max direct offer fee multiple (x typical fee) for view_offer_mult
    # --- lead-car multi-car gig pairing & posting order ---------------------------------------------
    lead_car: bool = False
    lead_car_max_gap_km: float = 0.0
    lead_car_max_deliv_gap_km: float = 25.0
    lead_car_fee_mult: float = 1.00
    chain_pair_km: float = 0.0        # if > 0, allow round-trip/homeward A->B chains in try_pair_lead_car within this deadhead km
    chain_pair_fee_mult: float = 0.85 # base fee multiplier on sum(referenceFeeCents) for round-trip chain pairs
    chain_patience_min: int = 30      # split unbooked chain_pair back into solo gigs after this many daytime minutes
    post_priority: bool = False       # sort outgoing posts so multi-car and tight/same_day gigs post before loose multi-day gigs
    defer_multiday_min: int = 0       # if > 0, hold new loose multi-day posts up to this many min while a local urgent/same_day gig is unbooked
    # --- hitch multi-car chain pairing & volume (stage 1: unbooked outbound) ------------------------
    hitch: bool = False
    hitch_after_min: int = 20
    hitch_km: float = 15.0
    hitch_fee: float = 0.85
    hitch_non_rt_fee: float = 0.0     # 0 = use hitch_fee; > 0 = pair open mult when B.delivery > 30km from A.pickup
    hitch_patience_min: int = 30
    hitch_quote: bool = False
    hitch_cap_day: int = 6
    hitch_max_b_supply: int = 0       # 0 = any B pickup supply; > 0 restricts B pickup supply <= this
    hitch_min_saving_floor: bool = False  # if True, pair open fee >= max(open_A, open_B)
    hitch_max_splits: int = 2         # 0 = unlimited; > 0 caps failed pair splits per order
    hitch_homeward: bool = True       # avoid diverging chains that end much further from A's pickup than A's delivery
    hitch_homeward_ratio: float = 0.0 # if > 0, require line_km(B.d, A.p) <= max(60, ratio * line_km(A.d, A.p))
    hitch_max_return_km: float = 0.0  # if > 0, require line_km(B.d, A.p) <= this (round-trip / home-ring pairs only)
    hitch_min_deliv_supply: int = 0   # if > 0, require supply[B.d] >= this or line_km(B.d, A.p) <= 55km
    hitch_preserve_age: bool = True   # resume rising schedule at car's first-posting age after a hitch split
    hitch_thin_solo_open: float = 0.0 # if > 0, solo posts of hitch_quote orders open at >= this x typical fee
    # --- return offers to our own finishing drivers (stage 2: booked outbound) ----------------------
    return_offer_km: float = 0.0      # 0 = off; quote thin slow requests within this km of our booked deliveries
    return_markup: float = 0.0        # price = tracker price * (1 + return_markup)
    return_cap_day: int = 8           # max return-offer wins per day
    return_fee_open: float = 0.75     # opening board fee x typical fee for return-offer gigs
    return_offer_mult: float = 0.90   # direct offer fee x typical fee sent to the outbound driver
    return_offer_lead_min: int = 45   # send offer this many min before planned outbound delivery
    return_offer_on_win: bool = False # also send a daytime offer on order_won while driver holds outbound gig
    return_toward_home: bool = False  # only match outbound drivers for whom delivery moves closer to home (or <=30km)
    return_min_deliv_supply: int = 0  # if > 0, require delivery 30km supply >= this (or <=30km of outbound driver home)
    return_max_wait_min: int = 0      # if > 0, max wait minutes from planned outbound delivery to return pickup
    chain_guard_target: float = 0.0   # if > 0, pause thin chain intake (hitch_quote/return_offer) when projected_on_time < this
    chain_max_urgent: int = 0         # if > 0, pause thin chain intake when active unstaffed urgent orders >= this
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
    """Geometry and timing constraints of a 1-leg car for hitch pairing."""
    oid: str
    place_p: str
    place_d: str
    pickup_sp: StopPlace
    delivery_sp: StopPlace
    pk_from: int
    pk_to: int
    dl_from: int
    dl_to: int
    deadline: int
    drive: int
    extra_pickup_min: int


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
        self.late_repriced: set[str] = set()         # orders already repriced in place upon becoming lost
        self.last_booked_fee: dict[str, int] = {}    # gig id -> last booked feeCents before a drop
        self.booked_driver: dict[str, str] = {}      # gig id -> driver id currently holding/working it
        self.gig_posted_at: dict[str, int] = {}      # gig id -> minute posted
        self.open_offers: dict[tuple[str, str], str] = {}  # (gig id, driver id) -> kind ("dest" | "view")
        self.offered_pairs: set[tuple[str, str]] = set()   # (gig id, driver id) already offered
        self.dest_offered_gigs: set[str] = set()     # gig ids already evaluated for dest_offer_mult
        self.recent_views: list[tuple[int, str, str]] = [] # (at, gig id, driver id)
        self.deferred_orders: dict[str, int] = {}    # order id -> minute deferred
        self.chain_pairs: dict[str, int] = {}        # gig id -> minute paired via chain_pair_km
        self.chain_split_orders: Counter = Counter() # order id -> times split from chain_pair
        self.ends_at: int = 14280                    # second Wednesday 22:00
        # --- hitch pairing & thin-quote state (stage 1) ---------------------------------------------
        self.single_open_since: dict[str, int] = {}
        self.hitch_gigs: dict[str, dict[str, Any]] = {}
        self.hitch_split_pairs: set[tuple[str, str]] = set()
        self.hitch_order_splits: Counter = Counter()
        self.hitch_ever_paired: set[str] = set()
        self.hitch_booked_orders: set[str] = set()
        self.hitch_quote_reqs: set[str] = set()
        self.hitch_quote_matched: dict[str, str] = {}
        self.hitch_won_day: Counter = Counter()
        self.hitch_newly_won: set[str] = set()
        self.saved_retry: dict[tuple[str, int], Retry] = {}
        self.first_posted_at: dict[str, int] = {}
        # --- return-offer state (stage 2: booked inbound deliveries) --------------------------------
        self.return_reqs: set[str] = set()
        self.return_targets: dict[str, tuple[str, str]] = {}  # req/order id -> (driver_id, outbound_gig_id)
        self.return_wins_by_day: Counter = Counter()
        self.return_offered_orders: set[str] = set()
        self.return_sent_stage: set[tuple[str, str, str]] = set()
        self.return_declined_orders: set[tuple[str, str]] = set()
        self.return_offer_gigs: dict[str, str] = {}           # gig_id -> order_id
        self.return_gone_home_counted: set[str] = set()
        self.open_gig_offers: dict[str, set[str]] = defaultdict(set)
        self.gig_driver: dict[str, str] = {}
        self.gig_booked_at: dict[str, int] = {}
        self.gig_started_at: dict[str, int] = {}
        self.gig_late_pickup: dict[str, int] = {}
        self.gig_picked_up: dict[tuple[str, str, int], tuple[int, str]] = {}
        self.gig_delivered_legs: dict[tuple[str, str, int], tuple[int, str]] = {}
        self.gig_completed_at: dict[str, int] = {}
        self.booked_deliveries: dict[str, list[dict[str, Any]]] = {}

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
            if self.p.return_offer_km > 0:
                for gid in list(self.booked_deliveries):
                    if any(e["order_id"] == event["order"]["id"] for e in self.booked_deliveries[gid]):
                        self.update_gig_deliveries(gid)
        elif kind == "order_cancelled":
            self.deferred_orders.pop(event["orderId"], None)
            if self.p.hitch:
                self.handle_cancelled_hitch(event)
            else:
                self.orders.pop(event["orderId"], None)
                if self.p.lead_car:
                    self.withdraw(event["orderId"])
                self.leg_gigs.pop(event["orderId"], None)
            if self.p.return_offer_km > 0:
                for cg in event["gigs"]:
                    gid = cg["gigId"]
                    if cg["outcome"] in ("withdrawn", "released"):
                        self.clear_gig_tracking(gid)
                    else:
                        self.update_gig_deliveries(gid)
        elif kind == "visit_failed":
            self.stats["visit_failed"] += 1
            self.stats[f"visit_failed_{event['reason']}"] += 1
            if self.p.hitch:
                prev = self.saved_retry.get((event["orderId"], event["leg"]), Retry())
                ord_obj = self.orders.get(event["orderId"])
                req_obj = self.requests.get(event["orderId"])
                p_from = retry_from(ord_obj, req_obj, event["leg"], self.now) if (ord_obj and req_obj and event["reason"] in ("not_ready", "closed")) else 0
                self.saved_retry[(event["orderId"], event["leg"])] = Retry(
                    max(prev.pickup_from, p_from),
                    prev.manual_licence or (event["reason"] == "licence"),
                    prev.plates or (event["reason"] == "no_plates"),
                )
                gid = event["gigId"]
                if gid in self.hitch_gigs:
                    self.stats["hitch_visit_failed"] += 1
                    if gid in self.posts:
                        rem_stops = [s for s in self.posts[gid]["stops"] if not (s["orderId"] == event["orderId"] and s["leg"] == event["leg"])]
                        self.posts[gid] = {**self.posts[gid], "stops": rem_stops}
                        if len(order_ids_of(self.posts[gid])) < 2:
                            self.hitch_gigs.pop(gid, None)
            self.retry(event["orderId"], event["leg"], event["reason"])
            if self.p.return_offer_km > 0 and event["gigId"] in self.booked_deliveries:
                self.update_gig_deliveries(event["gigId"])
        elif kind == "gig_expired":
            self.stats["gig_expired"] += 1
            post = self.posts.get(event["gigId"])
            if post:
                if self.p.hitch and event["gigId"] in self.hitch_gigs:
                    for s in post["stops"]:
                        oid = s["orderId"]
                        if oid in self.orders and (self.now > self.orders[oid]["lastPickupAt"] or (self.p.urgent_hygiene and self.cannot_be_on_time(self.orders[oid]))):
                            self.lost.add(oid)
                else:
                    for s in post["stops"]:
                        oid = s["orderId"]
                        if not self.p.urgent_hygiene or oid not in self.orders or self.cannot_be_on_time(self.orders[oid]):
                            self.lost.add(oid)
            self.repost(event["gigId"])
        elif kind == "deadline_close":
            self.stats["deadline_close"] += 1
            self.raise_fees(event["orderId"])
        elif kind == "gig_booked":
            gid = event["gigId"]
            self.booked.add(gid)
            self.last_booked_fee[gid] = event["feeCents"]
            self.booked_driver[gid] = event["driverId"]
            for ok in [k for k in self.open_offers if k[0] == gid]:
                self.open_offers.pop(ok, None)
            self.stats["booked"] += 1
            if self.p.return_offer_km > 0:
                self.open_gig_offers.pop(gid, None)
                self.gig_driver[gid] = event["driverId"]
                self.gig_booked_at[gid] = event["at"]
                self.update_gig_deliveries(gid)
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
                elif gid in self.chain_pairs:
                    self.stats["chain_pair_booked"] += 1
                elif gid in self.posts and len(order_ids_of(self.posts[gid])) > 1:
                    self.stats["lead_car_booked"] += 1
            elif gid in self.chain_pairs:
                self.stats["chain_pair_booked"] += 1
            elif gid in self.posts and len(order_ids_of(self.posts[gid])) > 1:
                self.stats["lead_car_booked"] += 1
            post = self.posts.get(gid)
            if post:
                order_ids = list(dict.fromkeys(s["orderId"] for s in post["stops"]))
                ref_cents = sum(self.requests[o]["referenceFeeCents"] for o in order_ids if o in self.requests)
                self.stats["booked_fee_cents"] += event["feeCents"]
                self.stats["booked_ref_cents"] += ref_cents
                if self.p.return_offer_km > 0:
                    for oid in order_ids:
                        if oid in self.return_reqs:
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
            self.booked_driver.pop(gid, None)
            self.stats[kind] += 1
            if self.p.return_offer_km > 0:
                self.clear_gig_tracking(gid)
            post = self.posts.get(gid)
            if post:
                for order_id in dict.fromkeys(s["orderId"] for s in post["stops"]):
                    order = self.orders.get(order_id)
                    if order and undelivered(order) and self.now > order["lastPickupAt"]:
                        self.lost.add(order_id)
            if self.p.hitch:
                if gid in self.hitch_gigs:
                    self.stats["hitch_dropped"] += 1
                    info = self.hitch_gigs[gid]
                    info["unbooked_since"] = self.now
                    oids = info["orders"]
                    if len(oids) != 2 or any(oid not in self.orders or oid in self.urgent or oid in self.lost for oid in oids):
                        self.split_hitch_gig(gid, reason="drop")
                    else:
                        sa = self.car_spec_for_order(self.orders[oids[0]])
                        sb = self.car_spec_for_order(self.orders[oids[1]])
                        if sa is None or sb is None or not self.chain_feasible(sa, sb, self.now)[0]:
                            self.split_hitch_gig(gid, reason="drop")
                elif post and len(post["stops"]) == 2 and len(order_ids_of(post)) == 1:
                    self.single_open_since[gid] = self.now
                post = self.posts.get(gid)
            rescued = False
            if self.p.drop_urgent_margin_min > 0 and post:
                for order_id in dict.fromkeys(s["orderId"] for s in post["stops"]):
                    if (
                        order_id in self.orders
                        and undelivered(self.orders[order_id])
                        and self.orders[order_id]["lastPickupAt"] - self.now <= self.p.drop_urgent_margin_min
                    ):
                        self.stats["drop_rescued"] += 1
                        self.raise_fees(order_id)
                        rescued = True
            if not rescued and self.p.drop_reprice_bump >= 0.0 and post:
                self.maybe_reprice_after_drop(gid, post)
        elif kind == "gig_started":
            if self.p.return_offer_km > 0:
                self.gig_started_at[event["gigId"]] = event["at"]
                self.update_gig_deliveries(event["gigId"])
        elif kind == "driver_late":
            if self.p.return_offer_km > 0:
                self.gig_late_pickup[event["gigId"]] = event["pickupAt"]
                self.update_gig_deliveries(event["gigId"])
        elif kind == "picked_up":
            if self.p.return_offer_km > 0:
                self.gig_picked_up[(event["gigId"], event["orderId"], event["leg"])] = (event["at"], event["placeId"])
                self.update_gig_deliveries(event["gigId"])
        elif kind == "gig_viewed":
            self.last_view[event["driverId"]] = event["at"]
            if self.p.view_offer_mult > 0:
                self.recent_views.append((event["at"], event["gigId"], event["driverId"]))
        elif kind == "ledger":
            line = event["line"]
            oid = line.get("orderId", "") or ""
            order = self.orders.get(oid) if oid else None
            dealer = self.requests[oid]["dealerId"] if oid and oid in self.requests else None
            is_ring = order and self.supply.get(order["legs"][0]["pickup"]["placeId"], 0) < self.p.min_supply
            is_ext_ring = order and self.gate_supply.get(order["legs"][0]["pickup"]["placeId"], 0) < self.p.min_supply
            if is_ring:
                self.stats["margin_ring_cents"] += line["cents"]
            if is_ext_ring:
                self.stats["margin_ext_ring_cents"] += line["cents"]
            if oid in self.hitch_quote_reqs:
                self.stats["hitch_quote_margin_cents"] += line["cents"]
            if oid in self.return_reqs:
                self.stats["ret_margin_cents"] += line["cents"]
                self.stats[f"ret_{line['kind']}_cents"] += line["cents"]
            if line["kind"] == "driver_fee" and line.get("gigId"):
                gid = line["gigId"]
                if gid in self.hitch_gigs:
                    info = self.hitch_gigs[gid]
                    self.stats["hitch_paid_gigs"] += 1
                    self.stats["hitch_paid_fee_cents"] += -line["cents"]
                    self.stats["hitch_paid_single_open_cents"] += info["single_open_sum"]
                    self.stats["hitch_paid_single_ref_cents"] += info["single_ref_sum"]
                elif not oid and self.p.return_offer_km > 0 and gid in self.return_offer_gigs:
                    ro_id = self.return_offer_gigs[gid]
                    if ro_id in self.return_reqs:
                        self.stats["ret_margin_cents"] += line["cents"]
                        self.stats["ret_driver_fee_cents"] += line["cents"]
            if line["kind"] in ("late_refund", "undelivered_penalty") and oid:
                if oid not in self.late:
                    if is_ring:
                        self.stats["late_ring"] += 1
                    if order and order["option"] == "same_day" and oid in self.ring_hub_same_day:
                        self.stats["late_ring_hub_same_day"] += 1
                    if is_ext_ring:
                        self.stats["late_ext_ring"] += 1
                    if oid in self.hitch_ever_paired:
                        self.stats["hitch_late"] += 1
                    if oid in self.hitch_booked_orders:
                        self.stats["hitch_late_booked"] += 1
                    if oid in self.hitch_quote_reqs:
                        self.stats["hitch_quote_late"] += 1
                    if oid in self.return_reqs:
                        self.stats["ret_late"] += 1
                self.late.add(oid)
                if dealer:
                    self.dealer_trust[dealer] //= 2
            elif line["kind"] == "revenue" and oid:
                if dealer and oid not in self.late:
                    if order and self.now <= order["deadline"]:
                        self.dealer_trust[dealer] = min(25, self.dealer_trust[dealer] + 1)
        elif kind == "offer_answered":
            self.stats[f"offer_{event['answer']}"] += 1
            tag = self.open_offers.pop((event["gigId"], event["driverId"]), None)
            if tag:
                self.stats[f"{tag}_offer_{event['answer']}"] += 1
            if self.p.return_offer_km > 0:
                gid = event["gigId"]
                drv_id = event["driverId"]
                self.open_gig_offers[gid].discard(drv_id)
                if gid in self.return_offer_gigs:
                    ro_id = self.return_offer_gigs[gid]
                    self.stats[f"ret_{event['answer']}"] += 1
                    if event["answer"] == "declined":
                        self.return_declined_orders.add((ro_id, drv_id))
        elif kind == "delivered":
            self.leg_gigs.get(event["orderId"], {}).pop(event["leg"], None)
            gid = event["gigId"]
            post = self.posts.get(gid)
            if post and not any(self.leg_gigs.get(s["orderId"], {}).get(s["leg"]) == gid for s in post["stops"]):
                self.booked_driver.pop(gid, None)
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
            if self.p.return_offer_km > 0:
                self.gig_delivered_legs[(event["gigId"], event["orderId"], event["leg"])] = (event["at"], event["placeId"])
                self.update_gig_deliveries(event["gigId"])

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
                if self.p.hitch:
                    for gid in list(self.gigs_of(order_id)):
                        if gid in self.hitch_gigs and gid not in self.booked:
                            self.split_hitch_gig(gid, reason="warn")
                if (
                    self.p.urgent_hygiene
                    and self.p.late_fee_open > 0
                    and not self.p.late_repost
                    and order_id not in self.late_repriced
                    and self.now > order["lastPickupAt"] + self.p.late_reprice_grace_min
                ):
                    self.send_post_of(order_id)
                    gigs = self.gigs_of(order_id)
                    if gigs and all(gig_id not in self.booked for gig_id in gigs):
                        self.late_repriced.add(order_id)
                        self.stats["late_repriced"] += 1
                        for gig_id in gigs:
                            post = self.posts.get(gig_id)
                            if post is not None:
                                sched = self.fees_for(order, pickups(post), post)
                                self.posts[gig_id] = {**post, "schedule": sched}
                                self.outbox.append({"type": "reprice", "gigId": gig_id, "schedule": sched})
                if self.p.late_repost and order_id not in self.late_reposted:
                    self.send_post_of(order_id)
                    gigs = self.gigs_of(order_id)
                    if gigs and all(gig_id not in self.booked for gig_id in gigs):
                        self.late_reposted.add(order_id)
                        self.stats["late_reposts"] += 1
                        self.leg_gigs.pop(order_id, None)
                        for gig_id in gigs:
                            self.single_open_since.pop(gig_id, None)
                            self.outbox.append({"type": "withdraw", "gigId": gig_id})
                            action = self.posts.get(gig_id)
                            if action is not None:
                                stops = without_windows(action["stops"], float("inf"))
                                self.outbox.append({**action, "stops": stops, "schedule": self.fees_for(order, pickups(action), action)})
        if self.deferred_orders:
            self.tick_deferred_posts()
        if self.p.chain_pair_km > 0 and self.chain_pairs:
            self.tick_chain_pairs()
        if self.p.hitch and self.level >= 3:
            self.tick_hitch()
        if self.p.return_offer_km > 0 and self.level >= 3:
            self.send_return_offers()
        if self.p.dest_offer_mult > 0 or self.p.view_offer_mult > 0:
            self.tick_proactive_offers()

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
        can_try_hitch = False
        can_try_return = False
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
                chain_braked = False
                if p.chain_guard_target > 0 and self.projected_on_time() < p.chain_guard_target:
                    chain_braked = True
                elif p.chain_max_urgent > 0:
                    urg_open = sum(1 for oid in self.urgent if oid in self.orders and undelivered(self.orders[oid]) and not self.staffed(self.orders[oid]))
                    if urg_open >= p.chain_max_urgent:
                        chain_braked = True
                if chain_braked:
                    self.stats["chain_guard_blocked"] += 1
                    return {}, "decline"
                can_try_hitch = p.hitch_quote and self.level >= 3 and len(legs) == 1 and self.hitch_cap_available()
                can_try_return = p.return_offer_km > 0 and self.level >= 3 and self.return_wins_by_day[self.now // DAY] < p.return_cap_day
                if not (can_try_hitch or can_try_return):
                    if p.hitch_quote and self.level >= 3 and len(legs) == 1:
                        self.stats["hitch_cap_blocked"] += 1
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
        pass_hitch = False
        matched_hitch_partner: Optional[str] = None
        pass_return_offer = False
        matched_return_driver: Optional[tuple[str, str]] = None
        for option in request["options"]:
            ring_hub_sd = False
            if (pass_ext_ring or pass_return_hub or can_try_hitch or can_try_return) and option["kind"] == "same_day":
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

            opt_is_hitch = False
            opt_is_ret = False
            if can_try_hitch or can_try_return:
                if can_try_hitch:
                    partner_oid = self.find_waiting_partner_for_request(request, deadline)
                    if partner_oid is not None:
                        opt_is_hitch = True
                        pass_hitch = True
                        if matched_hitch_partner is None:
                            matched_hitch_partner = partner_oid
                if not opt_is_hitch and can_try_return:
                    cands = self.find_return_drivers_for_option(request, ready, drive, deadline, for_quote=True)
                    if cands:
                        opt_is_ret = True
                        pass_return_offer = True
                        if matched_return_driver is None:
                            matched_return_driver = (cands[0][0], cands[0][1])
                if not (opt_is_hitch or opt_is_ret):
                    continue

            if ring_hub_sd:
                self.stats["quoted_ring_hub_same_day"] += 1
                self.ring_hub_same_day.add(request["id"])

            option_mult = mult
            if is_invest and slack >= 360:
                option_mult *= (1 - p.trust_invest)
            if p.return_hub_discount > 0 and pass_return_hub and not pass_ext_ring:
                option_mult *= (1.0 - p.return_hub_discount)
            if opt_is_ret and not opt_is_hitch and p.return_markup != 0.0:
                option_mult *= (1.0 + p.return_markup)

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
        elif pass_hitch:
            self.hitch_quote_reqs.add(request["id"])
            if matched_hitch_partner is not None:
                self.hitch_quote_matched[request["id"]] = matched_hitch_partner
            self.stats["hitch_quote_quoted"] += 1
        elif pass_return_offer:
            self.return_reqs.add(request["id"])
            if matched_return_driver is not None:
                self.return_targets[request["id"]] = matched_return_driver
            self.stats["ret_quoted"] += 1
        return prices, "floor" if floored else "quote"

    def learn(self, request_id: str, won: bool) -> None:
        """Moves the multiplier towards the price that wins `price_target_win` of the normal quotes."""
        if self.decided.get(request_id) != "quote":
            return
        if self.p.ext_ring_neutral_learn and request_id in self.ext_ring_reqs:
            self.stats["ext_ring_skipped_learn"] += 1
            return
        if self.p.ext_ring_neutral_learn and request_id in self.hitch_quote_reqs:
            self.stats["hitch_skipped_learn"] += 1
            return
        if request_id in self.return_reqs:
            self.stats["ret_skipped_learn"] += 1
            return
        if self.p.ext_ring_no_learn and not won and (request_id in self.ext_ring_reqs or request_id in self.hitch_quote_reqs):
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
    def cannot_be_on_time(self, order: Order) -> bool:
        open_legs = undelivered(order)
        if not open_legs:
            return False
        if self.now > order["lastPickupAt"]:
            return True
        rem_drive = sum(self.geo.minutes(order["legs"][i]["pickup"]["placeId"], order["legs"][i]["delivery"]["placeId"]) for i in open_legs)
        if len(open_legs) == 2:
            rem_drive += self.geo.minutes(order["legs"][open_legs[0]]["delivery"]["placeId"], order["legs"][open_legs[1]]["pickup"]["placeId"])
        first_from = order["legs"][open_legs[0]]["pickup"]["window"]["from"]
        return max(self.now, first_from) + rem_drive > order["deadline"]

    def has_competing_urgent_gig(self, pickup: str) -> bool:
        for gid, action in self.posts.items():
            if gid in self.booked:
                continue
            oids = order_ids_of(action)
            if not oids or not any(self.leg_gigs.get(s["orderId"], {}).get(s["leg"]) == gid for s in action["stops"]):
                continue
            o0 = self.orders.get(oids[0])
            if o0 is None:
                continue
            p0 = o0["legs"][action["stops"][0]["leg"]]["pickup"]["placeId"]
            if self.geo.line_km(pickup, p0) <= self.p.supply_radius_km:
                if any(oid in self.urgent or (oid in self.orders and (self.orders[oid]["option"] == "same_day" or self.orders[oid]["lastPickupAt"] - self.now <= 6 * HOUR)) for oid in oids):
                    return True
        return False

    def tick_deferred_posts(self) -> None:
        for oid in list(self.deferred_orders):
            deferred_at = self.deferred_orders[oid]
            order = self.orders.get(oid)
            if order is None or not undelivered(order):
                self.deferred_orders.pop(oid, None)
                continue
            pickup = order["legs"][0]["pickup"]["placeId"]
            if oid in self.urgent or self.now - deferred_at >= self.p.defer_multiday_min or not self.has_competing_urgent_gig(pickup):
                self.deferred_orders.pop(oid, None)
                self.post(order, undelivered(order))

    def win(self, order: Order) -> None:
        if order["id"] in self.requests and order["id"] not in self.orders:
            self.orders[order["id"]] = order
            if self.p.urgent_hygiene and self.cannot_be_on_time(order):
                self.lost.add(order["id"])
            self.stats["won"] += 1
            if order["id"] in self.hitch_quote_reqs:
                self.stats["hitch_quote_won"] += 1
                self.hitch_won_day[self.now // DAY] += 1
            if order["id"] in self.return_reqs:
                self.stats["ret_won"] += 1
                self.return_wins_by_day[self.now // DAY] += 1
            if self.p.hitch and len(order["legs"]) == 1:
                self.hitch_newly_won.add(order["id"])
            pickup = order["legs"][0]["pickup"]["placeId"]
            if self.supply.get(pickup, 0) < self.p.min_supply:
                self.stats["won_ring"] += 1
            if order["option"] == "same_day" and order["id"] in self.ring_hub_same_day:
                self.stats["won_ring_hub_same_day"] += 1
            if self.gate_supply.get(pickup, 0) < self.p.min_supply:
                self.stats["won_ext_ring"] += 1
                if self.p.return_hub_min_supply > 0 and self.supply.get(order["legs"][-1]["delivery"]["placeId"], 0) >= self.p.return_hub_min_supply:
                    self.stats["won_return_hub"] += 1
            self.stats[f"won_{order['option']}"] += 1
            if (
                self.p.defer_multiday_min > 0
                and order["option"] != "same_day"
                and len(order["legs"]) == 1
                and order["id"] not in self.urgent
                and order["lastPickupAt"] - self.now >= 18 * HOUR
                and self.has_competing_urgent_gig(pickup)
            ):
                self.deferred_orders[order["id"]] = self.now
                self.stats["deferred_multiday"] += 1
                return
            self.post(order, undelivered(order))
            if self.p.return_offer_km > 0 and order["id"] in self.return_reqs and self.p.return_offer_on_win:
                self.send_return_offers()

    def change(self, order: Order) -> None:
        if order["id"] in self.orders:
            self.orders[order["id"]] = order
            if self.p.urgent_hygiene:
                if order["lastPickupAt"] - self.now > 3 * HOUR and order["id"] in self.urgent:
                    self.urgent.discard(order["id"])
                    self.stats["urgent_cleared"] += 1
                if self.cannot_be_on_time(order):
                    self.lost.add(order["id"])
                    self.stats["lost_on_change"] += 1
                else:
                    self.lost.discard(order["id"])
            was_deferred = self.deferred_orders.pop(order["id"], None) is not None
            if was_deferred or self.withdraw(order["id"]):
                self.post(order, undelivered(order), self.saved_retry.get((order["id"], 0), Retry()) if self.p.hitch else Retry())

    def repost(self, gig_id: str) -> None:
        self.single_open_since.pop(gig_id, None)
        action = self.posts.get(gig_id)
        if action is None or not any(self.leg_gigs.get(s["orderId"], {}).get(s["leg"]) == gig_id for s in action["stops"]):
            return
        self.chain_pairs.pop(gig_id, None)
        for stop in action["stops"]:
            self.leg_gigs.get(stop["orderId"], {}).pop(stop["leg"], None)
        oids = order_ids_of(action)
        if self.p.hitch and gig_id in self.hitch_gigs:
            info = self.hitch_gigs.pop(gig_id)
            if len(info["orders"]) == 2:
                self.hitch_split_pairs.add((min(info["orders"][0], info["orders"][1]), max(info["orders"][0], info["orders"][1])))
                for oid in info["orders"]:
                    self.hitch_order_splits[oid] += 1
            self.stats["hitch_split"] += 1
            self.stats["hitch_split_expired"] += 1
            if info["thin_b"]:
                self.stats["hitch_split_thin_b"] += 1
            for oid in oids:
                if oid in self.orders and undelivered(self.orders[oid]):
                    self.post(self.orders[oid], undelivered(self.orders[oid]), self.saved_retry.get((oid, 0), Retry()), allow_pair=False)
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
        if order_id in self.deferred_orders:
            self.deferred_orders.pop(order_id, None)
            self.post(order, undelivered(order), allow_pair=False)
        self.send_post_of(order_id)
        for gig_id in list(self.gigs_of(order_id)):
            if gig_id not in self.booked and gig_id in self.posts and len(order_ids_of(self.posts[gig_id])) > 1:
                if self.p.hitch and gig_id in self.hitch_gigs:
                    self.split_hitch_gig(gig_id, reason="warn")
                else:
                    self.stats["lead_car_split"] += 1
                    self.chain_pairs.pop(gig_id, None)
                    self.single_open_since.pop(gig_id, None)
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
                self.single_open_since.pop(gig_id, None)
                sched = self.fees_for(order, pickups(self.posts[gig_id]), self.posts[gig_id])
                self.posts[gig_id] = {**self.posts[gig_id], "schedule": sched}
                self.outbox.append({"type": "reprice", "gigId": gig_id, "schedule": sched})
                self.offer(gig_id, order)

    def open_offer_count(self, gid: str) -> int:
        if self.p.return_offer_km <= 0:
            return sum(1 for k in self.open_offers if k[0] == gid)
        return len(self.open_gig_offers[gid] | {d for (g, d) in self.open_offers if g == gid})

    def maybe_reprice_after_drop(self, gig_id: str, post: PostAction) -> None:
        if not any(self.leg_gigs.get(s["orderId"], {}).get(s["leg"]) == gig_id for s in post["stops"]):
            return
        oids = order_ids_of(post)
        if not oids or any(oid not in self.orders or oid in self.urgent or oid in self.lost for oid in oids):
            return
        until = min(self.orders[oid]["lastPickupAt"] for oid in oids) - 3 * HOUR
        if until - self.now < 60:
            return
        if gig_id in self.hitch_gigs:
            base = self.hitch_gigs[gig_id]["single_ref_sum"] * self.p.hitch_fee
        elif len(oids) > 1:
            base = self.pair_base_cents(oids)
        else:
            o0 = self.orders[oids[0]]
            base = self.requests[o0["id"]]["referenceFeeCents"] * pickups(post) / len(o0["legs"])
        if base <= 0:
            return
        cur_fee = current_schedule_fee(post["schedule"], self.now)
        cur_mult = cur_fee / base
        last_fee = self.last_booked_fee.get(gig_id, 0)
        last_mult = (last_fee / base) if last_fee > 0 else self.p.fee_open
        new_open = clamp(last_mult + self.p.drop_reprice_bump, self.p.fee_open, self.p.fee_warn)
        if new_open + 0.03 < cur_mult:
            sched = self.rising(base, until, fee_open_override=new_open)
            self.posts[gig_id] = {**post, "schedule": sched}
            self.outbox.append({"type": "reprice", "gigId": gig_id, "schedule": sched})
            self.stats["drop_repriced"] += 1

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
            if p.return_offer_km > 0 and d["id"] in self.open_gig_offers[gig_id]:
                continue
            recent = self.now - self.last_view.get(d["id"], -10 ** 9) <= p.offer_recent_view_min
            candidates.append((0 if recent else 1, self.geo.minutes(d["homePlaceId"], pickup), d["id"]))
        candidates.sort()
        fee = int(self.requests[order["id"]]["referenceFeeCents"] * pickups(post) / len(order["legs"]) * p.offer_mult + 0.5)
        limit = min(3 - self.open_offer_count(gig_id), p.offers_per_warning) if p.return_offer_km > 0 else min(3, p.offers_per_warning)
        for _, _, driver_id in candidates[: max(0, limit)]:
            self.outbox.append({"type": "offer", "gigId": gig_id, "driverId": driver_id, "feeCents": fee})
            self.offers_sent[(driver_id, day)] += 1
            if p.return_offer_km > 0:
                self.open_gig_offers[gig_id].add(driver_id)
                if gig_id in self.return_offer_gigs:
                    self.stats["ret_offered"] += 1
            self.stats["offers"] += 1

    def tick_proactive_offers(self) -> None:
        if self.level < 3 or not (7 * HOUR <= self.now % DAY < 21 * HOUR):
            return
        p, day = self.p, self.now // DAY
        busy_drivers = set(self.booked_driver.values())

        def gig_base_and_ends(gid: str, post: PostAction) -> Optional[tuple[float, str, str]]:
            if not any(self.leg_gigs.get(s["orderId"], {}).get(s["leg"]) == gid for s in post["stops"]):
                return None
            oids = order_ids_of(post)
            if not oids or any(oid not in self.orders or oid in self.lost for oid in oids):
                return None
            first_s, last_s = post["stops"][0], post["stops"][-1]
            first_pick = self.orders[first_s["orderId"]]["legs"][first_s["leg"]]["pickup"]["placeId"]
            last_dest = self.orders[last_s["orderId"]]["legs"][last_s["leg"]]["delivery"]["placeId"]
            if gid in self.hitch_gigs:
                base = self.hitch_gigs[gid]["single_ref_sum"] * p.hitch_fee
            elif len(oids) > 1:
                base = self.pair_base_cents(oids)
            else:
                o0 = self.orders[oids[0]]
                base = self.requests[o0["id"]]["referenceFeeCents"] * pickups(post) / len(o0["legs"])
            return base, first_pick, last_dest

        if p.dest_offer_mult > 0:
            for gid, post in list(self.posts.items()):
                if gid in self.booked or gid in self.dest_offered_gigs:
                    continue
                if self.now - self.gig_posted_at.get(gid, self.now) < p.dest_offer_delay_min:
                    continue
                info = gig_base_and_ends(gid, post)
                if info is None:
                    continue
                base, first_pick, last_dest = info
                self.dest_offered_gigs.add(gid)
                open_cnt = self.open_offer_count(gid)
                if open_cnt >= 3:
                    continue
                audience = post["audience"]
                cands = []
                for d_id, d in self.drivers.items():
                    if d_id in busy_drivers or (gid, d_id) in self.offered_pairs or self.offers_sent[(d_id, day)] >= 3:
                        continue
                    if audience["experienced"] and not (d["rating"] >= 4.8 and d["completedGigs"] >= 50):
                        continue
                    if audience["manualLicence"] and d["licence"] != "manual":
                        continue
                    lv = self.last_view.get(d_id, -10 ** 9)
                    if lv // DAY != day:
                        continue
                    dk = self.geo.line_km(d["homePlaceId"], last_dest)
                    pk = self.geo.line_km(d["homePlaceId"], first_pick)
                    if dk <= p.dest_offer_km and pk > p.supply_radius_km:
                        cands.append((-lv, dk, d_id))
                cands.sort()
                fee = max(1, int(base * p.dest_offer_mult + 0.5))
                for _, _, d_id in cands[: 3 - open_cnt]:
                    self.outbox.append({"type": "offer", "gigId": gid, "driverId": d_id, "feeCents": fee})
                    self.offers_sent[(d_id, day)] += 1
                    self.open_offers[(gid, d_id)] = "dest"
                    self.offered_pairs.add((gid, d_id))
                    self.stats["offers"] += 1
                    self.stats["dest_offers_sent"] += 1

        if p.view_offer_mult > 0 and self.recent_views:
            win_m = max(15, p.view_offer_window_min)
            self.recent_views = [(at, gid, d_id) for (at, gid, d_id) in self.recent_views if self.now - at <= win_m + 5]
            for at, gid, d_id in list(self.recent_views):
                if not (2 <= self.now - at <= win_m):
                    continue
                post = self.posts.get(gid)
                if post is None or gid in self.booked or (gid, d_id) in self.offered_pairs:
                    continue
                if self.now - self.gig_posted_at.get(gid, self.now) < p.view_offer_after_min:
                    continue
                if d_id in busy_drivers or self.offers_sent[(d_id, day)] >= 3:
                    continue
                open_cnt = self.open_offer_count(gid)
                if open_cnt >= 3:
                    continue
                d = self.drivers.get(d_id)
                if d is None:
                    continue
                audience = post["audience"]
                if audience["experienced"] and not (d["rating"] >= 4.8 and d["completedGigs"] >= 50):
                    continue
                if audience["manualLicence"] and d["licence"] != "manual":
                    continue
                info = gig_base_and_ends(gid, post)
                if info is None:
                    continue
                base, first_pick, last_dest = info
                if min(self.geo.line_km(d["homePlaceId"], first_pick), self.geo.line_km(d["homePlaceId"], last_dest)) > 35.0:
                    continue
                cur_fee = current_schedule_fee(post["schedule"], self.now)
                fee = max(1, min(int(base * p.view_offer_cap + 0.5), int(cur_fee * p.view_offer_mult + 0.5)))
                self.outbox.append({"type": "offer", "gigId": gid, "driverId": d_id, "feeCents": fee})
                self.offers_sent[(d_id, day)] += 1
                self.open_offers[(gid, d_id)] = "view"
                self.offered_pairs.add((gid, d_id))
                self.stats["offers"] += 1
                self.stats["view_offers_sent"] += 1

    def pair_base_cents(self, oids: list[str]) -> float:
        p = self.p
        raw = sum(self.requests[oid]["referenceFeeCents"] for oid in oids if oid in self.requests)
        if p.chain_pair_km > 0 and len(oids) >= 2 and oids[0] in self.orders and oids[1] in self.orders:
            pa = self.orders[oids[0]]["legs"][0]["pickup"]["placeId"]
            da = self.orders[oids[0]]["legs"][0]["delivery"]["placeId"]
            pb = self.orders[oids[1]]["legs"][0]["pickup"]["placeId"]
            db = self.orders[oids[1]]["legs"][0]["delivery"]["placeId"]
            if not (self.geo.line_km(pa, pb) <= p.lead_car_max_gap_km and self.geo.line_km(da, db) <= p.lead_car_max_deliv_gap_km):
                return raw * p.chain_pair_fee_mult
        return raw * p.lead_car_fee_mult

    def fees_for(self, order: Order, cars: int, action: Optional[PostAction] = None) -> list[FeeStep]:
        p = self.p
        if action is not None:
            oids = order_ids_of(action)
            if len(oids) > 1:
                base = self.pair_base_cents(oids)
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
            if undelivered(order) and not self.staffed(order) and (self.now > order["lastPickupAt"] or (p.urgent_hygiene and self.cannot_be_on_time(order))):
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
        dest_supply = self.supply.get(order["legs"][-1]["delivery"]["placeId"], 0)
        fee_open_override: Optional[float] = None
        if p.return_offer_km > 0 and order["id"] in self.return_reqs:
            fee_open_override = p.return_fee_open
        elif p.hitch_thin_solo_open > 0 and order["id"] in self.hitch_quote_reqs:
            fee_open_override = p.hitch_thin_solo_open
        elif p.inbound_hub_fee_open > 0 and dest_supply >= 150 and until - self.now >= 2 * HOUR:
            fee_open_override = p.inbound_hub_fee_open
            self.stats["inbound_hub_posts"] += 1
        elif p.hub_multiday_fee_open > 0 and order["option"] != "same_day" and supply >= 150 and until - self.now >= 6 * HOUR:
            fee_open_override = p.hub_multiday_fee_open
            self.stats["hub_multiday_posts"] += 1
        elif p.thin_sameday_fee_open > 0 and order["option"] == "same_day" and supply < 65:
            fee_open_override = p.thin_sameday_fee_open
            self.stats["thin_sameday_posts"] += 1
        if p.hitch and p.hitch_preserve_age and cars == 1 and self.hitch_order_splits[order["id"]] > 0 and order["id"] in self.first_posted_at:
            first_at = self.first_posted_at[order["id"]]
            if first_at < self.now:
                base_open = fee_open_override if fee_open_override is not None else p.fee_open
                total_dt = daytime_minutes(first_at, until, p.day_start, p.day_end)
                elap_dt = daytime_minutes(first_at, self.now, p.day_start, p.day_end)
                aged_open = p.fee_warn if total_dt <= 0 else clamp(base_open + (p.fee_warn - base_open) * (elap_dt / total_dt), base_open, p.fee_warn)
                fee_open_override = max(base_open, aged_open)
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
        if p.max_rise_per_step > 0 and fee_warn_override is None and n > 1:
            fee_warn = max(fee_open, min(fee_warn, fee_open + p.max_rise_per_step * (n - 1)))
        power = p.fee_curve_power if fee_warn_override is None else 1.0
        return [
            {
                "at": at,
                "feeCents": max(
                    1,
                    int(base * (fee_open + (fee_warn - fee_open) * (((i / (n - 1)) ** power) if n > 1 else 0.0)) + 0.5),
                ),
            }
            for i, at in enumerate(times)
        ]

    def steep(self, base: float) -> list[FeeStep]:
        p = self.p
        if not p.urgent_hygiene:
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
        steps = [{"at": self.now, "feeCents": max(1, int(base * p.steep_open + 0.5))}]
        if p.steep_step <= 0:
            return steps
        k, h = 1, 1
        while k < 48 and h <= 144:
            mult = p.steep_open + k * p.steep_step
            if mult > p.steep_max + 1e-9:
                break
            at = self.now + h * 30
            if p.day_start <= at % DAY < p.day_end:
                steps.append({"at": at, "feeCents": max(1, int(base * mult + 0.5))})
                k += 1
            h += 1
        return steps

    def retry(self, order_id: str, leg: int, reason: str) -> None:
        if order_id in self.orders:
            order = self.orders[order_id]
            self.leg_gigs.get(order_id, {}).pop(leg, None)
            if self.p.hitch:
                retry_spec = self.saved_retry.get((order_id, leg))
                if retry_spec is not None:
                    self.post(order, [leg], retry_spec)
                    return
            car_not_there = reason in ("not_ready", "closed")
            pickup_from = retry_from(order, self.requests[order_id], leg, self.now) if car_not_there else 0
            self.post(order, [leg], Retry(pickup_from, manual_licence=reason == "licence", plates=reason == "no_plates"))

    # --- stage 1: hitch multi-car chain pairing & thin-quote ------------------------------------------
    def hitch_cap_available(self) -> bool:
        p = self.p
        if p.hitch_cap_day <= 0:
            return False
        day = self.now // DAY
        in_flight = 0.0
        for rid in self.hitch_quote_reqs:
            if rid not in self.orders and rid not in self.lost_requests and rid in self.requests and self.now <= self.requests[rid]["respondBy"]:
                in_flight += 0.35
        return self.hitch_won_day[day] + in_flight < p.hitch_cap_day

    def single_open_fee_cents(self, order: Order) -> int:
        p = self.p
        req = self.requests[order["id"]]
        base = req["referenceFeeCents"] / len(order["legs"])
        until = order["lastPickupAt"] - 3 * HOUR
        supply = self.supply.get(order["legs"][0]["pickup"]["placeId"], 0)
        mult = p.fee_open
        if p.return_offer_km > 0 and order["id"] in self.return_reqs:
            mult = p.return_fee_open
        elif p.hitch_thin_solo_open > 0 and order["id"] in self.hitch_quote_reqs:
            mult = p.hitch_thin_solo_open
        elif p.hub_multiday_fee_open > 0 and order["option"] != "same_day" and supply >= 150 and until - self.now >= 6 * HOUR:
            mult = p.hub_multiday_fee_open
        elif p.thin_sameday_fee_open > 0 and order["option"] == "same_day" and supply < 65:
            mult = p.thin_sameday_fee_open
        return max(1, int(base * mult + 0.5))

    def hitch_schedule_for(self, oid_a: str, oid_b: str) -> tuple[list[FeeStep], int, int]:
        p = self.p
        oa, ob = self.orders[oid_a], self.orders[oid_b]
        ra, rb = self.requests[oid_a], self.requests[oid_b]
        open_a = self.single_open_fee_cents(oa)
        open_b = self.single_open_fee_cents(ob)
        single_open_sum = open_a + open_b
        ref_sum = ra["referenceFeeCents"] + rb["referenceFeeCents"]
        is_rt = self.geo.line_km(ob["legs"][-1]["delivery"]["placeId"], oa["legs"][0]["pickup"]["placeId"]) <= 30.0
        pair_mult = p.hitch_fee if (is_rt or p.hitch_non_rt_fee <= 0) else p.hitch_non_rt_fee
        open_fee = max(1, int(single_open_sum * pair_mult + 0.5))
        if p.hitch_min_saving_floor:
            open_fee = max(open_fee, max(open_a, open_b))
        if self.level == 1:
            return [{"at": self.now, "feeCents": open_fee}], single_open_sum, ref_sum
        warn_fee = max(open_fee, int(ref_sum * p.fee_warn + 0.5))
        until = min(oa["lastPickupAt"], ob["lastPickupAt"]) - 3 * HOUR
        times = [self.now]
        t = (self.now // p.fee_step_min + 1) * p.fee_step_min
        while t <= until:
            if p.day_start <= t % DAY < p.day_end:
                times.append(t)
            t += p.fee_step_min
        if len(times) > 48:
            k = len(times) - 1
            times = [times[round(i * k / 47)] for i in range(48)]
        n = len(times)
        sched: list[FeeStep] = [
            {"at": at, "feeCents": max(1, int(open_fee + (warn_fee - open_fee) * (i / (n - 1) if n > 1 else 0) + 0.5))}
            for i, at in enumerate(times)
        ]
        return sched, single_open_sum, ref_sum

    def car_spec_for_order(self, order: Order) -> Optional[CarSpec]:
        p = self.p
        oid = order["id"]
        if len(order["legs"]) != 1 or undelivered(order) != [0]:
            return None
        req = self.requests.get(oid)
        if req is None:
            return None
        retry = self.saved_retry.get((oid, 0), Retry())
        flags = note_flags(req["note"], v2=p.notes_v2)
        retry = retry._replace(plates=retry.plates or flags.plates)
        stops = stops_for(order, [0], req["note"], retry, self.geo, p.charge_min_km, p.notes_v2, req["arrivedAt"])
        leg0 = order["legs"][0]
        pk_win = stops[0].get("window", leg0["pickup"]["window"])
        dl_base_to = max(leg0["delivery"]["window"]["from"], order["deadline"])
        dl_win = stops[1].get("window", {"from": leg0["delivery"]["window"]["from"], "to": dl_base_to})
        extra = (30 if stops[0].get("withPlates") else 0) + (40 if stops[0].get("withCharging") else 0)
        return CarSpec(
            oid=oid,
            place_p=leg0["pickup"]["placeId"],
            place_d=leg0["delivery"]["placeId"],
            pickup_sp=leg0["pickup"],
            delivery_sp=leg0["delivery"],
            pk_from=pk_win["from"],
            pk_to=pk_win["to"],
            dl_from=dl_win["from"],
            dl_to=dl_win["to"],
            deadline=order["deadline"],
            drive=self.geo.minutes(leg0["pickup"]["placeId"], leg0["delivery"]["placeId"]),
            extra_pickup_min=extra,
        )

    def car_spec_for_request_option(self, request: PriceRequest, deadline_raw: int) -> Optional[CarSpec]:
        p = self.p
        if len(request["legs"]) != 1:
            return None
        leg0 = request["legs"][0]
        extra_days = 0
        if p.notes_v2 and request["note"]:
            pn = parse_note_v2(request["note"], request["arrivedAt"])
            if pn.unsure and p.note_unsure == "decline":
                return None
            if pn.ready_at is not None and not leg0["pickup"]["privateAddress"]:
                extra_days = max(0, pn.ready_at // DAY - leg0["pickup"]["window"]["from"] // DAY)
        deadline = shift_business_days(deadline_raw, extra_days) if p.notes_v2 else deadline_raw
        pk_win = window_from_note(
            request["note"], leg0["pickup"]["window"], "pickup",
            v2=p.notes_v2, arrived_at=request["arrivedAt"],
            private_address=leg0["pickup"]["privateAddress"], stated_hours=leg0["pickup"]["hours"],
        )
        pk_to = pk_win["to"] if leg0["pickup"]["privateAddress"] else min(pk_win["to"], deadline)
        dl_base: TimeWindow = {"from": leg0["delivery"]["window"]["from"], "to": max(leg0["delivery"]["window"]["from"], deadline)}
        dl_win = window_from_note(
            request["note"], dl_base, "delivery",
            v2=p.notes_v2, arrived_at=request["arrivedAt"],
            private_address=leg0["delivery"]["privateAddress"], stated_hours=leg0["delivery"]["hours"],
        )
        flags = note_flags(request["note"], v2=p.notes_v2)
        car = leg0["car"]
        low_bat = car["electric"] and car["chargePercent"] is not None and car["chargePercent"] < 30
        if low_bat:
            low_bat = self.geo.road_km(leg0["pickup"]["placeId"], leg0["delivery"]["placeId"]) > p.charge_min_km
        extra = (30 if flags.plates else 0) + (40 if low_bat else 0)
        return CarSpec(
            oid=request["id"],
            place_p=leg0["pickup"]["placeId"],
            place_d=leg0["delivery"]["placeId"],
            pickup_sp=leg0["pickup"],
            delivery_sp=leg0["delivery"],
            pk_from=pk_win["from"],
            pk_to=pk_to,
            dl_from=dl_win["from"],
            dl_to=dl_win["to"],
            deadline=dl_win["to"],
            drive=self.geo.minutes(leg0["pickup"]["placeId"], leg0["delivery"]["placeId"]),
            extra_pickup_min=extra,
        )

    def chain_feasible(self, a: CarSpec, b: CarSpec, now_at: int) -> tuple[bool, int, int]:
        p = self.p
        sup_a = self.supply.get(a.place_p, 0)
        sup_b = self.supply.get(b.place_p, 0)
        if sup_a < sup_b:
            return False, 0, 0
        if p.hitch_max_b_supply > 0 and sup_b > p.hitch_max_b_supply:
            return False, 0, 0
        if self.geo.line_km(a.place_d, b.place_p) > p.hitch_km:
            return False, 0, 0
        if p.hitch_max_return_km > 0 and self.geo.line_km(b.place_d, a.place_p) > p.hitch_max_return_km:
            return False, 0, 0
        if p.hitch_min_deliv_supply > 0 and self.supply.get(b.place_d, 0) < p.hitch_min_deliv_supply and self.geo.line_km(b.place_d, a.place_p) > 55.0:
            return False, 0, 0
        if p.hitch_homeward:
            dist_da_ap = self.geo.line_km(a.place_d, a.place_p)
            limit_km = max(60.0, p.hitch_homeward_ratio * dist_da_ap) if p.hitch_homeward_ratio > 0 else max(60.0, dist_da_ap + 25.0)
            if self.geo.line_km(b.place_d, a.place_p) > limit_km:
                return False, 0, 0
        deadhead = self.geo.minutes(a.place_d, b.place_p)
        if a.drive + deadhead + b.drive > 12 * HOUR:
            return False, 0, 0
        min_slack = p.min_slack_min
        start_lo = max(now_at, a.pk_from)
        start_hi = min(
            a.pk_to,
            a.dl_to - a.extra_pickup_min - a.drive,
            a.deadline - min_slack - a.extra_pickup_min - a.drive,
        )
        if start_hi < start_lo or start_hi < now_at + min_slack:
            return False, 0, 0

        valid_open_minutes = 0
        earliest_finish = 10 ** 9
        step = 15
        first_t = ((start_lo + step - 1) // step) * step
        test_points = [start_lo] if first_t > start_hi else ([start_lo] if first_t > start_lo else []) + list(range(first_t, start_hi + 1, step))
        for t0 in test_points:
            if not site_open_at(a.pickup_sp, t0):
                continue
            arr_da = t0 + a.extra_pickup_min + a.drive
            if arr_da > min(a.dl_to, a.deadline):
                continue
            del_a = max(arr_da, a.dl_from)
            if not a.delivery_sp["privateAddress"] and a.delivery_sp["hours"] is not None:
                open_da = next_dealer_open_at(a.delivery_sp, del_a, min(a.dl_to, a.deadline))
                if open_da is None or open_da - arr_da > 120:
                    continue
                del_a = open_da
            elif del_a > min(a.dl_to, a.deadline):
                continue

            reach_pb = max(del_a + deadhead, b.pk_from)
            if reach_pb > b.pk_to:
                continue
            pick_b = next_dealer_open_at(b.pickup_sp, reach_pb, b.pk_to)
            if pick_b is None or pick_b - del_a - deadhead > 4 * HOUR:
                continue
            arr_db = pick_b + b.extra_pickup_min + b.drive
            if arr_db > min(b.dl_to, b.deadline - min_slack):
                continue
            del_b = max(arr_db, b.dl_from)
            if not b.delivery_sp["privateAddress"] and b.delivery_sp["hours"] is not None:
                open_db = next_dealer_open_at(b.delivery_sp, del_b, min(b.dl_to, b.deadline))
                if open_db is None or open_db - arr_db > 120:
                    continue
                del_b = open_db
            elif del_b > min(b.dl_to, b.deadline):
                continue

            valid_open_minutes += step
            if del_b < earliest_finish:
                earliest_finish = del_b

        if valid_open_minutes < min_slack:
            return False, 0, 0
        return True, valid_open_minutes, earliest_finish

    def can_order_hitch(self, oid: str) -> tuple[bool, Optional[str]]:
        if oid in self.urgent or oid in self.lost or oid in self.return_reqs or oid not in self.orders:
            return False, None
        if self.p.hitch_max_splits > 0 and self.hitch_order_splits[oid] >= self.p.hitch_max_splits:
            return False, None
        order = self.orders[oid]
        if len(order["legs"]) != 1 or undelivered(order) != [0]:
            return False, None
        gigs = self.gigs_of(oid)
        if len(gigs) != 1:
            return False, None
        gid = gigs[0]
        if gid in self.booked or gid not in self.posts or gid in self.hitch_gigs:
            return False, None
        post = self.posts[gid]
        if len(post["stops"]) != 2 or order_ids_of(post) != [oid]:
            return False, None
        return True, gid

    def waiting_single_orders(self) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        for oid in sorted(self.orders):
            ok, gid = self.can_order_hitch(oid)
            if ok and gid is not None:
                out.append((oid, gid))
        return out

    def find_waiting_partner_for_request(self, request: PriceRequest, deadline_raw: int) -> Optional[str]:
        spec_req = self.car_spec_for_request_option(request, deadline_raw)
        if spec_req is None:
            return None
        committed_partners: set[str] = set()
        for rid, partner_oid in self.hitch_quote_matched.items():
            if rid in self.lost_requests:
                continue
            if rid not in self.orders and rid in self.requests and self.now <= self.requests[rid]["respondBy"]:
                committed_partners.add(partner_oid)
            elif rid in self.orders and rid not in self.hitch_ever_paired and undelivered(self.orders[rid]) and not self.staffed(self.orders[rid]):
                committed_partners.add(partner_oid)

        best_score: Optional[tuple[int, float, int, str]] = None
        for oid, _ in self.waiting_single_orders():
            if oid in committed_partners:
                continue
            spec_o = self.car_spec_for_order(self.orders[oid])
            if spec_o is None:
                continue
            ok1, _, fin1 = self.chain_feasible(spec_o, spec_req, self.now + 15)
            if ok1:
                rt = 0 if self.geo.line_km(spec_req.place_d, spec_o.place_p) <= 30.0 else 1
                sc = (rt, self.geo.line_km(spec_o.place_d, spec_req.place_p), fin1, oid)
                if best_score is None or sc < best_score:
                    best_score = sc
            ok2, _, fin2 = self.chain_feasible(spec_req, spec_o, self.now + 15)
            if ok2:
                rt = 0 if self.geo.line_km(spec_o.place_d, spec_req.place_p) <= 30.0 else 1
                sc = (rt, self.geo.line_km(spec_req.place_d, spec_o.place_p), fin2, oid)
                if best_score is None or sc < best_score:
                    best_score = sc
        return best_score[3] if best_score is not None else None

    def post_hitch_pair(self, oid_a: str, gid_a: str, oid_b: str, gid_b: str) -> bool:
        oa, ob = self.orders[oid_a], self.orders[oid_b]
        pa, pb = self.posts[gid_a], self.posts[gid_b]
        stops_a = without_windows(pa["stops"], self.now)
        stops_b = without_windows(pb["stops"], self.now)
        audience: Audience = {
            "experienced": pa["audience"]["experienced"] or pb["audience"]["experienced"],
            "manualLicence": pa["audience"]["manualLicence"] or pb["audience"]["manualLicence"],
        }
        schedule, single_open_sum, ref_sum = self.hitch_schedule_for(oid_a, oid_b)
        self.single_open_since.pop(gid_a, None)
        self.single_open_since.pop(gid_b, None)
        self.leg_gigs.get(oid_a, {}).pop(0, None)
        self.leg_gigs.get(oid_b, {}).pop(0, None)
        self.outbox.append({"type": "withdraw", "gigId": gid_a})
        self.outbox.append({"type": "withdraw", "gigId": gid_b})
        post_action: PostAction = {"type": "post", "stops": stops_a + stops_b, "audience": audience, "schedule": schedule}
        self.outbox.append(post_action)
        self.stats["posts"] += 1
        self.send()
        pair_gigs = self.gigs_of(oid_a)
        if not pair_gigs or pair_gigs != self.gigs_of(oid_b):
            self.stats["hitch_post_refused"] += 1
            for oid in (oid_a, oid_b):
                if oid in self.orders and undelivered(self.orders[oid]) and not self.gigs_of(oid):
                    self.post(self.orders[oid], undelivered(self.orders[oid]), self.saved_retry.get((oid, 0), Retry()), allow_pair=False)
            self.send()
            return False
        pair_gid = pair_gigs[0]
        thin_b = self.supply.get(ob["legs"][0]["pickup"]["placeId"], 0) < self.p.min_supply
        rt = self.geo.line_km(ob["legs"][0]["delivery"]["placeId"], oa["legs"][0]["pickup"]["placeId"]) <= 30.0
        self.hitch_gigs[pair_gid] = {
            "posted_at": self.now,
            "unbooked_since": self.now,
            "orders": [oid_a, oid_b],
            "single_open_sum": single_open_sum,
            "single_ref_sum": ref_sum,
            "thin_b": thin_b,
            "round_trip": rt,
        }
        self.hitch_ever_paired.add(oid_a)
        self.hitch_ever_paired.add(oid_b)
        self.stats["hitch_posted"] += 1
        if thin_b:
            self.stats["hitch_posted_thin_b"] += 1
        if rt:
            self.stats["hitch_posted_rt"] += 1
        if oid_a in self.hitch_quote_reqs or oid_b in self.hitch_quote_reqs:
            self.stats["hitch_quote_paired"] += 1
        return True

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
        post = self.posts.get(gig_id)
        if post is not None:
            for stop in post["stops"]:
                if self.leg_gigs.get(stop["orderId"], {}).get(stop["leg"]) == gig_id:
                    self.leg_gigs[stop["orderId"]].pop(stop["leg"], None)
        self.outbox.append({"type": "withdraw", "gigId": gig_id})
        for oid in oids:
            if oid in self.orders and undelivered(self.orders[oid]) and not self.gigs_of(oid):
                self.post(self.orders[oid], undelivered(self.orders[oid]), self.saved_retry.get((oid, 0), Retry()), allow_pair=False)

    def tick_hitch(self) -> None:
        p = self.p
        for gid in sorted(list(self.hitch_gigs.keys())):
            if gid in self.booked:
                continue
            info = self.hitch_gigs[gid]
            if daytime_minutes(info["unbooked_since"], self.now, p.day_start, p.day_end) >= p.hitch_patience_min:
                self.split_hitch_gig(gid, reason="patience")

        has_outbox_single = any(
            a["type"] == "post" and len(a["stops"]) == 2 and len(order_ids_of(a)) == 1
            for a in self.outbox
        )
        if has_outbox_single and (self.hitch_newly_won or self.single_open_since):
            self.send()

        waiting = self.waiting_single_orders()
        newly_won = set(self.hitch_newly_won)
        self.hitch_newly_won.clear()
        if len(waiting) < 2:
            return

        aged: set[str] = set()
        for oid, gid in waiting:
            since = self.single_open_since.get(gid, self.now)
            if daytime_minutes(since, self.now, p.day_start, p.day_end) >= p.hitch_after_min:
                aged.add(oid)

        triggers = aged | newly_won
        if not triggers:
            return

        specs: dict[str, CarSpec] = {}
        gid_of: dict[str, str] = {}
        for oid, gid in waiting:
            sp = self.car_spec_for_order(self.orders[oid])
            if sp is not None:
                specs[oid] = sp
                gid_of[oid] = gid

        candidates: list[tuple[int, int, float, int, int, str, str]] = []
        oids = sorted(specs.keys())
        for oid_a in oids:
            sa = specs[oid_a]
            sup_a = self.supply.get(sa.place_p, 0)
            for oid_b in oids:
                if oid_a == oid_b:
                    continue
                if oid_a not in triggers and oid_b not in triggers:
                    continue
                pair_key = (min(oid_a, oid_b), max(oid_a, oid_b))
                if pair_key in self.hitch_split_pairs:
                    continue
                sb = specs[oid_b]
                ok, _, fin = self.chain_feasible(sa, sb, self.now)
                if not ok:
                    continue
                hq_prio = 0 if (oid_b in self.hitch_quote_reqs or oid_a in self.hitch_quote_reqs or oid_b in self.return_reqs) else 1
                rt_prio = 0 if self.geo.line_km(sb.place_d, sa.place_p) <= 30.0 else 1
                gap_km = self.geo.line_km(sa.place_d, sb.place_p)
                candidates.append((hq_prio, rt_prio, gap_km, -sup_a, fin, oid_a, oid_b))

        if not candidates:
            return
        candidates.sort()
        used: set[str] = set()
        for _, _, _, _, _, oid_a, oid_b in candidates:
            if oid_a in used or oid_b in used:
                continue
            ok_a, cur_ga = self.can_order_hitch(oid_a)
            ok_b, cur_gb = self.can_order_hitch(oid_b)
            if not (ok_a and ok_b and cur_ga == gid_of[oid_a] and cur_gb == gid_of[oid_b]):
                continue
            if self.post_hitch_pair(oid_a, gid_of[oid_a], oid_b, gid_of[oid_b]):
                used.add(oid_a)
                used.add(oid_b)

    def handle_cancelled_hitch(self, event: OrderCancelledEvent) -> None:
        oid = event["orderId"]
        self.orders.pop(oid, None)
        self.hitch_newly_won.discard(oid)

        kept_outbox: list[Action] = []
        orphan_oids: list[str] = []
        for a in self.outbox:
            if a["type"] == "post" and any(s["orderId"] == oid for s in a["stops"]):
                for other_id in order_ids_of(a):
                    if other_id != oid:
                        orphan_oids.append(other_id)
                continue
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

    # --- stage 2: booked-delivery tracking & return offers -------------------------------------------
    def clear_gig_tracking(self, gig_id: str) -> None:
        self.booked_deliveries.pop(gig_id, None)
        self.gig_driver.pop(gig_id, None)
        self.gig_booked_at.pop(gig_id, None)
        self.gig_started_at.pop(gig_id, None)
        self.gig_late_pickup.pop(gig_id, None)

    def update_gig_deliveries(self, gig_id: str) -> None:
        driver_id = self.gig_driver.get(gig_id)
        post = self.posts.get(gig_id)
        if not driver_id or not post or gig_id not in self.booked:
            self.booked_deliveries.pop(gig_id, None)
            return
        drv = self.drivers.get(driver_id)
        home = drv["homePlaceId"] if drv else None
        t = self.gig_started_at.get(gig_id, self.gig_booked_at.get(gig_id, self.now))
        cur_place: Optional[str] = home if gig_id in self.gig_started_at else None

        entries: list[dict[str, Any]] = []
        for idx, s in enumerate(post["stops"]):
            oid, leg, skind = s["orderId"], s["leg"], s["kind"]
            order = self.orders.get(oid)
            req = self.requests.get(oid)
            leg_info = order["legs"][leg] if order and leg < len(order["legs"]) else (req["legs"][leg] if req and leg < len(req["legs"]) else None)
            if leg_info is None:
                continue
            stop_info = leg_info["pickup"] if skind == "pickup" else leg_info["delivery"]
            place_id = stop_info["placeId"]
            extra = (30 if s.get("withPlates") else 0) + (40 if s.get("withCharging") else 0)

            if skind == "pickup":
                pk = self.gig_picked_up.get((gig_id, oid, leg))
                if pk is not None:
                    t = pk[0]
                    cur_place = pk[1]
                else:
                    if cur_place is not None:
                        t += self.geo.minutes(cur_place, place_id)
                    elif home is not None:
                        t = max(t, self.gig_booked_at.get(gig_id, self.now) + self.geo.minutes(home, place_id))
                    t = max(t, stop_info["window"]["from"])
                    if "window" in s:
                        t = max(t, s["window"]["from"])
                    if idx == 0 and gig_id in self.gig_late_pickup:
                        t = max(t, self.gig_late_pickup[gig_id])
                    if not stop_info["privateAddress"] and stop_info.get("hours"):
                        t = next_open_minute(t, stop_info["hours"])
                    t += extra
                    cur_place = place_id
            else:
                dl = self.gig_delivered_legs.get((gig_id, oid, leg))
                if dl is not None:
                    t = dl[0]
                    cur_place = dl[1]
                    entries.append({
                        "gig_id": gig_id,
                        "driver_id": driver_id,
                        "order_id": oid,
                        "leg": leg,
                        "place_id": dl[1],
                        "planned_at": dl[0],
                        "delivered": True,
                    })
                elif order and order["deliveredAt"][leg] is not None:
                    dat = order["deliveredAt"][leg]
                    assert dat is not None
                    t = dat
                    cur_place = place_id
                    entries.append({
                        "gig_id": gig_id,
                        "driver_id": driver_id,
                        "order_id": oid,
                        "leg": leg,
                        "place_id": place_id,
                        "planned_at": dat,
                        "delivered": True,
                    })
                else:
                    if cur_place is not None:
                        t += self.geo.minutes(cur_place, place_id)
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
            is_homebound = self.geo.line_km(drv["homePlaceId"], deliv_place) <= 30.0
            if p.return_min_deliv_supply > 0 and self.supply.get(deliv_place, 0) < p.return_min_deliv_supply and not is_homebound:
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
            home_prio = 0 if is_homebound else 1
            ranked.append((home_prio, dist_km, planned_at, drv_id, out_gid))
        ranked.sort()
        return [(drv_id, out_gid, planned_at, dist_km) for _, dist_km, planned_at, drv_id, out_gid in ranked]

    def send_return_offers(self) -> None:
        p = self.p
        if p.return_offer_km <= 0 or self.level < 3:
            return
        candidate_orders = sorted(self.return_reqs | (self.hitch_quote_reqs if p.hitch_thin_solo_open > 0 else set()))
        for order_id in candidate_orders:
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
        for order_id in candidate_orders:
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
            open_gigs = [
                g for g in self.gigs_of(order_id)
                if g not in self.booked and g in self.posts and len(order_ids_of(self.posts[g])) == 1
            ]
            if not open_gigs:
                continue
            gig_id = open_gigs[0]
            post = self.posts[gig_id]
            audience = post["audience"]
            fee = max(1, int(req["referenceFeeCents"] * pickups(post) / len(order["legs"]) * p.return_offer_mult + 0.5))
            seen_drv: set[str] = set()
            for _, _, _, drv_id, stage in due_cands:
                if drv_id in seen_drv or drv_id in self.open_gig_offers[gig_id] or (gig_id, drv_id) in self.offered_pairs:
                    continue
                seen_drv.add(drv_id)
                drv = self.drivers.get(drv_id)
                if not drv:
                    continue
                if audience["experienced"] and not (drv["rating"] >= 4.8 and drv["completedGigs"] >= 50):
                    continue
                if audience["manualLicence"] and drv["licence"] != "manual":
                    continue
                if self.open_offer_count(gig_id) >= 3:
                    self.stats["ret_limit_gig"] += 1
                    break
                if self.offers_sent[(drv_id, day)] >= 3:
                    self.stats["ret_limit_driver"] += 1
                    continue
                self.outbox.append({"type": "offer", "gigId": gig_id, "driverId": drv_id, "feeCents": fee})
                self.offers_sent[(drv_id, day)] += 1
                self.open_gig_offers[gig_id].add(drv_id)
                self.offered_pairs.add((gig_id, drv_id))
                self.return_offer_gigs[gig_id] = order_id
                if order_id not in self.return_offered_orders:
                    self.return_offered_orders.add(order_id)
                    self.stats["ret_offered_orders"] += 1
                self.return_sent_stage.add((order_id, drv_id, stage))
                self.stats["offers"] += 1
                self.stats["ret_offered"] += 1
                if drv_id == target_drv:
                    break

    def tick_chain_pairs(self) -> None:
        if not (self.p.day_start <= self.now % DAY < self.p.day_end):
            return
        for gid, paired_at in list(self.chain_pairs.items()):
            if gid in self.booked:
                self.chain_pairs.pop(gid, None)
                continue
            post = self.posts.get(gid)
            if post is None or not any(self.leg_gigs.get(s["orderId"], {}).get(s["leg"]) == gid for s in post["stops"]):
                self.chain_pairs.pop(gid, None)
                continue
            if daytime_minutes_between(paired_at, self.now, self.p.day_start, self.p.day_end) >= self.p.chain_patience_min:
                self.chain_pairs.pop(gid, None)
                self.stats["chain_pair_split"] += 1
                self.outbox.append({"type": "withdraw", "gigId": gid})
                oids = order_ids_of(post)
                for stop in post["stops"]:
                    self.leg_gigs.get(stop["orderId"], {}).pop(stop["leg"], None)
                for oid in oids:
                    self.chain_split_orders[oid] += 1
                    if oid in self.orders and undelivered(self.orders[oid]):
                        self.post(self.orders[oid], undelivered(self.orders[oid]), Retry(), allow_pair=False)

    def try_pair_lead_car(self, order: Order, legs: list[int], retry: Retry) -> bool:
        p = self.p
        if not p.lead_car or self.level < 3:
            return False
        if len(legs) != 1 or len(order["legs"]) != 1 or retry != Retry():
            return False
        if order["option"] == "same_day" or order["id"] in self.urgent or order["id"] in self.lost:
            return False
        if order["id"] in self.hitch_quote_reqs or order["id"] in self.return_reqs:
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
                    and oid not in self.hitch_quote_reqs
                    and oid not in self.return_reqs
                    and other["option"] != "same_day"
                    and oid not in self.urgent
                    and not self.requests.get(oid, {}).get("note")
                ):
                    pa = other["legs"][0]["pickup"]["placeId"]
                    da = other["legs"][0]["delivery"]["placeId"]
                    same_par = other["deadline"] // DAY == order["deadline"] // DAY and self.geo.line_km(pa, pb) <= p.lead_car_max_gap_km and self.geo.line_km(da, db) <= p.lead_car_max_deliv_gap_km
                    same_chn = p.chain_pair_km > 0 and (self.geo.line_km(da, pb) <= p.chain_pair_km or self.geo.line_km(db, pa) <= p.chain_pair_km)
                    if same_par or same_chn:
                        self.send()
                        break

        best: Optional[tuple[int, float, int, str, Order, PostAction, list[StopRef], bool]] = None
        for gig_id, action in list(self.posts.items()):
            if gig_id in self.booked or len(action["stops"]) != 2:
                continue
            other_id = action["stops"][0]["orderId"]
            if other_id == order["id"] or other_id in self.urgent or other_id in self.lost or other_id in self.hitch_quote_reqs or other_id in self.return_reqs:
                continue
            if self.leg_gigs.get(other_id, {}).get(action["stops"][0]["leg"]) != gig_id:
                continue
            other_order = self.orders.get(other_id)
            if other_order is None or len(other_order["legs"]) != 1 or undelivered(other_order) != [0]:
                continue
            if other_order["option"] == "same_day":
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
            if other_order["deadline"] // DAY == order["deadline"] // DAY and gap_p <= p.lead_car_max_gap_km and gap_d <= p.lead_car_max_deliv_gap_km:
                drive_a = self.geo.minutes(pa, da)
                deadhead_da_to_pb = self.geo.minutes(da, pb)
                total_min = drive_a + deadhead_da_to_pb + drive_b + 4 * 15
                if total_min <= 540:
                    start_at = max(
                        self.now,
                        other_order["legs"][0]["pickup"]["window"]["from"],
                        order["legs"][0]["pickup"]["window"]["from"],
                    )
                    if start_at + total_min + 240 <= min(order["deadline"], other_order["deadline"]):
                        cand = (0, gap_p + gap_d, total_min, gig_id, other_order, action, without_windows(action["stops"], self.now) + stops_b, False)
                        if best is None or cand[:3] < best[:3]:
                            best = cand
                continue

            if p.chain_pair_km > 0 and self.chain_split_orders[order["id"]] < 2 and self.chain_split_orders[other_id] < 2:
                stops_a = without_windows(action["stops"], self.now)
                for o1, s1, o2, s2 in ((other_order, stops_a, order, stops_b), (order, stops_b, other_order, stops_a)):
                    p1, d1 = o1["legs"][0]["pickup"]["placeId"], o1["legs"][0]["delivery"]["placeId"]
                    p2, d2 = o2["legs"][0]["pickup"]["placeId"], o2["legs"][0]["delivery"]["placeId"]
                    if self.supply.get(p1, 0) < self.supply.get(p2, 0):
                        continue
                    gap_mid = self.geo.line_km(d1, p2)
                    if gap_mid > p.chain_pair_km:
                        continue
                    gap_ret = self.geo.line_km(d2, p1)
                    if gap_ret > max(45.0, self.geo.line_km(d1, p1) + 20.0):
                        continue
                    drv1 = self.geo.minutes(p1, d1)
                    dh = self.geo.minutes(d1, p2)
                    drv2 = self.geo.minutes(p2, d2)
                    if drv1 + dh + drv2 > 660:
                        continue
                    start1 = max(self.now + 15, o1["legs"][0]["pickup"]["window"]["from"])
                    if start1 + 180 > o1["lastPickupAt"] or start1 + drv1 + 30 > o1["deadline"]:
                        continue
                    arr2 = max(start1 + drv1 + 15 + dh, o2["legs"][0]["pickup"]["window"]["from"])
                    if arr2 > o2["legs"][0]["pickup"]["window"]["to"] or not site_open_at(o2["legs"][0]["pickup"], arr2):
                        continue
                    if arr2 + drv2 + 15 + 180 > o2["deadline"]:
                        continue
                    cand = (1, gap_mid + 0.25 * gap_ret, drv1 + dh + drv2, gig_id, o1, action, s1 + s2, True)
                    if best is None or cand[:3] < best[:3]:
                        best = cand

        if best is None:
            return False
        _, _, _, gig_id, first_order, action, stops, is_chain = best
        other_order = self.orders[action["stops"][0]["orderId"]]
        self.chain_pairs.pop(gig_id, None)
        self.single_open_since.pop(gig_id, None)
        self.leg_gigs.get(other_order["id"], {}).pop(0, None)
        self.outbox.append({"type": "withdraw", "gigId": gig_id})
        audience: Audience = {
            "experienced": action["audience"]["experienced"] or any(leg["car"]["premium"] for leg in order["legs"]),
            "manualLicence": action["audience"]["manualLicence"] or note_flags(req["note"], v2=p.notes_v2).manual,
        }
        post_action: PostAction = {"type": "post", "stops": stops, "audience": audience, "schedule": []}
        post_action["schedule"] = self.fees_for(first_order, 2, post_action)
        self.outbox.append(post_action)
        self.stats["posts"] += 1
        self.send()
        if not self.gigs_of(order["id"]):
            self.post(other_order, undelivered(other_order), Retry(), allow_pair=False)
            return False
        if is_chain:
            new_gid = self.gigs_of(order["id"])[0]
            self.chain_pairs[new_gid] = self.now
            self.stats["chain_pair_paired"] += 1
        else:
            self.stats["lead_car_paired"] += 1
        return True

    def post(self, order: Order, legs: list[int], retry: Retry = Retry(), allow_pair: bool = True) -> None:
        if allow_pair and self.p.lead_car and order["id"] not in self.hitch_quote_reqs and order["id"] not in self.return_reqs and self.try_pair_lead_car(order, legs, retry):
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
        self.gig_posted_at.setdefault(gig_id, self.now)
        if self.p.return_offer_km > 0 and len(order_ids_of(action)) == 1:
            oid = action["stops"][0]["orderId"]
            if oid in self.return_reqs:
                self.return_offer_gigs[gig_id] = oid
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
            self.chain_pairs.pop(gig_id, None)
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

    def sort_actions(self, actions: list[Action]) -> list[Action]:
        if not self.p.post_priority or len(actions) <= 1:
            return actions
        posts = [a for a in actions if a["type"] == "post"]
        if len(posts) <= 1:
            return actions
        def post_key(a: PostAction) -> tuple[int, int, int]:
            oids = order_ids_of(a)
            is_pair = 0 if len(oids) > 1 else 1
            has_sd = 0 if any(oid in self.orders and (self.orders[oid]["option"] == "same_day" or oid in self.urgent) for oid in oids) else 1
            min_lp = min((self.orders[oid]["lastPickupAt"] for oid in oids if oid in self.orders), default=10 ** 9)
            return (is_pair, has_sd, min_lp)
        posts.sort(key=post_key)
        it = iter(posts)
        return [next(it) if a["type"] == "post" else a for a in actions]

    def send(self) -> None:
        """Sends the outbox now (live mode always; practice only when the desk needs a gig id at once)."""
        actions, self.outbox = self.sort_actions(self.outbox), []
        if actions:
            self.read_results(actions, self.world.act(actions))

    def take_outbox(self) -> list[Action]:
        actions, self.outbox = self.sort_actions(self.outbox), []
        return actions

    def read_results(self, actions: list[Action], results: list[ActionResult]) -> None:
        for action, result in zip(actions, results):
            if result["ok"] is True:
                if action["type"] == "post":
                    self.carry(action, result["id"])
            else:
                self.stats[f"refused_{action['type']}"] += 1

    # --- restart (live mode) --------------------------------------------------------------------------
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

    def rejoin(self, snapshot: DeskSnapshot, history: list[DeskEvent]) -> None:
        """Rebuilds the books from the world after a (re)start, then answers what it missed."""
        self.ends_at = snapshot.get("endsAt", 14280)
        posted: dict[str, list[Gig]] = {}
        gigs_by_id = {g["id"]: g for g in snapshot["gigs"]}
        self.booked = {g["id"] for g in snapshot["gigs"] if g["status"] in ("booked", "working", "done")}
        for gig in snapshot["gigs"]:
            self.gig_posted_at[gig["id"]] = gig["postedAt"]
            if gig["status"] in ("booked", "working") and gig.get("driverId"):
                self.booked_driver[gig["id"]] = gig["driverId"]
            for oid in order_ids_of(gig):
                posted.setdefault(oid, []).append(gig)
            if gig["status"] in ("open", "booked", "working"):
                self.carry({"type": "post", "stops": gig["stops"], "audience": gig["audience"], "schedule": gig["schedule"]}, gig["id"])
        self.requests = {e["request"]["id"]: e["request"] for e in history if e["kind"] == "price_request"}
        for req in self.requests.values():
            self.dealer_request_count[req["dealerId"]] += 1
        if self.p.urgent_hygiene:
            self.urgent = set()
            for e in history:
                if e["kind"] == "deadline_close":
                    self.urgent.add(e["orderId"])
                elif e["kind"] == "order_changed" and e["order"]["lastPickupAt"] - e["at"] > 3 * HOUR:
                    self.urgent.discard(e["order"]["id"])
        else:
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
                if pass_ext or pass_hub or (not self.p.hitch_quote and self.p.return_offer_km <= 0):
                    self.ext_ring_reqs.add(req_id)
                elif self.p.return_offer_km > 0:
                    self.return_reqs.add(req_id)
                else:
                    self.hitch_quote_reqs.add(req_id)
            elif self.supply.get(pickup, 0) < self.p.min_supply and self.p.ring_to_hub_same_day_min > 0:
                if self.supply.get(req["legs"][-1]["delivery"]["placeId"], 0) >= 200 and drive <= self.p.ring_to_hub_same_day_min:
                    self.ring_hub_same_day.add(req_id)

        for e in history:
            if e["kind"] == "gig_viewed":
                self.last_view[e["driverId"]] = e["at"]
            elif e["kind"] == "gig_booked":
                self.last_booked_fee[e["gigId"]] = e["feeCents"]
                if self.p.return_offer_km > 0:
                    self.gig_driver[e["gigId"]] = e["driverId"]
                    self.gig_booked_at[e["gigId"]] = e["at"]
            elif e["kind"] == "offer_answered":
                self.offers_sent[(e["driverId"], e["at"] // DAY)] += 1
                self.offered_pairs.add((e["gigId"], e["driverId"]))
            elif self.p.return_offer_km > 0:
                if e["kind"] in ("gig_dropped", "no_show"):
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
        if self.p.hitch or self.p.hitch_quote:
            self.rejoin_hitch(snapshot, history)
        if self.p.hitch_quote and self.p.return_offer_km > 0:
            # Distinguish thin orders that actually paired in a 2-car hitch gig from solo return orders
            for oid in list(self.return_reqs):
                if oid in self.hitch_ever_paired:
                    self.return_reqs.discard(oid)
                    self.hitch_quote_reqs.add(oid)
        if self.p.hitch_quote:
            for oid in self.hitch_quote_reqs:
                if oid in self.orders:
                    self.hitch_won_day[self.requests[oid]["respondBy"] // DAY] += 1
        if self.p.return_offer_km > 0:
            for gig in sorted(snapshot["gigs"], key=lambda g: self.gig_booked_at.get(g["id"], g["postedAt"])):
                if gig["status"] in ("booked", "working") and gig["driverId"]:
                    self.gig_driver[gig["id"]] = gig["driverId"]
                    self.gig_booked_at.setdefault(gig["id"], gig["postedAt"])
                    self.update_gig_deliveries(gig["id"])
                elif gig["status"] == "done":
                    self.gig_completed_at.setdefault(gig["id"], gig["postedAt"])
            for oid in self.return_reqs:
                if oid in self.orders:
                    self.return_wins_by_day[self.requests[oid]["respondBy"] // DAY] += 1
                    for gid in self.gigs_of(oid):
                        if gid in self.posts and len(order_ids_of(self.posts[gid])) == 1:
                            self.return_offer_gigs[gid] = oid
        for e in history:
            if e["kind"] == "gig_expired":
                g = gigs_by_id.get(e["gigId"])
                if g:
                    for s in g["stops"]:
                        oid = s["orderId"]
                        if not self.p.urgent_hygiene or oid not in self.orders or self.cannot_be_on_time(self.orders[oid]):
                            self.lost.add(oid)
        for order_id, order in self.orders.items():
            if undelivered(order) and not self.staffed(order) and (self.now > order["lastPickupAt"] or (self.p.urgent_hygiene and self.cannot_be_on_time(order))):
                self.lost.add(order_id)
        if self.p.chain_pair_km > 0:
            for gig in snapshot["gigs"]:
                if gig["status"] == "open":
                    oids = order_ids_of(gig)
                    if len(oids) >= 2 and oids[0] in self.orders and oids[1] in self.orders:
                        pa = self.orders[oids[0]]["legs"][0]["pickup"]["placeId"]
                        da = self.orders[oids[0]]["legs"][0]["delivery"]["placeId"]
                        pb = self.orders[oids[1]]["legs"][0]["pickup"]["placeId"]
                        db = self.orders[oids[1]]["legs"][0]["delivery"]["placeId"]
                        if not (self.geo.line_km(pa, pb) <= self.p.lead_car_max_gap_km and self.geo.line_km(da, db) <= self.p.lead_car_max_deliv_gap_km):
                            self.chain_pairs[gig["id"]] = gig["postedAt"]
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
def current_schedule_fee(schedule: list[FeeStep], minute: int) -> int:
    if not schedule:
        return 0
    cur = schedule[0]["feeCents"]
    for step in schedule:
        if step["at"] <= minute:
            cur = step["feeCents"]
        else:
            break
    return cur


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


def daytime_minutes_between(t0: int, t1: int, day_start: int, day_end: int) -> int:
    return daytime_minutes(t0, t1, day_start, day_end)


def site_open_at(stop_place: Any, minute: int) -> bool:
    if stop_place.get("privateAddress"):
        w = stop_place.get("window")
        return True if not w else (w["from"] <= minute <= w["to"])
    hours = stop_place.get("hours")
    if hours is None:
        w = stop_place.get("window")
        return True if not w else (w["from"] <= minute <= w["to"])
    wd = (minute // DAY) % 7
    tod = minute % DAY
    if wd == 6:
        return False
    if wd == 5:
        sat = hours.get("saturday")
        return bool(sat and sat["opens"] <= tod < sat["closes"])
    return wd in hours.get("weekdays", [0, 1, 2, 3, 4]) and hours["opens"] <= tod < hours["closes"]


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
