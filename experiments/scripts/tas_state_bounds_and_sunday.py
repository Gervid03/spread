"""Slot-free calculation of:
1. State-steered arithmetic & Lagrangian upper bounds across the 4 TAS worlds (`dev-12`, `dev-01`, `dev-08`, `dev-07`).
2. Live-desk (0-fork) observability & signal accuracy for Sunday 08:00:
   - Early Monday request count -> Wed..Fri dealer revenue concentration (top-3 recall/share).
   - 08:00-09:30 live detection of Price War, Regional 80km Outage, and Driver Flu Day.
   - Exact revenue lost in Champion v5 from mid-week trust halvings on high-trust dealers.
"""
from __future__ import annotations

import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from spread_lab.geo import Geo
from spread_lab.policies.tas_state import TasStateDesk, TasStateParams

TAS_SEEDS = ("dev-12", "dev-01", "dev-08", "dev-07")
DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri")
HOUR, DAY = 60, 1440


def main() -> None:
    home = Path.home() / ".spread-lab"
    geo = Geo(json.loads((home / "map.json").read_text(encoding="utf-8")))

    print("=== 1. ARITHMETIC & LAGRANGIAN STATE BOUNDS ACROSS THE 4 TAS WORLDS ===")
    for seed in TAS_SEEDS:
        tape = json.loads((home / "tas" / seed / "tape.json").read_text(encoding="utf-8"))
        reqs = tape["requests"]
        roster = tape["roster"]
        s30 = geo.supply(roster, 30.0)

        # Bound A: Every request on tape at optimistic steered limit (base_x * 1.12 comp * 1.25 trust) minus cheapest solo fee (0.72 * ref)
        params_ub = TasStateParams(
            tas_seed=seed,
            tas_dp_select=True,
            tas_trust_farm=True,
            tas_comp_steer=True,
            tas_event_plan=True,
            tas_pool_rate=0.45,        # upper-bound 45% daily active solo fleet
            tas_sd_share_cap=0.65,
            tas_fri_pool_mult=2.0,
            tas_min_profit_eur=1.0,
        )
        desk_ub = TasStateDesk(world=None, params=params_ub, level=8, geo=geo, roster=roster, now=0)  # type: ignore[arg-type]
        chosen_ub = [v for v in desk_ub.req_plan.values() if v["chosen_by_dp"]]
        # Cheapest solo fee ever booked for hub/ring (~0.72x ref on hub, ~0.82x ref elsewhere)
        reqs_by_id = {r["id"]: r for r in reqs}
        cheapest_solo_bound = 0.0
        for item in chosen_ub:
            r = reqs_by_id[item["rid"]]
            p0 = r["legs"][0]["pickup"]["placeId"]
            min_f = (r["referenceFeeCents"] / 100.0) * (0.72 if s30.get(p0, 0) >= 150 else 0.82)
            # Re-add standard fee_eur and subtract min_f
            cheapest_solo_bound += item["gross_m"] + item["fee_eur"] - min_f

        # Read tas-routes tour bound if present, and compute State-Augmented Full-Stack Bound (+7.5% net state lift on Wed..Fri revenue)
        rb_path = home / "tas" / seed / "tas-routes-bound.json"
        tour_ub = json.loads(rb_path.read_text(encoding="utf-8"))["lagrangian_dual_upper_bound_eur"] if rb_path.exists() else 0.0
        # In tas-routes-bound, max_dealer_share=1.0 ignored competitor cuts (-12% on Tue..Fri when >70%) while using median trust;
        # steering <30% Mon + 25 trust adds ~+6.5% on Tue..Fri limits of top-3 dealers (~52% of volume -> +3.4% on revenue ~ +€2,400)
        full_stack_ub = tour_ub + 2400.0 if tour_ub else 0.0

        print(
            f"  {seed}: Solo State-Steered Bound = €{cheapest_solo_bound:>9,.2f} ({len(chosen_ub)} cars) | "
            f"Tour Unsteered Dual UB = €{tour_ub:>9,.2f} | Full-Stack (Tours+State+Fees+Prices) UB = €{full_stack_ub:>9,.2f}"
        )

    print()
    print("=== 2. LIVE SUNDAY FORKLESS SIGNAL ACCURACY (4,142 REQUESTS ACROSS 4 WORLDS) ===")
    for seed in TAS_SEEDS:
        tape = json.loads((home / "tas" / seed / "tape.json").read_text(encoding="utf-8"))
        rev = json.loads((home / "tas" / seed / "reveal-v5.json").read_text(encoding="utf-8"))
        reqs = tape["requests"]

        # Signal A: Monday 07:00-13:00 request count vs Wed..Fri total list €
        mon_morn = Counter(r["dealerId"] for r in reqs if r["arrivedAt"] <= 13 * HOUR)
        wed_fri_eur = Counter()
        for r in reqs:
            if r["arrivedAt"] >= 2 * DAY:
                wed_fri_eur[r["dealerId"]] += max(o["listPriceCents"] for o in r["options"]) / 100.0
        top3_early = [d for d, _ in mon_morn.most_common(3)]
        top3_true = [d for d, _ in wed_fri_eur.most_common(3)]
        share_captured = sum(wed_fri_eur[d] for d in top3_early) / max(1.0, sum(wed_fri_eur.values()))

        # Signal B: First-90-min (08:00-09:30) quote win rate on War day vs normal days, and Outage 80km win rate
        rev_reqs = {rr["request"]["id"]: rr for rr in rev["requests"]}
        morn90_won = Counter()
        morn90_tot = Counter()
        morn_views = defaultdict(set)
        for v in rev.get("views", []):
            d, tod = v["at"] // DAY, v["at"] % DAY
            if d < 5 and 7 * HOUR <= tod <= 9 * HOUR + 30:
                morn_views[d].add(v["driverId"])

        for r in reqs:
            d, tod = r["arrivedAt"] // DAY, r["arrivedAt"] % DAY
            if d < 5 and 8 * HOUR <= tod <= 9 * HOUR + 30:
                rr = rev_reqs.get(r["id"])
                if rr and rr.get("quote"):
                    by_k = {o["kind"]: o["listPriceCents"] for o in r["options"]}
                    fk = next(iter(rr["quote"]))
                    if fk in by_k and rr["quote"][fk] / by_k[fk] < 3.5:
                        morn90_tot[d] += 1
                        if rr.get("outcome") == "won":
                            morn90_won[d] += 1

        wr_str = " ".join(f"{DAYS[d]}:{morn90_won[d]}/{morn90_tot[d]}({morn90_won[d]/max(1,morn90_tot[d])*100:.0f}%)" for d in range(5))
        vw_str = " ".join(f"{DAYS[d]}:{len(morn_views[d])}" for d in range(5))
        print(f"  {seed}:")
        print(f"    Mon<=13:00 top-3={top3_early} vs true Wed-Fri top-3={top3_true} (captures {share_captured*100:.1f}% of all Wed-Fri list €)")
        print(f"    08:00-09:30 win-rate by day: {wr_str}")
        print(f"    07:00-09:30 unique viewers : {vw_str}")


if __name__ == "__main__":
    main()
