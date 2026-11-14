"""Part of the unused-signals sizing (exp/claude-batch-bracket): reads the folder that signals_fetch.py writes."""
import json, collections, sys, statistics as st
from pathlib import Path
T = collections.Counter()
batch_sizes = collections.Counter()
drop_by_hist = collections.defaultdict(lambda: [0, 0])  # drops>0? -> [bookings, dropped]
drop_by_rating = collections.defaultdict(lambda: [0, 0])
late_causes = collections.Counter()
bt = collections.defaultdict(lambda: collections.Counter())
for f in sorted(Path(sys.argv[1]).glob("*.json")):
    d = json.loads(f.read_text()); ev = d["events"]
    roster = {r["id"]: r for r in d["roster"]}
    K = collections.Counter(e["kind"] for e in ev)
    for k in ("driver_late", "no_show", "visit_failed", "gig_dropped", "gig_expired", "forecast", "release", "order_changed", "order_cancelled", "deadline_close", "order_won"):
        T[k] += K[k]
    gig_orders = {g["id"]: list(dict.fromkeys(s["orderId"] for s in g["stops"])) for g in d["snapshot"]["gigs"]}
    late = {e["line"]["orderId"] for e in ev if e["kind"] == "ledger" and e["line"]["kind"] in ("late_refund", "undelivered_penalty")}
    T["late"] += len(late)
    led = collections.Counter()
    for e in ev:
        if e["kind"] == "ledger":
            led[e["line"]["kind"]] += e["line"]["cents"]
    for k, v in led.items():
        T["cents_" + k] += v
    touched = collections.defaultdict(set)
    for e in ev:
        if e["kind"] in ("gig_dropped", "no_show", "gig_expired", "driver_late"):
            for o in gig_orders.get(e["gigId"], []):
                touched[o].add(e["kind"])
        elif e["kind"] in ("visit_failed", "deadline_close"):
            touched[e["orderId"]].add(e["kind"])
        elif e["kind"] == "order_changed":
            touched[e["order"]["id"]].add("changed")
    for o in late:
        late_causes[tuple(sorted(touched.get(o, {"none"})))] += 1
    # roster drops vs our drops: booking -> was it dropped by that driver?
    booked = [(e["gigId"], e["driverId"], e["at"]) for e in ev if e["kind"] == "gig_booked"]
    dropped = collections.Counter((e["gigId"], e["driverId"]) for e in ev if e["kind"] == "gig_dropped")
    for g, drv, at in booked:
        r = roster[drv]
        key = "0" if r["drops"] == 0 else ("1-2" if r["drops"] <= 2 else "3+")
        rate = r["drops"] / max(1, r["completedGigs"])
        key2 = "rate0" if r["drops"] == 0 else ("rate<2%" if rate < 0.02 else ("rate<5%" if rate < 0.05 else "rate5%+"))
        x = 1 if dropped[(g, drv)] else 0
        drop_by_hist[key][0] += 1; drop_by_hist[key][1] += x
        drop_by_rating[key2][0] += 1; drop_by_rating[key2][1] += x
    # batches
    reqs = d["reveal"]["requests"]
    by = collections.defaultdict(list)
    for r in reqs:
        b = r["request"].get("batchId")
        if b: by[b].append(r)
    T["requests"] += len(reqs); T["batched_requests"] += sum(len(v) for v in by.values())
    for b, rs in by.items():
        n = len(rs); batch_sizes[min(n, 40) // 5 * 5 if n >= 5 else n] += 1
        pick = collections.Counter(r["request"]["legs"][0]["pickup"]["placeId"] for r in rs)
        deal = collections.Counter(r["request"]["dealerId"] for r in rs)
        cls = "bulk15+" if n >= 15 else ("5-14" if n >= 5 else "2-4")
        bt[cls]["batches"] += 1; bt[cls]["reqs"] += n
        bt[cls]["one_pickup"] += 1 if len(pick) == 1 else 0
        bt[cls]["one_dealer"] += 1 if len(deal) == 1 else 0
        bt[cls]["arrive_same_min"] += 1 if len({r["request"]["arrivedAt"] for r in rs}) == 1 else 0
        for r in rs:
            bt[cls][r["outcome"]] += 1
            if r["outcome"] == "won" and r["request"]["id"] in late: bt[cls]["won_late"] += 1
    for r in reqs:
        if not r["request"].get("batchId"):
            bt["single"]["reqs"] += 1; bt["single"][r["outcome"]] += 1
            if r["outcome"] == "won" and r["request"]["id"] in late: bt["single"]["won_late"] += 1
print("TOTALS over 16 worlds:", dict(T))
print("late causes:", late_causes.most_common())
print("drop rate by roster drops:", {k: (v[0], v[1], round(v[1] / max(1, v[0]), 3)) for k, v in sorted(drop_by_hist.items())})
print("drop rate by roster drop-rate:", {k: (v[0], v[1], round(v[1] / max(1, v[0]), 3)) for k, v in sorted(drop_by_rating.items())})
print("batch size hist:", sorted(batch_sizes.items()))
for k, v in bt.items(): print(k, dict(v))
