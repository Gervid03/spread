"""Part of the unused-signals sizing (exp/claude-batch-bracket): reads the folder that signals_fetch.py writes."""
"""Does today's active supply (distinct viewers of our gigs, by home) predict staffing outcomes better than the static roster count?"""
import json, collections, sys, math, bisect
from pathlib import Path
M = json.load(open(sys.argv[2]))
pl = {p["id"]: (p["lat"], p["lon"]) for p in M["places"]}
def km(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (*pl[a], *pl[b]))
    h = math.sin((la2-la1)/2)**2 + math.cos(la1)*math.cos(la2)*math.sin((lo2-lo1)/2)**2
    return 6371*2*math.asin(math.sqrt(h))
rows = []
for f in sorted(Path(sys.argv[1]).glob("*.json")):
    d = json.loads(f.read_text()); ev = d["events"]
    home = {r["id"]: r["homePlaceId"] for r in d["roster"]}
    near55 = {p: {q for q in pl if km(p, q) <= 55} for p in pl}
    static = {p: sum(1 for h in home.values() if h in near55[p]) for p in pl}
    gig_orders = {g["id"]: list(dict.fromkeys(s["orderId"] for s in g["stops"])) for g in d["snapshot"]["gigs"]}
    views = [(e["at"], e["driverId"]) for e in ev if e["kind"] == "gig_viewed"]
    vt = [v[0] for v in views]
    late = {e["line"]["orderId"] for e in ev if e["kind"] == "ledger" and e["line"]["kind"] in ("late_refund", "undelivered_penalty")}
    warned = {e["orderId"] for e in ev if e["kind"] == "deadline_close"}
    first_book = {}
    for e in ev:
        if e["kind"] == "gig_booked":
            for o in gig_orders.get(e["gigId"], []):
                first_book.setdefault(o, (e["at"], e["feeCents"]))
    for e in ev:
        if e["kind"] != "order_won": continue
        o = e["order"]
        if len(o["legs"]) != 1: continue
        t = e["at"]; p = o["legs"][0]["pickup"]["placeId"]
        i0 = bisect.bisect_left(vt, t - 360); i1 = bisect.bisect_right(vt, t)
        act = {drv for _, drv in views[i0:i1] if home[drv] in near55[p]}
        day0 = (t // 1440) * 1440
        j0 = bisect.bisect_left(vt, day0)
        act_day = {drv for _, drv in views[j0:i1] if home[drv] in near55[p]}
        fb = first_book.get(o["id"])
        rows.append(dict(seed=f.stem, static=static[p], act=len(act), act_day=len(act_day), late=o["id"] in late, warned=o["id"] in warned,
                         wait=(fb[0] - t) if fb else None, hour=(t % 1440) // 60, opt=o["option"]))
print("won 1-leg orders:", len(rows))
def tab(key, edges):
    out = collections.defaultdict(lambda: [0, 0, 0, []])
    for r in rows:
        k = next((f"<{e}" for e in edges if r[key] < e), f">={edges[-1]}")
        out[k][0] += 1; out[k][1] += r["late"]; out[k][2] += r["warned"]
        if r["wait"] is not None: out[k][3].append(r["wait"])
    for k in [f"<{e}" for e in edges] + [f">={edges[-1]}"]:
        if k in out:
            n, l, w, ws = out[k]; ws.sort()
            print(f"  {key} {k:>6}: n {n:4}  late {l/n:6.1%}  warned {w/n:6.1%}  median wait-to-book {ws[len(ws)//2] if ws else '-'}")
tab("static", [30, 60, 120, 250])
tab("act", [3, 8, 15, 30])
print("within static >= 60:")
keep = rows
rows = [r for r in keep if r["static"] >= 60]; tab("act", [5, 10, 20, 40])
print("within static 22-60:")
rows = [r for r in keep if 22 <= r["static"] < 60]; tab("act", [2, 4, 8, 15])
rows = keep
import statistics as st
print("corr static/act:", round(st.correlation([r["static"] for r in rows], [r["act"] for r in rows]), 3))
