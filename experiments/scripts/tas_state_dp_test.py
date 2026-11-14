"""Test the exact 5-day (competitor_step, trust) Dynamic Program per dealer across all 4 TAS seeds (offline)."""
from __future__ import annotations

import json
import statistics
from collections import Counter, defaultdict

from spread_lab.env import lab_home, load_dotenv
from spread_lab.geo import Geo, load_map
from spread_lab.lab import CountingClient
from spread_lab.notes import parse_note_v2, shift_business_days, window_from_note

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"]


def detect_world_events(seed: str, tape: dict, geo: Geo, names: dict[str, str]) -> dict:
    """Detect snow windows from tape forecasts, Flu day from reveal-v5 views, and War/Outage from limits-won-apply or reveal-v5."""
    dpath = lab_home() / "tas" / seed
    snow = []
    for fc in tape.get("forecasts", []):
        snow.append({"from": fc["from"], "to": fc["to"], "places": set(fc["placeIds"])})

    flu_day = None
    rev_path = dpath / "reveal-v5.json"
    if rev_path.exists():
        rev = json.loads(rev_path.read_text(encoding="utf-8"))
        morn = defaultdict(set)
        for v in rev.get("views", []):
            d, tod = v["at"] // 1440, v["at"] % 1440
            if d < 5 and 420 <= tod <= 780:
                morn[d].add(v["driverId"])
        if morn:
            med_v = statistics.median(len(morn[d]) for d in range(5))
            for d in range(5):
                if len(morn[d]) < 0.65 * med_v:
                    flu_day = d

    war_day = None
    outage = None  # (day, center_place_id)
    lwa = dpath / "limits-won-apply.jsonl"
    if lwa.exists() and lwa.stat().st_size > 20000:
        lines = [json.loads(l) for l in lwa.read_text(encoding="utf-8").splitlines() if l.strip()]
        day_meds = {}
        for d in range(5):
            dt = [l for l in lines if l["day"] == d and 480 <= (l["at"] % 1440) <= 1080 and l.get("x")]
            if dt:
                day_meds[d] = statistics.median(l["x"] / (1 + 0.01 * l["trust"]) for l in dt)
        if day_meds:
            min_d = min(day_meds, key=lambda k: day_meds[k])
            if day_meds[min_d] < 1.32:
                war_day = min_d
            # Outage: either regional spike or overall med_norm > 1.78
            best_out = None
            for d in range(5):
                if d == war_day:
                    continue
                dt = [l for l in lines if l["day"] == d and 480 <= (l["at"] % 1440) <= 1080 and l.get("x")]
                for p_id in names:
                    inc = [l["x"] / (1 + 0.01 * l["trust"]) for l in dt if geo.line_km(p_id, l["pickup"]) <= 80.0]
                    if len(inc) >= 5:
                        m_in = statistics.median(inc)
                        if m_in >= 1.68 and (best_out is None or m_in > best_out[0]):
                            best_out = (m_in, d, p_id)
            if best_out:
                outage = (best_out[1], best_out[2])
    else:
        # Fallback from reveal-v5 win rates & mults (e.g. dev-07 before limits-won-apply finishes)
        if rev_path.exists():
            rev = json.loads(rev_path.read_text(encoding="utf-8"))
            rev_reqs = {rr["request"]["id"]: rr for rr in rev.get("requests", [])}
            day_won_x = defaultdict(list)
            day_win_rate = {}
            for d in range(5):
                q, w = 0, 0
                for r in tape["requests"]:
                    if r["arrivedAt"] // 1440 != d or not (480 <= r["arrivedAt"] % 1440 <= 1080):
                        continue
                    rr = rev_reqs.get(r["id"])
                    if not rr or not rr.get("quote"):
                        continue
                    by_k = {o["kind"]: o["listPriceCents"] for o in r["options"]}
                    fk = next(iter(rr["quote"]))
                    m = rr["quote"][fk] / by_k[fk]
                    if m >= 3.5:
                        continue
                    q += 1
                    if rr.get("outcome") == "won":
                        w += 1
                        opt = rr.get("option") or fk
                        day_won_x[d].append(rr["quote"][opt] / by_k[opt])
                day_win_rate[d] = w / q if q else 0
            min_d = min(range(5), key=lambda d: (statistics.median(day_won_x[d]) if day_won_x[d] else 9.0))
            if day_won_x[min_d] and statistics.median(day_won_x[min_d]) < 1.33:
                war_day = min_d
            max_d = max(range(5), key=lambda d: (statistics.median(day_won_x[d]) if day_won_x[d] else 0.0))
            if day_won_x[max_d] and statistics.median(day_won_x[max_d]) > 1.70:
                outage = (max_d, "helsinki")

    return {"snow": snow, "flu_day": flu_day, "war_day": war_day, "outage": outage}


