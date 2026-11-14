"""Per-seed autopsy of r4-volume-dev1 (16 seeds) vs Champion v6 dev-L8.jsonl."""
from __future__ import annotations

import json
from pathlib import Path
from statistics import mean


def main() -> None:
    champ = {json.loads(l)["seed"]: json.loads(l) for l in Path("champion/results/dev-L8.jsonl").read_text().splitlines() if l.strip()}
    dev1 = {json.loads(l)["seed"]: json.loads(l) for l in Path("runs/20261114-150812-r4-volume-dev1/results.jsonl").read_text().splitlines() if l.strip()}

    print(f"{'seed':<7} {'dMargin':>8} {'dWon':>5} {'OT_c':>6} {'OT_n':>6} {'dRev':>7} {'dFee':>7} {'dLate':>6} {'dPen':>6} {'tBook':>5} {'tCars':>5} {'tSplit':>6} {'tDrop':>5} {'tiWon':>5} {'spWon':>5}")
    for s in sorted(champ):
        c, n = champ[s], dev1[s]
        dm = n["margin"] - c["margin"]
        dw = n["won"] - c["won"]
        drev = n["ledger"].get("revenue", 0) - c["ledger"].get("revenue", 0)
        dfee = n["ledger"].get("driver_fee", 0) - c["ledger"].get("driver_fee", 0)
        dlate = n["ledger"].get("late_refund", 0) - c["ledger"].get("late_refund", 0)
        dpen = n["ledger"].get("undelivered_penalty", 0) - c["ledger"].get("undelivered_penalty", 0)
        st = n["stats"]
        print(
            f"{s:<7} {dm:+8.2f} {dw:+5d} {c['on_time']*100:5.1f}% {n['on_time']*100:5.1f}% "
            f"{drev:+7.0f} {dfee:+7.0f} {dlate:+6.0f} {dpen:+6.0f} "
            f"{st.get('r4v_tour_booked',0):5d} {st.get('r4v_tour_cars_booked',0):5d} {st.get('r4v_tour_split',0):6d} "
            f"{st.get('r4v_tour_dropped',0):5d} {st.get('r4v_tradein_won',0):5d} {st.get('r4v_sponsor_won',0):5d}"
        )

    print()
    print("=== WORST 4 SEEDS DETAIL ===")
    for s in sorted(champ, key=lambda x: dev1[x]["margin"] - champ[x]["margin"])[:5]:
        c, n = champ[s], dev1[s]
        print(f"--- {s} (dMargin={n['margin']-c['margin']:+.2f}, dWon={n['won']-c['won']:+d}) ---")
        print("  champ ledger:", c["ledger"])
        print("  dev1  ledger:", n["ledger"])
        for k in ["won_same_day", "won_next_day", "won_within_3_days", "deadline_close", "gig_dropped", "late_repriced", "declined_backlog", "r4v_staged", "r4v_stage_solo", "r4v_tour_posted", "r4v_tour_booked", "r4v_shuttle_booked", "r4v_tour_dropped", "r4v_tradein_quoted", "r4v_tradein_won", "visit_failed"]:
            print(f"    {k:<22}: champ={c['stats'].get(k,0):4d}  dev1={n['stats'].get(k,0):4d}")


if __name__ == "__main__":
    main()
