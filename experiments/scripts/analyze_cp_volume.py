"""Compare telemetry counters and ledger lines between two run folders (or champion/results/dev-L8.jsonl)."""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path


def load_rows(p: str) -> list[dict]:
    path = Path(p)
    if path.is_dir():
        path = path / "results.jsonl"
    return [json.loads(line) for line in open(path, encoding="utf-8")]


def agg(rows: list[dict]) -> tuple[Counter, Counter]:
    s, a = Counter(), Counter()
    for r in rows:
        for k, v in r.get("stats", {}).items():
            if isinstance(v, (int, float)):
                s[k] += v
        for k, v in r.get("account", {}).items():
            if isinstance(v, (int, float)):
                a[k] += v
    return s, a


def main() -> None:
    base_rows = load_rows(sys.argv[1])
    cand_rows = load_rows(sys.argv[2])
    n = len(cand_rows)
    sb, ab = agg(base_rows)
    sc, ac = agg(cand_rows)
    keys = [
        "won", "won_same_day", "won_next_day", "won_within_3_days", "won_mon2",
        "quoted_trade_in", "won_trade_in", "late_trade_in", "margin_trade_in_cents", "dropped_trade_in_drive",
        "quoted_ext_ring", "quoted_return_hub", "won_ext_ring", "won_return_hub", "late_ext_ring", "margin_ext_ring_cents",
        "lead_car_paired", "lead_car_booked", "lead_car_split",
        "declined_backlog", "deadline_close", "gig_expired", "gig_dropped",
    ]
    print(f"{'Counter':26s} {'Base/wk':>10s} {'Cand/wk':>10s} {'Delta/wk':>10s}")
    for k in keys:
        vb, vc = sb[k] / n, sc[k] / n
        print(f"{k:26s} {vb:10.2f} {vc:10.2f} {vc - vb:+10.2f}")
    print("=== LEDGER (EUR/wk) ===")
    for k in sorted(set(ab) | set(ac)):
        vb, vc = ab[k] / (100 * n), ac[k] / (100 * n)
        print(f"{k:26s} {vb:10.2f} {vc:10.2f} {vc - vb:+10.2f}")
    print("=== PER SEED ===")
    bmap = {r["seed"]: r for r in base_rows}
    cmap = {r["seed"]: r for r in cand_rows}
    for s in sorted(cmap):
        b, c = bmap[s], cmap[s]
        dm = c["margin"] - b["margin"]
        st = c["stats"]
        ti_w, ti_l, ti_m = st.get("won_trade_in", 0), st.get("late_trade_in", 0), st.get("margin_trade_in_cents", 0) / 100
        ex_w, ex_l, ex_m = st.get("won_ext_ring", 0), st.get("late_ext_ring", 0), st.get("margin_ext_ring_cents", 0) / 100
        pr = st.get("lead_car_booked", 0)
        print(f"{s:7s} dm={dm:+8.2f}  ot={b['on_time']:.3f}->{c['on_time']:.3f}  won={b['won']:3d}->{c['won']:3d}  ti={ti_w:2d}({ti_l}L,{ti_m:+5.0f})  ext={ex_w:2d}({ex_l}L,{ex_m:+5.0f})  pair={pr:2d}")


if __name__ == "__main__":
    main()
