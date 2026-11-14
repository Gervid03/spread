"""Deep zero-slot analysis of:
1. Regional Outages & Price Wars across all 4 TAS worlds (`dev-12`, `dev-01`, `dev-08`, `dev-07`).
2. Option-structure pricing (`same_day`, `next_day` fastest vs stripped, `within_3_days`) in `dev-12/limits-all.jsonl` and 4 reveals.
3. Busy-dealer daily win shares (`<30%`, `30-69%`, `>=70%`) and trust contamination across 4 reveals.
4. Counterfactual simulation on `dev-12` (`limits-all.jsonl`, all 1,036 requests!) of live limit-based pricing rules.
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
    # 1. Option structure in dev-12 limits-all.jsonl
    # =========================================================================
    print("=" * 92)
    print("1. EXACT OPTION STRUCTURE ON dev-12 limits-all.jsonl (Mon-Thu, excl Fri price war)")
    print("=" * 92)
    tape12 = json.loads((tas_dir / "dev-12" / "tape.json").read_text(encoding="utf-8"))
    reqs12 = {r["id"]: r for r in tape12["requests"]}
    lall = [json.loads(l) for l in (tas_dir / "dev-12" / "limits-all.jsonl").read_text().splitlines() if l.strip()]

    opt_buckets = defaultdict(list)
    for row in lall:
        if row["day"] >= 4 or row.get("bound") != "exact" or not row.get("lo"):
            continue
        req = reqs12[row["rid"]]
        opt_set = "+".join(o["kind"][:2] for o in req["options"])
        y_adj = math.log(row["x"]) - math.log(1.0 + 0.01 * row["trust"]) - 0.80 * lane_eff(row["pickup"], row["delivery"])
        opt_buckets[(opt_set, row["option"])].append((y_adj, row["x"], row["list"]))

    print(f"  {'Req Options':<14} {'Probed Opt':<15} {'N':>4} {'Mean adj log(x)':>16} {'Exp(mean)':>10} {'Med raw x':>10} {'Stdev adj':>10}")
    for (oset, opt), vals in sorted(opt_buckets.items()):
        ys = [v[0] for v in vals]
        xs = [v[1] for v in vals]
        print(
            f"  {oset:<14} {opt:<15} {len(vals):>4} {statistics.mean(ys):>+16.4f} "
            f"{math.exp(statistics.mean(ys)):>10.4f} {statistics.median(xs):>10.3f} {statistics.stdev(ys) if len(ys)>1 else 0:>10.4f}"
        )

    # Check if world-specific place random effects explain the remaining 0.1166 within-(day,dealer) stdev!
    mon_thu_fast = []
    by_rid = defaultdict(dict)
    for r in lall:
        if r.get("bound") == "exact" and r.get("lo"):
            by_rid[r["rid"]][r["option"]] = r
    for rid, req in reqs12.items():
        fk = req["options"][0]["kind"]
        if req["arrivedAt"] // 1440 < 4 and fk in by_rid[rid]:
            mon_thu_fast.append(by_rid[rid][fk])

    # Fit (day, dealer) + world-specific pickup + world-specific delivery by alternating projections on dev-12 Mon-Thu
    res = [math.log(r["x"]) - math.log(1.0 + 0.01 * r["trust"]) - 0.80 * lane_eff(r["pickup"], r["delivery"]) for r in mon_thu_fast]
    for _ in range(15):
        # remove (day, dealer) mean
        g_dd = defaultdict(list)
        for i, r in enumerate(mon_thu_fast):
            g_dd[(r["day"], r["dealer"])].append(i)
        for idxs in g_dd.values():
            m = statistics.mean(res[i] for i in idxs)
            for i in idxs:
                res[i] -= m
        # remove pickup mean
        g_p = defaultdict(list)
        for i, r in enumerate(mon_thu_fast):
            g_p[r["pickup"]].append(i)
        for idxs in g_p.values():
            m = statistics.mean(res[i] for i in idxs)
            for i in idxs:
                res[i] -= m
        # remove delivery mean
        g_d = defaultdict(list)
        for i, r in enumerate(mon_thu_fast):
            g_d[r["delivery"]].append(i)
        for idxs in g_d.values():
            m = statistics.mean(res[i] for i in idxs)
            for i in idxs:
                res[i] -= m
    print()
    print(f"  Residual stdev after (day,dealer) + world-specific pickup + delivery on dev-12 Mon-Thu: {statistics.stdev(res):.4f}")

    # Also check: on dev-12 Mon-Thu, which day had the Outage?! Let's check mean residual by (day, pickup) and 80km circles!
    print()
    print("--- Identifying Exact Outage Circle & Price War Day on dev-12 (from limits-all.jsonl) ---")
    for d in range(5):
        day_rows = [by_rid[rid][req["options"][0]["kind"]] for rid, req in reqs12.items() if req["arrivedAt"] // 1440 == d and req["options"][0]["kind"] in by_rid[rid]]
        best_c = None
        for c in places:
            in_c = [math.log(r["x"]) - math.log(1.0 + 0.01 * r["trust"]) - 0.80 * lane_eff(r["pickup"], r["delivery"]) for r in day_rows if geo.line_km(c, r["pickup"]) <= 80.0]
            out_c = [math.log(r["x"]) - math.log(1.0 + 0.01 * r["trust"]) - 0.80 * lane_eff(r["pickup"], r["delivery"]) for r in day_rows if geo.line_km(c, r["pickup"]) > 80.0]
            if len(in_c) >= 15 and len(out_c) >= 15:
                diff = statistics.mean(in_c) - statistics.mean(out_c)
                if best_c is None or diff > best_c[0]:
                    best_c = (diff, c, len(in_c), statistics.mean(in_c), statistics.mean(out_c))
        all_adj = [math.log(r["x"]) - math.log(1.0 + 0.01 * r["trust"]) - 0.80 * lane_eff(r["pickup"], r["delivery"]) for r in day_rows]
        print(
            f"  Day {d}: overall mean adj={statistics.mean(all_adj):+.4f} ({math.exp(statistics.mean(all_adj)):.3f}x) | "
            f"max 80km jump: {best_c[1]:<12} diff={best_c[0]:+.4f} ({math.exp(best_c[0]):.3f}x, n_in={best_c[2]}, in={math.exp(best_c[3]):.3f}x vs out={math.exp(best_c[4]):.3f}x)"
        )

    # =========================================================================
    # 2. Across all 4 TAS worlds: Outage & Price War detection from live quote outcomes (reveal-v5.json)
    # =========================================================================
    print()
    print("=" * 92)
    print("2. LIVE SIGNAL CHECK ACROSS ALL 4 TAS WORLDS (reveal-v5.json + limits-won-apply.jsonl)")
    print("=" * 92)

    for seed in seeds:
        rev = json.loads((tas_dir / seed / "reveal-v5.json").read_text(encoding="utf-8"))
        won_lim = {
            json.loads(l)["rid"]: json.loads(l)
            for l in (tas_dir / seed / "limits-won-apply.jsonl").read_text().splitlines()
            if l.strip()
        }
        print()
        print(f"=== {seed} ===")
        # Reconstruct quoted (non-decline) requests per day
        q_by_day = defaultdict(list)
        dlr_day_tot = Counter()
        dlr_day_won = Counter()
        for item in rev["requests"]:
            req = item["request"]
            d = req["arrivedAt"] // 1440
            tod = req["arrivedAt"] % 1440
            dlr = req["dealerId"]
            dlr_day_tot[(dlr, d)] += 1
            if item["outcome"] == "won":
                dlr_day_won[(dlr, d)] += 1
            q = item.get("quote") or {}
            if not q:
                continue
            first_k = next(iter(q))
            lst = next(o["listPriceCents"] for o in req["options"] if o["kind"] == first_k)
            ratio = q[first_k] / lst
            if ratio >= 3.5:  # decline_mult = 4.0
                continue
            q_by_day[d].append((tod, req["legs"][0]["pickup"]["placeId"], req["legs"][-1]["delivery"]["placeId"], dlr, ratio, item["outcome"] == "won", req["id"]))

        for d in range(5):
            qs = q_by_day[d]
            morn = [x for x in qs if x[0] <= 9 * 60 + 45]  # by 09:45
            tot_w = sum(1 for x in qs if x[5])
            morn_w = sum(1 for x in morn if x[5])
            # Find best 80km circle by 10:15!
            early = [x for x in qs if x[0] <= 10 * 60 + 15]
            best_reg = None
            for c in places:
                inc = [x for x in early if geo.line_km(c, x[1]) <= 80.0]
                outc = [x for x in early if geo.line_km(c, x[1]) > 80.0]
                if len(inc) >= 6:
                    wr_in = sum(1 for x in inc if x[5]) / len(inc)
                    wr_out = (sum(1 for x in outc if x[5]) / len(outc)) if outc else 0.0
                    full_inc = [x for x in qs if geo.line_km(c, x[1]) <= 80.0]
                    gap_in = sum((won_lim[x[6]]["lo"] - won_lim[x[6]]["desk_cents"]) / 100.0 for x in full_inc if x[5] and x[6] in won_lim and won_lim[x[6]].get("lo"))
                    score = (wr_in, len(inc))
                    if best_reg is None or score > best_reg[0]:
                        best_reg = (score, c, len(inc), wr_in, len(outc), wr_out, len(full_inc), sum(1 for x in full_inc if x[5]), gap_in)
            reg_str = "none"
            if best_reg:
                _, c, ni, wri, no, wro, fni, fnw, gin = best_reg
                reg_str = f"top80km<=10:15 {c} {wri*100:4.0f}%({int(round(wri*ni))}/{ni}) vs out {wro*100:4.0f}%({int(round(wro*no))}/{no}) | day_in {fnw}/{fni} gap=€{gin:,.0f}"
            print(f"  Day {d}: quotes={len(qs):>3} won={tot_w:>3} ({100*tot_w/max(1,len(qs)):4.1f}%) | <=09:45 {morn_w:>2}/{len(morn):<2} ({100*morn_w/max(1,len(morn)):4.0f}%) | {reg_str}")

        # Busy dealers (>=10 reqs/day) on Mon..Thu
        busy_events = []
        for (dlr, d), tot in sorted(dlr_day_tot.items()):
            if d < 4 and tot >= 10:
                w = dlr_day_won[(dlr, d)]
                sh = w / tot
                tag = "HIKE(+4%)" if sh < 0.30 else ("CUT(-4%)!" if sh >= 0.70 else "flat")
                busy_events.append(f"d{d}:{dlr}={w}/{tot}({sh*100:.0f}%:{tag})")
        print("  Busy dealers Mon-Thu:", ", ".join(busy_events))


if __name__ == "__main__":
    main()
