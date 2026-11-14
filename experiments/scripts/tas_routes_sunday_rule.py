"""Step 5: The Rule for Sunday — Cross-World Return Arrival Law & Forkless Tour Opportunity Sizer.

Analyzes all four TAS tapes (`dev-12`, `dev-01`, `dev-08`, `dev-07` = 4,142 requests) with zero forks:
  1) Zone-to-zone return probability `P(B' -> A' arrives within H hours | A -> B won at hour h)`
     and worst-across-4-worlds probability `min_seed P(...)` ("almost the same in every world").
  2) Expected driver-fee saving per closed pair `(solo_A + solo_B - closed_AB)` by corridor.
  3) How many thin-town requests (`supply30 < 22`, currently DECLINED by Champion v5!) arrive AFTER
     an unbooked outbound hub car `Hub -> Thin` is ALREADY sitting in hand (0 foresight needed!),
     vs how many require holding `Hub -> Thin` for `H <= 4h` waiting for `Thin -> Hub`!
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict

from experiments.scripts.tas_routes_census import Arc, TAS_SEEDS, load_geo, load_tape, simulate_tour

HOUR, DAY = 60, 24 * 60


def cluster_of(p: str) -> str:
    if p in ("vantaa", "helsinki", "espoo"):
        return "Capital"
    if p in ("turku", "raisio", "salo"):
        return "Turku/SW"
    if p in ("tampere", "lempaala"):
        return "Tampere"
    return p


def main() -> None:
    geo = load_geo()
    tapes = {s: load_tape(s) for s in TAS_SEEDS}

    # 1. Zone-corridor return probabilities across all 4 worlds (and worst-world min!)
    corridor_tot: Counter = Counter()
    corridor_seed_tot: dict[tuple[str, str], Counter] = defaultdict(Counter)
    corridor_seed_ret4h: dict[tuple[str, str], Counter] = defaultdict(Counter)
    corridor_ret2h: Counter = Counter()
    corridor_ret4h: Counter = Counter()
    corridor_ret18h: Counter = Counter()  # includes overnight next-morning match!
    corridor_saving_eur: defaultdict[tuple[str, str], list[float]] = defaultdict(list)

    # 2. Forkless live-desk simulation:
    #    Mode A ("Reactive Hitch"): only pair B'->A' when A->B ALREADY arrived in the past 4 hours!
    #    Mode B ("Anticipatory Hold"): ALSO quote thin B'->A' first OR hold Hub->B up to 4h on high-p corridors!
    reactive_pairs_per_seed: Counter = Counter()
    reactive_thin_rescues_per_seed: Counter = Counter()

    for seed, tape in tapes.items():
        reqs = tape["requests"]
        supply30 = geo.supply(tape["roster"], 30.0)
        arcs = []
        for r in reqs:
            if len(r["legs"]) != 1:
                continue
            opts = [Arc(r, o, geo) for o in r["options"] if not Arc(r, o, geo).unsure]
            opts = [a for a in opts if a.deadline - a.ready_at - a.drive_min >= 110]
            if opts:
                opts.sort(key=lambda a: (a.deadline, a.list_cents), reverse=True)
                arcs.append(opts[0])

        for i, a in enumerate(arcs):
            if a.pickup not in ("vantaa", "helsinki", "espoo", "turku", "raisio", "tampere", "oulu", "lahti"):
                continue
            ca, cb = cluster_of(a.pickup), cluster_of(a.delivery)
            if ca == cb:
                continue
            corridor_tot[(ca, cb)] += 1
            corridor_seed_tot[(ca, cb)][seed] += 1

            f2 = f4 = f18 = False
            best_sav = None
            for b in arcs:
                dt = b.arrived_at - a.arrived_at
                if dt < 0 or dt > 18 * HOUR or b.rid == a.rid:
                    continue
                if geo.line_km(a.delivery, b.pickup) <= 30.0 and geo.line_km(b.delivery, a.pickup) <= 30.0:
                    sim = simulate_tour([a, b], geo, slack_min=105, start_buffer_min=45, max_road_min=690)
                    if sim is None:
                        continue
                    f18 = True
                    if dt <= 4 * HOUR:
                        f4 = True
                    if dt <= 2 * HOUR:
                        f2 = True
                    road_h = sim["road_min"] / 60.0
                    ref_sum = (a.ref_cents + b.ref_cents) / 100.0
                    closed_fee = max(0.56 * ref_sum, 14.0 * road_h + 13.0)
                    sav = 0.94 * ref_sum - closed_fee
                    if best_sav is None or sav > best_sav:
                        best_sav = sav
                    if f2:
                        break
            if f2:
                corridor_ret2h[(ca, cb)] += 1
            if f4:
                corridor_ret4h[(ca, cb)] += 1
                corridor_seed_ret4h[(ca, cb)][seed] += 1
            if f18:
                corridor_ret18h[(ca, cb)] += 1
            if best_sav is not None:
                corridor_saving_eur[(ca, cb)].append(best_sav)

        # Count disjoint reactive pairs (outbound A->B arrived 0..4h BEFORE return B'->A', zero future knowledge!)
        used = set()
        for idx, b in enumerate(arcs):
            if b.rid in used:
                continue
            # Look strictly BACKWARD 0..240 min for an unused hub outbound `a` that `b` closes!
            for j in range(idx - 1, -1, -1):
                a = arcs[j]
                if b.arrived_at - a.arrived_at > 4 * HOUR:
                    break
                if a.rid in used or supply30[a.pickup] < 25:
                    continue
                if geo.line_km(a.delivery, b.pickup) <= 30.0 and geo.line_km(b.delivery, a.pickup) <= 30.0:
                    if simulate_tour([a, b], geo, slack_min=110, start_buffer_min=45, max_road_min=680) is not None:
                        used.add(a.rid)
                        used.add(b.rid)
                        reactive_pairs_per_seed[seed] += 1
                        if supply30[b.pickup] < 22:
                            reactive_thin_rescues_per_seed[seed] += 1
                        break

    print("=== STEP 5: CROSS-WORLD CORRIDOR RETURN TABLE (4 worlds, feasible closed tour check) ===")
    print(f"{'Outbound Corridor':<26} {'N/wk':>5} {'P(<=2h)':>8} {'P(<=4h)':>8} {'MinSeed4h':>10} {'P(<=18h)':>9} {'AvgFeeSave':>11}")
    for (ca, cb), n in corridor_tot.most_common(22):
        if n < 8:
            continue
        p2 = corridor_ret2h[(ca, cb)] / n
        p4 = corridor_ret4h[(ca, cb)] / n
        p18 = corridor_ret18h[(ca, cb)] / n
        min_s = min(
            corridor_seed_ret4h[(ca, cb)][s] / max(1, corridor_seed_tot[(ca, cb)][s])
            for s in TAS_SEEDS if corridor_seed_tot[(ca, cb)][s] > 0
        )
        savs = corridor_saving_eur[(ca, cb)]
        avg_s = sum(savs) / max(1, len(savs))
        print(f"{ca + ' -> ' + cb:<26} {n/4:>5.1f} {p2:>7.0%} {p4:>7.0%} {min_s:>9.0%} {p18:>8.0%} {'€'+f'{avg_s:.1f}':>11}")

    print("=== FORKLESS REACTIVE CLOSED PAIRS (strictly causal: A->B already in hand <=4h before B'->A'!) ===")
    for s in TAS_SEEDS:
        print(f"  {s}: {reactive_pairs_per_seed[s]} disjoint causal closed pairs/wk ({reactive_thin_rescues_per_seed[s]} rescue a thin <22-driver pickup declined by v5!)")


if __name__ == "__main__":
    main()
