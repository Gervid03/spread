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
def q(xs, n=10):
    xs=sorted(xs)
    if len(xs)<2: return xs
    return [round(xs[min(len(xs)-1,int(len(xs)*i/n))],2) for i in range(1,n)]
CAP={"helsinki","espoo","vantaa"}
for d in sorted(root.iterdir()):
    print("="*100); print(d.name)
    places = {p["id"]:(float(p["lat"]), float(p["lon"])) for p in rd(d,"places")}
    line = {(a,b):hav(places[a],places[b]) for a in places for b in places}
    roads = {(r["from"],r["to"]):(float(r["km"]),int(r["minutes"])) for r in rd(d,"roads")}
    drivers = {x["id"]:x for x in rd(d,"drivers")}
    reqs = {r["id"]:r for r in rd(d,"requests")}; legs = rd(d,"legs")
    leg0 = {l["requestId"]:l for l in legs if l["leg"]=="0"}
    gigs = {g["id"]:g for g in rd(d,"gigs")}
    events = rd(d,"events"); views = rd(d,"views")
    # per gig: order, post time, book events
    gig_order = {g:json.loads(x["stops"])[0]["orderId"] for g,x in gigs.items()}
    first_post = {}
    for g,x in gigs.items():
        o=gig_order[g]; first_post[o]=min(first_post.get(o,10**9), int(x["postedAt"]))
    books=[e for e in events if e["kind"]=="gig_booked"]
    drops=[e for e in events if e["kind"]=="gig_dropped"]
    late_orders={e["line.orderId"] for e in events if e["kind"]=="ledger" and e["line.kind"] in ("late_refund","undelivered_penalty")}
    won=[r for r in reqs.values() if r["outcome"]=="won"]
    print("won",len(won),"late",len(late_orders))
    # booking stats
    ratio=[];delay=[];hp=[];hd=[];cls=collections.Counter()
    final_book={}
    for e in books:
        g=e["gigId"]; o=gig_order[g]; r=reqs[o]; l=leg0[o]
        nl=sum(1 for s in json.loads(gigs[g]["stops"]) if s["kind"]=="pickup")
        typ=int(r["referenceFeeCents"])
        ratio.append(int(e["feeCents"])/typ)
        delay.append(int(e["at"])-first_post[o])
        home=drivers[e["driverId"]]["homePlaceId"]
        a=line[(home,l["pickup.placeId"])]; b=line[(home,l["delivery.placeId"])]
        hp.append(a); hd.append(b)
        cls["home<=30km of pickup" if a<=30 else "home<=30km of delivery" if b<=30 else "home 30-60 of pickup" if a<=60 else "home 30-60 of delivery" if b<=60 else "far from both"]+=1
        final_book[o]=(e, a, b)
    print("bookings",len(books),"drops",len(drops))
    print(" fee/typical at booking deciles:", q(ratio))
    print(" minutes first post->booking deciles:", q(delay))
    print(" booker home class:", dict(cls))
    # views
    vg=collections.defaultdict(set); vfirst=collections.defaultdict(list)
    for v in views: vg[v["gigId"]].add(v["driverId"])
    nview=[len(vg[g]) for g in gigs]
    print(" distinct viewers per gig deciles:", q(nview), "gigs with 0 views:", sum(1 for n in nview if n==0), "of", len(gigs))
    vclass=collections.Counter()
    for v in views:
        o=gig_order[v["gigId"]]; l=leg0[o]; home=drivers[v["driverId"]]["homePlaceId"]
        a=line[(home,l["pickup.placeId"])]; b=line[(home,l["delivery.placeId"])]
        vclass["home<=30 pickup" if a<=30 else "home<=30 delivery" if b<=30 else "other"]+=1
    print(" views by viewer home:", dict(vclass), "total", len(views))
    # view timing relative to post
    dts=[int(v["at"])-int(gigs[v["gigId"]]["postedAt"]) for v in views]
    print(" view minutes after gig post deciles:", q(dts))
    # active drivers per day
    act=collections.defaultdict(set)
    for v in views: act[int(v["at"])//1440].add(v["driverId"])
    print(" distinct viewers per day:", {k:len(s) for k,s in sorted(act.items())}, "ever:", len({v['driverId'] for v in views}), "of", len(drivers))
    bookers=collections.Counter(e["driverId"] for e in books)
    print(" distinct bookers:", len(bookers), "gigs per booker top:", bookers.most_common(8))
    # completedGigs vs activity
    seen={v["driverId"] for v in views}
    cg_seen=[int(drivers[x]["completedGigs"]) for x in seen]; cg_not=[int(x["completedGigs"]) for i,x in drivers.items() if i not in seen]
    print(" completedGigs median seen/not seen:", st.median(cg_seen) if cg_seen else None, st.median(cg_not) if cg_not else None, " rating med:", st.median([float(drivers[x]['rating']) for x in seen]), st.median([float(x['rating']) for i,x in drivers.items() if i not in seen]))
    cg_book=[int(drivers[x]["completedGigs"]) for x in bookers]
    print(" completedGigs deciles all:", q([int(x['completedGigs']) for x in drivers.values()]), "bookers:", q(cg_book))
    # late orders characteristics
    def feat(o):
        r=reqs[o]; l=leg0[o]
        return (l["pickup.placeId"], l["delivery.placeId"], r["option"], round(roads[(l["pickup.placeId"],l["delivery.placeId"])][0]), "priv" if l["pickup.privateAddress"]=="true" or l["delivery.privateAddress"]=="true" else "", "note" if r["note"] else "", "prem" if l["car.premium"]=="true" else "")
    print(" late orders:")
    for o in sorted(late_orders):
        if o in reqs: print("   ", o, feat(o), "arr", int(reqs[o]["arrivedAt"])//1440, int(reqs[o]["arrivedAt"])%1440//60, "| note:", reqs[o]["note"][:70])
    # on-time by pickup town & option
    by=collections.defaultdict(lambda:[0,0])
    for r in won:
        k=(leg0[r["id"]]["pickup.placeId"] in CAP, r["option"]); by[k][0]+=1; by[k][1]+= r["id"] in late_orders
    print(" won/late by (pickup in capital, option):", {k:tuple(v) for k,v in sorted(by.items())})
    # fee paid by class
    fees=collections.defaultdict(list)
    for o,(e,a,b) in final_book.items():
        fees["cap" if leg0[o]["pickup.placeId"] in CAP else "other"].append(int(e["feeCents"])/int(reqs[o]["referenceFeeCents"]))
    print(" fee/typical median by pickup region:", {k:(round(st.median(v),2), len(v)) for k,v in fees.items()})
    # price / list for wins and non-declined losses
    pr=collections.defaultdict(list)
    for r in reqs.values():
        for k in ("same_day","next_day","within_3_days"):
            if r[k+".quoteCents"]:
                ratio_=int(r[k+".quoteCents"])/int(r[k+".listPriceCents"])
                if ratio_<3: pr[(r["outcome"], )].append(ratio_); break
    print(" quote/list (first quoted option) deciles: won", q(pr[("won",)]), "lost", q(pr[("lost",)]))
    print(" n quoted non-decline:", {k:len(v) for k,v in pr.items()})
