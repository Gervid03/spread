"""Experiment loops1: closed loops of 2-4 cars, chosen from the week's tape, won near the dealers' limits, posted as
one gig. And the "teach" test: does a Monday of releases make drivers book lower for the rest of the week?

Follows pairs1 (experiments/20261114-2230-claude-pairs1.md): a closed pair posted as one gig books at ~0.6x the two
typical fees and saves 15-19% of costs; separate gigs with a return offer did nothing; a fee search by releases lost
€15k. Open there: triangles and squares (one driver, a whole day of cars, back home), winning every piece of a loop
(pairs1 quoted the list price and won ~55%), and whether the release search teaches drivers anything.

Loops: every closed cycle of 2, 3 or 4 one-car slow-option dealer requests in the tape (each delivery within 30 km of
the next pickup, the last delivery within 30 km of the first pickup, under 700 road minutes, every deadline met with
SPARE to spare, all arriving within a day). Disjoint loops are taken greedily, biggest saving first (sum of typical
fees x (0.9 - the loop's opening multiple)). Quotes: each loop leg at QUOTE x its measured limit (tas-price's
limits-all.jsonl on this seed), every other request declined.

Arms (each one fresh world of the seed):
  loops   a loop is posted as one gig when all its cars are won, flat at OPEN[size] x the summed typical fees, raised
          once to 0.9x after BUMP minutes unbooked; a car whose loop broke (a leg lost) goes alone at 0.9x
  pairs   the same, sizes limited to 2 (a separate selection)
  solo    the loops arm's wins, every car alone at 0.9x (its control)
  solo2   the pairs arm's wins, every car alone (its control)
  teach   the loops selection posted alone; on Monday each car's fee is searched by releases (1.4x, booked -> release
          and halve down, an hour unbooked -> halve up); from Tuesday every car flat at TEACH x
  flat    the same without the Monday search: Monday at 0.9x, from Tuesday flat at TEACH x (teach's control)
Every arm keeps every event of its world (`events` in the output) and a timeline per gig, so the timing of each step
can be read afterwards.

    uv run --with networkx python experiments/orc/loops1.py dev-12 loops solo pairs solo2 teach flat
    uv run --with networkx python experiments/orc/loops1.py dev-12 report loops solo ...
Writes ~/.spread-lab/orc/<seed>/loops1-<arm>.json.
"""
import json
import statistics
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import networkx as nx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from orc import DAY, home, say, tape, world  # noqa: E402
from spread_lab.env import lab_home  # noqa: E402
from spread_lab.geo import Geo, load_map  # noqa: E402
from spread_lab.notes import note_flags  # noqa: E402
from spread_lab.policy import Retry, stops_for, without_windows  # noqa: E402

HOUR = 60
SEED = sys.argv[1]
ARMS = sys.argv[2:]
SPARE, BUMP, QUOTE, TEACH = 4 * HOUR, 120, 0.92, 0.7
OPEN = {2: 0.6, 3: 0.5, 4: 0.45}
SOLO, RESCUE = 0.9, 1.4
LO, HI, STEPS = 0.4, 1.4, 3
geo = Geo(load_map(None))
REQ = {r["id"]: r for r in tape(SEED)["requests"]}
LIMIT = {}
for line in open(lab_home() / "tas" / SEED / "limits-all.jsonl", encoding="utf-8"):
    x = json.loads(line)
    if x["bound"] == "exact":
        LIMIT[(x["rid"], x["option"])] = x["lo"]


# ── the loops, chosen from the tape before the week starts ────────────────────────────────────────────────
def slow_option(r):
    opts = [o for o in r["options"] if o["kind"] in ("next_day", "within_3_days")]
    return max(opts, key=lambda o: o["deadline"]) if opts else None


def ends(r):
    leg = r["legs"][0]
    return leg["pickup"]["placeId"], leg["delivery"]["placeId"]


def drivable(seq):
    """seq in this order in one gig: under 700 road minutes, every deadline met with SPARE to spare."""
    road = sum(geo.minutes(*ends(r)) for r in seq) + sum(geo.minutes(ends(a)[1], ends(b)[0]) for a, b in zip(seq, seq[1:]))
    if road > 700:
        return False
    t = max([r["respondBy"] + HOUR for r in seq] + [seq[0]["legs"][0]["pickup"]["window"]["from"]])
    if t % DAY > 20 * HOUR:
        t = t - t % DAY + DAY + 8 * HOUR
    t = max(t, t - t % DAY + 8 * HOUR)
    for i, r in enumerate(seq):
        if i:
            t += geo.minutes(ends(seq[i - 1])[1], ends(r)[0])
        t = max(t, r["legs"][0]["pickup"]["window"]["from"]) + geo.minutes(*ends(r))
        if t > slow_option(r)["deadline"] - SPARE:
            return False
    return True


