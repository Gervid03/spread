import collections
import csv
import math
import statistics as st
from pathlib import Path

csv.field_size_limit(10**9)
root = Path("/home/lab/.gemini/tmp/cp-margin/reveals-champ")


def rd(d, name):
    with open(d / f"{name}.csv", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def hav(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


cells = collections.defaultdict(lambda: {"uq": 0, "uw": 0, "fq": 0, "fw": 0, "fees": [], "margs": [], "lates": 0})

for d in sorted(root.iterdir()):
    places = {p["id"]: (float(p["lat"]), float(p["lon"])) for p in rd(d, "places")}
    line = {(a, b): hav(places[a], places[b]) for a in places for b in places}
    roads = {(r["from"], r["to"]): (float(r["km"]), int(r["minutes"])) for r in rd(d, "roads")}
    drivers = {x["id"]: x for x in rd(d, "drivers")}
    homes = collections.Counter(x["homePlaceId"] for x in drivers.values())
    supply = {p: sum(n for h, n in homes.items() if line[(p, h)] <= 30) for p in places}
    reqs = {r["id"]: r for r in rd(d, "requests")}
    legs_by_req = collections.defaultdict(list)
    for l in rd(d, "legs"):
        legs_by_req[l["requestId"]].append(l)
    events = rd(d, "events")
    order_ledger = collections.defaultdict(collections.Counter)
    late_orders = set()
    for e in events:
        if e["kind"] == "ledger" and e["line.orderId"]:
            oid = e["line.orderId"]
            order_ledger[oid][e["line.kind"]] += int(e["line.cents"])
            if e["line.kind"] in ("late_refund", "undelivered_penalty"):
                late_orders.add(oid)

    for rid, r in reqs.items():
        q_opts = {k: int(r[f"{k}.quoteCents"]) for k in ("same_day", "next_day", "within_3_days") if r.get(f"{k}.quoteCents")}
        if not q_opts:
            continue
        fk = next(iter(q_opts))
        m0 = q_opts[fk] / int(r[f"{fk}.listPriceCents"])
        if m0 > 3.5:
            continue
        ref = int(r["referenceFeeCents"])
        floor_c = int(ref * 1.25 / 0.92 + 0.5)
        is_fl = any(abs(v - floor_c) <= 2 for v in q_opts.values())
        l0 = legs_by_req[rid][0]
        l_last = legs_by_req[rid][-1]
        sp, sd = supply[l0["pickup.placeId"]], supply[l_last["delivery.placeId"]]
        drive = sum(roads[(x["pickup.placeId"], x["delivery.placeId"])][1] for x in legs_by_req[rid])
        cp = "hub" if sp >= 200 else "nonhub"
        cd = "hub" if sd >= 200 else ("mid" if sd >= 30 else "thin")
        dc = "long180+" if drive >= 180 else "under180"
        won = 1 if r["outcome"] == "won" else 0
        for key in [f"ALL {cp}->{cd}", f"DET {cp}->{cd} {dc}"]:
            c = cells[key]
            if is_fl:
                c["fq"] += 1
                c["fw"] += won
            else:
                c["uq"] += 1
                c["uw"] += won
            if won:
                led = order_ledger[rid]
                c["margs"].append(sum(led.values()) / 100.0)
                if led["driver_fee"] < 0:
                    c["fees"].append(-led["driver_fee"] / ref)
                if rid in late_orders:
                    c["lates"] += 1

for key in sorted(cells):
    c = cells[key]
    uq, uw, fq, fw = c["uq"], c["uw"], c["fq"], c["fw"]
    tw = len(c["margs"])
    if uq + fq < 50:
        continue
    fmean = st.mean(c["fees"]) if c["fees"] else 0
    fp90 = sorted(c["fees"])[int(0.9 * len(c["fees"]))] if c["fees"] else 0
    mmean = st.mean(c["margs"]) if c["margs"] else 0
    print(f"{key:<28} unfl={uw:4d}/{uq:4d} ({uw/max(uq,1):5.1%}) fl={fw:3d}/{fq:3d} ({fw/max(fq,1):5.1%}) fee/ref={fmean:.3f}(p90={fp90:.2f}) late={c['lates']/max(tw,1):4.1%} marg/w={mmean:5.1f}")
