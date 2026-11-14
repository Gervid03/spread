"""Analyze `limits-all.jsonl` (all 1,036 requests!) + `reveal-v5.json` booked fee ratios on `dev-12` (0 network calls)."""
from __future__ import annotations

import json
import statistics
from collections import defaultdict
from pathlib import Path
from spread_lab.geo import Geo


def main() -> None:
    home = Path.home() / ".spread-lab"
    geo = Geo(json.loads((home / "map.json").read_text(encoding="utf-8")))
    tape = json.loads((home / "tas" / "dev-12" / "tape.json").read_text(encoding="utf-8"))
    rev = json.loads((home / "tas" / "dev-12" / "reveal-v5.json").read_text(encoding="utf-8"))
    reqs = {r["id"]: r for r in tape["requests"]}
    s30 = geo.supply(tape["roster"], 30.0)
    s55 = geo.supply(tape["roster"], 55.0)

    # 1. Empirical booked fee / ref in reveal-v5 by (dest_hub, drive_bucket, option)
    # Check gigs in reveal-v5
    gig_fees = {}
    for g in rev.get("gigs", []):
        gid = g.get("id") or g.get("gigId")
        if g.get("status") in ("completed", "delivered", "booked") or g.get("bookedFeeCents"):
            pass
    print("reveal keys:", list(rev.keys()))
    if rev.get("gigs"):
        print("sample gig keys:", list(rev["gigs"][0].keys()))

    # 2. True limit/ref and limit - expected_fee across all 1,036 requests in limits-all.jsonl!
    lall = [json.loads(l) for l in (home / "tas" / "dev-12" / "limits-all.jsonl").read_text().splitlines() if l.strip()]
    print(f"limits-all rows: {len(lall)}")

    buckets = defaultdict(list)
    best_by_rid = {}
    for row in lall:
        rid = row["rid"]
        r = reqs[rid]
        lo = row.get("lo")
        if not lo:
            continue
        p0 = r["legs"][0]["pickup"]["placeId"]
        d0 = r["legs"][-1]["delivery"]["placeId"]
        drv = geo.minutes(p0, d0)
        ps = s30.get(p0, 0)
        ds = s30.get(d0, 0)
        ref = r["referenceFeeCents"]
        list_c = row["list"]
        # Empirical solo fee model: hub->hub short is ~0.78x, hub->thin long (>200m) is ~1.12x!
        if ps >= 180 and ds >= 150:
            est_f_mult = 0.78
            bname = "hub->hub"
        elif ps >= 180 and drv <= 180:
            est_f_mult = 0.86
            bname = "hub->near(<3h)"
        elif ps >= 180:
            est_f_mult = 1.08
            bname = "hub->far(>3h)"
        elif s55.get(p0, 0) >= 180 and ds >= 150:
            est_f_mult = 0.84
            bname = "ring->hub"
        elif s55.get(p0, 0) >= 40 and drv <= 200:
            est_f_mult = 0.94
            bname = "reg->near"
        else:
            est_f_mult = 1.18
            bname = "thin/far"
        if row["option"] == "same_day":
            est_f_mult += 0.12
        est_m = (lo - ref * est_f_mult) / 100.0
        buckets[bname].append((est_m, lo / max(1, ref), list_c / max(1, ref), drv))
        if rid not in best_by_rid or est_m > best_by_rid[rid][0]:
            best_by_rid[rid] = (est_m, bname, row["option"], lo / 100.0, ref * est_f_mult / 100.0, r["dealerId"], r["arrivedAt"] // 1440)

    print()
    print("--- TRUE LIMIT / REF AND PROFITABILITY BY CORRIDOR CLASS ON dev-12 ---")
    for bname, vals in sorted(buckets.items(), key=lambda kv: -statistics.mean(x[0] for x in kv[1])):
        pos = [x[0] for x in vals if x[0] > 10]
        print(
            f"  {bname:<16}: n_opts={len(vals):>4} | list/ref={statistics.median(x[2] for x in vals):.2f}x | "
            f"lim/ref={statistics.median(x[1] for x in vals):.2f}x | mean_est_m=€{statistics.mean(x[0] for x in vals):>6.1f} | "
            f"n(m>€10)={len(pos):>3} (sum €{sum(pos):,.0f})"
        )

    top320 = sorted(best_by_rid.values(), key=lambda x: -x[0])[:320]
    print()
    print(f"Top 320 requests on dev-12 (at unsteered limits): sum est margin = €{sum(x[0] for x in top320):,.0f} (rev €{sum(x[3] for x in top320):,.0f}, est_fee €{sum(x[4] for x in top320):,.0f})")
    top260 = top320[:260]
    print(f"Top 260 requests on dev-12 (at unsteered limits): sum est margin = €{sum(x[0] for x in top260):,.0f} (rev €{sum(x[3] for x in top260):,.0f}, est_fee €{sum(x[4] for x in top260):,.0f})")


if __name__ == "__main__":
    main()
