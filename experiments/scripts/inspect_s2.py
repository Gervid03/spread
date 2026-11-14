"""Inspect all counters and ledger lines of Screen 2 (dev-01..dev-04) vs Champion v6 noop."""
from __future__ import annotations

import json
from pathlib import Path


def main() -> None:
    noop = {json.loads(l)["seed"]: json.loads(l) for l in Path("runs/20261114-142131-r4-volume-noop/results.jsonl").read_text().splitlines() if l.strip()}
    s2 = {}
    for p in ["runs/20261114-143338-r4v-s2-full/results.jsonl", "runs/20261114-144014-r4v-s2-full-b/results.jsonl"]:
        for l in Path(p).read_text().splitlines():
            if l.strip():
                r = json.loads(l)
                s2[r["seed"]] = r

    for seed in sorted(noop):
        a, b = noop[seed], s2[seed]
        dm = b["margin"] - a["margin"]
        dw = b["won"] - a["won"]
        print(f"=== {seed}: dMargin={dm:+.2f}, dWon={dw:+d}, OT={a['on_time']*100:.2f}%->{b['on_time']*100:.2f}% ===")
        print(f"  noop ledger: {a['ledger']}")
        print(f"  s2   ledger: {b['ledger']}")
        keys = [
            "quote_quote", "quote_floor", "quote_decline", "declined_backlog",
            "won_same_day", "won_next_day", "won_within_3_days",
            "deadline_close", "gig_dropped", "booked_fee_cents", "booked_ref_cents",
        ]
        print("  deltas:", {k: b["stats"].get(k, 0) - a["stats"].get(k, 0) for k in keys})
        print("  r4v   :", {k: v for k, v in sorted(b["stats"].items()) if k.startswith("r4v_") or k.startswith("refused")})


if __name__ == "__main__":
    main()
