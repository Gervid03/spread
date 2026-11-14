"""Experiment pairs1: do chosen closed pairs book as one gig, at what fee, and arrive on time? (dev-12)

The question (Spread II lesson, Sat 14 Nov evening). About two thirds of a typical fee pays the driver's trip home,
so a car that closes a loop should cost ~0.3-0.45x the summed typical fees, against ~0.8x alone. Our oracle chose
cars first and toured them afterwards; its tours booked 63 of 102. Here the pairs are chosen first, from the week's
tape (a maximum matching of closed pairs), and only their requests are won.

One arm = one fresh world of the seed, played to the end by the ~100-line desk below:
  - quotes: a request in a chosen pair gets its slowest option at the list price (that wins most at level 8);
    every other request a decline (4 x list);
  - a won car waits for its partner. Both won: one 2-car gig, flat at MULT x the two typical fees. Partner lost,
    or the car's last pickup is under 6 h away: the car alone at SOLO x its typical fee;
  - rescue: deadline_close -> reprice to RESCUE x; expired / dropped / no-show / failed visit -> each car of that
    gig again alone at RESCUE x.
  The arm "solo" wins the same cars and posts every one alone at SOLO: the control.

    uv run --with networkx python experiments/orc/pairs1.py dev-12 0.45 0.6 solo [--spare H] [--bump MIN]
  --spare H: the hours a pair must leave before each deadline (default 1); --bump MIN: an unbooked pair is raised
  once, to SOLO x, after MIN minutes.
Writes ~/.spread-lab/orc/<seed>/pairs1[s<H>b<MIN>]-<arm>.json and prints one line per arm.
"""
import json
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import networkx as nx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from orc import DAY, clock, home, say, tape, world  # noqa: E402
from spread_lab.geo import Geo, load_map  # noqa: E402
from spread_lab.notes import note_flags  # noqa: E402
from spread_lab.policy import Retry, stops_for, without_windows  # noqa: E402

HOUR = 60
SEED = sys.argv[1]
ARGS = sys.argv[2:]
SPARE = HOUR * float(ARGS[ARGS.index("--spare") + 1]) if "--spare" in ARGS else HOUR   # spare time in a pair
BUMP = int(ARGS[ARGS.index("--bump") + 1]) if "--bump" in ARGS else 0    # minutes unbooked, then SOLO x
MINROAD = int(ARGS[ARGS.index("--minroad") + 1]) if "--minroad" in ARGS else 0   # each car's drive at least this
for flag in ("--spare", "--bump", "--minroad"):
    if flag in ARGS:
        del ARGS[ARGS.index(flag):ARGS.index(flag) + 2]
ARMS = ARGS or ["0.45", "0.6", "solo"]
TAG = (f"s{SPARE // HOUR:g}b{BUMP}" if (SPARE != HOUR or BUMP) else "") + (f"r{MINROAD}" if MINROAD else "")
SOLO, RESCUE = 0.9, 1.4
OFFER = (0.6, 0.8)          # split: the way back offered to the booked driver, at booking and when they set off
LO, HI, STEPS = 0.4, 1.4, 3  # bisect: the fee range searched, and how many halvings
geo = Geo(load_map(None))
tp = tape(SEED)
REQ = {r["id"]: r for r in tp["requests"]}


# ── the pairs, chosen from the tape before the week starts ────────────────────────────────────────────────
def slow_option(r):
    opts = [o for o in r["options"] if o["kind"] in ("next_day", "within_3_days")]
    return max(opts, key=lambda o: o["deadline"]) if opts else None


def fits(a, b):
    """a first, then b, in one gig: road minutes under 12 h, both deadlines met with an hour to spare."""
    la, lb = a["legs"][0], b["legs"][0]
    pa, da, pb, db = la["pickup"]["placeId"], la["delivery"]["placeId"], lb["pickup"]["placeId"], lb["delivery"]["placeId"]
    if geo.line_km(da, pb) > 30 or geo.line_km(db, pa) > 30:      # closed: b goes back to where a started
        return False
    if min(geo.minutes(pa, da), geo.minutes(pb, db)) < MINROAD:
        return False
    road = geo.minutes(pa, da) + geo.minutes(da, pb) + geo.minutes(pb, db)
    if road > 700:
        return False
    start = max(a["respondBy"] + HOUR, b["respondBy"] + HOUR, la["pickup"]["window"]["from"])
    if start % DAY > 20 * HOUR:
        start = start - start % DAY + DAY + 8 * HOUR
    start = max(start, start - start % DAY + 8 * HOUR)
    t1 = start + geo.minutes(pa, da)
    t2 = max(t1 + geo.minutes(da, pb), lb["pickup"]["window"]["from"]) + geo.minutes(pb, db)
    return t1 <= slow_option(a)["deadline"] - SPARE and t2 <= slow_option(b)["deadline"] - SPARE


