#!/usr/bin/env python3
"""Compare key Desk stats across A0..A5 on the 8 screening dev seeds."""
from __future__ import annotations

import json
from pathlib import Path
from statistics import mean

RUNS = [
    ("v6-champ", "champion/results/dev-L8.jsonl"),
    ("A0-all5", "runs/20261114-143153-r4t-a0-all5/results.jsonl"),
    ("A1-no-margin", "runs/20261114-143343-r4t-a1-no-margin/results.jsonl"),
    ("A2-no-demand", "runs/20261114-143804-r4t-a2-no-demand/results.jsonl"),
    ("A3-no-wild", "runs/20261114-144143-r4t-a3-no-wild/results.jsonl"),
    ("A4-no-volume", "runs/20261114-144456-r4t-a4-no-volume/results.jsonl"),
    ("A5-no-routes", "runs/20261114-145347-r4t-a5-no-routes/results.jsonl"),
    ("T1-nocalm", "runs/20261114-151054-r4t-t1-guards-nocalm/results.jsonl"),
    ("T2-surgical", "runs/20261114-151629-r4t-t2-tail-surgical/results.jsonl"),
]

SEEDS = {"dev-01", "dev-04", "dev-06", "dev-07", "dev-08", "dev-12", "dev-13", "dev-16"}

KEYS = [
    "quote_quote", "quote_floor", "quote_decline",
    "relay_paired", "relay_paired_roundtrip", "relay_split_patience",
    "lead_car_paired", "lead_car_split",
    "net_offers", "view_offers_sent", "deadline_close",
    "quoted_return_hub", "return_hub_throttled", "quoted_fut_sd",
    "quoted_trade_in", "inb_floor_saved", "inbound_paused_congested",
    "sd_prem_lifted", "sup_fri_thin_quoted",
    "dropped_next_day_long", "dropped_thin_long_next_day", "net_throttled",
]


def main() -> None:
    loaded = {}
    for label, p in RUNS:
        rows = [json.loads(line) for line in Path(p).read_text().splitlines() if line.strip()]
        rows = [r for r in rows if r["seed"] in SEEDS]
        loaded[label] = rows
        ots = [r["on_time"] for r in rows]
        margins = [r["margin"] for r in rows]
        wons = [r["won"] for r in rows]
        dfee_rev = [-r["ledger"].get("driver_fee", 0) / max(1, r["revenue"]) for r in rows]
        print(f"{label:14s}: margin €{mean(margins):8,.1f} (min €{min(margins):7,.1f}) | won {mean(wons):5.1f} | fee/rev {mean(dfee_rev):.1%} | OT mean {mean(ots):.2%} min {min(ots):.2%}")

    print()
    header = f"{'Counter':26s} " + " ".join(f"{lbl:>12s}" for lbl, _ in RUNS)
    print(header)
    for k in KEYS:
        vals = []
        for lbl, _ in RUNS:
            v = mean(r["stats"].get(k, 0) for r in loaded[lbl])
            vals.append(f"{v:12.1f}")
        print(f"{k:26s} " + " ".join(vals))


if __name__ == "__main__":
    main()
