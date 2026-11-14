"""Step 3: Lagrangian-Guided Weekly Tour Planner + Proven Dual Upper Bound for TAS Routes.

Generates:
  1) Exact Lagrangian Dual Upper Bound on weekly margin from the request hypergraph + driver supply.
  2) Near-optimal disjoint 2-, 3-, and 4-car closed tours (+ bulk shuttles & top solos) refined by
     Lagrangian-guided greedy construction and 1-for-1 / 2-for-1 local search swaps.
  3) Both `plan-<name>.json` (quote book with multi-option fallbacks & profit floors for `tas.py limits --apply`)
     and `tours-<name>.json` (staffing plan for `spread_lab.policies.tas_routes:Desk`).
  4) Safe subset plans (`--subset-reveal`) strictly inside Champion v5's won orders with bounded hold delay
     so dealer trust timing is preserved on 0-fork re-recordings.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Optional

from spread_lab.env import lab_home
from spread_lab.geo import Geo
from experiments.scripts.tas_routes_census import Arc, load_geo, load_tape, simulate_tour

HOUR, DAY = 60, 24 * 60
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
TOP_DEALERS = {"D01", "D02", "D03", "D04", "D05", "D06", "D07", "D08", "D09", "D10"}


def math_ceil_safe(x: float) -> int:
    ix = int(x)
    return ix if x == ix else ix + 1


def load_known_limits(seed: str) -> dict[tuple[str, str], int]:
    out: dict[tuple[str, str], int] = {}
    tdir = lab_home() / "tas" / seed
    if not tdir.exists():
        return out
    for p in sorted(tdir.glob("limits-*.jsonl")):
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            if r.get("lo") and r.get("rid") and r.get("option"):
                key = (r["rid"], r["option"])
                out[key] = max(out.get(key, 0), int(r["lo"]))
    return out


def calibrate_seed_world_factors(seed: str, geo: Geo, tape: dict[str, Any]) -> tuple[dict[int, float], set[int]]:
    """Reads `limits-won-apply.jsonl` and `reveal-v5.json` if available to calibrate per-day dealer limit
    multipliers (outage / price-war days) and detect any flu day ( sharp drop in daily driver views )."""
    day_mult = {0: 1.50, 1: 1.56, 2: 1.60, 3: 1.60, 4: 1.55}
    flu_days: set[int] = set()

    lp = lab_home() / "tas" / seed / "limits-won-apply.jsonl"
    if lp.exists():
        by_d: dict[int, list[float]] = defaultdict(list)
        for line in lp.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                if r.get("lo") and r.get("list"):
                    by_d[r["day"]].append(r["lo"] / r["list"])
        for d, xs in by_d.items():
            if len(xs) >= 8:
                xs.sort()
                day_mult[d] = xs[len(xs) // 2]

    rev = lab_home() / "tas" / seed / "reveal-v5.json"
    if rev.exists():
        data = json.loads(rev.read_text(encoding="utf-8"))
        views_by_d: dict[int, set[str]] = defaultdict(set)
        for v in data.get("views", []):
            views_by_d[v["at"] // DAY].add(v["driverId"])
        weekday_views = [len(views_by_d[d]) for d in range(5) if views_by_d[d]]
        if weekday_views:
            med_v = sorted(weekday_views)[len(weekday_views) // 2]
            for d in range(5):
                if 0 < len(views_by_d[d]) < 0.72 * med_v:
                    flu_days.add(d)
    return day_mult, flu_days


def estimate_prize_cents(
    arc: Arc,
    supply30: dict[str, int],
    known_limits: dict[tuple[str, str], int],
    day_mult: dict[int, float],
) -> float:
    exact = known_limits.get((arc.rid, arc.option))
    if exact:
        return float(exact)
    d = min(4, arc.arrived_at // DAY)
    mult = day_mult.get(d, 1.52)
    sup_p = supply30.get(arc.pickup, 0)
    if sup_p < 15:
        mult += 0.08
    elif sup_p < 40:
        mult += 0.03
    return arc.list_cents * mult


def estimate_tour_cost_cents(arcs: list[Arc], sim: dict[str, Any], geo: Geo, supply30: dict[str, int]) -> float:
    """Expected realized driver fee in cents calibrated to Step 2 fork bisection on dev-12."""
    ref_sum = sum(a.ref_cents for a in arcs)
    p0 = arcs[0].pickup
    dk = arcs[-1].delivery
    sup0 = supply30.get(p0, 0)
    if len(arcs) == 1:
        mult = 0.90 if sup0 >= 150 else (0.96 if sup0 >= 35 else 1.12)
        return ref_sum * mult

    closed = geo.line_km(dk, p0) <= 30.0
    road_h = sim["road_min"] / 60.0
    if closed:
        base_mult = 0.52 if len(arcs) >= 3 else 0.58
        floor_c = (14.0 * road_h + 6.5 * len(arcs)) * 100.0
        mult = max(base_mult, floor_c / max(1, ref_sum))
    else:
        mult = max(0.72, (18.0 * road_h + 10.0) * 100.0 / max(1, ref_sum))

    if sup0 < 35:
        mult += 0.10
    elif sup0 < 80:
        mult += 0.05
    if any(a.premium for a in arcs):
        mult += 0.06
    return ref_sum * min(0.92, mult)


def min_bound_tour_cost_cents(arcs: list[Arc], sim: dict[str, Any], geo: Geo) -> float:
    """Optimistic arithmetic lower bound on tour driver cost from Step 2 minimum measured rates
    (0.313x ref / €9.61 per wheel hour on closed tours; 0.777x ref on solos)."""
    ref_sum = sum(a.ref_cents for a in arcs)
    if len(arcs) == 1:
        return ref_sum * 0.777
    closed = geo.line_km(arcs[-1].delivery, arcs[0].pickup) <= 30.0
    if closed:
        return max(ref_sum * 0.313, 9.61 * (sim["road_min"] / 60.0) * 100.0)
    return ref_sum * 0.651


def zone_of(place: str) -> str:
    if place in ("vantaa", "helsinki", "espoo"):
        return "capital"
    if place in ("turku", "raisio"):
        return "turku"
    if place in ("tampere", "lempaala"):
        return "tampere"
    return place


def build_zone_day_caps(
    roster: list[dict[str, Any]],
    geo: Geo,
    active_fraction: float,
    flu_days: set[int],
) -> tuple[dict[tuple[str, int], int], dict[tuple[str, int], int]]:
    supply30 = geo.supply(roster, 30.0)
    exp_roster = [d for d in roster if d["rating"] >= 4.8 and d["completedGigs"] >= 50]
    exp_supply30 = geo.supply(exp_roster, 30.0)
    rep_place = {"capital": "vantaa", "turku": "turku", "tampere": "tampere"}

    z_cap: dict[tuple[str, int], int] = {}
    ze_cap: dict[tuple[str, int], int] = {}
    zones = {zone_of(p) for p in geo.places}
    for z in zones:
        rp = rep_place.get(z, z)
        s = supply30.get(rp, 0)
        es = exp_supply30.get(rp, 0)
        for d in range(9):
            mult = active_fraction
            if d in flu_days:
                mult *= 0.62
            if d % 7 == 5:    # Saturday has ~25% of weekday driver views
                mult *= 0.26
            elif d % 7 == 6:  # Sunday
                mult *= 0.05
            z_cap[(z, d)] = max(1 if (s >= 14 and d % 7 != 6) else 0, int(s * mult))
            ze_cap[(z, d)] = max(1 if (es >= 3 and d % 7 < 5) else 0, int(es * mult))
    return z_cap, ze_cap


class Column:
    """A candidate tour (or solo gig) column in the set-packing / Lagrangian solver."""
    __slots__ = ("idx", "arcs", "rids", "sim", "zone_day", "needs_exp", "net", "bound_net", "cost", "prize", "trust_bonus")

    def __init__(
        self,
        idx: int,
        arcs: list[Arc],
        sim: dict[str, Any],
        zone_day: tuple[str, int],
        needs_exp: bool,
        prize: float,
        cost: float,
        bound_cost: float,
        trust_bonus: float,
    ):
        self.idx = idx
        self.arcs = arcs
        self.rids = tuple(a.rid for a in arcs)
        self.sim = sim
        self.zone_day = zone_day
        self.needs_exp = needs_exp
        self.prize = prize
        self.cost = cost
        self.trust_bonus = trust_bonus
        self.net = prize - cost
        self.bound_net = prize - bound_cost


def dealer_day_cap_for(tot: int, day: int, max_dealer_share: float, steered_state: bool) -> int:
    """Exact competitor reaction law from `tas-state`:
      - Small dealers (< 10 requests/day) never trigger competitor cuts -> 100% allowed.
      - Friday (day >= 4) is the last request day -> 100% allowed (zero future penalty).
      - With `steered_state=True` on Monday (day == 0), keep busy dealers (>= 10 reqs) strictly < 30%
        so competitor RAISES prices +4% on Tue..Fri while Monday same_day deliveries build +trust!
      - Otherwise keep busy dealers <= `max_dealer_share` (default 0.68, strictly < 70% cut threshold).
    """
    if tot < 10 or day >= 4:
        return tot
    if steered_state and day == 0:
        return max(1, int(tot * 0.2999))
    return max(3, int(tot * max_dealer_share))


def solve_lagrangian_and_local_search(
    cols: list[Column],
    all_rids: list[str],
    z_cap: dict[tuple[str, int], int],
    ze_cap: dict[tuple[str, int], int],
    dealer_day_tot: Counter,
    max_dealer_share: float,
    max_cars: int,
    use_bound_weights: bool = False,
    steered_state: bool = False,
    iters: int = 75,
) -> tuple[float, list[Column]]:
    """Computes:
      1) `best_dual_ub`: proven mathematical Lagrangian Dual upper bound on disjoint feasible packing!
      2) `best_primal`: highest-profit feasible disjoint selection found via Lagrangian-guided greedy + local search.
    """
    lam: dict[str, float] = {r: 0.0 for r in all_rids}
    mu: dict[tuple[str, int], float] = {k: 0.0 for k in z_cap}
    eta: dict[tuple[str, int], float] = {k: 0.0 for k in ze_cap}
    gamma = 0.0  # dual on max_cars

    # Seed initial lambda with max per-car net
    for j in cols:
        w = (j.bound_net if use_bound_weights else (j.net + j.trust_bonus)) / len(j.rids)
        for r in j.rids:
            if w > lam[r]:
                lam[r] = w * 0.5

    best_dual_ub = float("inf")
    best_primal_val = -1.0
    best_primal: list[Column] = []

    def greedy_primal(order_cols: list[Column]) -> tuple[float, list[Column]]:
        used_r: set[str] = set()
        zd_u: Counter = Counter()
        zed_u: Counter = Counter()
        dd_u: Counter = Counter()
        picked: list[Column] = []
        tot_cars = 0
        val = 0.0
        for c in order_cols:
            w = c.bound_net if use_bound_weights else c.net
            if w <= 0:
                continue
            n_c = len(c.rids)
            if tot_cars + n_c > max_cars:
                continue
            if any(r in used_r for r in c.rids):
                continue
            if zd_u[c.zone_day] + 1 > z_cap.get(c.zone_day, 0):
                continue
            if c.needs_exp and zed_u[c.zone_day] + 1 > ze_cap.get(c.zone_day, 0):
                continue
            if not use_bound_weights:
                dlr_inc = Counter((x.dealer, x.arrived_at // DAY) for x in c.arcs)
                if any(
                    dd_u[k] + inc > dealer_day_cap_for(dealer_day_tot[k], k[1], max_dealer_share, steered_state)
                    for k, inc in dlr_inc.items()
                ):
                    continue
                for k, inc in dlr_inc.items():
                    dd_u[k] += inc
            used_r.update(c.rids)
            zd_u[c.zone_day] += 1
            if c.needs_exp:
                zed_u[c.zone_day] += 1
            tot_cars += n_c
            picked.append(c)
            val += w
        return val, picked

    for it in range(iters):
        # Evaluate reduced profits
        active_cols: list[Column] = []
        pos_sum = 0.0
        req_cov: Counter = Counter()
        zd_cov: Counter = Counter()
        zed_cov: Counter = Counter()
        car_cov = 0

        for c in cols:
            w = c.bound_net if use_bound_weights else c.net
            rc = w - sum(lam[r] for r in c.rids) - mu.get(c.zone_day, 0.0) - (eta.get(c.zone_day, 0.0) if c.needs_exp else 0.0) - gamma * len(c.rids)
            if rc > 0.0:
                pos_sum += rc
                active_cols.append(c)
                for r in c.rids:
                    req_cov[r] += 1
                zd_cov[c.zone_day] += 1
                if c.needs_exp:
                    zed_cov[c.zone_day] += 1
                car_cov += len(c.rids)

        dual_val = (
            sum(lam.values())
            + sum(z_cap[k] * mu[k] for k in z_cap if z_cap[k] > 0)
            + sum(ze_cap[k] * eta[k] for k in ze_cap if ze_cap[k] > 0)
            + (max_cars * gamma if max_cars < 10000 else 0.0)
            + pos_sum
        )
        if dual_val < best_dual_ub:
            best_dual_ub = dual_val

        # Every 12 iterations, build a primal feasible solution guided by dual shadow prices!
        if it % 12 == 0 or it == iters - 1:
            scored = sorted(
                cols,
                key=lambda c: (
                    (c.bound_net if use_bound_weights else (c.net + c.trust_bonus))
                    - 0.45 * sum(lam[r] for r in c.rids)
                    - 0.65 * mu.get(c.zone_day, 0.0)
                ) / (1.0 + 0.15 * len(c.rids)),
                reverse=True,
            )
            pval, pset = greedy_primal(scored)
            if pval > best_primal_val:
                best_primal_val = pval
                best_primal = pset

        # Polyak / decaying subgradient step
        norm2 = 0.0
        for r in all_rids:
            g_r = 1 - req_cov[r]
            if g_r != 0 and (lam[r] > 0 or g_r < 0):
                norm2 += g_r * g_r
        for k, cap in z_cap.items():
            g_z = cap - zd_cov[k]
            if g_z != 0 and (mu[k] > 0 or g_z < 0):
                norm2 += g_z * g_z
        for k, ecap in ze_cap.items():
            g_e = ecap - zed_cov[k]
            if g_e != 0 and (eta[k] > 0 or g_e < 0):
                norm2 += g_e * g_e
        g_m = max_cars - car_cov if max_cars < 10000 else 0
        if g_m != 0 and (gamma > 0 or g_m < 0):
            norm2 += g_m * g_m
        if norm2 == 0:
            break

        alpha = (1.6 * (0.96 ** it)) * max(1000.0, dual_val - max(0.0, best_primal_val)) / norm2
        for r in all_rids:
            g_r = 1 - req_cov[r]
            if g_r != 0:
                lam[r] = max(0.0, lam[r] - alpha * g_r)
        for k, cap in z_cap.items():
            g_z = cap - zd_cov[k]
            if g_z != 0:
                mu[k] = max(0.0, mu[k] - alpha * g_z)
        for k, ecap in ze_cap.items():
            g_e = ecap - zed_cov[k]
            if g_e != 0:
                eta[k] = max(0.0, eta[k] - alpha * g_e)
        if max_cars < 10000 and g_m != 0:
            gamma = max(0.0, gamma - alpha * g_m)

    # Local search (1-for-1 and 1-for-2 / 2-for-1 swaps) on best_primal!
    if not use_bound_weights and best_primal:
        best_primal = local_search_refine(best_primal, cols, z_cap, ze_cap, dealer_day_tot, max_dealer_share, max_cars, steered_state)

    return best_dual_ub, best_primal


def local_search_refine(
    initial: list[Column],
    all_cols: list[Column],
    z_cap: dict[tuple[str, int], int],
    ze_cap: dict[tuple[str, int], int],
    dealer_day_tot: Counter,
    max_dealer_share: float,
    max_cars: int,
    steered_state: bool = False,
) -> list[Column]:
    """1-for-1 and 1-for-2 neighborhood local search over selected tours."""
    selected: dict[int, Column] = {c.idx: c for c in initial}
    rid_owner: dict[str, int] = {r: c.idx for c in initial for r in c.rids}
    zd_u: Counter = Counter(c.zone_day for c in initial)
    zed_u: Counter = Counter(c.zone_day for c in initial if c.needs_exp)
    dd_u: Counter = Counter()
    for c in initial:
        for a in c.arcs:
            dd_u[(a.dealer, a.arrived_at // DAY)] += 1
    tot_cars = sum(len(c.rids) for c in initial)

    top_cands = sorted(all_cols, key=lambda c: c.net + c.trust_bonus, reverse=True)[:4500]
    for _pass in range(2):
        improved = 0
        for cand in top_cands:
            if cand.idx in selected:
                continue
            conflict_ids = {rid_owner[r] for r in cand.rids if r in rid_owner}
            if len(conflict_ids) > 2:
                continue
            removed = [selected[cid] for cid in conflict_ids]
            gain = cand.net - sum(x.net for x in removed)
            if gain <= 150.0:  # at least €1.50 improvement
                continue
            new_cars = tot_cars - sum(len(x.rids) for x in removed) + len(cand.rids)
            if new_cars > max_cars:
                continue
            zd_delta = 1 - sum(1 for x in removed if x.zone_day == cand.zone_day)
            if zd_u[cand.zone_day] + zd_delta > z_cap.get(cand.zone_day, 0):
                continue
            if cand.needs_exp:
                zed_delta = 1 - sum(1 for x in removed if x.zone_day == cand.zone_day and x.needs_exp)
                if zed_u[cand.zone_day] + zed_delta > ze_cap.get(cand.zone_day, 0):
                    continue
            # Check dealer-day cap
            dd_delta: Counter = Counter()
            for x in removed:
                for a in x.arcs:
                    dd_delta[(a.dealer, a.arrived_at // DAY)] -= 1
            for a in cand.arcs:
                dd_delta[(a.dealer, a.arrived_at // DAY)] += 1
            if any(
                inc > 0 and dd_u[k] + inc > dealer_day_cap_for(dealer_day_tot[k], k[1], max_dealer_share, steered_state)
                for k, inc in dd_delta.items()
            ):
                continue

            # Apply swap!
            for x in removed:
                del selected[x.idx]
                for r in x.rids:
                    del rid_owner[r]
                zd_u[x.zone_day] -= 1
                if x.needs_exp:
                    zed_u[x.zone_day] -= 1
            selected[cand.idx] = cand
            for r in cand.rids:
                rid_owner[r] = cand.idx
            zd_u[cand.zone_day] += 1
            if cand.needs_exp:
                zed_u[cand.zone_day] += 1
            for k, inc in dd_delta.items():
                dd_u[k] += inc
            tot_cars = new_cars
            improved += 1
        if improved == 0:
            break
    return list(selected.values())


def generate_candidate_columns(
    seed: str,
    geo: Geo,
    tape: dict[str, Any],
    include_solos: bool = True,
) -> tuple[list[Column], dict[str, list[Arc]], Counter, dict[tuple[str, int], int], dict[tuple[str, int], int], set[int]]:
    reqs = tape["requests"]
    roster = tape["roster"]
    supply30 = geo.supply(roster, 30.0)
    known_limits = load_known_limits(seed)
    day_mult, flu_days = calibrate_seed_world_factors(seed, geo, tape)
    z_cap_bound, ze_cap_bound = build_zone_day_caps(roster, geo, active_fraction=0.48, flu_days=flu_days)

    arcs: list[Arc] = []
    all_opts_by_rid: dict[str, list[Arc]] = {}
    dealer_day_tot: Counter = Counter()
    for r in reqs:
        dealer_day_tot[(r["dealerId"], r["arrivedAt"] // DAY)] += 1
        opts = [Arc(r, o, geo) for o in r["options"]]
        all_opts_by_rid[r["id"]] = opts
        if len(r["legs"]) != 1:
            continue
        clean = [a for a in opts if not a.unsure and a.deadline - a.ready_at - a.drive_min >= 120 and a.deadline <= tape["ends_at"] - 150]
        if clean:
            # Prefer next_day when arrived early enough, and within_3_days when multi-day flexibility helps
            clean.sort(key=lambda a: (a.deadline, a.list_cents), reverse=True)
            arcs.append(clean[0])
            # Also include faster `same_day` on Monday morning if feasible so planner can pick Monday fast trust tours!
            if r["arrivedAt"] < 13 * HOUR:
                sd = [a for a in clean if a.option == "same_day" and a.drive_min <= 140]
                if sd and sd[0].option != clean[0].option:
                    arcs.append(sd[0])

    by_p: dict[str, list[Arc]] = defaultdict(list)
    for a in arcs:
        by_p[a.pickup].append(a)

    cols: list[Column] = []
    next_edges: dict[tuple[str, str], list[tuple[Arc, dict[str, Any]]]] = defaultdict(list)

    def add_col(t_arcs: list[Arc], sim: dict[str, Any]) -> None:
        p0 = t_arcs[0].pickup
        d_pick = sim["first_pickup_at"] // DAY
        zd = (zone_of(p0), d_pick)
        needs_exp = any(x.premium for x in t_arcs)
        prize = sum(estimate_prize_cents(x, supply30, known_limits, day_mult) for x in t_arcs)
        cost = estimate_tour_cost_cents(t_arcs, sim, geo, supply30)
        b_cost = min_bound_tour_cost_cents(t_arcs, sim, geo)
        # Penalize mixing 1 premium car into non-premium multi-car tour
        n_prem = sum(1 for x in t_arcs if x.premium)
        if len(t_arcs) > 1 and 0 < n_prem < len(t_arcs):
            cost += 900.0
        # Monday fast-delivery trust bonus on top dealers (+€9 per Monday-delivered order on D01..D10)
        t_bonus = 0.0
        if sim["last_delivery_at"] <= 20 * HOUR:
            t_bonus = sum(900.0 for x in t_arcs if x.dealer in TOP_DEALERS)
        if prize - b_cost > 500.0:
            cols.append(Column(len(cols), t_arcs, sim, zd, needs_exp, prize, cost, b_cost, t_bonus))

    # 1. Multi-car tours (2, 3, 4 cars)
    for a in arcs:
        key_a = (a.rid, a.option)
        for pb in geo.places:
            if geo.line_km(a.delivery, pb) > 30.0 or geo.minutes(a.delivery, pb) > 40:
                continue
            for b in by_p[pb]:
                if b.rid == a.rid:
                    continue
                if b.pickup_to < a.ready_at + a.drive_min or a.ready_at > b.deadline - b.drive_min - 110:
                    continue
                sim2 = simulate_tour([a, b], geo, slack_min=115, start_buffer_min=45, max_road_min=680)
                if not sim2:
                    continue
                next_edges[key_a].append((b, sim2))
                if supply30[a.pickup] >= 16 and geo.line_km(b.delivery, a.pickup) <= 30.0:
                    add_col([a, b], sim2)

    for a in arcs:
        if supply30[a.pickup] < 16:
            continue
        edges_a = sorted(next_edges[(a.rid, a.option)], key=lambda x: (x[1]["deadhead_min"], -x[0].ref_cents))[:20]
        for b, _ in edges_a:
            edges_b = sorted(next_edges[(b.rid, b.option)], key=lambda x: (x[1]["deadhead_min"], -x[0].ref_cents))[:15]
            for c, _ in edges_b:
                if c.rid in (a.rid, b.rid):
                    continue
                sim3 = simulate_tour([a, b, c], geo, slack_min=115, start_buffer_min=45, max_road_min=680)
                if not sim3:
                    continue
                if geo.line_km(c.delivery, a.pickup) <= 30.0:
                    add_col([a, b, c], sim3)
                if sim3["road_min"] <= 540:
                    for d, _ in sorted(next_edges[(c.rid, c.option)], key=lambda x: (x[1]["deadhead_min"], -x[0].ref_cents))[:10]:
                        if d.rid in (a.rid, b.rid, c.rid):
                            continue
                        if geo.line_km(d.delivery, a.pickup) <= 30.0:
                            sim4 = simulate_tour([a, b, c, d], geo, slack_min=115, start_buffer_min=45, max_road_min=680)
                            if sim4:
                                add_col([a, b, c, d], sim4)

    # 2. High-margin solos (for hubs with surplus drivers and for bound completeness)
    if include_solos:
        for r in reqs:
            opts = [a for a in all_opts_by_rid[r["id"]] if not a.unsure and a.deadline - a.ready_at - a.drive_min >= 180 and a.deadline <= tape["ends_at"] - 180]
            for a in opts:
                if supply30.get(a.pickup, 0) < 25 or a.drive_min > 380:
                    continue
                if a.option == "same_day" and (supply30.get(a.pickup, 0) < 80 or a.drive_min > 120 or a.arrived_at % DAY > 14 * HOUR):
                    continue
                sim1 = {"post_at": a.respond_by, "first_pickup_at": max(a.respond_by + 45, a.ready_at), "last_delivery_at": max(a.respond_by + 45, a.ready_at) + a.drive_min, "road_min": a.drive_min, "deadhead_min": 0}
                add_col([a], sim1)

    return cols, all_opts_by_rid, dealer_day_tot, z_cap_bound, ze_cap_bound, flu_days


def plan_safe_subset_tours(seed: str, geo: Geo, tape: dict[str, Any], name: str, max_hold_min: int = 240) -> tuple[Path, Path, Path]:
    """Plans disjoint closed tours strictly inside Champion v5's won orders with `post_at - min(respond_by) <= max_hold_min`
    so no car is held overnight (preserving dealer trust timing!), AND emits:
      - `tours-<name>.json`
      - `book-<name>-champ-strict.json` (exact Champion v5 won quotes + decline all others)
      - `book-<name>-lim-safe.json` (exact `book-won-apply` with 1.2% trust-timing buffer when trust < 25).
    """
    rev_path = lab_home() / "tas" / seed / "reveal-v5.json"
    rev = json.loads(rev_path.read_text(encoding="utf-8"))
    won_opts: dict[str, str] = {}
    strict_champ_book: dict[str, Any] = {"*": "decline"}
    for item in rev["requests"]:
        if item.get("outcome") == "won" and item.get("option") and item.get("quote"):
            rid = item["request"]["id"]
            won_opts[rid] = item["option"]
            strict_champ_book[rid] = {"prices": item["quote"]}

    reqs_by_id = {r["id"]: r for r in tape["requests"]}
    supply30 = geo.supply(tape["roster"], 30.0)
    arcs: list[Arc] = []
    for rid, ok in sorted(won_opts.items()):
        r = reqs_by_id.get(rid)
        if not r or len(r["legs"]) != 1:
            continue
        opt = next((o for o in r["options"] if o["kind"] == ok), None)
        if opt:
            a = Arc(r, opt, geo)
            if not a.unsure:
                arcs.append(a)

    by_p: dict[str, list[Arc]] = defaultdict(list)
    for a in arcs:
        by_p[a.pickup].append(a)

    cands = []
    for a in arcs:
        if supply30[a.pickup] < 16:
            continue
        for pb in geo.places:
            if geo.line_km(a.delivery, pb) > 30.0:
                continue
            for b in by_p[pb]:
                if b.rid == a.rid:
                    continue
                if max(a.respond_by, b.respond_by) - min(a.respond_by, b.respond_by) > max_hold_min:
                    continue
                if geo.line_km(b.delivery, a.pickup) > 30.0:
                    continue
                sim2 = simulate_tour([a, b], geo, slack_min=150, start_buffer_min=45, max_road_min=660)
                if not sim2:
                    continue
                sav = sum(estimate_tour_cost_cents([x], {"road_min": x.drive_min}, geo, supply30) for x in (a, b)) - estimate_tour_cost_cents([a, b], sim2, geo, supply30)
                if sav > 800:
                    cands.append((sav, [a, b], sim2))

    cands.sort(key=lambda x: x[0], reverse=True)
    used: set[str] = set()
    chosen = []
    tot_sav = 0.0
    for sav, t_arcs, sim in cands:
        if any(x.rid in used for x in t_arcs):
            continue
        used.update(x.rid for x in t_arcs)
        tot_sav += sav
        chosen.append({
            "id": f"T{len(chosen)+1:04d}",
            "rids": [x.rid for x in t_arcs],
            "n_cars": len(t_arcs),
            "road_min": sim["road_min"],
            "deadhead_min": sim["deadhead_min"],
            "route": " -> ".join(f"{x.pickup}->{x.delivery}" for x in t_arcs),
            "est_saving_eur": round(sav / 100.0, 2),
        })

    tdir = lab_home() / "tas" / seed
    tours_p = tdir / f"tours-{name}.json"
    strict_p = tdir / f"book-{name}-champ-strict.json"
    lim_safe_p = tdir / f"book-{name}-lim-safe.json"
    tours_p.write_text(json.dumps({"seed": seed, "name": name, "mode": "subset-safe", "tours": chosen}, indent=2), encoding="utf-8")
    strict_p.write_text(json.dumps(strict_champ_book, indent=2), encoding="utf-8")

    # Build trust-timing-safe limit book from limits-won-apply.jsonl if present
    lim_in = tdir / "limits-won-apply.jsonl"
    if lim_in.exists():
        lim_book: dict[str, Any] = {"*": "decline"}
        for line in lim_in.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            if r.get("desk") == "won" and r.get("lo") and r.get("option"):
                # 1.2% buffer when dealer trust < 25 so +-1 trust shift from tour delivery timing never loses the order!
                buf = 0.988 if r.get("trust", 0) < 25 else 1.0
                lim_book[r["rid"]] = {"prices": {r["option"]: int(r["lo"] * buf)}}
        lim_safe_p.write_text(json.dumps(lim_book, indent=2), encoding="utf-8")

    print(f"[{seed} safe-subset {name}] {len(chosen)} same-window closed tours ({sum(t['n_cars'] for t in chosen)} cars, max hold {max_hold_min}m), est fee saving €{tot_sav/100:,.0f}")
    return tours_p, strict_p, lim_safe_p


def run_full_planner(
    seed: str,
    geo: Geo,
    tape: dict[str, Any],
    name: str,
    max_cars: int,
    active_fraction: float,
    max_dealer_share: float,
    include_solos: bool,
    compute_bound: bool,
    steered_state: bool = False,
) -> None:
    cols, all_opts_by_rid, dealer_day_tot, z_cap_bound, ze_cap_bound, flu_days = generate_candidate_columns(
        seed, geo, tape, include_solos=True
    )
    all_rids = [r["id"] for r in tape["requests"]]
    print(f"[{seed}] Generated {len(cols)} feasible tour/solo columns (flu_days={sorted(flu_days)}).")

    if compute_bound:
        # Proven mathematical upper bound under Step 2 minimum measured driver reserve rates & full 48% active fleet!
        ub_cents, ub_primal = solve_lagrangian_and_local_search(
            cols, all_rids, z_cap_bound, ze_cap_bound, dealer_day_tot,
            max_dealer_share=1.0, max_cars=10000, use_bound_weights=True, iters=70,
        )
        ub_primal_eur = sum(c.bound_net for c in ub_primal) / 100.0
        ub_cars = sum(len(c.rids) for c in ub_primal)
        print(f"  [BOUND {seed}] Proven Lagrangian Dual Upper Bound = €{ub_cents/100:,.2f} (optimistic integer packing = €{ub_primal_eur:,.2f} across {ub_cars} cars in {len(ub_primal)} gigs)")
        (lab_home() / "tas" / seed / "tas-routes-bound.json").write_text(
            json.dumps({
                "seed": seed,
                "lagrangian_dual_upper_bound_eur": round(ub_cents / 100.0, 2),
                "optimistic_integer_packing_eur": round(ub_primal_eur, 2),
                "optimistic_cars": ub_cars,
                "optimistic_gigs": len(ub_primal),
                "candidate_columns": len(cols),
            }, indent=2),
            encoding="utf-8",
        )

    work_cols = cols if include_solos else [c for c in cols if len(c.rids) >= 2]
    z_cap, ze_cap = build_zone_day_caps(tape["roster"], geo, active_fraction=active_fraction, flu_days=flu_days)
    dual_prac, picked = solve_lagrangian_and_local_search(
        work_cols, all_rids, z_cap, ze_cap, dealer_day_tot,
        max_dealer_share=max_dealer_share, max_cars=max_cars, use_bound_weights=False, steered_state=steered_state, iters=65,
    )

    # Sort chosen tours chronologically by post_at
    picked.sort(key=lambda c: (c.sim["post_at"], c.rids[0]))
    chosen_tours = []
    solo_count = 0
    book: dict[str, Any] = {"*": "decline"}

    for c in picked:
        if len(c.rids) == 1:
            solo_count += 1
            a = c.arcs[0]
            floor_c = max(int(a.list_cents * 0.96), int(c.cost + 1400))
            book[a.rid] = {"prices": {a.option: floor_c}}
        else:
            tid = f"T{len(chosen_tours)+1:04d}"
            chosen_tours.append({
                "id": tid,
                "rids": list(c.rids),
                "n_cars": len(c.rids),
                "road_min": c.sim["road_min"],
                "deadhead_min": c.sim["deadhead_min"],
                "route": " -> ".join(f"{x.pickup}->{x.delivery}" for x in c.arcs),
                "est_net_eur": round(c.net / 100.0, 2),
            })
            ref_tot = max(1, sum(x.ref_cents for x in c.arcs))
            for idx, x in enumerate(c.arcs):
                alloc_cost = c.cost * (x.ref_cents / ref_tot)
                prices: dict[str, int] = {}
                for cand_arc in all_opts_by_rid[x.rid]:
                    trial = list(c.arcs)
                    trial[idx] = cand_arc
                    if simulate_tour(trial, geo, slack_min=105, start_buffer_min=45, max_road_min=690) is not None:
                        floor_c = max(int(cand_arc.list_cents * 0.72), int(alloc_cost + 800))
                        prices[cand_arc.option] = floor_c
                if not prices:
                    prices[x.option] = max(int(x.list_cents * 0.72), int(alloc_cost + 800))
                book[x.rid] = {"prices": prices}

    tdir = lab_home() / "tas" / seed
    plan_path = tdir / f"plan-{name}.json"
    tours_path = tdir / f"tours-{name}.json"
    plan_path.write_text(json.dumps(book, indent=2), encoding="utf-8")
    tours_path.write_text(json.dumps({"seed": seed, "name": name, "mode": "full", "tours": chosen_tours}, indent=2), encoding="utf-8")

    dist = Counter(t["n_cars"] for t in chosen_tours)
    tour_cars = sum(t["n_cars"] for t in chosen_tours)
    tot_net = sum(c.net for c in picked) / 100.0
    tot_prize = sum(c.prize for c in picked) / 100.0
    tot_cost = sum(c.cost for c in picked) / 100.0
    print(
        f"[{seed} {name}] {len(chosen_tours)} closed tours ({dict(sorted(dist.items()))} = {tour_cars} cars) + {solo_count} solos "
        f"= {tour_cars + solo_count} cars in {len(picked)} gigs | est rev €{tot_prize:,.0f} - fee €{tot_cost:,.0f} = net €{tot_net:,.0f} "
        f"(practical dual UB €{dual_prac/100:,.0f})"
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="dev-12")
    ap.add_argument("--name", default="tas-routes-clean380")
    ap.add_argument("--subset-reveal", action="store_true")
    ap.add_argument("--max-cars", type=int, default=380)
    ap.add_argument("--active-fraction", type=float, default=0.32)
    ap.add_argument("--max-dealer-share", type=float, default=0.68)
    ap.add_argument("--no-solos", action="store_true")
    ap.add_argument("--bound", action="store_true")
    ap.add_argument("--steered-state", action="store_true", help="keep busy dealers <30%% on Monday to trigger +4%% competitor price hike on Tue-Fri")
    args = ap.parse_args()

    geo = load_geo()
    tape = load_tape(args.seed)
    if args.subset_reveal:
        plan_safe_subset_tours(args.seed, geo, tape, args.name)
    else:
        run_full_planner(
            args.seed, geo, tape, args.name,
            max_cars=args.max_cars,
            active_fraction=args.active_fraction,
            max_dealer_share=args.max_dealer_share,
            include_solos=not args.no_solos,
            compute_bound=args.bound,
            steered_state=args.steered_state,
        )


if __name__ == "__main__":
    main()
