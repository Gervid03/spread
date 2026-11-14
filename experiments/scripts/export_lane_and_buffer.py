"""Verify out-of-sample fit, analyze <2% late buffer classes, and export src/spread_lab/data/lane_table.json."""
from __future__ import annotations

import csv
import json
import math
import statistics as st
from collections import Counter, defaultdict
from pathlib import Path

from fit_acceptance_and_late import (
    CACHE_ROOT,
    build_and_fit_won,
    fit_logistic_fe,
    load_world_data,
    pearson_r,
    shrink_effects,
)
from spread_lab.env import REPO


def center_observed_only(
    places: list[str],
    ref_place: str,
    idx_map: dict[str, int],
    theta: list[float],
    cov: list[list[float]],
    counts: Counter,
    neg_b: float,
) -> dict[str, tuple[float, float]]:
    """Center place effects across observed places (weight = quote count) and convert to log-price units."""
    obs = [p for p in places if counts[p] > 0]
    tot_w = float(sum(counts[p] for p in obs))
    w = {p: (counts[p] / tot_w if counts[p] > 0 else 0.0) for p in places}
    raw = {p: (0.0 if p == ref_place else theta[idx_map[p]]) for p in places}
    mean_eff = sum(w[p] * raw[p] for p in obs)

    non_ref_obs = [p for p in obs if p != ref_place]
    out: dict[str, tuple[float, float]] = {}
    for p in places:
        if counts[p] == 0:
            out[p] = (0.0, 999.0)
            continue
        eff = (raw[p] - mean_eff) / neg_b
        var = 0.0
        for q1 in non_ref_obs:
            c1 = (1.0 if q1 == p else 0.0) - w[q1]
            i1 = idx_map[q1]
            for q2 in non_ref_obs:
                c2 = (1.0 if q2 == p else 0.0) - w[q2]
                i2 = idx_map[q2]
                var += c1 * c2 * cov[i1][i2]
        out[p] = (eff, math.sqrt(max(0.0, var)) / neg_b)
    return out


