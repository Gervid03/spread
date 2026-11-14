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
OPEN = {1: 0.5, 2: 0.6, 3: 0.5, 4: 0.45, "c": 0.65}   # 1 = a homeward single (offers meanwhile); "c" = chain home
SOLO, RESCUE = 0.9, 1.4
LO, HI, STEPS = 0.4, 1.4, 3
HOME_OFFER, POOL = 0.75, 40   # ride home: offered at 0.75x to drivers living near the delivery; a pool = 40+ drivers
RET = {"ret6": 0.6, "ret9": 0.9}   # way back offered to the driver the minute they deliver the first car, at this x typical
THIN = {"thin10": 1.0, "thin12": 1.2}   # his "driver first": thin-town cars (< 22 drivers near), paid up front
THIN_MAX = 22
SD = {"sd75": 0.75, "sd100": 1.0}    # same_day into a pool from a town v7 won't quote same_day in; posted at once at this x
SD_BUMP = 60
WEEK_MIN_MARGIN = 1500               # week arms: a single car is quoted when QUOTE x limit - SOLO x typical >= this (cents)                         # same_day: raise to 1.4x after an hour unbooked
OFF_OPEN = 0.75                    # offers arms: every car alone at 0.75x, raised to 0.9x after BUMP; offa/offu add offers
geo = Geo(load_map(None))
TAPE = tape(SEED)
REQ = {r["id"]: r for r in TAPE["requests"]}
ROSTER = {d["id"]: d for d in TAPE["roster"]}
NEAR = {p: sum(1 for d in ROSTER.values() if geo.line_km(d["homePlaceId"], p) <= 30) for p in geo.places}
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


def homeward(exclude):
    """One-car slow-option dealer requests that end in a pool (40+ drivers within 30 km of the delivery) and start
    outside it: for a driver living there, the car is a ride home."""
    out = []
    for r in REQ.values():
        if r["id"] in exclude or len(r["legs"]) != 1 or not slow_option(r):
            continue
        leg = r["legs"][0]
        if leg["pickup"]["privateAddress"] or leg["delivery"]["privateAddress"]:
            continue
        p, d = ends(r)
        if NEAR[d] >= POOL and geo.line_km(p, d) > 30:
            out.append([r["id"]])
    return out


def chains_home():
    """His idea (Sun 00:30): a driver living in A takes the train to B, drives B -> C, then C' -> A home. Two cars x, y:
    y's pickup within 30 km of x's delivery, y ends in a pool A (40+ drivers), x starts outside A (so it isn't a closed
    pair), drivable in one gig. Disjoint chains by a maximum matching."""
    ok = [r for r in REQ.values() if len(r["legs"]) == 1 and slow_option(r)
          and not r["legs"][0]["pickup"]["privateAddress"] and not r["legs"][0]["delivery"]["privateAddress"]]
    g = nx.Graph()
    for x in ok:
        for y in ok:
            if x is y or abs(x["arrivedAt"] - y["arrivedAt"]) > DAY:
                continue
            (b, c), (c2, a) = ends(x), ends(y)
            if geo.line_km(c, c2) <= 30 and NEAR[a] >= POOL and geo.line_km(b, a) > 30 and drivable([x, y]):
                w = (x["referenceFeeCents"] + y["referenceFeeCents"]) * (SOLO - OPEN["c"])
                if not g.has_edge(x["id"], y["id"]) or g.edges[x["id"], y["id"]]["w"] < w:
                    g.add_edge(x["id"], y["id"], w=w, c=[x["id"], y["id"]])
    return [g.edges[e]["c"] for e in nx.max_weight_matching(g, maxcardinality=True)]


