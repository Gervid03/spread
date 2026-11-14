"""Extracts cars-per-driver-gig and realized tour fee vs solo fee metrics from `runs.jsonl` across all 4 TAS worlds."""
from __future__ import annotations

import json
from spread_lab.env import lab_home

TARGETS = [
    ("dev-12", "tas-routes-elite385-exactfees"),
    ("dev-01", "tas-routes-steered440-exactfees"),
    ("dev-08", "tas-routes-steered440-exactfees"),
    ("dev-07", "tas-routes-safe360-exactfees"),
]


def main() -> None:
    for seed, target_name in TARGETS:
        rows = [json.loads(l) for l in (lab_home() / "tas" / seed / "runs.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
        r = next((x for x in reversed(rows) if x["name"] == target_name), None)
        if not r:
            continue
        st = r.get("stats", {})
        tb = st.get("tour_booked", 0)
        tcb = st.get("tour_cars_booked", 0)
        tf_c = st.get("tour_booked_fee_cents", 0)
        tr_c = st.get("tour_booked_ref_cents", 0)
        tot_b = st.get("booked", 0)
        tot_f_c = st.get("booked_fee_cents", 0)
        tot_r_c = st.get("booked_ref_cents", 0)
        solo_b = max(1, tot_b - tb)
        solo_f_c = max(0, tot_f_c - tf_c)
        solo_r_c = max(1, tot_r_c - tr_c)
        solo_cars = max(1, r["won"] - tcb)

        print(f"=== {seed}: {target_name} ===")
        print(f"  Margin: €{r['margin']:,.2f} | Won: {r['won']} | On-time: {r['on_time']*100:.2f}% | Total driver_fee: €{r['ledger'].get('driver_fee',0):,.2f}")
        print(f"  Tours posted: {st.get('tour_posted',0)} (2c={st.get('tour_posted_c2',0)}, 3c={st.get('tour_posted_c3',0)}, 4c={st.get('tour_posted_c4',0)})")
        print(f"  Tours booked: {tb} ({tcb} cars -> {tcb/max(1,tb):.2f} cars/tour-driver-day!) | Splits: {st.get('tour_split',0)}")
        print(f"  Overall fleet efficiency: {r['won']} cars across {tot_b} total booked gigs = {r['won']/max(1,tot_b):.2f} cars / booked driver-day (vs ~0.97 in Champion v5!)")
        print(f"  Booked TOUR fee: €{tf_c/100/max(1,tcb):.2f}/car ({tf_c/max(1,tr_c):.3f} x ref) vs Booked SOLO fee: €{solo_f_c/100/solo_cars:.2f}/car ({solo_f_c/solo_r_c:.3f} x ref)")


if __name__ == "__main__":
    main()
