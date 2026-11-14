"""Measure driver idle time, empty return/deadhead km, and missed multi-car/batch/slow-option opportunities on TAS reveals."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from statistics import mean

from spread_lab.env import lab_home
from spread_lab.geo import Geo
from spread_lab.notes import note_flags, window_from_note


def main() -> None:
    lh = lab_home()
    geo = Geo(json.loads((lh / "map.json").read_text()))

    for seed in ["dev-12", "dev-01", "dev-07", "dev-08"]:
        sdir = lh / "tas" / seed
        rev = json.loads((sdir / "reveal-v5.json").read_text())
        tape = json.loads((sdir / "tape.json").read_text())
        roster = {d["id"]: d for d in tape["roster"]}
        sup30 = geo.supply(tape["roster"], 30.0)
        sup55 = geo.supply(tape["roster"], 55.0)
        req_by_id = {x["request"]["id"]: x["request"] for x in rev["requests"]}
        out_by_id = {x["request"]["id"]: x for x in rev["requests"]}

        # Reconstruct driver trips from orders' pickedUpAt/deliveredAt + views/gigs if present
        orders_won = rev["orders"]
        loaded_km = 0.0
        loaded_min = 0
        oneway_return_km = 0.0
        benign_note_slow = 0
        any_note_slow = 0
        sameday_won = 0
        slow_won = 0
        for orow in orders_won:
            oid = orow["orderId"]
            req = req_by_id[oid]
            opt = out_by_id[oid]["option"]
            if opt == "same_day":
                sameday_won += 1
            else:
                slow_won += 1
                if req.get("note"):
                    any_note_slow += 1
                    fl = note_flags(req["note"], v2=True)
                    p_base = req["legs"][0]["pickup"]["window"]
                    d_base = req["legs"][0]["delivery"]["window"]
                    pw = window_from_note(req["note"], p_base, "pickup", v2=True, arrived_at=req["arrivedAt"],
                                          private_address=req["legs"][0]["pickup"]["privateAddress"],
                                          stated_hours=req["legs"][0]["pickup"]["hours"])
                    dw = window_from_note(req["note"], d_base, "delivery", v2=True, arrived_at=req["arrivedAt"],
                                          private_address=req["legs"][0]["delivery"]["privateAddress"],
                                          stated_hours=req["legs"][0]["delivery"]["hours"])
                    if not (fl.plates or fl.summer_tyres or pw != p_base or dw != d_base):
                        benign_note_slow += 1
            for idx, leg in enumerate(req["legs"]):
                p = leg["pickup"]["placeId"]
                d = leg["delivery"]["placeId"]
                loaded_km += geo.road_km(p, d)
                loaded_min += geo.minutes(p, d)
            p0 = req["legs"][0]["pickup"]["placeId"]
            dk = req["legs"][-1]["delivery"]["placeId"]
            oneway_return_km += geo.road_km(dk, p0)

        # Check closed-loop pairs & 2-car shuttle pairs among ALREADY WON orders in v5!
        won_single = [
            (orow["orderId"], req_by_id[orow["orderId"]], out_by_id[orow["orderId"]]["option"], orow["legs"][0])
            for orow in orders_won if len(req_by_id[orow["orderId"]]["legs"]) == 1
        ]
        closed_pairs_won = 0
        shuttle_pairs_won = 0
        used = set()
        for i, (id1, r1, opt1, l1) in enumerate(won_single):
            if id1 in used:
                continue
            p1, d1 = r1["legs"][0]["pickup"]["placeId"], r1["legs"][0]["delivery"]["placeId"]
            t1 = r1["arrivedAt"]
            for j in range(i + 1, len(won_single)):
                id2, r2, opt2, l2 = won_single[j]
                if id2 in used:
                    continue
                p2, d2 = r2["legs"][0]["pickup"]["placeId"], r2["legs"][0]["delivery"]["placeId"]
                t2 = r2["arrivedAt"]
                if abs(t2 - t1) <= 240:
                    if geo.line_km(d1, p2) <= 25 and geo.line_km(d2, p1) <= 30:
                        closed_pairs_won += 1
                        used.add(id1)
                        used.add(id2)
                        break
                    if geo.line_km(p1, p2) <= 20 and geo.line_km(d1, d2) <= 25 and geo.minutes(p1, d1) * 3 <= 540:
                        shuttle_pairs_won += 1
                        used.add(id1)
                        used.add(id2)
                        break

        # Check dense declined requests (why were dense pickups declined?!)
        dense_declined_reasons = Counter()
        for rrow in rev["requests"]:
            req = rrow["request"]
            q_vals = list(rrow["quote"].values())
            was_declined = bool(q_vals and min(q_vals) >= req["options"][0]["listPriceCents"] * 3.5)
            if not was_declined:
                continue
            p0 = req["legs"][0]["pickup"]["placeId"]
            if len(req["legs"]) > 1:
                dense_declined_reasons["trade_in_2leg"] += 1
                continue
            if sup55.get(p0, 0) < 22:
                continue
            drv = geo.minutes(p0, req["legs"][0]["delivery"]["placeId"])
            opts = [o["kind"] for o in req["options"]]
            s30 = sup30.get(p0, 0)
            if s30 < 22 and opts == ["same_day"]:
                dense_declined_reasons["ring_only_sameday"] += 1
            elif s30 < 65 and opts == ["same_day"]:
                dense_declined_reasons["dense_22_64_only_sameday"] += 1
            elif drv > 300 and opts == ["same_day"]:
                dense_declined_reasons["long_drive_only_sameday"] += 1
            elif s30 < 50 and drv > 300 and opts in (["next_day"], ["same_day", "next_day"]):
                dense_declined_reasons["thin_long_next_day_gt300"] += 1
            elif req["arrivedAt"] // 1440 >= 4 and opts == ["same_day"] and drv >= 150:
                dense_declined_reasons["fri_sameday_gt150"] += 1
            else:
                dense_declined_reasons[f"slack_or_backlog_opts={'+'.join(opts)}_drv={drv//60}h"] += 1

        print(f"=== {seed}: won={len(orders_won)} (sd={sameday_won}, slow={slow_won}, slow_note={any_note_slow}, benign_note={benign_note_slow}) ===")
        print(f"  Loaded km={loaded_km:.0f}, implied solo return km={oneway_return_km:.0f}, loaded wheel-hrs={loaded_min/60:.1f}h across {len(roster)} roster drivers ({loaded_min/60/len(roster):.2f}h/driver/wk!)")
        print(f"  Among ALREADY WON single-leg orders within 4h: closed_pairs={closed_pairs_won}, shuttle_pairs={shuttle_pairs_won}")
        print(f"  Non-thin declined breakdown: {dict(dense_declined_reasons.most_common(8))}")


if __name__ == "__main__":
    main()
