"""Inspect triage telemetry counters and paired comparisons across runs."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from spread_lab.lab import compare, load_results, summarize


def main() -> None:
    if len(sys.argv) > 1:
        paths = [Path(a) for a in sys.argv[1:]]
    else:
        paths = sorted(Path("runs").glob("*"))
        a_smoke = Path("/home/lab/spread-wt/n14-03324-supply-adaptive-fee-open-and-drop-rescue/runs/20261114-034543-fee-drop-smoke5-all180")
        a_dev = Path("/home/lab/spread-wt/n14-03324-supply-adaptive-fee-open-and-drop-rescue/runs/20261114-034812-fee-drop-all180-dev")
        paths = [p for p in [a_smoke, a_dev] if p.exists()] + paths
    for p in paths:
        rows = sorted(load_results(p), key=lambda r: r["seed"])
        s = summarize(rows)
        print(f"=== {p.name} (n={s['n']}, margin_mean=€{s['margin_mean']:,.2f}, min=€{s['margin_min']:,.2f}, on_time_min={s['on_time_min']:.2%}, on_time_mean={s['on_time_mean']:.2%}, SAFE={s['safe']}) ===")
        tot_lost_c = sum(r["stats"].get("fee_lost_cents", 0) for r in rows)
        tot_lost_n = sum(r["stats"].get("fee_lost_n", 0) for r in rows)
        tot_warn_c = sum(r["stats"].get("fee_warned_cents", 0) for r in rows)
        tot_warn_n = sum(r["stats"].get("fee_warned_n", 0) for r in rows)
        tot_rep = sum(r["stats"].get("late_reposts", 0) for r in rows)
        tot_exp = sum(r["stats"].get("gig_expired", 0) for r in rows)
        tot_le2 = sum(r["stats"].get("late_le_2h", 0) for r in rows)
        tot_le24 = sum(r["stats"].get("late_le_24h", 0) for r in rows)
        tot_more = sum(r["stats"].get("late_more", 0) for r in rows)
        n = len(rows)
        rev = sum(r["ledger"].get("revenue", 0) for r in rows) / n
        dfee = sum(r["ledger"].get("driver_fee", 0) for r in rows) / n
        lref = sum(r["ledger"].get("late_refund", 0) for r in rows) / n
        upen = sum(r["ledger"].get("undelivered_penalty", 0) for r in rows) / n
        late_orders = sum(round(r["won"] * (1 - r["on_time"])) for r in rows)
        print(f"  ledger/w: revenue=€{rev:,.2f}  driver_fee=€{dfee:,.2f}  late_refund=€{lref:,.2f}  undeliv_pen=€{upen:,.2f}")
        print(f"  lost bookings: {tot_lost_n} ({tot_lost_n/n:.2f}/w), fee=€{tot_lost_c/100:,.2f} (€{tot_lost_c/100/n:,.2f}/w, €{tot_lost_c/100/max(1,tot_lost_n):,.2f}/booking)")
        print(f"  warned saved bookings: {tot_warn_n} ({tot_warn_n/n:.2f}/w), fee=€{tot_warn_c/100:,.2f} (€{tot_warn_c/100/n:,.2f}/w, €{tot_warn_c/100/max(1,tot_warn_n):,.2f}/booking)")
        print(f"  late_reposts={tot_rep} ({tot_rep/n:.2f}/w)  gig_expired={tot_exp} ({tot_exp/n:.2f}/w)  total_late={late_orders} ({late_orders/n:.2f}/w)")
        print(f"  late tiers: <=2h={tot_le2} ({tot_le2/n:.2f}/w), <=24h={tot_le24} ({tot_le24/n:.2f}/w), >24h={tot_more} ({tot_more/n:.2f}/w)")
        for r in rows:
            st = r["stats"]
            print(
                f"    {r['seed']}: margin=€{r['margin']:,.2f} won={r['won']} on_time={r['on_time']:.4f} "
                f"dfee=€{r['ledger'].get('driver_fee',0):,.2f} lref=€{r['ledger'].get('late_refund',0):,.2f} upen=€{r['ledger'].get('undelivered_penalty',0):,.2f} "
                f"lost={st.get('fee_lost_n',0)}/€{st.get('fee_lost_cents',0)/100:,.2f} "
                f"warn={st.get('fee_warned_n',0)}/€{st.get('fee_warned_cents',0)/100:,.2f} "
                f"rep={st.get('late_reposts',0)} exp={st.get('gig_expired',0)} "
                f"tiers=({st.get('late_le_2h',0)},{st.get('late_le_24h',0)},{st.get('late_more',0)})"
            )
    if len(paths) >= 2:
        from spread_lab.lab import champion_results
        champ = champion_results()
        a_smoke = Path("/home/lab/spread-wt/n14-03324-supply-adaptive-fee-open-and-drop-rescue/runs/20261114-034543-fee-drop-smoke5-all180")
        a_dev = Path("/home/lab/spread-wt/n14-03324-supply-adaptive-fee-open-and-drop-rescue/runs/20261114-034812-fee-drop-all180-dev")
        base_smoke = load_results(a_smoke) if a_smoke.exists() else []
        base_dev = load_results(a_dev) if a_dev.exists() else []
        for cand_p in paths:
            if cand_p in (a_smoke, a_dev):
                continue
            cand = load_results(cand_p)
            base = base_smoke if len(cand) <= 4 else base_dev
            base_name = "A-smoke" if len(cand) <= 4 else "A-dev"
            if base:
                c_a = compare(cand, base)
                print(f"--- Compare {cand_p.name} vs {base_name}: {c_a} ---")
            c_ch = compare(cand, champ)
            print(f"--- Compare {cand_p.name} vs champion: {c_ch} ---")


if __name__ == "__main__":
    main()
