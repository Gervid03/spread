"""Analyze Stack v8 runs against parent baseline runs on dev (16 seeds)."""
from __future__ import annotations

import glob
import json
import math
from pathlib import Path


def load_run(path: Path) -> dict[str, dict]:
    rows = {}
    with (path / "results.jsonl").open() as f:
        for line in f:
            r = json.loads(line)
            rows[r["seed"]] = r
    return rows


def find_run(pattern: str) -> Path:
    matches = sorted(glob.glob(f"/home/lab/spread-wt/*/runs/*{pattern}*") + glob.glob(f"runs/*{pattern}*"))
    if not matches:
        raise FileNotFoundError(f"No run matching {pattern}")
    return Path(matches[-1])


def paired_stats(base_rows: dict[str, dict], cand_rows: dict[str, dict]) -> dict:
    seeds = sorted(set(base_rows) & set(cand_rows))
    diffs = [cand_rows[s]["margin"] - base_rows[s]["margin"] for s in seeds]
    ot_diffs = [(cand_rows[s]["on_time"] - base_rows[s]["on_time"]) * 100.0 for s in seeds]
    n = len(diffs)
    mean_d = sum(diffs) / n
    var_d = sum((d - mean_d) ** 2 for d in diffs) / (n - 1) if n > 1 else 0.0
    se_d = math.sqrt(var_d / n) if n > 1 else 0.0
    t_stat = mean_d / se_d if se_d > 0 else 0.0
    better = sum(1 for d in diffs if d > 1e-6)
    worse = sum(1 for d in diffs if d < -1e-6)
    tied = n - better - worse
    return {
        "n": n,
        "mean_d": mean_d,
        "se_d": se_d,
        "t": t_stat,
        "better": better,
        "worse": worse,
        "tied": tied,
        "mean_ot_d": sum(ot_diffs) / n,
    }


def summarize_run(rows: dict[str, dict]) -> dict:
    n = len(rows)
    margins = [r["margin"] for r in rows.values()]
    ots = [r["on_time"] * 100.0 for r in rows.values()]
    stats_keys = [
        "won",
        "quoted_ext_ring",
        "quoted_return_hub",
        "won_ext_ring",
        "won_return_hub",
        "late_ext_ring",
        "margin_ext_ring_cents",
        "ext_ring_skipped_learn",
        "lead_car_paired",
        "lead_car_booked",
        "lead_car_split",
        "hub_multiday_posts",
        "thin_sameday_posts",
        "drop_rescued",
        "gig_dropped",
        "no_show",
        "deadline_close",
        "gig_expired",
        "visit_failed",
        "won_ring",
        "late_ring",
        "declined_backlog",
        "in_flight_blocked",
    ]
    totals = {k: sum(r.get("stats", {}).get(k, 0) for r in rows.values()) for k in stats_keys}
    late_orders = sum(round(r["won"] * (1.0 - r["on_time"])) for r in rows.values())
    won_orders = sum(r.get("won", 0) for r in rows.values())
    ledger_keys = ["revenue", "driver_fee", "late_refund", "failed_visit", "waiting", "release_fee", "fine"]
    ledger_means = {
        k: sum(r.get("ledger", {}).get(k, 0.0) for r in rows.values()) / n for k in ledger_keys
    }
    return {
        "mean_margin": sum(margins) / n,
        "min_margin": min(margins),
        "median_margin": sorted(margins)[n // 2] if n % 2 == 1 else 0.5 * (sorted(margins)[n // 2 - 1] + sorted(margins)[n // 2]),
        "min_ot": min(ots),
        "mean_ot": sum(ots) / n,
        "won_orders": won_orders,
        "late_orders": late_orders,
        "totals": totals,
        "ledger": ledger_means,
    }


def main() -> None:
    champ_rows = {}
    with Path("champion/results/dev-L8.jsonl").open() as f:
        for line in f:
            r = json.loads(line)
            champ_rows[r["seed"]] = r

    runs = {
        "champ_v2": champ_rows,
        "n14-02462 (backlog)": load_run(find_run("20261114-030237-backlog-aware-gtn-ptw40-dev")),
        "n14-03322 (fw150)": load_run(find_run("backlog-s150-fw150-s20-dev")),
        "n14-03324 (fee-drop)": load_run(find_run("20261114-034812-fee-drop-all180-dev")),
        "n14-03501 (ext-lead)": load_run(find_run("20261114-040101-backlog-extring-neutral-leadcar-dev")),
        "Dev 1 (v8-feedrop-extlead)": load_run(find_run("20261114-045119-v8-feedrop-extlead-dev")),
        "Dev 2 (v8-feedrop-fw150-dlr01)": load_run(find_run("20261114-045340-v8-feedrop-fw150-dlr01-dev")),
        "Dev 3 (v8-full)": load_run(find_run("20261114-045846-v8-full-dev")),
        "Dev 4 (v8-feedrop-extonly)": load_run(find_run("20261114-050040-v8-feedrop-extonly-dev")),
    }

    print("=== PAIRED COMPARISONS ===")
    refs = ["champ_v2", "n14-02462 (backlog)", "n14-03322 (fw150)", "n14-03324 (fee-drop)", "n14-03501 (ext-lead)"]
    cands = [
        "Dev 1 (v8-feedrop-extlead)",
        "Dev 2 (v8-feedrop-fw150-dlr01)",
        "Dev 3 (v8-full)",
        "Dev 4 (v8-feedrop-extonly)",
    ]
    for c in cands:
        for ref in refs:
            st = paired_stats(runs[ref], runs[c])
            print(
                f"{c:30s} vs {ref:22s}: Δmargin €{st['mean_d']:+8.2f} ± {st['se_d']:6.2f} "
                f"(t={st['t']:+5.2f})  {st['better']}/{st['worse']}/{st['tied']}  ΔOT {st['mean_ot_d']:+.2f}%"
            )
        print()

    print("=== PAIRWISE AMONG V8 DEV RUNS ===")
    for i, c1 in enumerate(cands):
        for c2 in cands[i + 1 :]:
            st = paired_stats(runs[c2], runs[c1])
            print(
                f"{c1:30s} vs {c2:30s}: Δmargin €{st['mean_d']:+8.2f} ± {st['se_d']:6.2f} "
                f"(t={st['t']:+5.2f})  {st['better']}/{st['worse']}/{st['tied']}  ΔOT {st['mean_ot_d']:+.2f}%"
            )

    print("=== SUMMARY TABLE ===")
    for name, rows in runs.items():
        s = summarize_run(rows)
        print(f"--- {name} ---")
        print(
            f"margin: mean €{s['mean_margin']:.2f}, median €{s['median_margin']:.2f}, min €{s['min_margin']:.2f} | "
            f"OT: min {s['min_ot']:.2f}%, mean {s['mean_ot']:.2f}% | won_orders={s['won_orders']} ({s['won_orders']/16:.2f}/w), late={s['late_orders']} ({s['late_orders']/16:.2f}/w)"
        )
        print("totals:", s["totals"])
        print("ledger (€/w):", {k: round(v, 2) for k, v in s["ledger"].items()})


if __name__ == "__main__":
    main()
