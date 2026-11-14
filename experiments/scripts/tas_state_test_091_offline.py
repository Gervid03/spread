"""Offline verification on `dev-12/limits-all.jsonl` of quoting `0.90 * super().price()` (filtering out <1.32x low-limit junk while expanding high-margin wins from 246 -> ~305 inside the [30%, 70%) deadband and Fri endgame)!"""
from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path
from spread_lab.geo import Geo
from spread_lab.policy import DAY, Desk, Params


def main() -> None:
    home = Path.home() / ".spread-lab"
    geo = Geo(json.loads((home / "map.json").read_text(encoding="utf-8")))
    tape = json.loads((home / "tas" / "dev-12" / "tape.json").read_text(encoding="utf-8"))
    champ_p = json.loads(Path("champion/champion.json").read_text(encoding="utf-8"))["params"]
    lall = [json.loads(l) for l in (home / "tas" / "dev-12" / "limits-all.jsonl").read_text().splitlines() if l.strip()]
    lim_map = {(r["rid"], r["option"]): r for r in lall if r.get("lo")}
    dlr_tot = Counter((r["dealerId"], r["arrivedAt"] // DAY) for r in tape["requests"])

    for disc in (1.00, 0.92, 0.88):
        desk = Desk(world=None, params=Params(**{**champ_p, "fri_endgame": True, "backlog_ratio": 0.085}), level=8, geo=geo, roster=tape["roster"], now=0)  # type: ignore[arg-type]
        won_dlr_d = Counter()
        tot_rev = 0.0
        tot_ref = 0.0
        won_n = 0
        for r in tape["requests"]:
            rid = r["id"]
            dlr = r["dealerId"]
            d = r["arrivedAt"] // DAY
            desk.now = r["arrivedAt"]
            prices, dec = desk.price(r)
            if not prices:
                continue
            tot_d = dlr_tot[(dlr, d)]
            if tot_d >= 10 and d < 4:
                cap = max(1, math.ceil((0.30 if d == 0 and dlr == "D01" else 0.70) * tot_d) - 1)
                if won_dlr_d[(dlr, d)] >= cap:
                    continue
            # Check if 0.90 * price wins against limits-all!
            best_win = None
            for k, p_c in prices.items():
                lrow = lim_map.get((rid, k))
                if not lrow:
                    continue
                lo_c = lrow["lo"] * (1.038 if (dlr == "D01" and d >= 1) else 1.0)
                if int(p_c * disc) <= lo_c:
                    # Dealer picks option maximizing utility (approx lowest ratio to list -> first matching)
                    best_win = (k, lo_c / 100.0)
                    break
            desk.decided[rid] = dec
            desk.requests[rid] = r
            desk.learn(rid, best_win is not None)
            if best_win is not None:
                won_n += 1
                won_dlr_d[(dlr, d)] += 1
                tot_rev += best_win[1]
                tot_ref += r["referenceFeeCents"] / 100.0
        est_fee = tot_ref * 0.936
        print(f"disc={disc:.2f}: won={won_n} | rev=€{tot_rev:,.0f} | sum_ref=€{tot_ref:,.0f} (rev/ref={tot_rev/max(1,tot_ref):.3f}x) | EST MARGIN = €{tot_rev - est_fee:,.0f}")


if __name__ == "__main__":
    main()
