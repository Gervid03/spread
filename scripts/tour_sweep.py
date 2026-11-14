"""Driver prices for closed multi-car tours, swept over worlds (Sat 14 Nov, the user's ask: "get more info and find
correlations we can turn into profit").

Plays the champion's cycle desk on a world (with cycle-closing quotes on, so cycles form), and at each probe time
(every `--every` business hours, Mon-Thu) bisects on forks, for up to `--per` postable cycles among the won cars
without a driver, the lowest flat fee (x the summed typical fee) at which a driver books the cycle within `--within`
minutes. The main world is never touched by a probe. One JSON line per probed cycle, with its features, to
~/.spread-lab/coplay/tour-sweep.jsonl.

    uv run python scripts/tour_sweep.py --seed dev-03 [--every 3] [--per 3] [--within 90] [-s key=value ...]
"""
from __future__ import annotations

import argparse
import json
import sys
import time

sys.path.insert(0, "scripts")
from coplay_cycles import available_orders, ends, find_cycles, tour_actions  # noqa: E402
from spread.client import SpreadError  # noqa: E402
from spread_lab.env import lab_home, load_dotenv  # noqa: E402
from spread_lab.geo import Geo, load_map  # noqa: E402
from spread_lab.lab import CountingClient, Slot, champion, create_world, load_policy  # noqa: E402
from spread_lab.runner import DAY, HOUR, URGENT, busy, clock  # noqa: E402


def bisect(world, desk, oids, lo, hi, within, iters=5):
    w, post0 = tour_actions(desk, oids, lo)
    if w is None:
        return None, []
    base = [dict(a) for a in desk.outbox if not (a["type"] == "post" and {s["orderId"] for s in a["stops"]} & set(oids))]
    ref = sum(desk.requests[x]["referenceFeeCents"] for x in oids)
    trail = []

    def booked(m):
        with Slot():
            fw = None
            for _ in range(60):
                try:
                    fw = world.fork()
                    break
                except SpreadError as error:
                    if error.status != 409:
                        raise
                    time.sleep(5)
            try:
                post = dict(post0)
                post["schedule"] = [{"at": desk.now, "feeCents": max(100, int(ref * m + 0.5))}]
                acts = base + w + [post]
                res = fw.advance(to=desk.now + within, actions=acts)
                r = res["results"][len(acts) - 1] if len(res["results"]) >= len(acts) else {}
                gid = r.get("id") if r.get("ok") is True else None
                if not gid:
                    return "refused"
                views = sum(1 for e in res["events"] if e["kind"] == "gig_viewed" and e.get("gigId") == gid)
                hit = next((e["at"] - desk.now for e in res["events"] if e["kind"] == "gig_booked" and e.get("gigId") == gid), None)
                trail.append({"mult": round(m, 3), "booked_after": hit, "views": views})
                return hit
            finally:
                try:
                    fw.delete()
                except Exception:
                    pass

    top = booked(hi)
    if top == "refused":
        return None, trail
    if top is None:
        return f">{hi}", trail
    if booked(lo) is not None:
        return f"<={lo}", trail
    for _ in range(iters):
        mid = (lo + hi) / 2
        lo, hi = (lo, mid) if booked(mid) is not None else (mid, hi)
    return round(hi, 3), trail


def features(desk, names, oids):
    geo = desk.geo
    o = [desk.orders[x] for x in oids]
    legs = [x["legs"][0] for x in o]
    drive = sum(geo.minutes(l["pickup"]["placeId"], l["delivery"]["placeId"]) for l in legs)
    dead = sum(geo.minutes(legs[i]["delivery"]["placeId"], legs[i + 1]["pickup"]["placeId"]) for i in range(len(legs) - 1))
    p0, dk = legs[0]["pickup"]["placeId"], legs[-1]["delivery"]["placeId"]
    ref = sum(desk.requests[x]["referenceFeeCents"] for x in oids)
    lst = sum(x["priceCents"] for x in o)
    return {"cars": len(oids), "drive_min": drive, "deadhead_min": dead, "road_min": drive + dead,
            "close_km": round(geo.line_km(dk, p0), 1), "start": names.get(p0, p0), "start_supply": desk.supply.get(p0, 0),
            "min_supply": min(desk.supply.get(l["pickup"]["placeId"], 0) for l in legs),
            "towns": [names.get(l["pickup"]["placeId"], "?") for l in legs], "ref_eur": ref / 100, "price_eur": lst / 100,
            "day": desk.now // DAY, "hour": desk.now % DAY // 60, "lead_h": round((min(x["lastPickupAt"] for x in o) - desk.now) / 60, 1),
            "options": [x["option"] for x in o], "premium": any(l["car"]["premium"] for l in legs),
            "electric": sum(1 for l in legs if l["car"]["electric"]), "notes": sum(1 for x in oids if desk.requests[x].get("note"))}


