#!/usr/bin/env python3
"""Inspect roster sizes, drive lengths, and stress metrics across the 16 dev seeds for return-offer tuning."""
from __future__ import annotations

import csv
import json
from pathlib import Path
from spread_lab.geo import Geo


def load_jsonl(p: Path) -> dict[str, dict]:
    return {r["seed"]: r for r in (json.loads(x) for x in p.read_text().splitlines() if x.strip())}


def main() -> None:
    champ = load_jsonl(Path("champion/results/dev-L8.jsonl"))
    d1 = load_jsonl(Path("runs/20261114-082004-c14-ret-d1-cap8-open10-off105-onwin/results.jsonl"))
    geo = Geo(json.loads(Path("/home/lab/.spread-lab/map.json").read_text()))

    # Map world id in champion v3 reveals if needed, or inspect request drives per reveal
    rev_by_world = {p.name.replace("reveal-", ""): p for p in Path("runs/reveals-v3").glob("reveal-*")}
    print(f"{'seed':<7} {'champ_m':>8} {'d1_dm':>8} {'c_ot':>6} {'d1_ot':>6} {'c_won':>5} {'ret_w':>5} {'ret_l':>5} {'c_dlc':>5} {'d1_dlc':>6}")
    print("dev-07 d1 world:", d1["dev-07"]["world"])
    for s in sorted(champ):
        c, r = champ[s], d1[s]
        st = r["stats"]
        cst = c["stats"]
        print(
            f"{s:<7} {c['margin']:8.1f} {r['margin']-c['margin']:+8.1f} "
            f"{c['on_time']*100:5.1f}% {r['on_time']*100:5.1f}% "
            f"{c['won']:5d} {st.get('ret_won',0):5d} {st.get('ret_late',0):5d} "
            f"{cst.get('deadline_close',0):5d} {st.get('deadline_close',0):6d}"
        )

    # Also check roster distribution across the 16 reveals-v3 worlds
    rosters = []
    long_thin = []
    short_thin = []
    for wdir in sorted(Path("runs/reveals-v3").glob("reveal-*")):
        roster = list(csv.DictReader(open(wdir / "drivers.csv")))
        s55 = geo.supply(roster, 55.0)
        s70 = geo.supply(roster, 70.0)
        s30 = geo.supply(roster, 30.0)
        legs_by_req = {}
        for l in csv.DictReader(open(wdir / "legs.csv")):
            legs_by_req.setdefault(l["requestId"], []).append(l)
        lt = st_cnt = 0
        for req in csv.DictReader(open(wdir / "requests.csv")):
            rl = legs_by_req[req["id"]]
            p0, dl = rl[0]["pickup.placeId"], rl[-1]["delivery.placeId"]
            drv = sum(geo.minutes(x["pickup.placeId"], x["delivery.placeId"]) for x in rl)
            if s55[p0] >= 22 or (s70[p0] >= 30 and drv <= 220) or (s30[dl] >= 200 and drv <= 180):
                continue
            if not (req["next_day.deadline"] or req["within_3_days.deadline"]):
                continue
            if drv > 260:
                lt += 1
            else:
                st_cnt += 1
        rosters.append((len(roster), wdir.name, st_cnt, lt))
    rosters.sort()
    print()
    print("Reveals sorted by roster size (n_drivers, world, thin_slow<=260m, thin_slow>260m):")
    for n_drv, wn, sc, lc in rosters:
        print(f"  drivers={n_drv:4d}  {wn}  <=260m={sc:3d}  >260m={lc:3d}")

    rev07 = Path("runs/reveal-w81bb413bdc617b5ab524")
    if rev07.exists():
        roster = list(csv.DictReader(open(rev07 / "drivers.csv")))
        print(f"\n=== dev-07 reveal ({rev07.name}): roster={len(roster)} ===")
        s55 = geo.supply(roster, 55.0)
        s70 = geo.supply(roster, 70.0)
        s30 = geo.supply(roster, 30.0)
        legs_by_req = {}
        for l in csv.DictReader(open(rev07 / "legs.csv")):
            legs_by_req.setdefault(l["requestId"], []).append(l)
        late_orders = set()
        deliv_at = {}
        for e in csv.DictReader(open(rev07 / "events.csv")):
            if e["kind"] == "ledger" and e["line.kind"] in ("late_refund", "undelivered_penalty") and e["line.orderId"]:
                late_orders.add(e["line.orderId"])
            elif e["kind"] == "delivered":
                deliv_at[e["orderId"]] = int(e["at"])
        print("Return-offer won orders on dev-07:")
        for req in csv.DictReader(open(rev07 / "requests.csv")):
            if req["outcome"] != "won":
                continue
            rid = req["id"]
            rl = legs_by_req[rid]
            p0, dl = rl[0]["pickup.placeId"], rl[-1]["delivery.placeId"]
            drv = sum(geo.minutes(x["pickup.placeId"], x["delivery.placeId"]) for x in rl)
            if s55[p0] >= 22 or (s70[p0] >= 30 and drv <= 220) or (s30[dl] >= 200 and drv <= 180):
                continue
            arr = int(req["arrivedAt"])
            opt = req["option"]
            is_late = rid in late_orders
            print(
                f"  {rid} d={arr//1440} {p0:<12}->{dl:<12} s55={s55[p0]:2d} s30_deliv={s30[dl]:3d} "
                f"drive={drv:3d}m opt={opt:<13} LATE={is_late}"
            )

    hb_cnt = s30_cnt = dead_cnt = 0
    for wdir in sorted(Path("runs/reveals-v3").glob("reveal-*")):
        roster = list(csv.DictReader(open(wdir / "drivers.csv")))
        drivers = {r["id"]: r for r in roster}
        s30 = geo.supply(roster, 30.0)
        s55 = geo.supply(roster, 55.0)
        s70 = geo.supply(roster, 70.0)
        legs_by_req = {}
        for l in csv.DictReader(open(wdir / "legs.csv")):
            legs_by_req.setdefault(l["requestId"], []).append(l)
        gig_book, gig_deliv = {}, {}
        for e in csv.DictReader(open(wdir / "events.csv")):
            at = int(e["at"]) if e["at"] else 0
            gid = e["gigId"]
            if e["kind"] == "gig_booked":
                gig_book[gid] = (at, e["driverId"])
            elif e["kind"] in ("gig_dropped", "no_show"):
                gig_book.pop(gid, None)
            elif e["kind"] == "delivered":
                gig_deliv[(gid, e["orderId"], int(e["leg"]))] = (at, e["placeId"])
        active = [(gig_book[gid][0], dat, gig_book[gid][1], dplace) for (gid, oid, leg), (dat, dplace) in gig_deliv.items() if gid in gig_book]
        for req in csv.DictReader(open(wdir / "requests.csv")):
            rl = legs_by_req[req["id"]]
            p0, dl = rl[0]["pickup.placeId"], rl[-1]["delivery.placeId"]
            drv = sum(geo.minutes(l["pickup.placeId"], l["delivery.placeId"]) for l in rl)
            if s55[p0] >= 22 or (s70[p0] >= 30 and drv <= 220) or (s30[dl] >= 200 and drv <= 180):
                continue
            if not (req["next_day.deadline"] or req["within_3_days.deadline"]):
                continue
            arr = int(req["arrivedAt"])
            cands = [(d_id, dp) for bat, dat, d_id, dp in active if bat <= arr < dat and geo.line_km(dp, p0) <= 15.0]
            if not cands:
                continue
            has_hb = any(geo.line_km(drivers[d_id]["homePlaceId"], dl) <= 30.0 for d_id, _ in cands)
            if s30[dl] >= 30 or has_hb:
                if has_hb:
                    hb_cnt += 1
                else:
                    s30_cnt += 1
            else:
                dead_cnt += 1
    print(
        f"\n16-world matched breakdown: safe={(hb_cnt+s30_cnt)/16:.1f}/wk "
        f"(homebound={hb_cnt/16:.1f}/wk, s30_deliv>=30={s30_cnt/16:.1f}/wk) "
        f"| dead_end(s30_deliv<30)={dead_cnt/16:.1f}/wk"
    )


if __name__ == "__main__":
    main()
