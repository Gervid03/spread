"""Analyze and format Tier 0 sweeps results."""
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from spread_lab.lab import champion_results, compare, load_results, summarize

smoke_runs = {
    "S1: supply_radius_km": [
        ("supply_radius_km=30", "runs/20261113-234857-s1-supply_radius_km30"),
        ("supply_radius_km=40", "runs/20261113-234947-s1-supply_radius_km40"),
        ("supply_radius_km=55", "runs/20261113-235026-s1-supply_radius_km55"),
    ],
    "S2: price_mult_max / dealer_adj_max": [
        ("price_mult_max=1.8, dealer_adj_max=1.3", "runs/20261113-235057-s2-price_mult_max1.8-dealer_adj_max1.3"),
        ("price_mult_max=1.8, dealer_adj_max=1.6", "runs/20261113-235202-s2-price_mult_max1.8-dealer_adj_max1.6"),
        ("price_mult_max=2.3, dealer_adj_max=1.3", "runs/20261113-235221-s2-price_mult_max2.3-dealer_adj_max1.3"),
        ("price_mult_max=2.3, dealer_adj_max=1.6", "runs/20261113-235238-s2-price_mult_max2.3-dealer_adj_max1.6"),
    ],
    "S3: fee_open": [
        ("fee_open=0.85", "runs/20261113-235355-s3-fee_open0.85"),
        ("fee_open=0.90", "runs/20261113-235513-s3-fee_open0.9"),
        ("fee_open=1.00", "runs/20261113-235543-s3-fee_open1"),
    ],
    "S4: loss_streak_freeze / price_lr": [
        ("loss_streak_freeze=12, price_lr=0.02", "runs/20261113-235631-s4-loss_streak_freeze12-price_lr0.02"),
        ("loss_streak_freeze=12, price_lr=0.05", "runs/20261113-235645-s4-loss_streak_freeze12-price_lr0.05"),
        ("loss_streak_freeze=9999, price_lr=0.02", "runs/20261113-235705-s4-loss_streak_freeze9999-price_lr0.02"),
        ("loss_streak_freeze=9999, price_lr=0.05", "runs/20261113-235942-s4-loss_streak_freeze9999-price_lr0.05"),
    ],
    "S5: offers_per_warning": [
        ("offers_per_warning=0", "runs/20261114-000025-s5"),
    ],
    "S6: min_slack_min": [
        ("min_slack_min=120", "runs/20261114-000136-s6-min_slack_min120"),
        ("min_slack_min=180", "runs/20261114-000237-s6-min_slack_min180"),
        ("min_slack_min=240", "runs/20261114-000303-s6-min_slack_min240"),
    ],
}

dev_runs = [
    ("s1-dev (supply_radius_km=55)", "runs/20261114-000350-s1-dev"),
    ("s2-dev (dealer_adj_max=1.6)", "runs/20261114-001029-s2-dev"),
    ("s3-dev (fee_open=0.85)", "runs/20261114-000529-s3-dev"),
    ("s4-dev (price_lr=0.05)", "runs/20261114-000646-s4-dev"),
    ("s5-dev (offers_per_warning=0)", "runs/20261114-000817-s5-dev"),
    ("s6-dev (min_slack_min=180)", "runs/20261114-000929-s6-dev"),
    ("combined-dev (55, 0.85, 0.05, 0, 180)", "runs/20261114-001152-combined-dev"),
    ("combined-taxback (+ win=0.45)", "runs/20261114-001342-combined-taxback"),
]

def print_table():
    base = champion_results()
    print("## Smoke Runs (n=4)\n")
    for section, runs in smoke_runs.items():
        print(f"### {section}")
        print("| Setting | Mean Margin | Δmargin ± SE | t | better/worse | Min On-Time | SAFE | Run Folder |")
        print("|---|---|---|---|---|---|---|---|")
        for label, path in runs:
            p = Path(path)
            rows = load_results(p)
            s = summarize(rows)
            c = compare(rows, base)
            t_str = f"{c['t']:.2f}" if c and c['t'] is not None else "-"
            delta_str = f"€{c['delta_mean']:+,.2f} ± {c['delta_se']:,.2f}" if c else "-"
            bw_str = f"{c['better']}/{c['worse']}" if c else "-"
            safe_str = "SAFE" if s.get("safe") else "unsafe"
            min_ot = f"{s.get('on_time_min', 0):.1%}"
            mean_m = f"€{s.get('margin_mean', 0):,.2f}"
            print(f"| {label} | {mean_m} | {delta_str} | {t_str} | {bw_str} | {min_ot} | {safe_str} | `{p.name}` |")
        print()

    print("## Dev Runs (n=16)\n")
    print("| Run | Mean Margin | Δmargin ± SE | t | better/worse | Min On-Time | SAFE | Run Folder |")
    print("|---|---|---|---|---|---|---|---|")
    for label, path in dev_runs:
        p = Path(path)
        rows = load_results(p)
        s = summarize(rows)
        c = compare(rows, base)
        t_str = f"{c['t']:.2f}" if c and c['t'] is not None else "-"
        delta_str = f"€{c['delta_mean']:+,.2f} ± {c['delta_se']:,.2f}" if c else "-"
        bw_str = f"{c['better']}/{c['worse']}" if c else "-"
        safe_str = "SAFE" if s.get("safe") else "unsafe"
        min_ot = f"{s.get('on_time_min', 0):.1%}"
        mean_m = f"€{s.get('margin_mean', 0):,.2f}"
        print(f"| {label} | {mean_m} | {delta_str} | {t_str} | {bw_str} | {min_ot} | {safe_str} | `{p.name}` |")

if __name__ == "__main__":
    print_table()
