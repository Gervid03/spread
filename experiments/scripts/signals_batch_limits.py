"""Unused-signals sizing: args = a TAS limits-all.jsonl (dev-12) and that seed's JSON from signals_fetch.py."""
import json, collections, sys, statistics as st, math
L = [json.loads(l) for l in open(sys.argv[1])]
d = json.load(open(sys.argv[2]))
req = {r["request"]["id"]: r for r in d["reveal"]["requests"]}
rows = [x for x in L if x["bound"] == "exact"]
def within(keyf, label, maxgap=None):
    g = collections.defaultdict(list)
    for r in rows: g[keyf(r)].append(r)
    devs = []; n = 0; grp = 0; cars = 0
    for k, v in g.items():
        if len(v) < 2: continue
        lx = [math.log(x["x"]) for x in v]; m = st.mean(lx)
        devs += [(a - m) ** 2 for a in lx]; n += len(v) - 1; grp += 1; cars += len(v)
    print(f"{label:55} groups {grp:4} cars {cars:5} sd {math.sqrt(sum(devs)/max(1,n)):.3f}")
B = lambda r: req[r["rid"]]["request"].get("batchId")
within(lambda r: 0, "global")
within(lambda r: (r["option"],), "option")
within(lambda r: (r["dealer"], r["option"]), "dealer+option")
within(lambda r: (r["pickup"], r["delivery"], r["option"]), "lane+option")
within(lambda r: (r["dealer"], r["pickup"], r["delivery"], r["option"]), "dealer+lane+option")
within(lambda r: (r["dealer"], r["pickup"], r["delivery"], r["option"], r["day"]), "dealer+lane+option+day")
within(lambda r: (r["pickup"], r["delivery"], r["option"], r["day"]), "lane+option+day")
within(lambda r: (r["dealer"], r["option"], r["day"]), "dealer+option+day")
within(lambda r: (B(r), r["delivery"], r["option"]) if B(r) else r["rid"], "batch+dest+option")
within(lambda r: (B(r), r["option"]) if B(r) else r["rid"], "batch+option")
# how x relates to trust / list ratio: does option ratio hold within request? x(next_day)/x(same_day)
pair = collections.defaultdict(dict)
for r in rows: pair[r["rid"]][r["option"]] = r["x"]
rat = [v["next_day"] / v["same_day"] for v in pair.values() if "next_day" in v and "same_day" in v]
print("x(next_day)/x(same_day) within a request: n", len(rat), "median", round(st.median(rat), 3), "sd(log)", round(st.pstdev([math.log(a) for a in rat]), 3))
