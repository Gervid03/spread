"""Analyze Thursday-start (`arrivedAt >= 4320`, Thu 00:00 -> Wed+ 22:00) tour census & causal pairs across the 4 TAS seeds.

Motivated by LEDGER.md's finding that the 14:00 test final started at Thu 00:00 with Mon-Wed pre-played as 0% win share.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from experiments.scripts.tas_routes_census import Arc, TAS_SEEDS, load_geo, load_tape, simulate_tour

HOUR, DAY = 60, 24 * 60


def main() -> None:
    geo = load_geo()
    print("=== THURSDAY-START (Thu 00:00 .. Fri 23:59, arrivedAt >= 4320) TOUR CENSUS ===")
    for seed in TAS_SEEDS:
        tape = load_tape(seed)
        supply30 = geo.supply(tape["roster"], 30.0)
        reqs = [r for r in tape["requests"] if r["arrivedAt"] >= 3 * DAY]
        arcs: list[Arc] = []
        for r in reqs:
            if len(r["legs"]) != 1:
                continue
            opts = [Arc(r, o, geo) for o in r["options"]]
            clean = [a for a in opts if not a.unsure and a.deadline - a.ready_at - a.drive_min >= 115 and a.deadline <= tape["ends_at"] - 120]
            if clean:
                clean.sort(key=lambda a: (a.deadline, a.list_cents), reverse=True)
                arcs.append(clean[0])

        by_p: dict[str, list[Arc]] = defaultdict(list)
        for a in arcs:
            by_p[a.pickup].append(a)

        cands = []
        next_e = defaultdict(list)
        for a in arcs:
            for pb in geo.places:
                if geo.line_km(a.delivery, pb) > 30.0:
                    continue
                for b in by_p[pb]:
                    if b.rid == a.rid:
                        continue
                    sim2 = simulate_tour([a, b], geo, slack_min=110, start_buffer_min=45, max_road_min=680)
                    if not sim2:
                        continue
                    next_e[a.rid].append((b, sim2))
                    if supply30[a.pickup] >= 18 and geo.line_km(b.delivery, a.pickup) <= 30.0:
                        ref_s = (a.ref_cents + b.ref_cents) / 100.0
                        lst_s = (a.list_cents + b.list_cents) / 100.0
                        net = lst_s * 1.56 - max(0.56 * ref_s, 14.0 * sim2["road_min"] / 60.0 + 13.0)
                        if net > 30:
                            cands.append((net / 2, net, [a, b], sim2))

        for a in arcs:
            if supply30[a.pickup] < 18:
                continue
            for b, _ in sorted(next_e[a.rid], key=lambda x: x[1]["deadhead_min"])[:16]:
                for c, _ in sorted(next_e[b.rid], key=lambda x: x[1]["deadhead_min"])[:12]:
                    if c.rid in (a.rid, b.rid):
                        continue
                    if geo.line_km(c.delivery, a.pickup) <= 30.0:
                        sim3 = simulate_tour([a, b, c], geo, slack_min=110, start_buffer_min=45, max_road_min=680)
                        if sim3:
                            ref_s = (a.ref_cents + b.ref_cents + c.ref_cents) / 100.0
                            lst_s = (a.list_cents + b.list_cents + c.list_cents) / 100.0
                            net = lst_s * 1.56 - max(0.50 * ref_s, 14.0 * sim3["road_min"] / 60.0 + 19.5)
                            if net > 50:
                                cands.append((net / 3, net, [a, b, c], sim3))

        cands.sort(key=lambda x: x[0], reverse=True)
        used = set()
        packed = []
        for _, net, t_arcs, sim in cands:
            if any(x.rid in used for x in t_arcs):
                continue
            used.update(x.rid for x in t_arcs)
            packed.append((net, t_arcs, sim))

        dist = Counter(len(t[1]) for t in packed)
        thin_rescued = sum(1 for _, t_arcs, _ in packed for x in t_arcs if supply30[x.pickup] < 22)
        print(
            f"  {seed}: Thu-Fri reqs={len(reqs)} | disjoint closed tours={len(packed)} ({dict(sorted(dist.items()))}) "
            f"covering {len(used)}/{len(reqs)} ({len(used)/len(reqs):.1%}) cars ({thin_rescued} thin <22 rescues), "
            f"est tour net margin €{sum(t[0] for t in packed):,.0f}"
        )


if __name__ == "__main__":
    main()