def choose_pairs():
    ok = [r for r in tp["requests"] if len(r["legs"]) == 1 and slow_option(r)
          and not r["legs"][0]["pickup"]["privateAddress"] and not r["legs"][0]["delivery"]["privateAddress"]]
    g = nx.Graph()
    first = {}
    for a in ok:
        for b in ok:
            if a["id"] < b["id"] and abs(a["arrivedAt"] - b["arrivedAt"]) <= DAY:
                for x, y in ((a, b), (b, a)):
                    if fits(x, y):
                        g.add_edge(a["id"], b["id"])
                        first[frozenset((a["id"], b["id"]))] = x["id"]
                        break
    m = nx.max_weight_matching(g, maxcardinality=True)
    return {frozenset(p): first[frozenset(p)] for p in m}, len(ok)


PAIRS, CANDIDATES = choose_pairs()
PARTNER = {}
for p in PAIRS:
    a, b = sorted(p)
    PARTNER[a], PARTNER[b] = b, a


# ── the desk ──────────────────────────────────────────────────────────────────────────────────────────────
class Desk:
    def __init__(self, arm):
        self.arm = arm
        self.mult = None if arm in ("solo", "split", "bisect") else float(arm)
        self.orders, self.lost, self.held = {}, set(), set()
        self.driver = {}        # gig id -> the driver who booked it
        self.offered = {}       # split: (gig id, driver id) -> the fee offered
        self.search = {}        # bisect: order id -> {"lo", "hi", "m", "steps"}, the fee range still open (x typical)
        self.gigs = {}          # gig id -> {"oids", "kind", "fee"}
        self.sent = []          # the post actions of the last step, in order, to read the gig ids back
        self.booked, self.ledger, self.log = {}, [], Counter()

    def stops(self, oid, now, retry=Retry()):
        r = REQ[oid]
        flags = note_flags(r["note"], v2=True)
        retry = retry._replace(plates=retry.plates or flags.plates)
        return without_windows(stops_for(self.orders[oid], [0], r["note"], retry, geo, 200.0, True, r["arrivedAt"]), now), flags.manual

    def post(self, oids, mult, kind, now, retry=Retry()):
        stops, manual = [], retry.manual_licence
        for o in oids:
            s, man = self.stops(o, now, retry)
            stops += s
            manual = manual or man
        fee = max(100, int(mult * sum(REQ[o]["referenceFeeCents"] for o in oids)))
        premium = any(self.orders[o]["legs"][0]["car"]["premium"] for o in oids)
        self.sent.append({"oids": list(oids), "kind": kind, "fee": fee, "at": now})
        self.held -= set(oids)
        self.log[f"post_{kind}"] += 1
        return {"type": "post", "stops": stops, "audience": {"experienced": premium, "manualLicence": manual},
                "schedule": [{"at": now, "feeCents": fee}]}

    def quote(self, r):
        o = slow_option(r) if r["id"] in PARTNER else None
        if o:
            return {"type": "quote", "requestId": r["id"], "prices": {o["kind"]: o["listPriceCents"]}}
        return {"type": "quote", "requestId": r["id"], "prices": {x["kind"]: 4 * x["listPriceCents"] for x in r["options"]}}

    def offer_back(self, gig, mult):
        """split: the booked driver of one car of a pair gets a direct offer for the other car (their way back)."""
        o = self.gigs.get(gig, {}).get("oids", [None])[0]
        back = self.gig_of(PARTNER.get(o)) if o else None
        d = self.driver.get(gig)
        if not back or not d or back in self.booked or ((back, d) in self.offered and mult == OFFER[0]):
            return []
        fee = int(mult * REQ[PARTNER[o]]["referenceFeeCents"])
        self.offered[(back, d)] = fee
        self.log[f"offer_sent_{mult}"] += 1
        return [{"type": "offer", "gigId": back, "driverId": d, "feeCents": fee}]

    def halve_down(self, gig, now):
        """bisect: a driver took it -> the fee was high enough: release them and post the car again lower."""
        o = self.gigs[gig]["oids"][0]
        sr = self.search.get(o)
        if not sr or sr["steps"] >= STEPS or self.orders.get(o, {}).get("lastPickupAt", 0) - now <= 8 * HOUR:
            return []
        sr["hi"], sr["steps"] = sr["m"], sr["steps"] + 1
        sr["m"] = (sr["lo"] + sr["hi"]) / 2
        self.booked.pop(gig, None)
        self.gigs.pop(gig, None)
        self.log["bisect_release"] += 1
        return [{"type": "release", "gigId": gig}, self.post([o], sr["m"], "bisect", now)]

    def gig_of(self, oid):
        return next((g for g, x in self.gigs.items() if oid in x["oids"]), None)

    def step(self, events, now):
        out = []
        for e in events:
            k = e["kind"]
            if k == "price_request":
                out.append(self.quote(e["request"]))
            elif k == "order_won":
                oid = e["order"]["id"]
                self.orders[oid] = e["order"]
                mate = PARTNER.get(oid)
                if self.arm == "bisect":
                    self.search[oid] = {"lo": LO, "hi": HI, "m": HI, "steps": 0}
                    out.append(self.post([oid], HI, "bisect", now))
                elif self.mult is None:
                    out.append(self.post([oid], SOLO, self.arm, now))
                elif mate in self.held:
                    first = PAIRS[frozenset((oid, mate))]
                    out.append(self.post([first, mate if first == oid else oid], self.mult, "pair", now))
                elif mate in self.lost:
                    out.append(self.post([oid], SOLO, "alone", now))
                else:
                    self.held.add(oid)
            elif k == "order_lost":
                self.lost.add(e["requestId"])
                mate = PARTNER.get(e["requestId"])
                if mate in self.held:
                    out.append(self.post([mate], SOLO, "alone", now))
            elif k == "order_changed" and "order" in e:
                self.orders[e["order"]["id"]] = e["order"]
            elif k == "order_cancelled":
                self.orders.pop(e["orderId"], None)
                self.held.discard(e["orderId"])
            elif k == "gig_booked":
                self.booked[e["gigId"]] = e["feeCents"]
                self.driver[e["gigId"]] = e["driverId"]
                if self.arm == "split":
                    out += self.offer_back(e["gigId"], OFFER[0])
                elif self.arm == "bisect":
                    out += self.halve_down(e["gigId"], now)
            elif k == "gig_started" and self.arm == "split":
                out += self.offer_back(e["gigId"], OFFER[1])
            elif k == "offer_answered":
                self.log["offer_" + e["answer"]] += 1
                if e["answer"] == "accepted":
                    fee = self.offered.get((e["gigId"], e["driverId"]), 0)
                    self.booked[e["gigId"]] = fee
                    self.log["offer_fee_cents"] += fee
                    self.log["offer_ref_cents"] += REQ[self.gigs[e["gigId"]]["oids"][0]]["referenceFeeCents"] if e["gigId"] in self.gigs else 0
            elif k == "deadline_close":
                g = self.gig_of(e["orderId"])
                if g and g not in self.booked:
                    fee = int(RESCUE * sum(REQ[o]["referenceFeeCents"] for o in self.gigs[g]["oids"]))
                    if fee > self.gigs[g]["fee"]:
                        out.append({"type": "reprice", "gigId": g, "schedule": [{"at": now, "feeCents": fee}]})
                        self.gigs[g]["fee"] = fee
                        self.log["rescue_reprice"] += 1
            elif k in ("gig_expired", "gig_dropped", "no_show"):
                g = self.gigs.get(e["gigId"])
                self.booked.pop(e["gigId"], None)
                self.log[k] += 1
                if g and k == "gig_expired":
                    for o in g["oids"]:
                        if o in self.orders:
                            out.append(self.post([o], RESCUE, "rescue", now))
                    self.gigs.pop(e["gigId"])
            elif k == "visit_failed":
                self.log["visit_failed_" + e["reason"]] += 1
                if e["orderId"] in self.orders:
                    retry = Retry(pickup_from=now + HOUR, manual_licence=e["reason"] == "licence", plates=e["reason"] == "no_plates")
                    out.append(self.post([e["orderId"]], RESCUE, "rescue", now, retry))
            elif k == "ledger":
                self.ledger.append(e["line"])
        for g, x in self.gigs.items():     # a pair still unbooked after BUMP minutes: once, to SOLO x
            if BUMP and x["kind"] == "pair" and g not in self.booked and not x.get("bumped") and now - x["at"] >= BUMP:
                fee = int(SOLO * sum(REQ[o]["referenceFeeCents"] for o in x["oids"]))
                out.append({"type": "reprice", "gigId": g, "schedule": [{"at": now, "feeCents": fee}]})
                x.update(bumped=True, fee=fee)
                self.log["bump"] += 1
        for g, x in list(self.gigs.items()):   # bisect: unbooked for an hour -> the fee was too low: halve up
            o = x["oids"][0]
            sr = self.search.get(o)
            if sr and x["kind"] == "bisect" and g not in self.booked and sr["steps"] < STEPS and now - x["at"] >= 60                     and self.orders.get(o, {}).get("lastPickupAt", 0) - now > 8 * HOUR:
                sr["lo"], sr["steps"] = sr["m"], sr["steps"] + 1
                sr["m"] = (sr["lo"] + sr["hi"]) / 2
                fee = int(sr["m"] * REQ[o]["referenceFeeCents"])
                out.append({"type": "reprice", "gigId": g, "schedule": [{"at": now, "feeCents": fee}]})
                x.update(at=now, fee=fee)
                self.log["bisect_up"] += 1
        for oid in list(self.held):        # a held car whose partner hasn't come in time goes alone
            if self.orders.get(oid, {}).get("lastPickupAt", 0) - now < 6 * HOUR:
                out.append(self.post([oid], SOLO, "alone", now))
        return out

    def took(self, actions, results):
        posts = [a for a in actions if a["type"] == "post"]
        res = [r for a, r in zip(actions, results) if a["type"] == "post"]
        for meta, r in zip(self.sent, res):
            if r.get("ok"):
                self.gigs[r["id"]] = meta
            else:
                self.log["refused"] += 1
                self.log["refused: " + str(r.get("reason"))[:50]] += 1
        self.sent = []
        assert len(posts) == len(res)


