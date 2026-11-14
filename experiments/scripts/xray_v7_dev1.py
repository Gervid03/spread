"""Per-seed autopsy of r4-volume-v7-dev1 vs Champion v7 (dev-L8.jsonl)."""
from __future__ import annotations

import json
from pathlib import Path


def main() -> None:
    champ = {json.loads(l)["seed"]: json.loads(l) for l in Path("champion/results/dev-L8.jsonl").read_text().splitlines() if l.strip()}
    dev1 = {json.loads(l)["seed"]: json.loads(l) for l in Path("runs/20261114-165355-r4-volume-v7-dev1/results.jsonl").read_text().splitlines() if l.strip()}

    print(f"{'seed':<7} {'dMargin':>8} {'dWon':>5} {'OT_c':>6} {'OT_n':>6} {'dRev':>7} {'dFee':>7} {'retHub':>7} {'spWon':>5} {'clWon':>5} {'tiWon':>5} {'lcBook':>8} {'cyc2':>7} {'vf':>5}")
    for s in sorted(champ):
        c, n = champ[s], dev1[s]
        dm = n["margin"] - c["margin"]
        dw = n["won"] - c["won"]
        drev = n["ledger"].get("revenue", 0) - c["ledger"].get("revenue", 0)
        dfee = n["ledger"].get("driver_fee", 0) - c["ledger"].get("driver_fee", 0)
        st, cst = n["stats"], c["stats"]
        print(
            f"{s:<7} {dm:+8.2f} {dw:+5d} {c['on_time']*100:5.1f}% {n['on_time']*100:5.1f}% "
            f"{drev:+7.0f} {dfee:+7.0f} "
            f"{cst.get('won_return_hub',0):2d}->{st.get('won_return_hub',0):2d} "
            f"{st.get('r4v_sponsor_won',0):5d} {st.get('r4v_return_closing_won',0):5d} "
            f"{st.get('r4v_tradein_won',0):5d} "
            f"{cst.get('lead_car_booked',0):3d}->{st.get('lead_car_booked',0):3d} "
            f"{cst.get('cyc_posted_2',0):2d}->{st.get('cyc_posted_2',0):2d} "
            f"{cst.get('visit_failed',0):1d}->{st.get('visit_failed',0):1d}"
        )


if __name__ == "__main__":
    main()
