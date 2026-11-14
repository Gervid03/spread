"""Zero-slot X-ray of TAS oracle limits (`limits-all.jsonl` on dev-12 + `limits-won-apply.jsonl` on 4 worlds).

Answers:
1. Where does the +€4,821/wk (+39.5%) oracle gain sit across the 4 TAS worlds?
2. What is the exact structural equation of `log(limit / list)` and what is the residual noise `sigma`?
3. On multi-option requests in `limits-all.jsonl`, how does `limit / list` compare across `same_day`, `next_day`, `within_3_days`?
4. Within-dealer, within-day, and within-batch correlation of residuals: how accurately can a live desk track a dealer-day's true limit?
"""
from __future__ import annotations

import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from spread_lab.geo import Geo

# Out-of-sample 64-world lane effects (fitted strictly on night-01..32 + final-01..32; zero dev/holdout data)
LANE_PICKUP: dict[str, float] = {
    "espoo": 0.01801, "hameenlinna": -0.0375, "helsinki": -0.00067, "hyvinkaa": 0.01002, "joensuu": 0.03729,
    "jyvaskyla": -0.04095, "kajaani": 0.0, "kemi": 0.0, "kokkola": 0.00167, "kotka": -0.03791,
    "kouvola": -0.06463, "kuopio": -0.04077, "lahti": -0.03409, "lappeenranta": -0.02084, "lempaala": -0.04688,
    "mikkeli": -0.01258, "oulu": -0.04536, "pori": -0.02751, "porvoo": -0.00202, "raisio": -0.03281,
    "rauma": -0.01399, "rovaniemi": -0.03244, "salo": -0.05621, "savonlinna": 0.0, "seinajoki": 0.01883,
    "tampere": -0.03634, "turku": -0.03561, "vaasa": -0.01609, "vantaa": 0.03766, "ylivieska": 0.0,
}
LANE_DELIVERY: dict[str, float] = {
    "espoo": -0.05554, "hameenlinna": 0.02676, "helsinki": -0.06611, "hyvinkaa": -0.05914, "joensuu": 0.09158,
    "jyvaskyla": 0.05259, "kajaani": 0.13239, "kemi": 0.13471, "kokkola": 0.11852, "kotka": 0.08248,
    "kouvola": 0.078, "kuopio": 0.06653, "lahti": 0.04447, "lappeenranta": 0.0861, "lempaala": 0.0072,
    "mikkeli": 0.09635, "oulu": 0.05905, "pori": 0.09169, "porvoo": -0.0445, "raisio": 0.03204,
    "rauma": 0.06667, "rovaniemi": 0.09226, "salo": 0.04131, "savonlinna": 0.104, "seinajoki": 0.08591,
    "tampere": 0.02508, "turku": 0.03272, "vaasa": 0.08048, "vantaa": -0.10655, "ylivieska": 0.13922,
}


def lane_eff(pick: str, dest: str) -> float:
    return LANE_PICKUP.get(pick, 0.0) + LANE_DELIVERY.get(dest, 0.0)


def ols_1d(xs: list[float], ys: list[float]) -> tuple[float, float, float]:
    mx = statistics.mean(xs)
    my = statistics.mean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    syy = sum((y - my) ** 2 for y in ys)
    b = sxy / sxx if sxx > 0 else 0.0
    a = my - b * mx
    r2 = (sxy * sxy) / (sxx * syy) if sxx > 0 and syy > 0 else 0.0
    return a, b, r2


