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
T=collections.Counter()
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
    P=lambda o: leg0[o]["pickup.placeId"]
    D=lambda o: leg0[o]["delivery.placeId"]
    late={e["line.orderId"] for e in events if e["kind"]=="ledger" and e["line.kind"] in ("late_refund","undelivered_penalty")}
    won=[o for o,r in reqs.items() if r["outcome"]=="won"]
    warned={e["orderId"] for e in events if e["kind"]=="deadline_close"}
    print("deadline_close orders:", len(warned), "late among them:", len(warned&late), "| late without warning:", len(late-warned), "| won", len(won))
    T["warn"]+=len(warned); T["warn_late"]+=len(warned&late); T["late_nowarn"]+=len(late-warned)
    dropped={gig_order[e["gigId"]] for e in events if e["kind"]=="gig_dropped"}
    print("orders with a drop:", len(dropped), "late among them:", len(dropped&late))
    T["drop"]+=len(dropped); T["drop_late"]+=len(dropped&late)
    failed={e["orderId"] for e in events if e["kind"]=="visit_failed"}
    print("orders with failed visit:", len(failed), "late among them:", len(failed&late))
    T["fail"]+=len(failed); T["fail_late"]+=len(failed&late)
    first_post={}
    for g,x in gigs.items():
        o=gig_order[g]; first_post[o]=min(first_post.get(o,10**9), int(x["postedAt"]))
    books=[e for e in events if e["kind"]=="gig_booked"]
    firstbook={}
    for e in books:
        o=gig_order[e["gigId"]]
        if o not in firstbook: firstbook[o]=e
    # by option: fee ratio, delay, share booked same day as posted
    by=collections.defaultdict(list)
    for o,e in firstbook.items():
        r=reqs[o]; ratio=int(e["feeCents"])/int(r["referenceFeeCents"]); delay=int(e["at"])-first_post[o]
        sameday = int(e["at"])//1440==first_post[o]//1440
        by[r["option"]].append((ratio, delay, sameday, first_post[o]%1440//60))
    for k,v in sorted(by.items()):
        print(f" {k}: n={len(v)} fee/typ mean={st.mean(x[0] for x in v):.3f} med={st.median(x[0] for x in v):.2f} | booked within 5min: {sum(1 for x in v if x[1]<=5)/len(v):.0%} within 60: {sum(1 for x in v if x[1]<=60)/len(v):.0%} | booked on post day: {sum(1 for x in v if x[2])/len(v):.0%}")
    # next_day orders: fee ratio by whether booked on post day or later
    nd=by.get("next_day",[])
    a=[x[0] for x in nd if x[2]]; b=[x[0] for x in nd if not x[2]]
    print(f" next_day: booked on post day n={len(a)} mean ratio {st.mean(a) if a else 0:.3f}; booked later n={len(b)} mean ratio {st.mean(b) if b else 0:.3f}")
    # fee ratio by supply class of pickup
    homes=collections.Counter(x["homePlaceId"] for x in drivers.values())
    supply={p:sum(n for h,n in homes.items() if line[(p,h)]<=30) for p in places}
    bs=collections.defaultdict(list)
    for o,e in firstbook.items():
        s=supply[P(o)]; k="s<60" if s<60 else "s<200" if s<200 else "s>=200"
        bs[k].append((int(e["feeCents"])/int(reqs[o]["referenceFeeCents"]), int(e["at"])-first_post[o]))
    print(" by supply:", {k:(len(v), "mean ratio %.3f"%st.mean(x[0] for x in v), "<=5min %.0f%%"%(100*sum(1 for x in v if x[1]<=5)/len(v))) for k,v in sorted(bs.items())})
    # views by hour of day
    vh=collections.Counter(int(v["at"])%1440//60 for v in views)
    print(" views by hour:", sorted(vh.items()))
    bh=collections.Counter(int(e["at"])%1440//60 for e in books)
    print(" bookings by hour:", sorted(bh.items()))
    # offers
    offers=[e for e in events if e["kind"]=="offer_answered"]
    lastview={}
    vs=sorted(views, key=lambda v:int(v["at"]))
    res=collections.Counter()
    vi=0
    for e in sorted(offers, key=lambda e:int(e["at"])):
        t=int(e["at"])-10
        seen_today=any(v["driverId"]==e["driverId"] and int(v["at"])//1440==t//1440 and int(v["at"])<=t for v in vs)
        res[(seen_today, e["answer"])]+=1
    print(" offers by (driver viewed something earlier that day, answer):", dict(res))
    for k,v in res.items(): T[("offer",)+k]+=v
    # Monday first 2 hours: quotes and outcomes
    mon=[(int(r["arrivedAt"]), first_quote(r), r["outcome"]) for r in reqs.values() if int(r["arrivedAt"])<1440 and first_quote(r)]
    mon.sort()
    for lo,hi in ((480,600),(600,720),(720,900),(900,1140)):
        xs=[m for m in mon if lo<=m[0]<hi]
        if xs: print(f"  Mon {lo//60:02d}-{hi//60:02d}: quoted {len(xs)} won {sum(1 for m in xs if m[2]=='won')} med ratio {st.median(m[1] for m in xs):.2f}")
    # per day per 2h blocks win rate to spot price war/outage
    for day in range(5):
        row=[]
        for lo in range(480,1140,120):
            xs=[(first_quote(r), r["outcome"]) for r in reqs.values() if int(r["arrivedAt"])//1440==day and lo<=int(r["arrivedAt"])%1440<lo+120 and first_quote(r)]
            row.append(f"{sum(1 for x in xs if x[1]=='won')}/{len(xs)}@{st.median(x[0] for x in xs):.2f}" if xs else "-")
        print("  day",day," ".join(row))
    # drops: hours held and fee ratio
    bookat={}
    hh=[]
    for e in events:
        if e["kind"]=="gig_booked": bookat[(e["gigId"],e["driverId"])]=(int(e["at"]), int(e["feeCents"]))
        if e["kind"]=="gig_dropped":
            b=bookat.get((e["gigId"],e["driverId"]))
            if b: hh.append(((int(e["at"])-b[0])/60, b[1]/int(reqs[gig_order[e["gigId"]]]["referenceFeeCents"])))
    if hh: print(" drops: hours held deciles", q([h for h,_ in hh]), "fee/typ at booking median", round(st.median(r for _,r in hh),2))
    # hold time for all bookings: book->pickup
    pick={}
    for e in events:
        if e["kind"]=="picked_up" and e["gigId"] not in pick: pick[e["gigId"]]=int(e["at"])
    hold=[(pick[e["gigId"]]-int(e["at"]))/60 for e in books if e["gigId"] in pick]
    print(" hours from booking to pickup deciles:", q(hold))
print("TOTAL", dict(T))
