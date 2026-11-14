"""Experiment 1: what do direct offers cost? (dev-12, one time point)

Wins every one-car dealer-site request up to T at a throwaway price, posts each as a 1-cent gig (nobody books it),
then on forks:
  A. offers every driver 1 cent: `declined` = the driver read it, `expired` = unread. Who reads offers at T?
  B. for (gig, driver) pairs, bisects the lowest offer fee the driver accepts, in tracks:
     home = the driver lives at the delivery place (within 30 km), out = lives at the pickup, far = neither.
Writes ~/.spread-lab/orc/<seed>/offers1-<T>.json.
"""
import json
import math
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from orc import clock, home, say, solo_post, tape, world  # noqa: E402
from spread_lab.env import lab_home  # noqa: E402

SEED = sys.argv[1] if len(sys.argv) > 1 else "dev-12"
T = int(sys.argv[2]) if len(sys.argv) > 2 else 780
ROUNDS = 8
HI = 3.0

places = {p["id"]: p for p in json.loads((lab_home() / "map.json").read_text(encoding="utf-8"))["places"]}


def km(a, b):
    pa, pb = places[a], places[b]
    la1, lo1, la2, lo2 = map(math.radians, (pa["lat"], pa["lon"], pb["lat"], pb["lon"]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


tp = tape(SEED)
roster = {d["id"]: d for d in tp["roster"]}
n = [0]


def quote(request, now):
    legs = request["legs"]
    if len(legs) != 1 or legs[0]["pickup"]["privateAddress"] or legs[0]["delivery"]["privateAddress"]:
        return None
    n[0] += 1
    opts = request["options"]
    kinds = [o["kind"] for o in opts]
    pick = opts[0] if (n[0] % 2 == 0 and "same_day" in kinds) else opts[-1]
    return {pick["kind"]: max(100, int(pick["listPriceCents"] * 0.3))}


def answers(events):
    return {(e["gigId"], e["driverId"]): e["answer"] for e in events if e["kind"] == "offer_answered"}


with world(SEED, what="offers1") as w:
    w.to(T, on_request=quote)
    orders = dict(w.orders)
    say(f"{clock(w.now)}: {len(orders)} orders won of {n[0]} quoted; requests {w.client.requests}")
    oids = sorted(orders)
    res = w.act([solo_post(orders[o], 1, w.now) for o in oids])
    gig = {o: r["id"] for o, r in zip(oids, res) if r.get("ok")}
    bad = [(o, r.get("reason")) for o, r in zip(oids, res) if not r.get("ok")]
    say(f"posted {len(gig)} gigs; refused {len(bad)}: {bad[:3]}")
    reqs = {r["id"]: r for r in tp["requests"]}
    info = {}
    for o in gig:
        od = orders[o]
        leg = od["legs"][0]
        info[o] = {"gig": gig[o], "option": od["option"], "pickup": leg["pickup"]["placeId"], "delivery": leg["delivery"]["placeId"],
                   "ref": reqs[o]["referenceFeeCents"], "deadline": od["deadline"], "from": leg["pickup"]["window"]["from"],
                   "lastPickupAt": od.get("lastPickupAt"), "premium": leg["car"]["premium"]}
    out = {"seed": SEED, "T": T, "orders": info, "scan": {}, "pairs": []}

    # A. who reads an offer now
    drivers = sorted(roster)
    glist = sorted(gig.values())
    per = 3 * len(glist)
    reads = {}
    for i in range(0, len(drivers), per):
        part = drivers[i:i + per]
        acts = [{"type": "offer", "gigId": glist[j // 3], "driverId": d, "feeCents": 1} for j, d in enumerate(part)]
        with w.fork() as f:
            results, events = f.advance(by=11, actions=acts)
            ans = answers(events)
            for a, r in zip(acts, results):
                reads[a["driverId"]] = ans.get((a["gigId"], a["driverId"])) if r.get("ok") else "refused:" + str(r.get("reason"))[:60]
    out["scan"] = reads
    say("scan:", Counter(v if not str(v).startswith("refused") else "refused" for v in reads.values()))
    say("refusals:", Counter(v for v in reads.values() if str(v).startswith("refused")).most_common(3))
    readers = [d for d, v in reads.items() if v == "declined"]
    say("readers by home:", Counter(roster[d]["homePlaceId"] for d in readers).most_common())

    # B. reservation fees by bisection, in tracks
    rnd = random.Random(7)
    tracks = []
    for kind in ("home", "out", "far", "home", "out", "far", "any", "any"):
        free = set(readers)
        pairs = []
        order_ids = list(info)
        rnd.shuffle(order_ids)
        for o in order_ids:
            it = info[o]

            def cls(d, it=it):
                h = roster[d]["homePlaceId"]
                if km(h, it["delivery"]) <= 30:
                    return "home"
                if km(h, it["pickup"]) <= 30:
                    return "out"
                return "far"

            cand = [d for d in free if kind == "any" or cls(d) == kind]
            if it["premium"]:
                cand = [d for d in cand if roster[d]["rating"] >= 4.8 and roster[d]["completedGigs"] >= 50]
            if not cand:
                continue
            d = rnd.choice(sorted(cand))
            free.discard(d)
            pairs.append({"order": o, "driver": d, "cls": cls(d), "lo": 0.0, "hi": None, "state": "open", "log": []})
        tracks.append(pairs)
        say(f"track {kind}: {len(pairs)} pairs")
    for ti, pairs in enumerate(tracks):
        for rd in range(ROUNDS):
            live = [p for p in pairs if p["state"] == "open"]
            if not live:
                break
            acts = []
            for p in live:
                x = HI if p["hi"] is None else (p["lo"] + p["hi"]) / 2
                p["x"] = x
                acts.append({"type": "offer", "gigId": info[p["order"]]["gig"], "driverId": p["driver"],
                             "feeCents": max(1, int(x * info[p["order"]]["ref"]))})
            with w.fork() as f:
                results, events = f.advance(by=11, actions=acts)
                ans = answers(events)
            for p, a, r in zip(live, acts, results):
                got = ans.get((a["gigId"], a["driverId"])) if r.get("ok") else "refused"
                p["log"].append([round(p["x"], 4), got])
                if got == "accepted":
                    p["hi"] = p["x"]
                elif p["hi"] is None:
                    p["state"] = "no:" + str(got)     # not even at HI
                else:
                    p["lo"] = p["x"]
        done = [p for p in pairs if p["hi"] is not None]
        say(f"track {ti}: {len(done)} of {len(pairs)} accept at <= {HI}x; median x {sorted(p['hi'] for p in done)[len(done) // 2] if done else None}")
        out["pairs"] += pairs
        (home(SEED) / f"offers1-{T}.json").write_text(json.dumps(out), encoding="utf-8")
    by = defaultdict(list)
    for p in out["pairs"]:
        by[p["cls"]].append(p["hi"])
    for k, v in by.items():
        ok = sorted(x for x in v if x is not None)
        say(k, "pairs", len(v), "accepting", len(ok), "quantiles", [round(ok[int(len(ok) * q)], 3) for q in (0.1, 0.25, 0.5, 0.75, 0.9)] if ok else None)
    say("requests", w.client.requests)
