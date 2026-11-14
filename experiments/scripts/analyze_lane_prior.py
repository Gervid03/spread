"""Analyze lane-prior runs: per-seed paired deltas, worst world, ledger breakdown, and lane-tercile counters."""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

from spread_lab.env import REPO
from spread_lab.lab import champion_results, compare, load_results, summarize


def load_lane_baseline_from_reveals(seeds: set[str]) -> dict[str, float]:
    """Compute exact baseline lane_quotes, lane_wins, lane_late, lane_margin_cents for champion v3T on given seeds."""
    from export_lane_and_buffer import CACHE_ROOT, load_world_data

    lane_table = json.loads((REPO / "src/spread_lab/data/lane_table.json").read_text(encoding="utf-8"))
    pk_map = lane_table["pickup"]
    dl_map = lane_table["delivery"]
    t_lo, t_hi = lane_table["meta"]["terciles"]

    def bkt(pk: str, dl: str) -> str:
        eff = pk_map.get(pk, 0.0) + dl_map.get(dl, 0.0)
        return "low" if eff < t_lo else ("mid" if eff < t_hi else "high")

    manifest = json.loads((CACHE_ROOT / "manifest.json").read_text(encoding="utf-8"))
    entries = [m for m in manifest if m["version"] == "v3T" and m["seed"] in seeds]
    tot = Counter()
    for e in entries:
        qr, wr, _ = load_world_data(e)
        for r in qr:
            tot[f"lane_quotes_{bkt(r['pickup'], r['delivery'])}"] += 1
        for w in wr:
            b = bkt(w["pickup"], w["delivery"])
            tot[f"lane_wins_{b}"] += 1
            tot[f"lane_late_{b}"] += w["late"]
            tot[f"lane_margin_{b}_cents"] += round(w["margin_eur"] * 100)
    n = max(1, len(entries))
    return {k: v / n for k, v in tot.items()}


def main() -> None:
    champ = champion_results()
    champ_by_seed = {(r["seed"], r["level"]): r for r in champ}

    for arg in sys.argv[1:]:
        run_dir = Path(arg)
        rows = load_results(run_dir)
        s = summarize(rows)
        c = compare(rows, champ)
        seeds = {r["seed"] for r in rows}
        under_92 = sum(1 for r in rows if r["on_time"] < 0.92)
        worst_r = min(rows, key=lambda r: r["on_time"])

        print(f"=== {run_dir.name} (n={len(rows)}) ===")
        print(
            f"  Worst world: {worst_r['seed']} on_time={worst_r['on_time']:.2%} margin=€{worst_r['margin']:,.2f} "
            f"(champ on_time={champ_by_seed[(worst_r['seed'], 8)]['on_time']:.2%}, "
            f"margin=€{champ_by_seed[(worst_r['seed'], 8)]['margin']:,.2f}); worlds <92%: {under_92}"
        )
        print(f"  Summary: {s}")
        print(f"  Compare vs champion: {c}")

        # Per-seed comparison
        for r in sorted(rows, key=lambda x: x["seed"]):
             b = champ_by_seed[(r["seed"], r["level"])]
             dm = r["margin"] - b["margin"]
             dot = (r["on_time"] - b["on_time"]) * 100
             dw = r["won"] - b["won"]
             print(f"    {r['seed']}: margin €{r['margin']:9.2f} (Δ {dm:+8.2f}) | won {r['won']:3d} ({dw:+3d}) | on_time {r['on_time']:6.2%} ({dot:+5.2f}pp)")

        # Ledger & stats means
        n = len(rows)
        champ_sub = [champ_by_seed[(r["seed"], r["level"])] for r in rows]
        for kind in ["revenue", "driver_fee", "late_refund", "undelivered_penalty", "failed_visit", "release_fee"]:
            v_cand = sum(r.get("ledger", {}).get(kind, 0.0) for r in rows) / n
            v_base = sum(r.get("ledger", {}).get(kind, 0.0) for r in champ_sub) / n
            print(f"  Ledger {kind:<20}: cand €{v_cand:9.2f}  champ €{v_base:9.2f}  (Δ €{v_cand - v_base:+8.2f})")

        for sk in ["quote_quote", "quote_floor", "quote_decline", "won", "deadline_close"]:
            v_cand = sum(r.get("stats", {}).get(sk, 0) for r in rows) / n
            v_base = sum(r.get("stats", {}).get(sk, 0) for r in champ_sub) / n
            print(f"  Stat {sk:<22}: cand {v_cand:7.2f}/w  champ {v_base:7.2f}/w  (Δ {v_cand - v_base:+6.2f})")

        base_lane = load_lane_baseline_from_reveals(seeds)
        print("  Lane tercile breakdown (per world):")
        for b in ["low", "mid", "high"]:
            q = sum(r["stats"].get(f"lane_quotes_{b}", 0) for r in rows) / n
            w = sum(r["stats"].get(f"lane_wins_{b}", 0) for r in rows) / n
            lt = sum(r["stats"].get(f"lane_late_{b}", 0) for r in rows) / n
            mrg = sum(r["stats"].get(f"lane_margin_{b}_cents", 0) for r in rows) / n / 100.0
            bq = base_lane.get(f"lane_quotes_{b}", 0.0)
            bw = base_lane.get(f"lane_wins_{b}", 0.0)
            blt = base_lane.get(f"lane_late_{b}", 0.0)
            bmrg = base_lane.get(f"lane_margin_{b}_cents", 0.0) / 100.0
            print(
                f"    {b:<5}: quotes {q:6.1f} (champ {bq:6.1f}) | "
                f"wins {w:5.1f} [{w/max(1e-9,q):5.1%}] (champ {bw:5.1f} [{bw/max(1e-9,bq):5.1%}]) | "
                f"late {lt:4.2f} [{lt/max(1e-9,w):5.2%}] (champ {blt:4.2f}) | "
                f"margin €{mrg:7.2f} [€{mrg/max(1e-9,w):5.2f}/win] (champ €{bmrg:7.2f} [€{bmrg/max(1e-9,bw):5.2f}/win], Δ €{mrg-bmrg:+7.2f})"
            )


if __name__ == "__main__":
    main()
