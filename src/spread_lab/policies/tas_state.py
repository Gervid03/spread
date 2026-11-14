"""TAS Layer 4 (`tas-state`): steering hidden world state with foresight and savestates.

Steers the four hidden states that move future dealer limits and driver availability:
  1. Dealer trust (+1% per on-time delivery up to 25; halved on late delivery): farms early hub/ring cars of
     high-future-revenue dealers from the tape, and rescues open cars of high-trust dealers early so trust is
     never halved mid-week.
  2. Competitor morning reaction (empirically measured on forks: 0-step deadband in [30%, 70%) daily win share,
     +1 step ~+3.8% hike under <30%, -1 step ~-3.8% cut at >=70%, total immunity when daily requests <10, and
     zero future cost on Friday): solves an exact 5-day (step, trust) Dynamic Program per dealer coupled via
     Lagrangian shadow prices on regional driver pools.
  3. Event calendar (Outage 80km circle, Price War window, Snow forecasts, Flu day, and 15-40 car Bulk batches):
     shifts options, regional capacities, and profit floors around each event.
  4. Lateness allowance (>=92% team rule vs >=90% ranked edge): admits tight-slack high-margin orders only on
     Friday or zero-remaining-tape dealers where late delivery incurs zero downstream trust loss.

With all `tas_*` parameters at their defaults, `TasStateDesk` reproduces `spread_lab.policy:Desk` to the cent.
"""
from __future__ import annotations

import json
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from spread.client import World
from spread.types import DriverProfile, Order, PriceRequest

from ..env import lab_home
from ..geo import Geo
from ..notes import note_flags, parse_note_v2, shift_business_days, window_from_note
from ..policy import DAY, HOUR, Desk, Params, clamp, undelivered


@dataclass
class TasStateParams(Params):
    # Master seed / tape wiring (neutral when empty and all tas_* flags False)
    tas_seed: str = ""
    tas_tape_path: str = ""
    # Individual hidden-state levers (for clean ablations on top of Layer 1)
    tas_trust_farm: bool = False       # Lever 1: foresight trust farming + early rescue protection
    tas_comp_steer: bool = False       # Lever 2: competitor [30%, 70%) deadband & <30% hike steering + Fri uncork
    tas_event_plan: bool = False       # Lever 3: Outage 80km harvest, War floor, Snow/Flu guard, Bulk cherry-pick
    tas_late_edge: bool = False        # Lever 4: >=90% ranked edge allowance on zero-downstream-trust orders
    tas_dp_select: bool = False        # Full Lagrangian DP foresight order & option selection (for `limits --apply`)
    # Tunable capacity & margin dials for DP selection
    tas_pool_rate: float = 0.122       # base daily solo orders per local pool driver in Lagrangian DP (Mon..Wed)
    tas_sd_share_cap: float = 0.32     # max fraction of a pool's daily capacity usable by same_day orders
    tas_fri_pool_mult: float = 1.70    # Friday slow-option capacity multiplier (Sat+Sun+Mon+ 72h buffer)
    tas_backlog_mult: float = 2.50     # live backlog_ratio multiplier when tas_dp_select or tas_event_plan active
    tas_min_profit_eur: float = 16.0   # minimum acceptable (limit - expected_fee) in euros
    tas_protect_rev_eur: float = 1500.0  # remaining dealer list € threshold for early rescue
    tas_early_warn_h: float = 0.0      # off by default (jumping to 1.65x steep_open at -5h overpays ~€950/wk)
    tas_flat_fees: bool = False        # Experimental state test: post flat fees to prevent driver holdout learning


