"""Analyze Idea #21 (friday-on-a) smoke and dev runs against Policy A and champion."""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from spread_lab.cli import compare_text, summary_text
from spread_lab.lab import champion_results, compare, load_results, summarize

REPO = Path(__file__).resolve().parents[2]
A_WT = REPO.parent / "n14-03324-supply-adaptive-fee-open-and-drop-rescue" / "runs"
A_SMOKE = A_WT / "20261114-034543-fee-drop-smoke5-all180"
A_DEV = A_WT / "20261114-034812-fee-drop-all180-dev"

RUNS = [
    ("noop", "20261114-063514-friday-on-a-noop", "smoke"),
    ("s1: fg=10, d=0.0", "20261114-063653-friday-on-a-s1-fg10-d0", "smoke"),
    ("s2: fg=10, d=0.05", "20261114-063823-friday-on-a-s2-fg10-d05", "smoke"),
    ("s3: sur=6, slack", "20261114-064111-friday-on-a-s3-sur6-slack", "smoke"),
    ("s4: sur=6, midtown", "20261114-064217-friday-on-a-s4-sur6-midtown", "smoke"),
    ("s5: sur=6, ring", "20261114-064328-friday-on-a-s5-sur6-ring", "smoke"),
    ("dev1: fg=10, d=0.0", "20261114-064554-friday-on-a-fg10-d0-dev", "dev"),
    ("dev2: sur=6, slack", "20261114-064735-friday-on-a-sur6-slack-dev", "dev"),
]

KEYS = [
    "won_fri",
    "won_fri_same_day",
    "won_fri_next_day",
    "won_fri_within_3_days",
    "quoted_fri_gate",
    "won_fri_gate",
    "late_fri_gate",
    "margin_fri_gate_cents",
    "quote_tilt",
    "surplus_open_min",
    "quoted_surplus",
    "won_surplus",
    "late_surplus",
    "margin_surplus_cents",
]


def agg_stats(rows: list[dict]) -> dict[str, float]:
    n = len(rows)
    tot: Counter = Counter()
    for r in rows:
        st = r.get("stats", {})
        for k in KEYS:
            tot[k] += st.get(k, 0)
    return {k: tot[k] / n for k in KEYS if tot[k] != 0}


def main() -> None:
    a_smoke_rows = load_results(A_SMOKE)
    a_dev_rows = load_results(A_DEV)
    champ_rows = champion_results()

    print("=== Policy A Reference Summary ===")
    print("A smoke:", summary_text(summarize(a_smoke_rows)))
    print("A dev:  ", summary_text(summarize(a_dev_rows)))
    print("A dev vs champion:", compare_text(compare(a_dev_rows, champ_rows), "champion"))
    print()

    for label, folder, split in RUNS:
        path = REPO / "runs" / folder
        rows = load_results(path)
        s = summarize(rows)
        vs_a = compare(rows, a_smoke_rows if split == "smoke" else a_dev_rows)
        vs_c = compare(rows, champ_rows)
        print(f"=== {label} ({folder}) [{split}] ===")
        print(f"  Worst on-time: {s['on_time_min']:.2%} | Mean on-time: {s['on_time_mean']:.2%} | SAFE: {s['safe']}")
        print(" ", summary_text(s))
        print(" ", compare_text(vs_a, "Policy A"))
        print(" ", compare_text(vs_c, "champion (v3)"))
        print("  Stats (mean/world):", agg_stats(rows))
        print()


if __name__ == "__main__":
    main()
