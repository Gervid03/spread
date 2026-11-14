import csv
from collections import defaultdict
from pathlib import Path
from spread_lab.geo import Geo

rev = Path("/home/lab/.gemini/tmp/cp-chains/reveal-dev10/reveal-wf1a772bd88ece2422c10")
places = [{"id": r["id"], "name": r["name"], "lat": float(r["lat"]), "lon": float(r["lon"])} for r in csv.DictReader(open(rev / "places.csv"))]
roads = [{"from": r["from"], "to": r["to"], "km": float(r["km"]), "minutes": int(r["minutes"])} for r in csv.DictReader(open(rev / "roads.csv"))]
geo = Geo({"places": places, "roads": roads})

drivers = list(csv.DictReader(open(rev / "drivers.csv")))
s30 = geo.supply(drivers, 30.0)
s55 = geo.supply(drivers, 55.0)
s70 = geo.supply(drivers, 70.0)

print("=== SUPPLY BY TOWN ON DEV-10 (30km / 55km / 70km) ===")
for p in sorted(s30, key=lambda x: -s30[x]):
    print(f"  {p:14s}: 30km={s30[p]:3d}  55km={s55[p]:3d}  70km={s70[p]:3d}")

reqs = {r["id"]: r for r in csv.DictReader(open(rev / "requests.csv"))}
legs_by_req = defaultdict(list)
for l in csv.DictReader(open(rev / "legs.csv")):
    legs_by_req[l["requestId"]].append(l)

events = list(csv.DictReader(open(rev / "events.csv")))
late_lines = [e for e in events if e["kind"] == "ledger" and e["line.kind"] in ("late_refund", "undelivered_penalty")]
print()
print("=== LATE / UNDELIVERED ON DEV-10 (" + str(len(late_lines)) + ") ===")
for e in late_lines:
    oid = e["line.orderId"]
    r = reqs[oid]
    ls = legs_by_req[oid]
    p0, d0 = ls[0]["pickup.placeId"], ls[-1]["delivery.placeId"]
    print(f"  {oid} {e['line.kind']:20s} {int(e['line.cents'])/100:7.1f} EUR | opt={r['option']:10s} {p0}[{s30[p0]}]->{d0}[{s30[d0]}] arr={int(r['arrivedAt'])/60:5.1f}h pick={ls[0]['truth.pickedUpAt']} del={ls[-1]['truth.deliveredAt']}")

booked_at = {}
for e in events:
    if e["kind"] == "gig_booked" and e["gigId"] not in booked_at:
        booked_at[e["gigId"]] = (int(e["at"]), int(e["feeCents"]), e["driverId"])

gigs = list(csv.DictReader(open(rev / "gigs.csv")))
waits_by_opt = defaultdict(list)
for g in gigs:
    gid = g["id"]
    oids = [x.strip() for x in g["orders"].split(",") if x.strip()]
    if not oids or oids[0] not in reqs:
        continue
    opt = reqs[oids[0]]["option"]
    pat = int(g["postedAt"])
    if gid in booked_at:
        waits_by_opt[opt].append(booked_at[gid][0] - pat)

print()
print("=== GIG TIME-TO-FIRST-BOOKING BY OPTION ON DEV-10 ===")
for opt, ws in waits_by_opt.items():
    ws.sort()
    ge20 = sum(1 for w in ws if w >= 20)
    print(f"  {opt:14s}: n={len(ws):3d}  med={ws[len(ws)//2]:3d}m  >=20m: {ge20}/{len(ws)} ({100*ge20/len(ws):.1f}%)")

won_orders = [r for r in reqs.values() if r["outcome"] == "won"]
won_first_booked = {}
won_delivered = {}
for r in won_orders:
    oid = r["id"]
    ls = legs_by_req[oid]
    won_delivered[oid] = int(ls[-1]["truth.deliveredAt"]) if ls[-1]["truth.deliveredAt"] else 999999
    b_times = [booked_at[g["id"]][0] for g in gigs if oid in g["orders"].split(",") and g["id"] in booked_at]
    won_first_booked[oid] = min(b_times) if b_times else 999999

declined = []
for rid, r in reqs.items():
    quoted_opts = [(k, int(r[f"{k}.quoteCents"]), int(r[f"{k}.listPriceCents"])) for k in ("same_day", "next_day", "within_3_days") if r[f"{k}.quoteCents"]]
    if len(quoted_opts) == 1 and abs(quoted_opts[0][1] - 4 * quoted_opts[0][2]) <= 5:
        declined.append(r)

dec_slow = [r for r in declined if (r["next_day.listPriceCents"] or r["within_3_days.listPriceCents"]) and int(r["legs"]) == 1]
print()
print("=== DECLINED 1-CAR SLOW REQUESTS ON DEV-10: " + str(len(dec_slow)) + " (of " + str(len(declined)) + " total declined) ===")

unbooked_match = 0
booked_match = 0
either_match = 0
repat_booked_only = 0
both_details = []
for r in sorted(dec_slow, key=lambda x: int(x["arrivedAt"])):
    rid = r["id"]
    t_arr = int(r["respondBy"])
    lp = legs_by_req[rid][0]
    pb, db = lp["pickup.placeId"], lp["delivery.placeId"]
    drv_b = geo.minutes(pb, db)
    has_unb = False
    has_bkd = False
    sample_a = None
    for w in won_orders:
        oid = w["id"]
        if int(w["respondBy"]) > t_arr:
            continue
        la = legs_by_req[oid][-1]
        pa = legs_by_req[oid][0]["pickup.placeId"]
        da = la["delivery.placeId"]
        if geo.line_km(da, pb) > 15.0:
            continue
        drv_a = geo.minutes(pa, da)
        if drv_a + geo.minutes(da, pb) + drv_b > 720:
            continue
        fb = won_first_booked[oid]
        del_t = won_delivered[oid]
        if fb > t_arr:
            has_unb = True
            sample_a = ("UNBOOKED", oid, pa, da)
        elif fb <= t_arr < del_t:
            has_bkd = True
            if not sample_a:
                sample_a = ("BOOKED", oid, pa, da)
    if has_unb:
        unbooked_match += 1
    if has_bkd:
        booked_match += 1
    if has_bkd and not has_unb and s30[db] >= 30:
        repat_booked_only += 1
    if has_unb or has_bkd:
        either_match += 1
        both_details.append((t_arr, rid, pb, db, s30[pb], s30[db], has_unb, has_bkd, sample_a))

print(f"  Matches UNBOOKED won order (<=15km, <=12h): {unbooked_match}")
print(f"  Matches ALREADY-BOOKED active won order (<=15km, <=12h): {booked_match}")
print(f"  Matches EITHER unbooked or booked won order: {either_match} (booked-only NEW beyond unbooked: {either_match - unbooked_match}, of which s30[deliv]>=30: {repat_booked_only})")
print()
print("First 30 chainable declined slow requests on dev-10:")
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
for t_arr, rid, pb, db, sp, sd, hu, hb, sa in both_details[:30]:
    d_str = f"{DAYS[(t_arr//1440)%7]} {(t_arr%1440)//60:02d}:{t_arr%60:02d}"
    st = "UNB+BKD" if (hu and hb) else ("UNB_ONLY" if hu else "BKD_ONLY")
    print(f"  {d_str} {rid} {pb}[{sp}]->{db}[{sd}] | {st:8s} | e.g. {sa[1]} ({sa[2]}->{sa[3]})")
