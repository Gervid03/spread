"""Experiment 2: how deep is the evening market for closed tours? (dev-12)

Wins every one-car dealer-site request of a day on its slowest option (a throwaway price) and posts nothing. At T
(default Mon 18:20, after the last answer) it packs the cars into closed tours of 2-4 cars (each delivery within
30 km of the next pickup, the last delivery within 30 km of the first pickup, at most 690 road minutes, drivable the
next business day inside ready times, site hours and deadlines), each started from the town on it with most drivers.
Then, on forks, it posts ALL tours flat at f x the summed typical fee and plays to the next morning 09:30: how many
book, and hold, at each f? tas-routes measured 0.31-0.43x for single tours and 10 of 13 at 0.5x; this asks the same
of every car of a day at once.
Writes ~/.spread-lab/orc/<seed>/tours2-<T>.json.
"""
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from orc import DAY, clock, home, say, tape, world  # noqa: E402
from spread_lab.env import lab_home  # noqa: E402

SEED = sys.argv[1] if len(sys.argv) > 1 else "dev-12"
T = int(sys.argv[2]) if len(sys.argv) > 2 else 1100
MULTS = [float(x) for x in sys.argv[3].split(",")] if len(sys.argv) > 3 else [0.35, 0.45, 0.55, 0.7]
UNTIL = (T // DAY + 1) * DAY + 570          # the next morning 09:30
MAXROAD = 690

mp = json.loads((lab_home() / "map.json").read_text(encoding="utf-8"))
places = {p["id"]: p for p in mp["places"]}
road = {(r["from"], r["to"]): r["minutes"] for r in mp["roads"]}


def km(a, b):
    pa, pb = places[a], places[b]
    la1, lo1, la2, lo2 = map(math.radians, (pa["lat"], pa["lon"], pb["lat"], pb["lon"]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


tp = tape(SEED)
reqs = {r["id"]: r for r in tp["requests"]}
homes = Counter(d["homePlaceId"] for d in tp["roster"])
near = {p: sum(n for h, n in homes.items() if km(h, p) <= 30) for p in places}
n = [0]


def quote(request, now):
    legs = request["legs"]
    if len(legs) != 1 or legs[0]["pickup"]["privateAddress"] or legs[0]["delivery"]["privateAddress"]:
        return None
    n[0] += 1
    pick = request["options"][-1]
    return {pick["kind"]: max(100, int(pick["listPriceCents"] * 0.3))}


def open_at(hours, t):
    """The first minute >= t at which a site with these stated hours is open (None: never within a week)."""
    for _ in range(8):
        day, m = t // DAY, t % DAY
        wd = day % 7
        h = hours if wd in hours["weekdays"] else (hours.get("saturday") if wd == 5 else None)
        if h and "opens" in h:
            if m < h["opens"]:
                return day * DAY + h["opens"]
            if m < h["closes"]:
                return t
        t = (day + 1) * DAY
    return None


def simulate(cars, start):
    """Drives the tour from `start`; returns (end minute, road minutes) or None when a stop misses its window."""
    t, total = start, 0
    for i, c in enumerate(cars):
        if i:
            leg = road[(cars[i - 1]["D"], c["P"])]
            t += leg
            total += leg
        t = max(t, c["from"])
        t = open_at(c["phours"], t)
        if t is None or t > c["deadline"]:
            return None
        t += c["drive"]
        total += c["drive"]
        if open_at(c["dhours"], t) != t or t > c["deadline"]:
            return None
    return t, total


with world(SEED, what="tours2") as w:
    w.to(T, on_request=quote)
    say(f"{clock(w.now)}: {len(w.orders)} orders won of {n[0]} quoted")
    cars = {}
    for oid, od in w.orders.items():
        rq = reqs[oid]
        leg = rq["legs"][0]
        car = leg["car"]
        P, D = leg["pickup"]["placeId"], leg["delivery"]["placeId"]
        if car["premium"] or (car["electric"] and (car["chargePercent"] or 100) < 30):
            continue
        cars[oid] = {"id": oid, "P": P, "D": D, "ref": rq["referenceFeeCents"], "drive": road[(P, D)],
                     "from": od["legs"][0]["pickup"]["window"]["from"], "deadline": od["deadline"], "option": od["option"],
                     "phours": leg["pickup"]["hours"], "dhours": leg["delivery"]["hours"]}
    ids = sorted(cars)
    nxt = {a: [b for b in ids if b != a and km(cars[a]["D"], cars[b]["P"]) <= 30] for a in ids}
    day0 = (T // DAY + 1) * DAY

    def best_rotation(seq):
        best = None
        for r in range(len(seq)):
            rot = seq[r:] + seq[:r]
            cs = [cars[x] for x in rot]
            for start in (day0 + 420, day0 + 480, day0 + 540, day0 + 600, day0 + 660):
                sim = simulate(cs, start)
                if sim and sim[1] <= MAXROAD:
                    key = (near[cs[0]["P"]], -start)
                    if best is None or key > best[0]:
                        best = (key, rot, start, sim)
                    break
        return best

    cycles = []
    seen = set()
    for a in ids:
        for b in nxt[a]:
            if b < a:
                continue
            if a in nxt[b]:
                cycles.append((a, b))
            for c in nxt[b]:
                if c <= a or c == b:
                    continue
                if a in nxt[c]:
                    cycles.append((a, b, c))
                for d in nxt[c]:
                    if d <= a or d in (b, c):
                        continue
                    if a in nxt[d]:
                        cycles.append((a, b, c, d))
    say(f"{len(cars)} cars, {len(cycles)} closed cycles before timing")
    scored = []
    for cyc in cycles:
        key = tuple(sorted(cyc)), cyc
        if cyc in seen:
            continue
        seen.add(cyc)
        if sum(cars[x]["drive"] for x in cyc) > MAXROAD:
            continue
        br = best_rotation(list(cyc))
        if br:
            dead = br[3][1] - sum(cars[x]["drive"] for x in cyc)
            scored.append((len(cyc), -dead, near[cars[br[1][0]]["P"]], br))
    scored.sort(key=lambda s: (-s[0], -s[1], -s[2]))
    used, tours = set(), []
    for size, negdead, sup, br in scored:
        rot = br[1]
        if any(x in used for x in rot):
            continue
        used.update(rot)
        tours.append({"cars": rot, "start": br[2], "end": br[3][0], "road": br[3][1], "supply": sup,
                      "ref": sum(cars[x]["ref"] for x in rot), "towns": [cars[x]["P"] for x in rot]})
    say(f"{len(scored)} drivable cycles; packed {len(tours)} tours with {len(used)} of {len(cars)} cars:",
        dict(Counter(len(t["cars"]) for t in tours)), "start towns", Counter(t["towns"][0] for t in tours).most_common(8))
    out = {"seed": SEED, "T": T, "until": UNTIL, "cars": len(cars), "tours": tours, "runs": {}}

    def post(t, mult):
        stops = []
        for x in t["cars"]:
            stops += [{"orderId": x, "leg": 0, "kind": "pickup"}, {"orderId": x, "leg": 0, "kind": "delivery"}]
        return {"type": "post", "stops": stops, "audience": {"experienced": False, "manualLicence": False},
                "schedule": [{"at": w.now, "feeCents": max(1, int(mult * t["ref"]))}]}

    for mult in MULTS:
        with w.fork() as f:
            res = f.act([post(t, mult) for t in tours])
            gid = {r["id"]: i for i, r in enumerate(res) if r.get("ok")}
            bad = [r.get("reason") for r in res if not r.get("ok")]
            _, events = f.advance(to=UNTIL)
            state, when, views = {}, {}, Counter()
            for e in events:
                g = e.get("gigId")
                if g not in gid:
                    continue
                if e["kind"] == "gig_viewed":
                    views[gid[g]] += 1
                elif e["kind"] == "gig_booked":
                    state[gid[g]] = "booked"
                    when[gid[g]] = e["at"]
                elif e["kind"] in ("gig_dropped", "no_show"):
                    state[gid[g]] = "dropped"
                elif e["kind"] == "gig_started":
                    state[gid[g]] = "started"
                elif e["kind"] == "gig_expired":
                    state[gid[g]] = "expired"
            held = [i for i, s in state.items() if s in ("booked", "started")]
            by = defaultdict(lambda: [0, 0])
            for i, t in enumerate(tours):
                by[len(t["cars"])][1] += 1
                by[len(t["cars"])][0] += i in held
            hours = Counter((when[i] - T) // 60 for i in held)
            out["runs"][str(mult)] = {"refused": bad[:5], "posted": len(gid), "held": held, "when": {str(i): when[i] for i in held},
                                      "views": dict(views), "states": {str(i): s for i, s in state.items()}}
            say(f"x{mult}: posted {len(gid)} (refused {len(bad)}), held at {clock(UNTIL)}: {len(held)} tours = "
                f"{sum(len(tours[i]['cars']) for i in held)} cars; by size {dict((k, tuple(v)) for k, v in sorted(by.items()))}; "
                f"dropped {sum(s == 'dropped' for s in state.values())}; booked in hour after post {sorted(hours.items())}; "
                f"views/tour {sum(views.values()) / max(1, len(gid)):.1f}")
            if bad:
                say("  refusals:", Counter(str(b)[:70] for b in bad).most_common(3))
        (home(SEED) / f"tours2-{T}.json").write_text(json.dumps(out), encoding="utf-8")
    say("requests", w.client.requests)