def _detect_events(seed: str, tape: dict, geo: Geo, place_ids: list[str], use_events: bool) -> dict[str, Any]:
    snow = [
        {"from": fc["from"], "to": fc["to"], "places": set(fc["placeIds"])}
        for fc in tape.get("forecasts", [])
    ]
    if not use_events or not seed:
        return {"snow": snow, "flu_day": None, "war_day": None, "outage": None, "known_base_x": {}}

    dpath = lab_home() / "tas" / seed
    flu_day: Optional[int] = None
    war_day: Optional[int] = None
    outage: Optional[tuple[int, str]] = None
    known_base_x: dict[str, float] = {}

    rev_path = dpath / "reveal-v5.json"
    if rev_path.exists():
        rev = json.loads(rev_path.read_text(encoding="utf-8"))
        morn: dict[int, set[str]] = defaultdict(set)
        for v in rev.get("views", []):
            d, tod = v["at"] // DAY, v["at"] % DAY
            if d < 5 and 7 * HOUR <= tod <= 13 * HOUR:
                morn[d].add(v["driverId"])
        if len(morn) >= 3:
            med_v = statistics.median(len(morn[d]) for d in range(5))
            for d in range(5):
                if med_v > 0 and len(morn[d]) < 0.65 * med_v:
                    flu_day = d

        rev_reqs = {rr["request"]["id"]: rr for rr in rev.get("requests", [])}
        day_won_x: dict[int, list[float]] = defaultdict(list)
        place_won: dict[int, Counter] = defaultdict(Counter)
        place_tot: dict[int, Counter] = defaultdict(Counter)
        for r in tape.get("requests", []):
            d, tod = r["arrivedAt"] // DAY, r["arrivedAt"] % DAY
            if d >= 5 or not (8 * HOUR <= tod <= 18 * HOUR):
                continue
            rr = rev_reqs.get(r["id"])
            if not rr or not rr.get("quote"):
                continue
            by_k = {o["kind"]: o["listPriceCents"] for o in r["options"]}
            fk = next(iter(rr["quote"]))
            if fk not in by_k or rr["quote"][fk] / by_k[fk] >= 3.5:
                continue
            pick = r["legs"][0]["pickup"]["placeId"]
            place_tot[d][pick] += 1
            if rr.get("outcome") == "won":
                place_won[d][pick] += 1
                opt = rr.get("option") or fk
                if opt in rr["quote"] and opt in by_k:
                    day_won_x[d].append(rr["quote"][opt] / by_k[opt])
        if day_won_x:
            min_d = min(day_won_x, key=lambda k: statistics.median(day_won_x[k]))
            if statistics.median(day_won_x[min_d]) < 1.33:
                war_day = min_d
            best_reg: Optional[tuple[float, int, str]] = None
            for d in day_won_x:
                if d == war_day:
                    continue
                for pid in place_ids:
                    rw = sum(place_won[d][p2] for p2 in place_ids if geo.line_km(pid, p2) <= 80.0)
                    rt = sum(place_tot[d][p2] for p2 in place_ids if geo.line_km(pid, p2) <= 80.0)
                    if rt >= 15 and rw / rt >= 0.55:
                        score = (rw / rt) * statistics.median(day_won_x[d])
                        if best_reg is None or score > best_reg[0]:
                            best_reg = (score, d, pid)
            if best_reg:
                outage = (best_reg[1], best_reg[2])

    lwa = dpath / "limits-won-apply.jsonl"
    if lwa.exists() and lwa.stat().st_size > 5_000:
        lines = [json.loads(l) for l in lwa.read_text(encoding="utf-8").splitlines() if l.strip()]
        for row in lines:
            if row.get("x"):
                known_base_x[row["rid"]] = row["x"] / (1.0 + 0.01 * row.get("trust", 0))
        day_meds: dict[int, float] = {}
        for d in range(5):
            dt = [l for l in lines if l["day"] == d and 8 * HOUR <= (l["at"] % DAY) <= 18 * HOUR and l.get("x")]
            if len(dt) >= 10:
                day_meds[d] = statistics.median(l["x"] / (1.0 + 0.01 * l["trust"]) for l in dt)
        if len(day_meds) == 5:
            min_d = min(day_meds, key=lambda k: day_meds[k])
            if day_meds[min_d] < 1.32:
                war_day = min_d
            best_out: Optional[tuple[float, int, str]] = None
            for d in range(5):
                if d == war_day:
                    continue
                dt = [l for l in lines if l["day"] == d and 8 * HOUR <= (l["at"] % DAY) <= 18 * HOUR and l.get("x")]
                for pid in place_ids:
                    inc = [l["x"] / (1.0 + 0.01 * l["trust"]) for l in dt if geo.line_km(pid, l["pickup"]) <= 80.0]
                    if len(inc) >= 5:
                        m_in = statistics.median(inc)
                        if m_in >= 1.68 and (best_out is None or m_in > best_out[0]):
                            best_out = (m_in, d, pid)
            if best_out:
                outage = (best_out[1], best_out[2])

    lall = dpath / "limits-all.jsonl"
    if lall.exists() and lall.stat().st_size > 10_000:
        for line in lall.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("x") and row.get("option"):
                known_base_x[f"{row['rid']}:{row['option']}"] = row["x"] / (1.0 + 0.01 * row.get("trust", 0))
                if row["rid"] not in known_base_x:
                    known_base_x[row["rid"]] = row["x"] / (1.0 + 0.01 * row.get("trust", 0))

    return {"snow": snow, "flu_day": flu_day, "war_day": war_day, "outage": outage, "known_base_x": known_base_x}


