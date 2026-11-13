import csv, json, sys, math, collections, statistics as st
from pathlib import Path
csv.field_size_limit(10**9)
def rd(d, name):
    with open(d/f"{name}.csv", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))
def hav(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2-la1)/2)**2 + math.cos(la1)*math.cos(la2)*math.sin((lo2-lo1)/2)**2
    return 6371*2*math.asin(math.sqrt(h))
CAP={"helsinki","espoo","vantaa"}
for d in map(Path, sys.argv[1:]):
    print("="*90); print(d.name)
    places = {p["id"]:(float(p["lat"]), float(p["lon"])) for p in rd(d,"places")}
    line = {(a,b):hav(places[a],places[b]) for a in places for b in places}
    roads = {(r["from"],r["to"]):(float(r["km"]),int(r["minutes"])) for r in rd(d,"roads")}
    drivers = {x["id"]:x for x in rd(d,"drivers")}
    homes=collections.Counter(x["homePlaceId"] for x in drivers.values())
    supply={p:sum(n for h,n in homes.items() if line[(p,h)]<=30) for p in places}
    reqs = {r["id"]:r for r in rd(d,"requests")}; legs = rd(d,"legs")
    leg0 = {l["requestId"]:l for l in legs if l["leg"]=="0"}
    gigs = {g["id"]:g for g in rd(d,"gigs")}
    events = rd(d,"events")
    gig_order = {g:json.loads(x["stops"])[0]["orderId"] for g,x in gigs.items()}
    late={e["line.orderId"] for e in events if e["kind"]=="ledger" and e["line.kind"] in ("late_refund","undelivered_penalty")}
    acc=collections.defaultdict(int)
    for e in events:
        if e["kind"]=="ledger" and e["line.orderId"]: acc[e["line.orderId"]]+=int(e["line.cents"])
    first_post={}
    for g,x in gigs.items():
        o=gig_order[g]; first_post[o]=min(first_post.get(o,10**9), int(x["postedAt"]))
    fb={}
    for e in events:
        if e["kind"]=="gig_booked":
            o=gig_order[e["gigId"]]
            fb[o]=e   # last booking
    won=[o for o,r in reqs.items() if r["outcome"]=="won"]
    print("won", len(won), "late", len(late), "on-time %.3f"%(1-len(late)/len(won)), "hyvinkaa supply", supply["hyvinkaa"])
    def cls(o):
        p=leg0[o]["pickup.placeId"]; s=supply[p]
        if p=="hyvinkaa": return "HYV pickup"
        if p in CAP: return "CAP pickup"
        return "thin<30" if s<30 else "mid 30-200"
    tab=collections.defaultdict(lambda: collections.defaultdict(list))
    for o in won:
        r=reqs[o]
        tab[cls(o)][r["option"]].append(o)
    for c in sorted(tab):
        for opt,os_ in sorted(tab[c].items()):
            n=len(os_); l=sum(1 for o in os_ if o in late)
            ratio=[int(fb[o]["feeCents"])/int(reqs[o]["referenceFeeCents"]) for o in os_ if o in fb]
            homesb=collections.Counter()
            for o in os_:
                if o in fb:
                    h=drivers[fb[o]["driverId"]]["homePlaceId"]
                    homesb["cap" if h in CAP else "near pickup" if line[(h,leg0[o]["pickup.placeId"])]<=30 else "near delivery" if line[(h,leg0[o]["delivery.placeId"])]<=30 else "other"]+=1
            delay=[int(fb[o]["at"])-first_post[o] for o in os_ if o in fb]
            print(f"  {c:12s} {opt:14s} n={n:3d} late={l:2d} ({l/n:4.0%}) margin/order €{sum(acc[o] for o in os_)/n/100:6.1f} fee/typ mean {st.mean(ratio) if ratio else 0:.2f} med {st.median(ratio) if ratio else 0:.2f} med min-to-book {st.median(delay) if delay else 0:.0f} booker homes {dict(homesb)}")
    # hyvinkaa by delivery region
    hy=[o for o in won if leg0[o]["pickup.placeId"]=="hyvinkaa"]
    byd=collections.defaultdict(list)
    for o in hy: byd["->CAP" if leg0[o]["delivery.placeId"] in CAP else "->other"].append(o)
    for k,os_ in byd.items():
        print(f"  HYV {k}: n={len(os_)} late={sum(1 for o in os_ if o in late)} margin/order €{sum(acc[o] for o in os_)/len(os_)/100:.1f}")
