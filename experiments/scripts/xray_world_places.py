"""Zero-slot X-ray across all 4 TAS worlds (`dev-12`, `dev-01`, `dev-08`, `dev-07`):
1. Measure world-specific pickup & delivery place factors in `limits-all.jsonl` (dev-12) and `limits-won-apply.jsonl` + `reveal-v5.json` (all 4 worlds).
2. Check whether Mon-Tue town win rates / residuals predict Wed-Fri town win rates & limit headroom within the same world!
3. Check ALL other request fields (`car.premium`, `car.electric`, `privateAddress`, `legs`, `hours`, `batchId`) in `limits-all.jsonl`!
"""
from __future__ import annotations

import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from analyze_r4_limits import lane_eff


def main() -> None:
    tas_dir = Path.home() / ".spread-lab" / "tas"
    seeds = ["dev-12", "dev-01", "dev-08", "dev-07"]

    # 1. Check ALL request fields on dev-12 limits-all.jsonl (after removing day+dealer+trust+static_lane)!
    tape12 = json.loads((tas_dir / "dev-12" / "tape.json").read_text(encoding="utf-8"))
    reqs12 = {r["id"]: r for r in tape12["requests"]}
    lall = [json.loads(l) for l in (tas_dir / "dev-12" / "limits-all.jsonl").read_text().splitlines() if l.strip()]
    by_rid = defaultdict(dict)
    for r in lall:
        if r.get("bound") == "exact" and r.get("lo"):
            by_rid[r["rid"]][r["option"]] = r

    fast12 = []
    for rid, req in reqs12.items():
        fk = req["options"][0]["kind"]
        if req["arrivedAt"] // 1440 < 4 and fk in by_rid[rid]:
            r = by_rid[rid][fk]
            y = math.log(r["x"]) - math.log(1.0 + 0.01 * r["trust"]) - 0.80 * lane_eff(r["pickup"], r["delivery"])
            fast12.append((r, req, y))

    # Remove (day, dealer) mean
    dd_map = defaultdict(list)
    for r, req, y in fast12:
        dd_map[(r["day"], r["dealer"])].append(y)
    dd_mean = {k: statistics.mean(v) for k, v in dd_map.items()}
    res_dd = [(r, req, y - dd_mean[(r["day"], r["dealer"])]) for r, req, y in fast12 if len(dd_map[(r["day"], r["dealer"])]) >= 2]

    print("=" * 92)
    print("1. CHECKING REQUEST FEATURES ON WITHIN-(DAY,DEALER) RESIDUALS ON dev-12 (n=" + str(len(res_dd)) + ")")
    print("=" * 92)
    for feat_name, feat_fn in [
        ("car.premium", lambda req: req["legs"][0]["car"]["premium"]),
        ("car.electric", lambda req: req["legs"][0]["car"]["electric"]),
        ("pickup.privateAddress", lambda req: req["legs"][0]["pickup"]["privateAddress"]),
        ("delivery.privateAddress", lambda req: req["legs"][-1]["delivery"]["privateAddress"]),
        ("legs == 2", lambda req: len(req["legs"]) == 2),
        ("has_batchId", lambda req: req.get("batchId") is not None),
    ]:
        g_t = [v for _, req, v in res_dd if feat_fn(req)]
        g_f = [v for _, req, v in res_dd if not feat_fn(req)]
        if g_t and g_f:
            print(f"  {feat_name:<25}: True(n={len(g_t):>3})={statistics.mean(g_t):+.4f} vs False(n={len(g_f):>3})={statistics.mean(g_f):+.4f} | diff={statistics.mean(g_t)-statistics.mean(g_f):+.4f}")

    # Check Mon-Tue vs Wed-Thu stability of world-specific pickup & delivery effects on dev-12!
    print()
    print("=" * 92)
    print("2. MON-TUE vs WED-THU STABILITY OF WORLD-SPECIFIC PLACE EFFECTS ON dev-12 (limits-all)")
    print("=" * 92)
    pick_mt, pick_wt = defaultdict(list), defaultdict(list)
    deliv_mt, deliv_wt = defaultdict(list), defaultdict(list)
    pair_mt, pair_wt = defaultdict(list), defaultdict(list)
    for r, req, v in res_dd:
        if r["day"] in (0, 1):
            pick_mt[r["pickup"]].append(v)
            deliv_mt[r["delivery"]].append(v)
            pair_mt[(r["pickup"], r["delivery"])].append(v)
        elif r["day"] in (2, 3):
            pick_wt[r["pickup"]].append(v)
            deliv_wt[r["delivery"]].append(v)
            pair_wt[(r["pickup"], r["delivery"])].append(v)

    for label, mt, wt, min_n in [("Pickup town", pick_mt, pick_wt, 5), ("Delivery town", deliv_mt, deliv_wt, 5), ("Exact (pick,deliv) pair", pair_mt, pair_wt, 3)]:
        xs, ys = [], []
        for k in mt:
            if len(mt[k]) >= min_n and len(wt.get(k, [])) >= min_n:
                xs.append(statistics.mean(mt[k]))
                ys.append(statistics.mean(wt[k]))
        if len(xs) >= 4:
            mx, my = statistics.mean(xs), statistics.mean(ys)
            num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
            den = math.sqrt(sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys))
            corr = num / den if den > 0 else 0.0
            print(f"  {label:<25}: k={len(xs):>2} groups | Mon-Tue stdev={statistics.stdev(xs):.4f} | Wed-Thu stdev={statistics.stdev(ys):.4f} | corr(MonTue, WedThu) = {corr:+.4f}!")
            if label != "Exact (pick,deliv) pair":
                items = sorted([(k, statistics.mean(mt[k]), len(mt[k]), statistics.mean(wt[k]), len(wt[k])) for k in mt if len(mt[k]) >= min_n and len(wt.get(k, [])) >= min_n], key=lambda z: z[1])
                for k, m1, n1, m2, n2 in items[:4] + items[-4:]:
                    print(f"    {str(k):<16}: MonTue={m1:+.4f}(n={n1:>2}) -> WedThu={m2:+.4f}(n={n2:>2})")

    # 3. Check across all 4 TAS worlds: do world-specific delivery/pickup win-rate anomalies in Mon-Tue persist in Wed-Fri AND differ across worlds?!
    print()
    print("=" * 92)
    print("3. ACROSS ALL 4 TAS WORLDS: WORLD-SPECIFIC DELIVERY TOWN VARIATION (limits-won-apply + reveal-v5)")
    print("=" * 92)
    world_deliv_wr = defaultdict(dict)
    for seed in seeds:
        rev = json.loads((tas_dir / seed / "reveal-v5.json").read_text(encoding="utf-8"))
        mt_c, wt_c = defaultdict(lambda: [0, 0]), defaultdict(lambda: [0, 0])
        all_c = defaultdict(lambda: [0, 0])
        for item in rev["requests"]:
            req = item["request"]
            q = item.get("quote") or {}
            if not q:
                continue
            fk = next(iter(q))
            lst = next(o["listPriceCents"] for o in req["options"] if o["kind"] == fk)
            if q[fk] / lst >= 3.5:
                continue
            d = req["arrivedAt"] // 1440
            dest = req["legs"][-1]["delivery"]["placeId"]
            won = 1 if item["outcome"] == "won" else 0
            all_c[dest][1] += 1
            all_c[dest][0] += won
            if d <= 1:
                mt_c[dest][1] += 1
                mt_c[dest][0] += won
            else:
                wt_c[dest][1] += 1
                wt_c[dest][0] += won
        for dest, (w, n) in all_c.items():
            if n >= 10:
                world_deliv_wr[dest][seed] = f"{w}/{n}({100*w/n:.0f}%)"
        xs, ys = [], []
        for dest in mt_c:
            if mt_c[dest][1] >= 6 and wt_c[dest][1] >= 6:
                xs.append(mt_c[dest][0] / mt_c[dest][1])
                ys.append(wt_c[dest][0] / wt_c[dest][1])
        mx, my = statistics.mean(xs), statistics.mean(ys)
        corr = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / max(1e-9, math.sqrt(sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys)))
        print(f"  {seed}: delivery-town win-rate corr(MonTue, WedFri) across k={len(xs)} towns = {corr:+.4f}")

    print()
    print("  Delivery town win rates across the 4 worlds (notice how the SAME town flips from 10% in one world to 75% in another!):")
    for dest, smap in sorted(world_deliv_wr.items()):
        if len(smap) >= 3:
            row_s = " | ".join(f"{sd}: {smap.get(sd, '  -  '):<13}" for sd in seeds)
            print(f"    {dest:<14}: {row_s}")


if __name__ == "__main__":
    main()
