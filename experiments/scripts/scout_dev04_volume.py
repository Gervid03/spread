"""Comprehensive slot-free volume diagnostic on Champion's dev-04 reveal."""
from __future__ import annotations

import csv
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path


def main() -> None:
    rev = Path(sys.argv[1] if len(sys.argv) > 1 else "runs/reveals/reveal-we07744ba5bd2d430cc60")
    places = {r["id"]: r for r in csv.DictReader(open(rev / "places.csv", encoding="utf-8"))}
    roads = {(r["from"], r["to"]): (float(r["km"]), int(r["minutes"])) for r in csv.DictReader(open(rev / "roads.csv", encoding="utf-8"))}
    drivers = list(csv.DictReader(open(rev / "drivers.csv", encoding="utf-8")))
    reqs = list(csv.DictReader(open(rev / "requests.csv", encoding="utf-8")))
    gigs = list(csv.DictReader(open(rev / "gigs.csv", encoding="utf-8")))
    events = list(csv.DictReader(open(rev / "events.csv", encoding="utf-8")))

    legs_by_req = defaultdict(list)
    for l in csv.DictReader(open(rev / "legs.csv", encoding="utf-8")):
        legs_by_req[l["requestId"]].append(l)

    def hav(a: str, b: str) -> float:
        p1, p2 = places[a], places[b]
        la1, lo1, la2, lo2 = map(math.radians, (float(p1["lat"]), float(p1["lon"]), float(p2["lat"]), float(p2["lon"])))
        h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
        return 6371.0 * 2 * math.asin(math.sqrt(h))

    homes = Counter(d["homePlaceId"] for d in drivers)
    sup30 = {p: sum(n for h, n in homes.items() if hav(p, h) <= 30.0) for p in places}
    sup55 = {p: sum(n for h, n in homes.items() if hav(p, h) <= 55.0) for p in places}
    sup70 = {p: sum(n for h, n in homes.items() if hav(p, h) <= 70.0) for p in places}

    outcomes = Counter()
    day_table = defaultdict(Counter)
    decision_outcome = defaultdict(Counter)
    option_combos = defaultdict(Counter)
    declined_reasons = Counter()
    floored_analysis = Counter()
    legs_count_out = defaultdict(Counter)
    friday_detail = Counter()
    batches = defaultdict(list)

    for r in reqs:
        if r["batchId"]:
            batches[r["batchId"]].append(r)

    print(f"=== BATCHES (batchId != '') : {len(batches)} batches, {sum(len(v) for v in batches.values())} requests ===")
    for bid, grp in sorted(batches.items(), key=lambda kv: -len(kv[1]))[:20]:
        ls0 = legs_by_req[grp[0]["id"]]
        pk = ls0[0]["pickup.placeId"]
        dls = Counter(legs_by_req[x["id"]][-1]["delivery.placeId"] for x in grp)
        arrs = sorted(int(x["arrivedAt"]) for x in grp)
        won = sum(1 for x in grp if x["outcome"] == "won")
        print(f"  batch={bid} n={len(grp):2d} won={won:2d} arr={arrs[0]}..{arrs[-1]} (day {arrs[0]//1440}) pk={pk}[s30={sup30[pk]}] dls={dict(dls.most_common(4))}")

    for r in reqs:
        rid = r["id"]
        ls = legs_by_req[rid]
        pk = ls[0]["pickup.placeId"]
        dl = ls[-1]["delivery.placeId"]
        drv = sum(roads[(l["pickup.placeId"], l["delivery.placeId"])][1] for l in ls)
        if len(ls) == 2:
            drv += roads[(ls[0]["delivery.placeId"], ls[1]["pickup.placeId"])][1]

        opts = []
        quotes = {}
        for k in ("same_day", "next_day", "within_3_days"):
            if r[f"{k}.listPriceCents"]:
                opts.append({"kind": k, "listPriceCents": int(r[f"{k}.listPriceCents"]), "deadline": int(r[f"{k}.deadline"])})
            if r[f"{k}.quoteCents"]:
                quotes[k] = int(r[f"{k}.quoteCents"])

        ref = int(r["referenceFeeCents"])
        floor = (ref * 1.25) / 0.92
        arr = int(r["arrivedAt"])
        day = arr // 1440

        is_decl = False
        is_floor = False
        if quotes:
            k0 = next(iter(quotes))
            lp0 = next(o["listPriceCents"] for o in opts if o["kind"] == k0)
            qmult0 = quotes[k0] / lp0
            if qmult0 > 3.0:
                is_decl = True
            elif any(abs(quotes[k] - int(floor + 0.5)) <= 2 for k in quotes):
                is_floor = True

        dec = "decline" if is_decl else ("floor" if is_floor else "quote")
        out = "declined" if is_decl else r["outcome"]
        taken_opt = r.get("option") or "-"

        outcomes[out] += 1
        day_table[day][f"{dec}_{r['outcome']}"] += 1
        day_table[day]["total"] += 1
        decision_outcome[dec][f"{r['outcome']}_opt={taken_opt}"] += 1
        legs_count_out[len(ls)][out] += 1

        opt_set = "+".join(o["kind"][:2] for o in opts)
        quoted_set = "+".join(k[:2] for k in quotes.keys()) if not is_decl else "NONE"
        option_combos[f"offered={opt_set:<8} quoted={quoted_set:<10}"][f"{r['outcome']}(took:{taken_opt[:2]})"] += 1

        if is_decl:
            s30, s55, s70, d30 = sup30[pk], sup55[pk], sup70[pk], sup30[dl]
            if s55 < 22 and not (s70 >= 30 and drv <= 220) and not (d30 >= 200 and drv <= 180):
                if s70 >= 30:
                    declined_reasons["gate_ext70_drive>220"] += 1
                elif d30 >= 200:
                    declined_reasons["gate_rethub_drive>180"] += 1
                elif d30 >= 50:
                    declined_reasons[f"gate_thin_to_midhub(d30={d30},drv<=220:{drv<=220})"] += 1
                else:
                    declined_reasons[f"gate_thin_pickup({pk}:s55={s55}->dl={dl}:d30={d30})"] += 1
            elif opt_set == "sa":
                if day >= 4 and drv >= 100:
                    declined_reasons["same_day_only_fri_drv>=100"] += 1
                elif s30 < 50:
                    declined_reasons[f"same_day_only_sup30<50({pk}:s30={s30},s55={s55})"] += 1
                elif drv > 300:
                    declined_reasons["same_day_only_drv>300"] += 1
                else:
                    declined_reasons["same_day_only_slack_or_note_or_backlog"] += 1
            else:
                declined_reasons[f"other_declined({pk}:opts={opt_set},s30={s30},drv={drv})"] += 1

        if dec == "floor":
            # check if ALL quoted options were floored, or ONLY slower options (ne/wi) were floored!
            floored_opts = [k[:2] for k in quotes if abs(quotes[k] - int(floor + 0.5)) <= 2]
            unfloored_opts = [k[:2] for k in quotes if abs(quotes[k] - int(floor + 0.5)) > 2]
            fr = floor / opts[0]["listPriceCents"]
            b2 = "<1.4" if fr < 1.4 else ("1.4-1.7" if fr < 1.7 else ("1.7-2.0" if fr < 2.0 else ">=2.0"))
            floored_analysis[f"floored={'+'.join(floored_opts):<8} unfloored={'+'.join(unfloored_opts) or '-':<6} f/lp0={b2:<7} -> {r['outcome']}(took:{taken_opt[:2]})"] += 1

        if day == 4:
            friday_detail[f"dec={dec:<7} opts={opt_set:<8} q={quoted_set:<8} -> {r['outcome']}(took:{taken_opt[:2]})"] += 1

    print("--- Overall Outcomes ---")
    print(dict(outcomes))
    print("--- By Number of Legs (1 vs 2 trade-in) ---")
    for k, v in sorted(legs_count_out.items()):
        print(f"  legs={k}: {dict(v)}")

    print("--- By Day (0=Mon..4=Fri) ---")
    for d in sorted(day_table):
        print(f"  Day {d}: {dict(sorted(day_table[d].items()))}")

    print("--- By Decision (quote vs floor vs decline) ---")
    for dec, c in decision_outcome.items():
        print(f"  {dec:<8}: {dict(c)}")

    print("--- By Offered vs Quoted Options -> Dealer Choice ---")
    for k, c in sorted(option_combos.items(), key=lambda kv: -sum(kv[1].values())):
        print(f"  {k} : {dict(c)}")

    print("--- Why were 267 requests declined? ---")
    for k, n in declined_reasons.most_common(25):
        print(f"  {n:3d}  {k}")

    print("--- Floored requests breakdown ---")
    for k, n in floored_analysis.most_common(25):
        print(f"  {n:3d}  {k}")

    print("--- Friday (Day 4) breakdown ---")
    for k, n in friday_detail.most_common(25):
        print(f"  {n:3d}  {k}")

    booked_gigs = [g for g in gigs if g["status"] == "done"]
    drv_gigs = defaultdict(list)
    for g in booked_gigs:
        drv_gigs[g["driverId"]].append(g)

    pickup_day = Counter()
    deliv_day = Counter()
    for e in events:
        if e["kind"] == "picked_up":
            pickup_day[int(e["at"]) // 1440] += 1
        elif e["kind"] == "delivered":
            deliv_day[int(e["at"]) // 1440] += 1

    print("--- Driver utilization on dev-04 ---")
    print(f"  Unique drivers who completed >=1 gig: {len(drv_gigs)} / {len(drivers)} ({len(drv_gigs)/len(drivers):.1%})")
    gcount = Counter(len(v) for v in drv_gigs.values())
    print(f"  Completed gigs per active driver distribution: {dict(sorted(gcount.items()))}")
    print(f"  Pickups by day (0=Mon..5=Sat,6=Sun,7=Mon2): {dict(sorted(pickup_day.items()))}")
    print(f"  Deliveries by day (0=Mon..5=Sat,6=Sun,7=Mon2): {dict(sorted(deliv_day.items()))}")


if __name__ == "__main__":
    main()
