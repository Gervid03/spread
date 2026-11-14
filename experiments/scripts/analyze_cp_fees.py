"""Compare a cp-fees run folder against the champion on ledger lines, on-time tail, and mechanism counters."""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def main() -> None:
    run_dir = Path(sys.argv[1])
    champ_rows = {}
    for fn in ("dev-L8.jsonl", "holdout-L8.jsonl"):
        p = REPO / "champion" / "results" / fn
        if p.exists():
            for line in p.read_text().splitlines():
                if line.strip():
                    r = json.loads(line)
                    champ_rows[r["seed"]] = r

    rows = [json.loads(line) for line in (run_dir / "results.jsonl").read_text().splitlines() if line.strip()]
    rows.sort(key=lambda r: r["seed"])

    tot_dm = tot_dr = tot_df = 0.0
    for r in rows:
        sd = r["seed"]
        c = champ_rows.get(sd)
        s = r["stats"]
        bf = s.get("booked_fee_cents", 0) / max(1, s.get("booked_ref_cents", 1))
        if c:
            dm = r["margin"] - c["margin"]
            dr = r["ledger"].get("revenue", 0) - c["ledger"].get("revenue", 0)
            df = r["ledger"].get("driver_fee", 0) - c["ledger"].get("driver_fee", 0)
            dlr = r["ledger"].get("late_refund", 0) - c["ledger"].get("late_refund", 0)
            tot_dm += dm
            tot_dr += dr
            tot_df += df
            print(
                f"{sd}: margin €{r['margin']:>9,.2f} ({dm:+8.2f}) | rev {dr:+8.1f} | fee {df:+8.1f} | lateref {dlr:+6.1f} | "
                f"ot {r['on_time']:.2%} (vs {c['on_time']:.2%}, {r['on_time']-c['on_time']:+.2%}) | won {r['won']} (vs {c['won']}) | bk_mult {bf:.3f}x"
            )
        else:
            print(f"{sd}: margin €{r['margin']:>9,.2f} | fee €{r['ledger'].get('driver_fee',0):,.1f} | ot {r['on_time']:.2%} | won {r['won']} | bk_mult {bf:.3f}x")
        keys = [k for k in sorted(s) if any(w in k for w in ("view_offer", "drop_repr", "urgent_cl", "lost_on", "late_repr", "gig_dropped", "deadline_close", "fee_warned", "fee_lost"))]
        print("   ", {k: s[k] for k in keys})

    if champ_rows and all(r["seed"] in champ_rows for r in rows):
        n = len(rows)
        print(f"MEAN ({n} seeds): d_margin €{tot_dm/n:+,.2f} | d_rev €{tot_dr/n:+,.2f} | d_driver_fee €{tot_df/n:+,.2f}")


if __name__ == "__main__":
    main()
