#!/usr/bin/env python3
"""Per-seed comparison of r4-tune-dev-t3 vs Champion v6 across all 16 dev worlds."""
from __future__ import annotations

from pathlib import Path
from spread_lab.lab import compare, load_results, summarize


def main() -> None:
    v6 = load_results(Path("champion/results/dev-L8.jsonl"))
    t3 = load_results(Path("runs/20261114-153244-r4-tune-dev-t3"))
    c = compare(t3, v6)
    s6, st = summarize(v6), summarize(t3)
    print(f"Champion v6 : mean €{s6['margin_mean']:,.2f}, min €{s6['margin_min']:,.2f}, won {s6['won_mean']:.1f}, OT mean {s6['on_time_mean']:.2%} min {s6['on_time_min']:.2%}")
    print(f"r4-tune T3  : mean €{st['margin_mean']:,.2f}, min €{st['margin_min']:,.2f}, won {st['won_mean']:.1f}, OT mean {st['on_time_mean']:.2%} min {st['on_time_min']:.2%}")
    print(f"Paired Δ    : €{c['delta_mean']:+,.2f} ± {c['delta_se']:,.2f} (t={c['t']:.2f}, W/L={c['better']}/{c['worse']})")
    print()
    by_6 = {r["seed"]: r for r in v6}
    by_t = {r["seed"]: r for r in t3}
    for s in sorted(by_6):
        a, b = by_6[s], by_t[s]
        print(f"  {s:8s}: v6 €{a['margin']:8.2f} ({a['won']:3d}, {a['on_time']:.2%}) -> T3 €{b['margin']:8.2f} ({b['won']:3d}, {b['on_time']:.2%}) | Δ €{b['margin']-a['margin']:+8.2f} | ΔOT {(b['on_time']-a['on_time'])*100:+5.2f}pp | warns {a['stats'].get('deadline_close',0):2d}->{b['stats'].get('deadline_close',0):2d}")


if __name__ == "__main__":
    main()
