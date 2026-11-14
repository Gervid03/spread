"""Compute empirical class economics and implied margin/win/lateness curves vs target win rate w_c
across the 16 revealed champion v3T dev worlds (slot-free).
"""
from __future__ import annotations

import collections
import json
import math
from pathlib import Path

from scout_cp_classes import drv_cls, hav, rd, sup_cls

B_SLOPE = 11.92  # measured logistic slope in log(quote/list) from 73,718 L8 quotes


def logit(p: float) -> float:
    p = max(1e-4, min(1 - 1e-4, p))
    return math.log(p / (1 - p))


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def main() -> None:
    folders = sorted(p for p in Path("runs/reveals/dev16").iterdir() if (p / "requests.csv").exists())
    n_w = len(folders)
    cls_data = collections.defaultdict(lambda: collections.Counter())

    for d in folders:
        places = {p["id"]: (float(p["lat"]), float(p["lon"])) for p in rd(d, "places")}
        line = {(a, b): hav(places[a], places[b]) for a in places for b in places}
        roads = {(r["from"], r["to"]): (float(r["km"]), int(r["minutes"])) for r in rd(d, "roads")}
        drivers = {x["id"]: x for x in rd(d, "drivers")}
        homes = collections.Counter(x["homePlaceId"] for x in drivers.values())
        supply = {p: sum(n for h, n in homes.items() if line[(p, h)] <= 30.0) for p in places}

        reqs = {r["id"]: r for r in rd(d, "requests")}
        legs_by_req = collections.defaultdict(list)
        for l in rd(d, "legs"):
            legs_by_req[l["requestId"]].append(l)
        for rid in legs_by_req:
            legs_by_req[rid].sort(key=lambda x: int(x["leg"]))

        events = rd(d, "events")
        late_orders = set()
        ledger = collections.defaultdict(lambda: collections.Counter())
        for e in events:
            if e["kind"] == "ledger" and e.get("line.orderId"):
                oid = e["line.orderId"]
                k = e["line.kind"]
                c = int(e["line.cents"])
                ledger[oid][k] += c
                ledger[oid]["net"] += c
                if k in ("late_refund", "undelivered_penalty"):
                    late_orders.add(oid)

        for rid, r in reqs.items():
            rlegs = legs_by_req[rid]
            pick = rlegs[0]["pickup.placeId"]
            drive = sum(roads[(l["pickup.placeId"], l["delivery.placeId"])][1] for l in rlegs)
            if len(rlegs) == 2:
                drive += roads[(rlegs[0]["delivery.placeId"], rlegs[1]["pickup.placeId"])][1]
            c9 = f"{sup_cls(supply[pick])}-{drv_cls(drive)}"

            ref_fee = int(r["referenceFeeCents"])
            floor_cents = ref_fee * 1.25 / (1.0 - 0.08)
            quoted_opts = []
            for ok in ("same_day", "next_day", "within_3_days"):
                qc, lc = r.get(f"{ok}.quoteCents"), r.get(f"{ok}.listPriceCents")
                if qc and lc:
                    quoted_opts.append((ok, int(qc), int(lc)))
            is_decline = (not quoted_opts) or (len(quoted_opts) == 1 and abs(quoted_opts[0][1] / quoted_opts[0][2] - 4.0) < 0.02)
            if is_decline:
                continue
            is_floored = any(abs(qv - int(floor_cents + 0.5)) <= 2 for _, qv, _ in quoted_opts)
            b = cls_data[c9]
            b["quot"] += 1
            if is_floored:
                b["flr"] += 1
            else:
                b["nrm"] += 1
            if r["outcome"] == "won":
                b["won"] += 1
                if is_floored:
                    b["won_flr"] += 1
                else:
                    b["won_nrm"] += 1
                    b["rev_nrm"] += ledger[rid]["revenue"]
                    b["cost_nrm"] += ledger[rid]["revenue"] - ledger[rid]["net"]
                    if rid in late_orders:
                        b["late_nrm"] += 1
                b["rev"] += ledger[rid]["revenue"]
                b["cost"] += ledger[rid]["revenue"] - ledger[rid]["net"]
                if rid in late_orders:
                    b["late"] += 1

    print("Single-class response curves (holding fleet congestion fixed; d(logit P)/d(log m) = -11.92):")
    order_9 = [f"{s}-{d}" for s in ("hub", "mid", "thin") for d in ("short", "mid", "long")]
    targets = [0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65]
    for c in order_9:
        b = cls_data[c]
        nrm_w = b["nrm"] / n_w
        won_nrm_w = b["won_nrm"] / n_w
        p0 = b["won_nrm"] / max(1, b["nrm"])
        rev0 = (b["rev_nrm"] / 100) / max(1, b["won_nrm"])
        cost0 = (b["cost_nrm"] / 100) / max(1, b["won_nrm"])
        mrg0 = rev0 - cost0
        late0 = b["late_nrm"] / max(1, b["won_nrm"])
        # Unconstrained Lerner peak: 1 - p* = 1 / (B * mrg_rate(p*))
        print()
        print(
            f"{c:<10} | Nrm/w={nrm_w:5.1f}  CurrWinN={p0:5.1%}  Rev/o=€{rev0:5.1f}  Cost/o=€{cost0:5.1f}  "
            f"Mrg/o=€{mrg0:5.1f} ({mrg0/max(1e-6,rev0):4.1%})  LateN={late0:4.1%}"
        )
        row_str = []
        for wt in targets:
            # log(m / m0) needed to shift normal win prob from p0 to wt:
            dlogm = (logit(p0) - logit(wt)) / B_SLOPE
            rev_t = rev0 * math.exp(dlogm)
            # Note: if dlogm < 0, some quotes hit floor; approximate effective shift as 0.85 * dlogm when discounting
            mrg_t = rev_t - cost0
            dwon = nrm_w * (wt - p0)
            dmrg = nrm_w * (wt * mrg_t - p0 * mrg0)
            dlate = dwon * late0
            row_str.append(f"w={wt:.2f}: {dlogm*100:+4.1f}%p ΔW={dwon:+4.1f} Δ€={dmrg:+5.0f} ΔLt={dlate:+4.2f}")
        for i in range(0, len(row_str), 4):
            print("  " + " | ".join(row_str[i : i + 4]))


if __name__ == "__main__":
    main()
