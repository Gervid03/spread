"""Deep slot-free X-ray of capacity leaks, batchId structure, sunday-tours-dev, and RULES.md."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, stdev

from spread_lab.env import lab_home
from spread_lab.geo import Geo


def paired_delta(champ_by_seed: dict[str, dict], cand_rows: list[dict], name: str) -> None:
    diffs = []
    won_diffs = []
    ots = []
    for r in cand_rows:
        s = r["seed"]
        if s in champ_by_seed:
            diffs.append(r["margin"] - champ_by_seed[s]["margin"])
            won_diffs.append(r["won"] - champ_by_seed[s]["won"])
            ots.append(r["on_time"])
    if not diffs:
        return
    m = mean(diffs)
    se = (stdev(diffs) / (len(diffs) ** 0.5)) if len(diffs) > 1 else 0.0
    t = m / se if se > 0 else 0.0
    bw_b = sum(1 for d in diffs if d > 0.005)
    bw_w = sum(1 for d in diffs if d < -0.005)
    print(f"[{name}] n={len(diffs)} Δmargin={m:+.2f} ± {se:.2f} (t={t:.2f}) better/worse={bw_b}/{bw_w} Δwon={mean(won_diffs):+.1f} min_OT={min(ots)*100:.2f}% <92%={sum(1 for x in ots if x < 0.92)}")


def main() -> None:
    champ_rows = [json.loads(l) for l in Path("champion/results/dev-L8.jsonl").read_text().splitlines() if l.strip()]
    champ_by_seed = {r["seed"]: r for r in champ_rows}

    lh = lab_home()
    # Check sunday-tours-dev and sun-fri-endgame-dev16 in runs index if accessible
    runs_idx = lh / "runs.jsonl"
    if runs_idx.exists():
        lines = [json.loads(l) for l in runs_idx.read_text().splitlines() if l.strip()]
        for entry in lines[-20:]:
            rdir = Path(entry.get("dir", ""))
            if any(k in entry.get("name", "") for k in ("sunday-tours", "sun-fri", "cp-routes", "cp-volume", "cp-chains")):
                print("Run index:", entry.get("name"), entry.get("n"), entry.get("margin_mean"), entry.get("on_time_min"), rdir)

    geo = Geo(json.loads((lh / "map.json").read_text()))
    d12 = lh / "tas" / "dev-12"
    rev = json.loads((d12 / "reveal-v5.json").read_text())
    tape = json.loads((d12 / "tape.json").read_text())
    lims = [json.loads(l) for l in (d12 / "limits-all.jsonl").read_text().splitlines() if l.strip()]
    lim_by_rid_opt = {(r["rid"], r["option"]): r for r in lims}

    roster = tape["roster"]
    sup30 = geo.supply(roster, 30.0)
    sup55 = geo.supply(roster, 55.0)
    sup70 = geo.supply(roster, 70.0)

    # 1. Analyze ALL 1,036 requests on dev-12 against exact dealer limits & reference fees!
    print()
    print("=== DEV-12: WHERE ARE THE 785 UNWON REQUESTS? ===")
    buckets = Counter()
    profitable_declined = defaultdict(list)
    for rrow in rev["requests"]:
        req = rrow["request"]
        rid = req["id"]
        outcome = rrow["outcome"]
        p0 = req["legs"][0]["pickup"]["placeId"]
        dk = req["legs"][-1]["delivery"]["placeId"]
        s30 = sup30.get(p0, 0)
        s55 = sup55.get(p0, 0)
        s70 = sup70.get(p0, 0)
        ds30 = sup30.get(dk, 0)
        drv = sum(geo.minutes(l["pickup"]["placeId"], l["delivery"]["placeId"]) for l in req["legs"])
        ref = req["referenceFeeCents"] / 100.0

        # Find best true limit across options
        best_lim = 0.0
        best_opt = None
        for opt in req["options"]:
            lr = lim_by_rid_opt.get((rid, opt["kind"]))
            if lr and lr.get("lo"):
                val = lr["lo"] / 100.0
                if val > best_lim:
                    best_lim = val
                    best_opt = opt["kind"]

        q_vals = list(rrow["quote"].values())
        was_declined = bool(q_vals and min(q_vals) >= req["options"][0]["listPriceCents"] * 3.5)
        if outcome == "won":
            buckets["1_won"] += 1
        elif not was_declined:
            buckets["2_quoted_but_lost"] += 1
            # Check if we dropped same_day when same_day was offered
            offered_kinds = {o["kind"] for o in req["options"]}
            quoted_kinds = set(rrow["quote"].keys())
            if "same_day" in offered_kinds and "same_day" not in quoted_kinds:
                buckets["2a_quoted_slow_dropped_sameday_lost"] += 1
        else:
            buckets["3_declined"] += 1
            # Categorize WHY declined
            if len(req["legs"]) > 1:
                cat = "tradein_2leg"
            elif s55 < 22:
                if ds30 >= 200:
                    cat = f"thin_to_cap200_drv{180 if drv<=180 else 300 if drv<=300 else 999}"
                elif ds30 >= 35:
                    cat = f"thin_to_reg35_drv{240 if drv<=240 else 360 if drv<=360 else 999}"
                elif s70 >= 30:
                    cat = f"ext_ring70_drv{220 if drv<=220 else 999}"
                else:
                    cat = "thin_to_thin"
            elif s30 < 22:
                cat = "ring_declined_only_sameday_or_slack"
            else:
                cat = f"dense_declined_day{req['arrivedAt']//1440}"
            buckets[f"3_{cat}"] += 1
            if best_lim - ref > 25:
                profitable_declined[cat].append((best_lim - ref, rid, p0, dk, drv, [o["kind"] for o in req["options"]]))

    for k, v in sorted(buckets.items()):
        print(f"  {k:<42}: {v:4d}")

    print()
    print("=== PROFITABLE DECLINED CATEGORIES (limit - 1.0x ref > €25) ===")
    for cat, items in sorted(profitable_declined.items(), key=lambda kv: -sum(x[0] for x in kv[1])):
        tot_surplus = sum(x[0] for x in items)
        print(f"  {cat:<36}: n={len(items):3d}  sum(limit-ref)=€{tot_surplus:8.1f}  sample={items[:2]}")

    # 2. Analyze batchId across all 4 TAS tapes!
    print()
    print("=== BATCH_ID ANATOMY ACROSS 4 TAS TAPES ===")
    for seed in ["dev-12", "dev-01", "dev-07", "dev-08"]:
        tp = json.loads((lh / "tas" / seed / "tape.json").read_text())
        rv = json.loads((lh / "tas" / seed / "reveal-v5.json").read_text())
        req_by_id = {x["request"]["id"]: x for x in rv["requests"]}
        batches = defaultdict(list)
        for r in tp["requests"]:
            if r.get("batchId"):
                batches[r["batchId"]].append(r)
        big = [b for b in batches.values() if len(b) >= 5]
        med = [b for b in batches.values() if 2 <= len(b) <= 4]
        won_in_big = sum(1 for b in big for r in b if req_by_id[r["id"]]["outcome"] == "won")
        tot_in_big = sum(len(b) for b in big)
        won_in_med = sum(1 for b in med for r in b if req_by_id[r["id"]]["outcome"] == "won")
        tot_in_med = sum(len(b) for b in med)
        # Check same pickup+delivery pairs inside batches!
        same_lane_pairs = 0
        for b in batches.values():
            lanes = Counter((r["legs"][0]["pickup"]["placeId"], r["legs"][-1]["delivery"]["placeId"]) for r in b if len(r["legs"]) == 1)
            same_lane_pairs += sum(c // 2 for c in lanes.values())
        print(f"  {seed}: batches(2-4)={len(med)} ({won_in_med}/{tot_in_med} won), bulk(>=5)={len(big)} ({won_in_big}/{tot_in_big} won), exact_same_lane_pairs_in_batches={same_lane_pairs}")

    # 3. Analyze driver utilization & gig views on dev-12 reveal-v5!
    views = rev["views"]
    unique_viewers = len({v["driverId"] for v in views})
    views_by_day = Counter(v["at"] // 1440 for v in views)
    unique_viewers_by_day = {d: len({v["driverId"] for v in views if v["at"] // 1440 == d}) for d in range(8)}
    print()
    print(f"=== DEV-12 DRIVER ACTIVITY (roster={len(roster)}) ===")
    print(f"  Unique viewing drivers all week: {unique_viewers} / {len(roster)} ({unique_viewers/len(roster)*100:.1f}%)")
    print(f"  Unique viewing drivers by day (Mon=0..Sun=6): {unique_viewers_by_day}")
    print(f"  Views by day: {dict(sorted(views_by_day.items()))}")


if __name__ == "__main__":
    main()
