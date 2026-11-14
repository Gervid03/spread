"""Unused-signals sizing: args = a TAS limits-all.jsonl (dev-12) and that seed's JSON from signals_fetch.py."""
"""Offline: would a per-batch price bracket have earned more on dev-12, against the exact dealer limits?"""
import json, collections, sys, math
L = [json.loads(l) for l in open(sys.argv[1])]
d = json.load(open(sys.argv[2]))
req = {r["request"]["id"]: r for r in d["reveal"]["requests"]}
lim = {(x["rid"], x["option"]): x for x in L if x["bound"] == "exact"}
STEP = 10
def visible(t_out, t_dec, step):  # an outcome at t_out can change a quote decided at t_dec (needs a step end in [t_out, t_dec))
    if step == 1: return t_out < t_dec
    first_end = math.ceil(t_out / step) * step
    return first_end < t_dec
# consistency: champion outcome vs limit
ok = bad = 0
for (rid, opt), x in lim.items():
    r = req[rid]; q = (r.get("quote") or {}).get(opt)
    if not q or r["outcome"] == "unquoted" or q >= 3 * x["list"]: continue
    if r["outcome"] == "won" and r["option"] == opt: ok += (q <= x["hi"]); bad += (q > x["hi"])
print("consistency won<=hi:", ok, bad)
for step in (10, 1):
  for up, down in ((0.04, 0.06), (0.06, 0.08), (0.08, 0.10)):
    groups = collections.defaultdict(list)
    for rid, r in req.items():
        b = r["request"].get("batchId"); q = r.get("quote") or {}
        if not b or not q: continue
        if len(q) != 1: continue  # single-option quotes only, for a clean comparison
        (opt, cents), = q.items()
        opts = {o["kind"]: o for o in r["request"]["options"]}
        if cents >= 3 * opts[opt]["listPriceCents"] or (rid, opt) not in lim: continue
        groups[(b, opt, r["request"]["legs"][-1]["delivery"]["placeId"])].append((r["request"]["arrivedAt"], rid, opt, cents, opts[opt]["listPriceCents"]))
    base_rev = new_rev = 0; base_w = new_w = 0; changed = 0; n = 0
    for g, cars in groups.items():
        cars.sort()
        hist = []  # (outcome time, x_quoted, won)
        for arr, rid, opt, cents, lst in cars:
            n += 1
            x = lim[(rid, opt)]; limit_c = (x["lo"] + x["hi"]) / 2
            q0 = cents
            known = [(xq, w) for (t, xq, w) in hist if visible(t, arr + 15, step)]
            q1 = q0
            if known:
                los = [xq for xq, w in known if w]; his = [xq for xq, w in known if not w]
                lo = max(los) if los else None; hi = min(his) if his else None
                if lo and hi and lo < hi: q1 = (lo + hi) / 2 * lst
                elif lo and not hi: q1 = max(q0, lo * (1 + up) * lst)
                elif hi and not lo: q1 = min(q0, hi * (1 - down) * lst)
            q1 = int(q1)
            if q1 != q0: changed += 1
            w0 = q0 <= limit_c; w1 = q1 <= limit_c
            base_rev += q0 * w0; new_rev += q1 * w1; base_w += w0; new_w += w1
            hist.append((arr + 15, q1 / lst, w1))
    print(f"step {step:2} up {up} down {down}: cars {n}, changed {changed}, wins {base_w}->{new_w}, revenue €{base_rev/100:.0f} -> €{new_rev/100:.0f} (Δ €{(new_rev-base_rev)/100:+.0f})")