def evaluate_request_options(
    r: dict,
    geo: Geo,
    supply30: dict[str, int],
    supply55: dict[str, int],
    events: dict,
    known_base_x: dict[str, float],
) -> list[dict]:
    """Return feasible options for request r with estimated base_x (at trust=0, step=0) and expected driver fee."""
    if r.get("note"):
        pn = parse_note_v2(r["note"], r["arrivedAt"])
        if pn.unsure:
            return []
        extra_days = (
            max(
                (
                    max(0, pn.ready_at // 1440 - leg["pickup"]["window"]["from"] // 1440)
                    for leg in r["legs"]
                    if not leg["pickup"]["privateAddress"]
                ),
                default=0,
            )
            if pn.ready_at is not None
            else 0
        )
    else:
        extra_days = 0

    legs = r["legs"]
    p_id = legs[0]["pickup"]["placeId"]
    d_id = legs[-1]["delivery"]["placeId"]
    s30, s55, ds30 = supply30[p_id], supply55[p_id], supply30[d_id]

    drive = sum(geo.minutes(leg["pickup"]["placeId"], leg["delivery"]["placeId"]) for leg in legs)
    if len(legs) == 2:
        drive += geo.minutes(legs[0]["delivery"]["placeId"], legs[1]["pickup"]["placeId"])

    if s55 < 22 and not (ds30 >= 90 and drive <= 220):
        return []

    ready = max(
        [r["arrivedAt"]]
        + [
            window_from_note(
                r["note"],
                leg["pickup"]["window"],
                "pickup",
                v2=True,
                arrived_at=r["arrivedAt"],
                private_address=leg["pickup"]["privateAddress"],
            )["from"]
            for leg in legs
        ]
    )

    # Check snow overlap
    in_snow = any(
        (p_id in sw["places"] or d_id in sw["places"]) and not (ready >= sw["to"] or ready + 720 <= sw["from"])
        for sw in events["snow"]
    )
    eff_drive = int(drive * (1.30 if in_snow else 1.0))

    d = r["arrivedAt"] // 1440
    tod = r["arrivedAt"] % 1440
    daytime = 480 <= tod <= 1080

    # Base limit multiplier at trust=0, step=0
    if r["id"] in known_base_x:
        base_x = known_base_x[r["id"]]
    else:
        base_x = 1.50
        if daytime and events["war_day"] == d:
            base_x *= 0.79
        elif daytime and events["outage"] and events["outage"][0] == d and geo.line_km(events["outage"][1], p_id) <= 80.0:
            base_x *= 1.22

    ref_eur = r["referenceFeeCents"] / 100.0
    if s30 >= 200:
        fee_mult = 0.84 if ds30 >= 90 else 0.90
    elif s55 >= 200:
        fee_mult = 0.88 if ds30 >= 200 else 0.96
    elif s30 >= 40:
        fee_mult = 0.94
    elif s30 >= 22:
        fee_mult = 1.02
    else:
        fee_mult = 1.04

    out = []
    for o in r["options"]:
        kind = o["kind"]
        if kind == "same_day":
            if in_snow or events["flu_day"] == d:
                continue
            if s30 < 80 and not (s55 >= 200 and ds30 >= 200 and drive <= 135):
                continue
            if drive > 260 or (d == 4 and drive >= 180):
                continue
        dl = shift_business_days(o["deadline"], extra_days)
        dl = min(
            window_from_note(
                r["note"],
                {"from": leg["delivery"]["window"]["from"], "to": max(leg["delivery"]["window"]["from"], dl)},
                "delivery",
                v2=True,
                arrived_at=r["arrivedAt"],
                private_address=leg["delivery"]["privateAddress"],
            )["to"]
            for leg in legs
        )
        if kind == "next_day" and eff_drive > 410 and dl // 1440 <= ready // 1440 + 1:
            continue
        if s30 < 60 and s55 < 200 and eff_drive > 280 and dl // 1440 <= ready // 1440 + 1:
            continue
        slack = dl - ready - eff_drive
        if slack < 210 + 0.5 * eff_drive:
            continue

        opt_fee = ref_eur * (fee_mult + (0.06 if kind == "same_day" else (-0.03 if kind == "within_3_days" else 0.0)))
        deliv_day = d if kind == "same_day" else min(5, dl // 1440)
        out.append(
            {
                "kind": kind,
                "list_eur": o["listPriceCents"] / 100.0,
                "base_lim_eur": (o["listPriceCents"] / 100.0) * base_x,
                "fee_eur": opt_fee,
                "deliv_day": deliv_day,
                "slack": slack,
                "s30": s30,
                "s55": s55,
            }
        )
    return out


def solve_dealer_dp(dlr: str, dlr_reqs: list[dict], eval_map: dict[str, list[dict]]) -> dict:
    """Exact 5-day DP over (day d, comp_step s in -3..3, trust tr in 0..25)."""
    by_day = defaultdict(list)
    for r in dlr_reqs:
        by_day[r["arrivedAt"] // 1440].append(r)

    # Precompute future list volume for quick intra-day candidate ordering
    rem_list = {}
    acc = 0.0
    for d in range(4, -1, -1):
        rem_list[d] = acc
        acc += sum(max(o["listPriceCents"] for o in r["options"]) / 100.0 for r in by_day[d])

    STEP_MULT = 0.037
    TRUST_MULT = 0.0105

    memo: dict[tuple[int, int, int], tuple[float, list]] = {}

    def dp(d: int, s: int, tr: int) -> tuple[float, list]:
        if d >= 5:
            return 0.0, []
        key = (d, s, tr)
        if key in memo:
            return memo[key]

        n_tot = len(by_day[d])
        if n_tot < 10 or d == 4:
            regimes = [("FREE", n_tot, s)]
        else:
            regimes = [
                ("LOW", (30 * n_tot - 1) // 100, min(3, s + 1)),
                ("MID", (68 * n_tot) // 100, s),
                ("HIGH", n_tot, max(-3, s - 1)),
            ]

        # Score each candidate request on day d at state (s, tr)
        cands = []
        price_factor = (1.0 + STEP_MULT * s) * (1.0 + TRUST_MULT * min(25, tr))
        future_1pct_val = 0.0105 * 0.55 * 1.50 * rem_list[d]  # approx value of +1 trust for remaining days
        for r in by_day[d]:
            opts = eval_map.get(r["id"], [])
            if not opts:
                continue
            # Pick best option at current state (considering fast trust if tr < 25)
            best_o = None
            best_score = -1e9
            for o in opts:
                imm = o["base_lim_eur"] * price_factor - o["fee_eur"]
                # Fast delivery bonus if tr < 25 and deliv_day == d (same_day counts for d+1!)
                fast_bonus = (0.35 * future_1pct_val / max(1, 5 - d)) if (tr < 25 and o["deliv_day"] == d) else 0.0
                if imm >= 12.0 and imm + fast_bonus > best_score:
                    best_score = imm + fast_bonus
                    best_o = (imm, o)
            if best_o is not None:
                cands.append((best_score, best_o[0], best_o[1], r["id"]))

        cands.sort(key=lambda x: -x[0])

        best_val = -1e18
        best_plan = []
        for reg_name, cap, next_s in regimes:
            chosen = cands[:cap]
            day_profit = sum(x[1] for x in chosen)
            # Count how many chosen orders deliver before tomorrow vs later
            # Approximate trust entering d+1: orders with deliv_day <= d+1 (same_day on d, or next_day from d delivered on d/d+1)
            # More conservatively: same_day adds +1 by d+1, next_day adds +0.7 by d+1 and +1 by d+2 -> integer: same_day + half of next_day
            sd_cnt = sum(1 for x in chosen if x[2]["kind"] == "same_day")
            nd_cnt = len(chosen) - sd_cnt
            next_tr = min(25, tr + sd_cnt + (nd_cnt * 2) // 3)
            fut_val, fut_plan = dp(d + 1, next_s, next_tr)
            tot_val = day_profit + fut_val
            if tot_val > best_val:
                best_val = tot_val
                best_plan = [(d, reg_name, len(chosen), n_tot, s, next_s, tr, next_tr, round(day_profit, 1))] + fut_plan

        memo[key] = (best_val, best_plan)
        return memo[key]

    tot_v, plan = dp(0, 0, 0)
    return {"dealer": dlr, "total_est_margin": round(tot_v, 1), "plan": plan}


def main() -> None:
    load_dotenv()
    m = load_map(CountingClient())
    geo = Geo(m)
    names = {p["id"]: p.get("name", p["id"])[:10] for p in m["places"]}

    for seed in ("dev-12", "dev-01", "dev-08", "dev-07"):
        dpath = lab_home() / "tas" / seed
        tape = json.loads((dpath / "tape.json").read_text(encoding="utf-8"))
        roster = tape["roster"]
        supply30 = {p_id: sum(1 for d in roster if geo.line_km(d["homePlaceId"], p_id) <= 30.0) for p_id in names}
        supply55 = {p_id: sum(1 for d in roster if geo.line_km(d["homePlaceId"], p_id) <= 55.0) for p_id in names}
        events = detect_world_events(seed, tape, geo, names)

        known_base_x = {}
        lwa = dpath / "limits-won-apply.jsonl"
        if lwa.exists() and lwa.stat().st_size > 20000:
            for line in lwa.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    if row.get("x"):
                        known_base_x[row["rid"]] = row["x"] / (1 + 0.01 * row["trust"])

        eval_map = {
            r["id"]: evaluate_request_options(r, geo, supply30, supply55, events, known_base_x)
            for r in tape["requests"]
        }

        by_dlr = defaultdict(list)
        for r in tape["requests"]:
            by_dlr[r["dealerId"]].append(r)

        print("=" * 95)
        out_str = f"{DAYS[events['outage'][0]]}@{names[events['outage'][1]]}" if events["outage"] else "None"
        war_str = DAYS[events["war_day"]] if events["war_day"] is not None else "None"
        flu_str = DAYS[events["flu_day"]] if events["flu_day"] is not None else "None"
        print(f"SEED {seed} | War={war_str} | Outage={out_str} | Flu={flu_str} | Snow={len(events['snow'])}")

        tot_all = 0.0
        tot_wins = 0
        top_dlrs = sorted(by_dlr, key=lambda k: -len(by_dlr[k]))
        for idx, dlr in enumerate(top_dlrs):
            res = solve_dealer_dp(dlr, by_dlr[dlr], eval_map)
            tot_all += res["total_est_margin"]
            tot_wins += sum(p[2] for p in res["plan"])
            if idx < 5:
                p_str = " | ".join(
                    f"{DAYS[p[0]]}:{p[1]}({p[2]}/{p[3]},s={p[4]}->{p[5]},tr={p[6]}->{p[7]},€{p[8]:.0f})"
                    for p in res["plan"]
                )
                print(f"  {dlr} (est €{res['total_est_margin']:,.0f}): {p_str}")
        print(f"  TOTAL DP UNCONSTRAINED ESTIMATE: €{tot_all:,.0f} across {tot_wins} won orders")


if __name__ == "__main__":
    main()
