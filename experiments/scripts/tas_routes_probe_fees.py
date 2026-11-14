"""Step 2: Fork-bisect exact flat-fee booking costs of 1-, 2-, 3-, and 4-car tours on dev-12.

Usage:
  PYTHONPATH=. uv run python experiments/scripts/tas_routes_probe_fees.py --dry-run
  PYTHONPATH=. uv run python experiments/scripts/tas_routes_probe_fees.py
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from spread_lab.env import lab_home
from spread_lab.geo import Geo
from spread_lab.policy import Retry, stops_for, without_windows
from spread_lab.notes import note_flags
from tas import Tas, on_fork
from experiments.scripts.tas_routes_census import Arc, load_geo, load_tape, simulate_tour

HOUR, DAY = 60, 24 * 60


def build_monday_probe_set(geo: Geo, tape: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Builds:
      1) `probe_tours`: ~24 order-disjoint Monday tours across 1, 2, 3, 4 cars (closed & open, hub & regional)
      2) `depth_tours`: up to 20 order-disjoint Monday closed Vantaa/Capital tours to test driver pool depth.
    """
    reqs = [r for r in tape["requests"] if r["arrivedAt"] < DAY and len(r["legs"]) == 1]
    supply30 = geo.supply(tape["roster"], 30.0)

    # Prefer slowest option (within_3_days > next_day) so Tue morning booking has huge slack
    arcs: list[Arc] = []
    for r in reqs:
        opts = [Arc(r, o, geo) for o in r["options"] if o["kind"] != "same_day"]
        opts = [a for a in opts if not a.unsure and not a.private_pickup and not a.private_delivery]
        opts = [a for a in opts if a.deadline - max(1920, a.ready_at) - a.drive_min >= 180]
        if opts:
            opts.sort(key=lambda a: (a.deadline, a.list_cents), reverse=True)
            arcs.append(opts[0])

    by_p: dict[str, list[Arc]] = defaultdict(list)
    for a in arcs:
        by_p[a.pickup].append(a)

    used: set[str] = set()
    probe_tours: list[dict[str, Any]] = []

    def try_add(kind: str, cand_list: list[tuple[float, list[Arc], dict[str, Any]]], limit: int) -> None:
        cand_list.sort(key=lambda x: x[0], reverse=True)
        added = 0
        seen_lanes = set()
        for _, t_arcs, sim in cand_list:
            if added >= limit:
                break
            if any(x.rid in used for x in t_arcs):
                continue
            lane_sig = (t_arcs[0].pickup, t_arcs[0].delivery, len(t_arcs))
            if lane_sig in seen_lanes and limit <= 4:
                continue
            seen_lanes.add(lane_sig)
            used.update(x.rid for x in t_arcs)
            probe_tours.append({
                "kind": kind,
                "rids": [x.rid for x in t_arcs],
                "options": {x.rid: x.option for x in t_arcs},
                "route": " -> ".join(f"{x.pickup}->{x.delivery}" for x in t_arcs),
                "start_place": t_arcs[0].pickup,
                "end_place": t_arcs[-1].delivery,
                "supply30_start": supply30[t_arcs[0].pickup],
                "supply30_end": supply30[t_arcs[-1].delivery],
                "close_km": round(geo.line_km(t_arcs[-1].delivery, t_arcs[0].pickup), 1),
                "n_cars": len(t_arcs),
                "road_min": sim["road_min"],
                "deadhead_min": sim["deadhead_min"],
                "sum_ref_cents": sum(x.ref_cents for x in t_arcs),
                "sum_list_cents": sum(x.list_cents for x in t_arcs),
            })
            added += 1

    # Gather 4-car closed, 3-car closed, 2-car long closed (>=200m), 2-car short closed (<200m),
    # 2-car regional closed (non-capital start), 2-car open homeward, 2-car open outward, and 1-car solos
    c4, c3, c2_long, c2_short, c2_reg, c2_open_hub, c2_open_out = [], [], [], [], [], [], []
    for a in arcs:
        if supply30[a.pickup] < 15:
            continue
        is_cap = a.pickup in ("vantaa", "helsinki", "espoo")
        for pb in geo.places:
            if geo.line_km(a.delivery, pb) > 30.0:
                continue
            for b in by_p[pb]:
                if b.rid == a.rid:
                    continue
                sim2 = simulate_tour([a, b], geo, slack_min=120, start_buffer_min=45)
                if not sim2 or sim2["road_min"] > 660:
                    continue
                closes2 = geo.line_km(b.delivery, a.pickup) <= 30.0
                score2 = (a.ref_cents + b.ref_cents) - 40 * sim2["deadhead_min"]
                if closes2:
                    if not is_cap:
                        c2_reg.append((score2, [a, b], sim2))
                    elif sim2["road_min"] >= 200:
                        c2_long.append((score2, [a, b], sim2))
                    else:
                        c2_short.append((score2, [a, b], sim2))
                else:
                    if supply30[b.delivery] >= 90:
                        c2_open_hub.append((score2, [a, b], sim2))
                    elif supply30[b.delivery] <= 15 and is_cap:
                        c2_open_out.append((score2, [a, b], sim2))

                for pc in geo.places:
                    if geo.line_km(b.delivery, pc) > 30.0:
                        continue
                    for c in by_p[pc][:6]:
                        if c.rid in (a.rid, b.rid):
                            continue
                        sim3 = simulate_tour([a, b, c], geo, slack_min=120, start_buffer_min=45)
                        if not sim3 or sim3["road_min"] > 660:
                            continue
                        if geo.line_km(c.delivery, a.pickup) <= 30.0:
                            c3.append(((a.ref_cents + b.ref_cents + c.ref_cents) - 40 * sim3["deadhead_min"], [a, b, c], sim3))
                        for pd in geo.places:
                            if geo.line_km(c.delivery, pd) > 30.0:
                                continue
                            for d in by_p[pd][:4]:
                                if d.rid in (a.rid, b.rid, c.rid):
                                    continue
                                if geo.line_km(d.delivery, a.pickup) <= 30.0:
                                    sim4 = simulate_tour([a, b, c, d], geo, slack_min=120, start_buffer_min=45)
                                    if sim4 and sim4["road_min"] <= 660:
                                        c4.append(((a.ref_cents + b.ref_cents + c.ref_cents + d.ref_cents) - 40 * sim4["deadhead_min"], [a, b, c, d], sim4))

    try_add("4-closed", c4, 3)
    try_add("3-closed", c3, 4)
    try_add("2-closed-long", c2_long, 4)
    try_add("2-closed-short", c2_short, 3)
    try_add("2-closed-reg", c2_reg, 3)
    try_add("2-open-hub", c2_open_hub, 2)
    try_add("2-open-thin", c2_open_out, 2)

    # Also add 4 diverse 1-car solos (short cap, medium cap, long cap, regional Oulu/Turku)
    c1_short = [(a.ref_cents, [a], {"road_min": a.drive_min, "deadhead_min": 0}) for a in arcs if a.pickup == "vantaa" and 30 <= a.drive_min <= 65]
    c1_med = [(a.ref_cents, [a], {"road_min": a.drive_min, "deadhead_min": 0}) for a in arcs if a.pickup in ("vantaa", "helsinki") and 95 <= a.drive_min <= 180]
    c1_long = [(a.ref_cents, [a], {"road_min": a.drive_min, "deadhead_min": 0}) for a in arcs if a.pickup in ("vantaa", "helsinki") and 220 <= a.drive_min <= 400]
    c1_reg = [(a.ref_cents, [a], {"road_min": a.drive_min, "deadhead_min": 0}) for a in arcs if a.pickup in ("oulu", "turku", "tampere") and 80 <= a.drive_min <= 260]
    try_add("1-solo-short", c1_short, 1)
    try_add("1-solo-med", c1_med, 1)
    try_add("1-solo-long", c1_long, 1)
    try_add("1-solo-reg", c1_reg, 1)

    # Second set (can reuse Monday arcs since tested on separate forks from the same Mon 18:15 savestate!):
    # Up to 20 disjoint Capital closed 2-car tours for driver pool depth testing
    used_depth: set[str] = set()
    depth_tours: list[dict[str, Any]] = []
    for _, t_arcs, sim in sorted(c2_long + c2_short, key=lambda x: x[0], reverse=True):
        if any(x.rid in used_depth for x in t_arcs):
            continue
        used_depth.update(x.rid for x in t_arcs)
        depth_tours.append({
            "kind": "depth-2-closed",
            "rids": [x.rid for x in t_arcs],
            "options": {x.rid: x.option for x in t_arcs},
            "route": " -> ".join(f"{x.pickup}->{x.delivery}" for x in t_arcs),
            "start_place": t_arcs[0].pickup,
            "end_place": t_arcs[-1].delivery,
            "road_min": sim["road_min"],
            "deadhead_min": sim["deadhead_min"],
            "sum_ref_cents": sum(x.ref_cents for x in t_arcs),
        })
        if len(depth_tours) >= 18:
            break

    return probe_tours, depth_tours


