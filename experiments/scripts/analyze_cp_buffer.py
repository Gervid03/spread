"""Slot-free analysis of all 16 revealed champion dev worlds for cp-buffer:
1. Declined requests & dropped options by candidate buffer-opened gate
2. Booked fee/ref ratio, late rate, and floored quotes by route/option class
3. Day-by-day trajectory of projected_on_time() on tight vs safe worlds
"""
from __future__ import annotations

import collections
import csv
import json
import math
import sys
from pathlib import Path

from spread_lab.notes import parse_note_v2, shift_business_days, window_from_note

csv.field_size_limit(10**9)
DAY = 1440
HOUR = 60
CAPITAL = {"helsinki", "espoo", "vantaa"}


def rd(d: Path, name: str) -> list[dict[str, str]]:
    with open(d / f"{name}.csv", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def hav(a: tuple[float, float], b: tuple[float, float]) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(h))


def main() -> None:
    root = Path(sys.argv[1])
    world_dirs = sorted(root.glob("dev-*/reveal-*"))
    print(f"Analyzing {len(world_dirs)} revealed worlds...")

    decl_reasons = collections.Counter()
    cand_gates = collections.Counter()
    cand_gates_dev14 = collections.Counter()
    dropped_opts = collections.Counter()
    dropped_opts_dev14 = collections.Counter()

    # Won order fee/ref & late by class
    cls_stats: dict[str, list[tuple[float, int, float]]] = collections.defaultdict(list)
    # Floored quotes lost by class
    floored_lost = collections.Counter()
    floored_won = collections.Counter()

    proj_by_day: dict[str, dict[int, float]] = {}

    for wd in world_dirs:
        seed = wd.parent.name.split("-w")[0]
        places = {p["id"]: (float(p["lat"]), float(p["lon"])) for p in rd(wd, "places")}
        line = {(a, b): hav(places[a], places[b]) for a in places for b in places}
        roads = {(r["from"], r["to"]): int(r["minutes"]) for r in rd(wd, "roads")}
        drivers = rd(wd, "drivers")
        homes = collections.Counter(x["homePlaceId"] for x in drivers)
        sup30 = {p: sum(n for h, n in homes.items() if line[(p, h)] <= 30.0) for p in places}
        sup55 = {p: sum(n for h, n in homes.items() if line[(p, h)] <= 55.0) for p in places}
        sup70 = {p: sum(n for h, n in homes.items() if line[(p, h)] <= 70.0) for p in places}

        legs_by_req = collections.defaultdict(list)
        for leg in rd(wd, "legs"):
            legs_by_req[leg["requestId"]].append(leg)

        events = rd(wd, "events")
        late_oids = set()
        order_ledger = collections.Counter()
        order_fee = collections.Counter()
        gig_orders: dict[str, list[str]] = {}
        for g in rd(wd, "gigs"):
            oids = list(dict.fromkeys(s["orderId"] for s in json.loads(g["stops"])))
            gig_orders[g["id"]] = oids

        # Track day-by-day projected_on_time
        won_so_far: dict[str, int] = {}  # oid -> deadline
        delivered_oids: set[str] = set()
        staffed_oids: set[str] = set()
        urgent_oids: set[str] = set()
        late_so_far: set[str] = set()
        day_snaps: dict[int, float] = {}
        cur_check_idx = 0
        checkpoints = [d * DAY + 12 * HOUR for d in range(6)]  # Mon 12:00 .. Sat 12:00

        reqs_map = {r["id"]: r for r in rd(wd, "requests")}

        for ev in events:
            at = int(ev["at"])
            while cur_check_idx < len(checkpoints) and at >= checkpoints[cur_check_idx]:
                t_cp = checkpoints[cur_check_idx]
                l_cnt = 0
                r_cnt = 0
                for oid, dl in won_so_far.items():
                    open_leg = oid not in delivered_oids
                    if oid in late_so_far or (open_leg and t_cp > dl):
                        l_cnt += 1
                    elif open_leg and oid in urgent_oids and oid not in staffed_oids:
                        r_cnt += 1
                proj = 1.0 - (l_cnt + 0.5 * r_cnt) / max(len(won_so_far), 30)
                day_snaps[cur_check_idx] = proj
                cur_check_idx += 1

            k = ev["kind"]
            if k == "order_won":
                oid = ev["order.id"]
                won_so_far[oid] = int(ev["order.deadline"])
            elif k == "order_cancelled":
                won_so_far.pop(ev["orderId"], None)
            elif k == "deadline_close":
                urgent_oids.add(ev["orderId"])
            elif k == "gig_booked":
                for oid in gig_orders.get(ev["gigId"], []):
                    staffed_oids.add(oid)
            elif k in ("gig_dropped", "no_show", "gig_expired"):
                for oid in gig_orders.get(ev["gigId"], []):
                    staffed_oids.discard(oid)
            elif k == "delivered":
                # approximate single-leg or final leg
                oid = ev["orderId"]
                if int(ev["leg"]) == len(legs_by_req[oid]) - 1:
                    delivered_oids.add(oid)
            elif k == "ledger":
                lk = ev["line.kind"]
                cents = int(ev["line.cents"])
                oid = ev["line.orderId"]
                gid = ev["line.gigId"]
                if oid:
                    order_ledger[oid] += cents
                    if lk == "driver_fee":
                        order_fee[oid] += -cents
                    if lk in ("late_refund", "undelivered_penalty"):
                        late_oids.add(oid)
                        late_so_far.add(oid)
                elif gid and gid in gig_orders:
                    oids = gig_orders[gid]
                    ref_tot = sum(int(reqs_map[o]["referenceFeeCents"]) for o in oids if o in reqs_map)
                    for o in oids:
                        if o in reqs_map and ref_tot > 0:
                            sh = round(cents * int(reqs_map[o]["referenceFeeCents"]) / ref_tot)
                            order_ledger[o] += sh
                            if lk == "driver_fee":
                                order_fee[o] += -sh
        proj_by_day[seed] = day_snaps

        for r in reqs_map.values():
            rid = r["id"]
            rlegs = legs_by_req[rid]
            pk = rlegs[0]["pickup.placeId"]
            dl = rlegs[-1]["delivery.placeId"]
            s30 = sup30[pk]
            s55 = sup55[pk]
            s70 = sup70[pk]
            dl30 = sup30[dl]
            dl55 = sup55[dl]
            drive = sum(roads[(l["pickup.placeId"], l["delivery.placeId"])] for l in rlegs)
            if len(rlegs) == 2:
                drive += roads[(rlegs[0]["delivery.placeId"], rlegs[1]["pickup.placeId"])]
            ref = int(r["referenceFeeCents"])
            arr = int(r["arrivedAt"])
            note_txt = r["note"]
            pn = parse_note_v2({"text": note_txt, "language": r["language"]} if note_txt else None, arr)

            opts = []
            quoted_opts = {}
            for ok in ("same_day", "next_day", "within_3_days"):
                if r[f"{ok}.listPriceCents"]:
                    lp = int(r[f"{ok}.listPriceCents"])
                    dline = int(r[f"{ok}.deadline"])
                    qc = int(r[f"{ok}.quoteCents"]) if r[f"{ok}.quoteCents"] else None
                    opts.append((ok, lp, dline, qc))
                    if qc is not None:
                        quoted_opts[ok] = (lp, dline, qc)

            # Check if declined (single option quoted at ~4.0x list)
            first_ok, first_lp, _, first_qc = opts[0]
            is_declined = len(quoted_opts) == 1 and first_qc is not None and abs(first_qc - int(first_lp * 4.0)) <= 2
            has_slow = any(ok != "same_day" for ok, _, _, _ in opts)
            has_w3d = any(ok == "within_3_days" for ok, _, _, _ in opts)

            if is_declined:
                if pn.unsure:
                    decl_reasons["note_unsure"] += 1
                elif s55 < 22 and not (s70 >= 30 and drive <= 220) and not (dl30 >= 200 and drive <= 180):
                    decl_reasons["supply_gate"] += 1
                    if has_slow:
                        if dl30 >= 200 and 180 < drive <= 320:
                            cand_gates["ret_cap_181_320"] += 1
                            if seed == "dev-14":
                                cand_gates_dev14["ret_cap_181_320"] += 1
                        elif dl55 >= 200 and dl30 < 200 and drive <= 280:
                            cand_gates["ret_ringhub_le280 (e.g. Hyvinkaa)"] += 1
                            if seed == "dev-14":
                                cand_gates_dev14["ret_ringhub_le280 (e.g. Hyvinkaa)"] += 1
                        elif dl30 >= 100 and dl30 < 200 and drive <= 240:
                            cand_gates["ret_midhub100_le240 (e.g. Jyvaskyla)"] += 1
                            if seed == "dev-14":
                                cand_gates_dev14["ret_midhub100_le240 (e.g. Jyvaskyla)"] += 1
                        elif s70 >= 22 and drive <= 280:
                            cand_gates["ext_ring_s70>=22_d<=280"] += 1
                            if seed == "dev-14":
                                cand_gates_dev14["ext_ring_s70>=22_d<=280"] += 1
                        elif has_w3d and s55 >= 12 and drive <= 280:
                            cand_gates["thin_w3d_s55>=12_d<=280"] += 1
                            if seed == "dev-14":
                                cand_gates_dev14["thin_w3d_s55>=12_d<=280"] += 1
                        elif has_w3d and drive <= 260:
                            cand_gates["very_thin_w3d_d<=260"] += 1
                        else:
                            cand_gates["other_thin_slow"] += 1
                    else:
                        cand_gates["thin_sd_only"] += 1
                else:
                    decl_reasons["all_opts_dropped_or_backlog"] += 1
                    if not has_slow:
                        cand_gates["passed_gate_sd_only_dropped"] += 1
                        if seed == "dev-14":
                            cand_gates_dev14["passed_gate_sd_only_dropped"] += 1
            else:
                # Quoted request: check dropped options and floored options
                floor_cents = int(ref * 1.25 / 0.92 + 0.5)
                for ok, lp, dline, qc in opts:
                    if qc is None:
                        # Option dropped!
                        if ok == "same_day" and 22 <= s30 < 50 and dl30 >= 200 and drive <= 120:
                            dropped_opts["mid_to_cap_sd_d<=120"] += 1
                            if seed == "dev-14":
                                dropped_opts_dev14["mid_to_cap_sd_d<=120"] += 1
                        elif ok == "same_day" and s30 < 22 and dl30 >= 200 and 60 < drive <= 120:
                            dropped_opts["ring_to_cap_sd_61_120"] += 1
                            if seed == "dev-14":
                                dropped_opts_dev14["ring_to_cap_sd_61_120"] += 1
                        elif ok == "same_day" and 30 <= s30 < 50 and drive <= 90 and (arr % DAY) < 12 * HOUR:
                            dropped_opts["mid30_sd_morning_d<=90"] += 1
                            if seed == "dev-14":
                                dropped_opts_dev14["mid30_sd_morning_d<=90"] += 1
                        elif ok != "same_day":
                            dropped_opts[f"dropped_{ok}"] += 1
                            if seed == "dev-14":
                                dropped_opts_dev14[f"dropped_{ok}"] += 1
                        else:
                            dropped_opts["other_sd_dropped"] += 1
                    else:
                        if abs(qc - floor_cents) <= 1:
                            cls_key = (
                                "w3d" if ok == "within_3_days"
                                else ("to_cap" if dl30 >= 200 else ("to_ringhub" if dl55 >= 200 else ("cap_out_thin" if s30 >= 200 and dl30 < 30 else "other")))
                            )
                            if r["outcome"] == "won" and r["option"] == ok:
                                floored_won[f"{ok}:{cls_key}"] += 1
                            elif r["outcome"] == "lost":
                                floored_lost[f"{ok}:{cls_key}"] += 1

            if r["outcome"] == "won":
                ok = r["option"]
                fee_paid = order_fee[rid]
                margin_eur = order_ledger[rid] / 100.0
                is_late = 1 if rid in late_oids else 0
                fee_ratio = fee_paid / ref if ref > 0 else 0.0

                if ok == "within_3_days":
                    c = "w3d_all"
                elif dl30 >= 200 and s30 < 200:
                    c = f"inbound_to_cap_{ok}"
                elif dl30 >= 200 and s30 >= 200:
                    c = f"intra_cap_{ok}"
                elif dl55 >= 200 and dl30 < 200:
                    c = f"to_ringhub_hyvinkaa_{ok}"
                elif s30 >= 200 and dl30 < 30:
                    c = f"cap_to_thin_{ok}"
                elif s30 >= 200:
                    c = f"cap_to_mid_{ok}"
                else:
                    c = f"regional_{ok}"
                cls_stats[c].append((fee_ratio, is_late, margin_eur))

    print("\n=== DECLINE REASONS (per world avg over 16 dev worlds) ===")
    for k, v in decl_reasons.most_common():
        print(f"  {k:<32}: {v / 16:6.1f} / wk  (total {v})")

    print("\n=== CANDIDATE BUFFER GATES AMONG DECLINED (per world avg & dev-14) ===")
    for k, v in cand_gates.most_common():
        print(f"  {k:<38}: {v / 16:5.1f} / wk  | dev-14: {cand_gates_dev14[k]:3d}")

    print("\n=== DROPPED OPTIONS ON QUOTED REQUESTS (per world avg & dev-14) ===")
    for k, v in dropped_opts.most_common():
        print(f"  {k:<38}: {v / 16:5.1f} / wk  | dev-14: {dropped_opts_dev14[k]:3d}")

    print("\n=== WON ORDERS BY CLASS: n/wk, mean fee/ref, p90 fee/ref, late %, margin/order ===")
    for c, items in sorted(cls_stats.items(), key=lambda kv: -len(kv[1])):
        n = len(items)
        fr = sorted(x[0] for x in items)
        mean_fr = sum(fr) / n
        p90_fr = fr[int(0.9 * (n - 1))]
        late_pct = 100.0 * sum(x[1] for x in items) / n
        marg = sum(x[2] for x in items) / n
        print(f"  {c:<28}: {n / 16:5.1f}/wk | fee/ref={mean_fr:.3f} (p90={p90_fr:.2f}) | late={late_pct:4.2f}% | marg=€{marg:5.2f}")

    print("\n=== FLOORED OPTIONS: WON vs LOST (per world avg) ===")
    all_fk = sorted(set(floored_won) | set(floored_lost), key=lambda k: -(floored_won[k] + floored_lost[k]))
    for k in all_fk[:14]:
        w, l = floored_won[k], floored_lost[k]
        tot_f = w + l
        print(f"  {k:<24}: tot={tot_f / 16:5.1f}/wk | won={w / 16:4.1f} ({100*w/max(1,tot_f):4.1f}%) | lost={l / 16:4.1f}")

    print("\n=== PROJECTED ON-TIME TRAJECTORY (Mon..Sat 12:00) ===")
    for seed in sorted(proj_by_day):
        snaps = proj_by_day[seed]
        vals = " ".join(f"{snaps.get(i, 1.0):.3f}" for i in range(6))
        print(f"  {seed:<8}: {vals}")


if __name__ == "__main__":
    main()
