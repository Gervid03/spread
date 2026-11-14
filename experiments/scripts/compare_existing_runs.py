#!/usr/bin/env python3
"""Slot-free paired comparison and stat decomposition across existing runs in ~/.spread-lab/index.jsonl."""
from __future__ import annotations

import json
from pathlib import Path
from spread_lab.lab import compare, load_results, summarize


def main() -> None:
    v6_dev = load_results(Path("champion/results/dev-L8.jsonl"))
    v5_routes = load_results(Path("/home/lab/spread-wt/cp-routes/runs/20261114-110828-cp-routes-v5-dev-seed04"))
    v6_routes = load_results(Path("/home/lab/spread-wt/promote-20261114-140259-109621/runs/20261114-140302-dev"))

    for label, a, b in [
        ("v6 -> v6+routes (effect of routes on v6)", v6_dev, v6_routes),
        ("v5+routes -> v6+routes (effect of supervisor on routes!)", v5_routes, v6_routes),
    ]:
        c = compare(a, b)
        sa, sb = summarize(a), summarize(b)
        print(f"=== {label} ===")
        print(f"  Δmargin: €{c['delta_mean']:+,.2f} ± {c['delta_se']:,.2f} (t={c['t']:.2f}, better={c['better']}/{c['n']}, worse={c['worse']}/{c['n']})")
        print(f"  A: mean €{sa['margin_mean']:,.2f}, min €{sa['margin_min']:,.2f}, won {sa['won_mean']:.1f}, OT mean {sa['on_time_mean']:.2%} min {sa['on_time_min']:.2%}")
        print(f"  B: mean €{sb['margin_mean']:,.2f}, min €{sb['margin_min']:,.2f}, won {sb['won_mean']:.1f}, OT mean {sb['on_time_mean']:.2%} min {sb['on_time_min']:.2%}")

    # Per-seed diff between v5+routes and v6+routes to see WHY supervisor changed routes!
    by_a = {r["seed"]: r for r in v5_routes}
    by_b = {r["seed"]: r for r in v6_routes}
    print()
    print("Per-seed (v6+routes - v5+routes):")
    for seed in sorted(by_a):
        ra, rb = by_a[seed], by_b[seed]
        dm = rb["margin"] - ra["margin"]
        dw = rb["won"] - ra["won"]
        dot = (rb["on_time"] - ra["on_time"]) * 100
        fri_thin = rb["stats"].get("sup_fri_thin_quoted", 0)
        calm = sum(1 for d in range(1, 5) if rb["stats"].get(f"sup_d{d}_regime") == 1)
        print(f"  {seed:8s}: Δmargin €{dm:+8.2f} | Δwon {dw:+4d} ({ra['won']}->{rb['won']}) | ΔOT {dot:+5.2f}pp ({ra['on_time']:.2%}->{rb['on_time']:.2%}) | calm_days={calm} fri_thin_q={fri_thin}")


if __name__ == "__main__":
    main()
