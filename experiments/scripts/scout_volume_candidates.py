"""Size candidate additive volume classes on dev-04 reveal:
1. 2-leg trade-ins with sequential slack
2. return_hub to regional pools (supply >= 50) & longer drives (<= 280m)
3. Ring short same_day (Hyvinkaa -> non-hub <= 90m or morning)
4. Friday / Mon2+ slow options
"""
from __future__ import annotations

import csv
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path


def main() -> None:
    rev = Path(sys.argv[1] if len(sys.argv) > 1 else "runs/reveals/reveal-we07744ba5bd2d430cc60")
    places = {r["id"]: r for r in csv.DictReader(open(rev / "places.csv", encoding="utf-8"))}
    roads = {(r["from"], r["to"]): (float(r["km"]), int(r["minutes"])) for r in csv.DictReader(open(rev / "roads.csv", encoding="utf-8"))}
    drivers = list(csv.DictReader(open(rev / "drivers.csv", encoding="utf-8")))
    reqs = list(csv.DictReader(open(rev / "requests.csv", encoding="utf-8")))
    legs_by_req = defaultdict(list)
    for l in csv.DictReader(open(rev / "legs.csv", encoding="utf-8")):
        legs_by_req[l["requestId"]].append(l)

    def hav(a: str, b: str) -> float:
        p1, p2 = places[a], places[b]
        la1, lo1, la2, lo2 = map(math.radians, (float(p1["lat"]), float(p1["lon"]), float(p2["lat"]), float(p2["lon"])))
        h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
        return 6371.0 * 2 * math.asin(math.sqrt(h))

    homes = Counter(d["homePlaceId"] for d in drivers)
    sup30 = {p: sum(n for h, n in homes.items() if hav(p, h) <= 30.0) for p in places}
    sup55 = {p: sum(n for h, n in homes.items() if hav(p, h) <= 55.0) for p in places}
    sup70 = {p: sum(n for h, n in homes.items() if hav(p, h) <= 70.0) for p in places}

    def drv_min(a: str, b: str) -> int:
        return 0 if a == b else roads[(a, b)][1]

    print("=== 1. 2-LEG TRADE-INS SEQUENTIAL SLACK CHECK ===")
    ti_pass = 0
    for r in reqs:
        ls = legs_by_req[r["id"]]
        if len(ls) != 2:
            continue
        pk0, dl0 = ls[0]["pickup.placeId"], ls[0]["delivery.placeId"]
        pk1, dl1 = ls[1]["pickup.placeId"], ls[1]["delivery.placeId"]
        d0, d_mid, d1 = drv_min(pk0, dl0), drv_min(dl0, pk1), drv_min(pk1, dl1)
        tot_d = d0 + d_mid + d1
        s55 = sup55[pk0]
        arr = int(r["arrivedAt"])
        r0 = max(arr, int(ls[0]["pickup.window.from"]))
        dl0_to = int(ls[0]["delivery.window.to"])
        r1 = int(ls[1]["pickup.window.from"])
        for opt in ("same_day", "next_day", "within_3_days"):
            if not r[f"{opt}.deadline"]:
                continue
            dl = int(r[f"{opt}.deadline"])
            slack0 = dl0_to - r0 - d0
            handoff = max(r0 + d0 + d_mid, r1)
            slack1 = dl - handoff - d1
            ok_gate = s55 >= 22 and tot_d <= 600
            ok_opt = (opt != "same_day" or sup30[pk0] >= 50)
            ok_slack = slack0 >= 150 + 0.75 * d0 and slack1 >= 60 + 0.25 * d1
            if ok_gate and ok_opt and ok_slack:
                ti_pass += 1
                lp = int(r[f"{opt}.listPriceCents"]) / 100
                ref = int(r["referenceFeeCents"]) / 100
                print(f"  PASS {r['id']} {opt:10s} {pk0}[s30={sup30[pk0]},s55={s55}]->{dl0}->{dl1} d0={d0}m d1={d1}m slack0={slack0}m slack1={slack1}m lp=€{lp:.0f} ref=€{ref:.0f} (was {r['outcome']})")
                break
    print(f"Total 2-leg trade-ins passing sequential slack + gate: {ti_pass} / 23 (was 2 won / 21 declined)")

    print("=== 2. DECLINED THIN PICKUPS BY DEST SUPPLY & DRIVE ===")
    thin_buckets = Counter()
    for r in reqs:
        lps = [int(r[f"{k}.listPriceCents"]) for k in ("same_day", "next_day", "within_3_days") if r[f"{k}.listPriceCents"]]
        qs = [int(r[f"{k}.quoteCents"]) for k in ("same_day", "next_day", "within_3_days") if r[f"{k}.quoteCents"]]
        if max(qs) < 3.5 * max(lps):
            continue
        ls = legs_by_req[r["id"]]
        if len(ls) != 1:
            continue
        pk, dl = ls[0]["pickup.placeId"], ls[0]["delivery.placeId"]
        d = drv_min(pk, dl)
        has_slow = bool(r["next_day.listPriceCents"] or r["within_3_days.listPriceCents"])
        if sup55[pk] < 22 and sup70[pk] < 30 and has_slow:
            ds = sup30[dl]
            db = "dl>=200(hub)" if ds >= 200 else ("dl=50..199(reg)" if ds >= 50 else "dl<50(thin)")
            drvb = "drv<=220" if d <= 220 else ("drv=221..300" if d <= 300 else "drv>300")
            thin_buckets[(db, drvb)] += 1
    for k, v in sorted(thin_buckets.items()):
        print(f"  {str(k):40s}: {v}")

    print("=== 3. RING (HYVINKAA / s30<22, s55>=200) SAME_DAY DROPPED ===")
    ring_sd = Counter()
    for r in reqs:
        ls = legs_by_req[r["id"]]
        if len(ls) != 1:
            continue
        pk, dl = ls[0]["pickup.placeId"], ls[0]["delivery.placeId"]
        d = drv_min(pk, dl)
        if sup30[pk] < 22 and sup55[pk] >= 200 and r["same_day.listPriceCents"]:
            only_sd = not (r["next_day.listPriceCents"] or r["within_3_days.listPriceCents"])
            dl_b = "to_hub(>=200)" if sup30[dl] >= 200 else ("to_reg(>=50)" if sup30[dl] >= 50 else "to_thin")
            drv_b = "d<=60" if d <= 60 else ("d=61..100" if d <= 100 else "d>100")
            ring_sd[(only_sd, dl_b, drv_b)] += 1
    for k, v in sorted(ring_sd.items()):
        print(f"  only_sd={str(k[0]):5s} {k[1]:15s} {k[2]:10s}: {v}")


if __name__ == "__main__":
    main()
