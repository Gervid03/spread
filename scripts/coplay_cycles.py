"""Cycles for co-play: closed multi-car tours (Sat 14 Nov, the laptop lead).

A closed tour is 2-4 won cars in one gig: each car's delivery near the next car's pickup, and the last delivery back
near the first pickup, so a driver who lives at the start ends at home. tas-routes measured on forks that such tours
book at 0.31-0.43x the summed typical fee, against ~0.8x for single cars (most of a single car's fee is the trip home).

co-play uses this module for:
  - the "Cycles" section of the state: every closed tour among the won cars that no driver holds yet, with each
    rotation that is postable now (its start town and the drivers there), and waiting quotes that would close one;
  - the "tour" move: post a tour as one flat multi-car gig (the tour desk then steps it up and splits it as usual);
  - the "tourprobe" move: the lowest flat fee a driver books the tour at within N minutes, bisected on forks. Every
    fork is logged to ~/.spread-lab/coplay/tour-fees.jsonl: the driver-price data for multi-car gigs.
"""
from __future__ import annotations

import json
import time

from spread.client import SpreadError

from spread_lab.env import lab_home
from spread_lab.lab import Slot
from spread_lab.notes import note_flags
from spread_lab.policy import Retry, stops_for, undelivered, without_windows
from spread_lab.runner import clock

TOUR_KM = 30.0   # the next pickup within this straight-line distance of the last delivery; home within it too


def available_orders(desk) -> list[str]:
    """Won one-car orders with no driver yet: not delivered, not urgent or lost, no booked gig holding them."""
    held = {s["orderId"] for gid in desk.booked for s in desk.posts.get(gid, {}).get("stops", [])}
    out = []
    for oid, o in desk.orders.items():
        if len(o["legs"]) != 1 or undelivered(o) != [0] or oid in desk.urgent or oid in desk.lost or oid in held:
            continue
        out.append(oid)
    return out


def ends(desk, x):
    r = desk.orders.get(x) or desk.requests[x]
    return r["legs"][0]["pickup"]["placeId"], r["legs"][0]["delivery"]["placeId"]


def find_cycles(desk, ids: list[str], max_len: int = 4) -> list[list[str]]:
    """Closed tours: each car's delivery within TOUR_KM of the next car's pickup, the last back near the first."""
    P = {x: ends(desk, x)[0] for x in ids}
    D = {x: ends(desk, x)[1] for x in ids}

    def near(a, b):
        return a == b or desk.geo.line_km(a, b) <= TOUR_KM

    nxt = {a: [b for b in ids if b != a and near(D[a], P[b])] for a in ids}
    pos = {x: i for i, x in enumerate(ids)}
    out: list[list[str]] = []

    def dfs(start, path):
        if len(path) >= 2 and near(D[path[-1]], P[start]):
            out.append(list(path))
        if len(path) < max_len:
            for b in nxt[path[-1]]:
                if pos[b] > pos[start] and b not in path:
                    dfs(start, path + [b])

    for s in ids:
        dfs(s, [s])
    return out


