"""Print route-network stats and ledger summary from one or more run folders."""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path


def inspect_run(run_dir: Path) -> None:
    rows = [json.loads(line) for line in (run_dir / "results.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    n = len(rows)
    sums = defaultdict(float)
    for r in rows:
        for k, v in r.get("stats", {}).items():
            sums[k] += v
        for k, v in r.get("ledger", {}).items():
            sums[f"acct_{k}"] += v
    worst = min(rows, key=lambda r: r["on_time"])
    s = sums
    acc = s["net_accepted"]
    off = s["net_offers"]
    acc_h = s["net_accepted_home"]
    off_h = s["net_offers_home"]
    acc_nh = acc - acc_h
    off_nh = off - off_h
    ratio = s["net_acc_fee_ratio_sum"] / s["net_acc_fee_ratio_count"] if s["net_acc_fee_ratio_count"] else 0.0
    print(f"=== {run_dir.name} (n={n}) ===")
    print(f"  worst world: {worst['seed']} on_time={worst['on_time']:.2%} margin=€{worst['margin']:,.2f} won={worst['won']}")
    print(f"  acct/wk: rev=€{s['acct_revenue']/n:,.1f} drv_fee=€{s['acct_driver_fee']/n:,.1f} late_ref=€{s['acct_late_refund']/n:,.1f} fail_vis=€{s['acct_failed_visit']/n:,.1f}")
    print(f"  offers/wk: total={off/n:.1f} (acc={acc/n:.1f} [{acc/off:.1%}] dec={s['net_declined']/n:.1f} exp={s['net_expired']/n:.1f})" if off else "  offers/wk: 0")
    if off:
        hr = f"{acc_h / off_h:.1%}" if off_h else "0.0%"
        nhr = f"{acc_nh / off_nh:.1%}" if off_nh else "0.0%"
        print(
            f"    home-bound={off_h/n:.1f} (acc={acc_h/n:.1f} [{hr}]) | "
            f"non-home={off_nh/n:.1f} (acc={acc_nh/n:.1f} [{nhr}]) | "
            f"acc_fee/typ={ratio:.3f}"
        )
    print(
        f"  cands/gig/wk: 0={s['net_cands_0']/n:.1f}, 1={s['net_cands_1']/n:.1f}, 2={s['net_cands_2']/n:.1f}, 3+={s['net_cands_3plus']/n:.1f} | "
        f"offered_gigs={s['net_offered_gigs']/n:.1f} (1={s['net_offered_cands_1']/n:.1f}, 2={s['net_offered_cands_2']/n:.1f}, 3+={s['net_offered_cands_3plus']/n:.1f})"
    )
    print(
        f"  driver_days_2plus/wk: {s['driver_days_2plus']/n:.1f} | "
        f"net_quote/wk: q={s['net_quoted']/n:.1f} (thin={s['net_quoted_thin']/n:.1f}) won={s['net_won']/n:.1f} (thin={s['net_won_thin']/n:.1f}) late={s['net_late']/n:.2f} (thin={s['net_late_thin']/n:.2f}) mrg=€{s['margin_net_cents']/100/n:,.1f} (thin=€{s['margin_net_thin_cents']/100/n:,.1f})"
    )
    print(f"  seed/wk: q={s['seed_quoted']/n:.1f} won={s['seed_won']/n:.1f} late={s['seed_late']/n:.2f} mrg=€{s['margin_seed_cents']/100/n:,.1f}")


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        inspect_run(Path(arg))
