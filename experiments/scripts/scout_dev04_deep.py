"""Deep slot-free analysis of volume pools, options, Friday/Mon2 capacity, batches, and late orders on dev-04."""
from __future__ import annotations

import csv
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

    margin_by_oid = Counter()
    fee_by_oid = Counter()
    late_oids = set()
    for e in events:
        if e["kind"] == "ledger" and e["line.orderId"]:
            oid = e["line.orderId"]
            c = int(e["line.cents"])
            margin_by_oid[oid] += c
            if e["line.kind"] == "driver_fee":
                fee_by_oid[oid] += -c
            if e["line.kind"] in ("late_refund", "undelivered_penalty"):
                late_oids.add(oid)

    print("=== A. WON ORDERS BY OPTION (dev-04) ===")
    by_opt = defaultdict(list)
    for r in reqs:
        if r["outcome"] == "won":
            by_opt[r["option"]].append(r)
    for opt, rs in sorted(by_opt.items()):
        n = len(rs)
        late = sum(1 for r in rs if r["id"] in late_oids)
        tot_m = sum(margin_by_oid[r["id"]] for r in rs) / 100
        tot_f = sum(fee_by_oid[r["id"]] for r in rs)
        tot_ref = sum(int(r["referenceFeeCents"]) for r in rs)
        print(f"  {opt:15s}: n={n:3d}, late={late:2d} ({late/n:.1%}), fee/ref={tot_f/tot_ref:.3f}, margin=€{tot_m:,.0f} (€{tot_m/n:.1f}/ord)")

    print("=== B. REQUESTS WITH WEEK-2 MONDAY+ OPTIONS (deadline >= 10800, Thu/Fri slow options) ===")
    mon2_reqs = []
    for r in reqs:
        dls = [int(r[f"{k}.deadline"]) for k in ("same_day", "next_day", "within_3_days") if r[f"{k}.deadline"]]
        if max(dls) >= 10800:
            mon2_reqs.append(r)
    c_mon2 = Counter()
    for r in mon2_reqs:
        lps = [int(r[f"{k}.listPriceCents"]) for k in ("same_day", "next_day", "within_3_days") if r[f"{k}.listPriceCents"]]
        qs = [int(r[f"{k}.quoteCents"]) for k in ("same_day", "next_day", "within_3_days") if r[f"{k}.quoteCents"]]
        dec = "declined" if max(qs) >= 3.5 * max(lps) else r["outcome"]
        ls = legs_by_req[r["id"]]
        pk, dl = ls[0]["pickup.placeId"], ls[-1]["delivery.placeId"]
        s55 = sup55[pk]
        bucket = "gate_pass(s55>=22)" if s55 >= 22 else ("ext_ring(s70>=30)" if sup70[pk] >= 30 else f"thin(s55={s55},dl30>=50:{sup30[dl]>=50})")
        c_mon2[(dec, bucket)] += 1
    for k, v in sorted(c_mon2.items()):
        print(f"  {str(k):48s}: {v}")
    won_mon2 = [r for r in mon2_reqs if r["outcome"] == "won" and int(r[f"{r['option']}.deadline"]) >= 10800]
    late_mon2 = sum(1 for r in won_mon2 if r["id"] in late_oids)
    m_mon2 = sum(margin_by_oid[r["id"]] for r in won_mon2) / 100
    f_mon2 = sum(fee_by_oid[r["id"]] for r in won_mon2)
    ref_mon2 = sum(int(r["referenceFeeCents"]) for r in won_mon2)
    print(f"  -> Won due Mon2+: n={len(won_mon2)}, late={late_mon2} ({late_mon2/max(1,len(won_mon2)):.1%}), fee/ref={f_mon2/max(1,ref_mon2):.3f}, margin=€{m_mon2:,.0f} (€{m_mon2/max(1,len(won_mon2)):.1f}/ord)")

    print("=== C. ALL REQUESTS OFFERING within_3_days (dev-04) ===")
    w3_reqs = [r for r in reqs if r["within_3_days.listPriceCents"]]
    w3_stats = Counter()
    for r in w3_reqs:
        q_wi = r["within_3_days.quoteCents"]
        lp_wi = int(r["within_3_days.listPriceCents"])
        if not q_wi or int(q_wi) >= 3.5 * lp_wi:
            w3_stats["wi_not_quoted"] += 1
        else:
            w3_stats[f"wi_quoted_out={r['outcome']}({r['option'] or '-'})"] += 1
    for k, v in sorted(w3_stats.items()):
        print(f"  {k:38s}: {v}")

    print("=== D. ALL LATE ORDERS ON DEV-04 ===")
    for r in reqs:
        if r["id"] in late_oids:
            ls = legs_by_req[r["id"]]
            pk, dl = ls[0]["pickup.placeId"], ls[-1]["delivery.placeId"]
            drv = sum(0 if l["pickup.placeId"] == l["delivery.placeId"] else roads[(l["pickup.placeId"], l["delivery.placeId"])][1] for l in ls)
            print(f"  {r['id']} arr={r['arrivedAt']} (d{int(r['arrivedAt'])//1440}) opt={r['option']:13s} {pk}[s30={sup30[pk]},s55={sup55[pk]}]->{dl}[s30={sup30[dl]}] drv={drv}m legs={len(ls)} price={int(r[r['option']+'.quoteCents'])/100:.0f} ref={int(r['referenceFeeCents'])/100:.0f} margin={margin_by_oid[r['id']]/100:+.0f} note={r['note'][:30]!r}")

    print("=== E. BATCHES: HOW MUCH VOLUME DO WE LOSE INSIDE BATCHES? ===")
    batches = defaultdict(list)
    for r in reqs:
        if r["batchId"]:
            batches[r["batchId"]].append(r)
    b_partial, b_zero, b_all = 0, 0, 0
    lost_in_partial_batches = 0
    for bid, rs in batches.items():
        qrs = [r for r in rs if max(int(r[f"{k}.quoteCents"]) for k in ("same_day", "next_day", "within_3_days") if r[f"{k}.quoteCents"]) < 3.5 * max(int(r[f"{k}.listPriceCents"]) for k in ("same_day", "next_day", "within_3_days") if r[f"{k}.listPriceCents"])]
        if len(qrs) < 2:
            continue
        w = sum(1 for r in qrs if r["outcome"] == "won")
        if w == 0:
            b_zero += 1
        elif w == len(qrs):
            b_all += 1
        else:
            b_partial += 1
            lost_in_partial_batches += (len(qrs) - w)
    print(f"  Quoted batches (size>=2): zero_won={b_zero}, partial_won={b_partial} (lost {lost_in_partial_batches} cars inside batches where we won >=1!), all_won={b_all}")


if __name__ == "__main__":
    main()
