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
OPTS=("same_day","next_day","within_3_days")
def first_quote(r):
    for k in OPTS:
        if r[k+".quoteCents"]:
            x=int(r[k+".quoteCents"])/int(r[k+".listPriceCents"])
            return x if x<3 else None
    return None
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
    gig_order = {g:json.loads(x["stops"])[0]["orderId"] for g,x in gigs.items()}
    P=lambda r: leg0[r["id"]]["pickup.placeId"]
    D=lambda r: leg0[r["id"]]["delivery.placeId"]
    R=list(reqs.values())
    print("hyvinkaa out ->", collections.Counter(D(r) for r in R if P(r)=="hyvinkaa").most_common(8))
    print("hyvinkaa in  <-", collections.Counter(P(r) for r in R if D(r)=="hyvinkaa").most_common(8))
    print("hyvinkaa pickup dealers:", collections.Counter(r["dealerId"] for r in R if P(r)=="hyvinkaa").most_common(6))
    print("vantaa pickup dealers:", collections.Counter(r["dealerId"] for r in R if P(r)=="vantaa").most_common(6))
    print("D01 pickups:", collections.Counter(P(r) for r in R if r["dealerId"]=="D01").most_common(8))
    print("D02 pickups:", collections.Counter(P(r) for r in R if r["dealerId"]=="D02").most_common(5), "D03:", collections.Counter(P(r) for r in R if r["dealerId"]=="D03").most_common(4))
    print("hyvinkaa pickup options:", collections.Counter(tuple(k2 for k2 in OPTS if r[k2+".deadline"]) for r in R if P(r)=="hyvinkaa").most_common())
    lanes=collections.Counter((P(r),D(r)) for r in R)
    print("top lanes:", lanes.most_common(14))
    reg=lambda p: "CAP" if p in CAP else "HYV" if p=="hyvinkaa" else "oth"
    print("region lanes:", collections.Counter((reg(P(r)),reg(D(r))) for r in R).most_common())
    by_day=collections.defaultdict(list)
    for r in R: by_day[int(r["arrivedAt"])//1440].append(r)
    pairs=0; tot=0
    for day,rs in by_day.items():
        cand=rs+by_day.get(day+1,[])
        for a in rs:
            if roads[(P(a),D(a))][0]<60: continue
            tot+=1
            if any(b is not a and line[(P(b),D(a))]<=30 and line[(D(b),P(a))]<=30 for b in cand): pairs+=1
    print(f"requests >=60km with a reverse-lane partner same/next day: {pairs}/{tot}")
    for dl in ("D01","D02"):
        out=[]
        for day in range(5):
            rs=[r for r in R if r["dealerId"]==dl and int(r["arrivedAt"])//1440==day]
            qd=[(first_quote(r), r["outcome"]=="won") for r in rs if first_quote(r)]
            if qd: out.append((day, len(rs), len(qd), sum(w for _,w in qd), round(st.median([x for x,_ in qd]),2), round(st.median([x for x,w in qd if w] or [0]),2)))
        print(f" {dl} by day (day, reqs, quoted, won, med quote/list, med won ratio):", out)
    out=[]
    for day in range(5):
        qd=[(first_quote(r), r["outcome"]=="won") for r in by_day[day] if first_quote(r)]
        out.append((day, len(qd), sum(w for _,w in qd), round(st.median([x for x,_ in qd]),2)))
    print(" all by day (day, quoted, won, med quote/list):", out)
    books=[e for e in events if e["kind"]=="gig_booked"]
    per=collections.defaultdict(list)
    for e in events:
        if e["kind"]=="picked_up":
            dr = gigs[e["gigId"]]["driverId"]
            per[(dr, int(e["at"])//1440)].append((int(e["at"]), e["gigId"]))
    multi=[v for v in per.values() if len(v)>=2]
    chain=0;tot2=0
    for v in multi:
        v.sort()
        for (t1,g1),(t2,g2) in zip(v,v[1:]):
            o1,o2=gig_order[g1],gig_order[g2]; tot2+=1
            if line[(leg0[o1]["delivery.placeId"], leg0[o2]["pickup.placeId"])]<=30: chain+=1
    print(f" driver-days with >=2 pickups: {len(multi)} of {len(per)}; consecutive pairs where prev delivery within 30km of next pickup: {chain}/{tot2}")
    vt=collections.defaultdict(list)
    for v in views: vt[v["gigId"]].append((int(v["at"]), v["driverId"]))
    n_before=[len({dr for t,dr in vt[e["gigId"]] if t<=int(e["at"])}) for e in books]
    print(" distinct viewers at/before booking deciles:", q(n_before))
    late={e["line.orderId"] for e in events if e["kind"]=="ledger" and e["line.kind"] in ("late_refund","undelivered_penalty")}
    bk=collections.defaultdict(lambda:[0,0])
    kmb=lambda km: "a<100" if km<100 else "b<300" if km<300 else "c<500" if km<500 else "d>=500"
    for r in R:
        if r["outcome"]!="won": continue
        b=kmb(roads[(P(r),D(r))][0])
        bk[(b, r["option"])][0]+=1; bk[(b, r["option"])][1]+= r["id"] in late
    print(" won/late by (km, option):", {k:tuple(v) for k,v in sorted(bk.items())})
    acc=collections.defaultdict(int)
    for e in events:
        if e["kind"]=="ledger" and e["line.orderId"]: acc[e["line.orderId"]]+=int(e["line.cents"])
    mk=collections.defaultdict(list); mr=collections.defaultdict(list)
    for r in R:
        if r["outcome"]!="won": continue
        mk[kmb(roads[(P(r),D(r))][0])].append(acc[r["id"]]/100)
        mr[(reg(P(r)), reg(D(r)))].append(acc[r["id"]]/100)
    print(" order margin by km (n, sum, mean): ", {k:(len(v), round(sum(v)), round(st.mean(v),1)) for k,v in sorted(mk.items())})
    print(" order margin by region lane (n, sum, mean): ", {k:(len(v), round(sum(v)), round(st.mean(v),1)) for k,v in sorted(mr.items())})
    lk=collections.Counter()
    for e in events:
        if e["kind"]=="ledger": lk[(e["line.kind"], bool(e["line.orderId"]))]+=int(e["line.cents"])
    print(" ledger:", {k:round(v/100) for k,v in lk.items()})
    # fee paid / typical by km bucket; and booking delay by option
    fr=collections.defaultdict(list)
    for e in books:
        o=gig_order[e["gigId"]]; r=reqs[o]
        fr[kmb(roads[(P(r),D(r))][0])].append(int(e["feeCents"])/int(r["referenceFeeCents"]))
    print(" booked fee/typical by km (n, median, p90):", {k:(len(v), round(st.median(v),2), q(v)[-1] if len(v)>9 else None) for k,v in sorted(fr.items())})
    # typical fee / list by km bucket for all requests; and price/typical
    tl=collections.defaultdict(list)
    for r in R:
        lp=[int(r[k+".listPriceCents"]) for k in OPTS if r[k+".listPriceCents"]][0]
        tl[kmb(roads[(P(r),D(r))][0])].append(int(r["referenceFeeCents"])/lp)
    print(" typical/list by km (median):", {k:round(st.median(v),2) for k,v in sorted(tl.items())})
    # hour of day of arrivals
    hrs=collections.Counter(int(r["arrivedAt"])%1440//60 for r in R)
    print(" arrivals by hour:", sorted(hrs.items()))