def main():
    load_dotenv()
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", required=True)
    ap.add_argument("--every", type=float, default=3.0, help="business hours between probe times")
    ap.add_argument("--per", type=int, default=3, help="cycles probed per probe time")
    ap.add_argument("--within", type=int, default=90)
    ap.add_argument("--max-cars", type=int, default=5)
    ap.add_argument("-s", action="append", default=[])
    a = ap.parse_args()
    champ = champion()
    params = dict(champ["params"])
    params.update({"cyc_quote": True, "cyc_quote_mult": 1.05, "cyc_quote_cap_day": 60, "cyc_quote_floor": 0.70,
                   "cyc_max_cars": a.max_cars})
    for kv in a.s:
        k, v = kv.split("=", 1)
        params[k] = json.loads(v.lower()) if v.lower() in ("true", "false") else (float(v) if v.replace(".", "", 1).isdigit() else v)
    cls = load_policy(champ["policy"])
    client = CountingClient()
    m = load_map(client)
    geo = Geo(m)
    names = {p["id"]: p.get("name", p["id"])[:10] for p in m["places"]}
    out = lab_home() / "coplay" / "tour-sweep.jsonl"
    probed: set[frozenset] = set()
    slot = Slot().__enter__()          # the main world holds one slot for the whole week; each fork takes another
    world = create_world(client, 8, a.seed)
    try:
        snap = world.snapshot()
        ends_at = snap["endsAt"]
        desk = cls(world, cls.Params.from_dict(params), 8, geo, world.roster(), snap["now"])
        next_probe = 8 * 60 + 60 * a.every
        n = 0
        while desk.now < min(ends_at, 4 * DAY + 18 * HOUR):
            actions = desk.take_outbox()
            step_min = min(14, max(1, int(desk.p.step_min)))
            if busy(desk.now):
                step = world.advance(to=min(ends_at, desk.now + step_min), actions=actions)
            else:
                step = world.advance(until=URGENT, max=min(ends_at, desk.now + HOUR), actions=actions)
            desk.read_results(actions, step["results"])
            desk.now = step["now"]
            for e in step["events"]:
                desk.handle(e)
            desk.tick()
            if desk.now >= next_probe and busy(desk.now):
                next_probe = desk.now + 60 * a.every if desk.now % DAY < 15 * HOUR else (desk.now // DAY + 1) * DAY + 8 * 60 + 60 * a.every
                av = [x for x in available_orders(desk) if not any(x in {s["orderId"] for s in desk.posts[g]["stops"]} for g in desk.booked if g in desk.posts)]
                cands = []
                for c in find_cycles(desk, av, max_len=a.max_cars):
                    if frozenset(c) in probed:
                        continue
                    for i in range(len(c)):
                        rot = c[i:] + c[:i]
                        if desk.can_chain_orders_live(rot):
                            cands.append((-len(c), -desk.supply.get(ends(desk, rot[0])[0], 0), rot))
                            break
                cands.sort()
                for _, _, rot in cands[:a.per]:
                    probed.add(frozenset(rot))
                    m, trail = bisect(world, desk, rot, 0.20, 0.95, a.within)
                    row = {"seed": a.seed, "clock": clock(desk.now), "min_mult": m, **features(desk, names, rot), "trail": trail}
                    with open(out, "a", encoding="utf-8") as f:
                        f.write(json.dumps(row) + "\n")
                    n += 1
                    print(f"{clock(desk.now)} {row['cars']} cars {'-'.join(row['towns'])} road {row['road_min']}m supply {row['start_supply']}: min {m}", flush=True)
        print(f"done: {n} cycles probed", flush=True)
    finally:
        try:
            world.delete()
        except Exception:
            pass
        slot.__exit__(None, None, None)


if __name__ == "__main__":
    main()
