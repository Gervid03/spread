"""Analyze hitch counters, ledger breakdown, and worst-world stats across run folders."""
from __future__ import annotations

import json
import sys
from pathlib import Path


def inspect_run(run_dir: Path) -> None:
    rows = [json.loads(line) for line in open(run_dir / "results.jsonl", encoding="utf-8")]
    rows.sort(key=lambda x: x["seed"])
    print(f"=== {run_dir.name} ({len(rows)} worlds) ===")
    worst_ot = min(rows, key=lambda r: r["on_time"])
    worst_mg = min(rows, key=lambda r: r["margin"])
    under92 = sum(1 for r in rows if r["on_time"] < 0.92)
    print(
        f"Worst on-time: {worst_ot['seed']} ({worst_ot['on_time']:.2%}, margin €{worst_ot['margin']:,.2f}, won {worst_ot['won']}); "
        f"Worst margin: {worst_mg['seed']} (€{worst_mg['margin']:,.2f}, on-time {worst_mg['on_time']:.2%}); "
        f"under 92%: {under92}/{len(rows)}"
    )
    for r in rows:
        s = r["stats"]
        ld = r["ledger"]
        paid_f = s.get("hitch_paid_fee_cents", 0) / 100.0
        open_f = s.get("hitch_paid_single_open_cents", 0) / 100.0
        ref_f = s.get("hitch_paid_single_ref_cents", 0) / 100.0
        ratio_open = paid_f / open_f if open_f else 0.0
        ratio_ref = paid_f / ref_f if ref_f else 0.0
        refused = {k: v for k, v in s.items() if k.startswith("refused")}
        print(
            f"  {r['seed']}: margin=€{r['margin']:>9,.2f} won={r['won']:>3} ot={r['on_time']:.2%} req={r.get('requests',0):>4} "
            f"| posted={s.get('hitch_posted',0):>3} (thinB={s.get('hitch_posted_thin_b',0):>2}, rt={s.get('hitch_posted_rt',0):>2}) "
            f"booked={s.get('hitch_booked',0):>3} (thinB={s.get('hitch_booked_thin_b',0):>2}, rt={s.get('hitch_booked_rt',0):>2}) "
            f"split={s.get('hitch_split',0):>3} (pat={s.get('hitch_split_patience',0)}, wrn={s.get('hitch_split_warn',0)}, drp={s.get('hitch_split_drop',0)}) "
            f"paid={s.get('hitch_paid_gigs',0):>2} fee=€{paid_f:>6,.0f}/€{open_f:>6,.0f} ({ratio_open:.2f}x open, {ratio_ref:.2f}x ref) "
            f"late_pair={s.get('hitch_late',0)}/{s.get('hitch_late_booked',0)} "
            f"hq_q={s.get('hitch_quote_quoted',0)} hq_w={s.get('hitch_quote_won',0)} hq_p={s.get('hitch_quote_paired',0)} hq_late={s.get('hitch_quote_late',0)} "
            f"warn={s.get('deadline_close',0)} exp={s.get('gig_expired',0)} ref={refused}"
        )

    n = len(rows)
    tot_post = sum(r["stats"].get("hitch_posted", 0) for r in rows)
    tot_book = sum(r["stats"].get("hitch_booked", 0) for r in rows)
    tot_split = sum(r["stats"].get("hitch_split", 0) for r in rows)
    tot_paid = sum(r["stats"].get("hitch_paid_gigs", 0) for r in rows)
    tot_pf = sum(r["stats"].get("hitch_paid_fee_cents", 0) for r in rows) / 100.0
    tot_of = sum(r["stats"].get("hitch_paid_single_open_cents", 0) for r in rows) / 100.0
    tot_rf = sum(r["stats"].get("hitch_paid_single_ref_cents", 0) for r in rows) / 100.0
    tot_hqq = sum(r["stats"].get("hitch_quote_quoted", 0) for r in rows)
    tot_hqw = sum(r["stats"].get("hitch_quote_won", 0) for r in rows)
    tot_hqp = sum(r["stats"].get("hitch_quote_paired", 0) for r in rows)
    tot_hql = sum(r["stats"].get("hitch_quote_late", 0) for r in rows)
    tot_hl = sum(r["stats"].get("hitch_late", 0) for r in rows)
    tot_hlb = sum(r["stats"].get("hitch_late_booked", 0) for r in rows)
    rev = sum(r["ledger"].get("revenue", 0) for r in rows) / 100.0 / n
    dfee = sum(r["ledger"].get("driver_fee", 0) for r in rows) / 100.0 / n
    lref = sum(r["ledger"].get("late_refund", 0) for r in rows) / 100.0 / n
    print(
        f"MEAN/WK: won={sum(r['won'] for r in rows)/n:.1f} margin=€{sum(r['margin'] for r in rows)/n:,.2f} "
        f"(rev=€{rev:,.1f} dfee=€{dfee:,.1f} lref=€{lref:,.1f}) | "
        f"posted={tot_post/n:.1f} booked={tot_book/n:.1f} split={tot_split/n:.1f} paid={tot_paid/n:.1f} "
        f"pair_fee=€{tot_pf/n:,.1f} vs 2x_open=€{tot_of/n:,.1f} ({tot_pf/tot_of if tot_of else 0:.3f}x) vs 2x_ref=€{tot_rf/n:,.1f} ({tot_pf/tot_rf if tot_rf else 0:.3f}x) | "
        f"hq_quoted={tot_hqq/n:.1f} hq_won={tot_hqw/n:.1f} hq_paired={tot_hqp/n:.1f} hq_late={tot_hql} | "
        f"late_ever={tot_hl} late_booked={tot_hlb}"
    )


def main() -> None:
    for arg in sys.argv[1:]:
        inspect_run(Path(arg))


if __name__ == "__main__":
    main()
