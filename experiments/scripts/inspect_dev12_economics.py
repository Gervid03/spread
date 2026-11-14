"""Inspect referenceFeeCents, listPriceCents, road_min, and Monday/Tuesday tour candidates on dev-12."""
from __future__ import annotations

import json
from collections import Counter, defaultdict

from spread_lab.env import lab_home
from spread_lab.geo import Geo
from experiments.scripts.tas_routes_census import Arc, load_geo, load_tape, simulate_tour

DAY = 24 * 60


def main() -> None:
    geo = load_geo()
    tape = load_tape("dev-12")
    reqs = tape["requests"]
    roster = tape["roster"]
    supply30 = geo.supply(roster, 30.0)
    homes = Counter(d["homePlaceId"] for d in roster)

    # 1. Understand referenceFeeCents vs road_min and road_km on single-car requests
    buckets = defaultdict(list)
    for r in reqs:
        if len(r["legs"]) != 1:
            continue
        p = r["legs"][0]["pickup"]["placeId"]
        d = r["legs"][0]["delivery"]["placeId"]
        dm = geo.minutes(p, d)
        rk = geo.road_km(p, d)
        ref = r["referenceFeeCents"] / 100.0
        lst = max(o["listPriceCents"] for o in r["options"]) / 100.0
        b = (dm // 60) * 60
        buckets[b].append((dm, rk, ref, lst, ref / (dm / 60.0), lst / ref))

    print("=== SINGLE-CAR ECONOMICS BY DRIVE DURATION (dev-12) ===")
    print(f"{'Drive bin':<12} {'N':>5} {'Avg min':>8} {'Avg km':>8} {'Avg ref€':>9} {'Avg list€':>10} {'Ref €/h':>9} {'List/Ref':>9}")
    for b in sorted(buckets):
        rows = buckets[b]
        n = len(rows)
        print(
            f"{f'{b}-{b+59}m':<12} {n:>5} "
            f"{sum(x[0] for x in rows)/n:>8.1f} "
            f"{sum(x[1] for x in rows)/n:>8.1f} "
            f"{sum(x[2] for x in rows)/n:>9.2f} "
            f"{sum(x[3] for x in rows)/n:>10.2f} "
            f"{sum(x[4] for x in rows)/n:>9.2f} "
            f"{sum(x[5] for x in rows)/n:>9.2f}"
        )

    # 2. Check existing limits files in ~/.spread-lab/tas/dev-12/ if any
    tas_dir = lab_home() / "tas" / "dev-12"
    lim_files = sorted(tas_dir.glob("limits-*.jsonl"))
    print(f"Existing limit files in {tas_dir}: {[f.name for f in lim_files]}")
    for lf in lim_files[-2:]:
        rows = [json.loads(line) for line in lf.read_text().splitlines() if line.strip()]
        ratios = [r["lo"] / r["list"] for r in rows if r.get("lo") and r.get("list")]
        if ratios:
            ratios.sort()
            print(f"  {lf.name}: {len(rows)} rows, {len(ratios)} won bounds, median lo/list={ratios[len(ratios)//2]:.3f}, min={ratios[0]:.3f}, max={ratios[-1]:.3f}")

    # 3. Show high-saving closed tours on Monday (arrivedAt < 1440) in dev-12 across 2, 3, 4 cars
    mon_arcs = []
    for r in reqs:
        if r["arrivedAt"] >= DAY or len(r["legs"]) != 1:
            continue
        opts = [Arc(r, o, geo) for o in r["options"]]
        opts = [a for a in opts if not a.unsure and a.deadline - a.ready_at - a.drive_min >= 90]
        if opts:
            opts.sort(key=lambda a: (a.deadline, a.list_cents), reverse=True)
            mon_arcs.append(opts[0])

    print(f"Monday clean 1-leg arcs: {len(mon_arcs)}")
    by_p = defaultdict(list)
    for a in mon_arcs:
        by_p[a.pickup].append(a)

    # Sample diverse Monday tours for Step 2 fork fee probing
    samples = []
    for a in mon_arcs:
        if supply30[a.pickup] < 20:
            continue
        for pb in geo.places:
            if geo.line_km(a.delivery, pb) > 30.0:
                continue
            for b in by_p[pb]:
                if b.rid == a.rid:
                    continue
                sim2 = simulate_tour([a, b], geo)
                if not sim2:
                    continue
                closes2 = geo.line_km(b.delivery, a.pickup) <= 30.0
                ref2 = (a.ref_cents + b.ref_cents) / 100.0
                lst2 = (a.list_cents + b.list_cents) / 100.0
                samples.append(("2-closed" if closes2 else "2-open", [a, b], sim2, ref2, lst2))
                # Try 3-car
                for pc in geo.places:
                    if geo.line_km(b.delivery, pc) > 30.0:
                        continue
                    for c in by_p[pc][:8]:
                        if c.rid in (a.rid, b.rid):
                            continue
                        sim3 = simulate_tour([a, b, c], geo)
                        if not sim3:
                            continue
                        closes3 = geo.line_km(c.delivery, a.pickup) <= 30.0
                        if closes3:
                            ref3 = (a.ref_cents + b.ref_cents + c.ref_cents) / 100.0
                            lst3 = (a.list_cents + b.list_cents + c.list_cents) / 100.0
                            samples.append(("3-closed", [a, b, c], sim3, ref3, lst3))
                            for pd in geo.places:
                                if geo.line_km(c.delivery, pd) > 30.0:
                                    continue
                                for d in by_p[pd][:5]:
                                    if d.rid in (a.rid, b.rid, c.rid):
                                        continue
                                    if geo.line_km(d.delivery, a.pickup) <= 30.0:
                                        sim4 = simulate_tour([a, b, c, d], geo)
                                        if sim4:
                                            ref4 = (a.ref_cents + b.ref_cents + c.ref_cents + d.ref_cents) / 100.0
                                            lst4 = (a.list_cents + b.list_cents + c.list_cents + d.list_cents) / 100.0
                                            samples.append(("4-closed", [a, b, c, d], sim4, ref4, lst4))

    by_kind = defaultdict(list)
    for item in samples:
        by_kind[item[0]].append(item)
    for k, items in sorted(by_kind.items()):
        items.sort(key=lambda x: x[3] - 25.0 * (x[2]["road_min"] / 60.0), reverse=True)
        print(f"Top Monday {k} candidates (total={len(items)}):")
        shown = set()
        cnt = 0
        for kind, arcs, sim, ref, lst in items:
            key = tuple(x.pickup for x in arcs) + (arcs[-1].delivery,)
            if key in shown:
                continue
            shown.add(key)
            route = " -> ".join([f"{x.pickup}->{x.delivery}" for x in arcs])
            print(f"  {[x.rid for x in arcs]} {route} | road={sim['road_min']}m dh={sim['deadhead_min']}m | sum_ref=€{ref:.0f} sum_list=€{lst:.0f} | sup0={supply30[arcs[0].pickup]}")
            cnt += 1
            if cnt >= 6:
                break


if __name__ == "__main__":
    main()
