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
    Action, ActionResult, Audience, DeskEvent, DeskSnapshot, DriverProfile, FeeStep, Gig, Order, PostAction,
    PriceRequest, StopRef, TimeWindow,
)

from .geo import Geo
from .notes import note_flags, parse_note_v2, shift_business_days, window_from_note

HOUR, DAY = 60, 24 * 60

# Empirical-Bayes shrunk log-price lane factors fitted strictly out-of-sample on 64 Level-8 worlds
# (night-01..32 + final-01..32; zero dev or holdout worlds used).
LIM_LANE_PICKUP: dict[str, float] = {
    "espoo": 0.01801, "hameenlinna": -0.0375, "helsinki": -0.00067, "hyvinkaa": 0.01002, "joensuu": 0.03729,
    "jyvaskyla": -0.04095, "kajaani": 0.0, "kemi": 0.0, "kokkola": 0.00167, "kotka": -0.03791,
    "kouvola": -0.06463, "kuopio": -0.04077, "lahti": -0.03409, "lappeenranta": -0.02084, "lempaala": -0.04688,
    "mikkeli": -0.01258, "oulu": -0.04536, "pori": -0.02751, "porvoo": -0.00202, "raisio": -0.03281,
    "rauma": -0.01399, "rovaniemi": -0.03244, "salo": -0.05621, "savonlinna": 0.0, "seinajoki": 0.01883,
    "tampere": -0.03634, "turku": -0.03561, "vaasa": -0.01609, "vantaa": 0.03766, "ylivieska": 0.0,
}
LIM_LANE_DELIVERY: dict[str, float] = {
    "espoo": -0.05554, "hameenlinna": 0.02676, "helsinki": -0.06611, "hyvinkaa": -0.05914, "joensuu": 0.09158,
    "jyvaskyla": 0.05259, "kajaani": 0.13239, "kemi": 0.13471, "kokkola": 0.11852, "kotka": 0.08248,
    "kouvola": 0.078, "kuopio": 0.06653, "lahti": 0.04447, "lappeenranta": 0.0861, "lempaala": 0.0072,
    "mikkeli": 0.09635, "oulu": 0.05905, "pori": 0.09169, "porvoo": -0.0445, "raisio": 0.03204,
    "rauma": 0.06667, "rovaniemi": 0.09226, "salo": 0.04131, "savonlinna": 0.104, "seinajoki": 0.08591,
    "tampere": 0.02508, "turku": 0.03272, "vaasa": 0.08048, "vantaa": -0.10655, "ylivieska": 0.13922,
}


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
    live_from_min: int = 0            # practice only: the desk sits out until this minute, as in a live final it joins late
                                      # (the Sat 14:00 test final started at Thu 00:00 = 4320 with Mon-Wed lost); 0 = off
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
    # --- handling rules -----------------------------------------------------------------------------
    charge_min_km: float = 200.0      # rule 3: an EV under 30% charge needs a charging stop on a route over this
    notes_v2: bool = False            # v2 note reader + delivery hours / note deadlines shorten option slack
    note_unsure: str = "quote"        # "quote" or "decline" when a note has a time the reader cannot place
    # --- trust --------------------------------------------------------------------------------------
    trust_gain: float = 0.0           # multiply dealer's quote by 1 + trust_gain * count/100
    trust_invest: float = 0.0         # discount on safe requests for top 3 dealers, Mon-Wed
    trust_guard: bool = False         # decline same_day thin town or >300min if count >= 13
    # --- morning day supervisor (08:00 Mon-Fri) -----------------------------------------------------
    supervisor: bool = False          # master enable for 08:00 morning state supervisor
    sup_recover_frac: float = 0.0     # 0..1: at 08:00 Tue-Fri, recover mult toward yesterday's 08:00 mult after freeze
    sup_calm_ot: float = 0.965        # projected_on_time >= this (with low backlog/warns & free drivers) => calm day
    sup_calm_backlog: int = 3         # max unstaffed orders due within 24h for calm regime
    sup_calm_warns: int = 3           # max deadline_close warnings in prior 24h for calm regime
    sup_min_free_share: float = 0.80  # min share of roster not holding an active gig at 08:00 for calm/fri loosening
    sup_calm_sd_supply: int = 35      # same_day_min_supply on calm Tue-Fri days (0 = keep p.same_day_min_supply)
    sup_calm_slack_sub: int = 15      # subtract from min_slack_min on calm Tue-Fri days
    sup_calm_ret_supply: int = 0      # if > 0 (e.g. 40), return_hub_min_supply on calm days
    sup_calm_ret_drive: int = 0       # if > 0 (e.g. 280), return_hub_max_drive_min on calm days
    sup_stress_ot: float = 0.955      # projected_on_time < this => stressed day
    sup_stress_backlog: int = 6       # unstaffed orders due within 24h >= this => stressed day
    sup_stress_warns: int = 6         # deadline_close warnings in prior 24h >= this => stressed day
    sup_stress_sd_supply: int = 70    # min same_day_min_supply on stressed days (0 = keep p.same_day_min_supply)
    sup_stress_slack_add: int = 20    # add to min_slack_min on stressed days
    sup_emerg_unstaffed: int = 0      # 0 = off; if > 0 (e.g. 12) and warns >= sup_emerg_warns => emergency day
    sup_emerg_warns: int = 5          # warnings in prior 24h (with unstaffed >= sup_emerg_unstaffed) => emergency day
    sup_emerg_min_supply: int = 45    # min_supply on emergency days (also suspends ext_ring/return_hub)
    sup_emerg_sd_supply: int = 150    # same_day_min_supply on emergency days
    sup_emerg_slack_add: int = 50     # add to min_slack_min on emergency days
    sup_fri_ot: float = 0.965         # Fri 08:00 projected_on_time threshold for endgame slow-gate opening
    sup_fri_max_backlog: int = 5      # max total unstaffed orders at Fri 08:00 to open Friday surplus gates
    sup_fri_slow_min_supply: int = 0  # if > 0 (e.g. 3), Fri 08:00 surplus opens Monday-due slow options down to this supply
    sup_fri_sd_max_drive: int = 0     # if > 0 (e.g. 180), Fri 08:00 surplus relaxes fri_same_day_max_drive to this
    sup_fri_neutral_learn: bool = False  # if True, thin-town Friday surplus quotes skip learn() via ext_ring_reqs
    # --- r4-limits: live oracle limit estimator (events, dealer steps/trust, state-gated corridors) --
    lim_events: bool = False          # live Friday price-war unfreeze + optional outage/war snapback hooks
    lim_outage_mult: float = 1.20     # initial outage mult = clean mult x this inside confirmed 80km circle (< 18:00)
    lim_outage_max_mult: float = 2.35 # ceiling for local outage tracker (unlocks > 1.80 cap inside 80km outage only)
    lim_outage_target_win: float = 0.45  # target win share inside active 80km regional outage
    lim_outage_min_q: int = 9999      # min quote outcomes inside 80km circle today to confirm outage (9999 = off)
    lim_outage_min_wr: float = 0.80   # min win share inside 80km circle today to confirm outage
    lim_outage_diff_wr: float = 0.35  # min win-share excess over outside-circle quotes (when outside >= 4)
    lim_war_snapback: float = 0.0     # 0..1: 08:00 recovery of mult to pre-war morning open after confirmed war day
    lim_post_mon_war_min: float = 1.38  # min Tue 08:00 mult after a Monday price war (world base + <30% hike)
    lim_post_outage_snap: float = 0.0 # 0..1: 08:00 snap-down of outage-inflated mult toward yesterday's clean open
    lim_fri_war_unfreeze: bool = True # when lim_events: unfreeze Friday loss streak on healthy board (floor still guards)
    lim_dealer: bool = False          # zero-drift centered trust + wider dealer_adj bounds + cold-join calibration
    lim_trust_slope: float = 0.0035   # log-price slope on (dealer_trust[d] - lim_trust_ema) at level >= 8
    lim_trust_ema_alpha: float = 0.05 # online EMA rate of quoted dealer trust
    lim_comp_step: float = 0.0        # 08:00 log-step on dealer_adj after <30% (+step) or >=70% (-step) on >=10-req dealer
    lim_dealer_adj_min: float = 0.80  # wider dealer_adj floor when lim_dealer=True
    lim_dealer_adj_max: float = 1.40  # wider dealer_adj cap when lim_dealer=True
    lim_deadband_cap: float = 0.64    # Mon-Thu busy-dealer projected win-share threshold to add cliff guard bump
    lim_deadband_bump: float = 0.0    # fractional price bump when busy dealer approaches 70% competitor price-cut cliff
    lim_cold_join_mult: float = 1.50  # mult floor upon mid-week cold start (>=250 prior lost requests, 0 won orders)
    lim_corridor: bool = False        # state-gated out-of-sample lane factor + inbound-to-hub floor + floor sd spread
    lim_lane_neg_w: float = 0.55      # weight on negative lane_eff (inbound) when fleet has surplus capacity
    lim_cong_pos_w: float = 0.0       # weight on positive lane_eff (outbound) when fleet is congested
    lim_lane_comp_slope: float = 2.2  # target-win slope compensation in learn() so lane_mult induces zero mult drift
    lim_inb_fee_mult: float = 1.08    # expected_fee_mult for non-hub -> hub (supply>=200) floor when fleet has surplus
    lim_inb_max_unstaffed: int = 16   # max active unstaffed orders to allow inbound lane/floor discounting
    lim_inb_min_ot: float = 0.945     # min projected_on_time to allow inbound lane/floor discounting
    lim_floored_sd_prem: float = 0.10 # min (same_day / next_day - 1) spread when quote hits margin floor
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
        self.sup_days_done: set[int] = set()
        self.day_open_mult: dict[int, float] = {}
        self.day_max_streak: Counter = Counter()
        self.warn_times: list[int] = []
        self.drop_times: list[int] = []
        self.sup_regime: str = "init"
        self.sup_sd_supply: Optional[int] = None
        self.sup_min_slack: Optional[int] = None
        self.sup_ret_supply: Optional[int] = None
        self.sup_ret_drive: Optional[int] = None
        self.sup_emerg_active: bool = False
        self.sup_fri_surplus_active: bool = False
        self.sup_fri_thin_reqs: set[str] = set()
        # --- r4-limits state ---
        self.sorted_places: tuple[str, ...] = tuple(sorted(geo.places))
        self.circle_80: dict[str, frozenset[str]] = (
            {c: frozenset(geo.within(c, 80.0)) for c in self.sorted_places} if params.lim_events else {}
        )
        self.lim_days_done: set[int] = set()
        self.lim_day_open_mult: dict[int, float] = {}
        self.lim_outage_day: int = -1
        self.lim_outage_center: str = ""
        self.lim_outage_cur_mult: float = self.mult
        self.lim_outage_reqs: set[str] = set()
        self.lim_war_day: int = -1
        self.lim_req_quote_ratio: dict[str, float] = {}
        self.lim_day_outcomes: dict[int, list[tuple[str, bool, str, float, str, float]]] = defaultdict(list)
        self.dlr_day_tot: Counter = Counter()
        self.dlr_day_won: Counter = Counter()
        self.dlr_in_flight: Counter = Counter()
        self.lim_comp_steps: Counter = Counter()
        self.lim_trust_ema: float = 0.0
        self.lim_deadband_reqs: set[str] = set()
        self.lim_cold_join_checked: bool = False
        self.lim_req_lane_mult: dict[str, float] = {}

    # --- events ---------------------------------------------------------------------------------------
    def handle(self, event: DeskEvent) -> None:
        kind = event["kind"]
        if self.p.live_from_min and self.now < self.p.live_from_min:
            # not there yet: remember what a late join's rejoin() would rebuild from the history, and nothing else
            if kind == "price_request":
                req = event["request"]
                self.requests[req["id"]] = req
                self.dealer_request_count[req["dealerId"]] += 1
                self.dlr_day_tot[(req["dealerId"], req["arrivedAt"] // DAY)] += 1
            elif kind == "order_lost":
                self.lost_requests.add(event["requestId"])
            return
        if kind == "price_request":
            self.quote(event["request"])
        elif kind == "order_won":
            oid = event["order"]["id"]
            if oid in self.requests:
                req = self.requests[oid]
                self.dlr_day_won[(req["dealerId"], req["arrivedAt"] // DAY)] += 1
                if self.decided.get(oid) in ("quote", "floor") and self.dlr_in_flight[req["dealerId"]] > 0:
                    self.dlr_in_flight[req["dealerId"]] -= 1
            self.learn(oid, won=True)
            self.win(event["order"])
        elif kind == "order_lost":
            rid = event["requestId"]
            if rid in self.requests:
                req = self.requests[rid]
                if self.decided.get(rid) in ("quote", "floor") and self.dlr_in_flight[req["dealerId"]] > 0:
                    self.dlr_in_flight[req["dealerId"]] -= 1
            self.lost_requests.add(rid)
            self.learn(rid, won=False)
        elif kind == "order_changed":
            self.change(event["order"])
        elif kind == "order_cancelled":
            self.orders.pop(event["orderId"], None)
            self.deferred_orders.pop(event["orderId"], None)
            if self.p.lead_car:
                self.withdraw(event["orderId"])
            self.leg_gigs.pop(event["orderId"], None)
        elif kind == "visit_failed":
            self.stats["visit_failed"] += 1
            self.stats[f"visit_failed_{event['reason']}"] += 1
            self.retry(event["orderId"], event["leg"], event["reason"])
        elif kind == "gig_expired":
            self.stats["gig_expired"] += 1
            post = self.posts.get(event["gigId"])
            if post:
                for s in post["stops"]:
                    oid = s["orderId"]
                    if not self.p.urgent_hygiene or oid not in self.orders or self.cannot_be_on_time(self.orders[oid]):
                        self.lost.add(oid)
            self.repost(event["gigId"])
        elif kind == "deadline_close":
            self.stats["deadline_close"] += 1
            self.warn_times.append(self.now)
            self.raise_fees(event["orderId"])
        elif kind == "gig_booked":
            gid = event["gigId"]
            self.booked.add(gid)
            self.last_booked_fee[gid] = event["feeCents"]
            self.booked_driver[gid] = event["driverId"]
            for ok in [k for k in self.open_offers if k[0] == gid]:
                self.open_offers.pop(ok, None)
            self.stats["booked"] += 1
            if gid in self.chain_pairs:
                self.stats["chain_pair_booked"] += 1
            elif gid in self.posts and len(order_ids_of(self.posts[gid])) > 1:
                self.stats["lead_car_booked"] += 1
            post = self.posts.get(gid)
            if post:
                order_ids = list(dict.fromkeys(s["orderId"] for s in post["stops"]))
                ref_cents = sum(self.requests[o]["referenceFeeCents"] for o in order_ids if o in self.requests)
                self.stats["booked_fee_cents"] += event["feeCents"]
                self.stats["booked_ref_cents"] += ref_cents
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
            self.drop_times.append(self.now)
            post = self.posts.get(gid)
            if post:
                for order_id in dict.fromkeys(s["orderId"] for s in post["stops"]):
                    order = self.orders.get(order_id)
                    if order and undelivered(order) and self.now > order["lastPickupAt"]:
                        self.lost.add(order_id)
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
        elif kind == "gig_viewed":
            self.last_view[event["driverId"]] = event["at"]
            if self.p.view_offer_mult > 0:
                self.recent_views.append((event["at"], event["gigId"], event["driverId"]))
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
            if order and order["id"] in self.sup_fri_thin_reqs:
                self.stats["sup_fri_thin_margin_cents"] += line["cents"]
            if line["kind"] in ("late_refund", "undelivered_penalty") and line["orderId"]:
                if line["orderId"] not in self.late:
                    if is_ring:
                        self.stats["late_ring"] += 1
                    if order and order["option"] == "same_day" and line["orderId"] in self.ring_hub_same_day:
                        self.stats["late_ring_hub_same_day"] += 1
                    if is_ext_ring:
                        self.stats["late_ext_ring"] += 1
                    if line["orderId"] in self.sup_fri_thin_reqs:
                        self.stats["sup_fri_thin_late"] += 1
                self.late.add(line["orderId"])
                if dealer:
                    self.dealer_trust[dealer] //= 2
            elif line["kind"] == "revenue" and line["orderId"]:
                if dealer and line["orderId"] not in self.late:
                    if order and self.now <= order["deadline"]:
                        self.dealer_trust[dealer] = min(25, self.dealer_trust[dealer] + 1)
        elif kind == "offer_answered":
            self.stats[f"offer_{event['answer']}"] += 1
            tag = self.open_offers.pop((event["gigId"], event["driverId"]), None)
            if tag:
                self.stats[f"{tag}_offer_{event['answer']}"] += 1
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

    def maybe_supervise(self, allow_mult_recover: bool = True) -> None:
        """At 08:00 on each working day (Mon-Fri), reads board state (backlog, free drivers, wins/on-time,
        yesterday's warnings and freeze streak) and sets today's intake and recovery dials."""
        p = self.p
        if not p.supervisor:
            return
        day = self.now // DAY
        if day > 4 or self.now < day * DAY + 8 * HOUR or day in self.sup_days_done:
            return
        self.sup_days_done.add(day)
        self.stats["sup_calls"] += 1
        if day == 0:
            self.day_open_mult[0] = self.mult
            self.sup_regime = "mon_init"
            return

        if allow_mult_recover and p.sup_recover_frac > 0:
            prev = day - 1
            prev_open = self.day_open_mult.get(prev, self.mult)
            if self.day_max_streak[prev] > p.loss_streak_freeze and self.mult < prev_open:
                new_mult = clamp(self.mult + p.sup_recover_frac * (prev_open - self.mult), p.price_mult_min, p.price_mult_max)
                self.stats["sup_freeze_recoveries"] += 1
                self.stats[f"sup_recover_d{day}_bp"] = int(round((new_mult - self.mult) * 10000))
                self.mult = new_mult
        self.day_open_mult[day] = self.mult

        proj_ot = self.projected_on_time()
        unstaffed_orders = [o for o in self.orders.values() if undelivered(o) and not self.staffed(o)]
        unstaffed_all = len(unstaffed_orders)
        unstaffed_soon = sum(1 for o in unstaffed_orders if o["lastPickupAt"] - self.now <= 24 * HOUR)
        busy_gigs = sum(
            1
            for gid in self.booked
            if gid in self.posts and any(oid in self.orders and undelivered(self.orders[oid]) for oid in order_ids_of(self.posts[gid]))
        )
        free_drivers = max(0, len(self.drivers) - busy_gigs)
        free_share = free_drivers / max(1, len(self.drivers))
        window_start = self.now - 24 * HOUR
        warns_yday = sum(1 for t in self.warn_times if window_start < t <= self.now)

        self.stats[f"sup_d{day}_unstaffed"] = unstaffed_all
        self.stats[f"sup_d{day}_soon"] = unstaffed_soon
        self.stats[f"sup_d{day}_free_pct"] = int(round(free_share * 100))
        self.stats[f"sup_d{day}_ot_bp"] = int(round(proj_ot * 10000))
        self.stats[f"sup_d{day}_warns"] = warns_yday

        self.sup_sd_supply = None
        self.sup_min_slack = None
        self.sup_ret_supply = None
        self.sup_ret_drive = None
        self.sup_emerg_active = False
        self.sup_fri_surplus_active = False

        is_emergency = (
            p.sup_emerg_unstaffed > 0
            and unstaffed_all >= p.sup_emerg_unstaffed
            and warns_yday >= p.sup_emerg_warns
        )
        is_stressed = (
            is_emergency
            or proj_ot < p.sup_stress_ot
            or warns_yday >= p.sup_stress_warns
            or unstaffed_soon >= p.sup_stress_backlog
        )
        is_calm = (
            not is_stressed
            and proj_ot >= p.sup_calm_ot
            and warns_yday <= p.sup_calm_warns
            and unstaffed_soon <= p.sup_calm_backlog
            and free_share >= p.sup_min_free_share
        )
        if is_emergency:
            self.sup_emerg_active = True
            self.sup_regime = "emergency"
            self.stats["sup_days_emergency"] += 1
            self.stats[f"sup_d{day}_regime"] = -2
            if p.sup_emerg_sd_supply > 0:
                self.sup_sd_supply = max(p.same_day_min_supply, p.sup_emerg_sd_supply)
            if p.sup_emerg_slack_add != 0:
                self.sup_min_slack = p.min_slack_min + p.sup_emerg_slack_add
        elif is_stressed:
            self.sup_regime = "stressed"
            self.stats["sup_days_stressed"] += 1
            self.stats[f"sup_d{day}_regime"] = -1
            if p.sup_stress_sd_supply > 0:
                self.sup_sd_supply = max(p.same_day_min_supply, p.sup_stress_sd_supply)
            if p.sup_stress_slack_add != 0:
                self.sup_min_slack = p.min_slack_min + p.sup_stress_slack_add
        elif is_calm:
            self.sup_regime = "calm"
            self.stats["sup_days_calm"] += 1
            self.stats[f"sup_d{day}_regime"] = 1
            if p.sup_calm_sd_supply > 0:
                self.sup_sd_supply = p.sup_calm_sd_supply
            if p.sup_calm_slack_sub != 0:
                self.sup_min_slack = max(60, p.min_slack_min - p.sup_calm_slack_sub)
            if p.sup_calm_ret_supply > 0:
                self.sup_ret_supply = p.sup_calm_ret_supply
            if p.sup_calm_ret_drive > 0:
                self.sup_ret_drive = p.sup_calm_ret_drive
        else:
            self.sup_regime = "normal"
            self.stats["sup_days_normal"] += 1
            self.stats[f"sup_d{day}_regime"] = 0

        if (
            day == 4
            and not is_stressed
            and proj_ot >= p.sup_fri_ot
            and unstaffed_all <= p.sup_fri_max_backlog
            and warns_yday <= p.sup_calm_warns + 1
            and free_share >= p.sup_min_free_share
            and (p.sup_fri_slow_min_supply > 0 or p.sup_fri_sd_max_drive > 0)
        ):
            self.sup_fri_surplus_active = True
            self.sup_regime = "fri_surplus"
            self.stats["sup_fri_surplus_fired"] += 1
            self.stats[f"sup_d{day}_regime"] = 2

    def maybe_limit_morning(self, allow_mult_recover: bool = True) -> None:
        """At 08:00 on each working day (Mon-Fri), updates r4-limits morning state:
        mid-week cold-join calibration, post-war mult snapback, and exact competitor morning steps."""
        p = self.p
        if not (p.lim_events or p.lim_dealer):
            return
        if p.lim_dealer and not self.lim_cold_join_checked:
            self.lim_cold_join_checked = True
            if p.lim_cold_join_mult > 0 and self.now >= 2 * DAY and not self.orders and len(self.lost_requests) >= 250:
                if self.mult < p.lim_cold_join_mult:
                    self.mult = p.lim_cold_join_mult
                    self.stats["lim_cold_join_fired"] += 1
                if p.lim_comp_step > 0:
                    cur_d = self.now // DAY
                    for prev_d in range(min(4, cur_d)):
                        for dlr in sorted(self.dealer_request_count):
                            if self.dlr_day_tot[(dlr, prev_d)] >= 10 and self.lim_comp_steps[dlr] < 3:
                                self.lim_comp_steps[dlr] += 1
                                self.dealer_adj[dlr] = clamp(
                                    self.dealer_adj[dlr] * math.exp(p.lim_comp_step),
                                    p.lim_dealer_adj_min,
                                    p.lim_dealer_adj_max,
                                )
        day = self.now // DAY
        if day > 4 or self.now < day * DAY + 8 * HOUR or day in self.lim_days_done:
            return
        self.lim_days_done.add(day)
        if day == 0:
            self.lim_day_open_mult[0] = self.mult
            return

        prev = day - 1
        if p.lim_events and allow_mult_recover and p.lim_post_outage_snap > 0 and self.level >= 6:
            outs_prev = self.lim_day_outcomes.get(prev, [])
            prev_open = self.lim_day_open_mult.get(prev, self.mult)
            ref_open = max(prev_open, 1.48) if prev == 0 else prev_open
            if self.mult > ref_open + 0.04 and not hasattr(self, "_post_outage_snapped"):
                for c in self.sorted_places:
                    cset = self.circle_80[c]
                    inc = [x for x in outs_prev if x[0] in cset]
                    outc = [x for x in outs_prev if x[0] not in cset]
                    if len(inc) >= 15 and len(outc) >= 6:
                        w_in = sum(1 for x in inc if x[1]) / len(inc)
                        w_out = sum(1 for x in outc if x[1]) / len(outc)
                        if w_in >= 0.65 and w_in - w_out >= 0.32:
                            new_m = clamp(self.mult - p.lim_post_outage_snap * (self.mult - ref_open), p.price_mult_min, p.price_mult_max)
                            self._post_outage_snapped = prev
                            self.stats["lim_post_outage_snaps"] += 1
                            self.stats[f"lim_outsnap_d{day}_bp"] = int(round((self.mult - new_m) * 10000))
                            self.mult = new_m
                            break
        if p.lim_events and allow_mult_recover and p.lim_war_snapback > 0 and self.level >= 8:
            outs_prev = self.lim_day_outcomes.get(prev, [])
            is_war_prev = (
                self.lim_war_day == prev
                or (
                    prev != self.lim_outage_day
                    and self.day_max_streak[prev] > p.loss_streak_freeze
                    and len(outs_prev) >= 10
                    and (sum(1 for x in outs_prev if x[1]) / len(outs_prev)) <= 0.25
                )
            )
            if is_war_prev:
                target_open = self.lim_day_open_mult.get(prev, self.mult)
                if prev == 0 and p.lim_post_mon_war_min > 0:
                    target_open = max(target_open, p.lim_post_mon_war_min)
                if self.mult < target_open:
                    new_m = clamp(self.mult + p.lim_war_snapback * (target_open - self.mult), p.price_mult_min, p.price_mult_max)
                    self.stats["lim_war_snapbacks"] += 1
                    self.stats[f"lim_war_snap_d{day}_bp"] = int(round((new_m - self.mult) * 10000))
                    self.mult = new_m
        self.lim_day_open_mult[day] = self.mult

        if p.lim_dealer and p.lim_comp_step > 0 and allow_mult_recover:
            for dlr in sorted(self.dealer_request_count):
                n_prev = self.dlr_day_tot[(dlr, prev)]
                if n_prev < 10:
                    continue
                sh = self.dlr_day_won[(dlr, prev)] / n_prev
                if sh < 0.30 and self.lim_comp_steps[dlr] < 3:
                    self.lim_comp_steps[dlr] += 1
                    self.dealer_adj[dlr] = clamp(
                        self.dealer_adj[dlr] * math.exp(p.lim_comp_step),
                        p.lim_dealer_adj_min,
                        p.lim_dealer_adj_max,
                    )
                    self.stats["lim_comp_hikes"] += 1
                elif sh >= 0.70 and self.lim_comp_steps[dlr] > -3:
                    self.lim_comp_steps[dlr] -= 1
                    self.dealer_adj[dlr] = clamp(
                        self.dealer_adj[dlr] * math.exp(-p.lim_comp_step),
                        p.lim_dealer_adj_min,
                        p.lim_dealer_adj_max,
                    )
                    self.stats["lim_comp_cuts"] += 1

    def tick(self) -> None:
        """Called after every step (practice) or event (live)."""
        if self.p.live_from_min and self.now < self.p.live_from_min:
            return
        self.maybe_limit_morning()
        self.maybe_supervise()
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
                                self.outbox.append({"type": "reprice", "gigId": gig_id, "schedule": self.fees_for(order, pickups(post), post)})
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
        if self.deferred_orders:
            self.tick_deferred_posts()
        if self.p.chain_pair_km > 0 and self.chain_pairs:
            self.tick_chain_pairs()
        if self.p.dest_offer_mult > 0 or self.p.view_offer_mult > 0:
            self.tick_proactive_offers()

    # --- quoting --------------------------------------------------------------------------------------
    def quote(self, request: PriceRequest) -> None:
        self.maybe_limit_morning()
        self.maybe_supervise()
        self.requests[request["id"]] = request
        self.dealer_request_count[request["dealerId"]] += 1
        self.dlr_day_tot[(request["dealerId"], request["arrivedAt"] // DAY)] += 1
        prices, decision = self.price(request)
        self.stats[f"quote_{decision}"] += 1
        if self.level <= 3:  # every quote wins at its list price: send one only for what we take
            if prices:
                first = request["options"][0]
                self.outbox.append({"type": "quote", "requestId": request["id"], "prices": {first["kind"]: first["listPriceCents"]}})
            return
        self.decided[request["id"]] = decision
        if decision in ("quote", "floor"):
            self.dlr_in_flight[request["dealerId"]] += 1
        if prices:
            quoted_kind = next(iter(prices))
            quoted_option = next(o for o in request["options"] if o["kind"] == quoted_kind)
            ratio = prices[quoted_kind] / quoted_option["listPriceCents"]
            day = self.now // DAY
            self.stats[f"price_list_sum_d{day}"] += ratio
            self.stats[f"price_list_count_d{day}"] += 1
            if self.p.lim_events and decision == "quote":
                self.lim_req_quote_ratio[request["id"]] = ratio
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
        if p.supervisor and self.sup_emerg_active and p.sup_emerg_min_supply > 0:
            base_min_supply = max(p.min_supply, p.sup_emerg_min_supply)
        elif p.supervisor and self.sup_fri_surplus_active and p.sup_fri_slow_min_supply > 0 and (self.now // DAY) == 4:
            base_min_supply = p.sup_fri_slow_min_supply
        else:
            base_min_supply = p.min_supply
        gate_min = base_min_supply * (1 + (p.guard_supply_mult - 1) * tight)
        std_gate_min = p.min_supply * (1 + (p.guard_supply_mult - 1) * tight)
        drive = sum(self.geo.minutes(leg["pickup"]["placeId"], leg["delivery"]["placeId"]) for leg in legs)
        if len(legs) == 2:
            drive += self.geo.minutes(legs[0]["delivery"]["placeId"], legs[1]["pickup"]["placeId"])
        pass_ext_ring = False
        pass_return_hub = False
        fri_thin_only = False
        eff_ret_supply = self.sup_ret_supply if (p.supervisor and self.sup_ret_supply is not None) else p.return_hub_min_supply
        eff_ret_drive = self.sup_ret_drive if (p.supervisor and self.sup_ret_drive is not None) else p.return_hub_max_drive_min
        if gate_supply < gate_min:
            if p.supervisor and self.sup_emerg_active:
                self.stats["sup_emerg_declined"] += 1
                return {}, "decline"
            pass_ext_ring = (
                p.ext_ring_min_supply > 0
                and self.ext_supply.get(pickup, 0) >= p.ext_ring_min_supply
                and drive <= p.ext_ring_max_drive_min
            )
            pass_return_hub = (
                eff_ret_supply > 0
                and self.supply.get(legs[-1]["delivery"]["placeId"], 0) >= eff_ret_supply
                and drive <= eff_ret_drive
            )
            if not (pass_ext_ring or pass_return_hub):
                return {}, "decline"
            if self.backlog_near(pickup) + 1e-9 >= p.backlog_min:
                self.stats["declined_backlog"] += 1
                if p.backlog_in_flight_weight > 0 and self.backlog_near(pickup, include_in_flight=False) + 1e-9 < p.backlog_min:
                    self.stats["in_flight_blocked"] += 1
                return {}, "decline"
        else:
            if gate_supply < std_gate_min:
                fri_thin_only = True
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
        dlr = request["dealerId"]
        cur_day, cur_tod = self.now // DAY, self.now % DAY
        is_outage_quote = (
            p.lim_events
            and self.level >= 6
            and self.lim_outage_day == cur_day
            and cur_tod < 18 * HOUR
            and pickup in self.circle_80.get(self.lim_outage_center, ())
        )
        base_mult = self.lim_outage_cur_mult if is_outage_quote else self.mult
        mult = base_mult * self.dealer_adj[dlr]
        if p.trust_gain > 0:
            count = self.dealer_trust[dlr]
            mult *= (1 + p.trust_gain * count / 100.0)
        if p.lim_dealer and p.lim_trust_slope > 0 and self.level >= 8:
            t_cur = self.dealer_trust[dlr]
            mult *= math.exp(p.lim_trust_slope * (t_cur - self.lim_trust_ema))

        deadband_bump_active = False
        if p.lim_dealer and p.lim_deadband_bump > 0 and cur_day < 4:
            arr_day = request["arrivedAt"] // DAY
            n_dlr_today = self.dlr_day_tot[(dlr, arr_day)]
            if n_dlr_today >= 10:
                if (self.dlr_day_won[(dlr, arr_day)] / n_dlr_today) >= p.lim_deadband_cap:
                    mult *= (1.0 + p.lim_deadband_bump)
                    deadband_bump_active = True

        lane_mult = 1.0
        inb_surplus_ok = False
        is_inb_to_hub = False
        if p.lim_corridor:
            dest_place = legs[-1]["delivery"]["placeId"]
            unstaffed_now = sum(1 for o in self.orders.values() if undelivered(o) and not self.staffed(o))
            inb_surplus_ok = (unstaffed_now <= p.lim_inb_max_unstaffed and self.projected_on_time() >= p.lim_inb_min_ot)
            is_inb_to_hub = (supply < 200 and self.supply.get(dest_place, 0) >= 200)
            eff = LIM_LANE_PICKUP.get(pickup, 0.0) + LIM_LANE_DELIVERY.get(dest_place, 0.0)
            if eff < 0.0 and inb_surplus_ok and p.lim_lane_neg_w > 0:
                lane_mult = clamp(math.exp(p.lim_lane_neg_w * eff), 0.86, 1.0)
            elif eff > 0.0 and not inb_surplus_ok and p.lim_cong_pos_w > 0:
                lane_mult = clamp(math.exp(p.lim_cong_pos_w * eff), 1.0, 1.10)
            if lane_mult != 1.0:
                mult *= lane_mult

        is_invest = False
        if p.trust_invest > 0 and (self.now // DAY) <= 2 and self.dealer_trust[dlr] < 25 and supply >= 100 and not request.get("note"):
            top3 = sorted(self.dealer_request_count.keys(), key=lambda d: self.dealer_request_count[d], reverse=True)[:3]
            is_invest = dlr in top3

        eff_sd_supply = self.sup_sd_supply if (p.supervisor and self.sup_sd_supply is not None) else p.same_day_min_supply
        eff_min_slack = self.sup_min_slack if (p.supervisor and self.sup_min_slack is not None) else p.min_slack_min
        eff_fri_sd_drive = (
            p.sup_fri_sd_max_drive
            if (p.supervisor and self.sup_fri_surplus_active and p.sup_fri_sd_max_drive > 0 and (self.now // DAY) == 4)
            else p.fri_same_day_max_drive
        )

        std_floor = fee / (1 - p.min_margin_frac)
        eff_floor = std_floor
        if p.lim_corridor and is_inb_to_hub and inb_surplus_ok and p.lim_inb_fee_mult > 0:
            eff_floor = (request["referenceFeeCents"] * p.lim_inb_fee_mult) / (1 - p.min_margin_frac)

        prices: dict[str, int] = {}
        floored = False
        inb_floor_saved = False
        for option in request["options"]:
            ring_hub_sd = False
            if (pass_ext_ring or pass_return_hub or fri_thin_only) and option["kind"] == "same_day":
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
            if fri_thin_only and deadline // DAY < 7:
                continue
            if p.max_next_day_drive_min > 0 and drive > p.max_next_day_drive_min and not (fri_thin_only and deadline // DAY >= 7):
                if deadline // DAY <= ready // DAY + 1:
                    self.stats["dropped_next_day_long"] += 1
                    continue
            if p.thin_long_next_day_supply > 0 and not is_ring and supply < p.thin_long_next_day_supply and drive > p.long_drive_min and not (fri_thin_only and deadline // DAY >= 7):
                if deadline // DAY <= ready // DAY + 1:
                    self.stats["dropped_thin_long_next_day"] += 1
                    continue
            if eff_fri_sd_drive > 0 and ready // DAY >= 4 and option["kind"] == "same_day" and drive >= eff_fri_sd_drive:
                self.stats["dropped_fri_same_day"] += 1
                continue
            if p.long_drive_min > 0 and drive > p.long_drive_min:
                if deadline // DAY <= ready // DAY:
                    self.stats["dropped_long_drive"] += 1
                    continue
            if option["kind"] == "same_day" and eff_sd_supply > 0 and supply < eff_sd_supply and not ring_hub_sd:
                self.stats["dropped_same_day_supply"] += 1
                continue
            slack = deadline - ready - drive
            if slack < eff_min_slack + p.slack_per_drive * drive:
                self.stats["dropped_slack"] += 1
                continue
            if ring_hub_sd:
                self.stats["quoted_ring_hub_same_day"] += 1
                self.ring_hub_same_day.add(request["id"])

            option_mult = mult
            if is_invest and slack >= 360:
                option_mult *= (1 - p.trust_invest)
            if p.return_hub_discount > 0 and pass_return_hub and not pass_ext_ring:
                option_mult *= (1.0 - p.return_hub_discount)

            price = option["listPriceCents"] * option_mult * (1 + p.same_day_markup if option["kind"] == "same_day" else 1)
            if price < std_floor:
                floored = True
                if eff_floor < std_floor and price < std_floor:
                    inb_floor_saved = True
            if price < eff_floor:
                price = eff_floor
            prices[option["kind"]] = int(price + 0.5)
        if not prices:
            return {}, "decline"
        if p.lim_corridor and p.lim_floored_sd_prem > 0 and floored and "same_day" in prices and "next_day" in prices:
            min_sd = int(round(prices["next_day"] * (1.0 + p.lim_floored_sd_prem)))
            if prices["same_day"] < min_sd:
                prices["same_day"] = min_sd
                self.stats["lim_sd_prem_lifted"] += 1
        if inb_floor_saved:
            self.stats["lim_inb_floor_saved"] += 1
        if p.lim_dealer and p.lim_trust_slope > 0 and self.level >= 8:
            self.lim_trust_ema = (1.0 - p.lim_trust_ema_alpha) * self.lim_trust_ema + p.lim_trust_ema_alpha * self.dealer_trust[dlr]
        if is_outage_quote:
            self.lim_outage_reqs.add(request["id"])
        if deadband_bump_active:
            self.lim_deadband_reqs.add(request["id"])
            self.stats["lim_deadband_guarded"] += 1
        if lane_mult != 1.0:
            self.lim_req_lane_mult[request["id"]] = lane_mult
        if fri_thin_only:
            self.sup_fri_thin_reqs.add(request["id"])
            self.stats["sup_fri_thin_quoted"] += 1
            if p.sup_fri_neutral_learn:
                self.ext_ring_reqs.add(request["id"])
        if pass_ext_ring or pass_return_hub:
            self.ext_ring_reqs.add(request["id"])
            self.stats["quoted_ext_ring"] += 1
            if pass_return_hub:
                self.stats["quoted_return_hub"] += 1
        return prices, "floor" if floored else "quote"

    def learn(self, request_id: str, won: bool) -> None:
        """Moves the multiplier towards the price that wins `price_target_win` of the normal quotes."""
        if self.decided.get(request_id) != "quote":
            return
        if self.p.ext_ring_neutral_learn and request_id in self.ext_ring_reqs:
            self.stats["ext_ring_skipped_learn"] += 1
            return
        if self.p.ext_ring_no_learn and not won and request_id in self.ext_ring_reqs:
            return
        p, day = self.p, self.now // DAY
        if p.lim_events and request_id in self.lim_outage_reqs:
            self.stats["lim_outage_quoted"] += 1
            if won:
                self.stats["lim_outage_won"] += 1
            step_out = (1.0 - p.lim_outage_target_win) if won else -p.lim_outage_target_win
            self.lim_outage_cur_mult = clamp(
                self.lim_outage_cur_mult * math.exp(p.price_lr * step_out),
                self.mult,
                p.lim_outage_max_mult,
            )
            return
        if p.lim_dealer and request_id in self.lim_deadband_reqs and not won:
            return
        if day != self.streak_day:
            self.loss_streak, self.streak_day = 0, day
        self.loss_streak = 0 if won else self.loss_streak + 1
        if self.loss_streak > self.day_max_streak[day]:
            self.day_max_streak[day] = self.loss_streak
        eff_target = p.price_target_win
        if p.lim_corridor and p.lim_lane_comp_slope > 0:
            lm = self.lim_req_lane_mult.get(request_id, 1.0)
            if lm != 1.0:
                eff_target = clamp(p.price_target_win - p.lim_lane_comp_slope * math.log(lm), 0.15, 0.70)
        step = (1 - eff_target) if won else -eff_target
        frozen_skip = (not won and self.loss_streak > p.loss_streak_freeze)
        if frozen_skip and p.lim_events and p.lim_fri_war_unfreeze and day == 4:
            unstaffed_now = sum(1 for o in self.orders.values() if undelivered(o) and not self.staffed(o))
            if unstaffed_now <= 8 and self.projected_on_time() >= 0.945:
                frozen_skip = False
                self.stats["lim_fri_unfrozen"] += 1
        req = self.requests[request_id]
        dealer = req["dealerId"]
        pickup = req["legs"][0]["pickup"]["placeId"]
        d_log_m = 0.0
        d_log_dlr = 0.0
        if not frozen_skip:
            old_m = self.mult
            self.mult = clamp(self.mult * math.exp(p.price_lr * step), p.price_mult_min, p.price_mult_max)
            d_log_m = math.log(self.mult / old_m) if old_m > 0 else 0.0
            d_min = p.lim_dealer_adj_min if p.lim_dealer else p.dealer_adj_min
            d_max = p.lim_dealer_adj_max if p.lim_dealer else p.dealer_adj_max
            old_d = self.dealer_adj[dealer]
            self.dealer_adj[dealer] = clamp(old_d * math.exp(p.dealer_lr * step), d_min, d_max)
            d_log_dlr = math.log(self.dealer_adj[dealer] / old_d) if old_d > 0 else 0.0

        if p.lim_events and self.level >= 6 and day <= 4:
            outs = self.lim_day_outcomes[day]
            outs.append((pickup, won, request_id, d_log_m, dealer, d_log_dlr))
            if self.level >= 8 and self.lim_war_day < 0 and day != self.lim_outage_day and len(outs) >= 10:
                if (sum(1 for x in outs if x[1]) / len(outs)) <= 0.16:
                    self.lim_war_day = day
                    self.stats["lim_war_detected"] += 1
                    self.stats[f"lim_war_d{day}"] = 1
            if self.lim_outage_day < 0 and day != self.lim_war_day and (self.now % DAY) < 17 * HOUR:
                best_c = None
                for c in self.sorted_places:
                    cset = self.circle_80[c]
                    inc = [x for x in outs if x[0] in cset]
                    if len(inc) < p.lim_outage_min_q:
                        continue
                    w_in = sum(1 for x in inc if x[1]) / len(inc)
                    if w_in < p.lim_outage_min_wr:
                        continue
                    outc = [x for x in outs if x[0] not in cset]
                    w_out = (sum(1 for x in outc if x[1]) / len(outc)) if outc else 0.0
                    avg_r = sum(self.lim_req_quote_ratio.get(x[2], self.mult) for x in inc) / len(inc)
                    if (len(outc) >= 4 and w_in - w_out >= p.lim_outage_diff_wr) or (len(inc) >= 11 and w_in >= 0.82 and avg_r >= 1.52):
                        cand = (w_in, len(inc), c, inc)
                        if best_c is None or cand[:2] > best_c[:2]:
                            best_c = cand
                if best_c is not None:
                    _, _, c_star, inc_rows = best_c
                    self.lim_outage_day = day
                    self.lim_outage_center = c_star
                    in_log_sum = sum(x[3] for x in inc_rows)
                    if in_log_sum > 0:
                        self.mult = clamp(self.mult * math.exp(-in_log_sum), p.price_mult_min, p.price_mult_max)
                    d_min = p.lim_dealer_adj_min if p.lim_dealer else p.dealer_adj_min
                    d_max = p.lim_dealer_adj_max if p.lim_dealer else p.dealer_adj_max
                    for x in inc_rows:
                        if x[5] > 0:
                            self.dealer_adj[x[4]] = clamp(self.dealer_adj[x[4]] * math.exp(-x[5]), d_min, d_max)
                    self.lim_outage_cur_mult = clamp(self.mult * p.lim_outage_mult, self.mult, p.lim_outage_max_mult)
                    self.stats["lim_outage_detected"] += 1
                    self.stats[f"lim_outage_d{day}"] = 1

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
            pickup = order["legs"][0]["pickup"]["placeId"]
            if self.supply.get(pickup, 0) < self.p.min_supply:
                self.stats["won_ring"] += 1
            if order["option"] == "same_day" and order["id"] in self.ring_hub_same_day:
                self.stats["won_ring_hub_same_day"] += 1
            if self.gate_supply.get(pickup, 0) < self.p.min_supply:
                if order["id"] in self.sup_fri_thin_reqs:
                    self.stats["sup_fri_thin_won"] += 1
                else:
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
                self.post(order, undelivered(order))

    def repost(self, gig_id: str) -> None:
        action = self.posts.get(gig_id)
        if action is None or not any(self.leg_gigs.get(s["orderId"], {}).get(s["leg"]) == gig_id for s in action["stops"]):
            return
        self.chain_pairs.pop(gig_id, None)
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
        if order_id in self.deferred_orders:
            self.deferred_orders.pop(order_id, None)
            self.post(order, undelivered(order), allow_pair=False)
        self.send_post_of(order_id)
        for gig_id in list(self.gigs_of(order_id)):
            if gig_id not in self.booked and gig_id in self.posts and len(order_ids_of(self.posts[gig_id])) > 1:
                self.stats["lead_car_split"] += 1
                self.chain_pairs.pop(gig_id, None)
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
                sched = self.fees_for(order, pickups(self.posts[gig_id]), self.posts[gig_id])
                self.posts[gig_id] = {**self.posts[gig_id], "schedule": sched}
                self.outbox.append({"type": "reprice", "gigId": gig_id, "schedule": sched})
                self.offer(gig_id, order)

    def maybe_reprice_after_drop(self, gig_id: str, post: PostAction) -> None:
        if not any(self.leg_gigs.get(s["orderId"], {}).get(s["leg"]) == gig_id for s in post["stops"]):
            return
        oids = order_ids_of(post)
        if not oids or any(oid not in self.orders or oid in self.urgent or oid in self.lost for oid in oids):
            return
        until = min(self.orders[oid]["lastPickupAt"] for oid in oids) - 3 * HOUR
        if until - self.now < 60:
            return
        if len(oids) > 1:
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
            recent = self.now - self.last_view.get(d["id"], -10 ** 9) <= p.offer_recent_view_min
            candidates.append((0 if recent else 1, self.geo.minutes(d["homePlaceId"], pickup), d["id"]))
        candidates.sort()
        fee = int(self.requests[order["id"]]["referenceFeeCents"] * pickups(post) / len(order["legs"]) * p.offer_mult + 0.5)
        for _, _, driver_id in candidates[: min(3, p.offers_per_warning)]:
            self.outbox.append({"type": "offer", "gigId": gig_id, "driverId": driver_id, "feeCents": fee})
            self.offers_sent[(driver_id, day)] += 1
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
            if len(oids) > 1:
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
                open_cnt = sum(1 for k in self.open_offers if k[0] == gid)
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
                open_cnt = sum(1 for k in self.open_offers if k[0] == gid)
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
        if p.inbound_hub_fee_open > 0 and dest_supply >= 150 and until - self.now >= 2 * HOUR:
            fee_open_override = p.inbound_hub_fee_open
            self.stats["inbound_hub_posts"] += 1
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
            car_not_there = reason in ("not_ready", "closed")
            pickup_from = retry_from(order, self.requests[order_id], leg, self.now) if car_not_there else 0
            self.post(order, [leg], Retry(pickup_from, manual_licence=reason == "licence", plates=reason == "no_plates"))

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
            if other_id == order["id"] or other_id in self.urgent or other_id in self.lost:
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
        self.gig_posted_at.setdefault(gig_id, self.now)

    def withdraw(self, order_id: str) -> bool:
        self.send_post_of(order_id)
        gigs = self.gigs_of(order_id)
        if any(gig_id in self.booked for gig_id in gigs):
            return False
        self.leg_gigs.pop(order_id, None)
        self.outbox += [{"type": "withdraw", "gigId": gig_id} for gig_id in gigs]
        for gig_id in gigs:
            self.chain_pairs.pop(gig_id, None)
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
            self.dlr_day_tot[(req["dealerId"], req["arrivedAt"] // DAY)] += 1
        for e in history:
            if e["kind"] == "order_won":
                oid = e["order"]["id"]
                if oid in self.requests:
                    r_won = self.requests[oid]
                    self.dlr_day_won[(r_won["dealerId"], r_won["arrivedAt"] // DAY)] += 1
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
            elif e["kind"] == "gig_booked":
                self.last_booked_fee[e["gigId"]] = e["feeCents"]
            elif e["kind"] == "offer_answered":
                self.offers_sent[(e["driverId"], e["at"] // DAY)] += 1
                self.offered_pairs.add((e["gigId"], e["driverId"]))
            elif e["kind"] == "deadline_close":
                self.warn_times.append(e["at"])
            elif e["kind"] in ("gig_dropped", "no_show"):
                self.drop_times.append(e["at"])
        self.orders = {o["id"]: o for o in snapshot["orders"] if o["id"] in self.requests and o["status"] != "cancelled"}
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
        if self.p.lim_dealer and self.p.lim_trust_slope > 0 and self.level >= 8:
            for req in sorted(self.requests.values(), key=lambda r: r["arrivedAt"]):
                if self.gate_supply.get(req["legs"][0]["pickup"]["placeId"], 0) >= self.p.min_supply:
                    self.lim_trust_ema = (
                        (1.0 - self.p.lim_trust_ema_alpha) * self.lim_trust_ema
                        + self.p.lim_trust_ema_alpha * self.dealer_trust[req["dealerId"]]
                    )
        if self.p.lim_events and self.level >= 6:
            cur_d = self.now // DAY
            for prev_d in range(min(5, cur_d + 1)):
                day_reqs = [r for r in self.requests.values() if r["arrivedAt"] // DAY == prev_d and self.gate_supply.get(r["legs"][0]["pickup"]["placeId"], 0) >= self.p.min_supply]
                if not day_reqs:
                    continue
                for c in self.sorted_places:
                    cset = self.circle_80[c]
                    inc = [r for r in day_reqs if r["legs"][0]["pickup"]["placeId"] in cset]
                    outc = [r for r in day_reqs if r["legs"][0]["pickup"]["placeId"] not in cset]
                    if len(inc) >= 12 and len(outc) >= 6:
                        w_in = sum(1 for r in inc if r["id"] in self.orders) / len(inc)
                        w_out = sum(1 for r in outc if r["id"] in self.orders) / len(outc)
                        if w_in >= 0.65 and w_in - w_out >= 0.35:
                            self.lim_outage_day = prev_d
                            self.lim_outage_center = c
                            break
                if self.lim_outage_day >= 0:
                    break
        ratios = []  # the price level of the latest wins, so a restarted desk does not relearn from the prior
        for order in sorted(self.orders.values(), key=lambda o: self.requests[o["id"]]["arrivedAt"])[-30:]:
            req_o = self.requests[order["id"]]
            if self.p.lim_events and self.lim_outage_day >= 0 and (req_o["arrivedAt"] // DAY) == self.lim_outage_day:
                if req_o["legs"][0]["pickup"]["placeId"] in self.circle_80.get(self.lim_outage_center, ()):
                    continue
            option = next((o for o in req_o["options"] if o["kind"] == order["option"]), None)
            if option:
                denom = float(option["listPriceCents"])
                if self.p.lim_dealer and self.p.lim_trust_slope > 0 and self.level >= 8:
                    denom *= math.exp(self.p.lim_trust_slope * (self.dealer_trust[req_o["dealerId"]] - self.lim_trust_ema))
                ratios.append(order["priceCents"] / denom)
        if ratios:
            self.mult = clamp(median(ratios), self.p.price_mult_min, self.p.price_mult_max)
        if self.p.lim_events and self.lim_outage_day == (self.now // DAY) and (self.now % DAY) < 18 * HOUR:
            self.lim_outage_cur_mult = clamp(self.mult * self.p.lim_outage_mult, self.mult, self.p.lim_outage_max_mult)
        if self.p.lim_events or self.p.lim_dealer:
            cur_day = self.now // DAY
            self.lim_cold_join_checked = False
            self.maybe_limit_morning(allow_mult_recover=False)
            for prev_d in range(min(5, cur_day)):
                self.lim_days_done.add(prev_d)
                self.lim_day_open_mult[prev_d] = self.mult
                if self.p.lim_dealer and self.p.lim_comp_step > 0 and self.orders:
                    for dlr in sorted(self.dealer_request_count):
                        n_prev = self.dlr_day_tot[(dlr, prev_d)]
                        if n_prev >= 10:
                            sh = self.dlr_day_won[(dlr, prev_d)] / n_prev
                            if sh < 0.30 and self.lim_comp_steps[dlr] < 3:
                                self.lim_comp_steps[dlr] += 1
                                self.dealer_adj[dlr] = clamp(self.dealer_adj[dlr] * math.exp(self.p.lim_comp_step), self.p.lim_dealer_adj_min, self.p.lim_dealer_adj_max)
                            elif sh >= 0.70 and self.lim_comp_steps[dlr] > -3:
                                self.lim_comp_steps[dlr] -= 1
                                self.dealer_adj[dlr] = clamp(self.dealer_adj[dlr] * math.exp(-self.p.lim_comp_step), self.p.lim_dealer_adj_min, self.p.lim_dealer_adj_max)
            if cur_day <= 4 and self.now >= cur_day * DAY + 8 * HOUR:
                self.lim_days_done.add(cur_day)
                self.lim_day_open_mult[cur_day] = self.mult
        if self.p.supervisor:
            cur_day = self.now // DAY
            for prev_d in range(min(5, cur_day)):
                self.sup_days_done.add(prev_d)
                self.day_open_mult[prev_d] = self.mult
            if cur_day <= 4 and self.now >= cur_day * DAY + 8 * HOUR:
                self.maybe_supervise(allow_mult_recover=False)
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


def daytime_minutes_between(t0: int, t1: int, day_start: int, day_end: int) -> int:
    if t1 <= t0:
        return 0
    d0, d1 = t0 // DAY, t1 // DAY
    total = 0
    for d in range(d0, d1 + 1):
        lo = max(t0, d * DAY + day_start)
        hi = min(t1, d * DAY + day_end)
        if hi > lo:
            total += hi - lo
    return total


def site_open_at(stop_place: dict[str, Any], minute: int) -> bool:
    if stop_place.get("privateAddress"):
        w = stop_place.get("window")
        return True if not w else (w["from"] <= minute <= w["to"])
    hours = stop_place.get("hours")
    if hours is None:
        return True
    wd = (minute // DAY) % 7
    tod = minute % DAY
    if wd == 6:
        return False
    if wd == 5:
        sat = hours.get("saturday")
        return bool(sat and sat["opens"] <= tod < sat["closes"])
    return wd in hours.get("weekdays", [0, 1, 2, 3, 4]) and hours["opens"] <= tod < hours["closes"]


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
