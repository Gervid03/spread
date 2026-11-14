"""Validation and 48-world aggregation script for candidates A, B, C, and D vs Champion v2."""
from __future__ import annotations

import argparse
import json
import math
import statistics
import subprocess
from pathlib import Path

from spread_lab.lab import CHAMPION, compare, load_results, summarize

V2_FRESH = Path("/home/lab/spread/runs/20261114-002838-n-champ-fresh32")
NIGHT32_SEEDS = ",".join(f"night-{i:02d}" for i in range(1, 33))

BASE = [
    "-s", "trust_invest=0.05",
    "-s", "notes_v2=True",
    "-s", "note_unsure=decline",
    "-s", "max_next_day_drive_min=480",
    "-s", "fri_same_day_max_drive=100",
    "-s", "thin_long_next_day_supply=50",
    "-s", "ring_to_hub_same_day_min=60",
    "-s", "same_day_min_supply=50",
    "-s", "min_slack_min=150",
    "-s", "slack_per_drive=0.75",
]

CANDIDATES = {
    "A": {
        "branch": "origin/exp/gemini-n14-03324-supply-adaptive-fee-open-and-drop-rescue",
        "wt": Path("/home/lab/spread-wt/val-A"),
        "dev_run": Path("/home/lab/spread-wt/n14-03324-supply-adaptive-fee-open-and-drop-rescue/runs/20261114-034812-fee-drop-all180-dev"),
        "flags": BASE + [
            "-s", "backlog_multiday_weight=0.25",
            "-s", "backlog_in_flight_weight=0.35",
            "-s", "price_target_win=0.40",
            "-s", "min_supply=22",
            "-s", "drop_urgent_margin_min=180",
            "-s", "hub_multiday_fee_open=0.80",
            "-s", "thin_sameday_fee_open=0.90",
        ],
    },
    "B": {
        "branch": "origin/exp/gemini-n14-03111-adaptive-delivery-buffer-and-alarm",
        "wt": Path("/home/lab/spread-wt/val-B"),
        "dev_run": Path("/home/lab/spread-wt/n14-03111-adaptive-delivery-buffer-and-alarm/runs/20261114-032059-gtn-ptw40-buf-alarm-dev"),
        "flags": BASE + [
            "-s", "price_target_win=0.40",
            "-s", "min_supply=22",
            "-s", "delivery_buffer_min=30",
            "-s", "buffer_min_slack_min=210",
            "-s", "pre_warn_lead_min=60",
            "-s", "pre_warn_fee=1.35",
        ],
    },
    "C": {
        "branch": "origin/exp/gemini-n14-04154-stack-v7-feedrop-buf-alarm",
        "wt": Path("/home/lab/spread-wt/val-C"),
        "dev_run": Path("/home/lab/spread-wt/n14-04154-stack-v7-feedrop-buf-alarm/runs/20261114-044017-stack-v7-dlr01-dev"),
        "flags": BASE + [
            "-s", "backlog_multiday_weight=0.25",
            "-s", "backlog_in_flight_weight=0.35",
            "-s", "hub_multiday_fee_open=0.80",
            "-s", "thin_sameday_fee_open=0.90",
            "-s", "drop_urgent_margin_min=180",
            "-s", "delivery_buffer_min=30",
            "-s", "buffer_min_slack_min=210",
            "-s", "pre_warn_lead_min=60",
            "-s", "pre_warn_fee=1.35",
            "-s", "price_target_win=0.40",
            "-s", "min_supply=22",
            "-s", "fee_warn=1.48",
            "-s", "fee_step_min=25",
            "-s", "steep_open=1.55",
            "-s", "dealer_lr=0.01",
        ],
    },
    "D": {
        "branch": "origin/exp/gemini-n14-03501-extring-full-neutral-and-leadcar",
        "wt": Path("/home/lab/spread-wt/val-D"),
        "dev_run": Path("/home/lab/spread-wt/n14-03501-extring-full-neutral-and-leadcar/runs/20261114-040101-backlog-extring-neutral-leadcar-dev"),
        "flags": BASE + [
            "-s", "backlog_multiday_weight=0.25",
            "-s", "backlog_in_flight_weight=0.35",
            "-s", "price_target_win=0.40",
            "-s", "min_supply=22",
            "-s", "dealer_lr=0.01",
            "-s", "ext_ring_min_supply=30",
            "-s", "ext_ring_max_drive_min=220",
            "-s", "return_hub_min_supply=200",
            "-s", "return_hub_max_drive_min=180",
            "-s", "ext_ring_neutral_learn=True",
            "-s", "lead_car=True",
            "-s", "lead_car_max_gap_km=0.0",
            "-s", "lead_car_max_deliv_gap_km=25.0",
            "-s", "lead_car_fee_mult=1.00",
        ],
    },
}


