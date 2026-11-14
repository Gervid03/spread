"""Offline lab on cached tape.json + reveal-v5.json + limits-won-apply.jsonl for dev-12 and dev-01."""
from __future__ import annotations

import json
import statistics
from collections import Counter, defaultdict

from spread_lab.env import lab_home, load_dotenv
from spread_lab.geo import Geo, load_map
from spread_lab.lab import CountingClient
from spread_lab.notes import parse_note_v2, shift_business_days, window_from_note

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun", "Mon+", "Tue+", "Wed+"]


def inspect_seed(seed: str, geo: Geo, names: dict[str, str]) -> None:
    dpath = lab_home() / "tas" / seed
    tape = json.loads((dpath / "tape.json").read_text(encoding="utf-8"))
    rev = json.loads((dpath / "reveal-v5.json").read_text(encoding="utf-8"))
    lwa_path = dpath / "limits-won-apply.jsonl"
    if not lwa_path.exists() or lwa_path.stat().st_size == 0:
        return
    lines = [json.loads(l) for l in lwa_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    won_map = {l["rid"]: l for l in lines}
    reqs = {r["id"]: r for r in tape["requests"]}
    roster = tape["roster"]
    supply30 = {p_id: sum(1 for d in roster if geo.line_km(d["homePlaceId"], p_id) <= 30.0) for p_id in names}
    supply55 = {p_id: sum(1 for d in roster if geo.line_km(d["homePlaceId"], p_id) <= 55.0) for p_id in names}

    print("=" * 95)
    print(f"OFFLINE X-RAY FOR {seed}: {len(lines)} won orders in Layer 1")
    tot_ref = sum(l["ref"] for l in lines) / 100.0
    tot_lim = sum(l["lo"] for l in lines if l["lo"]) / 100.0
    tot_desk = sum(l["desk_cents"] for l in lines if l["desk_cents"]) / 100.0
    runs = [json.loads(x) for x in (dpath / "runs.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    l1_run = next((r for r in reversed(runs) if r["name"] == "limits-won-apply"), None)
    actual_fee = -l1_run["ledger"].get("driver_fee", 0) if l1_run else 0
    print(
        f"  Sum(ref)=€{tot_ref:,.2f} | Actual v5 driver_fee=€{actual_fee:,.2f} "
        f"(ratio fee/ref = {actual_fee/tot_ref:.3f}) | Desk rev=€{tot_desk:,.2f} | Limit rev=€{tot_lim:,.2f}"
    )

    # Check exact Outage town & radius on every day!
    for d in range(5):
        daytime = [l for l in lines if l["day"] == d and 480 <= (l["at"] % 1440) <= 1080 and l.get("x")]
        if not daytime:
            continue
        best = None
        for center_id in names:
            in_x = [l["x"] / (1 + 0.01 * l["trust"]) for l in daytime if geo.line_km(center_id, l["pickup"]) <= 80.0]
            out_x = [l["x"] / (1 + 0.01 * l["trust"]) for l in daytime if geo.line_km(center_id, l["pickup"]) > 80.0]
            if len(in_x) >= 5 and len(out_x) >= 3:
                ratio = statistics.median(in_x) / statistics.median(out_x)
                if best is None or ratio > best[0]:
                    best = (ratio, center_id, len(in_x), statistics.median(in_x), len(out_x), statistics.median(out_x))
        all_med = statistics.median(l["x"] / (1 + 0.01 * l["trust"]) for l in daytime)
        if best and best[0] >= 1.12:
            in_towns = sorted({names[p] for p in names if geo.line_km(best[1], p) <= 80.0})
            print(
                f"  {DAYS[d]}: med_norm={all_med:.3f} | OUTAGE CANDIDATE center={names[best[1]]} "
                f"in={best[3]:.3f}(n={best[2]}) vs out={best[5]:.3f}(n={best[4]}) ratio={best[0]:.3f} towns={in_towns}"
            )
        else:
            print(f"  {DAYS[d]}: med_norm={all_med:.3f} (no regional spike >=1.12)")

    # Inspect revealed truth of won orders to find which ones had tricky notes / release / snow / thin towns!
    rev_orders = {o["orderId"]: o for o in rev.get("orders", [])}
    # Check notes among won orders where readyAt > window.from or releasedAt is not None
    tricky = 0
    for oid, ro in rev_orders.items():
        r = reqs[oid]
        for leg_i, rleg in enumerate(ro["legs"]):
            if rleg.get("releasedAt") is not None or rleg["readyAt"] > r["legs"][leg_i]["pickup"]["window"]["from"] + 120:
                tricky += 1
    print(f"  Won orders with delayed readyAt (>2h) or releasedAt: {tricky}/{len(rev_orders)}")

    # Count ALL staffable requests on the tape that v5 MISSED (either lost on price or declined by backlog/supply)!
    missed_good = []
    for r in tape["requests"]:
        if r["id"] in won_map:
            continue
        p_id = r["legs"][0]["pickup"]["placeId"]
        d_id = r["legs"][-1]["delivery"]["placeId"]
        s30 = supply30[p_id]
        s55 = supply55[p_id]
        ds30 = supply30[d_id]
        legs = r["legs"]
        drive = sum(geo.minutes(leg["pickup"]["placeId"], leg["delivery"]["placeId"]) for leg in legs)
        if len(legs) == 2:
            drive += geo.minutes(legs[0]["delivery"]["placeId"], legs[1]["pickup"]["placeId"])
        # Check note safety
        if r.get("note"):
            pn = parse_note_v2(r["note"], r["arrivedAt"])
            if pn.unsure:
                continue
        # Check supply class
        if s55 < 22 and not (ds30 >= 90 and drive <= 240):
            continue
        # Best slow option if ring/thin, or best option with good slack
        best_opt = None
        for o in reversed(r["options"]):  # check slow options first for safety, or highest list*slack
            if (s30 < 22) and o["kind"] == "same_day" and not (s55 >= 200 and ds30 >= 200 and drive <= 135):
                continue
            if o["kind"] == "same_day" and (s30 < 50 or drive > 260):
                continue
            slack = o["deadline"] - max(r["arrivedAt"], legs[0]["pickup"]["window"]["from"]) - drive
            if slack >= 220 + 0.5 * drive:
                best_opt = o
                break
        if best_opt:
            # Estimate limit and fee
            d = r["arrivedAt"] // 1440
            est_x = 1.50 if d < 4 else 1.25
            est_lim = best_opt["listPriceCents"] * est_x / 100.0
            est_fee = r["referenceFeeCents"] * 0.65 / 100.0
            missed_good.append((est_lim - est_fee, d, r["dealerId"], s30, s55, best_opt["kind"], r["id"]))

    by_d = Counter(x[1] for x in missed_good)
    tot_potential = sum(x[0] for x in missed_good if x[0] > 15)
    top200_potential = sum(x[0] for x in sorted(missed_good, reverse=True)[:200])
    print(
        f"  Missed clean staffable requests: {len(missed_good)} across Mon..Fri={dict(sorted(by_d.items()))} | "
        f"gross est margin (>€15) = €{tot_potential:,.0f} (top 200 alone = €{top200_potential:,.0f})"
    )


def main() -> None:
    load_dotenv()
    m = load_map(CountingClient())
    geo = Geo(m)
    names = {p["id"]: p.get("name", p["id"])[:10] for p in m["places"]}
    for seed in ("dev-12", "dev-01", "dev-08", "dev-07"):
        inspect_seed(seed, geo, names)


if __name__ == "__main__":
    main()
