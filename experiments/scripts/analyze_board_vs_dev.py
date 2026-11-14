#!/usr/bin/env python3
"""Compare Round 7 (and Round 6) public board worlds against our 16 dev worlds (both played by Champion v6)."""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median

from spread.client import Client, SpreadError
from spread_lab.env import load_dotenv
from spread_lab.geo import Geo, load_map

ROUND7_WORLDS = [
    "wc8550ccd7438d978fbe3",
    "wbb70cb840b6a126d8efb",
    "w672e94d6a9a7482bb8d1",
    "we6fb10baf065315f2f0c",
    "wc6d14716c9816de0e723",
]


def fetch_all_events(world) -> list[dict]:
    events = []
    after = -1
    while True:
        batch = world.events(after=after, limit=5000)
        if not batch:
            break
        events.extend(batch)
        after = batch[-1]["seq"]
        if len(batch) < 5000:
            break
    return events


def summarize_world_events(wid: str, client, geo) -> dict | None:
    w = client.world(wid)
    try:
        score = w.score()
        roster = w.roster()
        events = fetch_all_events(w)
    except SpreadError as exc:
        print(f"  [skip {wid}] {exc}")
        return None

    sup30 = geo.supply(roster, 30.0)
    sup55 = geo.supply(roster, 55.0)

    # Identify major hubs by name or top supply
    by_name = {p["name"]: pid for pid, p in geo.places.items()}
    cap_sup = max((sup30.get(by_name[n], 0) for n in ("Vantaa", "Helsinki", "Espoo") if n in by_name), default=0)
    reg_hubs = {n: sup30.get(by_name[n], 0) for n in ("Hyvinkää", "Tampere", "Turku", "Oulu", "Lahti", "Jyväskylä", "Kuopio") if n in by_name}

    kinds = Counter(e["kind"] for e in events)
    reqs = [e["request"] for e in events if e["kind"] == "price_request"]
    wons = {e["order"]["id"]: e["order"] for e in events if e["kind"] == "order_won"}
    losts = {e["requestId"] for e in events if e["kind"] == "order_lost"}
    forecasts = [e for e in events if e["kind"] == "forecast"]

    req_by_day = Counter(r["arrivedAt"] // 1440 for r in reqs)
    won_by_day = Counter(r["arrivedAt"] // 1440 for r in reqs if r["id"] in wons)
    dealers = Counter(r["dealerId"] for r in reqs)
    batches = Counter(r.get("batchId") for r in reqs if r.get("batchId"))
    max_batch = max(batches.values(), default=0)

    notes_n = sum(1 for r in reqs if r.get("note"))
    two_leg_n = sum(1 for r in reqs if len(r["legs"]) > 1)
    opt_counts = Counter(o["kind"] for r in reqs for o in r["options"])

    # Supply buckets of pickups
    hub_p = sum(1 for r in reqs if sup30.get(r["legs"][0]["pickup"]["placeId"], 0) >= 200)
    reg_p = sum(1 for r in reqs if 50 <= sup30.get(r["legs"][0]["pickup"]["placeId"], 0) < 200)
    ring_p = sum(1 for r in reqs if sup30.get(r["legs"][0]["pickup"]["placeId"], 0) < 50 and sup55.get(r["legs"][0]["pickup"]["placeId"], 0) >= 22)
    thin_p = sum(1 for r in reqs if sup55.get(r["legs"][0]["pickup"]["placeId"], 0) < 22)
    thin_to_hub = sum(
        1
        for r in reqs
        if sup55.get(r["legs"][0]["pickup"]["placeId"], 0) < 22
        and sup30.get(r["legs"][-1]["delivery"]["placeId"], 0) >= 50
    )

    list_nd = [
        next((o["listPriceCents"] for o in r["options"] if o["kind"] == "next_day"), r["options"][0]["listPriceCents"])
        for r in reqs
    ]
    ref_over_list = [r["referenceFeeCents"] / lp for r, lp in zip(reqs, list_nd) if lp > 0]
    drives = [
        sum(geo.minutes(leg["pickup"]["placeId"], leg["delivery"]["placeId"]) for leg in r["legs"])
        for r in reqs
    ]

    ledger = Counter()
    for e in events:
        if e["kind"] == "ledger":
            ledger[e["line"]["kind"]] += e["line"]["cents"] / 100.0

    # Won price / list ratio
    won_mults = []
    for oid, o in wons.items():
        req = next((r for r in reqs if r["id"] == oid), None)
        if req:
            opt = next((op for op in req["options"] if op["kind"] == o["option"]), None)
            if opt and opt["listPriceCents"] > 0:
                won_mults.append(o["priceCents"] / opt["listPriceCents"])

    exp_drivers = sum(1 for d in roster if d.get("rating", 0) >= 4.8 and d.get("completedGigs", 0) >= 50)
    manual_drivers = sum(1 for d in roster if d.get("manualLicence", False))

    return {
        "world": wid,
        "margin": score.get("marginCents", 0) / 100.0 if "marginCents" in score else sum(ledger.values()),
        "won": len(wons),
        "on_time": score.get("onTimeShare", score.get("onTime")),
        "ranked": score.get("ranked"),
        "roster_n": len(roster),
        "exp_share": exp_drivers / max(1, len(roster)),
        "manual_share": manual_drivers / max(1, len(roster)),
        "cap_sup": cap_sup,
        "reg_hubs": reg_hubs,
        "events_total": len(events),
        "reqs_total": len(reqs),
        "req_by_day": [req_by_day[d] for d in range(5)],
        "won_by_day": [won_by_day[d] for d in range(5)],
        "win_rate_by_day": [round(won_by_day[d] / max(1, req_by_day[d]), 3) for d in range(5)],
        "dealers_n": len(dealers),
        "top1_dealer_reqs": dealers.most_common(1)[0][1] if dealers else 0,
        "top3_dealer_share": sum(c for _, c in dealers.most_common(3)) / max(1, len(reqs)),
        "max_batch": max_batch,
        "forecasts_n": len(forecasts),
        "notes_share": notes_n / max(1, len(reqs)),
        "two_leg_share": two_leg_n / max(1, len(reqs)),
        "opt_sd_share": opt_counts["same_day"] / max(1, len(reqs)),
        "opt_nd_share": opt_counts["next_day"] / max(1, len(reqs)),
        "opt_w3d_share": opt_counts["within_3_days"] / max(1, len(reqs)),
        "pickup_shares": {
            "hub200+": round(hub_p / max(1, len(reqs)), 3),
            "reg50_199": round(reg_p / max(1, len(reqs)), 3),
            "ring_g22": round(ring_p / max(1, len(reqs)), 3),
            "thin_<22": round(thin_p / max(1, len(reqs)), 3),
            "thin_to_50+": thin_to_hub,
        },
        "mean_list_eur": mean(list_nd) / 100.0 if list_nd else 0,
        "median_ref_list": median(ref_over_list) if ref_over_list else 0,
        "mean_drive_min": mean(drives) if drives else 0,
        "mean_won_mult": mean(won_mults) if won_mults else 0,
        "gig_viewed": kinds["gig_viewed"],
        "gig_booked": kinds["gig_booked"],
        "gig_dropped": kinds["gig_dropped"],
        "deadline_close": kinds["deadline_close"],
        "offer_answered": kinds["offer_answered"],
        "order_changed": kinds["order_changed"],
        "order_cancelled": kinds["order_cancelled"],
        "ledger": dict(ledger),
    }


def main() -> None:
    load_dotenv()
    client = Client()
    geo = Geo(load_map(client))

    # 1. Load dev-L8.jsonl (16 dev worlds played by v6) and holdout-L8.jsonl
    dev_rows = [json.loads(line) for line in Path("champion/results/dev-L8.jsonl").read_text().splitlines() if line.strip()]
    hold_rows = [json.loads(line) for line in Path("champion/results/holdout-L8.jsonl").read_text().splitlines() if line.strip()]

    print("=== CHAMPION v6 SUMMARY ACROSS DEV (16) vs HOLDOUT (16) ===")
    for label, rows in [("dev-16", dev_rows), ("holdout-16", hold_rows)]:
        tot_reqs = [r["stats"]["quote_quote"] + r["stats"]["quote_floor"] + r["stats"]["quote_decline"] for r in rows]
        declines = [r["stats"]["quote_decline"] for r in rows]
        floors = [r["stats"]["quote_floor"] for r in rows]
        wons = [r["won"] for r in rows]
        margins = [r["margin"] for r in rows]
        rev_per_won = [r["revenue"] / max(1, r["won"]) for r in rows]
        fee_share = [-r["ledger"].get("driver_fee", 0) / max(1, r["revenue"]) for r in rows]
        ots = [r["on_time"] for r in rows]
        warns = [r["stats"].get("deadline_close", 0) for r in rows]
        print(
            f"{label:10s}: margin mean €{mean(margins):,.1f} (med €{median(margins):,.1f}, min €{min(margins):,.1f}, max €{max(margins):,.1f}) | "
            f"reqs {mean(tot_reqs):.1f} (dec {mean(declines):.1f}, flr {mean(floors):.1f}) | "
            f"won {mean(wons):.1f} ({min(wons)}..{max(wons)}) | rev/won €{mean(rev_per_won):.2f} | "
            f"fee/rev {mean(fee_share):.1%} | OT mean {mean(ots):.2%} (min {min(ots):.2%}) | warns {mean(warns):.1f}"
        )

    print("\n=== INSPECTING ROUND 7 PUBLIC BOARD WORLDS (5) ===")
    r7_data = []
    for wid in ROUND7_WORLDS:
        info = summarize_world_events(wid, client, geo)
        if info:
            r7_data.append(info)
            rev = info["ledger"].get("revenue", 0.0)
            dfee = -info["ledger"].get("driver_fee", 0.0)
            print(
                f"  {wid}: margin €{info['margin']:,.2f} | won {info['won']}/{info['reqs_total']} ({info['won']/max(1,info['reqs_total']):.1%}) | "
                f"OT {info['on_time']:.2%} | roster {info['roster_n']} (cap {info['cap_sup']}) | "
                f"dealers {info['dealers_n']} (top1={info['top1_dealer_reqs']}, top3={info['top3_dealer_share']:.1%}) | "
                f"won_mult {info['mean_won_mult']:.3f} | rev/won €{rev/max(1,info['won']):.2f} | fee/rev {dfee/max(1,rev):.1%} | "
                f"warns {info['deadline_close']} | views {info['gig_viewed']} | batch_max {info['max_batch']} | forecasts {info['forecasts_n']}"
            )
            print(f"    req_by_day={info['req_by_day']} won_by_day={info['won_by_day']} win_rates={info['win_rate_by_day']}")
            print(f"    pickups={info['pickup_shares']} reg_hubs={info['reg_hubs']}")

    # Also check if any local reveal dirs exist to compare exact request/dealer/roster distributions on dev worlds!
    reveal_dirs = sorted(Path("/home/lab/spread/runs").glob("*reveal*")) + sorted(Path("/home/lab/spread/runs/reveals").glob("*")) if Path("/home/lab/spread/runs").exists() else []
    print(f"\nFound {len(reveal_dirs)} local reveal directories in /home/lab/spread/runs.")
    dev_csv_summaries = []
    for rd in reveal_dirs[:20]:
        req_csv = rd / "requests.csv"
        if not req_csv.exists():
            continue
        with req_csv.open() as f:
            rrows = list(csv.DictReader(f))
        if not rrows:
            continue
        dealers = Counter(r.get("dealerId", "") for r in rrows)
        notes_s = sum(1 for r in rrows if r.get("note")) / len(rrows)
        dev_csv_summaries.append({
            "dir": rd.name,
            "reqs": len(rrows),
            "dealers_n": len(dealers),
            "top1": dealers.most_common(1)[0][1],
            "top3_share": sum(c for _, c in dealers.most_common(3)) / len(rrows),
            "notes_share": notes_s,
        })
    if dev_csv_summaries:
        print(
            f"Local practice reveals ({len(dev_csv_summaries)} worlds): "
            f"reqs mean {mean(x['reqs'] for x in dev_csv_summaries):.1f} ({min(x['reqs'] for x in dev_csv_summaries)}..{max(x['reqs'] for x in dev_csv_summaries)}), "
            f"dealers mean {mean(x['dealers_n'] for x in dev_csv_summaries):.1f}, "
            f"top1 reqs {mean(x['top1'] for x in dev_csv_summaries):.1f}, "
            f"top3 share {mean(x['top3_share'] for x in dev_csv_summaries):.1%}, "
            f"notes share {mean(x['notes_share'] for x in dev_csv_summaries):.1%}"
        )

    if r7_data:
        print("\n=== AGGREGATE ROUND 7 (5 WORLDS) SUMMARY ===")
        print(f"  Mean margin:      €{mean(x['margin'] for x in r7_data):,.2f} (min €{min(x['margin'] for x in r7_data):,.2f}, max €{max(x['margin'] for x in r7_data):,.2f})")
        print(f"  Mean reqs/wk:     {mean(x['reqs_total'] for x in r7_data):.1f} ({min(x['reqs_total'] for x in r7_data)}..{max(x['reqs_total'] for x in r7_data)})")
        print(f"  Mean won/wk:      {mean(x['won'] for x in r7_data):.1f} ({min(x['won'] for x in r7_data)}..{max(x['won'] for x in r7_data)})")
        print(f"  Mean roster size: {mean(x['roster_n'] for x in r7_data):.1f} ({min(x['roster_n'] for x in r7_data)}..{max(x['roster_n'] for x in r7_data)}), cap30km={mean(x['cap_sup'] for x in r7_data):.1f}")
        print(f"  Mean dealers:     {mean(x['dealers_n'] for x in r7_data):.1f}, top1={mean(x['top1_dealer_reqs'] for x in r7_data):.1f}, top3={mean(x['top3_dealer_share'] for x in r7_data):.1%}")
        print(f"  Notes / 2-leg:    notes={mean(x['notes_share'] for x in r7_data):.1%}, 2-leg={mean(x['two_leg_share'] for x in r7_data):.2%}")
        print(f"  Options offered:  sd={mean(x['opt_sd_share'] for x in r7_data):.1%}, nd={mean(x['opt_nd_share'] for x in r7_data):.1%}, w3d={mean(x['opt_w3d_share'] for x in r7_data):.1%}")
        print(f"  Pickups share:    hub200+={mean(x['pickup_shares']['hub200+'] for x in r7_data):.1%}, reg50..199={mean(x['pickup_shares']['reg50_199'] for x in r7_data):.1%}, ring={mean(x['pickup_shares']['ring_g22'] for x in r7_data):.1%}, thin<22={mean(x['pickup_shares']['thin_<22'] for x in r7_data):.1%} (thin->50+={mean(x['pickup_shares']['thin_to_50+'] for x in r7_data):.1f}/wk)")
        print(f"  List / Ref / Drv: list=€{mean(x['mean_list_eur'] for x in r7_data):.2f}, med(ref/list)={mean(x['median_ref_list'] for x in r7_data):.3f}, drive={mean(x['mean_drive_min'] for x in r7_data):.1f}m, won_mult={mean(x['mean_won_mult'] for x in r7_data):.3f}")
        print(f"  Events/wk:        total={mean(x['events_total'] for x in r7_data):.0f}, views={mean(x['gig_viewed'] for x in r7_data):.0f}, drops={mean(x['gig_dropped'] for x in r7_data):.1f}, warns={mean(x['deadline_close'] for x in r7_data):.1f}, changes={mean(x['order_changed'] for x in r7_data):.1f}, cancels={mean(x['order_cancelled'] for x in r7_data):.1f}")

    print("\n=== INSPECTING DEV-16 WORLDS FROM dev-L8.jsonl (IF RETAINED) ===")
    dev_data = []
    for row in sorted(dev_rows, key=lambda r: r["seed"]):
        info = summarize_world_events(row["world"], client, geo)
        if info:
            info["seed"] = row["seed"]
            dev_data.append(info)
    if dev_data:
        print(f"Fetched {len(dev_data)} dev worlds directly:")
        print(f"  Mean margin:      €{mean(x['margin'] for x in dev_data):,.2f} (min €{min(x['margin'] for x in dev_data):,.2f}, max €{max(x['margin'] for x in dev_data):,.2f})")
        print(f"  Mean reqs/wk:     {mean(x['reqs_total'] for x in dev_data):.1f} ({min(x['reqs_total'] for x in dev_data)}..{max(x['reqs_total'] for x in dev_data)})")
        print(f"  Mean won/wk:      {mean(x['won'] for x in dev_data):.1f} ({min(x['won'] for x in dev_data)}..{max(x['won'] for x in dev_data)})")
        print(f"  Mean roster size: {mean(x['roster_n'] for x in dev_data):.1f} ({min(x['roster_n'] for x in dev_data)}..{max(x['roster_n'] for x in dev_data)}), cap30km={mean(x['cap_sup'] for x in dev_data):.1f}")
        print(f"  Mean dealers:     {mean(x['dealers_n'] for x in dev_data):.1f}, top1={mean(x['top1_dealer_reqs'] for x in dev_data):.1f}, top3={mean(x['top3_dealer_share'] for x in dev_data):.1%}")
        print(f"  Notes / 2-leg:    notes={mean(x['notes_share'] for x in dev_data):.1%}, 2-leg={mean(x['two_leg_share'] for x in dev_data):.2%}")
        print(f"  Options offered:  sd={mean(x['opt_sd_share'] for x in dev_data):.1%}, nd={mean(x['opt_nd_share'] for x in dev_data):.1%}, w3d={mean(x['opt_w3d_share'] for x in dev_data):.1%}")
        print(f"  Pickups share:    hub200+={mean(x['pickup_shares']['hub200+'] for x in dev_data):.1%}, reg50..199={mean(x['pickup_shares']['reg50_199'] for x in dev_data):.1%}, ring={mean(x['pickup_shares']['ring_g22'] for x in dev_data):.1%}, thin<22={mean(x['pickup_shares']['thin_<22'] for x in dev_data):.1%} (thin->50+={mean(x['pickup_shares']['thin_to_50+'] for x in dev_data):.1f}/wk)")
        print(f"  List / Ref / Drv: list=€{mean(x['mean_list_eur'] for x in dev_data):.2f}, med(ref/list)={mean(x['median_ref_list'] for x in dev_data):.3f}, drive={mean(x['mean_drive_min'] for x in dev_data):.1f}m, won_mult={mean(x['mean_won_mult'] for x in dev_data):.3f}")
        print(f"  Events/wk:        total={mean(x['events_total'] for x in dev_data):.0f}, views={mean(x['gig_viewed'] for x in dev_data):.0f}, drops={mean(x['gig_dropped'] for x in dev_data):.1f}, warns={mean(x['deadline_close'] for x in dev_data):.1f}, changes={mean(x['order_changed'] for x in dev_data):.1f}, cancels={mean(x['order_cancelled'] for x in dev_data):.1f}")


if __name__ == "__main__":
    main()
