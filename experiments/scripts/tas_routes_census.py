"""Step 1: Offline route census and Champion v5 reveal analysis across the four TAS worlds.

Reads ~/.spread-lab/tas/<seed>/tape.json, ~/.spread-lab/map.json, champion/results/dev-L8.jsonl,
and /home/lab/.gemini/tmp/tas-routes/reveals/reveal-<world>/ (zero server requests, zero slots).
"""
from __future__ import annotations

import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Optional

from spread_lab.env import lab_home
from spread_lab.geo import Geo
from spread_lab.notes import note_flags, parse_note_v2, shift_business_days, window_from_note

HOUR, DAY = 60, 24 * 60
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
TAS_SEEDS = ["dev-12", "dev-01", "dev-08", "dev-07"]
REVEAL_ROOT = Path("/home/lab/.gemini/tmp/tas-routes/reveals")


def load_geo() -> Geo:
    m = json.loads((lab_home() / "map.json").read_text(encoding="utf-8"))
    return Geo(m)


def load_tape(seed: str) -> dict[str, Any]:
    return json.loads((lab_home() / "tas" / seed / "tape.json").read_text(encoding="utf-8"))


def load_champ_rows() -> dict[str, dict[str, Any]]:
    out = {}
    for line in Path("champion/results/dev-L8.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            out[r["seed"]] = r
    return out


def site_next_open(stop_place: dict[str, Any], minute: int, custom_opens: Optional[int] = None, custom_closes: Optional[int] = None) -> Optional[int]:
    """Earliest minute >= `minute` when `stop_place` is open, or None if never open within week."""
    if stop_place.get("privateAddress"):
        w = stop_place.get("window")
        if not w:
            return minute
        if minute <= w["to"]:
            return max(minute, w["from"])
        return None
    hours = stop_place.get("hours")
    t = minute
    for _ in range(14):
        wd = (t // DAY) % 7
        tod = t % DAY
        if wd == 6:
            t = (t // DAY + 1) * DAY
            continue
        if hours is None:
            o = custom_opens if custom_opens is not None else 0
            c = custom_closes if custom_closes is not None else DAY
            if tod < c:
                return max(t, (t // DAY) * DAY + o)
            t = (t // DAY + 1) * DAY
            continue
        if wd == 5:
            sat = hours.get("saturday")
            if sat:
                o = max(sat["opens"], custom_opens) if custom_opens is not None else sat["opens"]
                c = min(sat["closes"], custom_closes) if custom_closes is not None else sat["closes"]
                if o < c and tod < c:
                    return max(t, (t // DAY) * DAY + o)
            t = (t // DAY + 1) * DAY
            continue
        if wd in hours.get("weekdays", [0, 1, 2, 3, 4]):
            o = max(hours["opens"], custom_opens) if custom_opens is not None else hours["opens"]
            c = min(hours["closes"], custom_closes) if custom_closes is not None else hours["closes"]
            if o < c and tod < c:
                return max(t, (t // DAY) * DAY + o)
        t = (t // DAY + 1) * DAY
    return None


class Arc:
    """One candidate (request, option) arc for tour planning."""
    __slots__ = (
        "rid", "option", "arrived_at", "respond_by", "dealer", "batch_id",
        "pickup", "delivery", "drive_min", "road_km", "list_cents", "ref_cents",
        "ready_at", "pickup_to", "deadline", "p_stop", "d_stop",
        "p_opens", "p_closes", "d_opens", "d_closes",
        "premium", "manual", "plates", "charging", "summer_tyres", "unsure", "has_note",
        "private_pickup", "private_delivery", "legs_count",
    )

    def __init__(self, req: dict[str, Any], opt: dict[str, Any], geo: Geo):
        self.rid = req["id"]
        self.option = opt["kind"]
        self.arrived_at = req["arrivedAt"]
        self.respond_by = req["respondBy"]
        self.dealer = req["dealerId"]
        self.batch_id = req.get("batchId", "")
        legs = req["legs"]
        self.legs_count = len(legs)
        p0 = legs[0]["pickup"]
        d0 = legs[-1]["delivery"]
        self.pickup = p0["placeId"]
        self.delivery = d0["placeId"]
        self.p_stop = p0
        self.d_stop = d0
        self.private_pickup = bool(p0.get("privateAddress"))
        self.private_delivery = bool(d0.get("privateAddress"))
        drv = sum(geo.minutes(l["pickup"]["placeId"], l["delivery"]["placeId"]) for l in legs)
        rkm = sum(geo.road_km(l["pickup"]["placeId"], l["delivery"]["placeId"]) for l in legs)
        if len(legs) == 2:
            drv += geo.minutes(legs[0]["delivery"]["placeId"], legs[1]["pickup"]["placeId"])
            rkm += geo.road_km(legs[0]["delivery"]["placeId"], legs[1]["pickup"]["placeId"])
        self.drive_min = drv
        self.road_km = rkm
        self.list_cents = opt["listPriceCents"]
        self.ref_cents = req["referenceFeeCents"]

        note = req.get("note")
        self.has_note = bool(note and note.get("text"))
        pn = parse_note_v2(note, req["arrivedAt"]) if self.has_note else parse_note_v2(None)
        flags = note_flags(note, v2=True)
        self.unsure = pn.unsure
        self.manual = flags.manual
        self.plates = flags.plates
        self.summer_tyres = flags.summer_tyres
        self.premium = any(l["car"]["premium"] for l in legs)
        self.charging = any(
            l["car"]["electric"] and l["car"]["chargePercent"] is not None and l["car"]["chargePercent"] < 30
            and geo.road_km(l["pickup"]["placeId"], l["delivery"]["placeId"]) > 200.0
            for l in legs
        )

        extra_days = 0
        if pn.ready_at is not None:
            extra_days = max(
                (max(0, pn.ready_at // DAY - l["pickup"]["window"]["from"] // DAY) for l in legs if not l["pickup"]["privateAddress"]),
                default=0,
            )
        base_dl = shift_business_days(opt["deadline"], extra_days)
        p_win = window_from_note(
            note, p0["window"], "pickup", v2=True, arrived_at=req["arrivedAt"],
            private_address=self.private_pickup, stated_hours=p0.get("hours"),
        )
        d_base = {"from": d0["window"]["from"], "to": max(d0["window"]["from"], base_dl)}
        d_win = window_from_note(
            note, d_base, "delivery", v2=True, arrived_at=req["arrivedAt"],
            private_address=self.private_delivery, stated_hours=d0.get("hours"),
        )
        self.ready_at = max(req["respondBy"], p_win["from"])
        self.deadline = min(base_dl, d_win["to"])
        self.pickup_to = p_win["to"] if self.private_pickup else min(self.deadline, p_win["to"])
        self.p_opens = pn.pickup_opens
        self.p_closes = pn.pickup_closes
        self.d_opens = pn.delivery_opens
        self.d_closes = pn.delivery_closes


def simulate_tour(
    arcs: list[Arc],
    geo: Geo,
    slack_min: int = 90,
    start_buffer_min: int = 60,
    max_road_min: int = 720,
) -> Optional[dict[str, Any]]:
    """Checks exact rule + time-window + site-hours feasibility of running `arcs` in sequence as one gig.

    Returns schedule dict {post_at, first_pickup_at, last_delivery_at, road_min, deadhead_min, active_min}
    or None if infeasible.
    """
    if len(arcs) > 1:
        road_min = sum(a.drive_min for a in arcs) + sum(geo.minutes(arcs[i].delivery, arcs[i + 1].pickup) for i in range(len(arcs) - 1))
        if road_min > max_road_min:
            return None
    else:
        road_min = arcs[0].drive_min

    post_at = max(a.respond_by for a in arcs)
    t = post_at + start_buffer_min
    first_pickup_at = None
    deadhead_min = 0
    for idx, a in enumerate(arcs):
        if idx > 0:
            dh = geo.minutes(arcs[idx - 1].delivery, a.pickup)
            deadhead_min += dh
            t += dh
        t = max(t, a.ready_at)
        p_time = site_next_open(a.p_stop, t, a.p_opens, a.p_closes)
        if p_time is None or p_time > a.pickup_to:
            return None
        # Also ensure we don't hold an earlier order past its deadline warning (lastPickupAt - 180) before posting!
        if post_at > a.deadline - a.drive_min - 210:
            return None
        if first_pickup_at is None:
            first_pickup_at = p_time
        extra = (30 if a.plates else 0) + (40 if a.charging else 0)
        arr_deliv = p_time + extra + a.drive_min
        if a.private_delivery:
            w = a.d_stop.get("window")
            if w and arr_deliv > w["to"] + 30 - slack_min:
                return None
            d_time = max(arr_deliv, w["from"]) if w else arr_deliv
        else:
            # Must count as delivered before deadline - slack_min; if site closed, delivery counts at next opening
            d_open = site_next_open(a.d_stop, arr_deliv, a.d_opens, a.d_closes)
            if d_open is None or d_open > a.deadline - slack_min:
                return None
            # Driver only waits if stated hours say open while note says closed; otherwise drops car & moves on!
            stated_open = site_next_open(a.d_stop, arr_deliv, None, None)
            if stated_open == arr_deliv and d_open > arr_deliv:
                # Note closed earlier than stated hours: avoid waiting penalty or model wait <= 120
                if d_open - arr_deliv > 60:
                    return None
                d_time = d_open
            else:
                d_time = arr_deliv
        if d_time > a.deadline - slack_min:
            return None
        t = d_time
    assert first_pickup_at is not None
    return {
        "post_at": post_at,
        "first_pickup_at": first_pickup_at,
        "last_delivery_at": t,
        "road_min": road_min,
        "deadhead_min": deadhead_min,
        "span_min": t - first_pickup_at,
    }


def analyze_reveal(seed: str, world_id: str, geo: Geo, tape: dict[str, Any]) -> None:
    rev_dir = REVEAL_ROOT / f"reveal-{world_id}"
    if not rev_dir.exists():
        return
    roster = {d["id"]: d for d in tape["roster"]}
    exp_count = sum(1 for d in roster.values() if d["rating"] >= 4.8 and d["completedGigs"] >= 50)
    man_count = sum(1 for d in roster.values() if d["licence"] == "manual")
    exp_man = sum(1 for d in roster.values() if d["rating"] >= 4.8 and d["completedGigs"] >= 50 and d["licence"] == "manual")

    # Views & bookings per day
    views_by_day: dict[int, set[str]] = defaultdict(set)
    with open(rev_dir / "views.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            d_id = row["driverId"]
            at = int(row["at"])
            views_by_day[at // DAY].add(d_id)

    booked_drivers_by_day: dict[int, set[str]] = defaultdict(set)
    booked_by_town_day: dict[tuple[str, int], set[str]] = defaultdict(set)
    win_ratios_by_day: dict[int, list[float]] = defaultdict(list)
    outage_clues: dict[tuple[int, str], list[int]] = defaultdict(list)

    with open(rev_dir / "events.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            k = row["kind"]
            at = int(row["at"])
            if k == "gig_booked" and row["driverId"]:
                d_id = row["driverId"]
                booked_drivers_by_day[at // DAY].add(d_id)
                home = roster[d_id]["homePlaceId"]
                booked_by_town_day[(home, at // DAY)].add(d_id)

    reqs_by_id = {r["id"]: r for r in tape["requests"]}
    won_ratios_day: dict[int, list[float]] = defaultdict(list)
    lost_ratios_day: dict[int, list[float]] = defaultdict(list)
    won_by_day_place: Counter = Counter()
    quoted_by_day_place: Counter = Counter()
    with open(rev_dir / "requests.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rid = row["id"]
            arr = int(row["arrivedAt"])
            d = arr // DAY
            p_place = reqs_by_id[rid]["legs"][0]["pickup"]["placeId"]
            # Check quoted mult
            best_q = None
            for ok in ("same_day", "next_day", "within_3_days"):
                qc = row.get(f"{ok}.quoteCents")
                lc = row.get(f"{ok}.listPriceCents")
                if qc and lc:
                    r = int(qc) / int(lc)
                    if r < 3.5:
                        best_q = r if best_q is None else min(best_q, r)
            if best_q is not None:
                quoted_by_day_place[(d, p_place)] += 1
                if row["outcome"] == "won":
                    won_ratios_day[d].append(best_q)
                    won_by_day_place[(d, p_place)] += 1
                elif row["outcome"] == "lost":
                    lost_ratios_day[d].append(best_q)

    # Check note parser accuracy on won legs
    note_mismatches = 0
    won_legs_checked = 0
    with open(rev_dir / "legs.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if not row["truth.pickedUpAt"] and not row["truth.manualGearbox"]:
                continue
            won_legs_checked += 1
            req = reqs_by_id[row["requestId"]]
            pn = parse_note_v2(req.get("note"), req["arrivedAt"])
            t_man = row["truth.manualGearbox"] == "true"
            t_plt = row["truth.needsPlates"] == "true"
            if pn.manual != t_man or pn.plates != t_plt:
                note_mismatches += 1

    # Done gigs fee vs road_min
    done_fees = []
    with open(rev_dir / "gigs.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["status"] == "done" and row["feeCents"]:
                stops = json.loads(row["stops"])
                oids = list(dict.fromkeys(s["orderId"] for s in stops))
                ref_sum = sum(reqs_by_id[o]["referenceFeeCents"] for o in oids)
                fee = int(row["feeCents"])
                done_fees.append((len(oids), fee, ref_sum, fee / ref_sum if ref_sum else 0))

    solo_ratios = [x[3] for x in done_fees if x[0] == 1]
    pair_ratios = [x[3] for x in done_fees if x[0] > 1]

    print(f"=== {seed} (world {world_id}) ===")
    print(f"Roster: {len(roster)} total | experienced: {exp_count} ({exp_count/len(roster):.1%}) | manual: {man_count} ({man_count/len(roster):.1%}) | both: {exp_man} ({exp_man/len(roster):.1%})")
    day_str = " | ".join(
        f"{WEEKDAYS[d % 7]}(d{d}): views={len(views_by_day[d])}, booked_drv={len(booked_drivers_by_day[d])}"
        for d in range(8) if views_by_day[d] or booked_drivers_by_day[d]
    )
    print(f"Active drivers by day: {day_str}")
    wr_str = " | ".join(
        f"{WEEKDAYS[d]}: won={len(won_ratios_day[d])}/{len(won_ratios_day[d])+len(lost_ratios_day[d])} "
        f"({len(won_ratios_day[d])/max(1, len(won_ratios_day[d])+len(lost_ratios_day[d])):.0%})"
        for d in range(5)
    )
    print(f"Champ quote win rate by day (price-war / outage detector): {wr_str}")
    print(f"Done gigs: {len(solo_ratios)} solo (mean fee/ref = {sum(solo_ratios)/max(1,len(solo_ratios)):.3f}), "
          f"{len(pair_ratios)} multi-car (mean fee/ref = {sum(pair_ratios)/max(1,len(pair_ratios)):.3f}), "
          f"note flag mismatches on {won_legs_checked} legs: {note_mismatches}")


def run_census(seed: str, geo: Geo, tape: dict[str, Any]) -> dict[str, Any]:
    reqs = tape["requests"]
    roster = tape["roster"]
    supply30 = geo.supply(roster, 30.0)
    homes = Counter(d["homePlaceId"] for d in roster)

    # Identify bulk batches
    batches = Counter(r.get("batchId", "") for r in reqs if r.get("batchId"))
    bulk_batches = [(b, n) for b, n in batches.items() if n >= 15]

    # Build best-flexibility clean single-leg arcs + all option arcs
    arcs_by_rid: dict[str, list[Arc]] = {}
    unsure_rids = set()
    tradein_rids = set()
    for r in reqs:
        if len(r["legs"]) > 1:
            tradein_rids.add(r["id"])
        opts = [Arc(r, o, geo) for o in r["options"]]
        if any(a.unsure for a in opts):
            unsure_rids.add(r["id"])
        arcs_by_rid[r["id"]] = opts

    # Pick slowest feasible option per clean single-leg request for maximum tour connectivity census
    slow_arcs: list[Arc] = []
    for r in reqs:
        rid = r["id"]
        if rid in unsure_rids or rid in tradein_rids:
            continue
        valid = [a for a in arcs_by_rid[rid] if a.deadline - a.ready_at - a.drive_min >= 90]
        if valid:
            # Prefer slowest option (largest deadline) to maximize tour window overlap
            valid.sort(key=lambda a: (a.deadline, -a.list_cents), reverse=True)
            slow_arcs.append(valid[0])

    # Index slow_arcs by pickup place and by near-pickup
    by_place: dict[str, list[Arc]] = defaultdict(list)
    for a in slow_arcs:
        by_place[a.pickup].append(a)

    # 1. Count feasible ordered pairs (a -> b) with deadhead <= 35 km (straight line) and <= 45 road min
    next_edges: dict[str, list[tuple[Arc, dict[str, Any]]]] = defaultdict(list)
    exact_round_trips = 0      # p_a == d_b and d_a == p_b (within 30km)
    closed_pairs_near_drivers = 0  # supply30[p_a] >= 10 and line_km(d_b, p_a) <= 30
    open_homeward_pairs = 0    # supply30[p_a] >= 10 and supply30[d_b] >= 50 and line_km(d_b, p_a) > 30
    rids_in_closed_pair: set[str] = set()
    rids_in_any_pair: set[str] = set()

    arc_map = {a.rid: a for a in slow_arcs}
    for a in slow_arcs:
        near_b_places = [p for p in geo.places if geo.line_km(a.delivery, p) <= 35.0 and geo.minutes(a.delivery, p) <= 45]
        for pb in near_b_places:
            for b in by_place[pb]:
                if b.rid == a.rid:
                    continue
                # Quick time prune before full simulation
                if b.pickup_to < a.ready_at + a.drive_min:
                    continue
                if a.ready_at > b.deadline - b.drive_min - 90:
                    continue
                sim = simulate_tour([a, b], geo)
                if sim is None:
                    continue
                next_edges[a.rid].append((b, sim))
                rids_in_any_pair.add(a.rid)
                rids_in_any_pair.add(b.rid)
                closes = geo.line_km(b.delivery, a.pickup) <= 30.0
                if closes:
                    exact_round_trips += 1
                    if supply30[a.pickup] > 0:
                        closed_pairs_near_drivers += 1
                        rids_in_closed_pair.add(a.rid)
                        rids_in_closed_pair.add(b.rid)
                elif supply30[a.pickup] > 0 and supply30[b.delivery] >= 50:
                    open_homeward_pairs += 1

    # 2. Count triangles (a -> b -> c with c.delivery within 30 km of a.pickup) and 3-car shuttles (A->B->A->B or A->B->C)
    triangles = 0
    shuttles_3 = 0
    closed_4 = 0
    rids_in_3plus_closed: set[str] = set()
    sample_tours_3_4: list[tuple[float, list[Arc], dict[str, Any]]] = []

    for a in slow_arcs:
        if supply30[a.pickup] == 0:
            continue
        # Keep top 25 outgoing edges by shortest deadhead + slack to keep 3/4-tour search fast & exact
        edges_a = sorted(next_edges[a.rid], key=lambda x: (x[1]["deadhead_min"], x[0].ready_at))[:25]
        for b, _ in edges_a:
            edges_b = sorted(next_edges[b.rid], key=lambda x: (x[1]["deadhead_min"], x[0].ready_at))[:20]
            for c, _ in edges_b:
                if c.rid in (a.rid, b.rid):
                    continue
                sim3 = simulate_tour([a, b, c], geo)
                if sim3 is None:
                    continue
                if geo.line_km(c.delivery, a.pickup) <= 30.0:
                    triangles += 1
                    rids_in_3plus_closed.update((a.rid, b.rid, c.rid))
                    val = (a.list_cents + b.list_cents + c.list_cents) * 1.40 / 100.0
                    sample_tours_3_4.append((val / (sim3["road_min"] / 60.0), [a, b, c], sim3))
                elif geo.line_km(a.pickup, c.pickup) <= 30.0 and geo.line_km(a.delivery, c.delivery) <= 30.0:
                    shuttles_3 += 1
                # Try closing at 4 cars (e.g. shuttle A->B->A->B or 4-cycle A->B->C->D->A)
                if sim3["road_min"] <= 600:
                    edges_c = sorted(next_edges[c.rid], key=lambda x: (x[1]["deadhead_min"], x[0].ready_at))[:12]
                    for d, _ in edges_c:
                        if d.rid in (a.rid, b.rid, c.rid):
                            continue
                        if geo.line_km(d.delivery, a.pickup) <= 30.0:
                            sim4 = simulate_tour([a, b, c, d], geo)
                            if sim4 is not None:
                                closed_4 += 1
                                rids_in_3plus_closed.update((a.rid, b.rid, c.rid, d.rid))
                                val4 = (a.list_cents + b.list_cents + c.list_cents + d.list_cents) * 1.40 / 100.0
                                sample_tours_3_4.append((val4 / (sim4["road_min"] / 60.0), [a, b, c, d], sim4))

    # 3. Greedy maximum disjoint packing of closed tours (2, 3, 4 cars) starting & ending within 30 km of drivers
    candidate_closed_tours: list[tuple[float, list[Arc], dict[str, Any]]] = list(sample_tours_3_4)
    for a in slow_arcs:
        if supply30[a.pickup] == 0:
            continue
        for b, sim2 in next_edges[a.rid]:
            if geo.line_km(b.delivery, a.pickup) <= 30.0:
                val2 = (a.list_cents + b.list_cents) * 1.40 / 100.0
                candidate_closed_tours.append((val2 / max(0.5, sim2["road_min"] / 60.0), [a, b], sim2))

    # Score by estimated margin per road hour: 1.40*list - 42 €/h * road_hours
    scored_tours = []
    for _, t_arcs, sim in candidate_closed_tours:
        est_rev = sum(x.list_cents for x in t_arcs) * 1.40 / 100.0
        est_cost = 42.0 * (sim["road_min"] / 60.0)
        est_profit = est_rev - est_cost
        scored_tours.append((est_profit / max(0.5, sim["road_min"] / 60.0), est_profit, t_arcs, sim))
    scored_tours.sort(key=lambda x: x[0], reverse=True)

    used_rids: set[str] = set()
    packed_tours: list[tuple[float, list[Arc], dict[str, Any]]] = []
    by_day_packed: Counter = Counter()
    by_town_packed: Counter = Counter()
    for _, prof, t_arcs, sim in scored_tours:
        if prof <= 0 or any(x.rid in used_rids for x in t_arcs):
            continue
        used_rids.update(x.rid for x in t_arcs)
        packed_tours.append((prof, t_arcs, sim))
        d = sim["first_pickup_at"] // DAY
        by_day_packed[d] += len(t_arcs)
        by_town_packed[t_arcs[0].pickup] += len(t_arcs)

    print(f"--- CENSUS: {seed} ---")
    print(f"Total requests: {len(reqs)} | trade-ins: {len(tradein_rids)} | unsure notes: {len(unsure_rids)} | clean 1-leg arcs: {len(slow_arcs)}")
    if bulk_batches:
        for b_id, cnt in bulk_batches:
            b_reqs = [r for r in reqs if r.get("batchId") == b_id]
            p_c = Counter(r["legs"][0]["pickup"]["placeId"] for r in b_reqs)
            d_c = Counter(r["legs"][-1]["delivery"]["placeId"] for r in b_reqs)
            arr0 = b_reqs[0]["arrivedAt"]
            print(f"Bulk batch {b_id}: {cnt} cars at {WEEKDAYS[arr0//DAY]} {(arr0%DAY)//60:02d}:{arr0%60:02d}, pickup={dict(p_c)}, top deliveries={d_c.most_common(5)}")
    print(f"Ordered feasible pairs (deadhead<=35km, <=12h): {sum(len(v) for v in next_edges.values())}")
    print(f"  Closed 2-car round trips near drivers: {closed_pairs_near_drivers} (covering {len(rids_in_closed_pair)} distinct requests)")
    print(f"  Open 2-car chains ending in >=50-driver hub: {open_homeward_pairs}")
    print(f"  Closed 3-car triangles/tours: {triangles} | 3-car shuttles: {shuttles_3} | Closed 4-car tours: {closed_4}")
    rids_union_closed = rids_in_closed_pair | rids_in_3plus_closed
    print(f"  Total requests fitting in >=1 closed tour (2+ cars, start/end <=30km of drivers): {len(rids_union_closed)} / {len(reqs)} ({len(rids_union_closed)/len(reqs):.1%})")
    len_dist = Counter(len(t[1]) for t in packed_tours)
    print(f"Disjoint closed-tour packing (uncapped drivers): {len(packed_tours)} tours ({dict(sorted(len_dist.items()))}) covering {len(used_rids)} cars, est profit €{sum(t[0] for t in packed_tours):,.0f}")
    print(f"  Packed cars by pickup day: " + ", ".join(f"{WEEKDAYS[d%7]}(d{d}): {n}" for d, n in sorted(by_day_packed.items())))
    print(f"  Packed cars top start towns: {by_town_packed.most_common(8)}")

    # Top towns driver supply
    top_supply = sorted(((homes[p], supply30[p], p) for p in geo.places if homes[p] > 0 or supply30[p] > 0), reverse=True)
    print(f"  Top driver towns (home, <=30km): {[(p, h, s) for h, s, p in top_supply[:10]]}")
    print(f"  Thin/zero towns (<=30km supply < 15): {[(p, homes[p], supply30[p]) for p in sorted(geo.places) if supply30[p] < 15]}")
    return {"reqs": reqs, "slow_arcs": slow_arcs}


def cross_world_return_rates(geo: Geo, tapes: dict[str, dict[str, Any]]) -> None:
    """Step 5 preview: across the 4 tapes, after an A->B request arrives, how often does a B'->A' (<=30km)
    return request arrive within 3h, 6h, or 24h?"""
    lane_counts: Counter = Counter()
    ret_3h: Counter = Counter()
    ret_6h: Counter = Counter()
    ret_24h: Counter = Counter()

    for seed, tape in tapes.items():
        reqs = tape["requests"]
        for i, r1 in enumerate(reqs):
            if len(r1["legs"]) != 1:
                continue
            a = r1["legs"][0]["pickup"]["placeId"]
            b = r1["legs"][0]["delivery"]["placeId"]
            t1 = r1["arrivedAt"]
            lane_counts[(a, b)] += 1
            found3 = found6 = found24 = False
            for r2 in reqs:
                t2 = r2["arrivedAt"]
                if t2 < t1 or t2 > t1 + 24 * HOUR or r2["id"] == r1["id"] or len(r2["legs"]) != 1:
                    continue
                p2 = r2["legs"][0]["pickup"]["placeId"]
                d2 = r2["legs"][0]["delivery"]["placeId"]
                if geo.line_km(b, p2) <= 30.0 and geo.line_km(a, d2) <= 30.0:
                    dt = t2 - t1
                    if dt <= 3 * HOUR:
                        found3 = True
                    if dt <= 6 * HOUR:
                        found6 = True
                    found24 = True
                    if found3:
                        break
            if found3:
                ret_3h[(a, b)] += 1
            if found6:
                ret_6h[(a, b)] += 1
            if found24:
                ret_24h[(a, b)] += 1

    print("=== CROSS-WORLD LANE RETURN PROBABILITY (4 tapes = ~4,142 requests) ===")
    print(f"{'Lane (A -> B)':<30} {'N/4wk':>6} {'P(<=3h)':>8} {'P(<=6h)':>8} {'P(<=24h)':>9} {'drive_min':>9}")
    for (a, b), n in lane_counts.most_common(30):
        print(f"{a + ' -> ' + b:<30} {n:>6} {ret_3h[(a,b)]/n:>7.0%} {ret_6h[(a,b)]/n:>7.0%} {ret_24h[(a,b)]/n:>8.0%} {geo.minutes(a,b):>9}")


def main() -> None:
    geo = load_geo()
    champ = load_champ_rows()
    tapes = {s: load_tape(s) for s in TAS_SEEDS}
    for s in TAS_SEEDS:
        analyze_reveal(s, champ[s]["world"], geo, tapes[s])
        run_census(s, geo, tapes[s])
    cross_world_return_rates(geo, tapes)


if __name__ == "__main__":
    main()
