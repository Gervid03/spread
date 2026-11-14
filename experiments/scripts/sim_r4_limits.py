"""Exact reverse-engineering & simulation on TAS datasets (0 network calls):
1. Multi-option choice rule (`same_day` + `next_day`): verify how dealers choose when we quote BOTH options!
2. Live Outage & Price-War detector verification across all 20 world-days of `dev-12`, `dev-01`, `dev-08`, `dev-07`.
3. Price-War day profitability check: are floor/quote wins during a Price War profitable or money-losing?
4. Counterfactual margin simulation on `dev-12` (`limits-all.jsonl` + empirical fees).
"""
from __future__ import annotations

import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from spread_lab.geo import Geo
from analyze_r4_limits import LANE_PICKUP, LANE_DELIVERY, lane_eff


def main() -> None:
    home = Path.home() / ".spread-lab"
    geo = Geo(json.loads((home / "map.json").read_text(encoding="utf-8")))
    tas_dir = home / "tas"
    seeds = ["dev-12", "dev-01", "dev-08", "dev-07"]
    places = list(LANE_PICKUP.keys())

    # =========================================================================
    # 1. Reverse-engineer multi-option dealer choice on dev-12 (reveal-v5 + limits-all)
    # =========================================================================
    print("=" * 92)
    print("1. EXACT MULTI-OPTION DEALER CHOICE RULE ON dev-12 (reveal-v5 vs limits-all)")
    print("=" * 92)
    rev12 = json.loads((tas_dir / "dev-12" / "reveal-v5.json").read_text(encoding="utf-8"))
    lall = [json.loads(l) for l in (tas_dir / "dev-12" / "limits-all.jsonl").read_text().splitlines() if l.strip()]
    lim_by_rid = defaultdict(dict)
    for r in lall:
        lim_by_rid[r["rid"]][r["option"]] = r

    # Note: limits-all was probed along v5's trajectory! So trust & competitor steps match reveal-v5!
    both_quoted = []
    for item in rev12["requests"]:
        req = item["request"]
        rid = req["id"]
        q = item.get("quote") or {}
        if "same_day" in q and "next_day" in q:
            lsd = lim_by_rid[rid].get("same_day", {}).get("lo")
            lnd = lim_by_rid[rid].get("next_day", {}).get("lo")
            if lsd and lnd:
                both_quoted.append((rid, q["same_day"], q["next_day"], lsd, lnd, item["outcome"], item.get("option")))

    print(f"Requests on dev-12 where v5 quoted BOTH same_day and next_day (with exact limits): {len(both_quoted)}")
    choice_table = Counter()
    surplus_check = [0, 0]
    ratio_check = [0, 0]
    for rid, psd, pnd, lsd, lnd, out, opt in both_quoted:
        sd_ok = psd <= lsd
        nd_ok = pnd <= lnd
        choice_table[(sd_ok, nd_ok, out, opt)] += 1
        if sd_ok and nd_ok and out == "won" and opt in ("same_day", "next_day"):
            # Test hypothesis A: dealer picks max(lsd - psd, lnd - pnd) (cents surplus)
            pred_cents = "same_day" if (lsd - psd) >= (lnd - pnd) else "next_day"
            surplus_check[0 if pred_cents == opt else 1] += 1
            # Test hypothesis B: dealer picks max(lsd / psd, lnd / pnd) (log surplus)
            pred_ratio = "same_day" if (lsd / psd) >= (lnd / pnd) else "next_day"
            ratio_check[0 if pred_ratio == opt else 1] += 1

    for k, cnt in sorted(choice_table.items()):
        print(f"  sd<=lim={str(k[0]):<5} nd<=lim={str(k[1]):<5} -> outcome={k[2]:<4} option={str(k[3]):<10} : n={cnt}")
    print(f"  When BOTH sd<=lim and nd<=lim: max(lim - price) accuracy = {surplus_check[0]}/{sum(surplus_check)} | max(lim / price) accuracy = {ratio_check[0]}/{sum(ratio_check)}")

    # Now simulate raising `same_day` markup on `both_quoted` requests on dev-12!
    # Wait: if we raise `psd` by +3%, +5%, +8%, +10% while keeping `pnd` unchanged, what happens on those 226 requests?!
    print()
    print("--- Counterfactual: Raising ONLY `same_day` price by +delta% when BOTH `same_day` & `next_day` are quoted (dev-12) ---")
    for bump in [0.0, 0.03, 0.05, 0.07, 0.10, 0.14]:
        won_sd, won_nd, lost_n = 0, 0, 0
        rev_eur = 0.0
        est_fee_eur = 0.0
        for rid, psd, pnd, lsd, lnd, out, opt in both_quoted:
            psd_new = int(round(psd * (1.0 + bump)))
            sd_ok = psd_new <= lsd
            nd_ok = pnd <= lnd
            ref = lim_by_rid[rid]["same_day"]["ref"] / 100.0
            if not sd_ok and not nd_ok:
                lost_n += 1
            elif sd_ok and (not nd_ok or (lsd - psd_new) >= (lnd - pnd)):
                won_sd += 1
                rev_eur += psd_new / 100.0
                est_fee_eur += ref * 0.96  # empirical same_day fee ~0.96x ref
            else:
                won_nd += 1
                rev_eur += pnd / 100.0
                est_fee_eur += ref * 0.87  # next_day books ~9% cheaper than same_day!
        print(
            f"  sd_bump=+{bump*100:4.1f}%: total_won={won_sd+won_nd:>3} (sd={won_sd:>2}, nd={won_nd:>2}, lost={lost_n:>3}) | "
            f"rev=€{rev_eur:8.1f} | est_margin=€{rev_eur - est_fee_eur:7.1f}"
        )

    # =========================================================================
    # 2. Check ALL 20 world-days across the 4 TAS worlds for Outage & Price War!
    # =========================================================================
    print()
    print("=" * 92)
    print("2. EXACT OUTAGE & PRICE WAR DETECTION SIMULATION ACROSS ALL 20 WORLD-DAYS (4 TAS WORLDS)")
    print("=" * 92)

    circle_80 = {c: {p for p in places if geo.line_km(c, p) <= 80.0} for c in places}

    for seed in seeds:
        rev = json.loads((tas_dir / seed / "reveal-v5.json").read_text(encoding="utf-8"))
        won_lim = {
            json.loads(l)["rid"]: json.loads(l)
            for l in (tas_dir / seed / "limits-won-apply.jsonl").read_text().splitlines()
            if l.strip()
        }
        # Also map orderId -> booked gig fees from views/orders? Wait: reveal has views, not ledger, so check won_lim ref vs desk_cents!
        print()
        print(f"=== {seed} ===")
        # Sort quoted (non-decline) requests by respondBy (when outcome arrives!)
        events = []
        for item in rev["requests"]:
            req = item["request"]
            q = item.get("quote") or {}
            if not q:
                continue
            fk = next(iter(q))
            lst = next(o["listPriceCents"] for o in req["options"] if o["kind"] == fk)
            ratio = q[fk] / lst
            if ratio >= 3.5:
                continue
            # Check if floored (price <= 1.25 * ref / 0.92 + 2 cents)
            floor_c = req["referenceFeeCents"] * 1.25 / 0.92
            is_floor = abs(q[fk] - floor_c) <= 3
            events.append({
                "rid": req["id"],
                "arr": req["arrivedAt"],
                "res": req["respondBy"],
                "day": req["arrivedAt"] // 1440,
                "tod": req["arrivedAt"] % 1440,
                "pick": req["legs"][0]["pickup"]["placeId"],
                "dest": req["legs"][-1]["delivery"]["placeId"],
                "dlr": req["dealerId"],
                "won": item["outcome"] == "won",
                "is_quote": not is_floor,
                "ratio": ratio,
                "ref": req["referenceFeeCents"],
                "quote_c": q.get(item.get("option") or fk, q[fk]),
            })
        events.sort(key=lambda e: e["res"])

        outage_fired_week = -1
        for d in range(5):
            day_evs = [e for e in events if e["day"] == d and e["is_quote"] and e["tod"] < 18 * 60]
            seen = []
            det_outage = None
            det_war = None
            for e in day_evs:
                seen.append(e)
                # War check: >=10 quote outcomes today, win rate <= 0.15
                if det_war is None and len(seen) >= 10:
                    wr_all = sum(1 for x in seen if x["won"]) / len(seen)
                    if wr_all <= 0.15:
                        det_war = (e["res"] % 1440, len(seen), wr_all)
                # Outage check (at most once per week!):
                if det_outage is None and outage_fired_week < 0:
                    best_c = None
                    for c, cset in circle_80.items():
                        inc = [x for x in seen if x["pick"] in cset]
                        if len(inc) < 8:
                            continue
                        w_in = sum(1 for x in inc if x["won"]) / len(inc)
                        if w_in < 0.80:
                            continue
                        outc = [x for x in seen if x["pick"] not in cset]
                        w_out = (sum(1 for x in outc if x["won"]) / len(outc)) if outc else 0.0
                        avg_r = statistics.mean(x["ratio"] for x in inc)
                        # Confirm if regional contrast OR already high quote/list >= 1.55 with >= 10 wins!
                        if (len(outc) >= 4 and w_in - w_out >= 0.35) or (len(inc) >= 11 and w_in >= 0.82 and avg_r >= 1.55):
                            cand = (w_in, len(inc), c, w_out, len(outc), avg_r)
                            if best_c is None or cand > best_c:
                                best_c = cand
                    if best_c is not None:
                        det_outage = (e["res"] % 1440, best_c)
                        outage_fired_week = d

            # Now evaluate what happens on the REMAINING outage quotes after detection on day d!
            after_gain = 0.0
            after_won_kept = 0
            after_lost = 0
            if det_outage is not None:
                t_det, (_, _, c_star, _, _, _) = det_outage
                cset = circle_80[c_star]
                for e in events:
                    if e["day"] == d and e["arr"] % 1440 > t_det and e["tod"] < 18 * 60 and e["pick"] in cset and e["won"]:
                        wl = won_lim.get(e["rid"])
                        if wl and wl.get("lo"):
                            new_q = int(round(wl["desk_cents"] * 1.18))
                            if new_q <= wl["lo"]:
                                after_won_kept += 1
                                after_gain += (new_q - wl["desk_cents"]) / 100.0
                            else:
                                after_lost += 1
                                # rough lost margin if lost: -(desk_cents - 0.92*ref)
                                after_gain -= max(0.0, (wl["desk_cents"] - 0.92 * wl["ref"]) / 100.0)

            o_str = "none"
            if det_outage:
                t_m, (wi, ni, cs, wo, no, ar) = det_outage
                o_str = f"OUTAGE@{t_m//60:02d}:{t_m%60:02d} {cs} in={wi*100:.0f}%({ni}) out={wo*100:.0f}%({no}) r={ar:.2f} -> 1.18x: kept={after_won_kept}, lost={after_lost}, net_Δ=€{after_gain:+.0f}"
            w_str = f"WAR@{det_war[0]//60:02d}:{det_war[0]%60:02d} ({det_war[2]*100:.0f}%/{det_war[1]})" if det_war else "no-war"
            print(f"  Day {d}: quote_evs={len(day_evs):>3} | {w_str:<22} | {o_str}")


if __name__ == "__main__":
    main()
