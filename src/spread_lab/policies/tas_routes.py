"""TAS Routes dispatcher (`spread_lab.policies.tas_routes:Desk`).

Executes planned multi-car tours (`tour_plan_file`) built with full-week foresight, with:
  1. Safe holding (`tour_waiting`) until all cars of a planned tour are won (or hold guard triggers).
  2. Piecewise-flat stepped tour fee schedules calibrated to fork-bisected reservation fees (~€10-12/wheel h
     or 0.35x-0.55x sum(ref) on closed tours), teaching zero holdout expectation when booked flat.
  3. Opportunistic live closed-tour salvage/pairing (`tour_dynamic`) when a planned tour leg loses, cancels,
     or changes, or when replaying an existing quote book without a pre-computed tour file.
  4. Relay direct offers (`relay_offers`) to working drivers about to finish an earlier gig near a pickup
     that heads back toward their home town (bypassing the 12-hour single-gig cap).
  5. Complete rule-safe fallbacks on `order_lost`, `order_cancelled` (open withdrawn vs booked shortened),
     `order_changed`, `gig_dropped`, `no_show`, `gig_expired`, `deadline_close`, and `rejoin`.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from spread.client import World
from spread.types import Action, ActionResult, Audience, DeskEvent, DeskSnapshot, DriverProfile, FeeStep, Order, PostAction, StopRef

from ..geo import Geo
from ..notes import note_flags, parse_note_v2
from ..policy import (
    DAY,
    HOUR,
    Desk as BaseDesk,
    Params as BaseParams,
    Retry,
    clamp,
    current_schedule_fee,
    daytime_minutes_between,
    order_ids_of,
    pickups,
    site_open_at,
    stops_for,
    undelivered,
    without_windows,
)


@dataclass
class Params(BaseParams):
    # --- planned & dynamic multi-car tour staffing ---------------------------------------------------
    tour_plan_file: str = ""            # path to JSON tour plan {"tours": [{"id": ..., "rids": [...], ...}]}
    tour_dynamic: bool = False          # salvage broken tour legs & pair unbooked solo legs into closed tours
    tour_max_cars: int = 4              # max cars per dynamically formed closed tour (2..4)
    tour_close_km: float = 30.0         # max straight-line km from last delivery to first pickup for closed tour
    tour_deadhead_km: float = 30.0      # max straight-line km between car i delivery and car i+1 pickup
    tour_max_road_min: int = 700        # <= 720 rule limit with safety margin
    tour_min_slack_min: int = 90        # delivery slack before each order's deadline in simulated tour
    tour_hold_guard_min: int = 300      # release held tour cars if lastPickupAt - now <= this (5h before last pickup)
    tour_split_guard_min: int = 330     # split unbooked multi-car tour into solos if lastPickupAt - now <= this (5.5h)
    tour_max_wait_min: int = 110        # split unbooked multi-car tour after this many daytime minutes
    # --- tour fee schedule (calibrated from Step 2 fork bisection on dev-12) -------------------------
    tour_flat_mode: bool = True         # post flat fee first and step up discretely so flat bookings teach 0 wait
    tour_closed_mult_2: float = 0.58    # opening multiple of sum(ref) for 2-car closed tour
    tour_closed_mult_3: float = 0.52    # opening multiple of sum(ref) for 3+-car closed tour
    tour_open_mult: float = 0.72        # opening multiple of sum(ref) for open homeward chain
    tour_eur_per_road_h: float = 14.0   # floor €/road-hour on closed tour opening fee (~1.3x €10.5 min reserve)
    tour_car_fixed_eur: float = 6.5     # fixed € per car added to road-hour floor
    tour_step_interval_min: int = 50    # daytime minutes before stepping up an unbooked flat tour gig
    tour_step_bump: float = 0.12        # multiple of sum(ref) added at discrete flat step before split
    tour_max_mult: float = 0.90         # cap on multi-car tour multiple before splitting to solo
    # --- relay direct offers to finishing drivers (own idea: >12h chains across gigs) ----------------
    relay_offers: bool = False          # send direct offers on open gigs to drivers finishing a gig nearby
    relay_radius_km: float = 30.0       # max km between driver's finishing delivery and next gig's first pickup
    relay_home_km: float = 35.0         # max km between next gig's last delivery and driver's homePlaceId
    relay_offer_mult: float = 0.62      # direct offer fee multiple of sum(ref) for homeward relay leg


class Desk(BaseDesk):
    Params = Params

    def __init__(self, world: World, params: Params, level: int, geo: Geo, roster: list[DriverProfile], now: int):
        super().__init__(world, params, level, geo, roster, now)
        self.planned_tours: dict[str, dict[str, Any]] = {}   # tour_id -> tour spec dict
        self.rid_to_tour: dict[str, str] = {}                # order/request id -> tour_id
        self.broken_tours: set[str] = set()                  # tour_ids that can no longer run as planned
        self.posted_tours: set[str] = set()                  # tour_ids already posted
        self.tour_waiting: set[str] = set()                  # won order_ids held waiting for rest of planned tour
        self.tour_gigs: dict[str, dict[str, Any]] = {}       # gig_id -> {"posted_at": int, "last_step_at": int, "mult": float, "closed": bool, "tid": str}
        self._pending_tour_meta: dict[tuple[str, ...], dict[str, Any]] = {}
        self.gig_est_finish: dict[str, tuple[int, str]] = {} # booked gig_id -> (est_finish_min, last_delivery_place)
        self._load_tour_plan()
        if self.planned_tours:
            self.p.lead_car = False

    def _load_tour_plan(self) -> None:
        path_str = self.p.tour_plan_file
        if not path_str:
            return
        path = Path(path_str)
        if not path.exists():
            raise FileNotFoundError(f"tour_plan_file not found: {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        for idx, t in enumerate(data.get("tours", [])):
            tid = str(t.get("id", f"T{idx:04d}"))
            rids = list(t["rids"])
            if len(rids) < 2:
                continue
            self.planned_tours[tid] = {**t, "id": tid, "rids": rids}
            for rid in rids:
                self.rid_to_tour[rid] = tid

    # --- exact live tour feasibility check ------------------------------------------------------------
    def _site_next_open_live(self, stop_place: dict[str, Any], minute: int, c_open: Optional[int] = None, c_close: Optional[int] = None) -> Optional[int]:
        if stop_place.get("privateAddress"):
            w = stop_place.get("window")
            if not w:
                return minute
            return max(minute, w["from"]) if minute <= w["to"] else None
        hours = stop_place.get("hours")
        t = minute
        for _ in range(14):
            wd = (t // DAY) % 7
            tod = t % DAY
            if wd == 6:
                t = (t // DAY + 1) * DAY
                continue
            if hours is None:
                o = c_open if c_open is not None else 0
                c = c_close if c_close is not None else DAY
                if tod < c:
                    return max(t, (t // DAY) * DAY + o)
                t = (t // DAY + 1) * DAY
                continue
            if wd == 5:
                sat = hours.get("saturday")
                if sat:
                    o = max(sat["opens"], c_open) if c_open is not None else sat["opens"]
                    c = min(sat["closes"], c_close) if c_close is not None else sat["closes"]
                    if o < c and tod < c:
                        return max(t, (t // DAY) * DAY + o)
                t = (t // DAY + 1) * DAY
                continue
            if wd in hours.get("weekdays", [0, 1, 2, 3, 4]):
                o = max(hours["opens"], c_open) if c_open is not None else hours["opens"]
                c = min(hours["closes"], c_close) if c_close is not None else hours["closes"]
                if o < c and tod < c:
                    return max(t, (t // DAY) * DAY + o)
            t = (t // DAY + 1) * DAY
        return None

    def can_chain_orders_live(self, oids: list[str], slack_override: Optional[int] = None) -> Optional[dict[str, Any]]:
        """Verifies whether won `oids` can be posted right now (`self.now`) as a single multi-car gig."""
        if len(oids) < 2:
            return None
        orders = []
        for oid in oids:
            o = self.orders.get(oid)
            if o is None or len(o["legs"]) != 1 or undelivered(o) != [0] or oid in self.lost:
                return None
            req = self.requests.get(oid)
            if req is None:
                return None
            if req.get("note") and parse_note_v2(req["note"], req["arrivedAt"]).unsure:
                return None
            orders.append(o)

        road_min = sum(self.geo.minutes(o["legs"][0]["pickup"]["placeId"], o["legs"][0]["delivery"]["placeId"]) for o in orders)
        road_min += sum(
            self.geo.minutes(orders[i]["legs"][0]["delivery"]["placeId"], orders[i + 1]["legs"][0]["pickup"]["placeId"])
            for i in range(len(orders) - 1)
        )
        if road_min > min(720, self.p.tour_max_road_min):
            return None

        slack = slack_override if slack_override is not None else self.p.tour_min_slack_min
        t = self.now + 30
        first_pick = None
        for idx, o in enumerate(orders):
            leg0 = o["legs"][0]
            req = self.requests[o["id"]]
            note = req.get("note")
            pn = parse_note_v2(note, req["arrivedAt"]) if note else parse_note_v2(None)
            flags = note_flags(note, v2=True)
            if idx > 0:
                t += self.geo.minutes(orders[idx - 1]["legs"][0]["delivery"]["placeId"], leg0["pickup"]["placeId"])
            p_from = leg0["pickup"]["window"]["from"]
            if pn.ready_at is not None and not leg0["pickup"]["privateAddress"]:
                p_from = max(p_from, pn.ready_at)
            if pn.released_at is not None:
                p_from = max(p_from, pn.released_at)
            t = max(t, p_from)
            p_time = self._site_next_open_live(leg0["pickup"], t, pn.pickup_opens, pn.pickup_closes)
            p_to = leg0["pickup"]["window"]["to"] if leg0["pickup"]["privateAddress"] else min(o["deadline"], leg0["pickup"]["window"]["to"])
            if p_time is None or p_time > p_to:
                return None
            if first_pick is None:
                first_pick = p_time
            car = leg0["car"]
            low_bat = car["electric"] and car["chargePercent"] is not None and car["chargePercent"] < 30 and self.geo.road_km(leg0["pickup"]["placeId"], leg0["delivery"]["placeId"]) > self.p.charge_min_km
            extra = (30 if flags.plates else 0) + (40 if low_bat else 0)
            arr_d = p_time + extra + self.geo.minutes(leg0["pickup"]["placeId"], leg0["delivery"]["placeId"])
            if leg0["delivery"]["privateAddress"]:
                w = leg0["delivery"].get("window")
                if w and arr_d > w["to"] + 30 - slack:
                    return None
                d_time = max(arr_d, w["from"]) if w else arr_d
            else:
                eff_dl = min(o["deadline"], pn.note_deadline) if pn.note_deadline is not None else o["deadline"]
                d_open = self._site_next_open_live(leg0["delivery"], arr_d, pn.delivery_opens, pn.delivery_closes)
                if d_open is None or d_open > eff_dl - slack:
                    return None
                stated_open = self._site_next_open_live(leg0["delivery"], arr_d, None, None)
                if stated_open == arr_d and d_open > arr_d:
                    if d_open - arr_d > 60:
                        return None
                    d_time = d_open
                else:
                    d_time = arr_d
                if d_time > eff_dl - slack:
                    return None
            t = d_time

        p0 = orders[0]["legs"][0]["pickup"]["placeId"]
        dk = orders[-1]["legs"][0]["delivery"]["placeId"]
        closed = self.geo.line_km(dk, p0) <= self.p.tour_close_km
        return {"road_min": road_min, "closed": closed, "finish_at": t, "last_place": dk}

    # --- fee computation for tours --------------------------------------------------------------------
    def tour_open_mult(self, oids: list[str], road_min: int, closed: bool, spec: Optional[dict[str, Any]] = None) -> float:
        ref_sum = sum(self.requests[oid]["referenceFeeCents"] for oid in oids if oid in self.requests)
        if ref_sum <= 0:
            return self.p.fee_open
        if spec and spec.get("fee_open_mult"):
            base_mult = float(spec["fee_open_mult"])
        elif closed:
            base_mult = self.p.tour_closed_mult_3 if len(oids) >= 3 else self.p.tour_closed_mult_2
        else:
            base_mult = self.p.tour_open_mult

        if closed:
            floor_cents = (self.p.tour_eur_per_road_h * (road_min / 60.0) + self.p.tour_car_fixed_eur * len(oids)) * 100.0
            base_mult = max(base_mult, floor_cents / ref_sum)

        # Slightly higher opening multiple in smaller regional pools (< 60 drivers within 30 km)
        p0 = self.orders[oids[0]]["legs"][0]["pickup"]["placeId"]
        sup = self.supply.get(p0, 0)
        if sup < 35:
            base_mult += 0.10
        elif sup < 80:
            base_mult += 0.05
        if any(any(l["car"]["premium"] for l in self.orders[oid]["legs"]) for oid in oids):
            base_mult += 0.06  # smaller experienced driver sub-pool (~7-9% of roster)
        return clamp(base_mult, 0.35, self.p.tour_max_mult)

    def pair_base_cents(self, oids: list[str]) -> float:
        raw = sum(self.requests[oid]["referenceFeeCents"] for oid in oids if oid in self.requests)
        if len(oids) >= 2 and oids[0] in self.orders and oids[-1] in self.orders:
            p0 = self.orders[oids[0]]["legs"][0]["pickup"]["placeId"]
            dk = self.orders[oids[-1]]["legs"][-1]["delivery"]["placeId"]
            if self.geo.line_km(dk, p0) <= self.p.tour_close_km:
                return raw * (0.65 if len(oids) >= 3 else 0.72)
        return super().pair_base_cents(oids)

    def build_tour_schedule(self, oids: list[str], mult: float) -> list[FeeStep]:
        ref_sum = sum(self.requests[oid]["referenceFeeCents"] for oid in oids if oid in self.requests)
        if self.p.tour_flat_mode:
            return [{"at": self.now, "feeCents": max(100, int(ref_sum * mult + 0.5))}]
        until = min(self.orders[oid]["lastPickupAt"] for oid in oids) - 3 * HOUR
        return self.rising(ref_sum, until, fee_open_override=mult, fee_warn_override=max(mult, self.p.tour_max_mult))

    def post_tour_orders(self, oids: list[str], tid: str = "", spec: Optional[dict[str, Any]] = None) -> bool:
        info = self.can_chain_orders_live(oids)
        if info is None:
            return False
        stops: list[StopRef] = []
        exp = False
        man = False
        for oid in oids:
            o = self.orders[oid]
            req = self.requests[oid]
            flags = note_flags(req["note"], v2=True)
            exp = exp or any(l["car"]["premium"] for l in o["legs"])
            man = man or flags.manual
            retry = Retry(plates=flags.plates)
            s = without_windows(stops_for(o, [0], req["note"], retry, self.geo, self.p.charge_min_km, True, req["arrivedAt"]), self.now)
            stops.extend(s)
        mult = self.tour_open_mult(oids, info["road_min"], info["closed"], spec=spec)
        sched = self.build_tour_schedule(oids, mult)
        action: PostAction = {
            "type": "post",
            "stops": stops,
            "audience": {"experienced": exp, "manualLicence": man},
            "schedule": sched,
        }
        for oid in oids:
            self.tour_waiting.discard(oid)
        self.outbox.append(action)
        self.stats["posts"] += 1
        self._pending_tour_meta[tuple(oids)] = {
            "posted_at": self.now,
            "last_step_at": self.now,
            "mult": mult,
            "closed": info["closed"],
            "road_min": info["road_min"],
            "finish_at": info["finish_at"],
            "last_place": info["last_place"],
            "tid": tid,
            "n_cars": len(oids),
        }
        if tid:
            self.posted_tours.add(tid)
        return True

    # --- salvage & dynamic closed-tour pairing --------------------------------------------------------
    def _release_waiting_orders(self, oids: list[str]) -> None:
        """Releases held orders from a broken planned tour: first tries closed sub-tours among them, then solo/dynamic."""
        rem = [oid for oid in oids if oid in self.orders and undelivered(self.orders[oid]) and not self.gigs_of(oid)]
        for oid in rem:
            self.tour_waiting.discard(oid)
        if len(rem) >= 2:
            # Try remaining legs in order if >= 2 still form a valid closed/homeward tour
            info = self.can_chain_orders_live(rem)
            if info and (info["closed"] or self.supply.get(info["last_place"], 0) >= 80):
                if self.post_tour_orders(rem, tid="salvage"):
                    self.stats["tour_salvaged"] += 1
                    return
            # Try all 2-car pairs among rem
            for i in range(len(rem)):
                for j in range(len(rem)):
                    if i == j:
                        continue
                    pair = [rem[i], rem[j]]
                    info2 = self.can_chain_orders_live(pair)
                    if info2 and info2["closed"]:
                        if self.post_tour_orders(pair, tid="salvage2"):
                            self.stats["tour_salvaged"] += 1
                            others = [x for x in rem if x not in pair]
                            for x in others:
                                self._post_single_or_dynamic(self.orders[x])
                            return
        for oid in rem:
            self._post_single_or_dynamic(self.orders[oid])

    def _try_dynamic_closed_tour(self, order: Order) -> bool:
        """Attempts to combine `order` with 1 or 2 existing open unbooked solo/2-car gigs into a closed tour."""
        if not self.p.tour_dynamic or self.level < 3:
            return False
        oid = order["id"]
        if len(order["legs"]) != 1 or undelivered(order) != [0] or oid in self.urgent or oid in self.lost:
            return False
        req = self.requests.get(oid)
        if req is None or (req.get("note") and parse_note_v2(req["note"], req["arrivedAt"]).unsure):
            return False

        # Flush any pending solo posts in outbox only when no quotes are waiting in outbox
        if any(a["type"] == "post" for a in self.outbox) and not any(a["type"] == "quote" for a in self.outbox):
            self.send()

        best: Optional[tuple[float, str, list[str]]] = None
        for gid, post in list(self.posts.items()):
            if gid in self.booked:
                continue
            existing_oids = order_ids_of(post)
            if not existing_oids or len(existing_oids) >= self.p.tour_max_cars:
                continue
            if oid in existing_oids:
                continue
            # Do not cannibalize an intact planned tour gig unless dynamic extension closes an open gig
            if gid in self.tour_gigs and self.tour_gigs[gid].get("tid", "").startswith("T") and self.tour_gigs[gid].get("closed"):
                continue
            if not all(x in self.orders and self.leg_gigs.get(x, {}).get(0) == gid and x not in self.urgent and x not in self.lost for x in existing_oids):
                continue

            for cand_oids in ([*existing_oids, oid], [oid, *existing_oids]):
                p0 = self.orders[cand_oids[0]]["legs"][0]["pickup"]["placeId"]
                if self.supply.get(p0, 0) < 15:
                    continue
                # Check intermediate deadheads <= tour_deadhead_km
                ok_dh = True
                for k in range(len(cand_oids) - 1):
                    da = self.orders[cand_oids[k]]["legs"][0]["delivery"]["placeId"]
                    pb = self.orders[cand_oids[k + 1]]["legs"][0]["pickup"]["placeId"]
                    if self.geo.line_km(da, pb) > self.p.tour_deadhead_km:
                        ok_dh = False
                        break
                if not ok_dh:
                    continue
                dk = self.orders[cand_oids[-1]]["legs"][0]["delivery"]["placeId"]
                if self.geo.line_km(dk, p0) > self.p.tour_close_km:
                    continue
                min_lp = min(self.orders[x]["lastPickupAt"] for x in cand_oids)
                if min_lp - self.now <= self.p.tour_split_guard_min + 120:
                    continue
                info = self.can_chain_orders_live(cand_oids, slack_override=max(180, self.p.tour_min_slack_min))
                if info is None or not info["closed"]:
                    continue
                ref_sum = sum(self.requests[x]["referenceFeeCents"] for x in cand_oids)
                est_saving = ref_sum * 0.40 - 20.0 * info["road_min"] / 60.0
                if best is None or est_saving > best[0]:
                    best = (est_saving, gid, cand_oids)

        if best is None:
            return False
        _, old_gid, cand_oids = best
        old_oids = order_ids_of(self.posts[old_gid])
        self.tour_gigs.pop(old_gid, None)
        self.chain_pairs.pop(old_gid, None)
        for x in old_oids:
            self.leg_gigs.get(x, {}).pop(0, None)
        self.outbox.append({"type": "withdraw", "gigId": old_gid})
        if self.post_tour_orders(cand_oids, tid="dyn"):
            self.stats["tour_dynamic_paired"] += 1
            return True
        # Fallback if refused
        for x in old_oids:
            if x in self.orders and undelivered(self.orders[x]):
                super().post(self.orders[x], undelivered(self.orders[x]), Retry(), allow_pair=False)
        return False

    def _post_single_or_dynamic(self, order: Order) -> None:
        if self._try_dynamic_closed_tour(order):
            return
        super().post(order, undelivered(order))

    def _check_planned_tour(self, tid: str) -> None:
        if tid in self.broken_tours or tid in self.posted_tours:
            return
        spec = self.planned_tours.get(tid)
        if not spec:
            return
        rids = spec["rids"]
        # Break immediately if any leg lost, was declined, or cancelled
        for rid in rids:
            if rid in self.lost_requests:
                self.broken_tours.add(tid)
                self.stats["tour_broken_lost_quote"] += 1
                self._release_waiting_orders([x for x in rids if x in self.tour_waiting])
                return
            if rid in self.requests and rid not in self.orders and self.now > self.requests[rid]["respondBy"] + 1:
                self.broken_tours.add(tid)
                self.stats["tour_broken_unwon"] += 1
                self._release_waiting_orders([x for x in rids if x in self.tour_waiting])
                return
            if rid in self.orders and (len(self.orders[rid]["legs"]) != 1 or not undelivered(self.orders[rid])):
                self.broken_tours.add(tid)
                self.stats["tour_broken_legs"] += 1
                self._release_waiting_orders([x for x in rids if x in self.tour_waiting])
                return

        if all(rid in self.orders for rid in rids):
            if self.post_tour_orders(rids, tid=tid, spec=spec):
                return
            self.broken_tours.add(tid)
            self.stats["tour_broken_infeasible_on_win"] += 1
            self._release_waiting_orders(rids)

    # --- overridden Desk lifecycle hooks --------------------------------------------------------------
    def handle(self, event: DeskEvent) -> None:
        kind = event["kind"]
        if kind == "order_cancelled":
            oid = event["orderId"]
            self.orders.pop(oid, None)
            self.deferred_orders.pop(oid, None)
            was_waiting = oid in self.tour_waiting
            self.tour_waiting.discard(oid)
            tid = self.rid_to_tour.get(oid)
            if tid and tid not in self.broken_tours and tid not in self.posted_tours:
                self.broken_tours.add(tid)
                self.stats["tour_broken_cancelled"] += 1
                self._release_waiting_orders([x for x in self.planned_tours[tid]["rids"] if x != oid and x in self.tour_waiting])
            # Check any live gigs holding oid: if open, server withdrew the gig so we must repost its other orders!
            # If booked ('shortened' or 'continues'), the booked driver keeps and delivers the other orders!
            self.send_post_of(oid)
            for gid in list(self.gigs_of(oid)):
                post = self.posts.get(gid)
                if gid in self.booked:
                    self.leg_gigs.get(oid, {}).pop(0, None)
                else:
                    self.tour_gigs.pop(gid, None)
                    self.chain_pairs.pop(gid, None)
                    if post:
                        other_oids = [x for x in order_ids_of(post) if x != oid]
                        for s in post["stops"]:
                            self.leg_gigs.get(s["orderId"], {}).pop(s["leg"], None)
                        for other_id in other_oids:
                            if other_id in self.orders and undelivered(self.orders[other_id]):
                                self._post_single_or_dynamic(self.orders[other_id])
            self.leg_gigs.pop(oid, None)
            if was_waiting:
                return
            return

        super().handle(event)

        if kind == "price_request":
            rid = event["request"]["id"]
            tid = self.rid_to_tour.get(rid)
            if tid:
                self._check_planned_tour(tid)
        elif kind == "order_lost":
            rid = event["requestId"]
            tid = self.rid_to_tour.get(rid)
            if tid:
                self._check_planned_tour(tid)
        elif kind == "gig_booked":
            gid = event["gigId"]
            if gid in self.tour_gigs:
                tinfo = self.tour_gigs[gid]
                self.stats["tour_booked"] += 1
                self.stats[f"tour_booked_c{tinfo['n_cars']}"] += 1
                self.stats["tour_cars_booked"] += tinfo["n_cars"]
                self.stats["tour_booked_fee_cents"] += event["feeCents"]
                oids = order_ids_of(self.posts[gid])
                self.stats["tour_booked_ref_cents"] += sum(self.requests[x]["referenceFeeCents"] for x in oids if x in self.requests)
                self.gig_est_finish[gid] = (max(self.now + tinfo["road_min"], tinfo["finish_at"]), tinfo["last_place"])
            elif gid in self.posts:
                oids = order_ids_of(self.posts[gid])
                if oids and oids[0] in self.orders:
                    o0 = self.orders[oids[0]]
                    p_place = o0["legs"][0]["pickup"]["placeId"]
                    d_place = o0["legs"][-1]["delivery"]["placeId"]
                    est_end = max(self.now, o0["legs"][0]["pickup"]["window"]["from"]) + self.geo.minutes(p_place, d_place)
                    self.gig_est_finish[gid] = (est_end, d_place)
        elif kind in ("gig_dropped", "no_show"):
            gid = event["gigId"]
            self.gig_est_finish.pop(gid, None)
            if gid in self.tour_gigs and gid in self.posts:
                self.stats["tour_dropped"] += 1
                oids = order_ids_of(self.posts[gid])
                # Split immediately if part of the tour was already delivered or if any order is close to lastPickupAt
                if any(oid not in self.orders or not undelivered(self.orders[oid]) or self.orders[oid]["lastPickupAt"] - self.now <= self.p.tour_split_guard_min + 60 for oid in oids):
                    self._split_open_tour_gig(gid, reason="drop")
        elif kind == "delivered":
            gid = event["gigId"]
            if gid not in self.booked_driver:
                self.gig_est_finish.pop(gid, None)

    def win(self, order: Order) -> None:
        oid = order["id"]
        if oid not in self.requests or oid in self.orders:
            return
        self.orders[oid] = order
        if self.p.urgent_hygiene and self.cannot_be_on_time(order):
            self.lost.add(oid)
        self.stats["won"] += 1
        pickup = order["legs"][0]["pickup"]["placeId"]
        if self.supply.get(pickup, 0) < self.p.min_supply:
            self.stats["won_ring"] += 1
        if self.gate_supply.get(pickup, 0) < self.p.min_supply:
            self.stats["won_ext_ring"] += 1
        self.stats[f"won_{order['option']}"] += 1

        tid = self.rid_to_tour.get(oid)
        if tid and tid not in self.broken_tours and tid not in self.posted_tours and len(order["legs"]) == 1:
            if order["lastPickupAt"] - self.now > self.p.tour_hold_guard_min:
                self.tour_waiting.add(oid)
                self.stats["tour_held_orders"] += 1
                self._check_planned_tour(tid)
                return
            else:
                self.broken_tours.add(tid)
                self.stats["tour_broken_tight_win"] += 1
                self._release_waiting_orders([x for x in self.planned_tours[tid]["rids"] if x in self.tour_waiting])

        self._post_single_or_dynamic(order)

    def change(self, order: Order) -> None:
        oid = order["id"]
        if oid not in self.orders:
            return
        if oid in self.tour_waiting:
            self.orders[oid] = order
            tid = self.rid_to_tour.get(oid)
            if tid:
                self.broken_tours.add(tid)
                self.stats["tour_broken_changed"] += 1
                all_wait = [x for x in self.planned_tours[tid]["rids"] if x in self.tour_waiting]
                self._release_waiting_orders(all_wait)
            else:
                self.tour_waiting.discard(oid)
                self._post_single_or_dynamic(order)
            return
        super().change(order)

    def _split_open_tour_gig(self, gid: str, reason: str) -> None:
        post = self.posts.get(gid)
        self.tour_gigs.pop(gid, None)
        self.chain_pairs.pop(gid, None)
        if post is None or gid in self.booked:
            return
        if not any(self.leg_gigs.get(s["orderId"], {}).get(s["leg"]) == gid for s in post["stops"]):
            return
        self.stats["tour_split"] += 1
        self.stats[f"tour_split_{reason}"] += 1
        self.outbox.append({"type": "withdraw", "gigId": gid})
        oids = order_ids_of(post)
        for s in post["stops"]:
            self.leg_gigs.get(s["orderId"], {}).pop(s["leg"], None)
        for oid in oids:
            if oid in self.orders and undelivered(self.orders[oid]):
                super().post(self.orders[oid], undelivered(self.orders[oid]), Retry(), allow_pair=False)

    def tick_tours(self) -> None:
        # 1. Release any held waiting orders approaching tour_hold_guard_min
        for oid in list(self.tour_waiting):
            o = self.orders.get(oid)
            if o is None or not undelivered(o):
                self.tour_waiting.discard(oid)
                continue
            tid = self.rid_to_tour.get(oid, "")
            if tid in self.broken_tours or oid in self.urgent or o["lastPickupAt"] - self.now <= self.p.tour_hold_guard_min:
                if tid and tid not in self.broken_tours:
                    self.broken_tours.add(tid)
                    self.stats["tour_broken_hold_timeout"] += 1
                    wait_list = [x for x in self.planned_tours[tid]["rids"] if x in self.tour_waiting]
                    self._release_waiting_orders(wait_list)
                else:
                    self.tour_waiting.discard(oid)
                    self._post_single_or_dynamic(o)

        # 2. Step-up flat fees or split unbooked open multi-car tour gigs before deadline warning
        for gid, tinfo in list(self.tour_gigs.items()):
            if gid in self.booked:
                continue
            post = self.posts.get(gid)
            if post is None or not any(self.leg_gigs.get(s["orderId"], {}).get(s["leg"]) == gid for s in post["stops"]):
                self.tour_gigs.pop(gid, None)
                continue
            oids = order_ids_of(post)
            if any(oid not in self.orders or oid in self.urgent or oid in self.lost for oid in oids):
                self._split_open_tour_gig(gid, reason="urgent")
                continue
            min_lp = min(self.orders[oid]["lastPickupAt"] for oid in oids)
            if min_lp - self.now <= self.p.tour_split_guard_min:
                self._split_open_tour_gig(gid, reason="guard")
                continue
            wait_day_min = daytime_minutes_between(tinfo["posted_at"], self.now, self.p.day_start, self.p.day_end)
            if self.p.tour_max_wait_min > 0 and wait_day_min >= self.p.tour_max_wait_min:
                self._split_open_tour_gig(gid, reason="patience")
                continue
            if self.p.tour_flat_mode and (self.p.day_start <= self.now % DAY < self.p.day_end):
                dt = daytime_minutes_between(tinfo["last_step_at"], self.now, self.p.day_start, self.p.day_end)
                if dt >= self.p.tour_step_interval_min and tinfo["mult"] + 1e-6 < self.p.tour_max_mult:
                    new_mult = min(self.p.tour_max_mult, tinfo["mult"] + self.p.tour_step_bump)
                    sched = self.build_tour_schedule(oids, new_mult)
                    self.posts[gid] = {**post, "schedule": sched}
                    tinfo["mult"] = new_mult
                    tinfo["last_step_at"] = self.now
                    self.outbox.append({"type": "reprice", "gigId": gid, "schedule": sched})
                    self.stats["tour_step_repriced"] += 1

        # 3. Relay direct offers: offer open homeward gigs to working drivers finishing nearby
        if self.p.relay_offers and (7 * HOUR <= self.now % DAY < 21 * HOUR):
            day = self.now // DAY
            for active_gid, d_id in list(self.booked_driver.items()):
                fin = self.gig_est_finish.get(active_gid)
                if fin is None:
                    continue
                fin_at, fin_place = fin
                if not (-30 <= fin_at - self.now <= 90):
                    continue
                if self.offers_sent[(d_id, day)] >= 3:
                    continue
                d_prof = self.drivers.get(d_id)
                if d_prof is None:
                    continue
                home = d_prof["homePlaceId"]
                for gid, post in list(self.posts.items()):
                    if gid in self.booked or (gid, d_id) in self.offered_pairs:
                        continue
                    if not any(self.leg_gigs.get(s["orderId"], {}).get(s["leg"]) == gid for s in post["stops"]):
                        continue
                    if sum(1 for k in self.open_offers if k[0] == gid) >= 3:
                        continue
                    aud: Audience = post["audience"]
                    if aud["experienced"] and not (d_prof["rating"] >= 4.8 and d_prof["completedGigs"] >= 50):
                        continue
                    if aud["manualLicence"] and d_prof["licence"] != "manual":
                        continue
                    oids = order_ids_of(post)
                    if not oids or any(x not in self.orders for x in oids):
                        continue
                    p_first = self.orders[oids[0]]["legs"][post["stops"][0]["leg"]]["pickup"]["placeId"]
                    d_last = self.orders[oids[-1]]["legs"][post["stops"][-1]["leg"]]["delivery"]["placeId"]
                    if self.geo.line_km(fin_place, p_first) <= self.p.relay_radius_km and self.geo.line_km(d_last, home) <= self.p.relay_home_km:
                        ref_sum = sum(self.requests[x]["referenceFeeCents"] for x in oids if x in self.requests)
                        cur_fee = current_schedule_fee(post["schedule"], self.now)
                        offer_fee = max(100, min(cur_fee, int(ref_sum * self.p.relay_offer_mult + 0.5)))
                        self.outbox.append({"type": "offer", "gigId": gid, "driverId": d_id, "feeCents": offer_fee})
                        self.offers_sent[(d_id, day)] += 1
                        self.open_offers[(gid, d_id)] = "relay"
                        self.offered_pairs.add((gid, d_id))
                        self.stats["offers"] += 1
                        self.stats["relay_offers_sent"] += 1
                        break

    def read_results(self, actions: list[Action], results: list[ActionResult]) -> None:
        super().read_results(actions, results)
        for action, result in zip(actions, results):
            if action["type"] != "post":
                continue
            key = tuple(order_ids_of(action))
            meta = self._pending_tour_meta.pop(key, None)
            if meta is None:
                continue
            if result["ok"] is True:
                gid = result["id"]
                self.tour_gigs[gid] = meta
                self.stats["tour_posted"] += 1
                self.stats[f"tour_posted_c{meta['n_cars']}"] += 1
                self.stats["tour_cars_posted"] += meta["n_cars"]
            else:
                self.stats["tour_post_refused"] += 1
                for oid in key:
                    if oid in self.orders and undelivered(self.orders[oid]) and not self.gigs_of(oid):
                        super().post(self.orders[oid], undelivered(self.orders[oid]), Retry(), allow_pair=False)

    def tick(self) -> None:
        self.tick_tours()
        super().tick()

    def rejoin(self, snapshot: DeskSnapshot, history: list[DeskEvent]) -> None:
        super().rejoin(snapshot, history)
        for gig in snapshot["gigs"]:
            if gig["status"] in ("open", "booked", "working"):
                oids = order_ids_of(gig)
                if len(oids) >= 2 and all(x in self.orders for x in oids):
                    p0 = self.orders[oids[0]]["legs"][0]["pickup"]["placeId"]
                    dk = self.orders[oids[-1]]["legs"][-1]["delivery"]["placeId"]
                    ref_sum = sum(self.requests[x]["referenceFeeCents"] for x in oids if x in self.requests)
                    cur_f = current_schedule_fee(gig["schedule"], self.now)
                    self.tour_gigs[gig["id"]] = {
                        "posted_at": gig["postedAt"],
                        "last_step_at": self.now,
                        "mult": (cur_f / ref_sum) if ref_sum > 0 else 0.6,
                        "closed": self.geo.line_km(dk, p0) <= self.p.tour_close_km,
                        "road_min": 240,
                        "finish_at": self.now + 240,
                        "last_place": dk,
                        "tid": "rejoined",
                        "n_cars": len(oids),
                    }
