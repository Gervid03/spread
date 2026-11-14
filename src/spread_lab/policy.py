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

# Out-of-sample Level-8 competitor log-price lane effects (fitted on 64 night+final worlds, 49,190 quotes; zero dev/holdout data)
LANE_PICKUP: dict[str, float] = {
    "espoo": 0.01801, "hameenlinna": -0.0375, "helsinki": -0.00067, "hyvinkaa": 0.01002, "joensuu": 0.03729,
    "jyvaskyla": -0.04095, "kajaani": 0.0, "kemi": 0.0, "kokkola": 0.00167, "kotka": -0.03791,
    "kouvola": -0.06463, "kuopio": -0.04077, "lahti": -0.03409, "lappeenranta": -0.02084, "lempaala": -0.04688,
    "mikkeli": -0.01258, "oulu": -0.04536, "pori": -0.02751, "porvoo": -0.00202, "raisio": -0.03281,
    "rauma": -0.01399, "rovaniemi": -0.03244, "salo": -0.05621, "savonlinna": 0.0, "seinajoki": 0.01883,
    "tampere": -0.03634, "turku": -0.03561, "vaasa": -0.01609, "vantaa": 0.03766, "ylivieska": 0.0,
}
LANE_DELIVERY: dict[str, float] = {
    "espoo": -0.05554, "hameenlinna": 0.02676, "helsinki": -0.06611, "hyvinkaa": -0.05914, "joensuu": 0.09158,
    "jyvaskyla": 0.05259, "kajaani": 0.13239, "kemi": 0.13471, "kokkola": 0.11852, "kotka": 0.08248,
    "kouvola": 0.078, "kuopio": 0.06653, "lahti": 0.04447, "lappeenranta": 0.0861, "lempaala": 0.0072,
    "mikkeli": 0.09635, "oulu": 0.05905, "pori": 0.09169, "porvoo": -0.0445, "raisio": 0.03204,
    "rauma": 0.06667, "rovaniemi": 0.09226, "salo": 0.04131, "savonlinna": 0.104, "seinajoki": 0.08591,
    "tampere": 0.02508, "turku": 0.03272, "vaasa": 0.08048, "vantaa": -0.10655, "ylivieska": 0.13922,
}
LANE_TERCILES: tuple[float, float] = (-0.0375, 0.0448)


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
    war_morning_reset: float = 0.0    # fraction (0..1) of war-day mult drop restored at the next morning boundary (0 = off)
    same_day_markup: float = 0.05     # extra on same_day prices (tight deadline, more risk)
    lane_prior_weight: float = 0.0    # 0 = off; tilt list price by clamp(exp(w * (pk_eff + dl_eff)), 0.85, 1.15)
    lane_pos_weight: float = -1.0     # if >= 0, weight used when pk_eff + dl_eff > 0 (asymmetric positive tilt)
    lane_prior_only_neg: bool = False # if True (and lane_pos_weight < 0), apply lane_prior_weight only when eff < 0
    lane_prior_comp_slope: float = 0.0  # if > 0, shift learn() target win rate by -slope * log(lane_mult) to keep mult neutral
    hub_inbound_fee_mult: float = 0.0 # if > 0, expected_fee_mult for floor on non-Hub -> Hub (pickup<200, deliv>=200)
    inbound_max_unstaffed: int = 0    # if > 0, pause inbound lane/floor discounts when total unstaffed active orders > this
    floored_sd_prem: float = 0.0      # if > 0, keep same_day >= next_day * (1 + prem) when next_day hits floor
    trust_center_slope: float = 0.0   # if > 0, zero-drift centered trust multiplier exp(slope * (trust - trust_ema))
    trust_ema_alpha: float = 0.05     # EMA step for mean quoted dealer trust when trust_center_slope > 0
    floored_sd_prem: float = 0.0      # minimum relative premium of same_day over slower options on multi-option quotes
    inbound_hub_disc: float = 0.0     # price discount on non-hub (<200) -> hub (>=200) return legs matching competitor cost
    inbound_hub_fee_mult: float = 0.0 # if > 0, expected_fee_mult for the floor on non-private non-hub (<200) -> hub (>=200)
    outbound_markup: float = 0.0      # price markup on hub->nonhub and long (>=180m) ->nonhub (1.5x when both)
    # --- selection: when to decline -----------------------------------------------------------------
    supply_radius_km: float = 30.0    # the app notifies drivers whose home is this close to the pickup
    gate_radius_km: float = 55.0      # radius of the supply count the decline gate uses (v1; 0 = supply_radius_km, as v0)
    far_options: str = "slow"         # "slow": quote next_day and within_3_days only for ring pickups (v1; v0 = "all")
    min_supply: int = 30              # decline below this many drivers near the pickup (6 missed 90% on 3/5 worlds; 20 on 1/32)
    expected_fee_mult: float = 1.25   # expected fee as a multiple of the typical fee
    slow_expected_fee_mult: float = 0.0  # if > 0, expected_fee_mult for next_day options
    w3d_expected_fee_mult: float = 0.0   # if > 0, expected_fee_mult for within_3_days and Mon2+ slow options
    w3d_discount: float = 0.0         # fractional price discount on within_3_days options
    mon2_discount: float = 0.0        # fractional price discount on slow options due Week-2 Monday+ (deadline >= 7*DAY)
    slow_comp_slope: float = 0.0      # win-target slope compensation in learn() for w3d/mon2 discounts
    min_margin_frac: float = 0.08     # price is raised to keep (price - expected fee) / price at least this
    min_margin_cents: int = 0         # if > 0, price is raised to keep (price - expected fee) at least this many cents
    min_slack_min: int = 180          # an option needs deadline - max(now, ready) - drive minutes >= this (v2: was 120)
    slack_per_drive: float = 0.5      # an option needs slack of at least min_slack_min + slack_per_drive * drive (v1; v0 = 0)
    trade_in_seq_slack: bool = False  # evaluate 2-leg trade-in slack sequentially (leg0 handoff then leg1 return)
    trade_in_max_drive_min: int = 450 # max total drive minutes when trade_in_seq_slack is True
    trade_in_leg1_slack_min: int = 90 # min post-handoff slack minutes on leg 1 when trade_in_seq_slack is True
    trade_in_handoff_pace: bool = False  # pace rising fees and early warning on 2-leg orders to leg0 handoff window
    long_drive_min: int = 300         # if drive > this (and > 0), quote only options with deadline on a later day than ready (v1; v0 = 0)
    live_from_min: int = 0            # practice only: the desk sits out until this minute, as in a live final it joins late
                                      # (the Sat 14:00 test final started at Thu 00:00 = 4320 with Mon-Wed lost); 0 = off
    max_next_day_drive_min: int = 0   # if > 0 and drive > this, drop options with deadline <= ready day + 1
    thin_long_next_day_supply: int = 0  # if > 0, non-ring pickup with supply < this and drive > long_drive_min drops next_day
    fri_same_day_max_drive: int = 0   # if > 0, on Friday (ready // DAY >= 4), drop same_day with drive >= this
    priv_pickup_min_slot_min: int = 0 # if > 0, decline/drop private pickups whose slot ends < this min after respondBy
    priv_pickup_sameday_only: bool = False  # if True, priv_pickup_min_slot_min drops only options due on/before the slot day
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
    return_hub_fee_open: float = 0.0  # if > 0, opening fee for non-hub (<200) -> hub (>=200) return legs with >= 2h to warning
    fix_slot_state: bool = False      # clear stale urgent/lost flags when order_changed/gig_expired still leaves order on-time
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
    # --- route network (idea 31: position ledger, finishing-driver offers, on-network quoting) ------
    net_offer: bool = False           # direct offers to our drivers finishing near an open gig's pickup
    net_km: float = 30.0              # max straight-line km from driver finish place to next pickup
    net_quote_km: float = 0.0         # > 0: override max km for thin net_quote sponsor (0 = net_km)
    net_fanout: int = 3               # max simultaneous open network offers per gig (<= 3)
    net_offer_mult: float = 0.80      # offer fee multiple of reference fee (non-home-bound)
    net_home_mult: float = 0.65       # offer fee multiple when gig ends within 30 km of driver's home
    net_lead_min: int = 60            # send offers within this many min of planned_finish (0 = at finish)
    net_offer_on_book: bool = False   # also offer pre-start while driver holds booked outbound gig
    net_offer_max_supply: int = 0     # > 0: offer immediately only where 30km supply < this (or aged/urgent)
    net_offer_min_age: int = 0        # > 0: on dense pickups, wait this many min open before offering
    net_viewer_offer: bool = False    # direct offer at board fee to drivers who viewed an aged/urgent gig
    net_viewer_min_age: int = 60      # min minutes open before sending viewer holdout-breaker offers
    net_quote: bool = False           # admit thin on-network slow requests & optional on-network discount
    net_discount: float = 0.0         # discount on gate-passing non-hub on-network quotes (0 = no discount)
    net_cap_day: int = 8              # max won thin on-network orders per day
    net_min_dest_supply: int = 0      # > 0: thin net_quote requires dest supply >= this or <=30km of home
    net_dest_use_gate: bool = False   # True: net_min_dest_supply checks 55km gate_supply instead of 30km supply
    net_one_to_one: bool = True       # each gig sponsors at most 1 active/in-flight thin net_quote order
    net_thin_fee_open: float = 0.0    # > 0: opening fee multiple for solo gigs of thin net_quote orders
    net_unblock_long_nd: bool = False # True: allow 300-420m next_day on supply < 50 when sponsored on-network
    net_seed: float = 0.0             # > 0: outbound discount from >=100 supply to >=seed_min demand towns
    seed_min: int = 6                 # min requests seen from a town since Mon 07:00 to qualify for net_seed
    seed_max_drive_min: int = 220     # > 0: max drive minutes for net_seed outbound discount
    net_relay: bool = False           # pre-booking 2-car route-chain pairing while outbound gig is still open
    net_relay_quote: bool = False     # quote thin-gate slow requests when an open outbound gig pairs homeward
    net_relay_cap_day: int = 6        # max won net_relay_quote orders per day
    net_relay_km: float = 15.0        # max straight-line km from A.delivery to B.pickup for 2-car relay
    net_relay_fee: float = 0.85       # relay pair opening fee multiple of (open_A + open_B)
    net_relay_after_min: int = 20     # daytime minutes open before re-scanning single gigs for relay pairing
    net_relay_patience_min: int = 30  # daytime minutes unbooked before splitting a relay pair back to solo
    net_relay_homeward: bool = True   # require B.delivery closer to A.pickup (<= max(60, line(da,pa)+25))
    net_relay_max_home_km: float = 0.0  # > 0: require B.delivery within this many km of A.pickup (true round-trip)
    net_relay_max_splits: int = 2     # max failed relay splits per order (0 = unlimited)
    net_relay_preserve_age: bool = True  # preserve car's first-posting age on rising schedule after split
    lead_car_allow_benign_notes: bool = False
    lead_car_cross_slow: bool = False
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
    # --- cp-wild mechanisms (all neutral by default) ------------------------------------------------
    decline_tradeins: bool = False    # decline 2-car trade-in requests (48.4% late rate + trust halving)
    future_sameday_slow: bool = False # treat 1-car dealer same_day with deadline on a future day as slow
    fut_sd_return_only: bool = False  # apply future_sameday_slow only on pass_return_hub return legs
    fut_sd_no_thin: bool = False      # do not apply future_sameday_slow to thin (<min_supply gate) pickups
    fut_sd_max_drive_min: int = 0     # if > 0, apply future_sameday_slow only when drive <= this
    fut_sd_min_deliv_supply: int = 0  # if > 0, apply future_sameday_slow only when delivery 30km supply >= this
    fut_sd_neutral_learn: bool = False  # skip learn() on requests admitted only via future_sameday_slow
    future_sameday_no_markup: bool = False  # omit same_day_markup on future-day dealer same_day options
    future_sameday_pair: bool = False # allow lead_car pairing on future-day same_day orders
    return_hub_major_supply: int = 0  # 0 = off; major-hub destination supply tier for longer return drives
    return_hub_major_max_drive_min: int = 0  # max drive min when delivery supply >= return_hub_major_supply
    return_hub_1leg_only: bool = False  # restrict expanded return_hub to 1-car requests
    return_hub_deliv_backlog_ratio: float = 0.0  # 0 = off; pause expanded return_hub when dest hub backlog/supply >= this
    return_hub_min_on_time: float = 0.0  # 0 = off; pause expanded return_hub when projected_on_time() < this
    return_hub_max_urgent: int = 0    # 0 = off; pause expanded return_hub when urgent unstaffed orders >= this
    floor_sd_gap: float = 0.0         # min relative price premium of today same_day above next_day after floor
    day_shock_lr: float = 0.0         # 0 = off; 08:00-18:00 80km daily shock kernel learning rate
    day_shock_radius_km: float = 80.0 # straight-line radius of daily shock kernel (matches 80km outage)
    day_shock_min: float = -0.22      # log-multiplier floor for daily shock kernel (matches -20% war)
    day_shock_max: float = 0.35       # log-multiplier cap for daily shock kernel (matches +30% outage)
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


@dataclass
class PosEntry:
    """Position ledger entry for a booked/working/completed gig."""
    gig_id: str
    driver_id: str
    home_place: str
    pickup_place: str
    finish_place: str
    booked_at: int
    planned_start: int
    planned_finish: int
    total_dur: int
    started: bool = False
    done: bool = False


class CarSpec(NamedTuple):
    """Single-car stop, window, hours, and drive specification for 2-car relay feasibility."""
    place_p: str
    place_d: str
    stop_p: Any
    stop_d: Any
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


def site_open_at(stop_place: Any, t: int) -> bool:
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


