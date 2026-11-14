"""Part of the unused-signals sizing (exp/claude-batch-bracket): reads the folder that signals_fetch.py writes."""
import json, collections, sys
from pathlib import Path
neg = 0; eq = 0; droppers = 0; cg_diff = []
by_start = collections.defaultdict(lambda: [0, 0])
by_rate = collections.defaultdict(lambda: [0, 0])
by_exp = collections.defaultdict(lambda: [0, 0])
for f in sorted(Path(sys.argv[1]).glob("*.json")):
    d = json.loads(f.read_text()); ev = d["events"]
    roster = {r["id"]: r for r in d["roster"]}
    k = collections.Counter(e["driverId"] for e in ev if e["kind"] == "gig_dropped")
    done = collections.Counter()
    gig_drv = {}
    for e in ev:
        if e["kind"] == "gig_booked": gig_drv[e["gigId"]] = e["driverId"]
        if e["kind"] == "gig_dropped": gig_drv.pop(e["gigId"], None)
    for g in d["snapshot"]["gigs"]:
        if g["status"] == "done" and g["driverId"]: done[g["driverId"]] += 1
    for drv, n in k.items():
        droppers += 1
        s = roster[drv]["drops"] - n
        if s < 0: neg += 1
        if s == 0: eq += 1
    dropped = collections.Counter((e["gigId"], e["driverId"]) for e in ev if e["kind"] == "gig_dropped")
    for e in ev:
        if e["kind"] != "gig_booked": continue
        r = roster[e["driverId"]]
        start = r["drops"] - k[e["driverId"]]
        cg = r["completedGigs"] - done[e["driverId"]]
        x = 1 if dropped[(e["gigId"], e["driverId"])] else 0
        key = "0" if start <= 0 else ("1" if start == 1 else ("2-3" if start <= 3 else "4+"))
        by_start[key][0] += 1; by_start[key][1] += x
        rate = max(0, start) / max(1, cg)
        rk = "0" if start <= 0 else ("<2%" if rate < .02 else ("<5%" if rate < .05 else ("<10%" if rate < .1 else "10%+")))
        by_rate[rk][0] += 1; by_rate[rk][1] += x
        ek = ("exp" if r["rating"] >= 4.8 and cg >= 50 else "new" if cg < 10 else "mid")
        by_exp[ek][0] += 1; by_exp[ek][1] += x
print("droppers", droppers, "end-our<0:", neg, "end-our==0:", eq)
fmt = lambda D: {k: (v[0], v[1], round(v[1] / max(1, v[0]), 3)) for k, v in sorted(D.items())}
print("by start drops:", fmt(by_start))
print("by start drop rate:", fmt(by_rate))
print("by experience:", fmt(by_exp))