KINDS = ["price_request", "order_won", "order_lost", "order_changed", "order_cancelled", "gig_booked", "deadline_close",
         "gig_expired", "gig_dropped", "no_show", "visit_failed", "offer_answered", "gig_started"]


def play(arm):
    desk = Desk(arm)
    with world(SEED, what=f"pairs1-{arm}") as w:
        pending = []
        while w.now < w.ends_at:
            nxt = w.ends_at if not (BUMP or arm == "bisect") else min(w.ends_at, w.now + 30)   # timers: look every 30 min
            results, events = w.advance(until=KINDS, max=nxt, actions=pending)
            desk.took(pending, results)
            pending = desk.step(events, w.now)
        score = w.score()
    late = {l["orderId"] for l in desk.ledger if l["kind"] in ("late_refund", "undelivered_penalty") and l.get("orderId")}
    fee_by_order = Counter()
    for l in desk.ledger:
        if l["kind"] == "driver_fee" and l.get("orderId"):
            fee_by_order[l["orderId"]] += -l["cents"]
    out = {"seed": SEED, "arm": arm, "pairs_chosen": len(PAIRS), "candidates": CANDIDATES, "score": score,
           "log": dict(desk.log), "gigs": {g: {**x, "booked": desk.booked.get(g)} for g, x in desk.gigs.items()},
           "late": sorted(late), "fee_by_order": fee_by_order}
    (home(SEED) / f"pairs1{TAG}-{arm}.json").write_text(json.dumps(out, default=list), encoding="utf-8")
    return out


