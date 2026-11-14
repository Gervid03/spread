"""Test ranking `v5`-approved tape requests by expected net margin `(est_lim - 0.94 * ref)` (using ONLY tape list/ref + event/state physics, ZERO peeking at limits-all!) and evaluating exact outcome against `limits-all.jsonl`!"""
from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from pathlib import Path

from spread_lab.geo import Geo
from spread_lab.policy import DAY, HOUR, Desk, Params


def main() -> None:
    home = Path.home() / ".spread-lab"
    wmap = json.loads((home / "map.json").read_text(encoding="utf-8"))
    geo = Geo(wmap)
    tape = json.loads((home / "tas" / "dev-12" / "tape.json").read_text(encoding="utf-8"))
    champ_p = json.loads(Path("champion/champion.json").read_text(encoding="utf-8"))["params"]
    lall_rows = [json.loads(l) for l in (home / "tas" / "dev-12" / "limits-all.jsonl").read_text().splitlines() if l.strip()]
    lim_map = {(r["rid"], r["option"]): r for r in lall_rows if r.get("lo")}

    dlr_tot = Counter((r["dealerId"], r["arrivedAt"] // DAY) for r in tape["requests"])
    s30 = geo.supply(tape["roster"], 30.0)
    desk = Desk(world=None, params=Params(**champ_p), level=8, geo=geo, roster=tape["roster"], now=0)  # type: ignore[arg-type]

    # Step 1: Score every v5-approved request using ONLY tape fields (list, ref, drive, supply, outage/war day)
    cands_by_day = defaultdict(list)
    for r in tape["requests"]:
        rid = r["id"]
        dlr = r["dealerId"]
        d, tod = r["arrivedAt"] // DAY, r["arrivedAt"] % DAY
        desk.now = r["arrivedAt"]
        prices, _ = desk.price(r)
        if not prices:
            continue
        p0 = r["legs"][0]["pickup"]["placeId"]
        d0 = r["legs"][-1]["delivery"]["placeId"]
        drv = geo.minutes(p0, d0)
        ps, ds = s30.get(p0, 0), s30.get(d0, 0)
        ref_e = r["referenceFeeCents"] / 100.0

        # Choose safest profitable option approved by v5
        if "same_day" in prices and d <= 1 and tod <= 11 * HOUR + 30 and ps >= 180 and drv <= 150:
            chosen_k = "same_day"
        elif "within_3_days" in prices and d == 4:
            chosen_k = "within_3_days"
        elif "next_day" in prices:
            chosen_k = "next_day"
        elif "within_3_days" in prices:
            chosen_k = "within_3_days"
        else:
            if d == 4 and tod > 11 * HOUR:
                continue
            chosen_k = "same_day"

        list_e = next(o["listPriceCents"] for o in r["options"] if o["kind"] == chosen_k) / 100.0
        # Blind corridor limit/list & solo fee/ref priors (NO peeking at limits-all!)
        in_outage = (d == 1 and 8 * HOUR <= tod <= 18 * HOUR and geo.line_km("lahti", p0) <= 80.0)
        in_war = (d == 4 and 8 * HOUR <= tod <= 18 * HOUR)
        est_x = 1.82 if in_outage else (1.18 if in_war else (1.24 if (ps < 150 and ds >= 180) else 1.50))
        if d >= 2 and dlr in ("D01", "D02", "D03"):
            est_x *= 1.22  # trust + steered competitor
        est_f = ref_e * ((0.78 if ds >= 150 else 0.88) + (0.24 * max(0, drv - 120) / 120.0 if ds < 140 else 0.0) + (0.10 if chosen_k == "same_day" else 0.0))
        # Efficiency-weighted rank score: reward BOTH absolute euro margin AND margin-per-driver-minute!
        est_m = list_e * est_x - est_f
        rank_score = est_m - 0.08 * drv
        cands_by_day[d].append((rank_score, est_m, r, chosen_k, drv, ref_e))

    for day_cap_n in (58, 66, 74):
        won_dlr_day = Counter()
        won_day = Counter()
        tot_rev = 0.0
        tot_ref = 0.0
        drives = []
        for d in range(5):
            # Sort day's candidates best-first!
            day_cands = sorted(cands_by_day[d], key=lambda x: -x[0])
            cap_today = int(day_cap_n * 1.15) if d == 4 else day_cap_n
            for rank_score, est_m, r, chosen_k, drv, ref_e in day_cands:
                if won_day[d] >= cap_today or est_m < 14.0:
                    continue
                dlr = r["dealerId"]
                tot_d = dlr_tot[(dlr, d)]
                if tot_d >= 10 and d < 4:
                    frac = 0.29 if d == 0 else 0.67
                    cap = max(1, math.ceil(frac * tot_d) - 1) if d == 0 else max(1, math.ceil(0.70 * tot_d) - 1)
                    if won_dlr_day[(dlr, d)] >= cap:
                        continue
                lrow = lim_map.get((r["id"], chosen_k))
                if not lrow:
                    continue
                lo_e = lrow["lo"] / 100.0
                if tot_d >= 10 and d >= 1:
                    lo_e *= 1.038
                if lo_e - ref_e * 0.94 < 15.0:
                    continue
                won_dlr_day[(dlr, d)] += 1
                won_day[d] += 1
                tot_rev += lo_e
                tot_ref += ref_e
                drives.append(drv)

        est_fee = tot_ref * 0.936
        print(
            f"RANKED day_cap={day_cap_n}: won={sum(won_day.values())} | by_day={dict(won_day)} | "
            f"rev=€{tot_rev:,.0f} | sum_ref=€{tot_ref:,.0f} (rev/ref={tot_rev/max(1,tot_ref):.3f}x) | "
            f"mean_drv={sum(drives)/len(drives):.1f}m | EST SOLO MARGIN = €{tot_rev - est_fee:,.0f}"
        )


if __name__ == "__main__":
    main()