def find_loops(max_size):
    ok = [r for r in REQ.values() if len(r["legs"]) == 1 and slow_option(r)
          and not r["legs"][0]["pickup"]["privateAddress"] and not r["legs"][0]["delivery"]["privateAddress"]]
    nxt = defaultdict(list)          # a -> b: b's pickup within 30 km of a's delivery, arriving within a day
    for a in ok:
        for b in ok:
            if a is not b and abs(a["arrivedAt"] - b["arrivedAt"]) <= DAY and geo.line_km(ends(a)[1], ends(b)[0]) <= 30:
                nxt[a["id"]].append(b["id"])
    closes = lambda last, first: geo.line_km(ends(REQ[last])[1], ends(REQ[first])[0]) <= 30  # noqa: E731
    found, seen = [], set()
    road = lambda p: sum(geo.minutes(*ends(REQ[i])) for i in p) + sum(  # noqa: E731
        geo.minutes(ends(REQ[a])[1], ends(REQ[b])[0]) for a, b in zip(p, p[1:]))

    def grow(path):
        if len(path) >= 2 and closes(path[-1], path[0]):
            key = frozenset(path)
            if key not in seen and drivable([REQ[i] for i in path]):
                seen.add(key)
                found.append(list(path))
        if len(path) < max_size:
            for j in nxt[path[-1]]:
                if j > path[0] and j not in path and abs(REQ[j]["arrivedAt"] - REQ[path[0]]["arrivedAt"]) <= DAY                         and road(path + [j]) <= 700:
                    grow(path + [j])

    for r in ok:                      # each loop once: it starts at its smallest id
        grow([r["id"]])
    saving = lambda c: sum(REQ[i]["referenceFeeCents"] for i in c) * (SOLO - OPEN[len(c)])  # noqa: E731
    if max_size == 2:                 # pairs: a maximum matching, as in pairs1
        g = nx.Graph()
        for c in found:
            g.add_edge(*c, w=saving(c), c=c)
        return [g.edges[e]["c"] for e in nx.max_weight_matching(g, maxcardinality=True)], len(ok), len(found)
    chosen, used = [], set()
    for c in sorted(found, key=saving, reverse=True):
        if not used & set(c):
            chosen.append(c)
            used |= set(c)
    return chosen, len(ok), len(found)


