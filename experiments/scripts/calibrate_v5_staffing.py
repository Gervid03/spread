"""Calibrate v5's actual late-order rate across all 4 TAS worlds from cached reveal-v5.json."""
from __future__ import annotations

import json
from collections import defaultdict

from spread_lab.env import lab_home
from spread_lab.geo import Geo, load_map


def main() -> None:
    geo = Geo(load_map(None))
    tas_dir = lab_home() / "tas"
    late_by_bucket = defaultdict(lambda: [0, 0])
    late_examples = []

    for seed in ["dev-12", "dev-01", "dev-08", "dev-07"]:
        rev = json.loads((tas_dir / seed / "reveal-v5.json").read_text(encoding="utf-8"))
        tp = json.loads((tas_dir / seed / "tape.json").read_text(encoding="utf-8"))
        s30 = geo.supply(tp["roster"], 30.0)
        s55 = geo.supply(tp["roster"], 55.0)
        reqs = {x["request"]["id"]: x for x in rev["requests"]}
        for ord_row in rev["orders"]:
            oid = ord_row["orderId"]
            rx = reqs[oid]
            r = rx["request"]
            opt_kind = rx["option"]
            dl = next(o["deadline"] for o in r["options"] if o["kind"] == opt_kind)
            # Check noteDeadline if any
            note_dls = [l["noteDeadline"] for l in ord_row["legs"] if l.get("noteDeadline") is not None]
            eff_dl = min([dl] + note_dls)
            deliv_ats = [l["deliveredAt"] for l in ord_row["legs"]]
            undeliv = any(d is None for d in deliv_ats)
            late = undeliv or max(deliv_ats) > eff_dl
            p0 = r["legs"][0]["pickup"]["placeId"]
            d0 = r["legs"][-1]["delivery"]["placeId"]
            ps, gs, ds = s30.get(p0, 0), s55.get(p0, 0), s30.get(d0, 0)
            legs = r["legs"]
            drive = sum(geo.minutes(l["pickup"]["placeId"], l["delivery"]["placeId"]) for l in legs)
            if len(legs) == 2:
                drive += geo.minutes(legs[0]["delivery"]["placeId"], legs[1]["pickup"]["placeId"])
            has_flags = any(l["manualGearbox"] or l["needsPlates"] or l["summerTyres"] for l in ord_row["legs"])
            b_ps = "ps<22" if ps < 22 else ("ps22..59" if ps < 60 else ("ps60..149" if ps < 150 else "ps>=150"))
            b_drv = "drv<=180" if drive <= 180 else ("drv181..320" if drive <= 320 else "drv>320")
            for key in [f"opt:{opt_kind}", f"ps:{b_ps}", f"drv:{b_drv}", f"flags:{has_flags}", f"legs:{len(legs)}"]:
                late_by_bucket[key][1] += 1
                if late:
                    late_by_bucket[key][0] += 1
            if late:
                late_examples.append((seed, oid, opt_kind, ps, gs, ds, drive, undeliv, max((d or 99999) for d in deliv_ats) - eff_dl, bool(r["note"])))

    print("=== v5 LATE RATE ACROSS ALL 4 TAS WORLDS (1,138 WON ORDERS) ===")
    for k, (l_cnt, tot) in sorted(late_by_bucket.items()):
        print(f"  {k:<22}: {l_cnt:2d}/{tot:4d} = {l_cnt/max(1,tot):5.1%}")
    print(f"Total late/undelivered examples ({len(late_examples)}):")
    for ex in late_examples[:20]:
        print(f"  {ex[0]} {ex[1]} {ex[2]:<12} ps={ex[3]:3d} gs={ex[4]:3d} ds={ex[5]:3d} drv={ex[6]:3d}m undeliv={ex[7]} lateness={ex[8]}m note={ex[9]}")


if __name__ == "__main__":
    main()
