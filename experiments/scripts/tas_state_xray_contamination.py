"""Check cross-dealer global mult contamination (Outage + D01 trust=25 pricing out low-trust dealers) across the 4 TAS seeds."""
from __future__ import annotations

import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path


def main() -> None:
    home = Path.home() / ".spread-lab"
    for seed in ("dev-12", "dev-01", "dev-08", "dev-07"):
        rev = json.loads((home / "tas" / seed / "reveal-v5.json").read_text(encoding="utf-8"))
        dlr_quoted = Counter()
        dlr_won = Counter()
        dlr_qratios = defaultdict(list)
        for rr in rev["requests"]:
            req = rr["request"]
            dlr = req["dealerId"]
            q = rr.get("quote") or {}
            prices = q["prices"] if "prices" in q else q
            if not prices or not isinstance(prices, dict):
                continue
            k = next(iter(prices))
            lp = next(o["listPriceCents"] for o in req["options"] if o["kind"] == k)
            ratio = prices[k] / lp
            if ratio >= 3.5:
                continue  # declined
            dlr_quoted[dlr] += 1
            dlr_qratios[dlr].append(ratio)
            if rr.get("outcome") == "won":
                dlr_won[dlr] += 1

        print(f"=== {seed}: non-declined quotes win rate by dealer ===")
        top_dlrs = [d for d, _ in dlr_quoted.most_common(6)]
        for d in top_dlrs:
            q_n = dlr_quoted[d]
            w_n = dlr_won[d]
            med_q = statistics.median(dlr_qratios[d])
            print(f"  {d}: won {w_n:>3}/{q_n:<3} ({w_n/max(1,q_n)*100:5.1f}%) | median quote = {med_q:.3f}x")
        other_q = sum(v for k, v in dlr_quoted.items() if k not in top_dlrs[:2])
        other_w = sum(dlr_won[k] for k in dlr_quoted if k not in top_dlrs[:2])
        print(f"  ALL EXCEPT TOP-2 ({top_dlrs[:2]}): won {other_w}/{other_q} ({other_w/max(1,other_q)*100:.1f}%)")


if __name__ == "__main__":
    main()