# ── the desk ──────────────────────────────────────────────────────────────────────────────────────────────
class Desk:
    def __init__(self, arm, loops):
        self.arm, self.loops = arm, loops
        self.loop_of = {i: tuple(c) for c in loops for i in c}
        self.orders, self.lost, self.held = {}, set(), set()
        self.gigs, self.sent, self.booked, self.driver = {}, [], {}, {}
        self.search = {}
        self.ledger, self.log = [], Counter()

    def fee_mult(self, now):
        if self.arm in ("teach", "flat") and now >= DAY:
            return TEACH
        return SOLO

    def post(self, oids, mult, kind, now, retry=Retry()):
        stops, manual = [], retry.manual_licence
        for o in oids:
            r = REQ[o]
            flags = note_flags(r["note"], v2=True)
            rt = retry._replace(plates=retry.plates or flags.plates)
            stops += without_windows(stops_for(self.orders[o], [0], r["note"], rt, geo, 200.0, True, r["arrivedAt"]), now)
            manual = manual or flags.manual
        fee = max(100, int(mult * sum(REQ[o]["referenceFeeCents"] for o in oids)))
        self.sent.append({"oids": list(oids), "kind": kind, "fee": fee, "at": now, "steps": [[now, fee, "post"]]})
        self.held -= set(oids)
        self.log[f"post_{kind}"] += 1
        premium = any(self.orders[o]["legs"][0]["car"]["premium"] for o in oids)
        return {"type": "post", "stops": stops, "audience": {"experienced": premium, "manualLicence": manual},
                "schedule": [{"at": now, "feeCents": fee}]}

    def reprice(self, g, fee, now, why):
        self.gigs[g]["fee"] = fee
        self.gigs[g]["steps"].append([now, fee, why])
        self.log[why] += 1
        return {"type": "reprice", "gigId": g, "schedule": [{"at": now, "feeCents": fee}]}

    def quote(self, r):
        o = slow_option(r) if r["id"] in self.loop_of else None
        if o:
            lim = LIMIT.get((r["id"], o["kind"]))
            price = int(QUOTE * lim) if lim else o["listPriceCents"]
            return {"type": "quote", "requestId": r["id"], "prices": {o["kind"]: price}}
        return {"type": "quote", "requestId": r["id"], "prices": {x["kind"]: 4 * x["listPriceCents"] for x in r["options"]}}

    def gig_of(self, oid):
        return next((g for g, x in self.gigs.items() if oid in x["oids"]), None)

    def won(self, oid, now):
        if self.arm in ("solo", "solo2", "teach", "flat"):
            if self.arm == "teach" and now < DAY:
                self.search[oid] = {"lo": LO, "hi": HI, "m": HI, "steps": 0}
                return [self.post([oid], HI, "search", now)]
            return [self.post([oid], self.fee_mult(now), "solo", now)]
        loop = self.loop_of[oid]
        self.held.add(oid)
        if any(i in self.lost for i in loop):
            return [self.post([oid], SOLO, "broken", now)]
        if all(i in self.held for i in loop):
            return [self.post(list(loop), OPEN[len(loop)], f"loop{len(loop)}", now)]
        return []

    def step(self, events, now):
        out = []
        for e in events:
            k = e["kind"]
            if k == "price_request":
                out.append(self.quote(e["request"]))
            elif k == "order_won":
                self.orders[e["order"]["id"]] = e["order"]
                out += self.won(e["order"]["id"], now)
            elif k == "order_lost":
                self.lost.add(e["requestId"])
                for i in self.loop_of.get(e["requestId"], ()):
                    if i in self.held:
                        out.append(self.post([i], SOLO, "broken", now))
            elif k == "order_changed" and "order" in e:
                self.orders[e["order"]["id"]] = e["order"]
            elif k == "order_cancelled":
                self.orders.pop(e["orderId"], None)
                self.held.discard(e["orderId"])
            elif k == "gig_booked":
                g = e["gigId"]
                self.booked[g], self.driver[g] = e["feeCents"], e["driverId"]
                if g in self.gigs:
                    self.gigs[g]["steps"].append([now, e["feeCents"], "booked"])
                    out += self.halve_down(g, now)
            elif k == "deadline_close":
                g = self.gig_of(e["orderId"])
                if g and g not in self.booked:
                    fee = int(RESCUE * sum(REQ[o]["referenceFeeCents"] for o in self.gigs[g]["oids"]))
                    if fee > self.gigs[g]["fee"]:
                        out.append(self.reprice(g, fee, now, "rescue"))
            elif k in ("gig_expired", "gig_dropped", "no_show"):
                g = e["gigId"]
                self.booked.pop(g, None)
                self.log[k] += 1
                if g in self.gigs:
                    self.gigs[g]["steps"].append([now, None, k])
                    if k == "gig_expired":
                        x = self.gigs.pop(g)
                        self.done.append(x)
                        out += [self.post([o], RESCUE, "rescue", now) for o in x["oids"] if o in self.orders]
            elif k == "visit_failed":
                self.log["visit_failed_" + e["reason"]] += 1
                if e["orderId"] in self.orders:
                    retry = Retry(pickup_from=now + HOUR, manual_licence=e["reason"] == "licence", plates=e["reason"] == "no_plates")
                    out.append(self.post([e["orderId"]], RESCUE, "rescue", now, retry))
            elif k == "ledger":
                self.ledger.append(e["line"])
        for g, x in list(self.gigs.items()):
            if g in self.booked:
                continue
            last = x["steps"][-1][0]
            if x["kind"].startswith("loop") and not x.get("bumped") and now - x["at"] >= BUMP:
                x["bumped"] = True
                out.append(self.reprice(g, int(SOLO * sum(REQ[o]["referenceFeeCents"] for o in x["oids"])), now, "bump"))
            elif x["kind"] == "search" and now - last >= HOUR:
                o = x["oids"][0]
                sr = self.search[o]
                if sr["steps"] < STEPS and now < DAY and self.orders.get(o, {}).get("lastPickupAt", 0) - now > 8 * HOUR:
                    sr["lo"], sr["steps"] = sr["m"], sr["steps"] + 1
                    sr["m"] = (sr["lo"] + sr["hi"]) / 2
                    out.append(self.reprice(g, int(sr["m"] * REQ[o]["referenceFeeCents"]), now, "search_up"))
        for oid in list(self.held):
            if self.orders.get(oid, {}).get("lastPickupAt", 0) - now < 6 * HOUR:
                out.append(self.post([oid], SOLO, "broken", now))
        return out

    def halve_down(self, g, now):
        x = self.gigs[g]
        if x["kind"] != "search":
            return []
        o = x["oids"][0]
        sr = self.search[o]
        if sr["steps"] >= STEPS or now >= DAY or self.orders.get(o, {}).get("lastPickupAt", 0) - now <= 8 * HOUR:
            return []
        sr["hi"], sr["steps"] = sr["m"], sr["steps"] + 1
        sr["m"] = (sr["lo"] + sr["hi"]) / 2
        self.booked.pop(g, None)
        x["steps"].append([now, None, "released"])
        self.gigs.pop(g)
        self.done.append(x)
        self.log["release"] += 1
        return [{"type": "release", "gigId": g}, self.post([o], sr["m"], "search", now)]

    def took(self, actions, results):
        res = [r for a, r in zip(actions, results) if a["type"] == "post"]
        for meta, r in zip(self.sent, res):
            if r.get("ok"):
                self.gigs[r["id"]] = meta
            else:
                self.log["refused"] += 1
        self.sent = []