def cycles_text(desk, names, limit: int = 14) -> list[str]:
    av = available_orders(desk)
    waiting = [a["requestId"] for a in desk.outbox if a["type"] == "quote" and len(desk.requests[a["requestId"]]["legs"]) == 1]
    rows = []
    for c in find_cycles(desk, av + waiting):
        reqs = [x for x in c if x not in desk.orders]
        if len(reqs) > 1:
            continue
        ref = sum(desk.requests[x]["referenceFeeCents"] for x in c)
        feas = []
        if not reqs and hasattr(desk, "can_chain_orders_live"):
            for i in range(len(c)):
                rot = c[i:] + c[:i]
                info = desk.can_chain_orders_live(rot)
                if info:
                    feas.append((rot[0], info["road_min"]))
        rows.append((bool(feas) or bool(reqs), len(c), ref, c, reqs, feas))
    rows.sort(key=lambda r: (not r[0], -r[1], -r[2]))
    n_feas = sum(1 for r in rows if r[5])
    town = lambda x: names.get(ends(desk, x)[0], ends(desk, x)[0])
    out = [f"\n## Cycles ({len(av)} won cars without a driver; {len(rows)} closed tours of 2-4 cars, {n_feas} postable now): "
           "cars · sum of typical fees · towns · each postable rotation: start town[drivers] road hours · ids"]
    for ok, n, ref, c, reqs, feas in rows[:limit]:
        towns = "→".join(town(x) for x in c) + "→"
        if feas:
            how = ", ".join(f"{town(s)}[{desk.supply.get(ends(desk, s)[0], 0)}] {rm / 60:.1f}h" for s, rm in feas)
        elif reqs:
            r = reqs[0]
            q = next(a for a in desk.outbox if a["type"] == "quote" and a["requestId"] == r)
            lst = {o["kind"]: o["listPriceCents"] for o in desk.requests[r]["options"]}
            qs = " ".join(f"{k[:2]}x{v / lst[k]:.2f}" for k, v in q["prices"].items() if k in lst)
            how = f"IF WON: waiting quote {r[:6]} ({desk.decided.get(r, '?')} {qs})"
        else:
            how = "not postable now (windows, 12 h or a note)"
        out.append(f"- {n}car €{ref / 100:.0f} · {towns} · {how} · {' '.join(x[:6] for x in c)}")
    tours = getattr(desk, "tour_gigs", None)
    if tours:
        out.append(f"Tour gigs so far: {len(tours)} posted, {sum(1 for gid in tours if gid in desk.booked)} booked.")
    return out


def resolve(desk, prefixes: list[str]) -> list[str]:
    ids = []
    for p in prefixes:
        m = [o for o in desk.orders if o.startswith(p)]
        if len(m) != 1:
            raise SystemExit(f"order prefix {p!r}: {len(m)} won orders match")
        ids.append(m[0])
    return ids


def tour_actions(desk, oids: list[str], mult: float):
    """The withdraws of the cars' open gigs and one flat multi-car post at mult x the summed typical fee, without
    changing the desk. Returns (withdraws, post) or (None, reason)."""
    withdraws = []
    for gid, post in desk.posts.items():
        if gid in desk.booked:
            continue
        held = {s["orderId"] for s in post["stops"]}
        if held & set(oids):
            if held - set(oids):
                return None, f"open gig {gid[:6]} also holds {sorted(x[:6] for x in held - set(oids))}"
            withdraws.append({"type": "withdraw", "gigId": gid})
    stops, exp, man = [], False, False
    for oid in oids:
        o, req = desk.orders[oid], desk.requests[oid]
        flags = note_flags(req["note"], v2=True)
        exp = exp or any(leg["car"]["premium"] for leg in o["legs"])
        man = man or flags.manual
        stops += without_windows(stops_for(o, [0], req["note"], Retry(plates=flags.plates), desk.geo, desk.p.charge_min_km, True,
                                           req["arrivedAt"]), desk.now)
    ref = sum(desk.requests[x]["referenceFeeCents"] for x in oids)
    return withdraws, {"type": "post", "stops": stops, "audience": {"experienced": exp, "manualLicence": man},
                       "schedule": [{"at": desk.now, "feeCents": max(100, int(ref * mult + 0.5))}]}


def apply_tour(desk, prefixes: list[str], mult: float) -> str:
    if not hasattr(desk, "post_tour_orders"):
        raise SystemExit("tour needs a tour desk: new ... --policy spread_lab.policies.sunday_tours:Desk")
    oids = resolve(desk, prefixes)
    label = " ".join(x[:6] for x in oids)
    if desk.can_chain_orders_live(oids) is None:
        return f"tour {label}: not postable now (windows, 12 h of driving, or a note)"
    w, post = tour_actions(desk, oids, mult)
    if w is None:
        return f"tour {label}: {post}"
    desk.outbox[:] = [a for a in desk.outbox if not (a["type"] == "post" and {s["orderId"] for s in a["stops"]} & set(oids))]
    for a in w:
        desk.outbox.append(a)
        for s in desk.posts.get(a["gigId"], {}).get("stops", []):
            desk.leg_gigs.get(s["orderId"], {}).pop(s["leg"], None)
    for oid in oids:
        getattr(desk, "staged_orders", {}).pop(oid, None)
    desk.tour_open_mult = lambda *a, **k: mult
    try:
        ok = desk.post_tour_orders(oids, tid="manual")
    finally:
        del desk.tour_open_mult
    desk.stats["manual_tours"] += 1
    return f"tour {label} at {mult:.2f}x the summed typical fee: {'posted' if ok else 'refused by the desk'}"


