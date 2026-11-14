"""Analyze costprice runs and compare against baseline run folders."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from spread_lab.cli import compare_text, summary_text
from spread_lab.lab import champion_results, compare, load_results, summarize


def analyze_run(run_dir: Path, base_dir: Path | None = None) -> None:
    rows = load_results(run_dir)
    s = summarize(rows)
    print(f"=== {run_dir.name} ===")
    print(summary_text(s))
    if base_dir is not None and base_dir.exists():
        base_rows = load_results(base_dir)
        c = compare(rows, base_rows)
        if c:
            print(compare_text(c, base_dir.name))
    c_champ = compare(rows, champion_results())
    if c_champ:
        print(compare_text(c_champ, "champion"))

    q_easy = sum(r["stats"].get("q_easy", 0) for r in rows)
    q_mid = sum(r["stats"].get("q_mid", 0) for r in rows)
    q_hard = sum(r["stats"].get("q_hard", 0) for r in rows)
    w_easy = sum(r["stats"].get("w_easy", 0) for r in rows)
    w_mid = sum(r["stats"].get("w_mid", 0) for r in rows)
    w_hard = sum(r["stats"].get("w_hard", 0) for r in rows)
    l_easy = sum(r["stats"].get("late_easy", 0) for r in rows)
    l_mid = sum(r["stats"].get("late_mid", 0) for r in rows)
    l_hard = sum(r["stats"].get("late_hard", 0) for r in rows)

    print("  By third of typical_fee / max_list (<0.8 easy, 0.8-1.0 mid, >=1.0 hard):")
    for label, q, w, l in [("easy", q_easy, w_easy, l_easy), ("mid", q_mid, w_mid, l_mid), ("hard", q_hard, w_hard, l_hard)]:
        wr = (w / q * 100) if q else 0.0
        lr = (l / w * 100) if w else 0.0
        print(f"    {label:<4}: quotes={q:<4} wins={w:<4} win_rate={wr:5.1f}%  late={l:<3} late_rate={lr:5.2f}%")

    q_quote = sum(r["stats"].get("quote_quote", 0) for r in rows)
    q_floor = sum(r["stats"].get("quote_floor", 0) for r in rows)
    q_decl = sum(r["stats"].get("quote_decline", 0) for r in rows)
    won = sum(r["stats"].get("won", 0) for r in rows)
    rev = sum(r["ledger"].get("revenue", 0) for r in rows)
    fee = -sum(r["ledger"].get("driver_fee", 0) for r in rows)
    late_ref = -sum(r["ledger"].get("late_refund", 0) for r in rows)
    undeliv = -sum(r["ledger"].get("undelivered_penalty", 0) for r in rows)
    n = len(rows)
    fee_rev = (fee / rev * 100) if rev else 0.0
    print(f"  Decisions: quote={q_quote} floor={q_floor} decline={q_decl} won={won} ({won/n:.1f}/w)")
    print(f"  Ledger (/w): revenue=€{rev/n:,.2f} driver_fee=€{fee/n:,.2f} (fee/rev={fee_rev:.2f}%) late_refund=€{late_ref/n:,.2f} undeliv=€{undeliv/n:,.2f}")


def main() -> None:
    smoke_base = Path("/home/lab/spread-wt/n14-03324-supply-adaptive-fee-open-and-drop-rescue/runs/20261114-034543-fee-drop-smoke5-all180")
    dev_base = Path("/home/lab/spread-wt/n14-03324-supply-adaptive-fee-open-and-drop-rescue/runs/20261114-034812-fee-drop-all180-dev")
    for arg in sys.argv[1:]:
        p = Path(arg)
        rows = load_results(p)
        base = smoke_base if len(rows) <= 4 else dev_base
        analyze_run(p, base)


if __name__ == "__main__":
    main()