def main() -> None:
    manifest = json.loads((CACHE_ROOT / "manifest.json").read_text(encoding="utf-8"))
    with open(Path(manifest[0]["dir"]) / "places.csv", encoding="utf-8", newline="") as f:
        all_places = sorted(p["id"] for p in csv.DictReader(f))

    v3t_entries = [m for m in manifest if m["version"] == "v3T"]
    v2_entries = [m for m in manifest if m["version"] == "v2"]

    v3t_quotes, v3t_won = [], []
    for e in v3t_entries:
        qr, wr, _ = load_world_data(e)
        v3t_quotes.extend(qr)
        v3t_won.extend(wr)

    v2_quotes, v2_won = [], []
    for e in v2_entries:
        qr, wr, _ = load_world_data(e)
        v2_quotes.extend(qr)
        v2_won.extend(wr)

    # Compare 3 fits on v3T:
    # 1. fresh64: night-01..32 + final-01..32 (ZERO dev worlds, ZERO holdout worlds!)
    # 2. noh80:   dev-01..16 + night-01..32 + final-01..32 (ZERO holdout worlds)
    # 3. full96:  all 96 distinct worlds
    fresh_q = [r for r in v3t_quotes if r["seed"].startswith(("night-", "final-"))]
    noh_q = [r for r in v3t_quotes if not r["seed"].startswith("hold-")]
    dev_q = [r for r in v3t_quotes if r["seed"].startswith("dev-")]
    hold_q = [r for r in v3t_quotes if r["seed"].startswith("hold-")]

    # Check if any of the 4 zero-count pickups in v3T had quotes anywhere in v2 or v3T
    all_pk_counts = Counter(r["pickup"] for r in (v3t_quotes + v2_quotes))
    zero_pks = [p for p in all_places if all_pk_counts[p] == 0]
    print("Zero-quote pickup towns across all 160 v2+v3T worlds:", zero_pks)

    res_fresh64 = build_and_fit_won(fresh_q, all_places)
    res_noh80 = build_and_fit_won(noh_q, all_places)
    res_full96 = build_and_fit_won(v3t_quotes, all_places)
    res_dev16 = build_and_fit_won(dev_q, all_places)
    res_hold16 = build_and_fit_won(hold_q, all_places)

    # Recompute exact zero-excluded centered effects & EB shrinkage on fresh64 and full96
    def clean_shrunk(res: dict) -> tuple[dict[str, tuple[float, float]], dict[str, float], float, dict[str, tuple[float, float]], dict[str, float], float]:
        ref_place = "helsinki"
        pk_idx = {p: res["names"].index(f"pk:{p}") for p in all_places if p != ref_place}
        dl_idx = {p: res["names"].index(f"dl:{p}") for p in all_places if p != ref_place}
        neg_b = -res["b_price"]
        pk_lp = center_observed_only(all_places, ref_place, pk_idx, res["theta"], res["cov"], res["pk_counts"], neg_b)
        dl_lp = center_observed_only(all_places, ref_place, dl_idx, res["theta"], res["cov"], res["dl_counts"], neg_b)
        pk_sh, pk_tau = shrink_effects(pk_lp)
        dl_sh, dl_tau = shrink_effects(dl_lp)
        return pk_lp, pk_sh, pk_tau, dl_lp, dl_sh, dl_tau

    pk_lp64, pk_sh64, pk_tau64, dl_lp64, dl_sh64, dl_tau64 = clean_shrunk(res_fresh64)
    pk_lp80, pk_sh80, pk_tau80, dl_lp80, dl_sh80, dl_tau80 = clean_shrunk(res_noh80)
    pk_lp96, pk_sh96, pk_tau96, dl_lp96, dl_sh96, dl_tau96 = clean_shrunk(res_full96)
    _, pk_sh_dev, _, _, dl_sh_dev, _ = clean_shrunk(res_dev16)
    _, pk_sh_hold, _, _, dl_sh_hold, _ = clean_shrunk(res_hold16)

    # Check correlations of fresh64 shrunk lane sum with dev16, hold16, noh80, full96
    lanes_all = Counter((r["pickup"], r["delivery"]) for r in v3t_quotes)
    s64 = [pk_sh64[pk] + dl_sh64[dl] for pk, dl in lanes_all]
    s80 = [pk_sh80[pk] + dl_sh80[dl] for pk, dl in lanes_all]
    s96 = [pk_sh96[pk] + dl_sh96[dl] for pk, dl in lanes_all]
    sdev = [pk_sh_dev[pk] + dl_sh_dev[dl] for pk, dl in lanes_all]
    shold = [pk_sh_hold[pk] + dl_sh_hold[dl] for pk, dl in lanes_all]
    ws = [float(c) for c in lanes_all.values()]

    print(f"Lane effect (pk+dl) weighted r: fresh64 vs noh80 = {pearson_r(s64, s80, ws):+.4f}")
    print(f"Lane effect (pk+dl) weighted r: fresh64 vs full96 = {pearson_r(s64, s96, ws):+.4f}")
    print(f"Lane effect (pk+dl) weighted r: fresh64 vs dev16 (OOS!) = {pearson_r(s64, sdev, ws):+.4f}")
    print(f"Lane effect (pk+dl) weighted r: fresh64 vs hold16 (OOS!) = {pearson_r(s64, shold, ws):+.4f}")

    # Also check unweighted r on pickup towns with n >= 200 across Half A vs Half B
    seeds_sorted = sorted(set(r["seed"] for r in v3t_quotes))
    res_a = build_and_fit_won([r for r in v3t_quotes if r["seed"] in set(seeds_sorted[0::2])], all_places)
    res_b = build_and_fit_won([r for r in v3t_quotes if r["seed"] in set(seeds_sorted[1::2])], all_places)
    pks_200 = [p for p in all_places if res_a["pk_counts"][p] >= 200 and res_b["pk_counts"][p] >= 200]
    pk_r_200 = pearson_r([res_a["pk_lp"][p][0] for p in pks_200], [res_b["pk_lp"][p][0] for p in pks_200])
    print(f"Half A vs Half B unweighted r on pickup towns with n>=200 (k={len(pks_200)}): {pk_r_200:+.4f}")

    # Compute lane effect distribution & terciles across non-declined quotes using fresh64 (zero dev/holdout leakage!)
    quote_lane_vals = sorted(pk_sh64[r["pickup"]] + dl_sh64[r["delivery"]] for r in fresh_q)
    q10, q25, q33, q50, q67, q75, q90 = [
        quote_lane_vals[int(len(quote_lane_vals) * frac)]
        for frac in (0.10, 0.25, 1.0 / 3.0, 0.50, 2.0 / 3.0, 0.75, 0.90)
    ]
    mean_lane = st.mean(quote_lane_vals)
    print(
        f"fresh64 lane_effect distribution (n={len(quote_lane_vals)}): "
        f"mean={mean_lane:+.4f}, p10={q10:+.4f}, p33={q33:+.4f}, p50={q50:+.4f}, p67={q67:+.4f}, p90={q90:+.4f}"
    )

    # Check empirical win rate, late rate, and margin/order by tercile of fresh64 lane_effect on dev+holdout (32 OOS worlds!)
    oos_quotes = [r for r in v3t_quotes if r["seed"].startswith(("dev-", "hold-"))]
    oos_won_map = {(r["world"], r["id"]): r for r in v3t_won if r["seed"].startswith(("dev-", "hold-"))}
    print()
    print("=== OOS CHECK ON DEV+HOLDOUT (32 worlds) BY TERCILE OF FRESH64 LANE EFFECT ===")
    for tname, lo, hi in [("low (<q33, inbound/easy)", -9.0, q33), ("mid (q33..q67)", q33, q67), ("high (>=q67, outbound/hard)", q67, 9.0)]:
        sub = [r for r in oos_quotes if lo <= (pk_sh64[r["pickup"]] + dl_sh64[r["delivery"]]) < hi]
        wins = [oos_won_map[(r["world"], r["id"])] for r in sub if (r["world"], r["id"]) in oos_won_map]
        lates = sum(w["late"] for w in wins)
        mrg_tot = sum(w["margin_eur"] for w in wins)
        floored_sh = sum(1 for r in sub if r["is_floored"]) / max(1, len(sub))
        mean_le = st.mean(pk_sh64[r["pickup"]] + dl_sh64[r["delivery"]] for r in sub)
        print(
            f"  {tname:<30} quotes={len(sub):<5} ({len(sub)/32:5.1f}/w)  "
            f"win={len(wins)/len(sub):5.1%} ({len(wins)/32:4.1f}/w)  floored={floored_sh:5.1%}  "
            f"mean_eff={mean_le:+.3f}  late={lates/max(1,len(wins)):5.2%}  "
            f"margin/win=€{mrg_tot/max(1,len(wins)):5.2f}  margin/w=€{mrg_tot/32:7.2f}"
        )

    # Detailed buffer class analysis on v3T 96 worlds (28,307 won orders)
    print()
    print("=== DETAILED BUFFER CLASS ANALYSIS (<2% LATE) ON v3T 96 WORLDS ===")
    capital = {"helsinki", "espoo", "vantaa"}

    def test_rule(name: str, pred_fn) -> None:
        sub = [r for r in v3t_won if pred_fn(r)]
        if not sub:
            return
        n_w = len(sub)
        n_l = sum(r["late"] for r in sub)
        lr = n_l / n_w
        # Wilson 95% upper bound
        z = 1.96
        denom = 1 + z * z / n_w
        center = (lr + z * z / (2 * n_w)) / denom
        half = z * math.sqrt((lr * (1 - lr) + z * z / (4 * n_w)) / n_w) / denom
        ub95 = center + half
        mrg = sum(r["margin_eur"] for r in sub) / n_w
        print(f"  {name:<58} n={n_w:<6} ({n_w/96:5.1f}/w)  late={n_l:<4} ({lr:5.2%}, ub95={ub95:5.2%})  €/ord={mrg:6.2f}")

    test_rule("ALL WON ORDERS (baseline)", lambda r: True)
    test_rule("c4 default: pk_sup30>=100, drv<=120, !(sd & hr>=13), !note", lambda r: r["pk_sup30"] >= 100 and r["drive_min"] <= 120 and not (r["is_same_day"] and r["hour"] >= 13) and not r["has_note"])
    test_rule("c4 default WITH note allowed: pk_sup30>=100, drv<=120, !(sd&hr>=13)", lambda r: r["pk_sup30"] >= 100 and r["drive_min"] <= 120 and not (r["is_same_day"] and r["hour"] >= 13))
    test_rule("Has note vs No note: has_note == False", lambda r: not r["has_note"])
    test_rule("Has note vs No note: has_note == True", lambda r: r["has_note"])
    test_rule("within_3_days & drive < 300m (any pickup)", lambda r: r["won_opt"] == "within_3_days" and r["drive_min"] < 300)
    test_rule("within_3_days (all drives)", lambda r: r["won_opt"] == "within_3_days")
    test_rule("Capital next_day < 300m", lambda r: r["pickup"] in capital and r["won_opt"] == "next_day" and r["drive_min"] < 300)
    test_rule("Capital next_day 60-299m", lambda r: r["pickup"] in capital and r["won_opt"] == "next_day" and 60 <= r["drive_min"] < 300)
    test_rule("Capital next_day < 60m (no note)", lambda r: r["pickup"] in capital and r["won_opt"] == "next_day" and r["drive_min"] < 60 and not r["has_note"])
    test_rule("Capital next_day < 60m (with note)", lambda r: r["pickup"] in capital and r["won_opt"] == "next_day" and r["drive_min"] < 60 and r["has_note"])
    test_rule("Capital same_day < 180m (no note, Mon-Thu, hr<13)", lambda r: r["pickup"] in capital and r["is_same_day"] and r["drive_min"] < 180 and not r["has_note"] and r["day"] <= 3 and r["hour"] < 13)
    test_rule("Capital same_day < 180m (no note)", lambda r: r["pickup"] in capital and r["is_same_day"] and r["drive_min"] < 180 and not r["has_note"])
    test_rule("Capital same_day < 180m (with note)", lambda r: r["pickup"] in capital and r["is_same_day"] and r["drive_min"] < 180 and r["has_note"])
    test_rule("Ring -> Capital (< 60m, any option)", lambda r: r["pickup"] not in capital and r["pk_sup30"] < 30 and r["pk_sup55"] >= 30 and r["delivery"] in capital and r["drive_min"] < 60)
    test_rule("Inbound to Capital: next_day < 300m (any pickup)", lambda r: r["delivery"] in capital and r["won_opt"] == "next_day" and r["drive_min"] < 300)
    test_rule("Non-capital next_day 60-179m", lambda r: r["pickup"] not in capital and r["won_opt"] == "next_day" and 60 <= r["drive_min"] < 180)
    test_rule("CLEAN BUFFER UNION: w3d<300 | (nd<300 & (cap | dl_cap | 60<=drv<180) & !note) | (sd<180 & (cap|ring_to_cap) & !note & day<4)", lambda r: (
        (r["won_opt"] == "within_3_days" and r["drive_min"] < 300)
        or (r["won_opt"] == "next_day" and r["drive_min"] < 300 and not r["has_note"] and (r["pickup"] in capital or r["delivery"] in capital or 60 <= r["drive_min"] < 180))
        or (r["is_same_day"] and r["drive_min"] < 180 and not r["has_note"] and r["day"] < 4 and (r["pickup"] in capital or r["delivery"] in capital))
    ))

    # Write src/spread_lab/data/lane_table.json (fitted on fresh64 = night-01..32 + final-01..32, zero dev/holdout leakage!)
    data_dir = REPO / "src/spread_lab/data"
    data_dir.mkdir(parents=True, exist_ok=True)
    lane_table = {
        "meta": {
            "description": "Competitor log-price lane effects (pickup + delivery), shrunk towards 0 by empirical-Bayes SE shrinkage.",
            "units": "log_price_equivalent (alpha = beta_place / -beta_log_price)",
            "fit_worlds": 64,
            "fit_seeds": "night-01..32 + final-01..32 (v3T, 49190 non-decline quotes; strictly out-of-sample on dev and holdout)",
            "b_log_price": round(res_fresh64["b_price"], 4),
            "se_log_price": round(res_fresh64["se_price"], 4),
            "b_trust": round(res_fresh64["b_trust"], 4),
            "se_trust": round(res_fresh64["se_trust"], 4),
            "pickup_tau": round(pk_tau64, 4),
            "delivery_tau": round(dl_tau64, 4),
            "terciles": [round(q33, 5), round(q67, 5)],
        },
        "pickup": {p: round(pk_sh64[p], 5) for p in all_places},
        "delivery": {p: round(dl_sh64[p], 5) for p in all_places},
        "pickup_se": {p: (round(pk_lp64[p][1], 5) if res_fresh64["pk_counts"][p] > 0 else None) for p in all_places},
        "delivery_se": {p: (round(dl_lp64[p][1], 5) if res_fresh64["dl_counts"][p] > 0 else None) for p in all_places},
    }
    out_path = data_dir / "lane_table.json"
    out_path.write_text(json.dumps(lane_table, indent=2) + chr(10), encoding="utf-8")
    print()
    print(f"Wrote {out_path} ({out_path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
