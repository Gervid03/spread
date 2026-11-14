"""Online tracker replay on `dev-12/limits-all.jsonl` (0 network calls, 1 second).
Checks:
1. Does `comp_steps[d]` (+1 step at <30% yesterday on >=10-req dealers, -1 at >=70%) match the actual day-over-day dealer shift in `limits-all.jsonl`?
2. Replays Champion v6's exact pricing + learning rules vs candidate `r4-limits` rules on `dev-12`'s 1,036 requests using empirical route fees from `reveal-v5` / `fees-layer3`.
"""
from __future__ import annotations

import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from analyze_r4_limits import lane_eff


def main() -> None:
    tas_dir = Path.home() / ".spread-lab" / "tas" / "dev-12"
    rev = json.loads((tas_dir / "reveal-v5.json").read_text(encoding="utf-8"))
    lall = [json.loads(l) for l in (tas_dir / "limits-all.jsonl").read_text().splitlines() if l.strip()]

    lim_by_rid = defaultdict(dict)
    for r in lall:
        if r.get("bound") == "exact" and r.get("lo"):
            lim_by_rid[r["rid"]][r["option"]] = r

    # Compute exact daily dealer counts & v5 win shares on dev-12
    dlr_tot = Counter()
    dlr_won = Counter()
    for item in rev["requests"]:
        req = item["request"]
        d = req["arrivedAt"] // 1440
        dlr = req["dealerId"]
        dlr_tot[(dlr, d)] += 1
        if item["outcome"] == "won":
            dlr_won[(dlr, d)] += 1

    # Compute mean trust-and-lane-adjusted log(x) by (day, dealer) on fastest option!
    dd_vals = defaultdict(list)
    day_overall = defaultdict(list)
    for item in rev["requests"]:
        req = item["request"]
        rid = req["id"]
        fk = req["options"][0]["kind"]
        if fk not in lim_by_rid[rid]:
            continue
        r = lim_by_rid[rid][fk]
        y = math.log(r["x"]) - math.log(1.0 + 0.01 * r["trust"]) - 0.80 * lane_eff(r["pickup"], r["delivery"])
        dd_vals[(r["dealer"], r["day"])].append(y)
        day_overall[r["day"]].append(y)

    day_med = {d: statistics.median(day_overall[d]) for d in range(5)}
    print("Day overall median adj log(x):", {d: round(day_med[d], 4) for d in range(5)})
    print()
    print("--- Busy dealers (>=10 reqs yesterday): Day-over-day shift relative to day median ---")
    step_diffs_hike = []
    step_diffs_flat = []
    for d in range(1, 5):
        for dlr in sorted({k[0] for k in dlr_tot}):
            n_prev = dlr_tot[(dlr, d - 1)]
            if n_prev >= 10 and dd_vals[(dlr, d - 1)] and dd_vals[(dlr, d)]:
                sh_prev = dlr_won[(dlr, d - 1)] / n_prev
                rel_prev = statistics.mean(dd_vals[(dlr, d - 1)]) - day_med[d - 1]
                rel_curr = statistics.mean(dd_vals[(dlr, d)]) - day_med[d]
                delta = rel_curr - rel_prev
                if sh_prev < 0.30:
                    step_diffs_hike.append(delta)
                elif sh_prev < 0.70:
                    step_diffs_flat.append(delta)
                print(
                    f"  d{d-1}->d{d} {dlr}: prev_won={dlr_won[(dlr,d-1)]:>2}/{n_prev:<2} ({sh_prev*100:4.0f}%) | "
                    f"rel_prev={rel_prev:+.4f} -> rel_curr={rel_curr:+.4f} | delta={delta:+.4f} ({math.exp(delta):.4f}x)"
                )

    if step_diffs_hike and step_diffs_flat:
        print()
        print(f"Mean delta after <30% share (n={len(step_diffs_hike)}): {statistics.mean(step_diffs_hike):+.4f} ({math.exp(statistics.mean(step_diffs_hike)):.4f}x)")
        print(f"Mean delta after 30-69% share (n={len(step_diffs_flat)}): {statistics.mean(step_diffs_flat):+.4f} ({math.exp(statistics.mean(step_diffs_flat)):.4f}x)")


if __name__ == "__main__":
    main()
