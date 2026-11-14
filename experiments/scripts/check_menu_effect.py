"""Check x(next_day) with vs without same_day option, outage by leg/dealer, and exact regression of limit/list on dev-12."""
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
    s30 = geo.supply(tape["roster"], 30.0)
    lines = load_jsonl(d12_dir / "limits-all.jsonl")
    book_all = json.loads((d12_dir / "book-all.json").read_text(encoding="utf-8"))

    by_rid = defaultdict(list)
    for r in lines:
        by_rid[r["rid"]].append(r)

    # 1. Compare x(next_day) when request HAS same_day vs DOES NOT HAVE same_day!
    nd_with_sd, nd_no_sd = [], []
    w3_with_faster, w3_only = [], []
    sd_all = []
    for rid, opts in by_rid.items():
        opt_kinds = {o["kind"] for o in reqs[rid]["options"]}
        for o in opts:
            if not o["lo"]:
                continue
            x_adj = (o["lo"] / o["list"]) / (1 + 0.01 * o["trust"])
            if o["option"] == "same_day":
                sd_all.append(x_adj)
            elif o["option"] == "next_day":
                if "same_day" in opt_kinds:
                    nd_with_sd.append(x_adj)
                else:
                    nd_no_sd.append(x_adj)
            elif o["option"] == "within_3_days":
                if "same_day" in opt_kinds or "next_day" in opt_kinds:
                    w3_with_faster.append(x_adj)
                else:
                    w3_only.append(x_adj)

    print("=== 1. TRUST-ADJUSTED LIMIT/LIST BY OPTION MENU STRUCTURE (dev-12, ALL 1,036 REQS) ===")
    print(f"  same_day (n={len(sd_all):3d})                          : median={median(sd_all):.4f}, mean={mean(sd_all):.4f}")
    print(f"  next_day WITHOUT same_day on menu (n={len(nd_no_sd):3d}) : median={median(nd_no_sd):.4f}, mean={mean(nd_no_sd):.4f}")
    print(f"  next_day WITH same_day on menu    (n={len(nd_with_sd):3d}) : median={median(nd_with_sd):.4f}, mean={mean(nd_with_sd):.4f}  <-- COMPETING AGAINST COMPETITOR'S SAME_DAY!")
    if w3_only:
        print(f"  within_3_days ALONE on menu       (n={len(w3_only):3d}) : median={median(w3_only):.4f}, mean={mean(w3_only):.4f}")
    if w3_with_faster:
        print(f"  within_3_days WITH faster on menu (n={len(w3_with_faster):3d}) : median={median(w3_with_faster):.4f}, mean={mean(w3_with_faster):.4f}")

    # Check win rate of v5 when v5 quoted ONLY next_day on a menu WITH same_day vs WITHOUT same_day!
    won_nd_with_sd, tot_nd_with_sd = 0, 0
    won_nd_no_sd, tot_nd_no_sd = 0, 0
    won_sd, tot_sd = 0, 0
    for rid, opts in by_rid.items():
        if opts[0]["decided"] == "decline":
            continue
        opt_kinds = {o["kind"] for o in reqs[rid]["options"]}
        qp = book_all.get(rid, {}).get("prices", {})
        won = any(o["desk"] == "won" for o in opts)
        if "same_day" in qp:
            tot_sd += 1
            won_sd += int(won)
        elif "next_day" in qp:
            if "same_day" in opt_kinds:
                tot_nd_with_sd += 1
                won_nd_with_sd += int(won)
            else:
                tot_nd_no_sd += 1
                won_nd_no_sd += int(won)
    print("=== 2. v5 ACTUAL WIN RATE BY QUOTED vs MENU OPTIONS (dev-12) ===")
    print(f"  v5 quoted same_day (with or without nd): {won_sd}/{tot_sd} = {won_sd/max(1,tot_sd):.1%}")
    print(f"  v5 quoted ONLY next_day (menu had NO same_day): {won_nd_no_sd}/{tot_nd_no_sd} = {won_nd_no_sd/max(1,tot_nd_no_sd):.1%}")
    print(f"  v5 quoted ONLY next_day (menu HAD same_day, v5 dropped sd!): {won_nd_with_sd}/{tot_nd_with_sd} = {won_nd_with_sd/max(1,tot_nd_with_sd):.1%}")

    # 3. Best option's limit/list (i.e. fastest option on the menu!) by day & outage region!
    print("=== 3. FASTEST-MENU-OPTION LIMIT/LIST BY DAY & OUTAGE CENTER (dev-12) ===")
    fastest = []
    for rid, opts in by_rid.items():
        first_kind = reqs[rid]["options"][0]["kind"]
        o = next((x for x in opts if x["option"] == first_kind and x["lo"]), None)
        if o:
            fastest.append(o)
    days = ["Mon", "Tue", "Wed", "Thu", "Fri"]
    for d in range(5):
        bh = [(o["lo"] / o["list"]) / (1 + 0.01 * o["trust"]) for o in fastest if o["day"] == d and 8 * 60 <= o["at"] % 1440 < 18 * 60]
        print(f"  {days[d]} 08-18 fastest-option trust-adj x (n={len(bh):3d}): median={median(bh):.4f}, mean={mean(bh):.4f}")
        if d == 1:
            tue_rows = [o for o in fastest if o["day"] == 1 and 8 * 60 <= o["at"] % 1440 < 18 * 60]
            best = None
            for place in geo.places:
                ins = [(o["lo"] / o["list"]) / (1 + 0.01 * o["trust"]) for o in tue_rows if geo.line_km(place, o["pickup"]) <= 80.0]
                outs = [(o["lo"] / o["list"]) / (1 + 0.01 * o["trust"]) for o in tue_rows if geo.line_km(place, o["pickup"]) > 80.0]
                if len(ins) >= 15 and len(outs) >= 15:
                    ratio = median(ins) / median(outs)
                    if best is None or ratio > best[0]:
                        best = (ratio, place, len(ins), median(ins), len(outs), median(outs))
            if best:
                print(f"    Tue outage 80km pickup on fastest option: {best[1]} ratio={best[0]:.3f} (in med={best[3]:.4f} n={best[2]} vs out med={best[5]:.4f} n={best[4]})")


if __name__ == "__main__":
    main()