def main() -> None:
    home = Path.home() / ".spread-lab"
    geo = Geo(json.loads((home / "map.json").read_text(encoding="utf-8")))
    tas_dir = home / "tas"
    seeds = ["dev-12", "dev-01", "dev-08", "dev-07"]

    # =========================================================================
    # PART 1: Decompose the €4,821/wk Oracle Gap across 4 worlds (1,138 won orders)
    # =========================================================================
    print("=" * 92)
    print("PART 1: DECOMPOSITION OF ORACLE HEADROOM (limits-won-apply.jsonl across 4 worlds)")
    print("=" * 92)

    all_won = []
    for seed in seeds:
        tape = json.loads((tas_dir / seed / "tape.json").read_text(encoding="utf-8"))
        reqs = {r["id"]: r for r in tape["requests"]}
        rows = [json.loads(l) for l in (tas_dir / seed / "limits-won-apply.jsonl").read_text().splitlines() if l.strip()]
        for row in rows:
            if row.get("lo") is None or row.get("desk_cents") is None:
                continue
            r = reqs[row["rid"]]
            gap_eur = (row["lo"] - row["desk_cents"]) / 100.0
            le = lane_eff(row["pickup"], row["delivery"])
            tod_h = (row["at"] % 1440) / 60.0
            row_ext = {
                **row,
                "seed": seed,
                "gap_eur": gap_eur,
                "quote_x": row["desk_cents"] / row["list"],
                "lim_x": row["lo"] / row["list"],
                "ratio_lim_to_quote": row["lo"] / max(1, row["desk_cents"]),
                "lane_eff": le,
                "lane_b": "low_inb" if le < -0.0375 else ("mid" if le < 0.0448 else "high_out"),
                "tod_h": tod_h,
                "batch": r.get("batchId"),
                "n_opts_req": len(r["options"]),
                "has_sd_req": any(o["kind"] == "same_day" for o in r["options"]),
            }
            all_won.append(row_ext)

    tot_gap = sum(r["gap_eur"] for r in all_won)
    print(f"Total won rows: {len(all_won)} across 4 worlds | Total headroom: €{tot_gap:,.2f} (€{tot_gap/4:,.2f}/world, €{tot_gap/len(all_won):.2f}/order)")

    def show_breakdown(title: str, key_fn) -> None:
        groups = defaultdict(list)
        for r in all_won:
            groups[key_fn(r)].append(r)
        print()
        print(f"--- By {title} ---")
        print(f"  {'Bucket':<20} {'N':>5} {'Total €':>10} {'€/wk':>8} {'€/ord':>7} {'Med Quote×':>10} {'Med Lim×':>9} {'Med Lim/Q':>9} {'Share%':>7}")
        for k in sorted(groups.keys()):
            g = groups[k]
            s = sum(x["gap_eur"] for x in g)
            mq = statistics.median(x["quote_x"] for x in g)
            ml = statistics.median(x["lim_x"] for x in g)
            mr = statistics.median(x["ratio_lim_to_quote"] for x in g)
            print(f"  {str(k):<20} {len(g):>5} {s:>10.1f} {s/4:>8.1f} {s/len(g):>7.2f} {mq:>10.3f} {ml:>9.3f} {mr:>9.3f} {100*s/tot_gap:>6.1f}%")

    show_breakdown("Seed", lambda r: r["seed"])
    show_breakdown("Day (0=Mon..4=Fri)", lambda r: f"d{r['day']}")
    show_breakdown("Trust bucket", lambda r: "0_t0" if r["trust"] == 0 else ("1_t1-5" if r["trust"] <= 5 else ("2_t6-14" if r["trust"] <= 14 else ("3_t15-24" if r["trust"] <= 24 else "4_t25"))))
    show_breakdown("Option won", lambda r: r["option"])
    show_breakdown("Desk decision", lambda r: r["decided"])
    show_breakdown("Lane tercile (64w)", lambda r: r["lane_b"])
    show_breakdown("Time of day", lambda r: "08-10" if r["tod_h"] < 10 else ("10-12" if r["tod_h"] < 12 else ("12-15" if r["tod_h"] < 15 else "15+")))
    show_breakdown("Lim/Quote outlier (>1.35 = Outage?)", lambda r: "outage_like(>1.35xQ)" if r["ratio_lim_to_quote"] > 1.35 else "normal_gap(<=1.35xQ)")

    # Let's inspect outage clusters across the 4 worlds!
    print()
    print("--- Inspecting high Lim/List clusters (lim_x >= 1.90) by (seed, day, pickup) ---")
    high_clusters = Counter((r["seed"], r["day"], r["pickup"]) for r in all_won if r["lim_x"] >= 1.90 and r["trust"] < 15)
    for k, cnt in high_clusters.most_common(15):
        sample_x = [round(r["lim_x"], 2) for r in all_won if (r["seed"], r["day"], r["pickup"]) == k][:6]
        print(f"  {k}: n={cnt}, sample lim_x={sample_x}")

    # =========================================================================
    # PART 2: Structural Equation of `log(limit / list)` on `dev-12` (`limits-all.jsonl`, ALL 1,833 rows!)
    # =========================================================================
    print()
    print("=" * 92)
    print("PART 2: EXACT GENERATIVE MODEL ON dev-12 limits-all.jsonl (ALL 1,036 REQUESTS, 1,833 OPTIONS)")
    print("=" * 92)

    tape12 = json.loads((tas_dir / "dev-12" / "tape.json").read_text(encoding="utf-8"))
    reqs12 = {r["id"]: r for r in tape12["requests"]}
    lall = [json.loads(l) for l in (tas_dir / "dev-12" / "limits-all.jsonl").read_text().splitlines() if l.strip()]
    exact_rows = [r for r in lall if r.get("bound") == "exact" and r.get("lo")]
    print(f"Total rows: {len(lall)} | Bound counts: {Counter(r['bound'] for r in lall)}")

    # 2A. Same-request option comparison!
    by_rid = defaultdict(dict)
    for r in exact_rows:
        by_rid[r["rid"]][r["option"]] = r

    sa_ne_diffs = []
    ne_wi_diffs = []
    sa_wi_diffs = []
    for rid, opts in by_rid.items():
        if "same_day" in opts and "next_day" in opts:
            sa_ne_diffs.append(math.log(opts["same_day"]["x"] / opts["next_day"]["x"]))
        if "next_day" in opts and "within_3_days" in opts:
            ne_wi_diffs.append(math.log(opts["next_day"]["x"] / opts["within_3_days"]["x"]))
        if "same_day" in opts and "within_3_days" in opts:
            sa_wi_diffs.append(math.log(opts["same_day"]["x"] / opts["within_3_days"]["x"]))

    print()
    print("--- 2A. Within-Request Option Multipliers (log(x_optA / x_optB) on THE EXACT SAME REQUEST!) ---")
    for label, diffs in [("same_day vs next_day", sa_ne_diffs), ("next_day vs within_3_days", ne_wi_diffs), ("same_day vs within_3_days", sa_wi_diffs)]:
        if diffs:
            print(
                f"  {label:<28}: n={len(diffs):>4} | mean={statistics.mean(diffs):+.4f} ({math.exp(statistics.mean(diffs)):.4f}x) | "
                f"med={statistics.median(diffs):+.4f} | stdev={statistics.stdev(diffs):.4f} | min={min(diffs):+.4f} max={max(diffs):+.4f}"
            )

    # Wait: why would `next_day` have a lower or higher `x` when `same_day` is ALSO offered on the request vs when `next_day` is the fastest option?!
    print()
    print("--- 2B. Does `next_day` limit/list depend on whether `same_day` existed on `request['options']`?! ---")
    nd_with_sd = []
    nd_without_sd = []
    w3d_with_sd = []
    w3d_only_slow = []
    for r in exact_rows:
        req = reqs12[r["rid"]]
        kinds = {o["kind"] for o in req["options"]}
        # Normalize out trust and 64w lane effect first!
        y_adj = math.log(r["x"]) - math.log(1.0 + 0.01 * r["trust"]) - lane_eff(r["pickup"], r["delivery"])
        if r["option"] == "next_day":
            if "same_day" in kinds:
                nd_with_sd.append((y_adj, r["day"], r))
            else:
                nd_without_sd.append((y_adj, r["day"], r))
        elif r["option"] == "within_3_days":
            if "same_day" in kinds:
                w3d_with_sd.append((y_adj, r["day"], r))
            else:
                w3d_only_slow.append((y_adj, r["day"], r))

    print(f"  next_day when request ALSO had same_day   : n={len(nd_with_sd):>4}, mean adj log(x)={statistics.mean(x[0] for x in nd_with_sd):+.4f} ({math.exp(statistics.mean(x[0] for x in nd_with_sd)):.4f}x)")
    print(f"  next_day when next_day WAS fastest option : n={len(nd_without_sd):>4}, mean adj log(x)={statistics.mean(x[0] for x in nd_without_sd):+.4f} ({math.exp(statistics.mean(x[0] for x in nd_without_sd)):.4f}x)")
    if w3d_with_sd and w3d_only_slow:
        print(f"  within_3d when request ALSO had same_day  : n={len(w3d_with_sd):>4}, mean adj log(x)={statistics.mean(x[0] for x in w3d_with_sd):+.4f} ({math.exp(statistics.mean(x[0] for x in w3d_with_sd)):.4f}x)")
        print(f"  within_3d when request had NO same_day    : n={len(w3d_only_slow):>4}, mean adj log(x)={statistics.mean(x[0] for x in w3d_only_slow):+.4f} ({math.exp(statistics.mean(x[0] for x in w3d_only_slow)):.4f}x)")

    # Let's check day by day on dev-12!
    print()
    print("--- 2C. Day-by-day limits on dev-12 (fastest option of each request, trust- and lane-adjusted) ---")
    fastest_rows = []
    for rid, r in reqs12.items():
        first_kind = r["options"][0]["kind"]
        if rid in by_rid and first_kind in by_rid[rid]:
            fastest_rows.append(by_rid[rid][first_kind])

    for d in range(5):
        sub = [r for r in fastest_rows if r["day"] == d]
        raw_x = [r["x"] for r in sub]
        nt_x = [r["x"] / (1.0 + 0.01 * r["trust"]) for r in sub]
        ntl_l = [math.log(r["x"]) - math.log(1.0 + 0.01 * r["trust"]) - lane_eff(r["pickup"], r["delivery"]) for r in sub]
        print(
            f"  Day {d}: n={len(sub):>3} | med raw x={statistics.median(raw_x):.3f} | "
            f"med x/(1+.01t)={statistics.median(nt_x):.3f} | stdev log(x)={statistics.stdev( math.log(z) for z in raw_x ):.4f} -> "
            f"after trust+lane stdev={statistics.stdev(ntl_l):.4f} (med {math.exp(statistics.median(ntl_l)):.3f}x)"
        )

    # Check slope of log(x / (1+.01*trust)) on lane_eff(pick, dest) on Monday..Thursday (excluding Friday war!)
    mon_thu_fast = [r for r in fastest_rows if r["day"] < 4]
    xs_lane = [lane_eff(r["pickup"], r["delivery"]) for r in mon_thu_fast]
    ys_nt = [math.log(r["x"]) - math.log(1.0 + 0.01 * r["trust"]) for r in mon_thu_fast]
    a, b, r2 = ols_1d(xs_lane, ys_nt)
    print()
    print(f"--- 2D. OLS of log(limit / (list*(1+0.01*trust))) on 64-world lane_eff (Mon-Thu fastest opt, n={len(mon_thu_fast)}) ---")
    print(f"  intercept = {a:+.4f} ({math.exp(a):.4f}x), slope on lane_eff = {b:+.4f}, R² = {r2:.4f}")

    # Residual variance decomposition!
    # Step 1: raw log(x) on Mon-Thu fastest opt
    s0 = statistics.stdev(math.log(r["x"]) for r in mon_thu_fast)
    # Step 2: remove trust
    s1 = statistics.stdev(ys_nt)
    # Step 3: remove 64w lane_eff (with fitted slope b and with unit slope 1.0)
    res_lane1 = [y - 1.0 * x for x, y in zip(xs_lane, ys_nt)]
    res_laneb = [y - b * x for x, y in zip(xs_lane, ys_nt)]
    # Step 4: remove (day, dealer) fixed effects!
    dd_groups = defaultdict(list)
    for r, rv in zip(mon_thu_fast, res_laneb):
        dd_groups[(r["day"], r["dealer"])].append((r, rv))
    within_dd_res = []
    for k, items in dd_groups.items():
        if len(items) >= 2:
            m = statistics.mean(v for _, v in items)
            for r, v in items:
                within_dd_res.append((r, v - m))
    s_within_dd = statistics.stdev(v for _, v in within_dd_res)

    # Step 5: within (day, batchId) residuals!
    batch_groups = defaultdict(list)
    for r, rv in zip(mon_thu_fast, res_laneb):
        b_id = reqs12[r["rid"]].get("batchId")
        if b_id:
            batch_groups[(r["day"], b_id)].append((r, rv))
    within_batch_res = []
    for k, items in batch_groups.items():
        if len(items) >= 2:
            m = statistics.mean(v for _, v in items)
            for r, v in items:
                within_batch_res.append((r, v - m))
    s_within_batch = statistics.stdev(v for _, v in within_batch_res) if within_batch_res else 0.0

    print()
    print("--- 2E. Variance / Noise (`sigma`) Waterfall on Mon-Thu Fastest Option (dev-12) ---")
    print(f"  Raw log(limit/list) stdev                       : {s0:.4f}")
    print(f"  After exact trust (1 + 0.01*trust)              : {s1:.4f}")
    print(f"  After 64w lane_eff (slope=1.00)                 : {statistics.stdev(res_lane1):.4f}")
    print(f"  After 64w lane_eff (slope={b:.2f})                 : {statistics.stdev(res_laneb):.4f}")
    print(f"  Within (day, dealer) stdev (n={len(within_dd_res):>3})              : {s_within_dd:.4f}")
    print(f"  Within (day, batchId) stdev (n={len(within_batch_res):>3})             : {s_within_batch:.4f}")

    # Check other covariates on within-(day, dealer) residuals!
    print()
    print("--- 2F. Covariates on within-(day, dealer) residuals (after trust + lane) ---")
    for name, fn in [
        ("tod_hour", lambda r: (r["at"] % 1440) / 60.0),
        ("log(ref/list)", lambda r: math.log(max(1, r["ref"]) / r["list"])),
        ("has_note", lambda r: 1.0 if r["note"] else 0.0),
        ("legs==2", lambda r: 1.0 if r["legs"] == 2 else 0.0),
        ("drive_hr", lambda r: geo.minutes(r["pickup"], r["delivery"]) / 60.0),
        ("is_next_day_fastest", lambda r: 1.0 if r["option"] == "next_day" else 0.0),
    ]:
        xs_c = [fn(r) for r, _ in within_dd_res]
        ys_c = [v for _, v in within_dd_res]
        _, bc, r2c = ols_1d(xs_c, ys_c)
        print(f"  {name:<22}: slope={bc:+.4f}, R²={r2c:.4f}")


if __name__ == "__main__":
    main()