KINDS = ["price_request", "order_won", "order_lost", "order_changed", "order_cancelled", "gig_booked", "deadline_close",
         "gig_expired", "gig_dropped", "no_show", "visit_failed"]
SELECT = {}


def selection(arm):
    size = 2 if arm in ("pairs", "solo2") else 4
    if size not in SELECT:
        SELECT[size] = find_loops(size)
    return SELECT[size]


def play(arm):
    loops, cands, nfound = selection(arm)
    desk = Desk(arm, loops)
    desk.done = []
    with world(SEED, what=f"loops1-{arm}") as w:
        pending = []
        while w.now < w.ends_at:
            results, events = w.advance(until=KINDS, max=min(w.ends_at, w.now + 30), actions=pending)
            desk.took(pending, results)
            pending = desk.step(events, w.now)
        score = w.score()
        events = w.events
    out = {"seed": SEED, "arm": arm, "loops": loops, "score": score, "log": dict(desk.log),
           "gigs": [{**x, "id": g, "booked": desk.booked.get(g)} for g, x in desk.gigs.items()] + desk.done,
           "ledger": desk.ledger, "events": events}
    (home(SEED) / f"loops1-{arm}.json").write_text(json.dumps(out), encoding="utf-8")
    return out


def report(o):
    s = o["score"]
    costs = (s["revenueCents"] - s["marginCents"]) / 100
    late = {l["orderId"] for l in o["ledger"] if l["kind"] in ("late_refund", "undelivered_penalty") and l.get("orderId")}
    rel = -sum(l["cents"] for l in o["ledger"] if l["kind"] == "release_fee") / 100
    say(f"{o['arm']:>6}: margin €{s['marginCents'] / 100:9,.0f}  revenue €{s['revenueCents'] / 100:7,.0f}  costs €{costs:7,.0f}"
        f"  won {s['wonOrders']:3d}  on time {100 * s['onTimeShare']:5.1f}%  release fees €{rel:,.0f}")
    by = defaultdict(list)
    for x in o["gigs"]:
        by[x["kind"]].append(x)
    for kind, xs in sorted(by.items()):
        ref = lambda x: sum(REQ[i]["referenceFeeCents"] for i in x["oids"])  # noqa: E731
        booked = [x for x in xs if any(st[2] == "booked" for st in x["steps"])]
        waits = Counter()           # minutes from the gig's last price change to its booking, in bins
        for x in booked:
            b = next(st for st in x["steps"] if st[2] == "booked")
            before = [st for st in x["steps"] if st[0] <= b[0] and st[2] in ("post", "bump", "rescue", "search_up")]
            m = b[0] - before[-1][0]
            waits["<15" if m < 15 else "15-30" if m < 30 else "30-60" if m < 60 else "60-120" if m < 120 else "120+"] += 1
            waits[f"after {before[-1][2]}"] += 1
        fees = [next(st[1] for st in x["steps"] if st[2] == "booked") / ref(x) for x in booked]
        cars = {i for x in xs for i in x["oids"]}
        say(f"        {kind:>8}: {len(xs):3d} gigs ({len(cars)} cars), booked {len(booked):3d}, fee x typical median "
            f"{statistics.median(fees) if fees else 0:.2f}, late cars {len(cars & late)}; booked after: {dict(waits)}")


if __name__ == "__main__":
    if ARMS[0] == "report":
        for arm in ARMS[1:]:
            report(json.loads((home(SEED) / f"loops1-{arm}.json").read_text(encoding="utf-8")))
        sys.exit()
    for size in sorted({2 if a in ("pairs", "solo2") else 4 for a in ARMS}):
        loops, cands, nfound = selection("pairs" if size == 2 else "loops")
        say(f"{SEED}, loops up to {size} cars: {nfound} closed loops among {cands} requests; chosen {len(loops)} "
            f"disjoint: {dict(Counter(len(c) for c in loops))} = {sum(len(c) for c in loops)} cars")
    with ThreadPoolExecutor(len(ARMS)) as ex:
        for o in ex.map(play, ARMS):
            report(o)