def latest_run(wt: Path, suffix: str) -> Path | None:
    runs_dir = wt / "runs"
    if not runs_dir.exists():
        return None
    matches = sorted(runs_dir.glob(f"*-{suffix}"))
    return matches[-1] if matches else None


def run_night32(key: str) -> Path:
    info = CANDIDATES[key]
    wt = info["wt"]
    existing = latest_run(wt, "night32")
    if existing and (existing / "summary.json").exists():
        s = json.loads((existing / "summary.json").read_text())
        if s.get("n") == 32 and s.get("failed", 0) == 0:
            print(f"[{key}] Using existing complete night32 run: {existing}")
            return existing
    cmd = [
        "uv", "--directory", str(wt), "run", "lab", "eval",
        "--seeds", NIGHT32_SEEDS,
        *info["flags"],
        "--vs", str(V2_FRESH),
        "--name", "night32",
    ]
    print(f"[{key}] Running night32 (32 worlds)...")
    subprocess.run(cmd, check=True)
    out = latest_run(wt, "night32")
    assert out is not None
    return out


def summarize_48() -> None:
    v2_hold = load_results(CHAMPION / "results" / "holdout-L8.jsonl")
    v2_night = load_results(V2_FRESH)
    v2_all = v2_hold + v2_night

    print("=== 48-World Summary Table ===")
    header = (
        "| Candidate | Holdout Mean | Holdout Δ vs v2 ± SE (t) | Night32 Mean | Night32 Δ vs v2 ± SE (t) "
        "| 48-World Mean | 48-World Δ vs v2 ± SE (t) | Worst On-Time | <92% | <91% | Ranked |"
    )
    sep = "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"
    print(header)
    print(sep)

    s_v2_h = summarize(v2_hold)
    s_v2_n = summarize(v2_night)
    s_v2_48 = summarize(v2_all)
    u92_v2 = sum(1 for r in v2_all if r["on_time"] < 0.92)
    u91_v2 = sum(1 for r in v2_all if r["on_time"] < 0.91)
    print(
        f"| **v2 (Champion)** | €{s_v2_h['margin_mean']:,.2f} | — | €{s_v2_n['margin_mean']:,.2f} | — "
        f"| €{s_v2_48['margin_mean']:,.2f} | — | {s_v2_48['on_time_min']:.2%} | {u92_v2} | {u91_v2} | {s_v2_48['ranked']}/48 |"
    )

    for key, info in CANDIDATES.items():
        wt = info["wt"]
        hold_dir = latest_run(wt, "holdout")
        night_dir = latest_run(wt, "night32")
        if not hold_dir or not night_dir:
            print(f"| **{key}** | (incomplete) | | | | | | | | | |")
            continue
        r_hold = load_results(hold_dir)
        r_night = load_results(night_dir)
        r_all = r_hold + r_night

        sh = summarize(r_hold)
        sn = summarize(r_night)
        s48 = summarize(r_all)

        ch = compare(r_hold, v2_hold)
        cn = compare(r_night, v2_night)
        c48 = compare(r_all, v2_all)

        u92 = sum(1 for r in r_all if r["on_time"] < 0.92)
        u91 = sum(1 for r in r_all if r["on_time"] < 0.91)
        u92_seeds = [f"{r['seed']} ({r['on_time']:.2%})" for r in r_all if r["on_time"] < 0.92]

        print(
            f"| **{key}** (`{info['branch'].split('/')[-1]}`) "
            f"| €{sh['margin_mean']:,.2f} | €{ch['delta_mean']:+,.2f} ± {ch['delta_se']:,.2f} ({ch['t']:.2f}, {ch['better']}/{ch['worse']}) "
            f"| €{sn['margin_mean']:,.2f} | €{cn['delta_mean']:+,.2f} ± {cn['delta_se']:,.2f} ({cn['t']:.2f}, {cn['better']}/{cn['worse']}) "
            f"| **€{s48['margin_mean']:,.2f}** | **€{c48['delta_mean']:+,.2f} ± {c48['delta_se']:,.2f} ({c48['t']:.2f}, {c48['better']}/{c48['worse']})** "
            f"| {s48['on_time_min']:.2%} | {u92} | {u91} | {s48['ranked']}/48 |"
        )
        print(f"  -> {key} dirs: holdout={hold_dir.name}, night32={night_dir.name}, <92% seeds={u92_seeds}")