def line(o):
    s, g = o["score"], o["gigs"].values()
    pairs = [x for x in g if x["kind"] == "pair"]
    booked = [x for x in pairs if x["booked"]]
    ref = lambda x: sum(REQ[i]["referenceFeeCents"] for i in x["oids"])  # noqa: E731
    paid = sum(x["booked"] for x in booked) / max(1, sum(ref(x) for x in booked))
    pair_cars = {i for x in pairs for i in x["oids"]}
    late_pair = len(pair_cars & set(o["late"]))
    fee_all = (s["revenueCents"] - s["marginCents"]) / 100   # fees + refunds + fines: a pair's fee line names no order
    return (f"{o['arm']:>5}: margin €{s['marginCents'] / 100:9,.2f}  won {s['wonOrders']:3d}  on time {100 * s['onTimeShare']:5.1f}%  "
            f"costs €{fee_all:8,.0f}  | pairs posted {len(pairs):3d}, booked as pairs {len(booked):3d} at {paid:.2f}x the typical fees, "
            f"pair cars late {late_pair}/{len(pair_cars)}  | {dict(o['log'])}")


if __name__ == "__main__":
    if ARMS[0] == "report":      # pairs1.py <seed> report <arm> ...: the saved results again, no worlds played
        for arm in ARMS[1:]:
            say(line(json.loads((home(SEED) / f"pairs1{TAG}-{arm}.json").read_text(encoding="utf-8"))))
        sys.exit()
    say(f"{SEED}: {CANDIDATES} one-car slow-option dealer requests; {len(PAIRS)} closed pairs chosen "
        f"({2 * len(PAIRS)} cars). Arms: {ARMS}")
    with ThreadPoolExecutor(len(ARMS)) as ex:
        for o in ex.map(play, ARMS):
            say(line(o))
