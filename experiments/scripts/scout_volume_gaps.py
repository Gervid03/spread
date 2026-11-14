"""Deep diagnostic of all un-won volume pools, actual booked fee ratios, trade-ins, outages, and driver capacity on dev-04."""
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
    views = list(csv.DictReader(open(rev / "views.csv", encoding="utf-8")))
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

    # 1. Trade-ins (legs == 2)
    print("=== 1. ALL 2-LEG TRADE-INS IN DEV-04 ===")
    print("legs.csv columns:", list(legs_by_req[reqs[0]["id"]][0].keys()))
    for r in reqs:
        ls = legs_by_req[r["id"]]
        if len(ls) == 2:
            l0, l1 = ls[0], ls[1]
            pk0, dl0 = l0["pickup.placeId"], l0["delivery.placeId"]
            pk1, dl1 = l1["pickup.placeId"], l1["delivery.placeId"]
            drv = roads[(pk0, dl0)][1] + roads[(dl0, pk1)][1] + roads[(pk1, dl1)][1]
            opts = [k for k in ("same_day", "next_day", "within_3_days") if r[f"{k}.listPriceCents"]]
            k0 = opts[0]
            dl_t = int(r[f"{k0}.deadline"])
            lp = int(r[f"{k0}.listPriceCents"])
            qc = int(r[f"{k0}.quoteCents"]) if r[f"{k0}.quoteCents"] else 0
            w0_from, w0_to = int(l0["pickup.window.from"]), int(l0["delivery.window.to"])
            w1_from, w1_to = int(l1["pickup.window.from"]), int(l1["delivery.window.to"])
            priv0d = l0["delivery.privateAddress"]
            priv1p = l1["pickup.window.from"]
            print(
                f"  {r['id']} arr={int(r['arrivedAt'])} ({int(r['arrivedAt'])//1440}d) {pk0}[s30={sup30[pk0]},s55={sup55[pk0]}]->{dl0}->{dl1} "
                f"drv={drv}m opt={k0} dl={dl_t} lp={lp/100:.0f} ref={int(r['referenceFeeCents'])/100:.0f} qc={qc/100:.0f} out={r['outcome']} "
                f"l0_pk_from={w0_from} l0_dl_to={w0_to}(priv={priv0d}) l1_pk_from={w1_from} l1_dl_to={w1_to} note={r['note'][:35]!r}"
            )

    # 2. Actual booked fee / referenceFeeCents by class!
    print("=== 2. ACTUAL BOOKED FEE / REF_FEE BY CLASS ON DEV-04 ===")
    req_by_id = {r["id"]: r for r in reqs}
    class_fees = defaultdict(list)
    late_orders = set()
    ord_ledger = defaultdict(int)
    for e in events:
        if e["kind"] == "ledger":
            oid = e.get("orderId") or e.get("line.orderId") or ""
            lkind = e.get("lineKind") or e.get("line.kind") or ""
            cents = int(e.get("cents") or e.get("line.cents") or 0)
            if oid:
                ord_ledger[oid] += cents
                if lkind in ("late_refund", "undelivered_penalty"):
                    late_orders.add(oid)

    for g in gigs:
        if g["status"] == "done":
            oids = json.loads(g["orders"]) if g.get("orders") and g["orders"].startswith("[") else g.get("orders", "").replace(",", " ").split()
            oids = [x.strip() for x in oids if x.strip()]
            if not oids:
                stops = json.loads(g["stops"])
                oids = list(dict.fromkeys(s["orderId"] for s in stops))
            ref_sum = sum(int(req_by_id[o]["referenceFeeCents"]) for o in oids if o in req_by_id)
            ratio = int(g["feeCents"]) / max(1, ref_sum)
            if len(oids) > 1:
                class_fees["paired_2car_gig"].append(ratio)
            else:
                o = oids[0]
                r = req_by_id[o]
                ls = legs_by_req[o]
                pk, dl = ls[0]["pickup.placeId"], ls[-1]["delivery.placeId"]
                opt = r["option"]
                s30 = sup30[pk]
                d30 = sup30[dl]
                pk_c = "hub(200+)" if s30 >= 200 else ("reg(50-199)" if s30 >= 50 else ("mid(22-49)" if s30 >= 22 else "ring/ext(<22)"))
                dl_c = "to_hub" if d30 >= 200 else ("to_reg(50+)" if d30 >= 50 else "to_other")
                class_fees[f"{pk_c:<14} {dl_c:<12} {opt:<13}"].append(ratio)

    for k, vals in sorted(class_fees.items(), key=lambda kv: -len(kv[1])):
        vals_s = sorted(vals)
        mean_v = sum(vals_s) / len(vals_s)
        p50 = vals_s[len(vals_s) // 2]
        p90 = vals_s[min(len(vals_s) - 1, int(len(vals_s) * 0.9))]
        n_085 = sum(1 for v in vals_s if v <= 0.86)
        print(f"  {k} n={len(vals_s):3d}  mean={mean_v:.3f}  p50={p50:.3f}  p90={p90:.3f}  @0.85={n_085/len(vals_s):.0%}")

    # 3. Viewers vs Bookers by day and by town!
    print("=== 3. ACTIVE VIEWING DRIVERS VS BOOKED DRIVERS BY DAY ===")
    drv_home = {d["id"]: d["homePlaceId"] for d in drivers}
    viewers_by_day = defaultdict(set)
    all_viewers = set()
    for v in views:
        d = int(v["at"]) // 1440
        viewers_by_day[d].add(v["driverId"])
        all_viewers.add(v["driverId"])

    bookers_by_day = defaultdict(set)
    for e in events:
        if e["kind"] == "picked_up":
            # find gig driver
            pass
    gig_by_id = {g["id"]: g for g in gigs}
    for e in events:
        if e["kind"] == "gig_started":
            gid = e.get("gigId") or ""
            if gid in gig_by_id and gig_by_id[gid]["driverId"]:
                bookers_by_day[int(e["at"]) // 1440].add(gig_by_id[gid]["driverId"])

    print(f"  Total unique viewers in week: {len(all_viewers)} / {len(drivers)} ({len(all_viewers)/len(drivers):.1%})")
    for d in range(9):
        if viewers_by_day[d] or bookers_by_day[d]:
            print(f"  Day {d}: viewers={len(viewers_by_day[d]):3d}, started_gigs_drivers={len(bookers_by_day[d]):3d}")

    # 4. Detect world events (outage day/region, price war day, bulk order)
    print("=== 4. WIN RATE & QUOTE MULT BY DAY AND PICKUP REGION (OUTAGE / WAR / BULK) ===")
    for d in range(5):
        day_reqs = [r for r in reqs if int(r["arrivedAt"]) // 1440 == d]
        by_pk = Counter()
        won_pk = Counter()
        qratios = []
        for r in day_reqs:
            pk = legs_by_req[r["id"]][0]["pickup.placeId"]
            opts = [k for k in ("same_day", "next_day", "within_3_days") if r[f"{k}.quoteCents"]]
            if not opts:
                continue
            k0 = opts[0]
            qr = int(r[f"{k0}.quoteCents"]) / int(r[f"{k0}.listPriceCents"])
            if qr > 3.0:
                continue
            qratios.append(qr)
            by_pk[pk] += 1
            if r["outcome"] == "won":
                won_pk[pk] += 1
        mean_qr = sum(qratios) / max(1, len(qratios))
        top_pks = [(pk, f"{won_pk[pk]}/{by_pk[pk]}") for pk, _ in by_pk.most_common(6)]
        print(f"  Day {d}: quoted={len(qratios):3d} won={sum(won_pk.values()):3d} ({sum(won_pk.values())/max(1,len(qratios)):.0%}) mean_q/list={mean_qr:.3f} top_pks={top_pks}")


if __name__ == "__main__":
    main()