def run_checks(key: str) -> None:
    info = CANDIDATES[key]
    wt = info["wt"]
    dev_run = info["dev_run"]
    dev_rows = {r["seed"]: r for r in load_results(dev_run)}

    print(f"=== Check 1: Restart at minute 3600 on dev-03 for {key} ===")
    restart_cmd = [
        "uv", "--directory", str(wt), "run", "lab", "play",
        "--seed", "dev-03",
        *info["flags"],
        "--restart-at", "3600",
    ]
    res = subprocess.run(restart_cmd, capture_output=True, text=True, check=True)
    print(res.stdout)
    d03 = dev_rows["dev-03"]
    print(
        f"Dev run dev-03 baseline ({dev_run.name}): "
        f"margin €{d03['margin']:,.2f}, won {d03['won']}, on_time {d03['on_time']:.2%}, ranked {d03['ranked']}"
    )

    print(f"=== Check 2: Live parity (step_min=3 on smoke) for {key} ===")
    step3_cmd = [
        "uv", "--directory", str(wt), "run", "lab", "eval",
        "--seeds-from", "smoke",
        *info["flags"],
        "-s", "step_min=3",
        "--vs", str(dev_run),
        "--name", "step3",
    ]
    subprocess.run(step3_cmd, check=True)
    step3_dir = latest_run(wt, "step3")
    assert step3_dir is not None
    s3_rows = load_results(step3_dir)
    print(f"Per-seed step3 ({step3_dir.name}) vs dev ({dev_run.name}):")
    print("| Seed | Dev Margin | Step3 Margin | Δmargin | Dev On-Time | Step3 On-Time | Δon-time (pp) | Ranked |")
    print("|---|---:|---:|---:|---:|---:|---:|---|")
    for r in sorted(s3_rows, key=lambda x: x["seed"]):
        base = dev_rows[r["seed"]]
        dm = r["margin"] - base["margin"]
        dot = (r["on_time"] - base["on_time"]) * 100.0
        print(
            f"| `{r['seed']}` | €{base['margin']:,.2f} | €{r['margin']:,.2f} | €{dm:+,.2f} "
            f"| {base['on_time']:.2%} | {r['on_time']:.2%} | {dot:+.2f} pp | {r['ranked']} |"
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", choices=["A", "B", "C", "D", "all"], help="Run night32 for candidate(s)")
    parser.add_argument("--checks", choices=["A", "B", "C", "D"], help="Run restart and step3 checks on winner W")
    parser.add_argument("--summary", action="store_true", help="Print 48-world summary table")
    args = parser.parse_args()

    if args.run:
        keys = ["A", "B", "C", "D"] if args.run == "all" else [args.run]
        for k in keys:
            run_night32(k)
    if args.checks:
        run_checks(args.checks)
    if args.summary or (not args.run and not args.checks):
        summarize_48()


if __name__ == "__main__":
    main()
