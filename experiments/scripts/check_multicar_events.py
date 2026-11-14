"""Verify exact server opening-hours and driving/stop-duration semantics against order.lastPickupAt in v3 reveals."""
from __future__ import annotations

import csv
import json
from pathlib import Path

csv.field_size_limit(10**9)
DAY = 24 * 60


def is_open(row: dict[str, str], side: str, t: int, inclusive_close: bool) -> bool:
    priv = row[f"{side}.privateAddress"] == "true"
    w_from = int(row[f"{side}.window.from"])
    w_to = int(row[f"{side}.window.to"])
    if priv:
        return (w_from <= t <= w_to) if inclusive_close else (w_from <= t < w_to)
    dow = (t // DAY) % 7
    tod = t % DAY
    if dow == 6:
        return False
    if dow == 5:
        sop = row.get(f"{side}.hours.saturday.opens", "")
        if not sop:
            return False
        op, cl = int(sop), int(row[f"{side}.hours.saturday.closes"])
    else:
        wds = json.loads(row[f"{side}.hours.weekdays"])
        if dow not in wds:
            return False
        op, cl = int(row[f"{side}.hours.opens"]), int(row[f"{side}.hours.closes"])
    return (op <= tod <= cl) if inclusive_close else (op <= tod < cl)


def main() -> None:
    folder = sorted(Path("/tmp/reveals-v3").iterdir())[0]
    roads = {(r["from"], r["to"]): (float(r["km"]), int(r["minutes"])) for r in csv.DictReader(open(folder / "roads.csv"))}
    reqs = {r["id"]: r for r in csv.DictReader(open(folder / "requests.csv"))}
    legs = {}
    for l in csv.DictReader(open(folder / "legs.csv")):
        legs.setdefault(l["requestId"], []).append(l)
    for k in legs:
        legs[k].sort(key=lambda x: int(x["leg"]))

    for inc in (False, True):
        exact = 0
        total = 0
        diffs = []
        for e in csv.DictReader(open(folder / "events.csv")):
            if e["kind"] != "order_won":
                continue
            oid = e["order.id"]
            req = reqs[oid]
            if req.get("note") or len(legs[oid]) != 1:
                continue
            l = legs[oid][0]
            dl = int(e["order.deadline"])
            lpa = int(e["order.lastPickupAt"])
            pk, dlv = l["pickup.placeId"], l["delivery.placeId"]
            km, drv = roads[(pk, dlv)]
            chg = 40 if (l["car.electric"] == "true" and l["car.chargePercent"] and int(l["car.chargePercent"]) < 30 and km > 200.0) else 0
            w_from = int(l["pickup.window.from"])
            best_t = None
            for t in range(dl - drv - chg, w_from - 1, -1):
                if is_open(l, "pickup", t, inc) and (l["delivery.privateAddress"] == "true" or is_open(l, "delivery", t + drv + chg, inc)):
                    if l["delivery.privateAddress"] == "true":
                        if t + drv + chg <= dl:
                            best_t = t
                            break
                    else:
                        best_t = t
                        break
            total += 1
            if best_t == lpa:
                exact += 1
            elif len(diffs) < 5:
                diffs.append((oid, lpa, best_t, drv, chg, dl, l["pickup.hours.closes"], l["delivery.hours.closes"], l["delivery.privateAddress"]))
        print(f"inclusive_close={inc}: exact={exact}/{total}, sample diffs={diffs}")


if __name__ == "__main__":
    main()
