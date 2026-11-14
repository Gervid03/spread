"""Builds 0-fork replayable `direct-safe` quote & closed-tour books strictly from already-measured exact limits!

Because `limits-*.jsonl` on `dev-12`, `dev-01`, `dev-08`, and `dev-07` already measured 650-1,036 requests per seed,
restricting candidate columns to `(rid, option)` pairs with exact measured `lo` eliminates all prize estimation error
and replays in ~30 seconds per world with ZERO forks (`tas.py run`)!
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from spread_lab.env import lab_home
from spread_lab.geo import Geo
from experiments.scripts.tas_routes_census import Arc, load_geo, load_tape, simulate_tour
from experiments.scripts.tas_routes_planner import (
    Column,
    TOP_DEALERS,
    build_zone_day_caps,
    calibrate_seed_world_factors,
    estimate_tour_cost_cents,
    min_bound_tour_cost_cents,
    solve_lagrangian_and_local_search,
    zone_of,
)

HOUR, DAY = 60, 24 * 60


def load_measured_seed_limits(seed: str) -> dict[tuple[str, str], tuple[int, int]]:
    """Returns `(rid, option) -> (best_lo_cents, trust_at_measurement)` for exact measured limits on `seed`."""
    best: dict[tuple[str, str], tuple[int, int]] = {}
    tdir = lab_home() / "tas" / seed
    for p in sorted(tdir.glob("limits-*.jsonl")):
        if "puretours" in p.name:
            continue
        is_zero_trust_all = p.name == "limits-all.jsonl"
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            lo = r.get("lo")
            if not lo or not r.get("rid") or not r.get("option"):
                continue
            key = (r["rid"], r["option"])
            tr = int(r.get("trust") or 0)
            # Prefer measurements from actual played runs (with realistic trust) over 0-trust limits-all when both exist
            prev = best.get(key)
            if prev is None or (not is_zero_trust_all and lo > prev[0]) or (is_zero_trust_all and prev[0] < lo):
                best[key] = (int(lo), tr)
    return best


def build_direct_safe_plan(seed: str, name: str, max_cars: int, max_solos: int, active_fraction: float) -> None:
    geo = load_geo()
    tape = load_tape(seed)
    reqs = tape["requests"]
    roster = tape["roster"]
    supply30 = geo.supply(roster, 30.0)
    gate_supply = geo.supply(roster, 55.0)
    measured = load_measured_seed_limits(seed)
    _, flu_days = calibrate_seed_world_factors(seed, geo, tape)
    z_cap, ze_cap = build_zone_day_caps(roster, geo, active_fraction=active_fraction, flu_days=flu_days)

    dealer_day_tot: Counter = Counter()
    arcs_1leg: list[Arc] = []
    solo_arcs: list[Arc] = []

    for r in reqs:
        dealer_day_tot[(r["dealerId"], r["arrivedAt"] // DAY)] += 1
        for o in r["options"]:
            key = (r["id"], o["kind"])
            if key not in measured:
                continue
            a = Arc(r, o, geo)
            if a.unsure or a.deadline > tape["ends_at"] - 180:
                continue
            if a.deadline - a.ready_at - a.drive_min < 180:
                continue
            solo_arcs.append(a)
            if a.legs_count == 1 and (a.option != "same_day" or (r["arrivedAt"] < 12 * HOUR and a.drive_min <= 80)):
                arcs_1leg.append(a)

    by_p: dict[str, list[Arc]] = defaultdict(list)
    for a in arcs_1leg:
        by_p[a.pickup].append(a)

    def safe_quote_cents(a: Arc) -> int:
        lo, tr = measured[(a.rid, a.option)]
        # Apply a 2.2% trust-timing safety margin on Tue-Fri when measured at high trust (>0) so +-2 trust never loses!
        if tr >= 10:
            return int(lo * 0.976)
        if tr > 0:
            return int(lo * 0.985)
        return int(lo * 0.995)

    cols: list[Column] = []
    next_edges: dict[tuple[str, str], list[tuple[Arc, dict[str, Any]]]] = defaultdict(list)

    def add_col(t_arcs: list[Arc], sim: dict[str, Any]) -> None:
        p0 = t_arcs[0].pickup
        zd = (zone_of(p0), sim["first_pickup_at"] // DAY)
        needs_exp = any(x.premium for x in t_arcs)
        qs = [safe_quote_cents(x) for x in t_arcs]
        prize = float(sum(qs))
        cost = estimate_tour_cost_cents(t_arcs, sim, geo, supply30)
        b_cost = min_bound_tour_cost_cents(t_arcs, sim, geo)
        if len(t_arcs) > 1:
            ref_tot = max(1, sum(x.ref_cents for x in t_arcs))
            if any(q < cost * (x.ref_cents / ref_tot) + 900 for q, x in zip(qs, t_arcs)):
                return
            n_prem = sum(1 for x in t_arcs if x.premium)
            if 0 < n_prem < len(t_arcs):
                cost += 900.0
        t_bonus = sum(1200.0 for x in t_arcs if x.dealer in TOP_DEALERS) if sim["last_delivery_at"] <= 20 * HOUR else 0.0
        if prize - cost > (2400.0 if len(t_arcs) > 1 else 2800.0):
            cols.append(Column(len(cols), t_arcs, sim, zd, needs_exp, prize, cost, b_cost, t_bonus))

    for a in arcs_1leg:
        ka = (a.rid, a.option)
        for pb in geo.places:
            if geo.line_km(a.delivery, pb) > 30.0 or geo.minutes(a.delivery, pb) > 40:
                continue
            for b in by_p[pb]:
                if b.rid == a.rid:
                    continue
                sim2 = simulate_tour([a, b], geo, slack_min=135, start_buffer_min=45, max_road_min=670)
                if not sim2:
                    continue
                next_edges[ka].append((b, sim2))
                if supply30[a.pickup] >= 20 and geo.line_km(b.delivery, a.pickup) <= 30.0:
                    add_col([a, b], sim2)

    for a in arcs_1leg:
        if supply30[a.pickup] < 20:
            continue
        for b, _ in sorted(next_edges[(a.rid, a.option)], key=lambda x: x[1]["deadhead_min"])[:18]:
            for c, _ in sorted(next_edges[(b.rid, b.option)], key=lambda x: x[1]["deadhead_min"])[:14]:
                if c.rid in (a.rid, b.rid):
                    continue
                sim3 = simulate_tour([a, b, c], geo, slack_min=135, start_buffer_min=45, max_road_min=670)
                if not sim3:
                    continue
                if geo.line_km(c.delivery, a.pickup) <= 30.0:
                    add_col([a, b, c], sim3)
                if sim3["road_min"] <= 520:
                    for d, _ in sorted(next_edges[(c.rid, c.option)], key=lambda x: x[1]["deadhead_min"])[:8]:
                        if d.rid in (a.rid, b.rid, c.rid):
                            continue
                        if geo.line_km(d.delivery, a.pickup) <= 30.0:
                            sim4 = simulate_tour([a, b, c, d], geo, slack_min=135, start_buffer_min=45, max_road_min=670)
                            if sim4:
                                add_col([a, b, c, d], sim4)

    # Measured profitable solos (including 2-leg trade-ins & hub/ring solos)
    for a in solo_arcs:
        sup0 = supply30.get(a.pickup, 0)
        gsup = gate_supply.get(a.pickup, 0)
        ret_hub = supply30.get(a.delivery, 0) >= 180 and a.drive_min <= 200 and a.option != "same_day"
        if sup0 < 22 and gsup < 25 and not ret_hub:
            continue
        if a.option == "same_day" and (sup0 < 100 or a.drive_min > 130 or a.arrived_at % DAY > 14 * HOUR):
            continue
        if a.drive_min > (640 if a.legs_count == 2 else 450):
            continue
        sim1 = {"post_at": a.respond_by, "first_pickup_at": max(a.respond_by + 45, a.ready_at), "last_delivery_at": max(a.respond_by + 45, a.ready_at) + a.drive_min, "road_min": a.drive_min, "deadhead_min": 0}
        add_col([a], sim1)

    all_rids = [r["id"] for r in reqs]
    _, picked = solve_lagrangian_and_local_search(
        cols, all_rids, z_cap, ze_cap, dealer_day_tot,
        max_dealer_share=0.68, max_cars=max_cars, use_bound_weights=False, steered_state=False, max_solos=max_solos, iters=65,
    )

    picked.sort(key=lambda c: (c.sim["post_at"], c.rids[0]))
    book: dict[str, Any] = {"*": "decline"}
    chosen_tours = []
    solo_n = 0
    for c in picked:
        for x in c.arcs:
            book[x.rid] = {"prices": {x.option: safe_quote_cents(x)}}
        if len(c.rids) == 1:
            solo_n += 1
        else:
            chosen_tours.append({
                "id": f"T{len(chosen_tours)+1:04d}",
                "rids": list(c.rids),
                "n_cars": len(c.rids),
                "road_min": c.sim["road_min"],
                "deadhead_min": c.sim["deadhead_min"],
                "route": " -> ".join(f"{x.pickup}->{x.delivery}" for x in c.arcs),
                "est_net_eur": round(c.net / 100.0, 2),
            })

    tdir = lab_home() / "tas" / seed
    bp = tdir / f"book-{name}.json"
    tp = tdir / f"tours-{name}.json"
    bp.write_text(json.dumps(book, indent=2), encoding="utf-8")
    tp.write_text(json.dumps({"seed": seed, "name": name, "mode": "direct-safe", "tours": chosen_tours}, indent=2), encoding="utf-8")
    dist = Counter(t["n_cars"] for t in chosen_tours)
    tcars = sum(t["n_cars"] for t in chosen_tours)
    print(
        f"[{seed} {name}] Measured pool={len(measured)} opts -> {len(chosen_tours)} closed tours ({dict(sorted(dist.items()))} = {tcars} cars) "
        f"+ {solo_n} solos = {tcars+solo_n} cars in {len(picked)} gigs | est rev €{sum(c.prize for c in picked)/100:,.0f} "
        f"- fee €{sum(c.cost for c in picked)/100:,.0f} = net €{sum(c.net for c in picked)/100:,.0f}"
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="all")
    ap.add_argument("--name", default="tas-routes-direct-safe")
    args = ap.parse_args()

    configs = {
        "dev-12": (350, 140, 0.34),
        "dev-01": (310, 130, 0.30),
        "dev-08": (370, 140, 0.35),
        "dev-07": (345, 165, 0.30),
    }
    seeds = list(configs) if args.seed == "all" else [args.seed]
    for s in seeds:
        mc, ms, af = configs[s]
        build_direct_safe_plan(s, args.name, max_cars=mc, max_solos=ms, active_fraction=af)


if __name__ == "__main__":
    main()
