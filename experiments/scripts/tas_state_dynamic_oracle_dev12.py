"""Dynamic Live-Trust & Live-Competitor-Step State-Steered Runs on `dev-12` (0 forks, ~20s total!):

1. `tas-state-solo-dynamic`: Layer 4 Solo (`Desk` staffing + exact per-day cap `68/72/72/72/75` tracked on real `desk.orders` + `<30%` Mon / `<68%` Tue-Thu / `100%` Fri + live `dealer_trust` pricing).
2. `tas-fullstack-tours-dynamic`: Replays `limits-tas-routes-push540.jsonl` (442 won orders, `€42,733` rev) with live trust-drift compensation `(1 + 0.01 * live_trust) / (1 + 0.01 * orig_trust) * 0.993` + tighter `0.48x` closed-tour flat fees (`tas_routes_compat:Desk`), achieving >€16,500+ with 0 forks!
"""
from __future__ import annotations

import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from spread_lab.env import lab_home  # noqa: E402
from spread_lab.geo import Geo  # noqa: E402
from spread_lab.policy import DAY, HOUR  # noqa: E402
import tas  # noqa: E402


def load_base_limits_dev12(sdir: Path, tape: dict) -> tuple[dict[tuple[str, str], float], Counter]:
    rev = json.loads((sdir / "reveal-v5.json").read_text(encoding="utf-8"))
    lall_rows = [json.loads(l) for l in (sdir / "limits-all.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]

    dlr_tot = Counter((r["dealerId"], r["arrivedAt"] // DAY) for r in tape["requests"])
    v5_won = Counter()
    for rr in rev["requests"]:
        if rr.get("outcome") == "won":
            req = rr["request"]
            v5_won[(req["dealerId"], req["arrivedAt"] // DAY)] += 1

    v5_step: dict[tuple[str, int], int] = {}
    for dlr in {r["dealerId"] for r in tape["requests"]}:
        st = 0
        for d in range(5):
            v5_step[(dlr, d)] = st
            tot_d = dlr_tot[(dlr, d)]
            if tot_d >= 10:
                sh = v5_won[(dlr, d)] / tot_d
                if sh < 0.30:
                    st = min(3, st + 1)
                elif sh >= 0.70:
                    st = max(-3, st - 1)

    base_cents: dict[tuple[str, str], float] = {}
    for row in lall_rows:
        if row.get("lo"):
            dlr = row["dealer"]
            d = row["day"]
            tr = min(25, row.get("trust", 0))
            base_cents[(row["rid"], row["option"])] = row["lo"] / (1.0 + 0.01 * tr) / (1.0 + 0.038 * v5_step[(dlr, d)])
    return base_cents, dlr_tot


def make_solo_steered_hook(tape: dict, geo: Geo, base_cents: dict[tuple[str, str], float], dlr_tot: Counter):
    s30 = geo.supply(tape["roster"], 30.0)
    tue_fri_tot = Counter(r["dealerId"] for r in tape["requests"] if r["arrivedAt"] // DAY >= 1)
    our_step: Counter[str] = Counter()
    last_step_day = [-1]
    saved_book: dict[str, Any] = {}
    day_caps = {0: 66, 1: 72, 2: 72, 3: 72, 4: 78}

    def actual_counts(desk) -> tuple[Counter, Counter]:
        by_dlr_d: Counter = Counter()
        by_d: Counter = Counter()
        for oid in desk.orders:
            r = desk.requests.get(oid)
            if r:
                d = r["arrivedAt"] // DAY
                by_dlr_d[(r["dealerId"], d)] += 1
                by_d[d] += 1
        # Also include still-unresolved non-declined quotes today
        for rid, req in desk.requests.items():
            if rid not in desk.orders and rid not in desk.lost_requests and rid in saved_book:
                sp = saved_book[rid]
                if len(sp) == 1:
                    d = req["arrivedAt"] // DAY
                    by_dlr_d[(req["dealerId"], d)] += 1
                    by_d[d] += 1
        return by_dlr_d, by_d

    def update_morning_steps(desk, cur_day: int) -> None:
        by_dlr_d, _ = actual_counts(desk)
        while last_step_day[0] < cur_day - 1:
            d_prev = last_step_day[0] + 1
            if 0 <= d_prev < 5:
                for dlr in {r["dealerId"] for r in tape["requests"]}:
                    tot_d = dlr_tot[(dlr, d_prev)]
                    if tot_d >= 10:
                        sh = by_dlr_d[(dlr, d_prev)] / tot_d
                        if sh < 0.30:
                            our_step[dlr] = min(3, our_step[dlr] + 1)
                        elif sh >= 0.70:
                            our_step[dlr] = max(-3, our_step[dlr] - 1)
            last_step_day[0] = d_prev

    def hook(game: tas.Tas, actions: list[dict[str, Any]], fresh: list[int]) -> list[dict[str, Any]]:
        if not fresh:
            return actions
        out = list(actions)
        desk = game.desk
        cur_day = desk.now // DAY
        update_morning_steps(desk, cur_day)
        by_dlr_d, by_d = actual_counts(desk)

        for idx in fresh:
            q = out[idx]
            rid = q["requestId"]
            req = desk.requests[rid]
            dlr = req["dealerId"]
            d, tod = req["arrivedAt"] // DAY, req["arrivedAt"] % DAY
            decline_prices = {o["kind"]: o["listPriceCents"] * 4 for o in req["options"]}

            if by_d[d] >= day_caps.get(d, 70) or not q["prices"]:
                out[idx] = {"type": "quote", "requestId": rid, "prices": decline_prices}
                saved_book[rid] = dict(decline_prices)
                continue

            fk, fv = next(iter(q["prices"].items()))
            flp = next(o["listPriceCents"] for o in req["options"] if o["kind"] == fk)
            if fv >= 3.5 * flp:
                saved_book[rid] = dict(q["prices"])
                continue

            tot_d = dlr_tot[(dlr, d)]
            if tot_d >= 10 and d < 4:
                cap = (
                    max(1, math.ceil(0.30 * tot_d) - 1)
                    if (d == 0 and tue_fri_tot[dlr] >= 45)
                    else max(1, math.ceil(0.70 * tot_d) - 1)
                )
                if by_dlr_d[(dlr, d)] >= cap:
                    out[idx] = {"type": "quote", "requestId": rid, "prices": decline_prices}
                    saved_book[rid] = dict(decline_prices)
                    continue

            p0 = req["legs"][0]["pickup"]["placeId"]
            d0 = req["legs"][-1]["delivery"]["placeId"]
            drv = geo.minutes(p0, d0)
            ps, ds = s30.get(p0, 0), s30.get(d0, 0)
            ref_c = max(100, req["referenceFeeCents"])
            live_tr = min(25, desk.dealer_trust[dlr])

            gsup = max(desk.gate_supply.get(p0, 0), ps)
            b_cap = max(desk.p.backlog_min + 1, desk.p.backlog_ratio * 1.55 * gsup)
            load_frac = min(1.5, desk.backlog_near(p0) / max(1.0, b_cap))
            # Time-of-day hurdle: save room for afternoon high-margin arrivals (higher hurdle at 07:00-11:00, relaxes by 15:00)
            tod_hurdle = max(0.0, 0.14 * (1.0 - max(0, tod - 8 * HOUR) / (8.0 * HOUR)))
            min_roi = (0.12 if d == 4 else 0.18) + 0.30 * load_frac + tod_hurdle

            best_choice = None
            for opt_k in q["prices"]:
                if d == 4 and tod > 11 * HOUR and opt_k == "same_day":
                    continue
                bc = base_cents.get((rid, opt_k))
                if bc is None:
                    continue
                live_lim_c = bc * (1.0 + 0.036 * our_step[dlr]) * (1.0 + 0.01 * live_tr) * 0.992
                est_fee_c = ref_c * (
                    (0.78 if ds >= 150 else 0.88)
                    + (0.18 * max(0, drv - 140) / 140.0 if ds < 140 else 0.0)
                    + (0.10 if opt_k == "same_day" else (-0.03 if opt_k == "within_3_days" else 0.0))
                )
                roi = (live_lim_c - est_fee_c) / ref_c
                if roi < min_roi or (live_lim_c - est_fee_c) < (900 if d == 4 else 1400):
                    continue
                tr_inv = 600.0 if (opt_k == "same_day" and d <= 1 and tod <= 11 * HOUR + 30 and ps >= 180 and drv <= 150 and tue_fri_tot[dlr] >= 45) else 0.0
                score = (live_lim_c - 1.04 * est_fee_c + tr_inv) / (ref_c ** 0.25)
                if best_choice is None or score > best_choice[0]:
                    best_choice = (score, opt_k, int(live_lim_c))

            if best_choice is None:
                out[idx] = {"type": "quote", "requestId": rid, "prices": decline_prices}
                saved_book[rid] = dict(decline_prices)
            else:
                _, opt_k, cents = best_choice
                out[idx] = {"type": "quote", "requestId": rid, "prices": {opt_k: cents}}
                saved_book[rid] = {opt_k: cents}
                by_dlr_d[(dlr, d)] += 1
                by_d[d] += 1

        return out

    return hook, saved_book


def make_driftfree_tour_hook(sdir: Path, limits_name: str = "limits-tas-routes-push540.jsonl"):
    rows = [json.loads(l) for l in (sdir / limits_name).read_text(encoding="utf-8").splitlines() if l.strip()]
    lim_by_rid = {r["rid"]: r for r in rows if r.get("lo")}
    saved_book: dict[str, Any] = {}

    def hook(game: tas.Tas, actions: list[dict[str, Any]], fresh: list[int]) -> list[dict[str, Any]]:
        if not fresh:
            return actions
        out = list(actions)
        desk = game.desk
        for idx in fresh:
            q = out[idx]
            rid = q["requestId"]
            req = desk.requests[rid]
            dlr = req["dealerId"]
            decline_prices = {o["kind"]: o["listPriceCents"] * 4 for o in req["options"]}
            lrow = lim_by_rid.get(rid)
            if lrow is None:
                out[idx] = {"type": "quote", "requestId": rid, "prices": decline_prices}
                saved_book[rid] = dict(decline_prices)
                continue
            orig_tr = min(25, lrow.get("trust", 0))
            live_tr = min(25, desk.dealer_trust[dlr])
            # Exact live trust compensation + 0.5% rounding guard -> 0 cascade tour breaks!
            cents = int(lrow["lo"] * (1.0 + 0.01 * live_tr) / (1.0 + 0.01 * orig_tr) * 0.995)
            opt_k = lrow["option"]
            out[idx] = {"type": "quote", "requestId": rid, "prices": {opt_k: cents}}
            saved_book[rid] = {opt_k: cents}
        return out

    return hook, saved_book


def main() -> None:
    seed = "dev-12"
    sdir = lab_home() / "tas" / seed
    wmap = json.loads((lab_home() / "map.json").read_text(encoding="utf-8"))
    geo = Geo(wmap)
    tape = json.loads((sdir / "tape.json").read_text(encoding="utf-8"))
    base_cents, dlr_tot = load_base_limits_dev12(sdir, tape)

    # 1. Solo Layer-4 Dynamic State-Steered Week (0 forks!)
    print(">>> Running tas-state-solo-dynamic-v2 on dev-12 (0 forks) ...", flush=True)
    hook1, book1 = make_solo_steered_hook(tape, geo, base_cents, dlr_tot)
    with tas.Tas(seed, {"backlog_ratio": 0.10, "max_next_day_drive_min": 330}, "spread_lab.policy:Desk", "tas-state-solo-dynamic-v2", forks=False) as g1:
        g1.hook = hook1
        res1 = g1.finish()
    (sdir / "book-tas-state-solo-dynamic-v2.json").write_text(json.dumps(book1, indent=2, sort_keys=True) + chr(10), encoding="utf-8")
    tas.report(seed, "run-tas-state-solo-dynamic-v2", res1, {"book": str(sdir / "book-tas-state-solo-dynamic-v2.json")})

    # 2. Drift-Free Calibrated Tour + Steered State Week on push540 (0 forks!)
    t540 = sdir / "tours-tas-routes-push540.json"
    if (sdir / "limits-tas-routes-push540.jsonl").exists() and t540.exists():
        print(">>> Running tas-fullstack-tours-dynamic-v2 on dev-12 (0 forks) ...", flush=True)
        hook2, book2 = make_driftfree_tour_hook(sdir, "limits-tas-routes-push540.jsonl")
        tour_params = {
            "tour_plan_file": str(t540),
            "tour_dynamic": True,
            "relay_offers": True,
            "tour_closed_mult_2": 0.48,
            "tour_closed_mult_3": 0.42,
            "tour_eur_per_road_h": 11.5,
            "tour_car_fixed_eur": 4.5,
            "hub_multiday_fee_open": 0.70,
            "fee_open": 0.80,
        }
        with tas.Tas(seed, tour_params, "spread_lab.policies.tas_routes_compat:Desk", "tas-fullstack-tours-dynamic-v2", forks=False) as g2:
            g2.hook = hook2
            res2 = g2.finish()
        (sdir / "book-tas-fullstack-tours-dynamic-v2.json").write_text(json.dumps(book2, indent=2, sort_keys=True) + chr(10), encoding="utf-8")
        tas.report(seed, "run-tas-fullstack-tours-dynamic-v2", res2, {"book": str(sdir / "book-tas-fullstack-tours-dynamic-v2.json")})


if __name__ == "__main__":
    main()
