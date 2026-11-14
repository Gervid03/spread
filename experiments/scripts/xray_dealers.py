import collections
import csv
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


rank_stats = collections.defaultdict(lambda: collections.Counter())
trust_gap_stats = collections.defaultdict(lambda: collections.Counter())

for d in sorted(root.iterdir()):
    places = {p["id"]: (float(p["lat"]), float(p["lon"])) for p in rd(d, "places")}
    line = {(a, b): hav(places[a], places[b]) for a in places for b in places}
    roads = {(r["from"], r["to"]): (float(r["km"]), int(r["minutes"])) for r in rd(d, "roads")}
    drivers = {x["id"]: x for x in rd(d, "drivers")}
    homes = collections.Counter(x["homePlaceId"] for x in drivers.values())
    supply = {p: sum(n for h, n in homes.items() if line[(p, h)] <= 30) for p in places}
    reqs = {r["id"]: r for r in rd(d, "requests")}
    legs_by_req = collections.defaultdict(list)
    for l in rd(d, "legs"):
        legs_by_req[l["requestId"]].append(l)
    events = rd(d, "events")

    order_ledger = collections.defaultdict(collections.Counter)
    late_orders = set()
    cur_dl = {}
    for e in events:
        if e["kind"] == "order_won":
            cur_dl[e["order.id"]] = int(e["order.deadline"])
        elif e["kind"] == "ledger" and e["line.orderId"]:
            oid = e["line.orderId"]
            order_ledger[oid][e["line.kind"]] += int(e["line.cents"])
            if e["line.kind"] in ("late_refund", "undelivered_penalty"):
                late_orders.add(oid)

    # Rank dealers by total requests in the week
    tot_req_by_dlr = collections.Counter(r["dealerId"] for r in reqs.values())
    ranked_dlrs = [dlr for dlr, _ in tot_req_by_dlr.most_common()]
    dlr_rank = {dlr: i + 1 for i, dlr in enumerate(ranked_dlrs)}

    # Replay trust + simulated dealer_adj (lr=0.01)
    dealer_trust = collections.defaultdict(int)
    dealer_adj = collections.defaultdict(lambda: 1.0)
    seen_late = set()
    req_by_min = collections.defaultdict(list)
    for r in reqs.values():
        req_by_min[int(r["arrivedAt"])].append(r)
    ev_idx = 0
    all_mins = sorted(set(req_by_min.keys()) | {int(e["at"]) for e in events})
    for m in all_mins:
        for r in req_by_min.get(m, []):
            q_opts = {k: int(r[f"{k}.quoteCents"]) for k in ("same_day", "next_day", "within_3_days") if r.get(f"{k}.quoteCents")}
            if not q_opts:
                continue
            fk = next(iter(q_opts))
            m0 = q_opts[fk] / int(r[f"{fk}.listPriceCents"])
            if m0 > 3.5:
                continue
            ref = int(r["referenceFeeCents"])
            floor_c = int(ref * 1.25 / 0.92 + 0.5)
            is_fl = any(abs(v - floor_c) <= 2 for v in q_opts.values())
            dlr = r["dealerId"]
            rk = dlr_rank[dlr]
            rk_b = "rank_1_3" if rk <= 3 else ("rank_4_8" if rk <= 8 else ("rank_9_15" if rk <= 15 else "rank_16+"))
            won = 1 if r["outcome"] == "won" else 0
            rank_stats[rk_b]["q"] += 1
            rank_stats[rk_b]["w"] += won
            if not is_fl:
                rank_stats[rk_b]["uq"] += 1
                rank_stats[rk_b]["uw"] += won
            if won:
                rank_stats[rk_b]["marg"] += sum(order_ledger[r["id"]].values())
                rank_stats[rk_b]["late"] += (1 if r["id"] in late_orders else 0)

            if not is_fl:
                # Compare trust bonus (1 + 0.01*trust) vs dealer_adj
                gap = (1.0 + 0.01 * dealer_trust[dlr]) - dealer_adj[dlr]
                gb = "gap<-0.02" if gap < -0.02 else ("gap_-0.02..0.05" if gap < 0.05 else ("gap_0.05..0.15" if gap < 0.15 else "gap_0.15+"))
                trust_gap_stats[gb]["uq"] += 1
                trust_gap_stats[gb]["uw"] += won
                step = 0.60 if won else -0.40
                dealer_adj[dlr] = max(0.85, min(1.30, dealer_adj[dlr] * math.exp(0.01 * step)))

        while ev_idx < len(events) and int(events[ev_idx]["at"]) <= m:
            e = events[ev_idx]
            ev_idx += 1
            if e["kind"] == "ledger" and e.get("line.orderId"):
                oid = e["line.orderId"]
                dlr = reqs[oid]["dealerId"] if oid in reqs else None
                lk = e["line.kind"]
                if lk in ("late_refund", "undelivered_penalty"):
                    seen_late.add(oid)
                    if dlr:
                        dealer_trust[dlr] //= 2
                elif lk == "revenue" and dlr and oid not in seen_late:
                    if int(e["at"]) <= cur_dl.get(oid, 10**9):
                        dealer_trust[dlr] = min(25, dealer_trust[dlr] + 1)

    for rk_b_dlr in ranked_dlrs:
        rk = dlr_rank[rk_b_dlr]
        rk_b = "rank_1_3" if rk <= 3 else ("rank_4_8" if rk <= 8 else ("rank_9_15" if rk <= 15 else "rank_16+"))
        rank_stats[rk_b]["end_trust_sum"] += dealer_trust[rk_b_dlr]
        rank_stats[rk_b]["dlr_n"] += 1

print("=== DEALER RANK BUCKETS (16 WORLDS) ===")
for k in ["rank_1_3", "rank_4_8", "rank_9_15", "rank_16+"]:
    v = rank_stats[k]
    print(f"  {k:<12} q={v['q']:4d} w={v['w']:4d} ({v['w']/v['q']:5.1%}) unfl_win={v['uw']/max(v['uq'],1):5.1%} late={v['late']/max(v['w'],1):4.1%} marg/w={v['marg']/100/max(v['w'],1):5.1f} end_trust={v['end_trust_sum']/max(v['dlr_n'],1):4.1f}")

print("=== TRUST BONUS (1 + 0.01*trust) MINUS dealer_adj ON UNFLOORED QUOTES ===")
for k in ["gap<-0.02", "gap_-0.02..0.05", "gap_0.05..0.15", "gap_0.15+"]:
    v = trust_gap_stats[k]
    if v["uq"]:
        print(f"  {k:<18} uq={v['uq']:4d} uw={v['uw']:4d} (unfl_win%={v['uw']/v['uq']:5.1%})")