def make_post_action(orders: dict[str, Any], reqs: dict[str, Any], rids: list[str], now: int, fee_cents: int, geo: Geo) -> dict[str, Any]:
    stops = []
    exp = False
    man = False
    for rid in rids:
        o = orders[rid]
        req = reqs[rid]
        flags = note_flags(req["note"], v2=True)
        exp = exp or any(l["car"]["premium"] for l in o["legs"])
        man = man or flags.manual
        retry = Retry(plates=flags.plates)
        s = without_windows(stops_for(o, [0], req["note"], retry, geo, 200.0, True, req["arrivedAt"]), now)
        stops.extend(s)
    return {
        "type": "post",
        "stops": stops,
        "audience": {"experienced": exp, "manualLicence": man},
        "schedule": [{"at": now, "feeCents": max(100, int(fee_cents))}],
    }


def pack_noncompeting_batches(tours: list[dict[str, Any]], geo: Geo) -> list[list[int]]:
    """Packs tour indices into batches where start places are > 80 km apart so driver pools don't compete."""
    batches: list[list[int]] = []
    for idx, t in enumerate(tours):
        placed = False
        for b in batches:
            if all(geo.line_km(t["start_place"], tours[j]["start_place"]) > 85.0 and geo.line_km(t["end_place"], tours[j]["start_place"]) > 85.0 for j in b):
                b.append(idx)
                placed = True
                break
        if not placed:
            batches.append([idx])
    return batches


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="dev-12")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    geo = load_geo()
    tape = load_tape(args.seed)
    probe_tours, depth_tours = build_monday_probe_set(geo, tape)

    target_opts: dict[str, str] = {}
    for t in probe_tours + depth_tours:
        for rid, opt in t["options"].items():
            target_opts.setdefault(rid, opt)

    batches = pack_noncompeting_batches(probe_tours, geo)
    print(f"Built {len(probe_tours)} probe tours in {len(batches)} non-competing batches, plus {len(depth_tours)} depth tours ({len(target_opts)} unique Monday requests).")
    for i, t in enumerate(probe_tours):
        print(f"  [{i:02d}] {t['kind']:<15} {t['rids']} {t['route']} | road={t['road_min']}m dh={t['deadhead_min']}m | ref=€{t['sum_ref_cents']/100:.0f}")

    if args.dry_run:
        return

    def eval_posts_on_fork(g: Tas, posts: list[dict[str, Any]], eval_to: int) -> dict[int, str]:
        """Returns {post_idx: booked_driver_id} for posts that book and remain booked (not dropped) by eval_to."""
        step = on_fork(g, posts, eval_to)
        gid_to_idx = {}
        for idx, res in enumerate(step["results"]):
            if res.get("ok"):
                gid_to_idx[res["id"]] = idx
        booked: dict[int, str] = {}
        for ev in step["events"]:
            k = ev["kind"]
            if k == "gig_booked" and ev["gigId"] in gid_to_idx:
                booked[gid_to_idx[ev["gigId"]]] = ev["driverId"]
            elif k in ("gig_dropped", "no_show", "gig_expired") and ev.get("gigId") in gid_to_idx:
                booked.pop(gid_to_idx[ev["gigId"]], None)
        return booked

    with Tas(args.seed, name="tas-routes-probe", forks=True) as g:
        # Hold all won orders unposted on the main line
        g.desk.post = lambda *a, **kw: None  # type: ignore[method-assign]

        def quote_hook(game: Tas, actions: list, fresh: list) -> list:
            out = list(actions)
            for idx in fresh:
                rid = out[idx]["requestId"]
                r = game.desk.requests[rid]
                want_opt = target_opts.get(rid)
                if want_opt and any(o["kind"] == want_opt for o in r["options"]):
                    o = next(o for o in r["options"] if o["kind"] == want_opt)
                    out[idx] = {"type": "quote", "requestId": rid, "prices": {want_opt: int(o["listPriceCents"] * 0.75)}}
                else:
                    o0 = r["options"][0]
                    out[idx] = {"type": "quote", "requestId": rid, "prices": {o0["kind"]: int(o0["listPriceCents"] * 4.0)}}
            return out

        g.hook = quote_hook
        g.play_to(1100)
        now = g.desk.now
        orders_won = g.desk.orders
        reqs_seen = g.desk.requests

        print(f"At Mon 18:20 (now={now}): won {len(orders_won)}/{len(target_opts)} target Monday orders.")
        valid_probes = [t for t in probe_tours if all(rid in orders_won and orders_won[rid]["option"] == t["options"][rid] for rid in t["rids"])]
        batches = pack_noncompeting_batches(valid_probes, geo)
        print(f"Valid probe tours won intact: {len(valid_probes)}/{len(probe_tours)} across {len(batches)} fork batches.")

        eval_to = 2010
        lo = [int(t["sum_ref_cents"] * 0.25) for t in valid_probes]
        hi = [int(t["sum_ref_cents"] * 1.60) for t in valid_probes]
        booked_driver_at_hi: dict[int, str] = {}

        for b_idx, batch in enumerate(batches):
            for rnd in range(8):
                active = [i for i in batch if hi[i] - lo[i] > 250]
                if not active:
                    break
                mids = [((lo[i] + hi[i]) // 2) for i in active]
                posts = [make_post_action(orders_won, reqs_seen, valid_probes[i]["rids"], now, m, geo) for i, m in zip(active, mids)]
                booked_map = eval_posts_on_fork(g, posts, eval_to)
                for p_pos, i in enumerate(active):
                    if p_pos in booked_map:
                        hi[i] = mids[p_pos]
                        booked_driver_at_hi[i] = booked_map[p_pos]
                    else:
                        lo[i] = mids[p_pos]

        print(f"=== STEP 2 MEASURED FLAT-FEE RESERVATION COSTS (dev-12, {g.forks} forks) ===")
        print(f"{'Kind':<15} {'Cars':>4} {'Road_m':>6} {'DH_m':>4} {'Ref€':>6} {'MinFee€':>8} {'Fee/Ref':>8} {'€/RoadH':>8} {'Route'}")
        out_rows = []
        for i, t in enumerate(valid_probes):
            fee_eur = hi[i] / 100.0
            ref_eur = t["sum_ref_cents"] / 100.0
            road_h = t["road_min"] / 60.0
            eur_per_h = fee_eur / road_h
            ratio = fee_eur / ref_eur
            print(f"{t['kind']:<15} {t['n_cars']:>4} {t['road_min']:>6} {t['deadhead_min']:>4} {ref_eur:>6.1f} {fee_eur:>8.2f} {ratio:>8.3f} {eur_per_h:>8.2f} {t['route']}")
            out_rows.append({
                **t,
                "lo_cents": lo[i],
                "hi_cents": hi[i],
                "fee_over_ref": round(ratio, 4),
                "eur_per_road_h": round(eur_per_h, 2),
                "driver_id": booked_driver_at_hi.get(i, ""),
            })

        valid_depth = [t for t in depth_tours if all(rid in orders_won for rid in t["rids"])]
        depth_summary = []
        if valid_depth:
            print(f"=== CAPITAL CLOSED-TOUR POOL DEPTH TEST ({len(valid_depth)} simultaneous 2-car tours) ===")
            for mult in (0.50, 0.60, 0.70, 0.80, 0.90):
                posts = [make_post_action(orders_won, reqs_seen, t["rids"], now, int(t["sum_ref_cents"] * mult), geo) for t in valid_depth]
                booked_map = eval_posts_on_fork(g, posts, eval_to)
                booked_n = len(booked_map)
                print(f"  Flat mult {mult:.2f} x sum(ref): {booked_n}/{len(posts)} simultaneous 2-car tours booked by Tue 09:30")
                depth_summary.append({"mult": mult, "posted": len(posts), "booked": booked_n})

        out_path = lab_home() / "tas" / args.seed / "tas-routes-step2-fees.json"
        out_path.write_text(json.dumps({"seed": args.seed, "forks_used": g.forks, "probes": out_rows, "depth": depth_summary}, indent=2), encoding="utf-8")
        print(f"Saved {out_path} (total forks={g.forks}, requests={g.client.requests}).")


if __name__ == "__main__":
    main()
