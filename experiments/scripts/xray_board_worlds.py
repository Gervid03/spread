#!/usr/bin/env python3
"""Deep autopsy of Round 6 + Round 7 public board worlds vs Dev-16, especially sd option share and w672e94d6a9a7482bb8d1 (91.9% OT)."""
from __future__ import annotations

from collections import Counter
from statistics import mean

from spread.client import Client
from spread_lab.env import load_dotenv
from spread_lab.geo import Geo, load_map
from analyze_board_vs_dev import ROUND7_WORLDS, fetch_all_events, summarize_world_events

ROUND6_WORLDS = [
    "we762c862480a871c9329",
    "wb6297c0d8efee6d46dc7",
    "w5451acfcdb0df1714892",
    "w8a8bb143cdbf69c6055a",
    "w91e165cbfe0fcf6ea7d5",
]


def autopsy_world(wid: str, client: Client, geo: Geo) -> None:
    w = client.world(wid)
    roster = w.roster()
    events = fetch_all_events(w)
    sup30 = geo.supply(roster, 30.0)
    sup55 = geo.supply(roster, 55.0)

    reqs = {e["request"]["id"]: e["request"] for e in events if e["kind"] == "price_request"}
    wons = {e["order"]["id"]: e["order"] for e in events if e["kind"] == "order_won"}
    cancels = {e["orderId"] for e in events if e["kind"] == "order_cancelled"}
    forecasts = [e for e in events if e["kind"] == "forecast"]

    late_oids = set()
    for e in events:
        if e["kind"] == "ledger" and e["line"]["kind"] in ("late_refund", "undelivered_penalty") and e["line"].get("orderId"):
            late_oids.add(e["line"]["orderId"])

    print(f"=== AUTOPSY {wid} (roster={len(roster)}, won={len(wons)-len(cancels)}, late={len(late_oids)}) ===")
    for fc in forecasts:
        print("  forecast:", fc)

    # Check ready day vs arrival day (explains sd share!)
    future_ready = sum(1 for r in reqs.values() if r["legs"][0]["pickup"]["window"]["from"] // 1440 > r["arrivedAt"] // 1440)
    after_1500 = sum(1 for r in reqs.values() if (r["arrivedAt"] % 1440) > 15 * 60 and r["legs"][0]["pickup"]["window"]["from"] // 1440 == r["arrivedAt"] // 1440)
    print(f"  future_ready_day={future_ready}/{len(reqs)} ({future_ready/len(reqs):.1%}), same_ready_after_15h={after_1500}/{len(reqs)} ({after_1500/len(reqs):.1%})")

    late_by_day = Counter()
    late_by_opt = Counter()
    late_by_sup = Counter()
    won_fri_thin = 0
    late_fri_thin = 0
    won_fri_sd100 = 0
    late_fri_sd100 = 0

    for oid, o in wons.items():
        if oid in cancels:
            continue
        r = reqs[oid]
        day = r["arrivedAt"] // 1440
        p = r["legs"][0]["pickup"]["placeId"]
        d = r["legs"][-1]["delivery"]["placeId"]
        s30 = sup30.get(p, 0)
        s55 = sup55.get(p, 0)
        drv = sum(geo.minutes(leg["pickup"]["placeId"], leg["delivery"]["placeId"]) for leg in r["legs"])
        is_late = oid in late_oids
        if day == 4 and s55 < 22:
            won_fri_thin += 1
            if is_late:
                late_fri_thin += 1
        if day == 4 and o["option"] == "same_day" and drv >= 100:
            won_fri_sd100 += 1
            if is_late:
                late_fri_sd100 += 1
        if is_late:
            late_by_day[day] += 1
            late_by_opt[o["option"]] += 1
            bucket = "thin(<22g)" if s55 < 22 else ("ring(<50)" if s30 < 50 else ("reg(50-199)" if s30 < 200 else "hub(200+)"))
            late_by_sup[bucket] += 1
            pname = geo.places[p]["name"]
            dname = geo.places[d]["name"]
            print(f"    LATE {oid} d{day} {o['option']:13s} {pname}[30:{s30},55:{s55}]->{dname}[30:{sup30.get(d,0)}] drv={drv}m note={bool(r.get('note'))} legs={len(r['legs'])}")

    print(f"  Late by arrival day: {dict(sorted(late_by_day.items()))}")
    print(f"  Late by option:      {dict(late_by_opt)}")
    print(f"  Late by pickup sup:  {dict(late_by_sup)}")
    print(f"  Fri thin (<22g) won={won_fri_thin}, late={late_fri_thin} | Fri sd>=100m won={won_fri_sd100}, late={late_fri_sd100}")


def main() -> None:
    load_dotenv()
    client = Client()
    geo = Geo(load_map(client))

    print("=== INSPECTING ROUND 6 PUBLIC BOARD WORLDS (5, played by v4) ===")
    r6 = []
    for wid in ROUND6_WORLDS:
        info = summarize_world_events(wid, client, geo)
        if info:
            r6.append(info)
            print(f"  {wid}: margin €{info['margin']:,.2f} | won {info['won']}/{info['reqs_total']} | OT {info['on_time']:.2%} | roster {info['roster_n']} (cap {info['cap_sup']}) | opt_sd {info['opt_sd_share']:.1%}")
    if r6:
        print(f"Round 6 mean: margin €{mean(x['margin'] for x in r6):,.2f}, reqs {mean(x['reqs_total'] for x in r6):.1f}, roster {mean(x['roster_n'] for x in r6):.1f}, sd={mean(x['opt_sd_share'] for x in r6):.1%}, nd={mean(x['opt_nd_share'] for x in r6):.1%}")

    autopsy_world("w672e94d6a9a7482bb8d1", client, geo)
    autopsy_world("wc8550ccd7438d978fbe3", client, geo)


if __name__ == "__main__":
    main()
