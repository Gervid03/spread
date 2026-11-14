#!/usr/bin/env python3
"""Slot-free sizing of all 6 stack-v7 mechanisms + Round 7 vs Dev-16 structural comparison (including Fri->Mon >480m next_day bug)."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean

from spread.client import Client
from spread_lab.env import load_dotenv
from spread_lab.geo import Geo, load_map
from analyze_board_vs_dev import ROUND7_WORLDS, fetch_all_events

DAY = 1440


def analyze_set(name: str, wids: list[str], client: Client, geo: Geo) -> None:
    rows = []
    for wid in wids:
        w = client.world(wid)
        roster = w.roster()
        events = fetch_all_events(w)
        sup30 = geo.supply(roster, 30.0)
        sup55 = geo.supply(roster, 55.0)
        sup85 = geo.supply(roster, 85.0)

        reqs = {e["request"]["id"]: e["request"] for e in events if e["kind"] == "price_request"}
        wons = {e["order"]["id"]: e["order"] for e in events if e["kind"] == "order_won"}
        cancels = {e["orderId"] for e in events if e["kind"] == "order_cancelled"}
        late_oids = {
            e["line"]["orderId"]
            for e in events
            if e["kind"] == "ledger" and e["line"]["kind"] in ("late_refund", "undelivered_penalty") and e["line"].get("orderId")
        }

        # Size each stack-v7 mechanism on the raw request stream
        thin_ret_v6 = 0        # thin (<22g) -> >=200, <=180m (already open in v6)
        thin_ret_vol = 0       # additional thin (<22g) -> >=45, <=270m (cp-volume)
        thin_ret_wild = 0      # additional thin (<22g) -> >=35, <=300m (cp-wild)
        fut_sd_ret = 0         # thin_ret_wild with same_day on future day & deliv>=50 (cp-wild)
        ext_ring_220_260 = 0   # thin (<22g) with 85km>=30 and 220 < drive <= 260 (cp-volume)
        inb_hub_reqs = 0       # pickup<200 -> deliv>=200
        inb_hub_high_ref = 0   # pickup<200 -> deliv>=200 where 1.25*ref/0.92 > 1.35 * list_nd (floor squeeze)
        trade_ins = 0
        trade_ins_won = 0
        trade_ins_late = 0
        fri_mon_long_nd_reqs = 0
        fri_mon_long_nd_won = 0
        fri_mon_long_nd_late = 0
        thin_slow_all = 0      # all thin (<22g) requests with next_day/within_3_days (candidate pool for cp-routes/cp-chains)

        # Outbound deliveries to near thin towns (<=20km)
        won_out_deliveries = []
        for oid, o in wons.items():
            if oid in cancels:
                continue
            dp = o["legs"][-1]["delivery"]["placeId"]
            if sup30.get(dp, 0) < 50:
                won_out_deliveries.append((reqs[oid]["arrivedAt"], dp))

        sponsored_thin = 0
        for rid, r in reqs.items():
            legs = r["legs"]
            p = legs[0]["pickup"]["placeId"]
            d = legs[-1]["delivery"]["placeId"]
            s30 = sup30.get(p, 0)
            s55 = sup55.get(p, 0)
            s85 = sup85.get(p, 0)
            ds30 = sup30.get(d, 0)
            drv = sum(geo.minutes(leg["pickup"]["placeId"], leg["delivery"]["placeId"]) for leg in legs)
            if len(legs) == 2:
                drv += geo.minutes(legs[0]["delivery"]["placeId"], legs[1]["pickup"]["placeId"])
                trade_ins += 1
                if rid in wons and rid not in cancels:
                    trade_ins_won += 1
                    if rid in late_oids:
                        trade_ins_late += 1

            opts = {o["kind"]: o for o in r["options"]}
            has_slow = "next_day" in opts or "within_3_days" in opts

            if s55 < 22:
                if has_slow:
                    thin_slow_all += 1
                    if any(t_arr < r["arrivedAt"] and geo.line_km(dp, p) <= 20.0 for t_arr, dp in won_out_deliveries):
                        sponsored_thin += 1
                is_v6 = ds30 >= 200 and drv <= 180 and has_slow
                is_vol = (not is_v6) and ds30 >= 45 and drv <= 270 and has_slow
                is_wild = (not is_v6) and ds30 >= 35 and drv <= 300 and (has_slow or "same_day" in opts)
                if is_v6:
                    thin_ret_v6 += 1
                if is_vol:
                    thin_ret_vol += 1
                if is_wild:
                    thin_ret_wild += 1
                if "same_day" in opts and opts["same_day"]["deadline"] // DAY > r["arrivedAt"] // DAY and ds30 >= 50 and drv <= 300 and len(legs) == 1:
                    fut_sd_ret += 1
                if s85 >= 30 and 220 < drv <= 260 and has_slow:
                    ext_ring_220_260 += 1

            if s30 < 200 and ds30 >= 200:
                inb_hub_reqs += 1
                lp = opts.get("next_day", r["options"][0])["listPriceCents"]
                if lp > 0 and (1.25 * r["referenceFeeCents"] / 0.92) > 1.35 * lp:
                    inb_hub_high_ref += 1

            # Check Friday-ready -> Monday-due >480m next_day bug!
            ready_day = max(r["arrivedAt"], legs[0]["pickup"]["window"]["from"]) // DAY
            if "next_day" in opts and drv > 480:
                nd_dl_day = opts["next_day"]["deadline"] // DAY
                if nd_dl_day > ready_day + 1:  # slipped past `deadline // DAY <= ready // DAY + 1`!
                    fri_mon_long_nd_reqs += 1
                    if rid in wons and rid not in cancels and wons[rid]["option"] == "next_day":
                        fri_mon_long_nd_won += 1
                        if rid in late_oids:
                            fri_mon_long_nd_late += 1

        rows.append({
            "thin_ret_v6": thin_ret_v6,
            "thin_ret_vol": thin_ret_vol,
            "thin_ret_wild": thin_ret_wild,
            "fut_sd_ret": fut_sd_ret,
            "ext_ring_220_260": ext_ring_220_260,
            "thin_slow_all": thin_slow_all,
            "sponsored_thin": sponsored_thin,
            "inb_hub_reqs": inb_hub_reqs,
            "inb_hub_high_ref": inb_hub_high_ref,
            "trade_ins": trade_ins,
            "trade_ins_won": trade_ins_won,
            "trade_ins_late": trade_ins_late,
            "fri_mon_long_nd_reqs": fri_mon_long_nd_reqs,
            "fri_mon_long_nd_won": fri_mon_long_nd_won,
            "fri_mon_long_nd_late": fri_mon_long_nd_late,
        })

    print(f"=== MECHANISM SIZING: {name} ({len(rows)} worlds) ===")
    for k in [
        "thin_ret_v6", "thin_ret_vol", "thin_ret_wild", "fut_sd_ret", "ext_ring_220_260",
        "thin_slow_all", "sponsored_thin", "inb_hub_reqs", "inb_hub_high_ref",
        "trade_ins", "trade_ins_won", "trade_ins_late",
        "fri_mon_long_nd_reqs", "fri_mon_long_nd_won", "fri_mon_long_nd_late",
    ]:
        vals = [r[k] for r in rows]
        print(f"  {k:24s}: mean {mean(vals):6.2f}/wk  (sum {sum(vals):4d}, min {min(vals):3d}, max {max(vals):3d})")


def main() -> None:
    load_dotenv()
    client = Client()
    geo = Geo(load_map(client))
    dev_rows = [json.loads(line) for line in Path("champion/results/dev-L8.jsonl").read_text().splitlines() if line.strip()]
    dev_wids = [r["world"] for r in sorted(dev_rows, key=lambda x: x["seed"])]
    analyze_set("ROUND 7 BOARD", ROUND7_WORLDS, client, geo)
    analyze_set("DEV-16", dev_wids, client, geo)


if __name__ == "__main__":
    main()
