#!/usr/bin/env python3
"""Summarize paired margin, on-time tail, and ret_* counters for return-offer runs."""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def summarize_run(run_dir: Path, champ_by_seed: dict[str, dict]) -> None:
    rows = sorted(load_jsonl(run_dir / "results.jsonl"), key=lambda r: r["seed"])
    deltas = []
    ot_deltas = []
    better = worse = 0
    print()
    print(f"=== {run_dir.name} (n={len(rows)}) ===")
    for r in rows:
        s = r["seed"]
        c = champ_by_seed.get(s)
        st = r.get("stats", {})
        dm = r["margin"] - c["margin"] if c else 0.0
        dot = r["on_time"] - c["on_time"] if c else 0.0
        if c:
            deltas.append(dm)
            ot_deltas.append(dot)
            if dm > 1e-6:
                better += 1
            elif dm < -1e-6:
                worse += 1
        print(
            f"  {s:<8} margin={r['margin']:9.2f} (d={dm:+8.2f}) "
            f"ot={r['on_time']*100:5.1f}% (d={dot*100:+5.2f}%) "
            f"won={r['won']:3d} "
            f"ret_q={st.get('ret_quoted',0):3d} ret_w={st.get('ret_won',0):2d} "
            f"off={st.get('ret_offered',0):2d} acc={st.get('ret_accepted',0):2d} "
            f"dec={st.get('ret_declined',0):2d} exp={st.get('ret_expired',0):2d} "
            f"home={st.get('ret_gone_home',0):2d} late={st.get('ret_late',0):2d} "
            f"ret_eur={st.get('ret_margin_cents',0)/100:+7.2f}"
        )
    if deltas:
        n = len(deltas)
        mean_d = sum(deltas) / n
        se_d = math.sqrt(sum((x - mean_d) ** 2 for x in deltas) / (n * (n - 1))) if n > 1 else 0.0
        t = mean_d / se_d if se_d > 0 else 0.0
        ot_min = min(r["on_time"] for r in rows)
        under_92 = sum(1 for r in rows if r["on_time"] < 0.92)
        print(
            f"  SUMMARY: d_margin={mean_d:+.2f} +/- {se_d:.2f} (t={t:.2f}) "
            f"better/worse={better}/{worse} ot_min={ot_min*100:.2f}% under_92={under_92} "
            f"won_mean={sum(r['won'] for r in rows)/n:.1f}"
        )
    keys = sorted(
        {
            k
            for r in rows
            for k in r.get("stats", {})
            if k.startswith("ret_") or k in ("won", "booked", "deadline_close", "gig_expired", "gig_dropped")
        }
    )
    print("  COUNTERS (sum | mean/wk):")
    for k in keys:
        tot = sum(r.get("stats", {}).get(k, 0) for r in rows)
        print(f"    {k:<26} {tot:>10}  ({tot/len(rows):>8.2f}/wk)")


def main() -> None:
    args = sys.argv[1:]
    champ_path = Path("champion/results/dev-L8.jsonl")
    if len(args) >= 2 and args[0] == "--vs":
        champ_path = Path(args[1])
        args = args[2:]
    champ_rows = load_jsonl(champ_path)
    champ_by_seed = {r["seed"]: r for r in champ_rows}
    patterns = args or ["*c14-ret*"]
    dirs = []
    for pat in patterns:
        dirs.extend(sorted(Path("runs").glob(pat)))
    for d in dirs:
        if (d / "results.jsonl").exists():
            summarize_run(d, champ_by_seed)


if __name__ == "__main__":
    main()
