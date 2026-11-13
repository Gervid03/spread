import csv, json, sys, math, collections, statistics as st
from pathlib import Path
csv.field_size_limit(10**9)
root = Path(sys.argv[1])
def rd(d, name):
    with open(d/f"{name}.csv", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))
def hav(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2-la1)/2)**2 + math.cos(la1)*math.cos(la2)*math.sin((lo2-lo1)/2)**2
    return 6371*2*math.asin(math.sqrt(h))
for d in sorted(root.iterdir()):
    print("="*100); print(d.name)
    places = {p["id"]:(float(p["lat"]), float(p["lon"])) for p in rd(d,"places")}
    line = {(a,b):hav(places[a],places[b]) for a in places for b in places}
    roads = {(r["from"],r["to"]):(float(r["km"]),int(r["minutes"])) for r in rd(d,"roads")}
    drivers = {x["id"]:x for x in rd(d,"drivers")}
    homes = collections.Counter(x["homePlaceId"] for x in drivers.values())
    supply = {p:sum(n for h,n in homes.items() if line[(p,h)]<=30) for p in places}
    print("drivers", len(drivers))
    print("homes  ", sorted(homes.items(), key=lambda x:-x[1]))
    print("supply30", sorted(supply.items(), key=lambda x:-x[1]))
    reqs = rd(d,"requests"); legs = rd(d,"legs")
    leg0 = {l["requestId"]:l for l in legs if l["leg"]=="0"}
    nlegs = collections.Counter(l["requestId"] for l in legs)
    print("requests", len(reqs), "tradeins", sum(1 for v in nlegs.values() if v==2), "outcomes", collections.Counter(r["outcome"] for r in reqs))
    # requests by pickup supply bucket
    b = collections.Counter(); 
    for r in reqs:
        s = supply[leg0[r["id"]]["pickup.placeId"]]
        b["<10" if s<10 else "<20" if s<20 else "<30" if s<30 else "<60" if s<60 else ">=60"] += 1
    print("requests by pickup supply:", dict(b))
    pk = collections.Counter(leg0[r["id"]]["pickup.placeId"] for r in reqs)
    dl = collections.Counter(leg0[r["id"]]["delivery.placeId"] for r in reqs)
    print("pickup towns:", pk.most_common(30))
    print("delivery towns:", dl.most_common(30))
    # distance distribution
    kms = [roads[(leg0[r["id"]]["pickup.placeId"], leg0[r["id"]]["delivery.placeId"])][0] for r in reqs]
    qs = st.quantiles(kms, n=10)
    print("lane km deciles:", [round(q) for q in qs])
    # typical fee / list price, list price vs km
    ratio=[]; 
    for r in reqs:
        lp = r["same_day.listPriceCents"] or r["next_day.listPriceCents"] or r["within_3_days.listPriceCents"]
        ratio.append(int(r["referenceFeeCents"])/int(lp))
    print("typical/list(first option) deciles:", [round(q,2) for q in st.quantiles(ratio,n=10)])
    # dealers
    dealers = collections.Counter(r["dealerId"] for r in reqs)
    won_by = collections.Counter(r["dealerId"] for r in reqs if r["outcome"]=="won")
    print("dealers", len(dealers), "req/dealer deciles", [round(q) for q in st.quantiles(dealers.values(), n=10)], "max", max(dealers.values()))
    print("wins/dealer top:", won_by.most_common(12))
    # dealer -> pickup places concentration
    dp = collections.defaultdict(collections.Counter)
    for r in reqs: dp[r["dealerId"]][leg0[r["id"]]["pickup.placeId"]]+=1
    conc = [max(c.values())/sum(c.values()) for c in dp.values()]
    print("dealer pickup concentration (share of top pickup town) deciles:", [round(q,2) for q in st.quantiles(conc,n=10)])
    dd = collections.defaultdict(collections.Counter)
    for r in reqs: dd[r["dealerId"]][leg0[r["id"]]["delivery.placeId"]]+=1
    conc = [max(c.values())/sum(c.values()) for c in dd.values()]
    print("dealer delivery concentration deciles:", [round(q,2) for q in st.quantiles(conc,n=10)])
    # batch
    batches = collections.Counter(r["batchId"] for r in reqs if r["batchId"])
    print("batches:", len(batches), "sizes", collections.Counter(batches.values()).most_common(8))
    big = [k for k,v in batches.items() if v>=10]
    for k in big:
        rs=[r for r in reqs if r["batchId"]==k]
        print("  bulk", k, len(rs), "dealer", {r["dealerId"] for r in rs}, "at", sorted({int(r['arrivedAt']) for r in rs})[:3], "pickup", collections.Counter(leg0[r['id']]['pickup.placeId'] for r in rs), "deliv", collections.Counter(leg0[r['id']]['delivery.placeId'] for r in rs).most_common(6), "opts", collections.Counter(tuple(k2 for k2 in ("same_day","next_day","within_3_days") if r[k2+".deadline"]) for r in rs), "outcome", collections.Counter(r['outcome'] for r in rs))
    # options offered
    oc = collections.Counter(tuple(k2 for k2 in ("same_day","next_day","within_3_days") if r[k2+".deadline"]) for r in reqs)
    print("options offered:", oc.most_common())
    print("won option:", collections.Counter(r["option"] for r in reqs if r["outcome"]=="won"))
    # arrivals by day/hour
    byday = collections.Counter(int(r["arrivedAt"])//1440 for r in reqs)
    print("requests by day:", sorted(byday.items()))
    # private
    print("private pickup", sum(1 for r in reqs if leg0[r['id']]['pickup.privateAddress']=='true'), "private delivery", sum(1 for r in reqs if leg0[r['id']]['delivery.privateAddress']=='true'), "premium", sum(1 for r in reqs if leg0[r['id']]['car.premium']=='true'), "ev", sum(1 for r in reqs if leg0[r['id']]['car.electric']=='true'), "notes", sum(1 for r in reqs if r['note']))