def next_site_open(stop_place: Any, t: int, limit: Optional[int] = None) -> Optional[int]:
    if site_open_at(stop_place, t):
        return t if (limit is None or t <= limit) else None
    if stop_place["privateAddress"] or stop_place["hours"] is None:
        w = stop_place["window"]
        if t < w["from"]:
            return w["from"] if (limit is None or w["from"] <= limit) else None
        return None
    h = stop_place["hours"]
    max_d = (limit // DAY) if limit is not None else (t // DAY + 8)
    for d in range(t // DAY, min(max_d, t // DAY + 8) + 1):
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
        cand = max(t, d * DAY + op)
        if cand < d * DAY + cl:
            return cand if (limit is None or cand <= limit) else None
    return None


def daytime_minutes(t0: int, t1: int, day_start: int, day_end: int) -> int:
    if t1 <= t0:
        return 0
    tot = 0
    for d in range(t0 // DAY, t1 // DAY + 1):
        lo = max(t0, d * DAY + day_start)
        hi = min(t1, d * DAY + day_end)
        if hi > lo:
            tot += hi - lo
    return tot


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
        self.trust_ema: float = 0.0
        self.inb_floor_saved_reqs: set[str] = set()
        self.congested_reqs: set[str] = set()
        self.loss_streak, self.streak_day = 0, -1
        self.war_open_mult: float = self.mult
        self.day_norm_quotes: int = 0
        self.day_norm_wins: int = 0
        self.war_reset_done: bool = False
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
        self.fut_sd_reqs: set[str] = set()           # request/order ids where future_sameday_slow unlocked same_day
        self.day_shock: dict[tuple[int, str], float] = defaultdict(float)  # (day, place) -> log-mult shock
        self._shock_nb_cache: dict[tuple[float, str], list[str]] = {}
        self.req_disc: dict[str, float] = {}         # request id -> average slow/Mon2 discount applied across quoted options
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
        # --- route network state ---------------------------------------------------------------------
        self.pos_ledger: dict[str, PosEntry] = {}
        self.order_first_posted_at: dict[str, int] = {}
        self.saved_retry: dict[tuple[str, int], Retry] = {}
        self.gig_viewers: dict[str, dict[str, int]] = defaultdict(dict)
        self.net_open_offers: dict[str, dict[str, tuple[int, bool, float, str]]] = defaultdict(dict)
        self.net_offered_pairs: set[tuple[str, str]] = set()
        self.offered_stages: set[tuple[str, str, str]] = set()
        self.declined_pairs: set[tuple[str, str]] = set()
        self.gig_cand_counted: set[str] = set()
        self.net_quote_reqs: set[str] = set()
        self.net_thin_reqs: set[str] = set()
        self.net_sponsor_gig: dict[str, str] = {}
        self.net_won_day: Counter = Counter()
        self.seed_reqs: set[str] = set()
        self.pickup_req_counts: Counter = Counter()
        self.driver_day_gigs_seen: set[tuple[str, int]] = set()
        self.driver_day_2plus: set[tuple[str, int]] = set()
        # --- pre-booking 2-car relay state -----------------------------------------------------------
        self.relay_gigs: dict[str, dict[str, Any]] = {}
        self.single_open_since: dict[str, int] = {}
        self.newly_won_relay: list[str] = []
        self.relay_split_pairs: set[tuple[str, str]] = set()
        self.relay_order_splits: Counter = Counter()
        self.relay_ever_paired: set[str] = set()
        self.relay_booked_orders: set[str] = set()
        self.relay_quote_reqs: set[str] = set()
        self.relay_quote_partner: dict[str, str] = {}
        self.relay_won_day: Counter = Counter()

    # --- events ---------------------------------------------------------------------------------------
    def handle(self, event: DeskEvent) -> None:
        kind = event["kind"]
        if self.p.live_from_min and self.now < self.p.live_from_min:
            # not there yet: remember what a late join's rejoin() would rebuild from the history, and nothing else
            if kind == "price_request":
                req = event["request"]
                self.requests[req["id"]] = req
                self.dealer_request_count[req["dealerId"]] += 1
            elif kind == "order_lost":
                self.lost_requests.add(event["requestId"])
            return
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
            self._refresh_pos_for_order(event["order"]["id"])
        elif kind == "order_cancelled":
            oid_c = event["orderId"]
            for cg in event.get("gigs", []):
                gid = cg["gigId"]
                if cg["outcome"] in ("withdrawn", "released"):
                    self.pos_ledger.pop(gid, None)
                    self.booked_driver.pop(gid, None)
                elif cg["outcome"] == "shortened" and gid in self.pos_ledger and gid in self.posts:
                    old = self.pos_ledger[gid]
                    rem = [s for s in self.posts[gid]["stops"] if s["orderId"] != oid_c]
                    rebuilt = self._build_pos_entry(gid, old.driver_id, rem, old.booked_at, old.started, old.done) if rem else None
                    if rebuilt is not None:
                        self.pos_ledger[gid] = rebuilt
                    else:
                        self.pos_ledger.pop(gid, None)
            self.orders.pop(oid_c, None)
            self.deferred_orders.pop(oid_c, None)
            if self.p.net_relay:
                self._handle_cancelled_relay(event)
            else:
                if self.p.lead_car:
                    self.withdraw(oid_c)
                self.leg_gigs.pop(oid_c, None)
        elif kind == "visit_failed":
            self.stats["visit_failed"] += 1
            self.stats[f"visit_failed_{event['reason']}"] += 1
            gid = event.get("gigId") or self.leg_gigs.get(event["orderId"], {}).get(event["leg"])
            if self.p.net_relay and gid:
                self.relay_gigs.pop(gid, None)
                if gid in self.posts and len(order_ids_of(self.posts[gid])) > 1:
                    rem = [s for s in self.posts[gid]["stops"] if not (s["orderId"] == event["orderId"] and s["leg"] == event["leg"])]
                    if rem:
                        self.posts[gid] = {**self.posts[gid], "stops": rem}
                        if gid in self.pos_ledger:
                            old = self.pos_ledger[gid]
                            rebuilt = self._build_pos_entry(gid, old.driver_id, rem, old.booked_at, old.started, old.done)
                            if rebuilt is not None:
                                self.pos_ledger[gid] = rebuilt
                    else:
                        self.posts.pop(gid, None)
                        self.booked.discard(gid)
                        self.pos_ledger.pop(gid, None)
                elif gid:
                    self.pos_ledger.pop(gid, None)
            elif gid:
                self.pos_ledger.pop(gid, None)
            self.retry(event["orderId"], event["leg"], event["reason"])
        elif kind == "gig_expired":
            self.stats["gig_expired"] += 1
            self.single_open_since.pop(event["gigId"], None)
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
            self.single_open_since.pop(gid, None)
            self.last_booked_fee[gid] = event["feeCents"]
            self.booked_driver[gid] = event["driverId"]
            for ok in [k for k in self.open_offers if k[0] == gid]:
                self.open_offers.pop(ok, None)
            self.net_open_offers.pop(gid, None)
            self.stats["booked"] += 1
            if gid in self.relay_gigs:
                info = self.relay_gigs[gid]
                self.stats["relay_booked"] += 1
                if info["thin_b"]:
                    self.stats["relay_booked_thin_b"] += 1
                self.stats["relay_booked_fee_cents"] += event["feeCents"]
                self.stats["relay_booked_ref_cents"] += info["ref_sum"]
                self.relay_booked_orders.update(info["orders"])
            elif gid in self.chain_pairs:
                self.stats["chain_pair_booked"] += 1
            elif gid in self.posts and len(order_ids_of(self.posts[gid])) > 1:
                self.stats["lead_car_booked"] += 1
            post = self.posts.get(gid)
            if post:
                pe = self._build_pos_entry(gid, event["driverId"], post["stops"], self.now)
                if pe is not None:
                    self.pos_ledger[gid] = pe
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
        elif kind == "gig_started":
            pe = self.pos_ledger.get(event["gigId"])
            if pe is not None:
                pe.started = True
                pe.planned_start = self.now
                pe.planned_finish = self.now + pe.total_dur
        elif kind == "driver_late":
            pe = self.pos_ledger.get(event["gigId"])
            if pe is not None:
                pe.planned_start = event["pickupAt"]
                pe.planned_finish = event["pickupAt"] + pe.total_dur
        elif kind == "picked_up":
            gid = event.get("gigId") or self.leg_gigs.get(event["orderId"], {}).get(event["leg"])
            if gid and gid in self.pos_ledger and gid in self.posts:
                pe = self.pos_ledger[gid]
                pe.started = True
                rem = self._remaining_dur_after_pickup(self.posts[gid]["stops"], event["orderId"], event["leg"])
                if rem is not None:
                    pe.planned_finish = event["at"] + rem
        elif kind in ("gig_dropped", "no_show"):
            gid = event["gigId"]
            self.booked.discard(gid)
            self.booked_driver.pop(gid, None)
            self.pos_ledger.pop(gid, None)
            self.stats[kind] += 1
            self.drop_times.append(self.now)
            relay_split_on_drop = False
            if self.p.net_relay:
                if gid in self.relay_gigs:
                    info = self.relay_gigs[gid]
                    info["unbooked_since"] = event["at"]
                    oids = info["orders"]
                    ok = all(oid in self.orders and oid not in self.urgent and undelivered(self.orders[oid]) == [0] for oid in oids)
                    if ok:
                        sa = self._car_spec_for_order(self.orders[oids[0]])
                        sb = self._car_spec_for_order(self.orders[oids[1]])
                        ok = sa is not None and sb is not None and self._relay_feasible(sa, sb, self.p.min_slack_min, self.now) is not None
                    if not ok:
                        self._split_relay_gig(gid, "drop")
                        relay_split_on_drop = True
                elif gid in self.posts and len(self.posts[gid]["stops"]) == 2 and len(order_ids_of(self.posts[gid])) == 1:
                    self.single_open_since[gid] = event["at"]
            post = self.posts.get(gid)
            if post:
                for order_id in dict.fromkeys(s["orderId"] for s in post["stops"]):
                    order = self.orders.get(order_id)
                    if order and undelivered(order) and self.now > order["lastPickupAt"]:
                        self.lost.add(order_id)
            rescued = False
            if self.p.drop_urgent_margin_min > 0 and post and not relay_split_on_drop:
                for order_id in dict.fromkeys(s["orderId"] for s in post["stops"]):
                    if (
                        order_id in self.orders
                        and undelivered(self.orders[order_id])
                        and self.orders[order_id]["lastPickupAt"] - self.now <= self.p.drop_urgent_margin_min
                    ):
                        self.stats["drop_rescued"] += 1
                        self.raise_fees(order_id)
                        rescued = True
            if not rescued and not relay_split_on_drop and gid not in self.relay_gigs and self.p.drop_reprice_bump >= 0.0 and post:
                self.maybe_reprice_after_drop(gid, post)
        elif kind == "gig_viewed":
            self.last_view[event["driverId"]] = event["at"]
            self.gig_viewers[event["gigId"]][event["driverId"]] = event["at"]
            if self.p.view_offer_mult > 0:
                self.recent_views.append((event["at"], event["gigId"], event["driverId"]))
        elif kind == "ledger":
            line = event["line"]
            oid = line.get("orderId", "")
            order = self.orders.get(oid) if oid else None
            dealer = self.requests[oid]["dealerId"] if oid and oid in self.requests else None
            req_for_line = self.requests.get(oid) if oid else None
            lane_b = self.lane_bucket(req_for_line) if req_for_line else None
            if lane_b is not None:
                self.stats[f"lane_margin_{lane_b}_cents"] += line["cents"]
            is_ring = order and self.supply.get(order["legs"][0]["pickup"]["placeId"], 0) < self.p.min_supply
            is_ext_ring = order and self.gate_supply.get(order["legs"][0]["pickup"]["placeId"], 0) < self.p.min_supply
            is_fut_sd = bool(order and line["orderId"] in self.fut_sd_reqs)
            is_trade_in = order and len(order["legs"]) == 2
            is_mon2 = order and order["option"] != "same_day" and order["deadline"] >= 7 * DAY
            if is_ring:
                self.stats["margin_ring_cents"] += line["cents"]
            if is_ext_ring:
                self.stats["margin_ext_ring_cents"] += line["cents"]
            if order and order["id"] in self.sup_fri_thin_reqs:
                self.stats["sup_fri_thin_margin_cents"] += line["cents"]
            if line["kind"] == "driver_fee" and line.get("gigId") in self.relay_gigs:
                info = self.relay_gigs[line["gigId"]]
                self.stats["relay_paid_gigs"] += 1
                self.stats["relay_paid_fee_cents"] += -line["cents"]
                self.stats["relay_paid_ref_cents"] += info["ref_sum"]
            if oid in self.net_quote_reqs:
                self.stats["margin_net_cents"] += line["cents"]
            if oid in self.net_thin_reqs:
                self.stats["margin_net_thin_cents"] += line["cents"]
            if oid in self.relay_quote_reqs:
                self.stats["margin_relay_quote_cents"] += line["cents"]
            if oid in self.seed_reqs:
                self.stats["margin_seed_cents"] += line["cents"]
            if is_fut_sd:
                self.stats["margin_fut_sd_cents"] += line["cents"]
            if is_trade_in:
                self.stats["margin_trade_in_cents"] += line["cents"]
            if is_mon2:
                self.stats["margin_mon2_cents"] += line["cents"]
            if line["kind"] in ("late_refund", "undelivered_penalty") and oid:
                if oid not in self.late:
                    if lane_b is not None:
                        self.stats[f"lane_late_{lane_b}"] += 1
                    if is_ring:
                        self.stats["late_ring"] += 1
                    if order and order["option"] == "same_day" and oid in self.ring_hub_same_day:
                        self.stats["late_ring_hub_same_day"] += 1
                    if is_ext_ring:
                        self.stats["late_ext_ring"] += 1
                    if oid in self.sup_fri_thin_reqs:
                        self.stats["sup_fri_thin_late"] += 1
                    if oid in self.net_quote_reqs:
                        self.stats["net_late"] += 1
                    if oid in self.net_thin_reqs:
                        self.stats["net_thin_late"] += 1
                    if oid in self.seed_reqs:
                        self.stats["seed_late"] += 1
                    if oid in self.relay_ever_paired:
                        self.stats["relay_late"] += 1
                    if oid in self.relay_booked_orders:
                        self.stats["relay_late_booked"] += 1
                    if oid in self.relay_quote_reqs:
                        self.stats["relay_quote_late"] += 1
                    if is_fut_sd:
                        self.stats["late_fut_sd"] += 1
                    if is_trade_in:
                        self.stats["late_trade_in"] += 1
                    if is_mon2:
                        self.stats["late_mon2"] += 1
                self.late.add(oid)
                if dealer:
                    self.dealer_trust[dealer] //= 2
            elif line["kind"] == "revenue" and oid:
                if dealer and oid not in self.late:
                    if order and self.now <= order["deadline"]:
                        self.dealer_trust[dealer] = min(25, self.dealer_trust[dealer] + 1)
        elif kind == "offer_answered":
            self.stats[f"offer_{event['answer']}"] += 1
            if event["answer"] == "declined":
                self.declined_pairs.add((event["gigId"], event["driverId"]))
            tag = self.open_offers.pop((event["gigId"], event["driverId"]), None)
            if tag:
                self.stats[f"{tag}_offer_{event['answer']}"] += 1
            meta = self.net_open_offers.get(event["gigId"], {}).pop(event["driverId"], None)
            if meta is not None:
                _, is_home, ratio_to_ref, okind = meta
                ans = event["answer"]
                if okind == "net":
                    self.stats[f"net_{ans}"] += 1
                    if is_home:
                        self.stats[f"net_home_{ans}"] += 1
                    if ans == "accepted":
                        self.stats["net_acc_fee_ratio_sum"] += ratio_to_ref
                        self.stats["net_acc_fee_ratio_n"] += 1
                elif okind == "viewer":
                    self.stats[f"viewer_{ans}"] += 1
        elif kind == "delivered":
            gid = event.get("gigId") or self.leg_gigs.get(event["orderId"], {}).get(event["leg"])
            if gid and gid in self.pos_ledger and gid in self.posts:
                stops = self.posts[gid]["stops"]
                if stops and stops[-1]["orderId"] == event["orderId"] and stops[-1]["leg"] == event["leg"] and stops[-1]["kind"] == "delivery":
                    pe = self.pos_ledger[gid]
                    pe.planned_finish = event["at"]
                    pe.done = True
                    dd = (pe.driver_id, event["at"] // DAY)
                    if dd in self.driver_day_gigs_seen and dd not in self.driver_day_2plus:
                        self.driver_day_2plus.add(dd)
                        self.stats["driver_days_2plus"] += 1
                    self.driver_day_gigs_seen.add(dd)
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
    # --- route network helpers -----------------------------------------------------------------------
    def _stop_place(self, stop: StopRef) -> Optional[str]:
        oid, leg_i, skind = stop["orderId"], stop["leg"], stop["kind"]
        src = self.orders[oid]["legs"] if oid in self.orders else (self.requests[oid]["legs"] if oid in self.requests else None)
        if src is None or leg_i >= len(src):
            return None
        return src[leg_i][skind]["placeId"]

    def _stops_dur(self, stops: list[StopRef]) -> Optional[tuple[list[str], int]]:
        places: list[str] = []
        for s in stops:
            pl = self._stop_place(s)
            if pl is None:
                return None
            places.append(pl)
        dur = sum(self.geo.minutes(places[i], places[i + 1]) for i in range(len(places) - 1))
        dur += sum((30 if s.get("withPlates") else 0) + (40 if s.get("withCharging") else 0) for s in stops if s["kind"] == "pickup")
        return places, dur

    def _build_pos_entry(
        self, gig_id: str, driver_id: str, stops: list[StopRef], booked_at: int, started: bool = False, done: bool = False
    ) -> Optional[PosEntry]:
        d = self.drivers.get(driver_id)
        if d is None or not stops:
            return None
        res = self._stops_dur(stops)
        if res is None:
            return None
        places, dur = res
        s0 = stops[0]
        oid0, leg0 = s0["orderId"], s0["leg"]
        src0 = self.orders[oid0]["legs"] if oid0 in self.orders else self.requests[oid0]["legs"]
        wfrom = s0["window"]["from"] if "window" in s0 else src0[leg0]["pickup"]["window"]["from"]
        p_start = max(booked_at, wfrom)
        return PosEntry(
            gig_id=gig_id,
            driver_id=driver_id,
            home_place=d["homePlaceId"],
            pickup_place=places[0],
            finish_place=places[-1],
            booked_at=booked_at,
            planned_start=p_start,
            planned_finish=p_start + dur,
            total_dur=dur,
            started=started,
            done=done,
        )

    def _remaining_dur_after_pickup(self, stops: list[StopRef], order_id: str, leg: int) -> Optional[int]:
        idx = next((i for i, s in enumerate(stops) if s["orderId"] == order_id and s["leg"] == leg and s["kind"] == "pickup"), None)
        if idx is None:
            return None
        sub = stops[idx:]
        res = self._stops_dur(sub)
        if res is None:
            return None
        _, dur = res
        # plates on the pickup just completed are already done; charging on road still applies
        if sub[0].get("withPlates"):
            dur = max(0, dur - 30)
        return dur

    def _refresh_pos_for_order(self, order_id: str) -> None:
        for gid, pe in list(self.pos_ledger.items()):
            post = self.posts.get(gid)
            if post and any(s["orderId"] == order_id for s in post["stops"]):
                rebuilt = self._build_pos_entry(gid, pe.driver_id, post["stops"], pe.booked_at, pe.started, pe.done)
                if rebuilt is not None:
                    if pe.started:
                        rebuilt.planned_start = pe.planned_start
                        rebuilt.planned_finish = pe.planned_start + rebuilt.total_dur
                    self.pos_ledger[gid] = rebuilt

    def _driver_gigs_on_day(self) -> Counter:
        cnt: Counter = Counter()
        for pe in self.pos_ledger.values():
            cnt[(pe.driver_id, pe.planned_finish // DAY)] += 1
            if pe.planned_start // DAY != pe.planned_finish // DAY:
                cnt[(pe.driver_id, pe.planned_start // DAY)] += 1
        return cnt

    def _current_board_fee(self, post: PostAction) -> int:
        sched = post.get("schedule", [])
        if not sched:
            return 0
        fee = sched[0]["feeCents"]
        for step in sched:
            if step["at"] <= self.now:
                fee = step["feeCents"]
            else:
                break
        return fee

    def _gig_ref_fee(self, post: PostAction) -> float:
        oids = order_ids_of(post)
        if len(oids) > 1:
            return float(sum(self.requests[o]["referenceFeeCents"] for o in oids if o in self.requests))
        oid = oids[0]
        req = self.requests.get(oid)
        order = self.orders.get(oid)
        if req is None or order is None:
            return 0.0
        return req["referenceFeeCents"] * pickups(post) / max(1, len(order["legs"]))

    def net_offer_tick(self) -> None:
        p = self.p
        if not (p.net_offer or p.net_viewer_offer) or self.level < 3:
            return
        tod = self.now % DAY
        if not (7 * HOUR <= tod < 21 * HOUR):
            return
        if p.net_offer and any(a["type"] == "post" for a in self.outbox):
            self._flush_non_quotes()

        day = self.now // DAY
        dd_counts = self._driver_gigs_on_day()
        busy_drivers: set[str] = {did for _, did in self.open_offers}
        for gid, omap in self.net_open_offers.items():
            if gid not in self.booked:
                for did, (sent_at, _, _, _) in omap.items():
                    if self.now - sent_at <= 10:
                        busy_drivers.add(did)

        for gig_id, post in list(self.posts.items()):
            if gig_id in self.booked:
                continue
            stops = post["stops"]
            if not stops:
                continue
            if not any(self.leg_gigs.get(s["orderId"], {}).get(s["leg"]) == gig_id for s in stops):
                continue
            oids = order_ids_of(post)
            first_order = self.orders.get(oids[0])
            if first_order is None:
                continue
            cp_open = sum(1 for k in self.open_offers if k[0] == gig_id)
            live_open = cp_open + sum(1 for sent_at, _, _, _ in self.net_open_offers.get(gig_id, {}).values() if self.now - sent_at <= 10)
            slots_left = min(3, p.net_fanout if p.net_offer else 3) - live_open
            if slots_left <= 0:
                continue

            res = self._stops_dur(stops)
            if res is None:
                continue
            places, gig_dur = res
            pickup, last_deliv = places[0], places[-1]
            sup30 = self.supply.get(pickup, 0)
            age = self.now - self.gig_posted_at.get(gig_id, self.now)
            is_urgent = any(o in self.urgent for o in oids)
            ref_base = self._gig_ref_fee(post)
            if ref_base <= 0:
                continue
            board_fee = self._current_board_fee(post)
            audience = post["audience"]
            s0 = stops[0]
            leg0 = first_order["legs"][s0["leg"]]
            p_from = s0["window"]["from"] if "window" in s0 else leg0["pickup"]["window"]["from"]
            p_to = s0["window"]["to"] if "window" in s0 else leg0["pickup"]["window"]["to"]
            min_deadline = min((self.orders[o]["deadline"] for o in oids if o in self.orders), default=first_order["deadline"])
            req_slack = 0 if is_urgent else p.min_slack_min

            # 1) Finishing-driver network offers
            if p.net_offer:
                allow_now = True
                if not is_urgent:
                    if p.net_offer_max_supply > 0 and sup30 >= p.net_offer_max_supply:
                        allow_now = False
                    elif p.net_offer_min_age > 0 and self.gate_supply.get(pickup, 0) >= p.min_supply and age < p.net_offer_min_age:
                        allow_now = False
                if allow_now:
                    cands: list[tuple[int, float, float, str, bool, str]] = []
                    seen_cands: set[str] = set()
                    for pe in self.pos_ledger.values():
                        if pe.done and (p.net_lead_min > 0 or self.now > pe.planned_finish):
                            continue
                        if not pe.started and not pe.done:
                            if not p.net_offer_on_book or pe.planned_finish // DAY != self.now // DAY:
                                continue
                            stage = "prestart"
                        else:
                            if p.net_lead_min == 0:
                                if not (pe.done and self.now == pe.planned_finish):
                                    continue
                            elif pe.planned_finish - self.now > p.net_lead_min:
                                continue
                            stage = "prefinish"
                        did = pe.driver_id
                        if did in seen_cands or did in busy_drivers:
                            continue
                        if (gig_id, did) in self.declined_pairs or (gig_id, did) in self.offered_pairs or (gig_id, did, stage) in self.offered_stages:
                            continue
                        if self.offers_sent[(did, day)] >= 3:
                            continue
                        if dd_counts[(did, pe.planned_finish // DAY)] >= 2:
                            continue
                        if self.geo.line_km(pe.home_place, pickup) <= 30.0:
                            continue
                        d = self.drivers.get(did)
                        if d is None:
                            continue
                        if audience["experienced"] and not (d["rating"] >= 4.8 and d["completedGigs"] >= 50):
                            continue
                        if audience["manualLicence"] and d["licence"] != "manual":
                            continue
                        dist_pick = self.geo.line_km(pe.finish_place, pickup)
                        if dist_pick > p.net_km:
                            continue
                        deadhead = self.geo.minutes(pe.finish_place, pickup)
                        avail_at = max(self.now, pe.planned_finish)
                        reach_at = avail_at + deadhead
                        p_limit = None if first_order["id"] in self.lost else p_to
                        start_g2 = next_site_open(leg0["pickup"], max(reach_at, p_from), p_limit)
                        if start_g2 is None:
                            continue
                        if start_g2 // DAY != pe.planned_finish // DAY or start_g2 - avail_at > 4 * HOUR:
                            continue
                        if first_order["id"] not in self.lost and min_deadline - (start_g2 + gig_dur) < req_slack:
                            continue
                        home_dist = self.geo.line_km(pe.home_place, last_deliv)
                        is_home = home_dist <= 30.0
                        seen_cands.add(did)
                        cands.append((0 if is_home else 1, round(home_dist, 2), round(dist_pick, 2), did, is_home, stage))

                    if gig_id not in self.gig_cand_counted:
                        self.gig_cand_counted.add(gig_id)
                        self.stats[f"net_cands_{min(3, len(cands))}"] += 1

                    cands.sort()
                    for _, _, _, did, is_home, stage in cands[:slots_left]:
                        mult_use = p.net_home_mult if is_home else p.net_offer_mult
                        fee_cents = max(1, int(ref_base * mult_use + 0.5))
                        if is_urgent and board_fee > fee_cents:
                            fee_cents = board_fee
                        ratio = fee_cents / ref_base
                        self.outbox.append({"type": "offer", "gigId": gig_id, "driverId": did, "feeCents": fee_cents})
                        self.offers_sent[(did, day)] += 1
                        self.net_offered_pairs.add((gig_id, did))
                        self.offered_stages.add((gig_id, did, stage))
                        self.net_open_offers[gig_id][did] = (self.now, is_home, ratio, "net")
                        busy_drivers.add(did)
                        self.stats["offers"] += 1
                        self.stats["net_offers"] += 1
                        self.stats[f"net_offers_{stage}"] += 1
                        if is_home:
                            self.stats["net_home_offers"] += 1
                        slots_left -= 1

            # 2) Viewer holdout-breaker offers on aged / urgent gigs
            if p.net_viewer_offer and slots_left > 0 and (is_urgent or age >= p.net_viewer_min_age) and board_fee > 0:
                v_cands: list[tuple[int, float, str]] = []
                for did, vat in self.gig_viewers.get(gig_id, {}).items():
                    if self.now - vat > 180 or did in busy_drivers:
                        continue
                    if (gig_id, did) in self.net_offered_pairs or (gig_id, did) in self.offered_pairs or self.offers_sent[(did, day)] >= 3:
                        continue
                    d = self.drivers.get(did)
                    if d is None:
                        continue
                    if audience["experienced"] and not (d["rating"] >= 4.8 and d["completedGigs"] >= 50):
                        continue
                    if audience["manualLicence"] and d["licence"] != "manual":
                        continue
                    reach_at = self.now + self.geo.minutes(d["homePlaceId"], pickup)
                    if first_order["id"] not in self.lost and reach_at > p_to:
                        continue
                    start_g = max(reach_at, p_from)
                    if first_order["id"] not in self.lost and min_deadline - (start_g + gig_dur) < req_slack:
                        continue
                    v_cands.append((self.now - vat, round(self.geo.line_km(d["homePlaceId"], last_deliv), 2), did))
                v_cands.sort()
                for _, _, did in v_cands[:slots_left]:
                    ratio = board_fee / ref_base
                    self.outbox.append({"type": "offer", "gigId": gig_id, "driverId": did, "feeCents": board_fee})
                    self.offers_sent[(did, day)] += 1
                    self.net_offered_pairs.add((gig_id, did))
                    self.net_open_offers[gig_id][did] = (self.now, False, ratio, "viewer")
                    busy_drivers.add(did)
                    self.stats["offers"] += 1
                    self.stats["viewer_offers"] += 1
                    slots_left -= 1

    def _busy_net_sponsors(self) -> set[str]:
        busy: set[str] = set()
        if not self.p.net_one_to_one:
            return busy
        for rid, sgid in self.net_sponsor_gig.items():
            if rid in self.orders:
                ord_r = self.orders[rid]
                if undelivered(ord_r) and not self.staffed(ord_r):
                    busy.add(sgid)
            elif rid not in self.lost_requests and rid in self.requests and self.now <= self.requests[rid]["respondBy"]:
                busy.add(sgid)
        return busy

    def _find_net_sponsor(
        self,
        request: PriceRequest,
        ready: int,
        drive: int,
        extra_days: int,
        thin_admission: bool,
    ) -> Optional[str]:
        p, legs = self.p, request["legs"]
        pickup = legs[0]["pickup"]["placeId"]
        if not thin_admission and self.supply.get(pickup, 0) >= 100:
            return None
        deliv = legs[-1]["delivery"]["placeId"]
        p_win = window_from_note(
            request["note"],
            legs[0]["pickup"]["window"],
            "pickup",
            v2=p.notes_v2,
            arrived_at=request["arrivedAt"],
            private_address=legs[0]["pickup"]["privateAddress"],
            stated_hours=legs[0]["pickup"]["hours"],
        )
        p_to = max(p_win["from"], p_win["to"])
        flags = note_flags(request["note"], v2=p.notes_v2)
        need_exp = any(leg["car"]["premium"] for leg in legs)
        need_man = flags.manual
        busy_sponsors = self._busy_net_sponsors() if thin_admission else set()
        dd_counts = self._driver_gigs_on_day()
        q_km = (p.net_quote_km if p.net_quote_km > 0 else p.net_km) if thin_admission else p.net_km

        opt_deadlines: list[tuple[str, int]] = []
        for opt in request["options"]:
            if thin_admission and opt["kind"] == "same_day":
                continue
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
            opt_deadlines.append((opt["kind"], dl))
        if not opt_deadlines:
            return None

        best: Optional[tuple[int, float, float, str]] = None
        for gid, pe in self.pos_ledger.items():
            if pe.done and self.now > pe.planned_finish:
                continue
            if thin_admission and gid in busy_sponsors:
                continue
            if dd_counts[(pe.driver_id, pe.planned_finish // DAY)] >= 2:
                continue
            if self.geo.line_km(pe.home_place, pickup) <= 30.0:
                continue
            d = self.drivers.get(pe.driver_id)
            if d is None:
                continue
            if need_exp and not (d["rating"] >= 4.8 and d["completedGigs"] >= 50):
                continue
            if need_man and d["licence"] != "manual":
                continue
            dist_pick = self.geo.line_km(pe.finish_place, pickup)
            if dist_pick > q_km:
                continue
            home_dist = self.geo.line_km(pe.home_place, deliv)
            if thin_admission and p.net_min_dest_supply > 0:
                dest_sup = self.gate_supply.get(deliv, 0) if p.net_dest_use_gate else self.supply.get(deliv, 0)
                if dest_sup < p.net_min_dest_supply and home_dist > 30.0:
                    continue
            if pe.planned_finish < ready - 3 * HOUR:
                continue
            avail_at = max(self.now, pe.planned_finish)
            reach_at = avail_at + self.geo.minutes(pe.finish_place, pickup)
            start_g2 = next_site_open(legs[0]["pickup"], max(reach_at, ready), p_to)
            if start_g2 is None:
                continue
            if start_g2 // DAY != pe.planned_finish // DAY or start_g2 - avail_at > 4 * HOUR:
                continue
            req_slack = p.min_slack_min + p.slack_per_drive * drive
            if not any(dl - start_g2 - drive >= req_slack for _, dl in opt_deadlines):
                continue
            cand_key = (0 if home_dist <= 30.0 else 1, round(home_dist, 2), round(dist_pick, 2), gid)
            if best is None or cand_key < best:
                best = cand_key
        return best[3] if best is not None else None

    def tick(self) -> None:
        """Called after every step (practice) or event (live)."""
        if self.p.live_from_min and self.now < self.p.live_from_min:
            return
        self.maybe_supervise()
        day = self.now // DAY
        if not hasattr(self, "_last_day"):
            self._last_day = day
            self.war_open_mult = self.mult
        elif day > self._last_day:
            if self.dealer_trust:
                self.stats[f"top_dealer_trust_d{self._last_day}"] = max(self.dealer_trust.values())
            if (
                self.p.war_morning_reset > 0
                and self.level >= 8
                and not self.war_reset_done
                and self.day_norm_quotes >= 15
                and (self.day_norm_wins / self.day_norm_quotes < 0.30 or self.mult < 0.88 * self.war_open_mult)
                and self.mult < self.war_open_mult
            ):
                target = self.mult + self.p.war_morning_reset * (self.war_open_mult - self.mult)
                self.mult = clamp(target, self.p.price_mult_min, self.p.price_mult_max)
                self.war_reset_done = True
                self.stats["war_morning_resets"] += 1
            self._last_day = day
            self.war_open_mult = self.mult
            self.day_norm_quotes = 0
            self.day_norm_wins = 0
        for order_id, order in list(self.orders.items()):
            open_legs = undelivered(order)
            if (
                self.p.trade_in_handoff_pace
                and len(order["legs"]) == 2
                and 0 in open_legs
                and not self.staffed(order)
                and order_id not in self.urgent
                and order_id not in self.lost
            ):
                d0 = self.geo.minutes(order["legs"][0]["pickup"]["placeId"], order["legs"][0]["delivery"]["placeId"])
                leg0_last_pk = order["legs"][0]["delivery"]["window"]["to"] - d0 - 15
                if leg0_last_pk - 3 * HOUR <= self.now <= leg0_last_pk:
                    self.stats["trade_in_early_warn"] += 1
                    self.raise_fees(order_id)
            if open_legs and not self.staffed(order) and self.now > order["lastPickupAt"]:
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
                        for gig_id in list(gigs):
                            if gig_id in self.relay_gigs:
                                self._split_relay_gig(gig_id, "lost")
                                self.send_post_of(order_id)
                        gigs = self.gigs_of(order_id)
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
        if self.p.net_relay and self.level >= 3:
            self._tick_relay()
        if self.p.dest_offer_mult > 0 or self.p.view_offer_mult > 0:
            self.tick_proactive_offers()
        self.net_offer_tick()

    # --- quoting --------------------------------------------------------------------------------------
    def lane_effect(self, request: PriceRequest) -> float:
        legs = request["legs"]
        return LANE_PICKUP.get(legs[0]["pickup"]["placeId"], 0.0) + LANE_DELIVERY.get(legs[-1]["delivery"]["placeId"], 0.0)

    def unstaffed_total(self) -> int:
        return sum(1 for o in self.orders.values() if undelivered(o) and not self.staffed(o))

    def lane_mult(self, request: PriceRequest, congested: bool = False) -> float:
        p = self.p
        if p.lane_prior_weight == 0.0 and p.lane_pos_weight < 0.0:
            return 1.0
        eff = self.lane_effect(request)
        if eff > 0.0:
            if p.lane_pos_weight >= 0.0:
                w = p.lane_pos_weight
            elif p.lane_prior_only_neg:
                return 1.0
            else:
                w = p.lane_prior_weight
        else:
            if congested:
                return 1.0
            w = p.lane_prior_weight
        if w == 0.0:
            return 1.0
        return clamp(math.exp(w * eff), 0.85, 1.15)

    def lane_bucket(self, request: PriceRequest) -> str:
        eff = self.lane_effect(request)
        t_lo, t_hi = LANE_TERCILES
        return "low" if eff < t_lo else ("mid" if eff < t_hi else "high")

    def quote(self, request: PriceRequest) -> None:
        self.maybe_supervise()
        self.requests[request["id"]] = request
        self.dealer_request_count[request["dealerId"]] += 1
        self.pickup_req_counts[request["legs"][0]["pickup"]["placeId"]] += 1
        prices, decision = self.price(request)
        self.stats[f"quote_{decision}"] += 1
        if self.level <= 3:  # every quote wins at its list price: send one only for what we take
            if prices:
                first = request["options"][0]
                self.outbox.append({"type": "quote", "requestId": request["id"], "prices": {first["kind"]: first["listPriceCents"]}})
            return
        self.decided[request["id"]] = decision
        if prices:
            self.stats[f"lane_quotes_{self.lane_bucket(request)}"] += 1
            t_count = self.dealer_trust[request["dealerId"]]
            t_diff = t_count - self.trust_ema
            if self.now // DAY >= 1:
                if t_diff < -5.0:
                    self.stats["quotes_trust_low"] += 1
                elif t_diff > 5.0:
                    self.stats["quotes_trust_high"] += 1
            self.trust_ema += self.p.trust_ema_alpha * (t_count - self.trust_ema)
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

    def _shock_neighbors(self, place: str) -> list[str]:
        key = (self.p.day_shock_radius_km, place)
        nbs = self._shock_nb_cache.get(key)
        if nbs is None:
            r = self.p.day_shock_radius_km
            nbs = [q for q in self.geo.places if self.geo.line_km(place, q) <= r]
            self._shock_nb_cache[key] = nbs
        return nbs

    def price(self, request: PriceRequest) -> tuple[dict[str, int], str]:
        """The prices to quote, and "quote", "floor" (a price raised to keep the margin) or "decline"."""
        p, legs = self.p, request["legs"]
        if p.decline_tradeins and len(legs) > 1:
            self.stats["declined_tradein"] += 1
            return {}, "decline"
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
        if p.priv_pickup_min_slot_min > 0 and not p.priv_pickup_sameday_only:
            if any(
                leg["pickup"]["privateAddress"]
                and leg["pickup"]["window"]["to"] - request["respondBy"] < p.priv_pickup_min_slot_min
                for leg in legs
            ):
                self.stats["declined_priv_pickup_slot"] += 1
                return {}, "decline"
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

        ready_pre: Optional[int] = None
        if p.net_quote or p.net_unblock_long_nd:
            ready_pre = max(
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
        deliv_place = legs[-1]["delivery"]["placeId"]
        deliv_supply = self.supply.get(deliv_place, 0)
        expanded_ret_ok = True
        if p.return_hub_1leg_only and len(legs) > 1:
            expanded_ret_ok = False
        if expanded_ret_ok and p.return_hub_min_on_time > 0 and self.projected_on_time() < p.return_hub_min_on_time:
            expanded_ret_ok = False
        if expanded_ret_ok and p.return_hub_max_urgent > 0:
            urg_open = sum(
                1 for oid in self.urgent if oid in self.orders and undelivered(self.orders[oid]) and not self.staffed(self.orders[oid])
            )
            if urg_open >= p.return_hub_max_urgent:
                expanded_ret_ok = False
        if expanded_ret_ok and p.return_hub_deliv_backlog_ratio > 0 and deliv_supply > 0:
            if self.backlog_near(deliv_place) + 1e-9 >= p.return_hub_deliv_backlog_ratio * deliv_supply:
                expanded_ret_ok = False

            if p.trade_in_seq_slack and p.trade_in_max_drive_min > 0 and drive > p.trade_in_max_drive_min:
                self.stats["dropped_trade_in_drive"] += 1
                return {}, "decline"
        pass_ext_ring = False
        pass_return_hub = False
        fri_thin_only = False
        eff_ret_supply = self.sup_ret_supply if (p.supervisor and self.sup_ret_supply is not None) else p.return_hub_min_supply
        eff_ret_drive = self.sup_ret_drive if (p.supervisor and self.sup_ret_drive is not None) else p.return_hub_max_drive_min
        pass_relay_quote = False
        relay_partner: Optional[str] = None
        relay_ok_kinds: set[str] = set()
        pass_net_thin = False
        net_sponsor: Optional[str] = None
        if gate_supply < gate_min:
            if p.supervisor and self.sup_emerg_active:
                self.stats["sup_emerg_declined"] += 1
                return {}, "decline"
            ext_sup = self.ext_supply.get(pickup, 0) if self.ext_supply else 0
            pass_ext_ring = (
                p.ext_ring_min_supply > 0
                and ext_sup >= p.ext_ring_min_supply
                and drive <= p.ext_ring_max_drive_min
            )
            want_return_hub = (
                (eff_ret_supply > 0 and deliv_supply >= eff_ret_supply and drive <= eff_ret_drive)
                or (p.return_hub_major_supply > 0 and deliv_supply >= p.return_hub_major_supply and drive <= p.return_hub_major_max_drive_min)
            )
            if expanded_ret_ok:
                pass_return_hub = want_return_hub
            else:
                pass_return_hub = p.return_hub_min_supply > 0 and deliv_supply >= 200 and drive <= 180
                if want_return_hub and not pass_return_hub:
                    self.stats["return_hub_throttled"] += 1
            if not (pass_ext_ring or pass_return_hub) and p.net_relay_quote and self.level >= 3:
                if self._relay_cap_available():
                    found_r = self._find_relay_partner_for_request(request, extra_days)
                    if found_r is not None:
                        relay_partner, relay_ok_kinds = found_r
                        pass_relay_quote = True
            if not (pass_ext_ring or pass_return_hub or pass_relay_quote) and p.net_quote and ready_pre is not None:
                if self.net_won_day[self.now // DAY] < p.net_cap_day:
                    net_sponsor = self._find_net_sponsor(request, ready_pre, drive, extra_days, thin_admission=True)
                    pass_net_thin = net_sponsor is not None
            if not (pass_ext_ring or pass_return_hub or pass_relay_quote or pass_net_thin):
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

        leg_readies = [
            max(
                self.now,
                window_from_note(
                    request["note"],
                    leg["pickup"]["window"],
                    "pickup",
                    v2=p.notes_v2,
                    arrived_at=request["arrivedAt"],
                    private_address=leg["pickup"]["privateAddress"],
                )["from"],
            )
            for leg in legs
        ]
        ready = ready_pre if ready_pre is not None else max(leg_readies)
        eff_ready = leg_readies[0] if (p.trade_in_seq_slack and len(legs) == 2) else ready

        on_net_gate = False
        if p.net_quote and p.net_discount > 0 and gate_supply >= gate_min:
            on_net_gate = self._find_net_sponsor(request, ready, drive, extra_days, thin_admission=False) is not None

        unblock_long_nd = False
        if p.net_unblock_long_nd and p.thin_long_next_day_supply > 0 and not is_ring and supply < p.thin_long_next_day_supply and p.long_drive_min < drive <= 420:
            unblock_long_nd = (
                self._find_net_sponsor(request, ready, drive, extra_days, thin_admission=False) is not None
                or (p.net_relay and self._find_relay_partner_for_request(request, extra_days) is not None)
            )

        is_seed = False
        if p.net_seed > 0 and self.now >= 12 * HOUR and supply >= 100 and self.supply.get(legs[-1]["delivery"]["placeId"], 0) < 100 and (p.seed_max_drive_min <= 0 or drive <= p.seed_max_drive_min):
            deliv_place = legs[-1]["delivery"]["placeId"]
            is_seed = any(
                cnt >= p.seed_min and self.geo.line_km(deliv_place, pl) <= 30.0
                for pl, cnt in self.pickup_req_counts.items()
            )

        deliv_supply = self.supply.get(legs[-1]["delivery"]["placeId"], 0)
        is_inbound_hub = supply < 200 and deliv_supply >= 200
        eff_fee_mult = p.expected_fee_mult
        if p.inbound_hub_fee_mult > 0 and is_inbound_hub and not any(leg["pickup"]["privateAddress"] for leg in legs):
            eff_fee_mult = p.inbound_hub_fee_mult
        fee = request["referenceFeeCents"] * eff_fee_mult
        mult = self.mult * self.dealer_adj[request["dealerId"]]
        if p.inbound_hub_disc > 0 and is_inbound_hub:
            mult *= (1.0 - p.inbound_hub_disc)
            self.stats["priced_inbound_hub"] += 1
        elif p.outbound_markup > 0 and deliv_supply < 200 and (supply >= 200 or drive >= 180):
            w_out = 1.5 if (supply >= 200 and drive >= 180) else 1.0
            mult *= (1.0 + w_out * p.outbound_markup)
            self.stats["priced_outbound_markup"] += 1
        if p.day_shock_lr > 0:
            tod = self.now % DAY
            if 480 <= tod <= 1080:
                mult *= math.exp(self.day_shock[(self.now // DAY, pickup)])
        if p.trust_gain > 0:
            count = self.dealer_trust[request["dealerId"]]
            mult *= (1 + p.trust_gain * count / 100.0)
        if p.trust_center_slope > 0.0 and self.level >= 8:
            count = self.dealer_trust[request["dealerId"]]
            mult *= math.exp(p.trust_center_slope * (count - self.trust_ema))

        is_invest = False
        if p.trust_invest > 0 and (self.now // DAY) <= 2 and self.dealer_trust[request["dealerId"]] < 25 and supply >= 100 and not request.get("note"):
            top3 = sorted(self.dealer_request_count.keys(), key=lambda d: self.dealer_request_count[d], reverse=True)[:3]
            is_invest = request["dealerId"] in top3

        eff_sd_supply = self.sup_sd_supply if (p.supervisor and self.sup_sd_supply is not None) else p.same_day_min_supply
        eff_min_slack = self.sup_min_slack if (p.supervisor and self.sup_min_slack is not None) else p.min_slack_min
        eff_fri_sd_drive = (
            p.sup_fri_sd_max_drive
            if (p.supervisor and self.sup_fri_surplus_active and p.sup_fri_sd_max_drive > 0 and (self.now // DAY) == 4)
            else p.fri_same_day_max_drive
        )
        congested = p.inbound_max_unstaffed > 0 and self.unstaffed_total() > p.inbound_max_unstaffed
        if congested:
            self.congested_reqs.add(request["id"])
            self.stats["inbound_paused_congested"] += 1
        base_floor = fee / (1 - p.min_margin_frac)
        eff_floor = base_floor
        deliv_supply = self.supply.get(legs[-1]["delivery"]["placeId"], 0)
        if p.hub_inbound_fee_mult > 0.0 and supply < 200 and deliv_supply >= 200 and tight == 0.0 and not congested:
            eff_floor = (request["referenceFeeCents"] * p.hub_inbound_fee_mult) / (1 - p.min_margin_frac)
        l_mult = self.lane_mult(request, congested=congested)

        prices: dict[str, int] = {}
        opt_discs: list[float] = []
        floored = False
        nd_floored = False
        inb_saved = False
        unlocked_fut_sd = False
        has_today_sd = False
        for option in request["options"]:
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
            fut_sd = (
                p.future_sameday_slow
                and expanded_ret_ok
                and option["kind"] == "same_day"
                and len(legs) == 1
                and not legs[0]["pickup"]["privateAddress"]
                and not legs[0]["delivery"]["privateAddress"]
                and deadline // DAY > self.now // DAY
                and (not p.fut_sd_return_only or pass_return_hub)
                and (not p.fut_sd_no_thin or not (pass_ext_ring or pass_return_hub))
                and (p.fut_sd_max_drive_min <= 0 or drive <= p.fut_sd_max_drive_min)
                and (p.fut_sd_min_deliv_supply <= 0 or deliv_supply >= p.fut_sd_min_deliv_supply)
            )
            ring_hub_sd = False
            was_blocked_sd = False
            if (fri_thin_only or pass_relay_quote or pass_net_thin) and option["kind"] == "same_day":
                continue
            if pass_relay_quote and option["kind"] not in relay_ok_kinds:
                continue
            if (pass_ext_ring or pass_return_hub) and option["kind"] == "same_day":
                if not fut_sd:
                    continue
                was_blocked_sd = True
            if is_ring and p.far_options == "slow" and option["kind"] == "same_day":
                if p.ring_to_hub_same_day_min > 0 and deliv_supply >= 200 and drive <= p.ring_to_hub_same_day_min:
                    ring_hub_sd = True
                elif fut_sd:
                    was_blocked_sd = True
                else:
                    continue
            if fri_thin_only and deadline // DAY < 7:
                continue
            if p.max_next_day_drive_min > 0 and drive > p.max_next_day_drive_min and not (fri_thin_only and deadline // DAY >= 7):
                if deadline // DAY <= eff_ready // DAY + 1:
                    self.stats["dropped_next_day_long"] += 1
                    continue
            if p.thin_long_next_day_supply > 0 and not is_ring and supply < p.thin_long_next_day_supply and drive > p.long_drive_min and not (fri_thin_only and deadline // DAY >= 7) and not unblock_long_nd:
                if deadline // DAY <= eff_ready // DAY + 1:
                    self.stats["dropped_thin_long_next_day"] += 1
                    continue
            if eff_fri_sd_drive > 0 and eff_ready // DAY >= 4 and option["kind"] == "same_day" and drive >= eff_fri_sd_drive:
                self.stats["dropped_fri_same_day"] += 1
                continue
            if p.priv_pickup_min_slot_min > 0 and p.priv_pickup_sameday_only:
                if any(
                    leg["pickup"]["privateAddress"]
                    and leg["pickup"]["window"]["to"] - request["respondBy"] < p.priv_pickup_min_slot_min
                    and deadline // DAY <= leg["pickup"]["window"]["to"] // DAY
                    for leg in legs
                ):
                    self.stats["dropped_priv_pickup_slot"] += 1
                    continue
            if p.long_drive_min > 0 and drive > p.long_drive_min:
                if deadline // DAY <= eff_ready // DAY:
                    self.stats["dropped_long_drive"] += 1
                    continue
            if option["kind"] == "same_day" and eff_sd_supply > 0 and supply < eff_sd_supply and not ring_hub_sd:
                if fut_sd:
                    was_blocked_sd = True
                else:
                    self.stats["dropped_same_day_supply"] += 1
                    continue
            if p.trade_in_seq_slack and len(legs) == 2:
                if legs[0]["delivery"]["window"]["to"] - legs[0]["delivery"]["window"]["from"] < 45:
                    self.stats["dropped_slack"] += 1
                    continue
                d0 = self.geo.minutes(legs[0]["pickup"]["placeId"], legs[0]["delivery"]["placeId"])
                d_mid = self.geo.minutes(legs[0]["delivery"]["placeId"], legs[1]["pickup"]["placeId"])
                d1 = self.geo.minutes(legs[1]["pickup"]["placeId"], legs[1]["delivery"]["placeId"])
                dl0_cap = min(legs[0]["delivery"]["window"]["to"], shift_business_days(option["deadline"], extra_days) if p.notes_v2 else option["deadline"])
                if p.notes_v2:
                    dl0 = window_from_note(
                        request["note"],
                        {"from": legs[0]["delivery"]["window"]["from"], "to": max(legs[0]["delivery"]["window"]["from"], dl0_cap)},
                        "delivery",
                        v2=True,
                        arrived_at=request["arrivedAt"],
                        private_address=legs[0]["delivery"]["privateAddress"],
                    )["to"]
                else:
                    dl0 = dl0_cap
                slack0 = dl0 - leg_readies[0] - d0
                handoff = max(leg_readies[0] + d0 + d_mid + 30, leg_readies[1])
                slack1 = deadline - handoff - d1
                if slack0 < eff_min_slack + p.slack_per_drive * d0 or slack1 < p.trade_in_leg1_slack_min + 0.25 * d1:
                    self.stats["dropped_slack"] += 1
                    continue
                slack = min(slack0, slack1 + 90)
            else:
                slack = deadline - ready - drive
                if slack < eff_min_slack + p.slack_per_drive * drive:
                    self.stats["dropped_slack"] += 1
                    continue
            if ring_hub_sd:
                self.stats["quoted_ring_hub_same_day"] += 1
                self.ring_hub_same_day.add(request["id"])
            if was_blocked_sd:
                unlocked_fut_sd = True
            if option["kind"] == "same_day" and not fut_sd:
                has_today_sd = True

            is_mon2 = option["kind"] != "same_day" and deadline >= 7 * DAY
            option_mult = mult
            if is_invest and slack >= 360:
                option_mult *= (1 - p.trust_invest)
            if p.return_hub_discount > 0 and pass_return_hub and not pass_ext_ring:
                option_mult *= (1.0 - p.return_hub_discount)
            if on_net_gate and p.net_discount > 0:
                option_mult *= (1.0 - p.net_discount)
            elif is_seed and p.net_seed > 0:
                option_mult *= (1.0 - p.net_seed)
            opt_disc = 0.0
            if option["kind"] == "within_3_days" and p.w3d_discount > 0:
                opt_disc = max(opt_disc, p.w3d_discount)
            if is_mon2 and p.mon2_discount > 0:
                opt_disc = max(opt_disc, p.mon2_discount)
            if opt_disc > 0:
                option_mult *= (1.0 - opt_disc)

            sd_mult = 1.0
            if option["kind"] == "same_day" and not (fut_sd and p.future_sameday_no_markup):
                sd_mult = 1.0 + p.same_day_markup
            base_list = option["listPriceCents"] * l_mult if l_mult != 1.0 else option["listPriceCents"]
            price = base_list * option_mult * sd_mult
            if price < base_floor:
                floored = True
                if eff_floor < base_floor:
                    inb_saved = True
            if price < eff_floor:
                price = eff_floor
                if option["kind"] == "next_day":
                    nd_floored = True
            prices[option["kind"]] = int(price + 0.5)
            opt_discs.append(opt_disc)
        if not prices:
            return {}, "decline"
        if fri_thin_only:
            self.sup_fri_thin_reqs.add(request["id"])
            self.stats["sup_fri_thin_quoted"] += 1
            if p.sup_fri_neutral_learn:
                self.ext_ring_reqs.add(request["id"])
        if p.floored_sd_prem > 0.0 and nd_floored and "same_day" in prices and "next_day" in prices:
            lifted = int(prices["next_day"] * (1.0 + p.floored_sd_prem) + 0.5)
            if lifted > prices["same_day"]:
                prices["same_day"] = lifted
                self.stats["sd_prem_lifted"] += 1
        if inb_saved:
            self.inb_floor_saved_reqs.add(request["id"])
            self.stats["inb_floor_saved"] += 1
        if p.floored_sd_prem > 0 and "same_day" in prices and len(prices) > 1:
            slow_min = min(v for k, v in prices.items() if k != "same_day")
            min_sd = int(slow_min * (1.0 + p.floored_sd_prem) + 0.5)
            if prices["same_day"] < min_sd:
                prices["same_day"] = min_sd
                self.stats["floored_sd_lifted"] += 1
        if p.floor_sd_gap > 0 and has_today_sd and "same_day" in prices and "next_day" in prices:
            min_sd = int(prices["next_day"] * (1.0 + p.floor_sd_gap) + 0.5)
            if prices["same_day"] < min_sd:
                prices["same_day"] = min_sd
                self.stats["floor_sd_gapped"] += 1
        if unlocked_fut_sd:
            self.fut_sd_reqs.add(request["id"])
            self.stats["quoted_fut_sd"] += 1
        if opt_discs and any(d > 0 for d in opt_discs):
            self.req_disc[request["id"]] = sum(opt_discs) / len(opt_discs)
            self.stats["quoted_slow_disc"] += 1
        if len(legs) == 2:
            self.stats["quoted_trade_in"] += 1
        if pass_ext_ring or pass_return_hub:
            self.ext_ring_reqs.add(request["id"])
            self.stats["quoted_ext_ring"] += 1
            if pass_return_hub:
                self.stats["quoted_return_hub"] += 1
        if pass_relay_quote:
            self.relay_quote_reqs.add(request["id"])
            if relay_partner is not None:
                self.relay_quote_partner[request["id"]] = relay_partner
            self.stats["relay_quote_quoted"] += 1
        elif pass_net_thin or on_net_gate:
            self.net_quote_reqs.add(request["id"])
            self.stats["net_quoted"] += 1
            if pass_net_thin:
                self.net_thin_reqs.add(request["id"])
                self.stats["net_quoted_thin"] += 1
                if net_sponsor is not None:
                    self.net_sponsor_gig[request["id"]] = net_sponsor
        elif is_seed:
            self.seed_reqs.add(request["id"])
            self.stats["seed_quoted"] += 1
        return prices, "floor" if floored else "quote"

    def learn(self, request_id: str, won: bool) -> None:
        """Moves the multiplier towards the price that wins `price_target_win` of the normal quotes."""
        if self.decided.get(request_id) != "quote":
            return
        if request_id in self.net_quote_reqs or request_id in self.seed_reqs or request_id in self.relay_quote_reqs:
            return
        if self.p.ext_ring_neutral_learn and request_id in self.ext_ring_reqs:
            self.stats["ext_ring_skipped_learn"] += 1
            return
        if self.p.fut_sd_neutral_learn and request_id in self.fut_sd_reqs and len(self.requests[request_id]["options"]) == 1:
            self.stats["fut_sd_skipped_learn"] += 1
            return
        if self.p.ext_ring_no_learn and not won and request_id in self.ext_ring_reqs:
            return
        p, day = self.p, self.now // DAY
        self.day_norm_quotes += 1
        if won:
            self.day_norm_wins += 1
        if day != self.streak_day:
            self.loss_streak, self.streak_day = 0, day
        self.loss_streak = 0 if won else self.loss_streak + 1
        if self.loss_streak > self.day_max_streak[day]:
            self.day_max_streak[day] = self.loss_streak
        target = p.price_target_win
        if p.lane_prior_comp_slope > 0.0:
            lm = self.lane_mult(self.requests[request_id], congested=(request_id in self.congested_reqs))
            if lm != 1.0:
                target = clamp(target - p.lane_prior_comp_slope * math.log(lm), 0.05, 0.90)
        step = (1 - target) if won else -target
        if p.day_shock_lr > 0:
            req = self.requests[request_id]
            arr = req["arrivedAt"]
            if 480 <= arr % DAY <= 1080:
                r_day = arr // DAY
                pk = req["legs"][0]["pickup"]["placeId"]
                for nb in self._shock_neighbors(pk):
                    self.day_shock[(r_day, nb)] = clamp(
                        self.day_shock[(r_day, nb)] + p.day_shock_lr * step,
                        p.day_shock_min,
                        p.day_shock_max,
                    )
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
            oid = order["id"]
            req = self.requests[order["id"]]
            self.stats[f"lane_wins_{self.lane_bucket(req)}"] += 1
            if order["id"] in self.inb_floor_saved_reqs:
                self.stats["won_inb_floor_saved"] += 1
            if self.now // DAY >= 1:
                t_diff = self.dealer_trust[req["dealerId"]] - self.trust_ema
                if t_diff < -5.0:
                    self.stats["wins_trust_low"] += 1
                elif t_diff > 5.0:
                    self.stats["wins_trust_high"] += 1
            pickup = order["legs"][0]["pickup"]["placeId"]
            if self.supply.get(pickup, 0) < self.p.min_supply:
                self.stats["won_ring"] += 1
            if order["option"] == "same_day" and oid in self.ring_hub_same_day:
                self.stats["won_ring_hub_same_day"] += 1
            if order["option"] == "same_day" and order["id"] in self.fut_sd_reqs:
                self.stats["won_fut_sd"] += 1
            if self.gate_supply.get(pickup, 0) < self.p.min_supply:
                if order["id"] in self.sup_fri_thin_reqs:
                    self.stats["sup_fri_thin_won"] += 1
                else:
                    self.stats["won_ext_ring"] += 1
                    if self.p.return_hub_min_supply > 0 and self.supply.get(order["legs"][-1]["delivery"]["placeId"], 0) >= self.p.return_hub_min_supply:
                        self.stats["won_return_hub"] += 1
            if oid in self.net_quote_reqs:
                self.stats["net_won"] += 1
                if oid in self.net_thin_reqs:
                    self.stats["net_won_thin"] += 1
                    self.net_won_day[self.now // DAY] += 1
            if oid in self.relay_quote_reqs:
                self.stats["relay_quote_won"] += 1
                self.relay_won_day[self.now // DAY] += 1
            if oid in self.seed_reqs:
                self.stats["seed_won"] += 1
            if len(order["legs"]) == 2:
                self.stats["won_trade_in"] += 1
            if order["option"] != "same_day" and order["deadline"] >= 7 * DAY:
                self.stats["won_mon2"] += 1
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
            if self.p.net_relay and len(order["legs"]) == 1:
                self.newly_won_relay.append(oid)
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
        was_relay = self.relay_gigs.pop(gig_id, None) is not None
        self.chain_pairs.pop(gig_id, None)
        for stop in action["stops"]:
            self.leg_gigs.get(stop["orderId"], {}).pop(stop["leg"], None)
        oids = order_ids_of(action)
        if len(oids) > 1:
            if was_relay:
                self.stats["relay_split"] += 1
                self.stats["relay_split_expired"] += 1
                for oid in oids:
                    if oid in self.orders and undelivered(self.orders[oid]):
                        self.post(self.orders[oid], undelivered(self.orders[oid]), self.saved_retry.get((oid, 0), Retry()), allow_pair=False)
                return
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
                if gig_id in self.relay_gigs:
                    self._split_relay_gig(gig_id, "warning")
                else:
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
                if (p.net_offer or p.net_viewer_offer) and (gid, d_id) in self.net_offered_pairs:
                    continue
                if self.now - self.gig_posted_at.get(gid, self.now) < p.view_offer_after_min:
                    continue
                if d_id in busy_drivers or self.offers_sent[(d_id, day)] >= 3:
                    continue
                open_cnt = sum(1 for k in self.open_offers if k[0] == gid)
                if p.net_offer or p.net_viewer_offer:
                    open_cnt += sum(1 for sent_at, _, _, _ in self.net_open_offers.get(gid, {}).values() if self.now - sent_at <= 10)
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
        if p.trade_in_handoff_pace and len(order["legs"]) == 2 and 0 in undelivered(order):
            d0 = self.geo.minutes(order["legs"][0]["pickup"]["placeId"], order["legs"][0]["delivery"]["placeId"])
            until = min(until, order["legs"][0]["delivery"]["window"]["to"] - d0 - 15 - 3 * HOUR)
        supply = self.supply.get(order["legs"][0]["pickup"]["placeId"], 0)
        dest_supply = self.supply.get(order["legs"][-1]["delivery"]["placeId"], 0)
        deliv_supply = self.supply.get(order["legs"][-1]["delivery"]["placeId"], 0)
        fee_open_override: Optional[float] = None
        if p.net_thin_fee_open > 0 and cars == 1 and order["id"] in self.net_thin_reqs:
            fee_open_override = p.net_thin_fee_open
            self.stats["net_thin_fee_posts"] += 1
        elif p.inbound_hub_fee_open > 0 and dest_supply >= 150 and until - self.now >= 2 * HOUR:
            fee_open_override = p.inbound_hub_fee_open
            self.stats["inbound_hub_posts"] += 1
        elif (
            p.return_hub_fee_open > 0
            and supply < 200
            and deliv_supply >= 200
            and until - self.now >= 2 * HOUR
            and not any(leg["pickup"]["privateAddress"] for leg in order["legs"])
        ):
            fee_open_override = p.return_hub_fee_open
            self.stats["return_hub_fee_posts"] += 1
        elif p.hub_multiday_fee_open > 0 and order["option"] != "same_day" and supply >= 150 and until - self.now >= 6 * HOUR:
            fee_open_override = p.hub_multiday_fee_open
            self.stats["hub_multiday_posts"] += 1
        elif p.thin_sameday_fee_open > 0 and order["option"] == "same_day" and supply < 65:
            fee_open_override = p.thin_sameday_fee_open
            self.stats["thin_sameday_posts"] += 1
        first_at: Optional[int] = None
        if p.net_relay and p.net_relay_preserve_age and cars == 1 and self.relay_order_splits[order["id"]] > 0:
            first_at = self.order_first_posted_at.get(order["id"])
        return self.rising(base, until, fee_open_override=fee_open_override, first_at=first_at)

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
        if first_at is not None and first_at < self.now < until:
            orig_times = [first_at]
            t0 = (first_at // p.fee_step_min + 1) * p.fee_step_min
            while t0 <= until:
                if p.day_start <= t0 % DAY < p.day_end:
                    orig_times.append(t0)
                t0 += p.fee_step_min
            if len(orig_times) > 1:
                idx = sum(1 for ts in orig_times if ts <= self.now) - 1
                idx = max(0, min(len(orig_times) - 1, idx))
                fee_open = fee_open + (fee_warn - fee_open) * (idx / (len(orig_times) - 1))
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
            prev = self.saved_retry.get((order_id, leg), Retry())
            new_r = Retry(
                max(prev.pickup_from, pickup_from),
                manual_licence=prev.manual_licence or (reason == "licence"),
                plates=prev.plates or (reason == "no_plates"),
            )
            self.saved_retry[(order_id, leg)] = new_r
            self.post(order, [leg], new_r)

    # --- pre-booking 2-car route relay (open outbound + open return) ----------------------------------
    def _relay_cap_available(self) -> bool:
        day = self.now // DAY
        used = self.relay_won_day[day]
        for rid, req in self.requests.items():
            if rid in self.relay_quote_reqs and rid not in self.orders and rid not in self.lost_requests and self.now <= req["respondBy"]:
                used += 1
        return used < self.p.net_relay_cap_day

    def _car_spec_for_order(self, order: Order, retry: Optional[Retry] = None) -> Optional[CarSpec]:
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

    def _car_spec_for_request_option(self, request: PriceRequest, option_deadline: int, extra_days: int) -> Optional[CarSpec]:
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

    def _relay_feasible(self, a: CarSpec, b: CarSpec, min_slack: int, now_at: int) -> Optional[tuple[int, int]]:
        if a.supply_p < b.supply_p:
            return None
        if self.geo.line_km(a.place_d, b.place_p) > self.p.net_relay_km:
            return None
        if self.p.net_relay_max_home_km > 0 and self.geo.line_km(b.place_d, a.place_p) > self.p.net_relay_max_home_km:
            return None
        if self.p.net_relay_homeward and self.geo.line_km(b.place_d, a.place_p) > max(60.0, self.geo.line_km(a.place_d, a.place_p) + 25.0):
            return None
        deadhead = self.geo.minutes(a.place_d, b.place_p)
        total_drive = a.drive_min + deadhead + b.drive_min
        if total_drive + a.extra_min + b.extra_min + 60 > 12 * HOUR:
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
                        t_del_a_opt = next_site_open(a.stop_d, t_arr_da, a_lim)
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
                            ok = next_site_open(b.stop_d, t_arr_db, b_lim) is not None
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

    def _has_live_booked_net_sponsor(self, oid: str) -> bool:
        return False

    def _waiting_single_orders(self) -> list[tuple[str, Optional[str]]]:
        res: list[tuple[str, Optional[str]]] = []
        for oid, order in self.orders.items():
            if len(order["legs"]) != 1 or undelivered(order) != [0]:
                continue
            if oid in self.urgent or oid in self.lost or self.now > order["lastPickupAt"]:
                continue
            if self.p.net_relay_max_splits > 0 and self.relay_order_splits[oid] >= self.p.net_relay_max_splits:
                continue
            if self._has_live_booked_net_sponsor(oid):
                continue
            gigs = self.gigs_of(oid)
            if len(gigs) == 1:
                gid = gigs[0]
                if gid in self.booked or gid in self.relay_gigs:
                    continue
                post = self.posts.get(gid)
                if post is not None and len(order_ids_of(post)) == 1 and len(post["stops"]) == 2:
                    res.append((oid, gid))
            elif len(gigs) == 0:
                if any(a["type"] == "post" and len(a["stops"]) == 2 and a["stops"][0]["orderId"] == oid for a in self.outbox):
                    res.append((oid, None))
        return res

    def _find_relay_partner_for_request(self, request: PriceRequest, extra_days: int) -> Optional[tuple[str, set[str]]]:
        if len(request["legs"]) != 1:
            return None
        waiting = self._waiting_single_orders()
        if not waiting:
            return None
        committed_partners = {
            self.relay_quote_partner[rid]
            for rid, req in self.requests.items()
            if rid in self.relay_quote_reqs
            and rid in self.relay_quote_partner
            and rid not in self.orders
            and rid not in self.lost_requests
            and self.now <= req["respondBy"]
        }
        partner_specs: list[tuple[str, CarSpec]] = []
        for oid, _ in waiting:
            if oid in committed_partners:
                continue
            sp = self._car_spec_for_order(self.orders[oid])
            if sp is not None:
                partner_specs.append((oid, sp))
        if not partner_specs:
            return None

        ok_kinds: set[str] = set()
        best_partner: Optional[tuple[float, str]] = None
        for opt in request["options"]:
            if opt["kind"] == "same_day":
                continue
            spec_r = self._car_spec_for_request_option(request, opt["deadline"], extra_days)
            if spec_r is None:
                continue
            for oid, spec_p in partner_specs:
                if self._relay_feasible(spec_p, spec_r, self.p.min_slack_min, self.now) is not None:
                    ok_kinds.add(opt["kind"])
                    dist_home = self.geo.line_km(spec_r.place_d, spec_p.place_p)
                    if best_partner is None or dist_home < best_partner[0]:
                        best_partner = (dist_home, oid)
                elif self._relay_feasible(spec_r, spec_p, self.p.min_slack_min, self.now) is not None:
                    ok_kinds.add(opt["kind"])
                    dist_home = self.geo.line_km(spec_p.place_d, spec_r.place_p)
                    if best_partner is None or dist_home < best_partner[0]:
                        best_partner = (dist_home, oid)
        if not ok_kinds or best_partner is None:
            return None
        return best_partner[1], ok_kinds

    def _relay_schedule(self, order_a: Order, order_b: Order, last_start: int) -> tuple[list[FeeStep], int, int]:
        sched_a = self.fees_for(order_a, 1)
        sched_b = self.fees_for(order_b, 1)
        single_open_sum = sched_a[0]["feeCents"] + sched_b[0]["feeCents"]
        ref_a = self.requests[order_a["id"]]["referenceFeeCents"]
        ref_b = self.requests[order_b["id"]]["referenceFeeCents"]
        ref_sum = ref_a + ref_b
        open_cents = max(1, int(self.p.net_relay_fee * single_open_sum + 0.5))
        if self.level == 1:
            return [{"at": self.now, "feeCents": open_cents}], single_open_sum, ref_sum
        warn_at = min(order_a["lastPickupAt"] - 3 * HOUR, order_b["lastPickupAt"] - 3 * HOUR, last_start - HOUR)
        until = max(self.now, warn_at)
        base = float(ref_sum)
        open_mult = open_cents / base
        warn_mult = max(open_mult, self.p.fee_warn * self.p.net_relay_fee)
        return self.rising(base, until, fee_open_override=open_mult, fee_warn_override=warn_mult), single_open_sum, ref_sum

    def _stops_and_audience_for_single(self, order: Order) -> tuple[list[StopRef], Audience]:
        req = self.requests[order["id"]]
        retry = self.saved_retry.get((order["id"], 0), Retry())
        flags = note_flags(req["note"], v2=self.p.notes_v2)
        audience: Audience = {
            "experienced": any(leg["car"]["premium"] for leg in order["legs"]),
            "manualLicence": retry.manual_licence or flags.manual,
        }
        retry = retry._replace(plates=retry.plates or flags.plates)
        stops = without_windows(
            stops_for(order, [0], req["note"], retry, self.geo, self.p.charge_min_km, self.p.notes_v2, req["arrivedAt"]),
            self.now,
        )
        return stops, audience

    def _split_relay_gig(self, gig_id: str, reason: str) -> None:
        info = self.relay_gigs.pop(gig_id, None)
        post = self.posts.get(gig_id)
        if post is None:
            return
        oids = info["orders"] if info is not None else order_ids_of(post)
        if len(oids) == 2:
            self.relay_split_pairs.add((oids[0], oids[1]))
            for oid in oids:
                self.relay_order_splits[oid] += 1
        self.stats["relay_split"] += 1
        self.stats[f"relay_split_{reason}"] += 1
        if gig_id not in self.booked:
            self.outbox.append({"type": "withdraw", "gigId": gig_id})
        for stop in post["stops"]:
            if self.leg_gigs.get(stop["orderId"], {}).get(stop["leg"]) == gig_id:
                self.leg_gigs.get(stop["orderId"], {}).pop(stop["leg"], None)
        for oid in oids:
            if oid in self.orders and undelivered(self.orders[oid]):
                self.post(self.orders[oid], undelivered(self.orders[oid]), self.saved_retry.get((oid, 0), Retry()), allow_pair=False)

    def _tick_relay(self) -> None:
        p = self.p
        for gid, info in list(self.relay_gigs.items()):
            if gid in self.booked:
                continue
            oids = info["orders"]
            if any(oid not in self.orders or oid in self.urgent or oid in self.lost or not undelivered(self.orders[oid]) for oid in oids):
                self._split_relay_gig(gid, "urgent")
                continue
            if daytime_minutes(info["unbooked_since"], self.now, p.day_start, p.day_end) >= p.net_relay_patience_min:
                self._split_relay_gig(gid, "patience")

        new_set = set(self.newly_won_relay)
        self.newly_won_relay.clear()
        waiting = self._waiting_single_orders()
        if len(waiting) < 2:
            return

        mature_or_new: set[str] = set()
        specs: dict[str, CarSpec] = {}
        gid_of: dict[str, Optional[str]] = {}
        for oid, gid in waiting:
            sp = self._car_spec_for_order(self.orders[oid])
            if sp is None:
                continue
            specs[oid] = sp
            gid_of[oid] = gid
            if oid in new_set or oid in self.relay_quote_reqs:
                mature_or_new.add(oid)
            elif gid is not None and gid in self.single_open_since:
                if daytime_minutes(self.single_open_since[gid], self.now, p.day_start, p.day_end) >= p.net_relay_after_min:
                    mature_or_new.add(oid)
            elif gid is None:
                mature_or_new.add(oid)

        if not mature_or_new or len(specs) < 2:
            return

        cand_pairs: list[tuple[int, float, float, int, str, str, int]] = []
        oids_sorted = sorted(specs.keys())
        for oid_a in oids_sorted:
            sa = specs[oid_a]
            for oid_b in oids_sorted:
                if oid_a == oid_b:
                    continue
                if oid_a not in mature_or_new and oid_b not in mature_or_new:
                    continue
                if (oid_a, oid_b) in self.relay_split_pairs:
                    continue
                sb = specs[oid_b]
                feas = self._relay_feasible(sa, sb, p.min_slack_min, self.now)
                if feas is None:
                    continue
                last_start, total_drive = feas
                thin_b = 0 if (oid_b in self.relay_quote_reqs or self.gate_supply.get(sb.place_p, 0) < p.min_supply) else 1
                home_gap = round(self.geo.line_km(sb.place_d, sa.place_p), 2)
                mid_gap = round(self.geo.line_km(sa.place_d, sb.place_p), 2)
                cand_pairs.append((thin_b, home_gap, mid_gap, total_drive, oid_a, oid_b, last_start))

        if not cand_pairs:
            return
        cand_pairs.sort()
        paired_now: set[str] = set()
        for _, home_gap, _, _, oid_a, oid_b, last_start in cand_pairs:
            if oid_a in paired_now or oid_b in paired_now:
                continue
            order_a, order_b = self.orders[oid_a], self.orders[oid_b]
            for oid_x, gid_x in ((oid_a, gid_of[oid_a]), (oid_b, gid_of[oid_b])):
                if gid_x is None:
                    self.outbox = [
                        act for act in self.outbox
                        if not (act["type"] == "post" and len(act["stops"]) == 2 and act["stops"][0]["orderId"] == oid_x)
                    ]
                else:
                    self.single_open_since.pop(gid_x, None)
                    for ok in [k for k in self.open_offers if k[0] == gid_x]:
                        self.open_offers.pop(ok, None)
                    self.net_open_offers.pop(gid_x, None)
                    self.leg_gigs.get(oid_x, {}).pop(0, None)
                    self.outbox.append({"type": "withdraw", "gigId": gid_x})

            stops_a, aud_a = self._stops_and_audience_for_single(order_a)
            stops_b, aud_b = self._stops_and_audience_for_single(order_b)
            audience: Audience = {
                "experienced": aud_a["experienced"] or aud_b["experienced"],
                "manualLicence": aud_a["manualLicence"] or aud_b["manualLicence"],
            }
            sched, single_open_sum, ref_sum = self._relay_schedule(order_a, order_b, last_start)
            post_action: PostAction = {"type": "post", "stops": stops_a + stops_b, "audience": audience, "schedule": sched}
            self.outbox.append(post_action)
            self.stats["posts"] += 1
            self._flush_non_quotes()
            gigs_a = self.gigs_of(oid_a)
            gigs_b = self.gigs_of(oid_b)
            if len(gigs_a) == 1 and gigs_a == gigs_b:
                pair_gid = gigs_a[0]
                is_thin_b = self.gate_supply.get(specs[oid_b].place_p, 0) < p.min_supply
                self.relay_gigs[pair_gid] = {
                    "orders": (oid_a, oid_b),
                    "posted_at": self.now,
                    "unbooked_since": self.now,
                    "single_open_sum": single_open_sum,
                    "ref_sum": ref_sum,
                    "thin_b": is_thin_b,
                }
                self.relay_ever_paired.update((oid_a, oid_b))
                self.stats["relay_paired"] += 1
                if is_thin_b:
                    self.stats["relay_paired_thin_b"] += 1
                if home_gap <= 30.0:
                    self.stats["relay_paired_roundtrip"] += 1
                if oid_a in self.relay_quote_reqs or oid_b in self.relay_quote_reqs:
                    self.stats["relay_paired_from_quote"] += 1
                paired_now.add(oid_a)
                paired_now.add(oid_b)
            else:
                self.stats["relay_post_refused"] += 1
                self.relay_split_pairs.add((oid_a, oid_b))
                for oid_x in (oid_a, oid_b):
                    if oid_x in self.orders and undelivered(self.orders[oid_x]) and not self.gigs_of(oid_x):
                        self.post(self.orders[oid_x], [0], self.saved_retry.get((oid_x, 0), Retry()), allow_pair=False)

    def _handle_cancelled_relay(self, event: DeskEvent) -> None:
        oid = event["orderId"]
        outcomes = {cg["gigId"]: cg["outcome"] for cg in event.get("gigs", [])}
        if outcomes:
            for gid, outcome in outcomes.items():
                self.single_open_since.pop(gid, None)
                info = self.relay_gigs.pop(gid, None)
                post = self.posts.get(gid)
                other_oids = [o for o in (info["orders"] if info is not None else (order_ids_of(post) if post else [])) if o != oid]
                if outcome in ("withdrawn", "released"):
                    self.booked.discard(gid)
                    if post:
                        for s in post["stops"]:
                            if self.leg_gigs.get(s["orderId"], {}).get(s["leg"]) == gid:
                                self.leg_gigs.get(s["orderId"], {}).pop(s["leg"], None)
                    for other_id in other_oids:
                        if other_id in self.orders and undelivered(self.orders[other_id]) and not self.gigs_of(other_id):
                            self.stats["relay_split"] += 1
                            self.stats["relay_split_cancel"] += 1
                            self.post(self.orders[other_id], undelivered(self.orders[other_id]), self.saved_retry.get((other_id, 0), Retry()), allow_pair=False)
                elif outcome == "shortened":
                    if post:
                        self.posts[gid] = {**post, "stops": [s for s in post["stops"] if s["orderId"] != oid]}
            self.leg_gigs.pop(oid, None)
        else:
            self.outbox = [
                act for act in self.outbox
                if not (act["type"] == "post" and len(order_ids_of(act)) == 1 and act["stops"][0]["orderId"] == oid)
            ]
            if self.p.lead_car:
                self.withdraw(oid)
            self.leg_gigs.pop(oid, None)

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
        if order["id"] in self.relay_quote_reqs:
            return False
        if len(legs) != 1 or len(order["legs"]) != 1 or retry != Retry():
            return False
        is_today_sd = lambda o: o["option"] == "same_day" and (not p.future_sameday_pair or o["deadline"] // DAY <= self.now // DAY)
        if is_today_sd(order) or order["id"] in self.urgent or order["id"] in self.lost:
            return False
        req = self.requests.get(order["id"])
        if req is None:
            return False
        if req.get("note") and not p.lead_car_allow_benign_notes:
            return False
        flags_b = note_flags(req["note"], v2=p.notes_v2) if req.get("note") else None
        if flags_b is not None and (flags_b.manual or flags_b.plates):
            return False
        stops_b = without_windows(
            stops_for(order, legs, req["note"], retry, self.geo, p.charge_min_km, p.notes_v2, req["arrivedAt"], p.trade_in_seq_slack),
            self.now,
        )
        if any(s.get("withCharging") for s in stops_b):
            return False
        if req.get("note") and any("window" in s for s in stops_b):
            return False
        pb = order["legs"][0]["pickup"]["placeId"]
        db = order["legs"][0]["delivery"]["placeId"]
        drive_b = self.geo.minutes(pb, db)
        # Flush any matching single-car slow post still sitting in outbox from the current step (e.g. same batch)
        for a in self.outbox:
            if a["type"] == "post" and len(a["stops"]) == 2:
                oid = a["stops"][0]["orderId"]
                other = self.orders.get(oid)
                other_req_out = self.requests.get(oid, {})
                note_ok = (not other_req_out.get("note")) or (
                    p.lead_car_allow_benign_notes
                    and not a["audience"]["manualLicence"]
                    and not any(s.get("withPlates") or "window" in s for s in a["stops"])
                )
                dl_ok = p.lead_car_cross_slow or (other is not None and other["deadline"] // DAY == order["deadline"] // DAY)
                if (
                    other is not None
                    and oid != order["id"]
                    and not is_today_sd(other)
                    and oid not in self.urgent
                    and oid not in self.lost
                    and note_ok
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
            if gig_id in self.booked or gig_id in self.relay_gigs or len(action["stops"]) != 2:
                continue
            other_id = action["stops"][0]["orderId"]
            if other_id == order["id"] or other_id in self.urgent or other_id in self.lost or other_id in self.relay_quote_reqs:
                continue
            if self.leg_gigs.get(other_id, {}).get(action["stops"][0]["leg"]) != gig_id:
                continue
            other_order = self.orders.get(other_id)
            if other_order is None or len(other_order["legs"]) != 1 or undelivered(other_order) != [0]:
                continue
            if is_today_sd(other_order):
                continue
            other_req = self.requests.get(other_id)
            if other_req is None:
                continue
            if other_req.get("note"):
                if not p.lead_car_allow_benign_notes:
                    continue
                if action["audience"]["manualLicence"] or any(s.get("withPlates") or "window" in s for s in action["stops"]):
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
        if len(legs) == 1:
            self.saved_retry[(order["id"], legs[0])] = retry
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
            stops_for(order, legs, note, retry, self.geo, self.p.charge_min_km, self.p.notes_v2, req["arrivedAt"], self.p.trade_in_seq_slack),
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
            self.order_first_posted_at.setdefault(stop["orderId"], self.now)
        self.posts[gig_id] = action
        self.gig_posted_at.setdefault(gig_id, self.now)
        if self.p.net_relay and gig_id not in self.booked and len(action["stops"]) == 2 and len(order_ids_of(action)) == 1:
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
            self.chain_pairs.pop(gig_id, None)
            for ok in [k for k in self.open_offers if k[0] == gig_id]:
                self.open_offers.pop(ok, None)
            self.net_open_offers.pop(gig_id, None)
            info = self.relay_gigs.pop(gig_id, None)
            if info is not None:
                self.stats["relay_split"] += 1
                self.stats["relay_split_withdraw"] += 1
                for oid in info["orders"]:
                    if oid != order_id and oid in self.orders:
                        self.leg_gigs.pop(oid, None)
                        if undelivered(self.orders[oid]):
                            self.post(self.orders[oid], undelivered(self.orders[oid]), self.saved_retry.get((oid, 0), Retry()), allow_pair=False)
            elif gig_id in self.posts and len(order_ids_of(self.posts[gig_id])) > 1:
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

    def _flush_non_quotes(self) -> None:
        quotes = [a for a in self.outbox if a["type"] == "quote"]
        others = self.sort_actions([a for a in self.outbox if a["type"] != "quote"])
        self.outbox = quotes
        if others:
            self.read_results(others, self.world.act(others))

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

    def _rejoin_network_and_relay(self, snapshot: DeskSnapshot, history: list[DeskEvent]) -> None:
        p = self.p
        if not (p.net_offer or p.net_viewer_offer or p.net_quote or p.net_seed or p.net_relay or p.net_relay_quote):
            return
        for req in self.requests.values():
            self.pickup_req_counts[req["legs"][0]["pickup"]["placeId"]] += 1
        for e in history:
            if e["kind"] == "visit_failed" and e["orderId"] in self.orders:
                oid, leg, reason = e["orderId"], e["leg"], e["reason"]
                car_not_there = reason in ("not_ready", "closed")
                pickup_from = retry_from(self.orders[oid], self.requests[oid], leg, e["at"]) if car_not_there else 0
                prev = self.saved_retry.get((oid, leg), Retry())
                self.saved_retry[(oid, leg)] = Retry(
                    max(prev.pickup_from, pickup_from),
                    manual_licence=prev.manual_licence or (reason == "licence"),
                    plates=prev.plates or (reason == "no_plates"),
                )
            elif e["kind"] == "gig_viewed":
                self.gig_viewers[e["gigId"]][e["driverId"]] = e["at"]
            elif e["kind"] == "offer_answered" and e["answer"] == "declined":
                self.declined_pairs.add((e["gigId"], e["driverId"]))
            elif e["kind"] == "order_won":
                oid = e["order"]["id"]
                req = self.requests.get(oid)
                if req is not None:
                    pk = req["legs"][0]["pickup"]["placeId"]
                    drive = sum(self.geo.minutes(l["pickup"]["placeId"], l["delivery"]["placeId"]) for l in req["legs"])
                    if len(req["legs"]) == 2:
                        drive += self.geo.minutes(req["legs"][0]["delivery"]["placeId"], req["legs"][1]["pickup"]["placeId"])
                    if self.gate_supply.get(pk, 0) < p.min_supply:
                        pass_er = p.ext_ring_min_supply > 0 and self.ext_supply.get(pk, 0) >= p.ext_ring_min_supply and drive <= p.ext_ring_max_drive_min
                        pass_rh = p.return_hub_min_supply > 0 and self.supply.get(req["legs"][-1]["delivery"]["placeId"], 0) >= p.return_hub_min_supply and drive <= p.return_hub_max_drive_min
                        if not (pass_er or pass_rh):
                            if p.net_quote:
                                self.net_quote_reqs.add(oid)
                                self.net_thin_reqs.add(oid)
                                self.net_won_day[e["at"] // DAY] += 1
                            elif p.net_relay_quote:
                                self.relay_quote_reqs.add(oid)
                                self.relay_won_day[e["at"] // DAY] += 1

        booked_ev: dict[str, DeskEvent] = {}
        started_at: dict[str, int] = {}
        late_pick: dict[str, int] = {}
        picked_ev: dict[str, tuple[str, int, int]] = {}
        done_at: dict[str, int] = {}
        last_unbooked: dict[str, int] = {}
        for e in history:
            ek = e["kind"]
            if ek == "gig_booked":
                booked_ev[e["gigId"]] = e
            elif ek in ("gig_dropped", "no_show"):
                booked_ev.pop(e["gigId"], None)
                last_unbooked[e["gigId"]] = e["at"]
            elif ek == "gig_started":
                started_at[e["gigId"]] = e["at"]
            elif ek == "driver_late":
                late_pick[e["gigId"]] = e["pickupAt"]
            elif ek == "picked_up" and e.get("gigId"):
                picked_ev[e["gigId"]] = (e["orderId"], e["leg"], e["at"])
            elif ek == "delivered" and e.get("gigId"):
                done_at[e["gigId"]] = e["at"]

        self.order_first_posted_at.clear()
        self.single_open_since.clear()
        for gig in snapshot["gigs"]:
            gid = gig["id"]
            self.gig_posted_at[gid] = gig["postedAt"]
            oids = order_ids_of(gig)
            for oid in oids:
                prev_t = self.order_first_posted_at.get(oid)
                if prev_t is None or gig["postedAt"] < prev_t:
                    self.order_first_posted_at[oid] = gig["postedAt"]

            if p.net_relay and len(oids) == 2 and len(gig["stops"]) == 4:
                self.relay_ever_paired.update(oids)
                if gig["status"] == "withdrawn":
                    self.relay_split_pairs.add((oids[0], oids[1]))
                    for oid in oids:
                        self.relay_order_splits[oid] += 1
                elif gig["status"] in ("open", "booked", "working"):
                    ref_sum = sum(self.requests[o]["referenceFeeCents"] for o in oids if o in self.requests)
                    open_sum = sum(int(self.requests[o]["referenceFeeCents"] * p.fee_open + 0.5) for o in oids if o in self.requests)
                    thin_b = oids[1] in self.requests and self.gate_supply.get(self.requests[oids[1]]["legs"][0]["pickup"]["placeId"], 0) < p.min_supply
                    self.relay_gigs[gid] = {
                        "orders": (oids[0], oids[1]),
                        "posted_at": gig["postedAt"],
                        "unbooked_since": last_unbooked.get(gid, gig["postedAt"]),
                        "single_open_sum": open_sum,
                        "ref_sum": ref_sum,
                        "thin_b": thin_b,
                    }
                    if gig["status"] in ("booked", "working"):
                        self.relay_booked_orders.update(oids)
            elif p.net_relay and gig["status"] == "open" and len(oids) == 1 and len(gig["stops"]) == 2:
                self.single_open_since[gid] = last_unbooked.get(gid, gig["postedAt"])

            if (p.net_offer or p.net_quote) and gig["status"] in ("booked", "working", "done"):
                driver_id = gig.get("driverId") or (booked_ev[gid]["driverId"] if gid in booked_ev else None)
                b_at = gig.get("bookedAt") or (booked_ev[gid]["at"] if gid in booked_ev else gig["postedAt"])
                if driver_id is not None:
                    is_done = gig["status"] == "done"
                    is_started = gig["status"] == "working" or gid in started_at or is_done
                    pe = self._build_pos_entry(gid, driver_id, gig["stops"], b_at, started=is_started, done=is_done)
                    if pe is not None:
                        if gid in started_at:
                            pe.planned_start = started_at[gid]
                            pe.planned_finish = pe.planned_start + pe.total_dur
                        if gid in late_pick:
                            pe.planned_start = late_pick[gid]
                            pe.planned_finish = pe.planned_start + pe.total_dur
                        if gid in picked_ev:
                            p_oid, p_leg, p_at = picked_ev[gid]
                            rem = self._remaining_dur_after_pickup(gig["stops"], p_oid, p_leg)
                            if rem is not None:
                                pe.planned_finish = p_at + rem
                        if is_done and gid in done_at:
                            pe.planned_finish = done_at[gid]
                        if not is_done or pe.planned_finish // DAY == self.now // DAY:
                            self.pos_ledger[gid] = pe

        for dp in snapshot.get("driverPositions", []):
            did = dp.get("driverId")
            place = dp.get("placeId")
            if did and place:
                for pe in self.pos_ledger.values():
                    if pe.driver_id == did and pe.started and not pe.done:
                        rem_road = self.geo.minutes(place, pe.finish_place)
                        pe.planned_finish = max(self.now, self.now + rem_road)

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
        
        # replay ledger and requests to build trust and trust_ema deterministically
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
            elif e["kind"] == "price_request":
                req_e = e["request"]
                pk_e = req_e["legs"][0]["pickup"]["placeId"]
                if self.gate_supply.get(pk_e, 0) >= self.p.min_supply or (
                    self.p.return_hub_min_supply > 0 and self.supply.get(req_e["legs"][-1]["delivery"]["placeId"], 0) >= self.p.return_hub_min_supply
                ):
                    t_c = self.dealer_trust[req_e["dealerId"]]
                    self.trust_ema += self.p.trust_ema_alpha * (t_c - self.trust_ema)
                            
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
            if self.p.future_sameday_slow and len(req["legs"]) == 1:
                sd_opt = next((o for o in req["options"] if o["kind"] == "same_day"), None)
                if sd_opt and sd_opt["deadline"] // DAY > req["arrivedAt"] // DAY and self.supply.get(pickup, 0) < max(self.p.min_supply, self.p.same_day_min_supply):
                    self.fut_sd_reqs.add(req_id)

        if self.p.day_shock_lr > 0:
            cur_day = self.now // DAY
            for e in history:
                if e["kind"] in ("order_won", "order_lost"):
                    rid = e["order"]["id"] if e["kind"] == "order_won" else e["requestId"]
                    req = self.requests.get(rid)
                    if req is None:
                        continue
                    arr = req["arrivedAt"]
                    if arr // DAY != cur_day or not (480 <= arr % DAY <= 1080):
                        continue
                    if self.p.ext_ring_neutral_learn and rid in self.ext_ring_reqs:
                        continue
                    won = e["kind"] == "order_won"
                    step = (1 - self.p.price_target_win) if won else -self.p.price_target_win
                    pk = req["legs"][0]["pickup"]["placeId"]
                    for nb in self._shock_neighbors(pk):
                        self.day_shock[(cur_day, nb)] = clamp(
                            self.day_shock[(cur_day, nb)] + self.p.day_shock_lr * step,
                            self.p.day_shock_min,
                            self.p.day_shock_max,
                        )

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
        self._rejoin_network_and_relay(snapshot, history)
        for e in history:
            if e["kind"] == "gig_expired":
                g = gigs_by_id.get(e["gigId"])
                if g:
                    for s in g["stops"]:
                        oid = s["orderId"]
                        if not self.p.urgent_hygiene or oid not in self.orders or self.cannot_be_on_time(self.orders[oid]):
                            self.lost.add(oid)
        if self.p.war_morning_reset > 0:
            by_d: dict[int, list[bool]] = defaultdict(list)
            for e in history:
                if e["kind"] == "order_won":
                    by_d[e["at"] // DAY].append(True)
                elif e["kind"] == "order_lost":
                    by_d[e["at"] // DAY].append(False)
            cur_d = self.now // DAY
            for d_idx, outs in by_d.items():
                if d_idx < cur_d and len(outs) >= 15 and sum(outs) / len(outs) < 0.25:
                    self.war_reset_done = True
        for order_id, order in self.orders.items():
            if undelivered(order) and not self.staffed(order) and (self.now > order["lastPickupAt"] or (self.p.urgent_hygiene and self.cannot_be_on_time(order))):
                self.lost.add(order_id)
            elif (
                self.p.trade_in_handoff_pace
                and len(order["legs"]) == 2
                and 0 in undelivered(order)
                and not self.staffed(order)
            ):
                d0 = self.geo.minutes(order["legs"][0]["pickup"]["placeId"], order["legs"][0]["delivery"]["placeId"])
                leg0_last_pk = order["legs"][0]["delivery"]["window"]["to"] - d0 - 15
                if leg0_last_pk - 3 * HOUR <= self.now <= leg0_last_pk:
                    self.urgent.add(order_id)
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
            if any(g["status"] == "withdrawn" for g in g_list) and order_id not in self.relay_ever_paired:
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
            req = self.requests[order["id"]]
            option = next((o for o in req["options"] if o["kind"] == order["option"]), None)
            if option:
                denom = option["listPriceCents"] * self.lane_mult(req)
                if self.p.trust_center_slope > 0.0 and self.level >= 8:
                    denom *= math.exp(self.p.trust_center_slope * (self.dealer_trust[req["dealerId"]] - self.trust_ema))
                r_val = order["priceCents"] / denom
                disc = 0.0
                if order["option"] == "within_3_days" and self.p.w3d_discount > 0:
                    disc = max(disc, self.p.w3d_discount)
                if order["option"] != "same_day" and order["deadline"] >= 7 * DAY and self.p.mon2_discount > 0:
                    disc = max(disc, self.p.mon2_discount)
                if disc > 0 and disc < 0.9:
                    r_val /= (1.0 - disc)
                ratios.append(r_val)
        if ratios:
            self.mult = clamp(median(ratios), self.p.price_mult_min, self.p.price_mult_max)
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
    trade_in_seq_slack: bool = False,
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
        dl_cap = min(delivery["window"]["to"], order["deadline"]) if (trade_in_seq_slack and len(order["legs"]) == 2 and leg == 0) else order["deadline"]
        delivery_base: TimeWindow = {"from": delivery["window"]["from"], "to": max(delivery["window"]["from"], dl_cap)}
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
