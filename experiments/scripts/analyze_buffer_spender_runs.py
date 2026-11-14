"""Summarize runs and mechanism counters for c4 (buffer spender)."""
from __future__ import annotations

import json
import math
import statistics as st
import sys
from pathlib import Path


def main() -> None:
    champ = {json.loads(line)["seed"]: json.loads(line) for line in open("champion/results/dev-L8.jsonl")}
    champ_min_seed = min(champ.values(), key=lambda r: r["on_time"])
    print(
        f"Champion dev (16): mean €{st.mean(r['margin'] for r in champ.values()):,.2f}, "
        f"won {st.mean(r['won'] for r in champ.values()):.1f}/w, "
        f"mean OT {st.mean(r['on_time'] for r in champ.values()):.4%}, "
        f"worst OT {champ_min_seed['on_time']:.4%} ({champ_min_seed['seed']}), "
        f"min margin €{min(r['margin'] for r in champ.values()):,.2f}"
    )
    print("=" * 120)

    for run_dir_str in sys.argv[1:]:
        run_dir = Path(run_dir_str)
        summary = json.loads((run_dir / "summary.json").read_text())
        rows = [json.loads(line) for line in open(run_dir / "results.jsonl")]
        worst = min(rows, key=lambda r: r["on_time"])
        under92 = sum(1 for r in rows if r["on_time"] < 0.92)
        diffs = [r["margin"] - champ[r["seed"]]["margin"] for r in rows]
        ot_diffs = [r["on_time"] - champ[r["seed"]]["on_time"] for r in rows]
        n = len(rows)
        dm = st.mean(diffs)
        se = st.stdev(diffs) / math.sqrt(n) if n > 1 else 0.0
        t = dm / se if se > 0 else 0.0
        wins = sum(1 for d in diffs if d > 1e-9)
        losses = sum(1 for d in diffs if d < -1e-9)

        bq = st.mean(r["stats"].get("buf_quoted", 0) for r in rows)
        bw = st.mean(r["stats"].get("buf_won", 0) for r in rows)
        bl = st.mean(r["stats"].get("buf_late", 0) for r in rows)
        bm = st.mean(r["stats"].get("buf_margin_cents", 0) / 100.0 for r in rows)
        nbw = st.mean(r["stats"].get("nonbuf_won", 0) for r in rows)
        nbl = st.mean(r["stats"].get("nonbuf_late", 0) for r in rows)
        bmin = st.mean(r["stats"].get("buf_open_min", 0) for r in rows)
        bbusy = st.mean(r["stats"].get("buf_open_busy_min", 0) for r in rows)
        eot = st.mean(r["stats"].get("end_on_time", r["on_time"]) for r in rows)
        tot_bw = sum(r["stats"].get("buf_won", 0) for r in rows)
        tot_bl = sum(r["stats"].get("buf_late", 0) for r in rows)
        tot_nbw = sum(r["stats"].get("nonbuf_won", 0) for r in rows)
        tot_nbl = sum(r["stats"].get("nonbuf_late", 0) for r in rows)

        print(f"RUN: {run_dir.name} (n={n}, safe={summary['safe']})")
        print(
            f"  Worst OT: {worst['on_time']:.2%} ({worst['seed']}) | <92%: {under92}/{n} | "
            f"Won/wk: {summary['won_mean']:.1f} (ch {st.mean(champ[r['seed']]['won'] for r in rows):.1f}) | "
            f"Mean OT: {summary['on_time_mean']:.2%} (Δ {st.mean(ot_diffs)*100:+.2f}%)"
        )
        print(
            f"  Margin: mean €{summary['margin_mean']:,.2f} (min €{summary['margin_min']:,.2f}) | "
            f"Δmargin: €{dm:+.2f} ± {se:.2f} (t={t:.2f}, W/L={wins}/{losses})"
        )
        print(
            f"  Counters/wk: buf_quoted={bq:.1f}, buf_won={bw:.1f}, buf_late={bl:.2f} "
            f"({tot_bl}/{tot_bw} = {tot_bl/max(1,tot_bw):.2%}), buf_margin=€{bm:,.2f} "
            f"(€{bm/max(1e-9,bw):.2f}/win), open_min={bmin:.0f} (busy {bbusy:.0f}), end_on_time={eot:.4f}"
        )
        print(
            f"  Non-buf/wk:  nonbuf_won={nbw:.1f}, nonbuf_late={nbl:.2f} "
            f"({tot_nbl}/{tot_nbw} = {tot_nbl/max(1,tot_nbw):.2%})"
        )
        if n == 16:
            print("  Tail worlds (champion's 5 lowest on-time worlds):")
            tail_seeds = sorted(rows, key=lambda r: champ[r["seed"]]["on_time"])[:5]
            for r in tail_seeds:
                c = champ[r["seed"]]
                s = r["stats"]
                c_late = round(c["won"] * (1.0 - c["on_time"]))
                r_late = round(r["won"] * (1.0 - r["on_time"]))
                print(
                    f"    {r['seed']}: ch OT {c['on_time']:.2%} ({c_late}/{c['won']} late, €{c['margin']:,.2f}) -> "
                    f"OT {r['on_time']:.2%} ({r_late}/{r['won']} late: buf {s.get('buf_late',0)}/{s.get('buf_won',0)}, "
                    f"nonbuf {s.get('nonbuf_late',0)}/{s.get('nonbuf_won',0)}, open_busy={s.get('buf_open_busy_min',0)}m, "
                    f"€{r['margin']:,.2f}, Δ€{r['margin']-c['margin']:+.2f})"
                )


if __name__ == "__main__":
    main()
