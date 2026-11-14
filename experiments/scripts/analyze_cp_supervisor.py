#!/usr/bin/env python3
"""Summarize Morning Day Supervisor (cp-supervisor) dev and night32 telemetry."""
from __future__ import annotations

import json
import sys
from pathlib import Path


def load_rows(path: Path) -> dict[str, dict]:
    rows = {}
    with path.open() as f:
        for line in f:
            r = json.loads(line)
            if "error" not in r:
                rows[r["seed"]] = r
    return rows


def summarize_run(run_dir: Path, baseline_jsonl: Path | None = None) -> None:
    rows = load_rows(run_dir / "results.jsonl")
    summary = json.loads((run_dir / "summary.json").read_text())
    print(f"=== {run_dir.name} (n={summary['n']}, SAFE={summary['safe']}) ===")
    print(
        f"  margin mean €{summary['margin_mean']:,.2f} | median €{summary['margin_median']:,.2f} | "
        f"min €{summary['margin_min']:,.2f} | OT min {summary['on_time_min']*100:.2f}% | "
        f"OT mean {summary['on_time_mean']*100:.2f}% | won {summary['won_mean']:.1f}"
    )

    calm_days = sum(r["stats"].get("sup_days_calm", 0) for r in rows.values())
    norm_days = sum(r["stats"].get("sup_days_normal", 0) for r in rows.values())
    stress_days = sum(r["stats"].get("sup_days_stressed", 0) for r in rows.values())
    fri_fired = sum(r["stats"].get("sup_fri_surplus_fired", 0) for r in rows.values())
    fri_won = sum(r["stats"].get("sup_fri_thin_won", 0) for r in rows.values())
    fri_late = sum(r["stats"].get("sup_fri_thin_late", 0) for r in rows.values())
    fri_eur = sum(r["stats"].get("sup_fri_thin_margin_cents", 0) for r in rows.values()) / 100.0
    print(
        f"  regimes (Tue-Fri): calm={calm_days}, normal={norm_days}, stressed={stress_days} | "
        f"fri_surplus fired={fri_fired}/{len(rows)} worlds -> won={fri_won}, late={fri_late}, "
        f"net margin=€{fri_eur:+,.2f} (€{fri_eur/max(1,len(rows)):+,.2f}/world)"
    )

    if baseline_jsonl and baseline_jsonl.exists():
        base = load_rows(baseline_jsonl)
        common = sorted(set(rows) & set(base))
        diffs = [rows[s]["margin"] - base[s]["margin"] for s in common]
        n = len(diffs)
        mean_d = sum(diffs) / n
        se_d = (sum((d - mean_d) ** 2 for d in diffs) / (n * (n - 1))) ** 0.5
        better = sum(1 for d in diffs if d > 1e-6)
        worse = sum(1 for d in diffs if d < -1e-6)
        under92 = sum(1 for s in common if rows[s]["on_time"] < 0.92)
        print(
            f"  paired vs {baseline_jsonl.name}: Δmargin €{mean_d:+,.2f} ± {se_d:,.2f} "
            f"(t={mean_d/se_d:.2f}) | better {better}, worse {worse} | under 92%: {under92}"
        )


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    champ_dev = root / "champion" / "results" / "dev-L8.jsonl"
    targets = sys.argv[1:] or [
        "runs/20261114-102824-cp-supervisor-dev",
        "runs/20261114-103535-cp-supervisor-night32",
        "runs/20261114-105539-cp-supervisor-v5-dev2",
        "runs/20261114-105817-cp-supervisor-v5-nostress-dev",
        "runs/20261114-110023-cp-supervisor-v5-nostress-night32",
    ]
    for rel in targets:
        p = root / rel
        if p.exists():
            summarize_run(p, champ_dev if "v5" in p.name and "dev" in p.name else None)


if __name__ == "__main__":
    main()
