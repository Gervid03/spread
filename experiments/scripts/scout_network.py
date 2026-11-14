#!/usr/bin/env python3
"""R15: The network census (for Idea 31, the route network).

Standard-library scouting script over finished world reveals (Champion v3 16 dev worlds).
Usage:
    uv run python experiments/scripts/scout_network.py runs/reveals-v3
"""
from __future__ import annotations

import csv
import json
import math
import statistics as st
import sys
from collections import Counter, defaultdict
from pathlib import Path

csv.field_size_limit(10**9)

EARTH_KM = 6371.0
DAY = 1440
CAPITAL = {"helsinki", "espoo", "vantaa"}


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_KM * math.asin(math.sqrt(a))


def read_csv(folder: Path, name: str) -> list[dict[str, str]]:
    with open(folder / f"{name}.csv", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def fmt_mr(vals: list[float], digits: int = 1) -> str:
    if not vals:
        return "0.0 [0..0]"
    m = st.mean(vals)
    lo, hi = min(vals), max(vals)
    if digits == 0:
        return f"{m:.1f} [{lo:.0f}..{hi:.0f}]"
    return f"{m:.{digits}f} [{lo:.{digits}f}..{hi:.{digits}f}]"


def max_bipartite_matching(
    num_left: int,
    num_right: int,
    adj_phase1: dict[int, list[int]],
    adj_phase2: dict[int, list[int]],
) -> tuple[int, int, dict[int, int]]:
    """Two-phase augmenting-path matching:
    Phase 1 maximizes matches on home-bound edges (adj_phase1).
    Phase 2 augments from the Phase 1 matching using remaining valid edges (adj_phase2),
    preserving every matched left/right vertex and maximizing total cardinality.
    Returns (hb_matches, total_matches, match_right_to_left).
    """
    match_r: dict[int, int] = {}
    match_l: dict[int, int] = {}

    def dfs(u: int, adj: dict[int, list[int]], seen: set[int]) -> bool:
        for v in adj.get(u, ()):
            if v in seen:
                continue
            seen.add(v)
            if v not in match_r or dfs(match_r[v], adj, seen):
                match_r[v] = u
                match_l[u] = v
                return True
        return False

    hb = 0
    for u in range(num_left):
        if dfs(u, adj_phase1, set()):
            hb += 1

    combined: dict[int, list[int]] = {}
    for u in range(num_left):
         combined[u] = list(adj_phase1.get(u, ())) + list(adj_phase2.get(u, ()))

    tot = hb
    for u in range(num_left):
        if u not in match_l:
            if dfs(u, combined, set()):
                tot += 1

    return hb, tot, match_r


def discover_reveals(args: list[str]) -> list[Path]:
    paths: list[Path] = []
    inputs = [Path(a) for a in args] if args else [Path("runs/reveals-v3")]
    for p in inputs:
        if not p.exists():
            continue
        if (p / "gigs.csv").exists():
            paths.append(p)
        else:
            for child in sorted(p.iterdir()):
                if child.is_dir() and (child / "gigs.csv").exists():
                    paths.append(child)
    seen: set[str] = set()
    unique: list[Path] = []
    for p in paths:
        wid = p.name.replace("reveal-", "")
        if wid not in seen:
            seen.add(wid)
            unique.append(p)
    return unique


def load_seed_map() -> dict[str, str]:
    mapping: dict[str, str] = {}
    champ = Path("champion/results/dev-L8.jsonl")
    if champ.exists():
        with open(champ, encoding="utf-8") as f:
            for line in f:
                row = json.loads(line)
                mapping[row["world"]] = row["seed"]
    return mapping


def analyze_world(folder: Path, seed_label: str) -> dict:
    places = read_csv(folder, "places")
    roads = read_csv(folder, "roads")
    drivers_rows = read_csv(folder, "drivers")
    requests_rows = read_csv(folder, "requests")
    legs_rows = read_csv(folder, "legs")
    gigs_rows = read_csv(folder, "gigs")
    events_rows = read_csv(folder, "events")
    views_rows = read_csv(folder, "views")

    coords = {p["id"]: (float(p["lat"]), float(p["lon"])) for p in places}
    place_ids = [p["id"] for p in places]
    line_km: dict[tuple[str, str], float] = {}
    for a in place_ids:
        la, loa = coords[a]
        for b in place_ids:
            lb, lob = coords[b]
            line_km[(a, b)] = 0.0 if a == b else haversine_km(la, loa, lb, lob)

    road_min: dict[tuple[str, str], int] = {}
    road_km: dict[tuple[str, str], float] = {}
    for r in roads:
        road_min[(r["from"], r["to"])] = int(r["minutes"])
        road_km[(r["from"], r["to"])] = float(r["km"])

    drivers = {d["id"]: d for d in drivers_rows}
    homes = Counter(d["homePlaceId"] for d in drivers_rows)
    supply_30 = {
        p: sum(n for h, n in homes.items() if line_km[(p, h)] <= 30.0)
        for p in place_ids
    }
    supply_55 = {
        p: sum(n for h, n in homes.items() if line_km[(p, h)] <= 55.0)
        for p in place_ids
    }

    legs_by_req: dict[str, list[dict]] = defaultdict(list)
    for leg in legs_rows:
        legs_by_req[leg["requestId"]].append(leg)
    for rid in legs_by_req:
        legs_by_req[rid].sort(key=lambda x: int(x["leg"]))

    # Parse requests
    reqs: dict[str, dict] = {}
    pickup_town_counts: Counter = Counter()
    for r in requests_rows:
        rid = r["id"]
        rlegs = legs_by_req[rid]
        p0 = rlegs[0]["pickup.placeId"]
        d_last = rlegs[-1]["delivery.placeId"]
        pickup_town_counts[p0] += 1
        opts = []
        quoted_opts = []
        for kind in ("same_day", "next_day", "within_3_days"):
            dl_s = r.get(f"{kind}.deadline", "")
            lp_s = r.get(f"{kind}.listPriceCents", "")
            qc_s = r.get(f"{kind}.quoteCents", "")
            if dl_s and lp_s:
                dl, lp = int(dl_s), int(lp_s)
                qc = int(qc_s) if qc_s else None
                opts.append((kind, dl, lp, qc))
                if qc is not None:
                    quoted_opts.append((kind, dl, lp, qc))
        # Determine outcome class: won, lost (competitive quote), declined (4x list)
        if r["outcome"] == "won":
            status = "won"
        elif len(quoted_opts) == 1 and quoted_opts[0][3] >= int(quoted_opts[0][2] * 3.5):
            status = "declined"
        else:
            status = "lost"

        first_q_ratio = (
            quoted_opts[0][3] / quoted_opts[0][2] if quoted_opts else None
        )
        drive_m = sum(
            road_min[(lg["pickup.placeId"], lg["delivery.placeId"])] for lg in rlegs
        )
        if len(rlegs) == 2:
            drive_m += road_min[(rlegs[0]["delivery.placeId"], rlegs[1]["pickup.placeId"])]

        reqs[rid] = {
            "id": rid,
            "arrivedAt": int(r["arrivedAt"]),
            "respondBy": int(r["respondBy"]),
            "refFee": int(r["referenceFeeCents"]),
            "outcome": r["outcome"],
            "status": status,
            "won_option": r["option"],
            "legs": rlegs,
            "p0": p0,
            "d_last": d_last,
            "ready": int(rlegs[0]["pickup.window.from"]),
            "p0_to": int(rlegs[0]["pickup.window.to"]),
            "opts": opts,
            "quoted_opts": quoted_opts,
            "first_q_ratio": first_q_ratio,
            "drive_min": drive_m,
            "has_slow": any(k in ("next_day", "within_3_days") for k, _, _, _ in opts),
            "premium": any(lg["car.premium"] == "true" for lg in rlegs),
        }

    # Parse gigs & events
    gigs = {g["id"]: g for g in gigs_rows}
    gig_booked_driver: dict[str, str] = {}
    gig_booked_at: dict[str, int] = {}
    gig_started_at: dict[str, int] = {}
    gig_pickups: dict[str, list[tuple[int, str, str, int]]] = defaultdict(list)
    gig_deliveries: dict[str, list[tuple[int, str, str, int]]] = defaultdict(list)
    # Track working intervals per driver: (start_at, end_at, gig_id)
    # Also booking-held intervals before start: (booked_at, leave_or_drop_at, gig_id)
    active_book: dict[str, tuple[int, str]] = {}
    active_work: dict[str, tuple[int, str]] = {}
    booked_prestart_spans: dict[str, list[tuple[int, int, str]]] = defaultdict(list)
    working_spans: dict[str, list[tuple[int, int, str]]] = defaultdict(list)

    # Sort events by seq
    events_sorted = sorted(events_rows, key=lambda e: int(e["seq"]))
    for e in events_sorted:
        kind = e["kind"]
        at = int(e["at"])
        gid = e["gigId"]
        if kind == "gig_booked":
            did = e["driverId"]
            gig_booked_driver[gid] = did
            gig_booked_at[gid] = at
            active_book[gid] = (at, did)
        elif kind in ("gig_dropped", "no_show"):
            if gid in active_book:
                b_at, did = active_book.pop(gid)
                booked_prestart_spans[did].append((b_at, at, gid))
        elif kind == "gig_started":
            did = e["driverId"] or gig_booked_driver.get(gid, "")
            gig_started_at[gid] = at
            if gid in active_book:
                b_at, _ = active_book.pop(gid)
                booked_prestart_spans[did].append((b_at, at, gid))
            active_work[gid] = (at, did)
        elif kind == "picked_up":
            gig_pickups[gid].append((at, e["orderId"], e["placeId"], int(e["leg"])))
        elif kind == "delivered":
            gig_deliveries[gid].append((at, e["orderId"], e["placeId"], int(e["leg"])))
        elif kind == "order_cancelled":
            if e.get("gigs"):
                for cg in json.loads(e["gigs"]):
                    cgid = cg.get("gigId") or cg.get("id", "")
                    eff = cg.get("outcome") or cg.get("effect") or cg.get("status") or ""
                    if eff == "released" and cgid in active_book:
                        b_at, did = active_book.pop(cgid)
                        booked_prestart_spans[did].append((b_at, at, cgid))

    # Close working spans at last delivery (or last pickup/visit_failed) of each started gig
    gig_last_event_at: dict[str, int] = {}
    for e in events_sorted:
        if e["gigId"] and e["kind"] in ("picked_up", "delivered", "visit_failed"):
            gig_last_event_at[e["gigId"]] = int(e["at"])
    for gid, (s_at, did) in active_work.items():
        end_at = gig_last_event_at.get(gid, s_at)
        if did:
            working_spans[did].append((s_at, end_at, gid))

    # --- Q1: Finishes ---
    finishes: list[dict] = []
    for gid, delivs in gig_deliveries.items():
        g = gigs.get(gid, {})
        did = g.get("driverId") or gig_booked_driver.get(gid, "")
        drv = drivers.get(did, {})
        home = drv.get("homePlaceId", "")
        delivs_sorted = sorted(delivs, key=lambda x: x[0])
        for idx, (at, oid, place, leg_i) in enumerate(delivs_sorted):
            dist_home = line_km[(place, home)] if home else 0.0
            is_gig_final = idx == len(delivs_sorted) - 1
            finishes.append({
                "gigId": gid,
                "driverId": did,
                "home": home,
                "orderId": oid,
                "leg": leg_i,
                "place": place,
                "at": at,
                "day": at // DAY,
                "block2h": (at % DAY) // 120,
                "far_from_home": dist_home > 30.0,
                "dist_home": dist_home,
                "is_gig_final": is_gig_final,
                "experienced": float(drv.get("rating", 0)) >= 4.8 and int(drv.get("completedGigs", 0)) >= 50,
                "manual": drv.get("licence") == "manual",
            })
    finishes.sort(key=lambda x: (x["at"], x["gigId"], x["orderId"], x["leg"]))

    town_day_finishes: Counter = Counter()
    town_block_finishes: Counter = Counter()
    town_finishes: Counter = Counter()
    town_far_finishes: Counter = Counter()
    block_finishes: Counter = Counter()
    day_finishes: Counter = Counter()
    for f in finishes:
        town_finishes[f["place"]] += 1
        day_finishes[f["day"]] += 1
        town_day_finishes[(f["place"], f["day"])] += 1
        town_block_finishes[(f["place"], f["block2h"])] += 1
        block_finishes[f["block2h"]] += 1
        if f["far_from_home"]:
            town_far_finishes[f["place"]] += 1

    # Helper: check if a driver finishing at (f_place, f_at) can deliver req on time by road minutes
    def can_deliver_req(f_place: str, f_at: int, req: dict, slack_req: int = 0) -> bool:
        ready = req["ready"]
        if not (f_at - 60 <= ready <= f_at + 180):
            return False
        t_p0 = max(ready, f_at + road_min[(f_place, req["p0"])])
        if t_p0 > req["p0_to"]:
            return False
        rlegs = req["legs"]
        if len(rlegs) == 1:
            t_deliv = t_p0 + road_min[(req["p0"], req["d_last"])]
        else:
            d0 = rlegs[0]["delivery.placeId"]
            p1 = rlegs[1]["pickup.placeId"]
            d1 = rlegs[1]["delivery.placeId"]
            t_d0 = t_p0 + road_min[(req["p0"], d0)]
            t_p1 = max(int(rlegs[1]["pickup.window.from"]), t_d0 + road_min[(d0, p1)])
            if t_p1 > int(rlegs[1]["pickup.window.to"]):
                return False
            t_deliv = t_p1 + road_min[(p1, d1)]
        return any(t_deliv + slack_req <= dl for _, dl, _, _ in req["opts"])

    # --- Q2 & Q3: Continuations & Redundancy ---
    req_list = [reqs[rid] for rid in sorted(reqs)]
    req_idx_map = {r["id"]: i for i, r in enumerate(req_list)}

    cont_stats: dict[int, dict] = {}
    for radius in (15, 30):
        # Map req_i -> list of (finish_idx, driverId, is_hb)
        req_cands: dict[int, list[tuple[int, str, bool]]] = defaultdict(list)
        req_cands_slack180: set[int] = set()
        adj_hb_all: dict[int, list[int]] = defaultdict(list)
        adj_nhb_all: dict[int, list[int]] = defaultdict(list)
        adj_hb_nonwon: dict[int, list[int]] = defaultdict(list)
        adj_nhb_nonwon: dict[int, list[int]] = defaultdict(list)
        adj_hb_decl: dict[int, list[int]] = defaultdict(list)
        adj_nhb_decl: dict[int, list[int]] = defaultdict(list)

        for fi, f in enumerate(finishes):
            f_gig_orders = set(gigs.get(f["gigId"], {}).get("orders", "").split())
            for ri, req in enumerate(req_list):
                if req["id"] == f["orderId"] or req["id"] in f_gig_orders:
                    continue
                if line_km[(f["place"], req["p0"])] > radius:
                    continue
                if not can_deliver_req(f["place"], f["at"], req, slack_req=0):
                    continue
                is_hb = bool(f["home"]) and line_km[(req["d_last"], f["home"])] <= 30.0
                req_cands[ri].append((fi, f["driverId"], is_hb))
                if can_deliver_req(f["place"], f["at"], req, slack_req=180):
                    if not req["premium"] or f["experienced"]:
                        req_cands_slack180.add(ri)
                if is_hb:
                    adj_hb_all[fi].append(ri)
                    if req["status"] != "won":
                        adj_hb_nonwon[fi].append(ri)
                    if req["status"] == "declined":
                        adj_hb_decl[fi].append(ri)
                else:
                    adj_nhb_all[fi].append(ri)
                    if req["status"] != "won":
                        adj_nhb_nonwon[fi].append(ri)
                    if req["status"] == "declined":
                        adj_nhb_decl[fi].append(ri)

        # Order nhb edges: capital delivery first, then other
        for adj in (adj_nhb_all, adj_nhb_nonwon, adj_nhb_decl):
            for fi in adj:
                adj[fi].sort(key=lambda ri: (0 if req_list[ri]["d_last"] in CAPITAL else 1, ri))

        disj_hb_all, disj_tot_all, match_all = max_bipartite_matching(
            len(finishes), len(req_list), adj_hb_all, adj_nhb_all
        )
        disj_cap_all = sum(
            1
            for ri, fi in match_all.items()
            if ri not in adj_hb_all.get(fi, ()) and req_list[ri]["d_last"] in CAPITAL
        )
        disj_oth_all = disj_tot_all - disj_hb_all - disj_cap_all

        disj_hb_nw, disj_tot_nw, match_nw = max_bipartite_matching(
            len(finishes), len(req_list), adj_hb_nonwon, adj_nhb_nonwon
        )
        disj_hb_decl, disj_tot_decl, _ = max_bipartite_matching(
            len(finishes), len(req_list), adj_hb_decl, adj_nhb_decl
        )

        # Count requests (not pairs) and redundancy
        n_hb, n_cap_only, n_other, n_hb_also_cap = 0, 0, 0, 0
        by_status = Counter()
        by_status_hb = Counter()
        redundancy_all = Counter()       # 0, 1, 2, 3, 4+
        redundancy_hb = Counter()        # for HB requests: total candidate drivers
        redundancy_nhb = Counter()       # for non-HB requests: total candidate drivers
        redundancy_nonwon_hb = Counter()
        redundancy_nonwon_nhb = Counter()
        redundancy_decl_hb = Counter()
        redundancy_decl_nhb = Counter()
        redundancy_noncap_pickup = Counter()

        for ri, req in enumerate(req_list):
            cands = req_cands.get(ri, [])
            if not cands:
                redundancy_all[0] += 1
                continue
            drv_all = {did for _, did, _ in cands}
            drv_hb = {did for _, did, hb in cands if hb}
            k = len(drv_all)
            kb = min(k, 4)
            redundancy_all[kb] += 1
            if req["p0"] not in CAPITAL and req["p0"] != "hyvinkaa":
                redundancy_noncap_pickup[kb] += 1

            is_req_hb = len(drv_hb) > 0
            is_req_cap = req["d_last"] in CAPITAL
            by_status[req["status"]] += 1
            if is_req_hb:
                n_hb += 1
                by_status_hb[req["status"]] += 1
                if is_req_cap:
                    n_hb_also_cap += 1
                redundancy_hb[kb] += 1
                if req["status"] != "won":
                    redundancy_nonwon_hb[kb] += 1
                if req["status"] == "declined":
                    redundancy_decl_hb[kb] += 1
            elif is_req_cap:
                n_cap_only += 1
                redundancy_nhb[kb] += 1
                if req["status"] != "won":
                    redundancy_nonwon_nhb[kb] += 1
                if req["status"] == "declined":
                    redundancy_decl_nhb[kb] += 1
            else:
                n_other += 1
                redundancy_nhb[kb] += 1
                if req["status"] != "won":
                    redundancy_nonwon_nhb[kb] += 1
                if req["status"] == "declined":
                    redundancy_decl_nhb[kb] += 1

        # Exact fanout-3 acceptance sum per world for Q6
        prize: dict[str, dict[float, float]] = {
            "all_hb": {}, "all_nhb": {},
            "nonwon_hb": {}, "nonwon_nhb": {},
            "decl_hb": {}, "decl_nhb": {},
            "won_hb": {}, "won_nhb": {},
        }
        for p_acc in (0.2, 0.4, 0.6):
            for key in prize:
                prize[key][p_acc] = 0.0
            for ri, req in enumerate(req_list):
                cands = req_cands.get(ri, [])
                if not cands:
                    continue
                k = len({did for _, did, _ in cands})
                m = min(k, 3)  # at most 3 open offers per gig
                prob = 1.0 - (1.0 - p_acc) ** m
                is_req_hb = any(hb for _, _, hb in cands)
                suf = "hb" if is_req_hb else "nhb"
                prize[f"all_{suf}"][p_acc] += prob
                if req["status"] == "won":
                    prize[f"won_{suf}"][p_acc] += prob
                else:
                    prize[f"nonwon_{suf}"][p_acc] += prob
                    if req["status"] == "declined":
                        prize[f"decl_{suf}"][p_acc] += prob

        cont_stats[radius] = {
            "total_reqs": n_hb + n_cap_only + n_other,
            "slack180_reqs": len(req_cands_slack180),
            "hb": n_hb,
            "cap_only": n_cap_only,
            "hb_also_cap": n_hb_also_cap,
            "cap_total": n_cap_only + n_hb_also_cap,
            "other": n_other,
            "by_status": by_status,
            "by_status_hb": by_status_hb,
            "disj_hb_all": disj_hb_all,
            "disj_cap_all": disj_cap_all,
            "disj_oth_all": disj_oth_all,
            "disj_tot_all": disj_tot_all,
            "disj_hb_nw": disj_hb_nw,
            "disj_tot_nw": disj_tot_nw,
            "disj_hb_decl": disj_hb_decl,
            "disj_tot_decl": disj_tot_decl,
            "redundancy_all": redundancy_all,
            "redundancy_hb": redundancy_hb,
            "redundancy_nhb": redundancy_nhb,
            "redundancy_nonwon_hb": redundancy_nonwon_hb,
            "redundancy_nonwon_nhb": redundancy_nonwon_nhb,
            "redundancy_decl_hb": redundancy_decl_hb,
            "redundancy_decl_nhb": redundancy_decl_nhb,
            "redundancy_noncap_pickup": redundancy_noncap_pickup,
            "prize": prize,
            "has_cand_set": set(req_cands.keys()),
        }

    # --- Q4: Organic chaining & views while working ---
    # Typical fee of a gig
    def gig_typical_fee(g: dict) -> float:
        stops = json.loads(g["stops"])
        order_legs: dict[str, set[int]] = defaultdict(set)
        for s in stops:
            if s["kind"] == "pickup":
                order_legs[s["orderId"]].add(int(s["leg"]))
        tot = 0.0
        for oid, lset in order_legs.items():
            if oid in reqs:
                tot += reqs[oid]["refFee"] * len(lset) / len(reqs[oid]["legs"])
        return tot

    # Completed / executed gigs per driver
    driver_gigs_by_day: dict[tuple[str, int], list[dict]] = defaultdict(list)
    hub_pickup_lags: list[int] = []
    for gid, pups in gig_pickups.items():
        delivs = gig_deliveries.get(gid, [])
        if not pups or not delivs:
            continue
        g = gigs.get(gid, {})
        did = g.get("driverId") or gig_booked_driver.get(gid, "")
        if not did:
            continue
        pups_s = sorted(pups, key=lambda x: x[0])
        delivs_s = sorted(delivs, key=lambda x: x[0])
        first_p_at, first_oid, first_p_place, _ = pups_s[0]
        last_d_at, _, last_d_place, _ = delivs_s[-1]
        typ = gig_typical_fee(g)
        fee = int(g["feeCents"]) if g.get("feeCents") else 0
        if first_oid in reqs and supply_30.get(first_p_place, 0) >= 100:
            r0 = reqs[first_oid]
            hub_pickup_lags.append(max(0, first_p_at - max(r0["respondBy"], r0["ready"])))
        day = first_p_at // DAY
        driver_gigs_by_day[(did, day)].append({
            "gigId": gid,
            "driverId": did,
            "first_p_at": first_p_at,
            "first_p_place": first_p_place,
            "last_d_at": last_d_at,
            "last_d_place": last_d_place,
            "booked_at": gig_booked_at.get(gid, first_p_at),
            "fee": fee,
            "typ": typ,
            "fee_ratio": fee / typ if typ > 0 else 1.0,
        })

    multi_driver_days = 0
    chain_pairs: list[dict] = []
    for (did, day), glist in driver_gigs_by_day.items():
        if len(glist) >= 2:
            multi_driver_days += 1
            glist.sort(key=lambda x: x["first_p_at"])
            home = drivers.get(did, {}).get("homePlaceId", "")
            for a, b in zip(glist, glist[1:]):
                dist_d1_p2 = line_km[(a["last_d_place"], b["first_p_place"])]
                p2_near_home = bool(home) and line_km[(b["first_p_place"], home)] <= 30.0
                gap_min = b["first_p_at"] - a["last_d_at"]
                booked_after_d1 = b["booked_at"] >= a["last_d_at"]
                chain_pairs.append({
                    "dist_km": dist_d1_p2,
                    "p2_near_home": p2_near_home,
                    "gap_min": gap_min,
                    "booked_after_d1": booked_after_d1,
                    "r1": a["fee_ratio"],
                    "r2": b["fee_ratio"],
                })

    # Views from drivers working one of our gigs at the time
    total_views = len(views_rows)
    views_while_working = 0
    views_while_working_other_gig = 0
    views_while_booked_prestart = 0
    working_viewer_drivers: set[str] = set()
    for v in views_rows:
        did = v["driverId"]
        vat = int(v["at"])
        vgid = v["gigId"]
        in_work = False
        in_work_other = False
        for s_at, e_at, wgid in working_spans.get(did, ()):
            if s_at <= vat <= e_at:
                in_work = True
                if wgid != vgid:
                    in_work_other = True
        if in_work:
            views_while_working += 1
            working_viewer_drivers.add(did)
            if in_work_other:
                views_while_working_other_gig += 1
        else:
            for b_at, e_at, _ in booked_prestart_spans.get(did, ()):
                if b_at <= vat < e_at:
                    views_while_booked_prestart += 1
                    break

    # --- Q5: Seeding ---
    active_towns_6 = {t for t, c in pickup_town_counts.items() if c >= 6}
    med_hub_lag = int(st.median(hub_pickup_lags)) if hub_pickup_lags else 60

    seed_reqs_all: list[dict] = []
    for req in req_list:
        if req["status"] == "won":
            continue
        if supply_30.get(req["p0"], 0) < 100:
            continue
        if not any(line_km[(req["d_last"], t)] <= 30.0 for t in active_towns_6):
            continue
        # Estimate when a driver from p0 would finish at d_last if won
        est_finish = max(req["respondBy"], req["ready"]) + med_hub_lag + req["drive_min"]
        c15_all, c15_new, c15_nonwon = 0, 0, 0
        c30_all, c30_new, c30_nonwon = 0, 0, 0
        for ri2, r2 in enumerate(req_list):
            if r2["id"] == req["id"]:
                continue
            d_km = line_km[(req["d_last"], r2["p0"])]
            if d_km > 30.0:
                continue
            if not can_deliver_req(req["d_last"], est_finish, r2, slack_req=0):
                continue
            c30_all += 1
            if r2["status"] != "won":
                c30_nonwon += 1
            if ri2 not in cont_stats[30]["has_cand_set"]:
                c30_new += 1
            if d_km <= 15.0:
                c15_all += 1
                if r2["status"] != "won":
                    c15_nonwon += 1
                if ri2 not in cont_stats[15]["has_cand_set"]:
                    c15_new += 1

        seed_reqs_all.append({
            "status": req["status"],
            "q_ratio": req["first_q_ratio"],
            "d_last": req["d_last"],
            "non_cap_deliv": supply_30.get(req["d_last"], 0) < 100,
            "thin_deliv": supply_55.get(req["d_last"], 0) < 30,
            "c15_all": c15_all,
            "c15_new": c15_new,
            "c15_nonwon": c15_nonwon,
            "c30_all": c30_all,
            "c30_new": c30_new,
            "c30_nonwon": c30_nonwon,
        })

    return {
        "seed": seed_label,
        "world": folder.name.replace("reveal-", ""),
        "n_reqs": len(req_list),
        "n_won": sum(1 for r in req_list if r["status"] == "won"),
        "n_lost": sum(1 for r in req_list if r["status"] == "lost"),
        "n_decl": sum(1 for r in req_list if r["status"] == "declined"),
        "finishes_total": len(finishes),
        "finishes_gig_final": sum(1 for f in finishes if f["is_gig_final"]),
        "finishes_far": sum(1 for f in finishes if f["far_from_home"]),
        "finishes_gig_final_far": sum(1 for f in finishes if f["is_gig_final"] and f["far_from_home"]),
        "town_finishes": town_finishes,
        "town_far_finishes": town_far_finishes,
        "town_day_finishes": town_day_finishes,
        "town_block_finishes": town_block_finishes,
        "block_finishes": block_finishes,
        "day_finishes": day_finishes,
        "cont": cont_stats,
        "multi_driver_days": multi_driver_days,
        "chain_pairs": chain_pairs,
        "total_views": total_views,
        "views_while_working": views_while_working,
        "views_while_working_other": views_while_working_other_gig,
        "views_while_booked_prestart": views_while_booked_prestart,
        "working_viewer_drivers": len(working_viewer_drivers),
        "med_hub_lag": med_hub_lag,
        "seed_reqs": seed_reqs_all,
        "active_towns_6": len(active_towns_6),
    }


def main() -> None:
    folders = discover_reveals(sys.argv[1:])
    if not folders:
        sys.exit("No reveal folders found.")
    seed_map = load_seed_map()
    worlds = []
    for f in folders:
        wid = f.name.replace("reveal-", "")
        worlds.append(analyze_world(f, seed_map.get(wid, wid)))
    worlds.sort(key=lambda w: w["seed"])
    nw = len(worlds)
    print(f"Analyzed {nw} worlds: {', '.join(w['seed'] for w in worlds)}")
    print()

    # === 1. FINISHES ===
    print("=== 1. FINISHES PER WEEK ===")
    print("  Delivered cars / wk:      ", fmt_mr([w["finishes_total"] for w in worlds]))
    print("  Gig-final finishes / wk:  ", fmt_mr([w["finishes_gig_final"] for w in worlds]))
    print("  Finish >30 km from home:  ", fmt_mr([w["finishes_far"] for w in worlds]),
          f"({100 * st.mean(w['finishes_far'] / w['finishes_total'] for w in worlds):.1f}%)")
    print("  Gig-final >30 km home:    ", fmt_mr([w["finishes_gig_final_far"] for w in worlds]),
          f"({100 * st.mean(w['finishes_gig_final_far'] / w['finishes_gig_final'] for w in worlds):.1f}%)")

    print()
    print("  Finishes by world day (0=Mon .. 4=Fri, 5=Sat, 6=Sun, 7=Mon2, 8+=Tue2+):")
    for d, lbl in [(0, "Mon"), (1, "Tue"), (2, "Wed"), (3, "Thu"), (4, "Fri"), (5, "Sat"), (6, "Sun"), (7, "Mon2")]:
        vals = [w["day_finishes"][d] for w in worlds]
        print(f"    {lbl:<5}: {fmt_mr(vals)}")
    vals_late = [sum(v for k, v in w["day_finishes"].items() if k >= 8) for w in worlds]
    print(f"    Tue2+: {fmt_mr(vals_late)}")

    print()
    print("  Finishes by 2-hour block of the day (weekly sum [min..max], and per weekday /5):")
    for b in range(12):
        vals = [w["block_finishes"][b] for w in worlds]
        if max(vals) > 0:
            print(f"    {b*2:02d}:00-{b*2+2:02d}:00 : {fmt_mr(vals):<18}  ({st.mean(vals)/5.0:.2f}/weekday)")

    all_towns = sorted(
        {t for w in worlds for t in w["town_finishes"]},
        key=lambda t: -st.mean(w["town_finishes"][t] for w in worlds),
    )
    print()
    print("  Finishes by delivery town (weekly total, >30 km from home, Mon-Fri/day, and per-day in 2h blocks):")
    hdr_blocks = " ".join(f"{b*2:02d}-{b*2+2:02d}" for b in range(4, 11))
    print(f"    {'Town':<14} {'Total/wk':<16} {'>30km home/wk':<16} {'%>30k':>6} {'M-F/d':>6} | {hdr_blocks} (per day, /5)")
    for t in all_towns:
        tot_v = [w["town_finishes"][t] for w in worlds]
        far_v = [w["town_far_finishes"][t] for w in worlds]
        mf_day = [sum(w["town_day_finishes"][(t, d)] for d in range(5)) / 5.0 for w in worlds]
        s_tot = sum(tot_v)
        pct_far = 100.0 * sum(far_v) / s_tot if s_tot else 0.0
        b_cells = " ".join(
            f"{st.mean(w['town_block_finishes'][(t, b)] for w in worlds) / 5.0:5.2f}"
            for b in range(4, 11)
        )
        print(f"    {t:<14} {fmt_mr(tot_v):<16} {fmt_mr(far_v):<16} {pct_far:5.1f}% {st.mean(mf_day):6.2f} | {b_cells}")

    # === 2. CONTINUATIONS ===
    print()
    print("=== 2. CONTINUATIONS PER WEEK (ready in [finish-1h, finish+3h], on-time by road min) ===")
    for rad in (15, 30):
        print()
        print(f"  --- Pickup within {rad} km of finish ---")
        c_list = [w["cont"][rad] for w in worlds]
        print("    Unique continuation requests (all):       ", fmt_mr([c["total_reqs"] for c in c_list]))
        print("      with >=180m slack & audience check:     ", fmt_mr([c["slack180_reqs"] for c in c_list]))
        print("      Split 1: Home-bound (<=30km drv home):  ", fmt_mr([c["hb"] for c in c_list]),
              f"(of which {fmt_mr([c['hb_also_cap'] for c in c_list])} also end in Capital)")
        print("      Split 2: Capital delivery (non-HB):     ", fmt_mr([c["cap_only"] for c in c_list]),
              f"(total Capital incl HB: {fmt_mr([c['cap_total'] for c in c_list])})")
        print("      Split 3: Other delivery (non-HB):       ", fmt_mr([c["other"] for c in c_list]))
        for st_k in ("won", "lost", "declined"):
            print(f"      Outcome = {st_k:<8} (all / HB):          ",
                  f"{fmt_mr([c['by_status'][st_k] for c in c_list])}  /  {fmt_mr([c['by_status_hb'][st_k] for c in c_list])}")
        print("    Disjoint 1-to-1 pairs (all outcomes, HB first):")
        print("      Total disjoint pairs:                   ", fmt_mr([c["disj_tot_all"] for c in c_list]))
        print("      ├─ Home-bound disjoint:                 ", fmt_mr([c["disj_hb_all"] for c in c_list]))
        print("      ├─ Capital (non-HB) disjoint:           ", fmt_mr([c["disj_cap_all"] for c in c_list]))
        print("      └─ Other (non-HB) disjoint:             ", fmt_mr([c["disj_oth_all"] for c in c_list]))
        print("    Disjoint 1-to-1 pairs (lost + declined only, HB first):")
        print("      Total non-won disjoint pairs:           ", fmt_mr([c["disj_tot_nw"] for c in c_list]),
              f"(HB: {fmt_mr([c['disj_hb_nw'] for c in c_list])})")
        print("    Disjoint 1-to-1 pairs (declined thin only, HB first):")
        print("      Total declined disjoint pairs:          ", fmt_mr([c["disj_tot_decl"] for c in c_list]),
              f"(HB: {fmt_mr([c['disj_hb_decl'] for c in c_list])})")

    # === 3. REDUNDANCY ===
    print()
    print("=== 3. REDUNDANCY (Candidate finishing drivers per request) ===")
    for rad in (15, 30):
        print()
        print(f"  --- Pickup within {rad} km ---")
        c_list = [w["cont"][rad] for w in worlds]
        for k_lbl, k_val in [("0", 0), ("1", 1), ("2", 2), ("3", 3), ("4+", 4)]:
            v_all = [c["redundancy_all"][k_val] for c in c_list]
            if k_val == 0:
                print(f"    {k_lbl:<3} candidates (not a continuation): {fmt_mr(v_all)}")
            else:
                v_hb = [c["redundancy_hb"][k_val] for c in c_list]
                v_nhb = [c["redundancy_nhb"][k_val] for c in c_list]
                v_nw = [c["redundancy_nonwon_hb"][k_val] + c["redundancy_nonwon_nhb"][k_val] for c in c_list]
                v_dc = [c["redundancy_decl_hb"][k_val] + c["redundancy_decl_nhb"][k_val] for c in c_list]
                v_reg = [c["redundancy_noncap_pickup"][k_val] for c in c_list]
                print(f"    {k_lbl:<3} candidates: all={fmt_mr(v_all):<16} HB={fmt_mr(v_hb):<15} nonHB={fmt_mr(v_nhb):<15} "
                      f"nonWon={fmt_mr(v_nw):<15} decl={fmt_mr(v_dc):<14} outsideCapRing={fmt_mr(v_reg)}")

    # === 4. ORGANIC CHAINING ===
    print()
    print("=== 4. ORGANIC CHAINING & WORKING-DRIVER VIEWS ===")
    print("  Driver-days with >=2 executed gigs: ", fmt_mr([w["multi_driver_days"] for w in worlds]))
    print("  Consecutive same-day gig pairs / wk:", fmt_mr([len(w["chain_pairs"]) for w in worlds]))
    p2_home_v = [sum(1 for p in w["chain_pairs"] if p["p2_near_home"]) for w in worlds]
    p2_far_v = [sum(1 for p in w["chain_pairs"] if not p["p2_near_home"]) for w in worlds]
    d15_v = [sum(1 for p in w["chain_pairs"] if p["dist_km"] <= 15.0) for w in worlds]
    d30_v = [sum(1 for p in w["chain_pairs"] if p["dist_km"] <= 30.0) for w in worlds]
    aft_v = [sum(1 for p in w["chain_pairs"] if p["booked_after_d1"]) for w in worlds]
    print("    2nd pickup <=30 km of driver home:", fmt_mr(p2_home_v))
    print("    2nd pickup > 30 km of driver home:", fmt_mr(p2_far_v))
    print("    1st deliv -> 2nd pickup <=15 km:  ", fmt_mr(d15_v))
    print("    1st deliv -> 2nd pickup <=30 km:  ", fmt_mr(d30_v))
    print("    2nd gig booked AFTER 1st delivery:", fmt_mr(aft_v))

    all_pairs = [p for w in worlds for p in w["chain_pairs"]]
    if all_pairs:
        print(f"    Pooled across {len(all_pairs)} pairs:")
        print(f"      Distance 1st deliv -> 2nd pickup (km): mean {st.mean(p['dist_km'] for p in all_pairs):.1f}, median {st.median(p['dist_km'] for p in all_pairs):.1f}")
        print(f"      Minutes between 1st deliv & 2nd pickup: mean {st.mean(p['gap_min'] for p in all_pairs):.1f}, median {st.median(p['gap_min'] for p in all_pairs):.1f}")
        print(f"      1st gig booked_fee / typical_fee:       mean {st.mean(p['r1'] for p in all_pairs):.3f}, median {st.median(p['r1'] for p in all_pairs):.3f}")
        print(f"      2nd gig booked_fee / typical_fee:       mean {st.mean(p['r2'] for p in all_pairs):.3f}, median {st.median(p['r2'] for p in all_pairs):.3f}")
        far_pairs = [p for p in all_pairs if not p["p2_near_home"]]
        near_pairs = [p for p in all_pairs if p["p2_near_home"]]
        if far_pairs:
            print(f"      [2nd pickup >30km home, n={len(far_pairs)}] dist med {st.median(p['dist_km'] for p in far_pairs):.1f} km, "
                  f"gap med {st.median(p['gap_min'] for p in far_pairs):.0f} min, r1={st.mean(p['r1'] for p in far_pairs):.3f}, r2={st.mean(p['r2'] for p in far_pairs):.3f}")
        if near_pairs:
            print(f"      [2nd pickup <=30km home, n={len(near_pairs)}] dist med {st.median(p['dist_km'] for p in near_pairs):.1f} km, "
                  f"gap med {st.median(p['gap_min'] for p in near_pairs):.0f} min, r1={st.mean(p['r1'] for p in near_pairs):.3f}, r2={st.mean(p['r2'] for p in near_pairs):.3f}")

    print("  Total gig views / wk:               ", fmt_mr([w["total_views"] for w in worlds]))
    print("  Views while working a gig of ours:  ", fmt_mr([w["views_while_working"] for w in worlds]),
          f"({100 * sum(w['views_while_working'] for w in worlds) / sum(w['total_views'] for w in worlds):.2f}%)")
    print("    (specifically viewing OTHER gig): ", fmt_mr([w["views_while_working_other"] for w in worlds]))
    print("    Distinct working viewer drivers:  ", fmt_mr([w["working_viewer_drivers"] for w in worlds]))
    print("  Views while holding pre-start gig:  ", fmt_mr([w["views_while_booked_prestart"] for w in worlds]))

    # === 5. SEEDING ===
    print()
    print("=== 5. SEEDING POTENTIAL ===")
    print("  Towns sending >=6 requests / wk:    ", fmt_mr([w["active_towns_6"] for w in worlds]))
    print("  Median hub pickup lag (min):        ", fmt_mr([w["med_hub_lag"] for w in worlds]))
    for label, pred in [
        ("All (pickup>=100, deliv <=30km of >=6-req town)", lambda s: True),
        ("  ├─ Lost (competitively quoted)", lambda s: s["status"] == "lost"),
        ("  ├─ Declined (4x list)", lambda s: s["status"] == "declined"),
        ("  ├─ Outbound to non-Capital (<100 drv at deliv)", lambda s: s["non_cap_deliv"]),
        ("  └─ Outbound to thin (<30 drv in 55km at deliv) & lost", lambda s: s["thin_deliv"] and s["status"] == "lost"),
    ]:
        counts = [sum(1 for s in w["seed_reqs"] if pred(s)) for w in worlds]
        q_vals = [
            st.mean(s["q_ratio"] for s in w["seed_reqs"] if pred(s) and s["q_ratio"] is not None)
            for w in worlds
            if any(pred(s) and s["q_ratio"] is not None for s in w["seed_reqs"])
        ]
        c15_per = [
            st.mean(s["c15_all"] for s in w["seed_reqs"] if pred(s))
            for w in worlds
            if any(pred(s) for s in w["seed_reqs"])
        ]
        c15_new_per = [
            st.mean(s["c15_new"] for s in w["seed_reqs"] if pred(s))
            for w in worlds
            if any(pred(s) for s in w["seed_reqs"])
        ]
        c30_per = [
            st.mean(s["c30_all"] for s in w["seed_reqs"] if pred(s))
            for w in worlds
            if any(pred(s) for s in w["seed_reqs"])
        ]
        c30_new_per = [
            st.mean(s["c30_new"] for s in w["seed_reqs"] if pred(s))
            for w in worlds
            if any(pred(s) for s in w["seed_reqs"])
        ]
        print(f"  {label}:")
        print(f"    Count/wk: {fmt_mr(counts)} | quote/list: {fmt_mr(q_vals, 3)}")
        print(f"    Continuations opened per seeded win: <=15km {fmt_mr(c15_per, 2)} (new 0->1: {fmt_mr(c15_new_per, 2)}) | "
              f"<=30km {fmt_mr(c30_per, 2)} (new 0->1: {fmt_mr(c30_new_per, 2)})")

    # === 6. SIZE OF THE PRIZE ===
    print()
    print("=== 6. SIZE OF THE PRIZE (Offer acceptance p in {0.2, 0.4, 0.6}, fanout <=3) ===")
    for rad in (15, 30):
        print()
        print(f"  --- Radius <= {rad} km ---")
        c_list = [w["cont"][rad] for w in worlds]
        for p_acc in (0.2, 0.4, 0.6):
            nw_hb = [c["prize"]["nonwon_hb"][p_acc] for c in c_list]
            nw_nhb = [c["prize"]["nonwon_nhb"][p_acc] for c in c_list]
            nw_tot = [a + b for a, b in zip(nw_hb, nw_nhb)]
            dc_hb = [c["prize"]["decl_hb"][p_acc] for c in c_list]
            dc_nhb = [c["prize"]["decl_nhb"][p_acc] for c in c_list]
            dc_tot = [a + b for a, b in zip(dc_hb, dc_nhb)]
            won_hb = [c["prize"]["won_hb"][p_acc] for c in c_list]
            won_nhb = [c["prize"]["won_nhb"][p_acc] for c in c_list]
            # Disjoint-capped & quote-win-rate (w=0.40) expected extra orders on declined and non-won
            dc_w40_hb = [min(c["disj_hb_decl"], 0.40 * c["prize"]["decl_hb"][p_acc]) for c in c_list]
            dc_w40_nhb = [
                min(c["disj_tot_decl"] - c["disj_hb_decl"], 0.40 * c["prize"]["decl_nhb"][p_acc])
                for c in c_list
            ]
            dc_w40_tot = [a + b for a, b in zip(dc_w40_hb, dc_w40_nhb)]
            nw_w40_hb = [min(c["disj_hb_nw"], 0.40 * c["prize"]["nonwon_hb"][p_acc]) for c in c_list]
            nw_w40_nhb = [
                min(c["disj_tot_nw"] - c["disj_hb_nw"], 0.40 * c["prize"]["nonwon_nhb"][p_acc])
                for c in c_list
            ]
            nw_w40_tot = [a + b for a, b in zip(nw_w40_hb, nw_w40_nhb)]
            print(f"    p = {p_acc:.1f}:")
            print(f"      All non-won (100% quote ceiling):  total={fmt_mr(nw_tot)} | HB={fmt_mr(nw_hb)} | not-HB={fmt_mr(nw_nhb)}")
            print(f"      All non-won (@40% quote win, disj):total={fmt_mr(nw_w40_tot)} | HB={fmt_mr(nw_w40_hb)} | not-HB={fmt_mr(nw_w40_nhb)}")
            print(f"      Declined thin (100% quote ceiling):total={fmt_mr(dc_tot)} | HB={fmt_mr(dc_hb)} | not-HB={fmt_mr(dc_nhb)}")
            print(f"      Declined thin (@40% quote win):    total={fmt_mr(dc_w40_tot)} | HB={fmt_mr(dc_w40_hb)} | not-HB={fmt_mr(dc_w40_nhb)}")
            print(f"      Already-won gigs staffed cheaper:  total={fmt_mr([a+b for a,b in zip(won_hb, won_nhb)])} | HB={fmt_mr(won_hb)} | not-HB={fmt_mr(won_nhb)}")


if __name__ == "__main__":
    main()
