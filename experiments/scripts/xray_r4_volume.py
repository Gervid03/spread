"""Slot-free capacity & volume X-ray on Champion v6 dev results and cached TAS reveals/tapes."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean

from spread_lab.env import lab_home
from spread_lab.geo import Geo


def main() -> None:
    champ_rows = [json.loads(line) for line in Path("champion/results/dev-L8.jsonl").read_text().splitlines() if line.strip()]
    print(f"=== CHAMPION v6 DEV-16 SUMMARY (n={len(champ_rows)}) ===")
    print(f"Won/wk: mean={mean(r['won'] for r in champ_rows):.1f}, min={min(r['won'] for r in champ_rows)}, max={max(r['won'] for r in champ_rows)}")
    print(f"Margin: mean={mean(r['margin'] for r in champ_rows):.2f}, min={min(r['margin'] for r in champ_rows):.2f}")
    print(f"On-time: mean={mean(r['on_time'] for r in champ_rows)*100:.2f}%, min={min(r['on_time'] for r in champ_rows)*100:.2f}%")

    keys = [
        "quote_quote", "quote_floor", "quote_decline",
        "declined_backlog", "dropped_same_day_supply", "dropped_fri_same_day",
        "dropped_long_drive", "dropped_next_day_long", "dropped_thin_long_next_day", "dropped_slack",
        "lead_car_paired", "lead_car_booked",
        "quoted_ext_ring", "quoted_return_hub", "won_ext_ring", "won_return_hub", "won_ring",
        "won_same_day", "won_next_day", "won_within_3_days",
        "sup_days_calm", "sup_days_normal", "sup_days_stressed", "sup_fri_surplus_fired",
        "sup_fri_thin_quoted", "sup_fri_thin_won", "sup_fri_thin_late", "sup_fri_thin_margin_cents",
        "deadline_close", "gig_dropped",
    ]
    for k in keys:
        vals = [r["stats"].get(k, 0) for r in champ_rows]
        print(f"  {k:<28}: mean={mean(vals):7.2f}  min={min(vals):5}  max={max(vals):5}")

    lh = lab_home()
    map_path = lh / "map.json"
    geo = Geo(json.loads(map_path.read_text())) if map_path.exists() else None

    tas_dir = lh / "tas"
    if tas_dir.exists():
        print()
        print("=== CACHED TAS WORLDS ===")
        for seed_dir in sorted(tas_dir.iterdir()):
            if not seed_dir.is_dir():
                continue
            files = [p.name for p in sorted(seed_dir.iterdir())]
            print(f"  {seed_dir.name}: {files}")

    for seed in ["dev-12", "dev-01", "dev-07", "dev-08"]:
        sdir = tas_dir / seed
        if not (sdir / "tape.json").exists():
            continue
        tape = json.loads((sdir / "tape.json").read_text())
        reqs = tape.get("requests", [])
        roster = tape.get("roster", [])
        supply30 = geo.supply(roster, 30.0) if geo and roster else {}
        supply55 = geo.supply(roster, 55.0) if geo and roster else {}
        print()
        print(f"=== {seed} TAPE ANATOMY ({len(reqs)} requests, {len(roster)} drivers) ===")
        opt_combos = Counter(tuple(o["kind"] for o in r["options"]) for r in reqs)
        print("Option combinations:", dict(opt_combos))
        legs_cnt = Counter(len(r["legs"]) for r in reqs)
        print("Legs per request:", dict(legs_cnt))

        by_burst: dict[tuple[str, str, int], list[dict]] = defaultdict(list)
        for r in reqs:
            p0 = r["legs"][0]["pickup"]["placeId"]
            by_burst[(r["dealerId"], p0, r["arrivedAt"] // 30)].append(r)
        big_bursts = [
            (k[1], k[2] * 30 // 1440, (k[2] * 30 % 1440) // 60, len(v), Counter(x["legs"][-1]["delivery"]["placeId"] for x in v).most_common(4))
            for k, v in by_burst.items() if len(v) >= 4
        ]
        print("Bursts >= 4 cars (pickup, day, hr, count, top_dests):", big_bursts[:10])

        thin_gate = [r for r in reqs if supply55.get(r["legs"][0]["pickup"]["placeId"], 0) < 22]
        ring_only = [r for r in reqs if supply30.get(r["legs"][0]["pickup"]["placeId"], 0) < 22 <= supply55.get(r["legs"][0]["pickup"]["placeId"], 0)]
        dense = [r for r in reqs if supply30.get(r["legs"][0]["pickup"]["placeId"], 0) >= 22]
        print(f"By pickup supply: dense(30km>=22)={len(dense)}, ring(55km>=22)={len(ring_only)}, thin(55km<22)={len(thin_gate)}")

        thin_dest_hub200 = sum(1 for r in thin_gate if supply30.get(r["legs"][-1]["delivery"]["placeId"], 0) >= 200)
        thin_dest_reg40 = sum(1 for r in thin_gate if 40 <= supply30.get(r["legs"][-1]["delivery"]["placeId"], 0) < 200)
        thin_dest_thin = sum(1 for r in thin_gate if supply30.get(r["legs"][-1]["delivery"]["placeId"], 0) < 40)
        print(f"Thin pickup destinations: hub(>=200)={thin_dest_hub200}, regional(40..199)={thin_dest_reg40}, thin(<40)={thin_dest_thin}")

        fri_reqs = [r for r in reqs if r["arrivedAt"] // 1440 == 4]
        print(f"Friday requests: {len(fri_reqs)} (dense={sum(1 for r in fri_reqs if supply30.get(r['legs'][0]['pickup']['placeId'],0)>=22)}, thin_gate={sum(1 for r in fri_reqs if supply55.get(r['legs'][0]['pickup']['placeId'],0)<22)})")

    d12 = tas_dir / "dev-12"
    if (d12 / "limits-all.jsonl").exists():
        lims = [json.loads(l) for l in (d12 / "limits-all.jsonl").read_text().splitlines() if l.strip()]
        print()
        print(f"=== DEV-12 LIMITS-ALL ({len(lims)} rows) ===")
        if lims:
            print("Sample limit row:", lims[0])
            by_opt = defaultdict(list)
            for row in lims:
                if isinstance(row.get("limit"), (int, float)):
                    by_opt[row["kind"]].append(row["limit"])
            for k, vs in by_opt.items():
                print(f"  Option {k:<15}: n={len(vs):4d}  mean_limit={mean(vs):.3f}  median={sorted(vs)[len(vs)//2]:.3f}")

    if (d12 / "reveal-v5.json").exists():
        rev = json.loads((d12 / "reveal-v5.json").read_text())
        print()
        print(f"=== DEV-12 REVEAL KEYS: {sorted(rev.keys())} ===")
        for k, v in rev.items():
            if isinstance(v, list):
                print(f"  {k}: {len(v)} rows; sample={v[0] if v else None}")


if __name__ == "__main__":
    main()
