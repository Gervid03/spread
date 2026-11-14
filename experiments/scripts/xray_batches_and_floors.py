"""Exact slot-free measurement on TAS limits-all & 4 tapes:
1. Do requests in one batchId have correlated dealer limits? How many pairs in a batchId can a single driver shuttle or loop?
2. How many quotes are lost purely due to expected_fee_mult=1.25 floor on slow / within_3_days / closed-tour legs?
3. What is true dealer limit vs listPriceCents on within_3_days vs next_day vs same_day?
4. What is the Friday endgame opportunity (d==4 slow options)?
5. What is the 2-leg trade-in opportunity (20/21 declined on dev-12 had limit - ref > €25, total €2,227 surplus!)?
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from statistics import mean

from spread_lab.env import lab_home
from spread_lab.geo import Geo


def main() -> None:
    lh = lab_home()
    geo = Geo(json.loads((lh / "map.json").read_text()))
    d12 = lh / "tas" / "dev-12"
    tape = json.loads((d12 / "tape.json").read_text())
    rev = json.loads((d12 / "reveal-v5.json").read_text())
    lims = [json.loads(l) for l in (d12 / "limits-all.jsonl").read_text().splitlines() if l.strip()]

    lim_map: dict[tuple[str, str], dict] = {(r["rid"], r["option"]): r for r in lims}
    req_map = {r["id"]: r for r in tape["requests"]}
    rev_map = {r["request"]["id"]: r for r in rev["requests"]}
    sup30 = geo.supply(tape["roster"], 30.0)
    sup55 = geo.supply(tape["roster"], 55.0)

    # 1. True limit multiplier `lo / list` by option kind on dev-12!
    print("=== 1. DEV-12 TRUE DEALER LIMIT / LIST BY OPTION KIND ===")
    by_kind = defaultdict(list)
    by_kind_margin_at_090ref = defaultdict(list)
    for r in lims:
        if r.get("lo") and r.get("list"):
            by_kind[r["option"]].append(r["lo"] / r["list"])
            surplus = (r["lo"] - 0.90 * r["ref"]) / 100.0
            by_kind_margin_at_090ref[r["option"]].append(surplus)
    for k in ("same_day", "next_day", "within_3_days"):
        xs = by_kind[k]
        ms = by_kind_margin_at_090ref[k]
        if xs:
            print(f"  {k:<15}: n={len(xs):4d}  mean(limit/list)={mean(xs):.3f}  median={sorted(xs)[len(xs)//2]:.3f}  mean(limit - 0.90*ref)=€{mean(ms):.2f}  %(>€20)={sum(1 for m in ms if m>20)/len(ms)*100:.1f}%")

    # Compare multi-option requests: when a request has (same_day, next_day, within_3_days), how do limits compare?
    print()
    print("=== 2. MULTI-OPTION RELATIVE LIMITS ON SAME REQUEST ===")
    ratios_nd_sd = []
    ratios_w3_nd = []
    for req in tape["requests"]:
        rid = req["id"]
        l_sd = lim_map.get((rid, "same_day"))
        l_nd = lim_map.get((rid, "next_day"))
        l_w3 = lim_map.get((rid, "within_3_days"))
        if l_sd and l_nd and l_sd.get("lo") and l_nd.get("lo"):
            ratios_nd_sd.append((l_nd["lo"] / l_nd["list"]) / (l_sd["lo"] / l_sd["list"]))
        if l_nd and l_w3 and l_nd.get("lo") and l_w3.get("lo"):
            ratios_w3_nd.append((l_w3["lo"] / l_w3["list"]) / (l_nd["lo"] / l_nd["list"]))
    print(f"  (limit/list)_next_day / (limit/list)_same_day     : n={len(ratios_nd_sd)} mean={mean(ratios_nd_sd):.4f}")
    print(f"  (limit/list)_within_3_days / (limit/list)_next_day: n={len(ratios_w3_nd)} mean={mean(ratios_w3_nd):.4f}")

    # 3. Check quotes floored in reveal-v5 that LOST despite true limit > 0.95*ref + €20!
    print()
    print("=== 3. FLOORED QUOTES IN DEV-12 THAT LOST DESPITE HIGH PROFIT MARGIN ===")
    floored_lost_good = []
    for rrow in rev["requests"]:
        req = rrow["request"]
        rid = req["id"]
        if rrow["outcome"] == "won" or not rrow["quote"]:
            continue
        q_min = min(rrow["quote"].values())
        if q_min >= req["options"][0]["listPriceCents"] * 3.5:
            continue  # declined
        ref = req["referenceFeeCents"]
        floor_v6 = int(ref * 1.25 / 0.92 + 0.5)
        # Check if any quoted option was at floor_v6 and lost, while limit > 0.95*ref + 1800
        for opt_k, q_c in rrow["quote"].items():
            lr = lim_map.get((rid, opt_k))
            if abs(q_c - floor_v6) <= 3 and lr and lr.get("lo"):
                lim_c = lr["lo"]
                if lim_c > ref * 0.95 + 1800 and lim_c < q_c:
                    floored_lost_good.append((opt_k, (lim_c - 0.90 * ref) / 100.0, rid, req["legs"][0]["pickup"]["placeId"], req["legs"][-1]["delivery"]["placeId"], q_c / 100.0, lim_c / 100.0, ref / 100.0))
    print(f"  Floored-out profitable quotes on dev-12: n={len(floored_lost_good)}, potential margin at 0.90*ref = €{sum(x[1] for x in floored_lost_good):.1f}")
    for row in sorted(floored_lost_good, key=lambda x: -x[1])[:12]:
        print("   ", row)

    # 4. Trade-ins (2-leg requests): why were 21/22 declined on dev-12?!
    print()
    print("=== 4. 2-LEG TRADE-INS ANATOMY ACROSS ALL 4 TAS TAPES ===")
    for seed in ["dev-12", "dev-01", "dev-07", "dev-08"]:
        tp = json.loads((lh / "tas" / seed / "tape.json").read_text())
        rv = json.loads((lh / "tas" / seed / "reveal-v5.json").read_text())
        rmap = {x["request"]["id"]: x for x in rv["requests"]}
        s30 = geo.supply(tp["roster"], 30.0)
        s55 = geo.supply(tp["roster"], 55.0)
        tis = [r for r in tp["requests"] if len(r["legs"]) == 2]
        won_ti = sum(1 for r in tis if rmap[r["id"]]["outcome"] == "won")
        gate_ok = [r for r in tis if s55.get(r["legs"][0]["pickup"]["placeId"], 0) >= 22]
        # Why did gate_ok trade-ins get declined?
        reasons = Counter()
        for r in gate_ok:
            l0, l1 = r["legs"][0], r["legs"][1]
            drv = geo.minutes(l0["pickup"]["placeId"], l0["delivery"]["placeId"]) + geo.minutes(l0["delivery"]["placeId"], l1["pickup"]["placeId"]) + geo.minutes(l1["pickup"]["placeId"], l1["delivery"]["placeId"])
            ready = max(r["arrivedAt"], l0["pickup"]["window"]["from"], l1["pickup"]["window"]["from"])
            opts = [o["kind"] for o in r["options"]]
            best_slack = max(o["deadline"] - ready - drv - (150 + 0.75 * drv) for o in r["options"] if not (o["kind"] == "same_day" and (drv > 300 or s30.get(l0["pickup"]["placeId"], 0) < 50))) if any(not (o["kind"] == "same_day" and (drv > 300 or s30.get(l0["pickup"]["placeId"], 0) < 50)) for o in r["options"]) else -9999
            reasons[f"drv<=300:{drv<=300}_drv<=480:{drv<=480}_l1from>l0from:{l1['pickup']['window']['from']>l0['pickup']['window']['from']}_slackOK:{best_slack>=0}"] += 1
        print(f"  {seed}: total_2leg={len(tis)}, gate55>=22={len(gate_ok)}, won_v5={won_ti}, breakdown={dict(reasons)}")

    # 5. BatchId correlation & shuttle pairs on dev-12!
    print()
    print("=== 5. BATCH_ID LIMIT CORRELATION & SHUTTLE / TOUR PAIRS ON DEV-12 ===")
    batches = defaultdict(list)
    for r in tape["requests"]:
        if r.get("batchId"):
            batches[r["batchId"]].append(r)
    within_batch_stds = []
    batch_shuttle_count = 0
    for bid, breqs in batches.items():
        xs = []
        for r in breqs:
            opt0 = r["options"][-1]["kind"]
            lr = lim_map.get((r["id"], opt0))
            if lr and lr.get("x"):
                xs.append(lr["x"])
        if len(xs) >= 3:
            m = mean(xs)
            within_batch_stds.append(mean(abs(x - m) for x in xs))
        # Count shuttle pairs inside same batch (same pickup, delivery within 25km, slow option available, 3*drv <= 540)
        slow_1leg = [r for r in breqs if len(r["legs"]) == 1 and any(o["kind"] != "same_day" for o in r["options"])]
        used = set()
        for i, r1 in enumerate(slow_1leg):
            if r1["id"] in used:
                continue
            p1, d1 = r1["legs"][0]["pickup"]["placeId"], r1["legs"][0]["delivery"]["placeId"]
            for r2 in slow_1leg[i + 1:]:
                if r2["id"] in used:
                    continue
                p2, d2 = r2["legs"][0]["pickup"]["placeId"], r2["legs"][0]["delivery"]["placeId"]
                if geo.line_km(p1, p2) <= 20 and geo.line_km(d1, d2) <= 25:
                    tot = geo.minutes(p1, d1) + geo.minutes(d1, p2) + geo.minutes(p2, d2)
                    if tot <= 540:
                        batch_shuttle_count += 1
                        used.add(r1["id"])
                        used.add(r2["id"])
                        break
    print(f"  Mean |x - batch_mean_x| inside batches (>=3 cars): {mean(within_batch_stds):.4f} (tight correlation!)")
    print(f"  Within-batch 2-car slow shuttle pairs (tot road <= 9h): {batch_shuttle_count} pairs ({batch_shuttle_count*2} cars)")

    # 6. Friday endgame opportunity on dev-12!
    print()
    print("=== 6. FRIDAY ENDGAME (day == 4) ON DEV-12 ===")
    fri_slow_lost = []
    for rrow in rev["requests"]:
        req = rrow["request"]
        if req["arrivedAt"] // 1440 != 4 or rrow["outcome"] == "won":
            continue
        p0 = req["legs"][0]["pickup"]["placeId"]
        if sup55.get(p0, 0) < 22:
            continue
        for opt in req["options"]:
            if opt["kind"] == "same_day":
                continue
            lr = lim_map.get((req["id"], opt["kind"]))
            if lr and lr.get("lo"):
                surplus = (lr["lo"] - 0.90 * req["referenceFeeCents"]) / 100.0
                if surplus > 15:
                    fri_slow_lost.append((surplus, req["id"], p0, req["legs"][-1]["delivery"]["placeId"], opt["kind"], rrow["quote"].get(opt["kind"]), lr["lo"]))
    print(f"  Friday gate-passing slow options LOST with surplus > €15: n={len(fri_slow_lost)} requests/options, sum_surplus=€{sum(x[0] for x in fri_slow_lost):.1f}")
    for row in sorted(fri_slow_lost, key=lambda x: -x[0])[:10]:
        print("   ", row)


if __name__ == "__main__":
    main()