# ── the desk ──────────────────────────────────────────────────────────────────────────────────────────────
class Desk:
    def __init__(self, arm, loops):
        self.arm, self.loops = arm, loops
        self.loop_of = {i: tuple(c) for c in loops for i in c}
        self.orders, self.lost, self.held = {}, set(), set()
        self.gigs, self.sent, self.booked, self.driver = {}, [], {}, {}
        self.search = {}
        self.ledger, self.log = [], Counter()
        self.last_view = {}                       # driver -> minute of their last view of any of our gigs
        self.offers = defaultdict(set)            # gig -> drivers offered
        self.open_offers = defaultdict(int)       # gig -> offers still open
        self.offers_today = Counter()             # (driver, day) -> offers sent
        self.offer_fee = {}
        self.ret_wait = {}                        # ret arms: first car of a pair -> the second car, held
        self.ret_offer = []                       # ret arms: (oid, driver) to offer once the post has a gig id

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
        if (self.arm in SD or (self.arm in WEEK and r["id"] in SAME_DAY)) and r["id"] in self.loop_of:
            o = next(x for x in r["options"] if x["kind"] == "same_day")
        if o:
            lim = LIMIT.get((r["id"], o["kind"]))
            price = int(QUOTE * lim) if lim else o["listPriceCents"]
            return {"type": "quote", "requestId": r["id"], "prices": {o["kind"]: price}}
        return {"type": "quote", "requestId": r["id"], "prices": {x["kind"]: 4 * x["listPriceCents"] for x in r["options"]}}

    def gig_of(self, oid):
        return next((g for g, x in self.gigs.items() if oid in x["oids"]), None)

    def won(self, oid, now):
        if self.arm in THIN:
            return [self.post([oid], THIN[self.arm], "thin", now)]
        if self.arm in SD or (self.arm in WEEK and oid in SAME_DAY):
            return [self.post([oid], SD.get(self.arm, 0.75), "sd", now)]
        if self.arm in WEEK and len(self.loop_of[oid]) == 1:
            return [self.post([oid], SOLO, "solo", now)]
        if self.arm in ("off0", "offa", "offu"):
            return [self.post([oid], OFF_OPEN, "offsolo", now)]
        if self.arm in RET:
            loop = self.loop_of[oid]
            self.held.add(oid)
            if any(i in self.lost for i in loop):
                return [self.post([oid], SOLO, "broken", now)]
            if all(i in self.held for i in loop):          # first car out now, the second waits for its delivery
                self.ret_wait[loop[0]] = loop[1]
                return [self.post([loop[0]], SOLO, "first", now)]
            return []
        if self.arm.startswith("solo") or self.arm in ("teach", "flat"):
            if self.arm == "teach" and now < DAY:
                self.search[oid] = {"lo": LO, "hi": HI, "m": HI, "steps": 0}
                return [self.post([oid], HI, "search", now)]
            return [self.post([oid], self.fee_mult(now), "solo", now)]
        loop = self.loop_of[oid]
        self.held.add(oid)
        if any(i in self.lost for i in loop):
            return [self.post([oid], SOLO, "broken", now)]
        if all(i in self.held for i in loop):
            if self.arm in ("chain", "rest"):
                return [self.post(list(loop), OPEN["c"], "chain", now)]
            return [self.post(list(loop), OPEN[len(loop)], "home" if len(loop) == 1 else f"loop{len(loop)}", now)]
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
            elif k == "delivered" and e["orderId"] in self.ret_wait:
                b = self.ret_wait.pop(e["orderId"])
                drv = self.driver.get(e["gigId"])
                if b in self.held and b in self.orders:
                    out.append(self.post([b], SOLO, "second", now))
                    if drv:
                        self.ret_offer.append((b, drv))
                        self.log["ret_delivered_in_time"] += 1
            elif k == "ledger":
                self.ledger.append(e["line"])
            elif k == "gig_viewed":
                self.last_view[e["driverId"]] = now
            elif k == "offer_answered":
                g = e["gigId"]
                self.open_offers[g] = max(0, self.open_offers[g] - 1)
                self.log["offer_" + e["answer"]] += 1
                if e["answer"] == "accepted" and g in self.gigs:
                    fee = self.offer_fee.get((g, e["driverId"]), 0)
                    self.booked[g] = fee
                    self.gigs[g]["steps"].append([now, fee, "booked"])
                    self.gigs[g]["by_offer"] = True
        out += self.offer_rounds(now)
        for g, x in list(self.gigs.items()):
            if g in self.booked:
                continue
            last = x["steps"][-1][0]
            if self.arm in ("week1", "week10") and x["kind"] in LADDER:
                rung = x.get("rung", 0)
                if rung < len(LADDER[x["kind"]]) and now - x["at"] >= LADDER[x["kind"]][rung][0]:
                    x["rung"] = rung + 1
                    m = LADDER[x["kind"]][rung][1]
                    out.append(self.reprice(g, int(m * sum(REQ[o]["referenceFeeCents"] for o in x["oids"])), now, "bump"))
                continue
            wait = SD_BUMP if x["kind"] == "sd" else BUMP
            if (x["kind"].startswith("loop") or x["kind"] in ("home", "chain", "offsolo", "thin", "sd")) and not x.get("bumped") and now - x["at"] >= wait:
                x["bumped"] = True
                up = RESCUE if x["kind"] in ("thin", "sd") else SOLO
                out.append(self.reprice(g, int(up * sum(REQ[o]["referenceFeeCents"] for o in x["oids"])), now, "bump"))
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

    def offer_rounds(self, now):
        """Ride home: while a homeward gig is unbooked and not yet raised, keep 3 offers open to drivers who live within
        30 km of its delivery, recent viewers first; each driver at most 3 offers a day, never twice for one gig."""
        out = []
        if now % DAY < 7 * HOUR or now % DAY >= 23 * HOUR:       # nobody reads an offer at night
            return out
        for g, x in self.gigs.items():
            if x["kind"] == "offsolo":
                if self.arm in ("offa", "offu") and g not in self.booked and not x.get("bumped") \
                        and all(o in self.orders for o in x["oids"]):
                    out += self.offers_near_pickup(g, x, now)
                continue
            if x["kind"] not in ("home", "chain") or self.arm == "rest" or g in self.booked or x.get("bumped") \
                    or not all(o in self.orders for o in x["oids"]):     # a cancelled order: leave it
                continue
            last = x["oids"][-1]                  # the car that ends at the driver's home
            d = self.orders[last]["legs"][0]["delivery"]["placeId"]
            premium = any(self.orders[o]["legs"][0]["car"]["premium"] for o in x["oids"])
            manual = any(note_flags(REQ[o]["note"], v2=True).manual for o in x["oids"])
            cands = [v for v in ROSTER.values() if geo.line_km(v["homePlaceId"], d) <= 30 and v["id"] not in self.offers[g]
                     and self.offers_today[(v["id"], now // DAY)] < 3
                     and (not premium or (v["rating"] >= 4.8 and v["completedGigs"] >= 50))
                     and (not manual or v["licence"] == "manual")]
            cands.sort(key=lambda v: (-self.last_view.get(v["id"], -10 ** 6), v["id"]))
            fee = x["fee"] if x["kind"] == "chain" else int(HOME_OFFER * REQ[x["oids"][0]]["referenceFeeCents"])
            # a chain's offer is its app fee: an aimed notification to the drivers it takes home
            for v in cands[:max(0, 3 - self.open_offers[g])]:
                out.append({"type": "offer", "gigId": g, "driverId": v["id"], "feeCents": fee})
                self.offers[g].add(v["id"])
                self.open_offers[g] += 1
                self.offers_today[(v["id"], now // DAY)] += 1
                self.offer_fee[(g, v["id"])] = fee
                self.log["offer_sent"] += 1
                self.log["offer_to_recent_viewer"] += int(now - self.last_view.get(v["id"], -10 ** 6) <= 3 * HOUR)
        return out

    def offers_near_pickup(self, g, x, now):
        """Offers arms: keep 3 offers open at the gig's own fee to drivers living within 30 km of its pickup. offa: drivers
        who viewed one of our gigs in the last 6 h first (most recent first), then the rest; offu: a fixed random order."""
        o = self.orders[x["oids"][0]]
        p = o["legs"][0]["pickup"]["placeId"]
        premium = o["legs"][0]["car"]["premium"]
        manual = note_flags(REQ[o["id"]]["note"], v2=True).manual
        cands = [v for v in ROSTER.values() if geo.line_km(v["homePlaceId"], p) <= 30 and v["id"] not in self.offers[g]
                 and self.offers_today[(v["id"], now // DAY)] < 3
                 and (not premium or (v["rating"] >= 4.8 and v["completedGigs"] >= 50))
                 and (not manual or v["licence"] == "manual")]
        shuffle = lambda v: sum(map(ord, v["id"] + g)) * 7919 % 997  # noqa: E731  (fixed, not Python's salted hash)
        if self.arm == "offa":
            recent = lambda v: now - self.last_view.get(v["id"], -10 ** 6) <= 6 * HOUR  # noqa: E731
            cands.sort(key=lambda v: (0, -self.last_view[v["id"]]) if recent(v) else (1, shuffle(v)))
        else:
            cands.sort(key=shuffle)
        out = []
        for v in cands[:max(0, 3 - self.open_offers[g])]:
            out.append({"type": "offer", "gigId": g, "driverId": v["id"], "feeCents": x["fee"]})
            self.offers[g].add(v["id"])
            self.open_offers[g] += 1
            self.offers_today[(v["id"], now // DAY)] += 1
            self.offer_fee[(g, v["id"])] = x["fee"]
            self.log["offer_sent"] += 1
            self.log["offer_to_recent_viewer"] += int(now - self.last_view.get(v["id"], -10 ** 6) <= 6 * HOUR)
        return out

    def ret_offers(self, now):
        """ret arms: the second car's gig now has an id; offer it to the driver who just delivered the first."""
        out = []
        for b, drv in self.ret_offer:
            g = self.gig_of(b)
            if g and g not in self.booked:
                fee = int(RET[self.arm] * REQ[b]["referenceFeeCents"])
                out.append({"type": "offer", "gigId": g, "driverId": drv, "feeCents": fee})
                self.offer_fee[(g, drv)] = fee
                self.open_offers[g] += 1
                self.log["offer_sent"] += 1
                self.log["offer_sent_night"] += int(now % DAY < 7 * HOUR or now % DAY >= 23 * HOUR)
        self.ret_offer = []
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
         "gig_expired", "gig_dropped", "no_show", "visit_failed", "offer_answered"]
SELECT = {}
GROUP = {"week": "w", "week0": "w0", "week1": "w", "week10": "w0", "sd75": "s", "sd100": "s", "rest": "r", "solo7": "r", "thin10": "t", "thin12": "t", "ret6": "2", "ret9": "2", "off0": "4", "offa": "4", "offu": "4", "loops": "4", "solo": "4", "pairs": "2", "solo2": "2", "teach": "4", "flat": "4", "tri": "3", "solo3": "3",
         "home": "2h", "solo4": "2h", "homeonly": "h", "solo5": "h", "chain": "c", "solo6": "c"}


def chains_rest(max_road=480):
    """His idea (Sun ~01:30): after the closed pairs and triangles, link what is left two at a time, back to back (y's
    pickup within 30 km of x's delivery), wherever they end; one gig, under max_road road minutes, deadlines with SPARE."""
    taken = {i for c in selection("tri")[0] for i in c}
    ok = [r for r in REQ.values() if r["id"] not in taken and len(r["legs"]) == 1 and slow_option(r)
          and not r["legs"][0]["pickup"]["privateAddress"] and not r["legs"][0]["delivery"]["privateAddress"]]
    road = lambda x, y: geo.minutes(*ends(x)) + geo.minutes(ends(x)[1], ends(y)[0]) + geo.minutes(*ends(y))  # noqa: E731
    g = nx.Graph()
    for x in ok:
        for y in ok:
            if x is y or abs(x["arrivedAt"] - y["arrivedAt"]) > DAY or geo.line_km(ends(x)[1], ends(y)[0]) > 30:
                continue
            if road(x, y) <= max_road and drivable([x, y]):
                w = (x["referenceFeeCents"] + y["referenceFeeCents"]) * (SOLO - OPEN["c"])
                if not g.has_edge(x["id"], y["id"]) or g.edges[x["id"], y["id"]]["w"] < w:
                    g.add_edge(x["id"], y["id"], w=w, c=[x["id"], y["id"]])
    return [g.edges[e]["c"] for e in nx.max_weight_matching(g, maxcardinality=True)]


def same_day_in():
    """same_day cars from a town with fewer than 50 drivers near the pickup (v7 declines same_day there) into a pool
    (40+ drivers near the delivery), at most 2 h of driving: a capital driver trains out and drives home the same day."""
    out = []
    for r in REQ.values():
        if len(r["legs"]) != 1 or not any(o["kind"] == "same_day" for o in r["options"]):
            continue
        leg = r["legs"][0]
        if leg["pickup"]["privateAddress"] or leg["delivery"]["privateAddress"]:
            continue
        p, d = ends(r)
        if NEAR[p] < 50 and NEAR[d] >= POOL and geo.minutes(p, d) <= 120 and (r["id"], "same_day") in LIMIT:
            out.append([r["id"]])
    return out


def thin_singles():
    """One-car slow-option requests whose pickup has fewer than THIN_MAX drivers within 30 km: the cars v7 declines."""
    return [[r["id"]] for r in REQ.values() if len(r["legs"]) == 1 and slow_option(r)
            and not r["legs"][0]["pickup"]["privateAddress"] and NEAR[ends(r)[0]] < THIN_MAX]


SAME_DAY = set()
WEEK = ("week", "week0", "week1", "week10")
LADDER = {"solo": [(120, 1.15), (240, 1.4)], "sd": [(60, 1.0), (120, 1.4)],
          "loop2": [(120, 0.9), (240, 1.15)], "loop3": [(120, 0.9), (240, 1.15)]}   # week1/week10: raise as time passes


def week():
    """The oracle week: closed pairs and triangles first (week0: none), then same_day into pools, then every other
    one-car request whose slow option clears WEEK_MIN_MARGIN at QUOTE x its limit and a driver at SOLO x typical, from a
    pickup v7 would serve (22+ drivers near)."""
    loops = selection("tri")[0]
    taken = {i for c in loops for i in c}
    sd = [c for c in same_day_in() if c[0] not in taken]
    SAME_DAY.update(c[0] for c in sd)
    taken |= SAME_DAY
    singles = []
    for r in REQ.values():
        o = slow_option(r)
        if r["id"] in taken or len(r["legs"]) != 1 or not o or NEAR[ends(r)[0]] < THIN_MAX:
            continue
        lim = LIMIT.get((r["id"], o["kind"]))
        if lim and QUOTE * lim - SOLO * r["referenceFeeCents"] >= WEEK_MIN_MARGIN:
            singles.append([r["id"]])
    return loops + sd + singles


def selection(arm):
    """The loops an arm aims at: '4', '3', '2' = closed loops up to that size; '2h' = pairs, then the homeward
    singles not in a pair; 'h' = homeward singles only."""
    key = GROUP[arm]
    if key not in SELECT:
        if key in ("2", "3", "4"):
            SELECT[key] = find_loops(int(key))
        elif key == "2h":
            pairs, cands, n = selection("pairs")
            SELECT[key] = (pairs + homeward({i for c in pairs for i in c}), cands, n)
        elif key == "w":
            SELECT[key] = (week(), 0, 0)
        elif key == "w0":
            SELECT[key] = ([[i] for c in selection("week")[0] for i in c], 0, 0)
        elif key == "s":
            SELECT[key] = (same_day_in(), 0, 0)
        elif key == "r":
            SELECT[key] = (chains_rest(), 0, 0)
        elif key == "t":
            SELECT[key] = (thin_singles(), 0, 0)
        elif key == "c":
            SELECT[key] = (chains_home(), 0, 0)
        else:
            SELECT[key] = (homeward(set()), 0, 0)
    return SELECT[key]


def play(arm):
    loops, cands, nfound = selection(arm)
    desk = Desk(arm, loops)
    desk.done = []
    with world(SEED, what=f"loops1-{arm}") as w:
        pending = []
        if arm not in RET:
            desk.ret_offer = None
        while w.now < w.ends_at:
            offers = GROUP[arm] in ("2h", "h", "c") or arm in ("offa", "offu")
            tick = 10 if offers else 30          # offers last 10 minutes
            until = KINDS + ["delivered"] if arm in RET else KINDS
            results, events = w.advance(until=until, max=min(w.ends_at, w.now + tick), actions=pending)
            desk.took(pending, results)
            if desk.ret_offer is not None and any(e["kind"] == "delivered" for e in events) and arm in RET:
                pending = desk.step(events, w.now)
                desk.took(pending, w.act(pending))     # post the second car now, then offer it in the same minute
                pending = desk.ret_offers(w.now)
                continue
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
    off = {k: v for k, v in o["log"].items() if k.startswith("offer")}
    if off:
        say(f"        offers: {off}; gigs booked by an offer: {sum(1 for x in o['gigs'] if x.get('by_offer'))}")
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
    for key in sorted({GROUP[a] for a in ARMS}):
        loops, cands, nfound = selection(next(a for a in ARMS if GROUP[a] == key))
        say(f"{SEED}, selection {key}: {nfound} closed loops among {cands} requests; chosen {len(loops)}: "
            f"{dict(Counter(len(c) for c in loops))} = {sum(len(c) for c in loops)} cars")
    with ThreadPoolExecutor(len(ARMS)) as ex:
        for o in ex.map(play, ARMS):
            report(o)