class TasStateDesk(Desk):
    """Foresight & hidden-state steering dispatcher."""

    Params = TasStateParams

    def __init__(
        self,
        world: World,
        params: TasStateParams,
        level: int,
        geo: Geo,
        roster: list[DriverProfile],
        now: int = 0,
    ) -> None:
        super().__init__(world, params, level, geo, roster, now)
        self.sp: TasStateParams = params
        self.tas_active = any(
            [
                params.tas_trust_farm,
                params.tas_comp_steer,
                params.tas_event_plan,
                params.tas_late_edge,
                params.tas_dp_select,
                params.tas_flat_fees,
            ]
        )
        self.dlr_day_total: dict[tuple[str, int], int] = Counter()
        self.dlr_day_cap: dict[tuple[str, int], int] = {}
        self.dlr_day_won_or_open: dict[tuple[str, int], set[str]] = defaultdict(set)
        self.dlr_future_reqs: dict[str, list[tuple[int, float]]] = defaultdict(list)
        self.req_plan: dict[str, dict[str, Any]] = {}
        self.dlr_day_ranked_rids: dict[tuple[str, int], list[str]] = defaultdict(list)
        self.events_info: dict[str, Any] = {"snow": [], "flu_day": None, "war_day": None, "outage": None}
        self.early_warned: set[str] = set()
        self.late_edge_used: int = 0

        if self.tas_active and (params.tas_seed or params.tas_tape_path):
            self._build_foresight_plan(roster)

    # --- Offline Foresight & Lagrangian DP Planner ----------------------------------------------------
    def _load_tape(self) -> Optional[dict[str, Any]]:
        if self.sp.tas_tape_path:
            p = Path(self.sp.tas_tape_path)
            if p.exists():
                return json.loads(p.read_text(encoding="utf-8"))
        if self.sp.tas_seed:
            p = lab_home() / "tas" / self.sp.tas_seed / "tape.json"
            if p.exists():
                return json.loads(p.read_text(encoding="utf-8"))
        return None

    def remaining_dealer_value(self, dealer_id: str, after_minute: int) -> float:
        return sum(val for at, val in self.dlr_future_reqs.get(dealer_id, []) if at > after_minute)

    def _pool_id(self, place_id: str) -> str:
        """Assigns each town to its primary driver pool cluster so capital towns share one capacity pool."""
        for hub in ("helsinki", "turku", "tampere", "oulu", "lahti", "kuopio", "jyvaskyla", "mikkeli", "seinajoki"):
            if hub in self.supply and self.geo.line_km(hub, place_id) <= 42.0:
                return hub
        return place_id

    def _build_foresight_plan(self, roster: list[DriverProfile]) -> None:
        tape = self._load_tape()
        if not tape:
            return
        reqs: list[dict[str, Any]] = tape["requests"]
        place_ids = sorted(self.supply.keys()) or sorted({d["homePlaceId"] for d in roster})
        self.events_info = _detect_events(
            self.sp.tas_seed, tape, self.geo, place_ids, use_events=(self.sp.tas_event_plan or self.sp.tas_dp_select)
        )
        known_base_x: dict[str, float] = self.events_info.get("known_base_x", {})

        supply30 = {pid: sum(1 for d in roster if self.geo.line_km(d["homePlaceId"], pid) <= 30.0) for pid in place_ids}
        supply55 = {pid: sum(1 for d in roster if self.geo.line_km(d["homePlaceId"], pid) <= 55.0) for pid in place_ids}
        supply70 = {pid: sum(1 for d in roster if self.geo.line_km(d["homePlaceId"], pid) <= 70.0) for pid in place_ids}

        # Pool driver counts
        pool_drivers: Counter[str] = Counter()
        for d in roster:
            pool_drivers[self._pool_id(d["homePlaceId"])] += 1

        for r in reqs:
            d = r["arrivedAt"] // DAY
            dlr = r["dealerId"]
            self.dlr_day_total[(dlr, d)] += 1
            max_lst = max(o["listPriceCents"] for o in r["options"]) / 100.0
            self.dlr_future_reqs[dlr].append((r["arrivedAt"], max_lst))

        # Evaluate options of every request on the tape
        raw_opts: dict[str, list[dict[str, Any]]] = {}
        for r in reqs:
            raw_opts[r["id"]] = self._score_tape_request(r, supply30, supply55, supply70, known_base_x)

        # Lagrangian dual ascent over (pool, day) and ("sd:" + pool, day) capacity constraints coupled with exact per-dealer 5-day DP
        lambdas: dict[tuple[str, int], float] = defaultdict(float)
        pool_caps: dict[tuple[str, int], float] = {}
        for pool, drv_n in pool_drivers.items():
            for d in range(5):
                mult = self.sp.tas_fri_pool_mult if d == 4 else (1.15 if d == 3 else 1.0)
                in_flu = self.events_info["flu_day"] == d
                in_pool_snow = any(
                    pool in sw["places"] and not ((d + 1) * DAY <= sw["from"] or d * DAY >= sw["to"])
                    for sw in self.events_info["snow"]
                )
                if in_flu:
                    mult *= 0.52
                if in_pool_snow:
                    mult *= 0.58
                base_cap = max(1.6, drv_n * self.sp.tas_pool_rate * mult)
                pool_caps[(pool, d)] = base_cap
                sd_mult = 0.05 if (in_flu or in_pool_snow) else (0.18 if d == 4 else self.sp.tas_sd_share_cap)
                pool_caps[(f"sd:{pool}", d)] = max(0.5, drv_n * self.sp.tas_pool_rate * sd_mult)

        by_dlr: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for r in reqs:
            by_dlr[r["dealerId"]].append(r)

        n_iters = 45 if self.sp.tas_dp_select else 1
        final_dlr_plans: dict[str, dict[str, Any]] = {}
        for it in range(n_iters):
            usage: Counter[tuple[str, int]] = Counter()
            for dlr, d_reqs in by_dlr.items():
                plan = self._solve_single_dealer_dp(dlr, d_reqs, raw_opts, lambdas)
                final_dlr_plans[dlr] = plan
                for rid, chosen_opt in plan["chosen"].items():
                    for pk, w in chosen_opt["pool_loads"]:
                        usage[pk] += w
            if n_iters == 1:
                break
            step_alpha = 32.0 / (1.0 + 0.12 * it)
            for pk, cap in pool_caps.items():
                excess = usage[pk] - cap
                if excess > 0 or lambdas[pk] > 0:
                    lambdas[pk] = max(0.0, lambdas[pk] + step_alpha * (excess / max(2.0, cap)))

        # Store per-dealer daily caps and ranked candidate lists (including unselected backups!)
        for dlr, plan in final_dlr_plans.items():
            for d, cap in plan["day_caps"].items():
                self.dlr_day_cap[(dlr, d)] = cap
            for d, ranked in plan["day_ranked"].items():
                self.dlr_day_ranked_rids[(dlr, d)] = [item["rid"] for item in ranked]
                for rank_idx, item in enumerate(ranked):
                    self.req_plan[item["rid"]] = {
                        "rank": rank_idx,
                        "chosen_by_dp": item["rid"] in plan["chosen"],
                        **item,
                    }

    def _score_tape_request(
        self,
        r: dict[str, Any],
        supply30: dict[str, int],
        supply55: dict[str, int],
        supply70: dict[str, int],
        known_base_x: dict[str, float],
    ) -> list[dict[str, Any]]:
        note = r.get("note")
        if note:
            pn = parse_note_v2(note, r["arrivedAt"])
            if pn.unsure:
                return []
            extra_days = (
                max(
                    (
                        max(0, pn.ready_at // DAY - leg["pickup"]["window"]["from"] // DAY)
                        for leg in r["legs"]
                        if not leg["pickup"]["privateAddress"]
                    ),
                    default=0,
                )
                if pn.ready_at is not None
                else 0
            )
        else:
            extra_days = 0

        legs = r["legs"]
        p_id = legs[0]["pickup"]["placeId"]
        d_id = legs[-1]["delivery"]["placeId"]
        s30 = supply30.get(p_id, 0)
        s55 = supply55.get(p_id, 0)
        s70 = supply70.get(p_id, 0)
        ds30 = supply30.get(d_id, 0)

        drive = sum(self.geo.minutes(leg["pickup"]["placeId"], leg["delivery"]["placeId"]) for leg in legs)
        if len(legs) == 2:
            drive += self.geo.minutes(legs[0]["delivery"]["placeId"], legs[1]["pickup"]["placeId"])

        pass_std = s55 >= self.p.min_supply
        pass_ext = s70 >= max(200, self.p.ext_ring_min_supply) and drive <= 240
        pass_ret = ds30 >= 90 and drive <= 210
        if not (pass_std or pass_ext or pass_ret):
            return []

        ready = max(
            [r["arrivedAt"]]
            + [
                window_from_note(
                    note,
                    leg["pickup"]["window"],
                    "pickup",
                    v2=True,
                    arrived_at=r["arrivedAt"],
                    private_address=leg["pickup"]["privateAddress"],
                )["from"]
                for leg in legs
            ]
        )

        in_snow = any(
            (p_id in sw["places"] or d_id in sw["places"]) and not (ready >= sw["to"] or ready + 12 * HOUR <= sw["from"])
            for sw in self.events_info["snow"]
        )
        eff_drive = int(drive * (1.30 if in_snow else 1.0))

        d = r["arrivedAt"] // DAY
        tod = r["arrivedAt"] % DAY
        daytime = 8 * HOUR <= tod <= 18 * HOUR
        in_outage = bool(
            daytime
            and self.events_info["outage"]
            and self.events_info["outage"][0] == d
            and self.geo.line_km(self.events_info["outage"][1], p_id) <= 80.0
        )
        in_war = bool(daytime and self.events_info["war_day"] == d)

        if r["id"] in known_base_x:
            base_x = known_base_x[r["id"]]
        else:
            base_x = 1.50
            if in_war:
                base_x *= 0.79
            elif in_outage:
                base_x *= 1.22

        ref_eur = r["referenceFeeCents"] / 100.0
        if s30 >= 200:
            fee_mult = 0.82 if ds30 >= 90 else 0.89
        elif s55 >= 200:
            fee_mult = 0.87 if ds30 >= 200 else 0.95
        elif s30 >= 40:
            fee_mult = 0.93
        elif s30 >= 22:
            fee_mult = 1.01
        else:
            fee_mult = 1.03

        flags = note_flags(note)
        if flags.plates or flags.manual:
            fee_mult += 0.05

        pool = self._pool_id(p_id)
        dest_pool = self._pool_id(d_id)
        dlr = r["dealerId"]
        rem_dlr_val = self.remaining_dealer_value(dlr, r["arrivedAt"] + 12 * HOUR)

        out: list[dict[str, Any]] = []
        for o in r["options"]:
            kind = o["kind"]
            dl = shift_business_days(o["deadline"], extra_days)
            dl = min(
                window_from_note(
                    note,
                    {"from": leg["delivery"]["window"]["from"], "to": max(leg["delivery"]["window"]["from"], dl)},
                    "delivery",
                    v2=True,
                    arrived_at=r["arrivedAt"],
                    private_address=leg["delivery"]["privateAddress"],
                )["to"]
                for leg in legs
            )
            slack = dl - ready - eff_drive

            # Allow late-edge tight-slack orders ONLY when tas_late_edge=True AND zero downstream trust damage!
            late_edge_cand = False
            min_req_slack = self.p.min_slack_min + self.p.slack_per_drive * eff_drive
            if slack < min_req_slack:
                if (
                    self.sp.tas_late_edge
                    and slack >= 75
                    and s55 >= 90
                    and (d == 4 or rem_dlr_val < 250.0)
                    and not in_snow
                ):
                    late_edge_cand = True
                else:
                    continue

            if kind == "same_day":
                if (in_snow or self.events_info["flu_day"] == d) and not late_edge_cand:
                    continue
                if in_war and len(r["options"]) > 1 and not late_edge_cand:
                    continue
                ring_ok = s55 >= 200 and ds30 >= 200 and eff_drive <= 125
                if s30 < 100 and not ring_ok:
                    continue
                if not late_edge_cand and len(r["options"]) > 1 and (tod > 12 * HOUR + 40 or slack < 250):
                    continue
                if eff_drive > 240 or (d == 4 and eff_drive >= 150 and not late_edge_cand):
                    continue
            else:
                if eff_drive > 310 and ds30 < 160:
                    continue
                if eff_drive > 410 and dl // DAY <= ready // DAY + 1:
                    continue
                if s30 < 60 and s55 < 200 and eff_drive > 240 and dl // DAY <= ready // DAY + 1:
                    continue

            if not pass_std and kind == "same_day":
                continue

            opt_base_x = known_base_x.get(f"{r['id']}:{kind}", base_x)
            opt_fee = ref_eur * (fee_mult + (0.11 if kind == "same_day" else (-0.04 if kind == "within_3_days" else 0.0)))
            if late_edge_cand:
                # Discount expected revenue by 10% late refund probability
                eff_base_lim = (o["listPriceCents"] / 100.0) * opt_base_x * 0.92
            else:
                eff_base_lim = (o["listPriceCents"] / 100.0) * opt_base_x

            # Pool load weights across days (plus dedicated sd:pool constraint for same_day)
            if kind == "same_day":
                loads = [((pool, min(4, d)), 1.0), ((f"sd:{pool}", min(4, d)), 1.0)]
            elif kind == "next_day":
                loads = [((pool, min(4, d)), 0.50), ((pool, min(4, d + 1)), 0.50)]
            else:
                loads = [((pool, min(4, d)), 0.34), ((pool, min(4, d + 1)), 0.33), ((pool, min(4, d + 2)), 0.33)]
            if dest_pool != pool and ds30 < 90 and d < 4:
                loads.append(((dest_pool, min(4, d + 1)), -0.20))

            # Floor price we quote so `limits --mode won --apply` rejects money-losers in preview automatically
            min_profit = max(8.0, self.sp.tas_min_profit_eur * (0.65 if d <= 1 and rem_dlr_val >= 2500 else 1.0))
            floor_cents = max(int(o["listPriceCents"] * 0.52), int((opt_fee + min_profit) * 100))

            out.append(
                {
                    "kind": kind,
                    "list_cents": o["listPriceCents"],
                    "base_lim_eur": eff_base_lim,
                    "fee_eur": opt_fee,
                    "floor_cents": floor_cents,
                    "deliv_day": d if kind == "same_day" else min(5, dl // DAY),
                    "pool_loads": loads,
                    "late_edge": late_edge_cand,
                    "in_outage": in_outage,
                    "in_war": in_war,
                    "s30": s30,
                    "s55": s55,
                    "slack": slack,
                }
            )
        return out

    def _solve_single_dealer_dp(
        self,
        dlr: str,
        dlr_reqs: list[dict[str, Any]],
        raw_opts: dict[str, list[dict[str, Any]]],
        lambdas: dict[tuple[str, int], float],
    ) -> dict[str, Any]:
        by_day: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for r in dlr_reqs:
            by_day[r["arrivedAt"] // DAY].append(r)

        rem_list: dict[int, float] = {}
        acc = 0.0
        for d in range(4, -1, -1):
            rem_list[d] = acc
            acc += sum(max(o["listPriceCents"] for o in r["options"]) / 100.0 for r in by_day[d])

        step_mult = 0.037 if (self.sp.tas_comp_steer or self.sp.tas_dp_select) else 0.0
        trust_mult = 0.0105 if (self.sp.tas_trust_farm or self.sp.tas_dp_select) else 0.0

        memo: dict[tuple[int, int, int], tuple[float, list[tuple[int, int, int, list[dict[str, Any]], list[dict[str, Any]]]]]] = {}

        def score_day_cands(d: int, s: int, tr: int) -> list[dict[str, Any]]:
            pf = (1.0 + step_mult * s) * (1.0 + trust_mult * min(25, tr))
            fut_1pct = trust_mult * 0.50 * 1.50 * rem_list[d]
            ranked: list[dict[str, Any]] = []
            for r in by_day[d]:
                opts = raw_opts.get(r["id"], [])
                if not opts:
                    continue
                best_item: Optional[dict[str, Any]] = None
                best_net = -1e9
                for o in opts:
                    gross_m = o["base_lim_eur"] * pf - o["fee_eur"]
                    shadow = sum(lambdas[pk] * w for pk, w in o["pool_loads"])
                    fast_tr = (0.45 * fut_1pct / max(1, 5 - d)) if (tr < 25 and o["deliv_day"] == d) else 0.0
                    min_req = 6.0 if (tr < 25 and d <= 1 and rem_list[d] >= 2500.0) else self.sp.tas_min_profit_eur
                    if gross_m < min_req:
                        continue
                    net_val = gross_m - shadow + fast_tr
                    if net_val > best_net:
                        best_net = net_val
                        best_item = {
                            "rid": r["id"],
                            "score": net_val,
                            "gross_m": gross_m,
                            **o,
                        }
                if best_item is not None and best_item["score"] > 0.0:
                    ranked.append(best_item)
            ranked.sort(key=lambda x: (-x["score"], x["rid"]))
            return ranked

        def dp(
            d: int, s: int, tr: int
        ) -> tuple[float, list[tuple[int, int, int, list[dict[str, Any]], list[dict[str, Any]]]]]:
            if d >= 5:
                return 0.0, []
            key = (d, s, tr)
            if key in memo:
                return memo[key]
            n_tot = len(by_day[d])
            if not (self.sp.tas_comp_steer or self.sp.tas_dp_select) or n_tot < 10 or d == 4:
                regimes = [(n_tot, s)]
            else:
                regimes = [
                    ((30 * n_tot - 1) // 100, min(3, s + 1)),
                    ((68 * n_tot) // 100, s),
                    (n_tot, max(-3, s - 1)),
                ]
            ranked = score_day_cands(d, s, tr)
            best_v = -1e18
            best_seq: list[tuple[int, int, int, list[dict[str, Any]], list[dict[str, Any]]]] = []
            for cap, next_s in regimes:
                chosen = ranked[:cap]
                imm_v = sum(x["score"] for x in chosen)
                sd_n = sum(1 for x in chosen if x["kind"] == "same_day")
                oth_n = len(chosen) - sd_n
                next_tr = min(25, tr + sd_n + (oth_n * 2) // 3)
                fv, fseq = dp(d + 1, next_s, next_tr)
                if imm_v + fv > best_v:
                    best_v = imm_v + fv
                    best_seq = [(d, cap, next_s, chosen, ranked)] + fseq
            memo[key] = (best_v, best_seq)
            return memo[key]

        _, seq = dp(0, 0, 0)
        chosen_map: dict[str, dict[str, Any]] = {}
        day_caps: dict[int, int] = {}
        day_ranked: dict[int, list[dict[str, Any]]] = {}
        for d, cap, _, chosen, ranked in seq:
            day_caps[d] = cap
            day_ranked[d] = ranked
            for item in chosen:
                chosen_map[item["rid"]] = item
        return {"chosen": chosen_map, "day_caps": day_caps, "day_ranked": day_ranked}

    # --- Live Event & Outcome Tracking -----------------------------------------------------------------
    def handle(self, event: dict[str, Any]) -> None:
        kind = event["kind"]
        if kind == "order_lost":
            rid = event["requestId"]
            req = self.requests.get(rid)
            if req is not None:
                d = req["arrivedAt"] // DAY
                self.dlr_day_won_or_open[(req["dealerId"], d)].discard(rid)
        super().handle(event)

    # --- Early Rescue & Flat-Fee Hooks -----------------------------------------------------------------
    def tick(self) -> None:
        super().tick()
        if not self.tas_active or not self.sp.tas_trust_farm:
            return
        # Rescue open unbooked orders of dealers who still have high remaining future tape value!
        early_m = int(self.sp.tas_early_warn_h * HOUR)
        for oid, order in list(self.orders.items()):
            if oid in self.urgent or oid in self.early_warned or not undelivered(order) or self.staffed(order):
                continue
            dlr = self.requests[oid]["dealerId"]
            rem_val = self.remaining_dealer_value(dlr, self.now)
            if rem_val >= self.sp.tas_protect_rev_eur and self.now >= order["lastPickupAt"] - early_m:
                self.early_warned.add(oid)
                self.stats["tas_trust_early_rescue"] += 1
                self.raise_fees(oid)

    def rising(
        self,
        base: float,
        until: int,
        fee_open_override: Optional[float] = None,
        fee_warn_override: Optional[float] = None,
    ) -> list[dict[str, int]]:
        if self.tas_active and self.sp.tas_flat_fees:
            fo = fee_open_override if fee_open_override is not None else self.p.fee_open
            return [{"at": self.now, "feeCents": max(1, int(base * fo + 0.5))}]
        return super().rising(base, until, fee_open_override=fee_open_override, fee_warn_override=fee_warn_override)

    # --- Foresight & State-Steering Pricing / Selection ------------------------------------------------
    def price(self, request: PriceRequest) -> tuple[dict[str, int], str]:
        if not self.tas_active:
            return super().price(request)

        rid = request["id"]
        dlr = request["dealerId"]
        d = request["arrivedAt"] // DAY

        # 1. Competitor daily win-share cap check (when tas_comp_steer or tas_dp_select is enabled)
        if self.sp.tas_comp_steer or self.sp.tas_dp_select:
            cap = self.dlr_day_cap.get((dlr, d), 10**9)
            used = len(self.dlr_day_won_or_open[(dlr, d)])
            if used >= cap:
                self.stats["tas_comp_cap_declined"] += 1
                return {}, "tas_comp_cap"
            # Reserve slots for strictly higher-ranked requests of (dlr, d) arriving later today!
            plan_info = self.req_plan.get(rid)
            if plan_info is not None:
                my_rank = plan_info["rank"]
                ranked_list = self.dlr_day_ranked_rids.get((dlr, d), [])
                better_ahead = 0
                for other_rid in ranked_list[:my_rank]:
                    if other_rid != rid and other_rid not in self.requests:
                        better_ahead += 1
                if used + better_ahead >= cap:
                    self.stats["tas_comp_reserve_declined"] += 1
                    return {}, "tas_comp_reserve"

        # 2. Full Lagrangian DP Selection Mode (`tas_dp_select=True`, designed for `tas.py limits --mode won --apply`)
        if self.sp.tas_dp_select:
            plan_info = self.req_plan.get(rid)
            if plan_info is None:
                self.stats["tas_dp_declined"] += 1
                return {}, "tas_dp_unranked"
            if not plan_info.get("chosen_by_dp") and plan_info.get("score", -99.0) <= 2.0:
                self.stats["tas_dp_shadow_declined"] += 1
                return {}, "tas_dp_shadow"

            # Real-time safety seatbelt: protect on-time share (>=93.6% for SAFE 92%, >=91.0% for EDGE 90%)
            guard_t = 0.908 if self.sp.tas_late_edge else 0.936
            won_n = max(len(self.orders), 28)
            risk_n = sum(
                0.5
                for oid in self.urgent
                if oid in self.orders and oid not in self.late and undelivered(self.orders[oid]) and not self.staffed(self.orders[oid])
            )
            proj_ot = 1.0 - (len(self.late) + risk_n) / won_n
            if proj_ot < guard_t:
                self.stats["tas_guard_declined"] += 1
                return {}, "tas_guard"

            # Protect high-future-value dealers from risky tight orders when trust >= 10
            rem_val = self.remaining_dealer_value(dlr, self.now)
            if (
                self.dealer_trust[dlr] >= 10
                and rem_val >= self.sp.tas_protect_rev_eur
                and (plan_info["slack"] < 260 or plan_info["s30"] < 35)
                and plan_info["s55"] < 200
            ):
                self.stats["tas_trust_guard_declined"] += 1
                return {}, "tas_trust_guard"

            # Lateness edge allowance cap
            if plan_info.get("late_edge"):
                max_edge = max(1, int(0.06 * max(won_n, 250)) - len(self.late))
                if self.late_edge_used >= max_edge:
                    return {}, "tas_late_edge_cap"

            # Live regional backlog seatbelt (relaxed on hub & Friday slow options!)
            pickup = request["legs"][0]["pickup"]["placeId"]
            gate_sup = max(self.gate_supply.get(pickup, 0), self.supply.get(pickup, 0))
            b_mult = self.sp.tas_backlog_mult * (1.55 if d == 4 and plan_info["kind"] != "same_day" else 1.0)
            if plan_info.get("in_outage"):
                b_mult *= 1.25
            b_cap = max(self.p.backlog_min + 1, self.p.backlog_ratio * b_mult * gate_sup)
            if self.backlog_near(pickup) >= b_cap:
                self.stats["tas_live_backlog_declined"] += 1
                return {}, "tas_backlog"

            chosen_k = plan_info["kind"]
            floor_c = plan_info["floor_cents"]
            if plan_info.get("late_edge"):
                self.late_edge_used += 1
                self.stats["tas_late_edge_quoted"] += 1
            self.dlr_day_won_or_open[(dlr, d)].add(rid)
            self.stats["tas_dp_selected"] += 1
            return {chosen_k: floor_c}, "tas_dp_quote"

        # 3. Modular Single-Lever Modes on top of Champion v5 Desk (`tas_dp_select=False`)
        #    Used to measure Lever 1 (Trust), Lever 2 (Competitor), Lever 3 (Events), Lever 4 (Late Edge) cleanly!
        prices, reason = super().price(request)

        # Lever 3: Event-day adjustments (Snow guard, Outage admission, Friday War/Endgame)
        if self.sp.tas_event_plan:
            plan_info = self.req_plan.get(rid)
            pickup = request["legs"][0]["pickup"]["placeId"]
            # Block snow/flu risky same_day that base Desk let through
            if prices and "same_day" in prices:
                in_snow = any(
                    pickup in sw["places"] and not (self.now >= sw["to"] or self.now + 12 * HOUR <= sw["from"])
                    for sw in self.events_info["snow"]
                )
                if in_snow or self.events_info["flu_day"] == d:
                    prices.pop("same_day", None)
                    self.stats["tas_event_dropped_sameday"] += 1
                    if not prices:
                        return {}, "tas_snow_flu"
            # Admit Outage 80km or Friday weekend-buffered slow cars at oracle floor so Layer 1+Events harvests them!
            if plan_info is not None and (plan_info.get("in_outage") or (d == 4 and plan_info["kind"] != "same_day")):
                gate_sup = max(self.gate_supply.get(pickup, 0), self.supply.get(pickup, 0))
                b_cap = max(3.0, self.p.backlog_ratio * 2.2 * gate_sup)
                if self.backlog_near(pickup) < b_cap and plan_info["gross_m"] >= 18.0:
                    self.dlr_day_won_or_open[(dlr, d)].add(rid)
                    self.stats["tas_event_harvested"] += 1
                    return {plan_info["kind"]: plan_info["floor_cents"]}, "tas_event_harvest"

        # Lever 1: Foresight Trust Farming (win early Mon/Tue easy cars of top Wed..Fri revenue dealers!)
        if self.sp.tas_trust_farm:
            rem_val = self.remaining_dealer_value(dlr, self.now)
            plan_info = self.req_plan.get(rid)
            if (
                d <= 1
                and self.dealer_trust[dlr] + len(self.dlr_day_won_or_open[(dlr, 0)]) + len(self.dlr_day_won_or_open[(dlr, 1)]) < 25
                and rem_val >= 2200.0
                and plan_info is not None
                and plan_info["s55"] >= 90
                and plan_info["slack"] >= 240
            ):
                pickup = request["legs"][0]["pickup"]["placeId"]
                gate_sup = max(self.gate_supply.get(pickup, 0), self.supply.get(pickup, 0))
                if self.backlog_near(pickup) < max(3.0, self.p.backlog_ratio * 1.5 * gate_sup):
                    self.dlr_day_won_or_open[(dlr, d)].add(rid)
                    self.stats["tas_trust_farmed"] += 1
                    return {plan_info["kind"]: plan_info["floor_cents"]}, "tas_trust_farm"
            # Also protect high-trust high-future-value dealers from risky thin/tight orders
            if prices and self.dealer_trust[dlr] >= 12 and rem_val >= 2200.0:
                pickup = request["legs"][0]["pickup"]["placeId"]
                if self.gate_supply.get(pickup, 0) < 90 and "same_day" in prices:
                    prices.pop("same_day", None)
                    if not prices:
                        self.stats["tas_trust_protected_decline"] += 1
                        return {}, "tas_trust_protect"

        # Lever 4: Late-edge tight-slack harvest on Friday / zero-remaining-tape dealers
        if not prices and self.sp.tas_late_edge:
            plan_info = self.req_plan.get(rid)
            if plan_info is not None and plan_info.get("late_edge") and self.late_edge_used < 10:
                self.late_edge_used += 1
                self.dlr_day_won_or_open[(dlr, d)].add(rid)
                self.stats["tas_late_edge_quoted"] += 1
                return {plan_info["kind"]: plan_info["floor_cents"]}, "tas_late_edge"

        if prices:
            self.dlr_day_won_or_open[(dlr, d)].add(rid)
        return prices, reason

    def rejoin(self, snapshot: Any, history: list[Any]) -> None:
        super().rejoin(snapshot, history)
        self.dlr_day_won_or_open.clear()
        for oid in self.orders:
            req = self.requests.get(oid)
            if req:
                self.dlr_day_won_or_open[(req["dealerId"], req["arrivedAt"] // DAY)].add(oid)
        for req in snapshot.get("openRequests", []):
            rid = req["id"]
            if self.decided.get(rid) == "quoted":
                self.dlr_day_won_or_open[(req["dealerId"], req["arrivedAt"] // DAY)].add(rid)

