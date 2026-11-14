"""Inspect exact counters and ledger deltas of r4v-s1-tours vs r4-volume-noop on smoke."""
from __future__ import annotations

import json
from pathlib import Path


def main() -> None:
    noop = {json.loads(l)["seed"]: json.loads(l) for l in Path("runs/20261114-142131-r4-volume-noop/results.jsonl").read_text().splitlines() if l.strip()}
    s1 = {json.loads(l)["seed"]: json.loads(l) for l in Path("runs/20261114-142848-r4v-s1-tours/results.jsonl").read_text().splitlines() if l.strip()}
    for seed in sorted(noop):
        a, b = noop[seed], s1[seed]
        print(f"=== {seed} (keys={sorted(a.keys())}) ===")
        acct_k = "ledger" if "ledger" in a else "by_kind"
        print(f"  noop: margin={a['margin']:.2f} won={a['won']} ot={a['on_time']*100:.2f}% req={a.get('requests')} acct={a.get(acct_k)}")
        print(f"  s1  : margin={b['margin']:.2f} won={b['won']} ot={b['on_time']*100:.2f}% req={b.get('requests')} acct={b.get(acct_k)}")
        r4v_stats = {k: v for k, v in sorted(b["stats"].items()) if k.startswith("r4v_") or k.startswith("refused") or k in ("booked_fee_cents", "booked_ref_cents", "deadline_close", "gig_dropped", "declined_backlog", "posts")}
        noop_stats = {k: a["stats"].get(k, 0) for k in ("booked_fee_cents", "booked_ref_cents", "deadline_close", "gig_dropped", "declined_backlog", "lead_car_paired", "lead_car_booked", "posts")}
        print(f"  noop_stats: {noop_stats}")
        print(f"  s1_stats  : {r4v_stats}")


if __name__ == "__main__":
    main()
