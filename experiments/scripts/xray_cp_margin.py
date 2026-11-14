import collections
import csv
import json
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


pp_short_by_seed = collections.defaultdict(lambda: [0, 0, 0.0])  # [won, late, margin_eur]
eq_floor_pnl = collections.defaultdict(collections.Counter)
lead_car_pnl = []
inbound_hub_fees = collections.defaultdict(list)
priv_pk_all_quoted = collections.Counter()

for d in sorted(root.iterdir()):
    seed = d.name[:6]
    places = {p["id"]: (float(p["lat"]), float(p["lon"])) for p in rd(d, "places")}
    line = {(a, b): hav(places[a], places[b]) for a in places for b in places}
    drivers = {x["id"]: x for x in rd(d, "drivers")}
    homes = collections.Counter(x["homePlaceId"] for x in drivers.values())
    supply = {p: sum(n for h, n in homes.items() if line[(p, h)] <= 30) for p in places}
    reqs = {r["id"]: r for r in rd(d, "requests")}
    legs_by_req = collections.defaultdict(list)
    for l in rd(d, "legs"):
        legs_by_req[l["requestId"]].append(l)
    gigs = {g["id"]: g for g in rd(d, "gigs")}
    events = rd(d, "events")

    order_ledger = collections.defaultdict(collections.Counter)
    late_orders = set()
    for e in events:
        if e["kind"] == "ledger" and e["line.orderId"]:
            oid = e["line.orderId"]
            order_ledger[oid][e["line.kind"]] += int(e["line.cents"])
            if e["line.kind"] in ("late_refund", "undelivered_penalty"):
                late_orders.add(oid)

    for gid, g in gigs.items():
        if g["status"] in ("booked", "working", "done") and g["feeCents"]:
            oids = list(dict.fromkeys(s["orderId"] for s in json.loads(g["stops"])))
            if len(oids) > 1:
                ref_sum = sum(int(reqs[o]["referenceFeeCents"]) for o in oids if o in reqs)
                lead_car_pnl.append((seed, gid, len(oids), int(g["feeCents"]) / max(ref_sum, 1), sum(sum(order_ledger[o].values()) for o in oids) / 100))

    for rid, r in reqs.items():
        l0 = legs_by_req[rid][0]
        l_last = legs_by_req[rid][-1]
        pk, dl = l0["pickup.placeId"], l_last["delivery.placeId"]
        sp, sd = supply[pk], supply[dl]
        q_opts = {k: int(r[f"{k}.quoteCents"]) for k in ("same_day", "next_day", "within_3_days") if r.get(f"{k}.quoteCents")}
        if not q_opts:
            continue
        fk = next(iter(q_opts))
        if q_opts[fk] / int(r[f"{fk}.listPriceCents"]) > 3.5:
            continue

        if any(x["pickup.privateAddress"] == "true" for x in legs_by_req[rid]):
            tts = int(l0["pickup.window.to"]) - (int(r["arrivedAt"]) + 15)
            b = "tts<360" if tts < 360 else "tts>=360"
            priv_pk_all_quoted[f"{b}_quoted"] += 1
            if r["outcome"] == "won":
                priv_pk_all_quoted[f"{b}_won"] += 1
                if tts < 360:
                    pp_short_by_seed[seed][0] += 1
                    pp_short_by_seed[seed][1] += (1 if rid in late_orders else 0)
                    pp_short_by_seed[seed][2] += sum(order_ledger[rid].values()) / 100.0

        if len(q_opts) >= 2 and len(set(q_opts.values())) == 1 and r["outcome"] == "won":
            opt = r["option"]
            led = order_ledger[rid]
            eq_floor_pnl[opt]["won"] += 1
            eq_floor_pnl[opt]["late"] += (1 if rid in late_orders else 0)
            eq_floor_pnl[opt]["rev"] += led["revenue"]
            eq_floor_pnl[opt]["dfee"] += led["driver_fee"]
            eq_floor_pnl[opt]["margin"] += sum(led.values())

        if r["outcome"] == "won" and order_ledger[rid]["driver_fee"] < 0:
            ratio = -order_ledger[rid]["driver_fee"] / int(r["referenceFeeCents"])
            if sd >= 200 and sp < 200:
                inbound_hub_fees[f"nonhub->hub {r['option']}"].append(ratio)
            elif sp >= 200 and sd >= 200:
                inbound_hub_fees[f"hub->hub {r['option']}"].append(ratio)
            elif sp >= 200 and sd < 200:
                inbound_hub_fees[f"hub->out {r['option']}"].append(ratio)

print("Private pickup quoted/won:", dict(priv_pk_all_quoted))
print("Per-seed tts < 360 won / late / margin_eur:")
neg_seeds = 0
for s in sorted(pp_short_by_seed):
    w, l, m = pp_short_by_seed[s]
    if m < 0:
        neg_seeds += 1
    print(f"  {s}: won={w:2d} late={l:2d} margin={m:+7.2f} ({m/max(w,1):+6.2f}/ord)")
print(f"Seeds where tts<360 has negative total margin: {neg_seeds}/16")

print("=== Equal-price multi-option floored quotes WON ===")
for opt, v in sorted(eq_floor_pnl.items()):
    w = v["won"]
    print(f"  {opt:<14} won={w:3d} late={v['late']:2d} ({v['late']/w:.1%}) rev/w={v['rev']/100/w:6.1f} dfee/w={v['dfee']/100/w:7.1f} MARG/w={v['margin']/100/w:6.1f}")

print(f"=== Lead-car multi-car gigs booked: n={len(lead_car_pnl)} ===")
if lead_car_pnl:
    print("  fee / sum(ref) mean:", st.mean(x[3] for x in lead_car_pnl), "med:", st.median(x[3] for x in lead_car_pnl), "min:", min(x[3] for x in lead_car_pnl), "marg/gig:", st.mean(x[4] for x in lead_car_pnl))

print("=== Fee / ref distributions (inbound vs outbound) ===")
for k, arr in sorted(inbound_hub_fees.items()):
    at85 = sum(1 for x in arr if abs(x - 0.85) < 0.005)
    print(f"  {k:<26} n={len(arr):4d} @0.85={at85/len(arr):5.1%} mean={st.mean(arr):.3f} med={st.median(arr):.3f}")
