"""Compare Dev 1, Dev 2, Dev 3 against reference dev runs and summarize counters."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from spread_lab.cli import compare_text, summary_text
from spread_lab.env import lab_home
from spread_lab.lab import champion_results, compare, load_results, summarize


def find_run_dir(suffix: str) -> Path:
    local = Path("runs") / suffix
    if local.exists():
        return local
    idx = lab_home() / "index.jsonl"
    for line in idx.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if Path(row["dir"]).name == suffix:
            return Path(row["dir"])
    raise FileNotFoundError(suffix)


def stats_summary(rows: list[dict]) -> dict:
    totals = Counter()
    ledger = Counter()
    for r in rows:
        for k, v in r.get("stats", {}).items():
            totals[k] += v
        for k, v in r.get("ledger", {}).items():
            ledger[k] += v
    return {"stats": totals, "ledger": ledger}


def main() -> None:
    targets = [
        "20261114-035828-backlog-extring-neutral-dev",
        "20261114-040101-backlog-extring-neutral-leadcar-dev",
        "20261114-040453-backlog-leadcar-only-dev",
    ]
    refs = [
        "20261114-030237-backlog-aware-gtn-ptw40-dev",
        "20261114-032146-stack-gtn-dlr01-ptw38-dev",
        "20261114-032429-stack-gtn-extring-ptw38-dlr01-dev",
    ]
    loaded_refs = {name: load_results(find_run_dir(name)) for name in refs}
    loaded_targets = {name: load_results(find_run_dir(name)) for name in targets}

    for tname, trows in loaded_targets.items():
        print(f"=== {tname} ===")
        print(summary_text(summarize(trows)))
        print(compare_text(compare(trows, champion_results()), "champion"))
        for rname, rrows in loaded_refs.items():
            print(compare_text(compare(trows, rrows), rname))
        for other_name, other_rows in loaded_targets.items():
            if other_name != tname:
                print(compare_text(compare(trows, other_rows), other_name))

    print("=== Counter & Ledger Totals (16 dev seeds) ===")
    all_runs = {**loaded_refs, **loaded_targets}
    keys = [
        "won",
        "won_same_day",
        "won_next_day",
        "won_within_3_days",
        "won_ring",
        "late_ring",
        "margin_ring_cents",
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
        "declined_backlog",
        "in_flight_blocked",
        "deadline_close",
        "gig_expired",
        "visit_failed",
    ]
    for name, rows in all_runs.items():
        s = summarize(rows)
        st = stats_summary(rows)
        stats = st["stats"]
        led = st["ledger"]
        late_total = sum(round(r["won"] * (1.0 - r["on_time"])) for r in rows)
        print(f"Run: {name} (margin mean €{s['margin_mean']:,.2f}, min €{s['margin_min']:,.2f}, on-time min {s['on_time_min']:.2%} mean {s['on_time_mean']:.2%}, total late {late_total})")
        for k in keys:
            print(f"  {k:<26}: {stats.get(k, 0):>10}  (mean/wk: {stats.get(k, 0)/16:.2f})")
        for lk in ["revenue", "driver_fee", "late_refund", "failed_visit", "undelivered_penalty"]:
            print(f"  ledger.{lk:<19}: €{led.get(lk, 0)/16:,.2f}/wk")


if __name__ == "__main__":
    main()