def tour_probe(g, prefixes: list[str], lo: float, hi: float, within: int, iters: int = 5) -> dict:
    """The lowest flat multiple of the summed typical fee at which a driver books the tour within `within` minutes,
    searched on forks. Every fork is logged to coplay/tour-fees.jsonl."""
    desk = g.desk
    oids = resolve(desk, prefixes)
    info = desk.can_chain_orders_live(oids) if hasattr(desk, "can_chain_orders_live") else None
    w, post0 = tour_actions(desk, oids, lo)
    if w is None:
        return {"error": post0}
    base = [dict(a) for a in desk.outbox if not (a["type"] == "post" and {s["orderId"] for s in a["stops"]} & set(oids))]
    ref = sum(desk.requests[x]["referenceFeeCents"] for x in oids)
    p0, _ = ends(desk, oids[0])
    _, dk = ends(desk, oids[-1])
    meta = {"game": g.log["game"], "seed": g.log["seed"], "now": desk.now, "clock": clock(desk.now), "orders": oids,
            "cars": len(oids), "towns": [g.names.get(ends(desk, x)[0], "?") for x in oids], "ref_eur": ref / 100,
            "road_min": info["road_min"] if info else None, "closed": desk.geo.line_km(dk, p0) <= TOUR_KM,
            "start_supply": desk.supply.get(p0, 0), "within_min": within, "options": [desk.orders[x]["option"] for x in oids]}
    path = lab_home() / "coplay" / "tour-fees.jsonl"

    def booked(m):
        with Slot():
            fw = None
            for _ in range(120):
                try:
                    fw = g.world.fork()
                    break
                except SpreadError as error:
                    if error.status != 409:
                        raise
                    time.sleep(5)
            try:
                post = dict(post0)
                post["schedule"] = [{"at": desk.now, "feeCents": max(100, int(ref * m + 0.5))}]
                acts = base + w + [post]
                res = fw.advance(to=min(g.ends_at, desk.now + within), actions=acts)
                r = res["results"][len(acts) - 1] if len(res["results"]) >= len(acts) else {}
                gid = r.get("id") if r.get("ok") is True else None
                hit = None
                if gid:
                    hit = next((e["at"] - desk.now for e in res["events"] if e["kind"] == "gig_booked" and e.get("gigId") == gid), None)
                with open(path, "a", encoding="utf-8") as f:
                    f.write(json.dumps({**meta, "mult": round(m, 4), "fee_eur": round(ref * m / 100, 2), "posted": bool(gid),
                                        "booked_after_min": hit}) + "\n")
                if not gid:
                    raise SystemExit(f"the tour post was refused: {r}")
                return hit
            finally:
                try:
                    fw.delete()
                except Exception:
                    pass

    if booked(hi) is None:
        return {**meta, "min_mult": f"> {hi}"}
    if booked(lo) is not None:
        return {**meta, "min_mult": f"<= {lo}"}
    for _ in range(iters):
        mid = (lo + hi) / 2
        lo, hi = (lo, mid) if booked(mid) is not None else (mid, hi)
    per_h = ref * hi / 100 / (meta["road_min"] / 60) if meta["road_min"] else None
    return {**meta, "min_mult": round(hi, 3), "fee_eur": round(ref * hi / 100, 2),
            "eur_per_road_h": round(per_h, 2) if per_h else None}
