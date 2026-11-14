"""Comprehensive analysis of dev-12 limits-all.jsonl and 4-world limits-won-apply.jsonl."""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from statistics import mean, median

from spread_lab.env import lab_home
from spread_lab.geo import Geo, load_map


def load_jsonl(p: Path) -> list[dict]:
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    geo = Geo(load_map(None))
    tas_dir = lab_home() / "tas"
    d12_dir = tas_dir / "dev-12"
    tape = json.loads((d12_dir / "tape.json").read_text(encoding="utf-8"))
    reqs = {r["id"]: r for r in tape["requests"]}
    roster = tape["roster"]
    supply30 = geo.supply(roster, 30.0)
    supply55 = geo.supply(roster, 55.0)

    lines = load_jsonl(d12_dir / "limits-all.jsonl")
    print(f"Loaded {len(lines)} option limit rows across {len({r['rid'] for r in lines})} requests on dev-12.")

    by_rid: dict[str, list[dict]] = defaultdict(list)
    for row in lines:
        by_rid[row["rid"]].append(row)

    # 1. Arithmetic revenue & margin bounds on dev-12
    max_rev_cents = 0
    pos_margin_085 = 0
    pos_margin_085_n = 0
    pos_margin_040 = 0
    pos_margin_040_n = 0
    pos_margin_100 = 0
    pos_margin_100_n = 0
    for rid, opts in by_rid.items():
        best_lo = max((o["lo"] or 0) for o in opts)
        ref = reqs[rid]["referenceFeeCents"]
        max_rev_cents += best_lo
        if best_lo > ref * 1.00:
            pos_margin_100 += best_lo - ref * 1.00
            pos_margin_100_n += 1
        if best_lo > ref * 0.85:
            pos_margin_085 += best_lo - ref * 0.85
            pos_margin_085_n += 1
        if best_lo > ref * 0.40:
            pos_margin_040 += best_lo - ref * 0.40
            pos_margin_040_n += 1

    print("=== 1. ARITHMETIC BOUNDS ON DEV-12 (ALL 1,036 REQUESTS) ===")
    print(f"Max gross revenue (every request won at best option's lo): €{max_rev_cents / 100:,.2f}")
    print(f"Sum(max(0, limit - 1.00*ref)): €{pos_margin_100 / 100:,.2f} across {pos_margin_100_n} requests")
    print(f"Sum(max(0, limit - 0.85*ref)): €{pos_margin_085 / 100:,.2f} across {pos_margin_085_n} requests (v5 opening solo fee)")
    print(f"Sum(max(0, limit - 0.40*ref)): €{pos_margin_040 / 100:,.2f} across {pos_margin_040_n} requests (closed-tour fee bound)")

    # 2. Option comparison on SAME request (paired!)
    print("=== 2. PAIRED OPTION RATIOS ON THE EXACT SAME REQUEST (dev-12) ===")
    pairs = [("same_day", "next_day"), ("next_day", "within_3_days"), ("same_day", "within_3_days")]
    for a, b in pairs:
        xa_list, xb_list, diff_x, euro_diff = [], [], [], []
        list_ratio = []
        for rid, opts in by_rid.items():
            ma = next((o for o in opts if o["option"] == a and o["bound"] == "exact" and o["lo"]), None)
            mb = next((o for o in opts if o["option"] == b and o["bound"] == "exact" and o["lo"]), None)
            if ma and mb:
                xa, xb = ma["lo"] / ma["list"], mb["lo"] / mb["list"]
                xa_list.append(xa)
                xb_list.append(xb)
                diff_x.append(xa - xb)
                euro_diff.append((ma["lo"] - mb["lo"]) / 100.0)
                list_ratio.append(ma["list"] / mb["list"])
        if xa_list:
            print(f"{a} vs {b} (n={len(xa_list)} paired exact):")
            print(f"  list({a})/list({b}) median={median(list_ratio):.4f}")
            print(f"  x({a}) median={median(xa_list):.4f} mean={mean(xa_list):.4f} | x({b}) median={median(xb_list):.4f} mean={mean(xb_list):.4f}")
            print(f"  x({a}) - x({b}): median={median(diff_x):+.4f}, mean={mean(diff_x):+.4f}, % where {a} has higher limit €: {sum(1 for e in euro_diff if e > 0)/len(euro_diff):.1%} (median Δ€={median(euro_diff):+.2f})")

    won_better_euro = 0
    won_better_sum = 0.0
    slower_higher_euro = 0
    slower_higher_sum = 0.0
    rank = {"same_day": 0, "next_day": 1, "within_3_days": 2}
    for rid, opts in by_rid.items():
        w = next((o for o in opts if o["desk"] == "won" and o["desk_option"] == o["option"]), None)
        if not w or not w["lo"]:
            continue
        best = max(opts, key=lambda o: o["lo"] or 0)
        if (best["lo"] or 0) > w["lo"]:
            won_better_euro += 1
            won_better_sum += (best["lo"] - w["lo"]) / 100.0
        slower = [o for o in opts if rank[o["option"]] > rank[w["option"]] and (o["lo"] or 0) > w["lo"]]
        if slower:
            best_slow = max(slower, key=lambda o: o["lo"] or 0)
            slower_higher_euro += 1
            slower_higher_sum += (best_slow["lo"] - w["lo"]) / 100.0
    print(f"On v5's 251 won orders: {won_better_euro} have a DIFFERENT option with higher € limit (+€{won_better_sum:,.2f} total); "
          f"{slower_higher_euro} have a STRICTLY SLOWER option with a HIGHER € limit (+€{slower_higher_sum:,.2f})!")

    # 3. Day & Hour & Outage / Price War anatomy on dev-12
    print("=== 3. LIMIT / LIST BY DAY AND WINDOW ON DEV-12 ===")
    primary = []
    for rid, opts in by_rid.items():
        cand = next((o for o in opts if o["option"] == "next_day" and o["lo"]), None) or next((o for o in opts if o["lo"]), None)
        if cand:
            primary.append(cand)

    days = ["Mon", "Tue", "Wed", "Thu", "Fri"]
    for d in range(5):
        sub_bh = [o["lo"] / o["list"] for o in primary if o["day"] == d and 8 * 60 <= o["at"] % 1440 < 18 * 60]
        sub_ev = [o["lo"] / o["list"] for o in primary if o["day"] == d and (o["at"] % 1440 < 8 * 60 or o["at"] % 1440 >= 18 * 60)]
        print(f"  {days[d]} 08-18 (n={len(sub_bh):3d}): median={median(sub_bh):.4f}, mean={mean(sub_bh):.4f}, min={min(sub_bh):.3f}, max={max(sub_bh):.3f}"
              + (f" | off-hours (n={len(sub_ev):2d}): median={median(sub_ev):.4f}" if sub_ev else ""))

    tue_bh = [o for o in primary if o["day"] == 1 and 8 * 60 <= o["at"] % 1440 < 18 * 60]
    best_town, best_sep = None, -1.0
    for place in geo.places:
        inside = [o["lo"] / o["list"] for o in tue_bh if geo.line_km(place, o["pickup"]) <= 80.0]
        outside = [o["lo"] / o["list"] for o in tue_bh if geo.line_km(place, o["pickup"]) > 80.0]
        if len(inside) >= 15 and len(outside) >= 15:
            sep = median(inside) - median(outside)
            if sep > best_sep:
                best_sep, best_town = sep, (place, len(inside), median(inside), len(outside), median(outside))
    if best_town:
        print(f"  Tue outage best 80km center: {best_town[0]} -> inside (n={best_town[1]}) median={best_town[2]:.4f} vs outside (n={best_town[3]}) median={best_town[4]:.4f} (ratio={best_town[2]/best_town[4]:.3f})")

    # 4. Lane difficulty / delivery supply / ref-to-list ratio on normal days (Mon, Wed, Thu)
    print("=== 4. LANE STRUCTURE: DELIVERY SUPPLY & REF/LIST ON NORMAL DAYS (Mon, Wed, Thu) ===")
    norm = [o for o in primary if o["day"] in (0, 2, 3)]
    buckets_deliv = [("Deliv supply < 15 (dead-end)", lambda s: s < 15),
                     ("Deliv supply 15..59 (small)", lambda s: 15 <= s < 60),
                     ("Deliv supply 60..199 (regional hub)", lambda s: 60 <= s < 200),
                     ("Deliv supply >= 200 (Capital hub)", lambda s: s >= 200)]
    for label, pred in buckets_deliv:
        vals = [(o["lo"] / o["list"]) / (1 + 0.01 * o["trust"]) for o in norm if pred(supply30.get(o["delivery"], 0))]
        raw = [o["lo"] / o["list"] for o in norm if pred(supply30.get(o["delivery"], 0))]
        if vals:
            print(f"  {label:<36} n={len(vals):3d} | raw median={median(raw):.4f} | trust-adj median={median(vals):.4f}, mean={mean(vals):.4f}")

    buckets_ref = [("ref/list < 0.55 (easy/return)", lambda r: r < 0.55),
                   ("ref/list 0.55..0.68", lambda r: 0.55 <= r < 0.68),
                   ("ref/list 0.68..0.82", lambda r: 0.68 <= r < 0.82),
                   ("ref/list >= 0.82 (hard/dead-end)", lambda r: r >= 0.82)]
    for label, pred in buckets_ref:
        vals = [(o["lo"] / o["list"]) / (1 + 0.01 * o["trust"]) for o in norm if pred(o["ref"] / o["list"])]
        if vals:
            print(f"  {label:<36} n={len(vals):3d} | trust-adj median={median(vals):.4f}, mean={mean(vals):.4f}")

    # 5. Lost and Declined requests analysis on dev-12
    print("=== 5. LOST vs DECLINED OPPORTUNITIES ON DEV-12 ===")
    floor_mult = 1.25 / 0.92
    quoted_lost_above_floor = []
    declined_above_floor = []
    decline_reasons = defaultdict(list)

    for rid, opts in by_rid.items():
        r = reqs[rid]
        ref = r["referenceFeeCents"]
        floor_cents = ref * floor_mult
        best = max(opts, key=lambda o: (o["lo"] or 0))
        best_lo = best["lo"] or 0
        dec = best["decided"]
        won = any(o["desk"] == "won" for o in opts)
        if won:
            continue
        if dec in ("quote", "floor"):
            if best_lo >= floor_cents:
                quoted_lost_above_floor.append((rid, dec, best_lo, floor_cents, best))
        elif dec == "decline":
            if best_lo >= floor_cents:
                declined_above_floor.append((rid, best_lo, floor_cents, best))
                p_place = r["legs"][0]["pickup"]["placeId"]
                gs = supply55.get(p_place, 0)
                legs = r["legs"]
                drive = sum(geo.minutes(l["pickup"]["placeId"], l["delivery"]["placeId"]) for l in legs)
                if len(legs) == 2:
                    drive += geo.minutes(legs[0]["delivery"]["placeId"], legs[1]["pickup"]["placeId"])
                if gs < 22:
                    reason = "gate_supply<22"
                else:
                    ready = max([r["arrivedAt"]] + [l["pickup"]["window"]["from"] for l in legs])
                    any_opt_ok = False
                    for o in r["options"]:
                        if drive > 300 and o["deadline"] // 1440 <= ready // 1440:
                            continue
                        if o["kind"] == "same_day" and supply30.get(p_place, 0) < 100:
                            continue
                        if supply30.get(p_place, 0) < 22 and o["kind"] == "same_day":
                            continue
                        if o["deadline"] - ready - drive >= 180 + 0.5 * drive:
                            any_opt_ok = True
                    reason = "backlog_cap" if any_opt_ok else "slack_or_same_day_gate"
                decline_reasons[reason].append((best_lo - ref * 0.95) / 100.0)

    print(f"Quoted/floored by v5, LOST, yet limit >= 1.359*ref (v5 floor): {len(quoted_lost_above_floor)} requests! "
          f"Potential net margin at 0.95*ref fee: €{sum((x[2] - reqs[x[0]]['referenceFeeCents']*0.95)/100 for x in quoted_lost_above_floor):,.2f}")
    by_dec = defaultdict(int)
    for x in quoted_lost_above_floor:
        by_dec[x[1]] += 1
    print(f"  Breakdown by v5 decision: {dict(by_dec)}")

    print(f"Declined by v5, yet limit >= 1.359*ref: {len(declined_above_floor)} requests! "
          f"Potential net margin at 0.95*ref fee: €{sum((x[1] - reqs[x[0]]['referenceFeeCents']*0.95)/100 for x in declined_above_floor):,.2f}")
    for reason, margins in sorted(decline_reasons.items()):
        print(f"  Decline reason '{reason}': n={len(margins)}, potential net margin (@0.95*ref) = €{sum(margins):,.2f} (median €{median(margins):.2f})")

    # 6. Where did v5 leave money on WON orders across all 4 worlds?
    print("=== 6. WHERE v5 LEFT MONEY ON ITS WON ORDERS (ALL 4 WORLDS!) ===")
    for seed in ["dev-12", "dev-01", "dev-08", "dev-07"]:
        wlines = load_jsonl(tas_dir / seed / "limits-won-apply.jsonl")
        tp = json.loads((tas_dir / seed / "tape.json").read_text(encoding="utf-8"))
        s30 = geo.supply(tp["roster"], 30.0)
        by_type = defaultdict(list)
        by_trust = defaultdict(list)
        by_dsup = defaultdict(list)
        for w in wlines:
            gap = (w["lo"] - w["desk_cents"]) / 100.0
            by_type[w["decided"]].append(gap)
            tb = "trust 0..4" if w["trust"] < 5 else ("trust 5..14" if w["trust"] < 15 else "trust 15..25")
            by_trust[tb].append((gap, w["lo"] / w["list"], w["desk_cents"] / w["list"]))
            ds = s30.get(w["delivery"], 0)
            db = "deliv<30" if ds < 30 else ("deliv 30..149" if ds < 150 else "deliv>=150")
            by_dsup[db].append((gap, w["lo"] / w["list"], w["desk_cents"] / w["list"]))
        print(f"  [{seed}] Total won={len(wlines)}, total gap=€{sum((w['lo']-w['desk_cents'])/100 for w in wlines):,.2f}:")
        for k, v in sorted(by_type.items()):
            print(f"    decided={k:<8}: n={len(v):3d}, gap=€{sum(v):7.2f} (mean €{mean(v):5.2f}/car)")
        for k in ["trust 0..4", "trust 5..14", "trust 15..25"]:
            v = by_trust[k]
            if v:
                print(f"    {k:<12}: n={len(v):3d}, gap=€{sum(x[0] for x in v):7.2f} (mean €{mean(x[0] for x in v):5.2f}/car, med lim_x={median(x[1] for x in v):.3f} vs desk_x={median(x[2] for x in v):.3f})")
        for k in ["deliv<30", "deliv 30..149", "deliv>=150"]:
            v = by_dsup[k]
            if v:
                print(f"    {k:<12}: n={len(v):3d}, gap=€{sum(x[0] for x in v):7.2f} (mean €{mean(x[0] for x in v):5.2f}/car, med lim_x={median(x[1] for x in v):.3f} vs desk_x={median(x[2] for x in v):.3f})")

    # 7. Cross-world lane stability (Idea 28)
    print("=== 7. CROSS-WORLD LANE & DELIVERY-PLACE STABILITY ACROSS 4 WORLDS ===")
    world_deliv_x: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for seed in ["dev-12", "dev-01", "dev-08", "dev-07"]:
        wlines = load_jsonl(tas_dir / seed / "limits-won-apply.jsonl")
        med_world = median((w["lo"] / w["list"]) / (1 + 0.01 * w["trust"]) for w in wlines)
        for w in wlines:
            rel = ((w["lo"] / w["list"]) / (1 + 0.01 * w["trust"])) / med_world
            world_deliv_x[w["delivery"]][seed].append(rel)

    common_delivs = [d for d, m in world_deliv_x.items() if sum(len(v) for v in m.values()) >= 12 and len(m) >= 3]
    rows_d = []
    for d in common_delivs:
        per_s = [median(v) for v in world_deliv_x[d].values()]
        rows_d.append((mean(per_s), min(per_s), max(per_s), sum(len(v) for v in world_deliv_x[d].values()), d))
    rows_d.sort()
    print("  Delivery towns (trust- and world-median-normalized limit/list across >=3 worlds):")
    for avg_r, mn_r, mx_r, cnt, d in rows_d[:8] + rows_d[-8:]:
        print(f"    {d:<16} (n={cnt:3d}): mean_rel={avg_r:.3f} [min={mn_r:.3f}, max={mx_r:.3f}]")


if __name__ == "__main__":
    main()
