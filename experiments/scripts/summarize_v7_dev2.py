"""Print 16-world mean ledger and counter breakdown of r4-volume-v7-dev2 vs Champion v7."""
from __future__ import annotations

import json
from pathlib import Path
from statistics import mean


def main() -> None:
    champ = {json.loads(l)["seed"]: json.loads(l) for l in Path("champion/results/dev-L8.jsonl").read_text().splitlines() if l.strip()}
    dev2 = {json.loads(l)["seed"]: json.loads(l) for l in Path("runs/20261114-172144-r4-volume-v7-dev2/results.jsonl").read_text().splitlines() if l.strip()}
    seeds = sorted(champ)

    for k in ["revenue", "driver_fee", "late_refund", "undelivered_penalty", "failed_visit", "release_fee", "waiting"]:
        cv = mean(champ[s]["ledger"].get(k, 0.0) for s in seeds)
        nv = mean(dev2[s]["ledger"].get(k, 0.0) for s in seeds)
        print(f"  ledger.{k:<20}: {cv:9.2f} -> {nv:9.2f} ({nv-cv:+8.2f})")

    for k in ["won", "quoted_ext_ring", "quoted_return_hub", "won_ext_ring", "won_return_hub", "r4v_ret_hub_guarded", "r4v_tradein_quoted", "r4v_tradein_won", "lead_car_paired", "lead_car_booked", "cyc_held", "cyc_posted_2", "cyc_posted_3", "tour_booked", "tour_cars_booked", "sup_days_stressed", "sup_fri_surplus_fired", "deadline_close", "gig_dropped"]:
        cv = mean(champ[s]["stats"].get(k, 0) for s in seeds)
        nv = mean(dev2[s]["stats"].get(k, 0) for s in seeds)
        print(f"  stats.{k:<21}: {cv:7.2f} -> {nv:7.2f} ({nv-cv:+7.2f})")


if __name__ == "__main__":
    main()
