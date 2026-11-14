"""Inspect cached reveal-v5.json across all 4 TAS worlds + dev-12 limits-all.jsonl to size Layer 2 OracleDesk."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median

from spread_lab.env import lab_home
from spread_lab.geo import Geo, load_map


def load_jsonl(p: Path) -> list[dict]:
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    geo = Geo(load_map(None))
    tas_dir = lab_home() / "tas"

    # First check structure of reveal-v5.json
    rev12 = json.loads((tas_dir / "dev-12" / "reveal-v5.json").read_text(encoding="utf-8"))
    print("reveal-v5.json keys:", list(rev12.keys()))
    for k, v in rev12.items():
        if isinstance(v, list):
            print(f"  {k}: len={len(v)}, sample={v[0] if v else None}")
        elif isinstance(v, dict):
            print(f"  {k}: dict keys={list(v.keys())[:8]}")

    # Analyze dev-12 limits-all.jsonl distribution of (limit - expected_fee) for gate-passing requests!
    d12_dir = tas_dir / "dev-12"
    tape = json.loads((d12_dir / "tape.json").read_text(encoding="utf-8"))
    reqs = {r["id"]: r for r in tape["requests"]}
    s30 = geo.supply(tape["roster"], 30.0)
    s55 = geo.supply(tape["roster"], 55.0)
    s70 = geo.supply(tape["roster"], 70.0)
    lines = load_jsonl(d12_dir / "limits-all.jsonl")
    by_rid = defaultdict(list)
    for r in lines:
        by_rid[r["rid"]].append(r)

    # Check per-won-order margin in Layer 1 on dev-12 vs all feasible requests in limits-all!
    # Estimate expected fee mult: 0.90*ref for hub->hub, 1.00*ref for normal, 1.15*ref for same_day/thin
    won_margins = []
    lost_feasible_margins = []
    for rid, opts in by_rid.items():
        r = reqs[rid]
        ref = r["referenceFeeCents"] / 100.0
        p0 = r["legs"][0]["pickup"]["placeId"]
        d0 = r["legs"][-1]["delivery"]["placeId"]
        ps = s30.get(p0, 0)
        gs = s55.get(p0, 0)
        es = s70.get(p0, 0)
        ds = s30.get(d0, 0)
        legs = r["legs"]
        drive = sum(geo.minutes(l["pickup"]["placeId"], l["delivery"]["placeId"]) for l in legs)
        if len(legs) == 2:
            drive += geo.minutes(legs[0]["delivery"]["placeId"], legs[1]["pickup"]["placeId"])

        w = next((o for o in opts if o["desk"] == "won" and o["desk_option"] == o["option"]), None)
        if w and w["lo"]:
            est_m = w["lo"] / 100.0 - ref * (1.02 if w["option"] == "same_day" else 0.92)
            won_margins.append((est_m, rid, w["option"], w["lo"] / 100.0, ref, ps, ds, drive))
        else:
            # Check if physically feasible under v5's supply/slack gates
            if gs < 22 and not (es >= 30 and drive <= 220) and not (ds >= 200 and drive <= 180):
                continue
            ready = max([r["arrivedAt"]] + [l["pickup"]["window"]["from"] for l in legs])
            best_cand = None
            for o in r["options"]:
                kind = o["kind"]
                if gs < 22 and kind == "same_day":
                    continue
                if ps < 22 and kind == "same_day" and not (ds >= 200 and drive <= 60):
                    continue
                if kind == "same_day" and ps < 50 and not (ds >= 200 and drive <= 60):
                    continue
                if drive > 480 and o["deadline"] // 1440 <= ready // 1440 + 1:
                    continue
                if ps >= 22 and ps < 50 and drive > 300 and o["deadline"] // 1440 <= ready // 1440 + 1:
                    continue
                if ready // 1440 >= 4 and kind == "same_day" and drive >= 100:
                    continue
                if drive > 300 and o["deadline"] // 1440 <= ready // 1440:
                    continue
                if o["deadline"] - ready - drive < 150 + 0.75 * drive:
                    continue
                om = next((x for x in opts if x["option"] == kind and x["lo"]), None)
                if om:
                    est_m = om["lo"] / 100.0 - ref * (1.02 if kind == "same_day" else 0.92)
                    if best_cand is None or est_m > best_cand[0]:
                        best_cand = (est_m, rid, kind, om["lo"] / 100.0, ref, ps, ds, drive)
            if best_cand:
                lost_feasible_margins.append(best_cand)

    won_margins.sort()
    lost_feasible_margins.sort(reverse=True)
    print(f"=== DEV-12: LAYER 1 WON ORDERS (n={len(won_margins)}) vs LOST GATE-FEASIBLE ORDERS (n={len(lost_feasible_margins)}) ===")
    print(f"  Won est net margins: sum=€{sum(x[0] for x in won_margins):,.2f}, min=€{won_margins[0][0]:.2f}, "
          f"p10=€{won_margins[len(won_margins)//10][0]:.2f}, median=€{median(x[0] for x in won_margins):.2f}, "
          f"p90=€{won_margins[9*len(won_margins)//10][0]:.2f}, count < €30: {sum(1 for x in won_margins if x[0] < 30)}")
    print(f"  Lost gate-feasible: n={len(lost_feasible_margins)}, top 100 est net margin sum=€{sum(x[0] for x in lost_feasible_margins[:100]):,.2f}, "
          f"count > €60: {sum(1 for x in lost_feasible_margins if x[0] > 60)}, count > €45: {sum(1 for x in lost_feasible_margins if x[0] > 45)}")
    print("  Bottom 8 won orders in Layer 1:")
    for x in won_margins[:8]:
        print(f"    {x[1]} {x[2]:<13} est_margin=€{x[0]:6.2f} (lim=€{x[3]:6.2f}, ref=€{x[4]:6.2f}, ps={x[5]:3d}, ds={x[6]:3d}, drv={x[7]:3d}m)")
    print("  Top 12 LOST gate-feasible orders on dev-12:")
    for x in lost_feasible_margins[:12]:
        print(f"    {x[1]} {x[2]:<13} est_margin=€{x[0]:6.2f} (lim=€{x[3]:6.2f}, ref=€{x[4]:6.2f}, ps={x[5]:3d}, ds={x[6]:3d}, drv={x[7]:3d}m)")

    # If we simply picked the top K orders out of (won + lost_feasible) = 251 + len(lost_feasible):
    pool = sorted(won_margins + lost_feasible_margins, reverse=True)
    for k in [246, 280, 310, 340]:
        print(f"  Top {k:3d} gate-feasible orders est net margin sum: €{sum(x[0] for x in pool[:k]):,.2f} "
              f"(cutoff=€{pool[min(k, len(pool))-1][0]:.2f} vs Layer 1's 251 est sum=€{sum(x[0] for x in won_margins):,.2f} -> Δ=+€{sum(x[0] for x in pool[:k]) - sum(x[0] for x in won_margins):,.2f}!)")


if __name__ == "__main__":
    main()
