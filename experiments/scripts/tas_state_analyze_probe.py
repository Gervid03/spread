"""Inspect exact numbers from tas-state-mechanics-probe.json and current limits-won-apply.jsonl."""
from __future__ import annotations

import json
from collections import Counter, defaultdict

from spread_lab.env import lab_home


def main() -> None:
    d12 = lab_home() / "tas" / "dev-12"
    probe = json.loads((d12 / "tas-state-mechanics-probe.json").read_text(encoding="utf-8"))

    base = probe["tue_decline_4x"]["probed"]
    print("=== EXACT REQUEST-BY-REQUEST TUESDAY PROBE TABLE ===")
    header = f"{'rid':<8} {'dlr':<4} {'opt':<10} {'list':>7} {'0%_lo':>7} {'25%_r':>7} {'50%_r':>7} {'100%_r':>7} {'tr_late_r':>9} {'tr':>3}"
    print(header)
    for rid in sorted(base):
        b = base[rid]
        if not b["lo"]:
            continue
        r25 = probe["tue_win_25"]["probed"][rid]["lo"] / b["lo"]
        r50 = probe["tue_win_50"]["probed"][rid]["lo"] / b["lo"]
        r100 = probe["tue_win_100"]["probed"][rid]["lo"] / b["lo"]
        tl = probe["tue_trust_and_late"]["probed"][rid]
        rtl = tl["lo"] / b["lo"] if tl["lo"] else 0
        print(
            f"{rid:<8} {b['dealer']:<4} {b['option']:<10} {b['list']:>7} {b['lo']:>7} "
            f"{r25:>7.4f} {r50:>7.4f} {r100:>7.4f} {rtl:>9.4f} {tl['trust']:>3}"
        )

    # Check limits-won-apply.jsonl progress from tas-price!
    lwa = d12 / "limits-won-apply.jsonl"
    if lwa.exists() and lwa.stat().st_size > 0:
        lines = [json.loads(line) for line in lwa.read_text(encoding="utf-8").splitlines() if line.strip()]
        print(f"=== limits-won-apply.jsonl progress: {len(lines)} lines (up to minute {lines[-1]['at']}) ===")
        by_day = defaultdict(list)
        for l in lines:
            if l.get("x"):
                by_day[l["day"]].append(l)
        for d in sorted(by_day):
            xs = [x["x"] for x in by_day[d]]
            left = sum(max(0, (x["lo"] or 0) - (x["desk_cents"] or 0)) for x in by_day[d] if x["desk"] == "won") / 100
            print(f"  day {d}: n={len(xs):>3}, median_x={sorted(xs)[len(xs)//2]:.4f}, mean_x={sum(xs)/len(xs):.4f}, left=€{left:,.2f}")

    runs = d12 / "runs.jsonl"
    if runs.exists():
        print("=== latest runs.jsonl lines ===")
        for line in runs.read_text(encoding="utf-8").splitlines()[-5:]:
            r = json.loads(line)
            print(f"  {r['name']}: margin=€{r['margin']:,.2f} won={r['won']} on_time={r['on_time']:.2%} forks={r['forks']}")


if __name__ == "__main__":
    main()
