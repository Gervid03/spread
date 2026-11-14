"""Run Layer 2 (OracleDesk: oracle selection + option steering + perfect pricing on v5 staffing).

Supports:
  --fast-lookup   0-fork rapid screening on dev-12 using limits-all.jsonl (trust-adjusted)
  (default)       100% true live fork bisection + optional --replay 0-fork book verification
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import tas  # noqa: E402
from spread_lab.env import load_dotenv  # noqa: E402
from spread_lab.lab import champion, parse_overrides  # noqa: E402
from spread_lab.policies.tas_price import OracleDesk  # noqa: E402
from spread_lab.policy import DAY  # noqa: E402


def make_oracle_select_hook(fast_lookup: dict[tuple[str, str], dict] | None, lo_x: float, hi_x: float, iters: int, sink):
    def hook(g: tas.Tas, actions: list, fresh: list) -> list:
        desk: OracleDesk = g.desk  # type: ignore[assignment]
        quotes = [actions[i] for i in fresh]

        feas_by_rid: dict[str, tuple[list[str], dict]] = {}
        series: list[dict[str, str]] = []
        for idx in fresh:
            rid = actions[idx]["requestId"]
            req = desk.requests[rid]
            ok_kinds, meta = desk.feasible_options(req)
            feas_by_rid[rid] = (ok_kinds, meta)
            if fast_lookup is None:
                for j, kind in enumerate(ok_kinds):
                    while len(series) <= j:
                        series.append({})
                    series[j][rid] = kind

        measured: dict[str, dict[str, int]] = defaultdict(dict)
        if fast_lookup is not None:
            for rid, (ok_kinds, _) in feas_by_rid.items():
                req = desk.requests[rid]
                cur_t = desk.dealer_trust.get(req["dealerId"], 0)
                for kind in ok_kinds:
                    row = fast_lookup.get((rid, kind))
                    if row and row.get("lo"):
                        scaled = int(row["lo"] * (1 + 0.01 * cur_t) / (1 + 0.01 * row["trust"])) - 150
                        measured[rid][kind] = max(0, scaled)
        else:
            for targets in series:
                res = tas.probe_prices(g, quotes, targets, lo_x, hi_x, iters)
                for rid, st in res.items():
                    req = desk.requests[rid]
                    lo_val = st["lo"] or 0
                    measured[rid][st["option"]] = lo_val
                    sink({
                        "rid": rid,
                        "at": desk.now,
                        "day": desk.now // DAY,
                        "dealer": req["dealerId"],
                        "trust": desk.dealer_trust.get(req["dealerId"], 0),
                        "legs": len(req["legs"]),
                        "pickup": req["legs"][0]["pickup"]["placeId"],
                        "delivery": req["legs"][-1]["delivery"]["placeId"],
                        "ref": req["referenceFeeCents"],
                        **st,
                        "x": round(lo_val / st["list"], 4) if lo_val else None,
                    })

        # Sort feasible requests in this batch by preliminary max net margin descending so high-margin orders get priority!
        prelim_order = []
        for idx in fresh:
            rid = actions[idx]["requestId"]
            ok_kinds, meta = feas_by_rid[rid]
            if not ok_kinds or not measured.get(rid):
                prelim_order.append((-1e9, idx, rid))
                continue
            req = desk.requests[rid]
            best_pre = max(((measured[rid].get(k, 0) / 100.0 - desk.expected_fee_eur(req, k, meta)) / desk.driver_blocks(k, meta)) for k in ok_kinds)
            prelim_order.append((best_pre, idx, rid))
        prelim_order.sort(key=lambda t: (-t[0], t[2]))

        out = list(actions)
        for _, idx, rid in prelim_order:
            req = desk.requests[rid]
            ok_kinds, meta = feas_by_rid[rid]
            first = req["options"][0]
            decline_prices = {first["kind"]: int(first["listPriceCents"] * desk.p.decline_mult)}

            if not ok_kinds or not measured.get(rid):
                out[idx] = {"type": "quote", "requestId": rid, "prices": decline_prices}
                desk.decided[rid] = "decline"
                desk.oracle_in_flight.discard(rid)
                continue

            chosen_kind, chosen_cents, _ = desk.choose_from_limits(req, measured[rid], meta)
            if chosen_kind is None or chosen_cents <= 0:
                out[idx] = {"type": "quote", "requestId": rid, "prices": decline_prices}
                desk.decided[rid] = "decline"
                desk.oracle_in_flight.discard(rid)
            else:
                out[idx] = {"type": "quote", "requestId": rid, "prices": {chosen_kind: chosen_cents}}
                desk.decided[rid] = "quote"
                desk.oracle_in_flight.add(rid)
                if fast_lookup is None:
                    g.expect[rid] = chosen_kind
        return out

    return hook


V5_PARAMS = {
    "backlog_ratio": 0.06,
    "price_target_win": 0.4,
    "min_supply": 22,
    "gate_radius_km": 55.0,
    "far_options": "slow",
    "same_day_min_supply": 50,
    "slack_per_drive": 0.75,
    "long_drive_min": 300,
    "fee_open": 0.85,
    "price_lr": 0.05,
    "offers_per_warning": 0,
    "min_slack_min": 150,
    "trust_invest": 0.05,
    "notes_v2": True,
    "note_unsure": "decline",
    "max_next_day_drive_min": 480,
    "fri_same_day_max_drive": 100,
    "thin_long_next_day_supply": 50,
    "ring_to_hub_same_day_min": 60,
    "backlog_multiday_weight": 0.25,
    "backlog_in_flight_weight": 0.35,
    "dealer_lr": 0.01,
    "ext_ring_min_supply": 30,
    "ext_ring_max_drive_min": 220,
    "return_hub_min_supply": 200,
    "return_hub_max_drive_min": 180,
    "ext_ring_neutral_learn": True,
    "lead_car": True,
    "lead_car_max_gap_km": 0.0,
    "lead_car_max_deliv_gap_km": 25.0,
    "lead_car_fee_mult": 1.0,
    "late_fee_open": 1.0,
    "urgent_hygiene": True,
    "late_reprice_grace_min": 60,
    "drop_reprice_bump": 0.03,
    "steep_open": 1.65,
    "steep_step": 0.2,
    "steep_max": 2.25,
    "view_offer_mult": 1.03,
    "view_offer_cap": 1.15,
}


def main() -> None:
    load_dotenv()
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="dev-12")
    ap.add_argument("--name", required=True)
    ap.add_argument("-s", "--set", action="append", default=[])
    ap.add_argument("--fast-lookup", action="store_true")
    ap.add_argument("--replay", action="store_true")
    ap.add_argument("--lo", type=float, default=0.65)
    ap.add_argument("--hi", type=float, default=3.4)
    ap.add_argument("--iters", type=int, default=8)
    a = ap.parse_args()

    base_params = dict(V5_PARAMS)
    overrides = parse_overrides(OracleDesk, a.set)
    merged = {**base_params, **overrides}

    fast_map = None
    if a.fast_lookup:
        lim_path = tas.home(a.seed) / "limits-all.jsonl"
        fast_map = {}
        for line in lim_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                fast_map[(row["rid"], row["option"])] = row

    lines: list[dict] = []
    lim_out = tas.home(a.seed) / f"limits-{a.name}.jsonl"
    book_out = tas.home(a.seed) / f"book-{a.name}.json"

    sink_target = lim_out if not a.fast_lookup else Path("/dev/null")
    with open(sink_target, "w", encoding="utf-8") as f, tas.Tas(
        a.seed, merged, "spread_lab.policies.tas_price:OracleDesk", a.name, forks=not a.fast_lookup
    ) as g:
        def sink(row: dict) -> None:
            lines.append(row)
            print(json.dumps(row), file=f, flush=True)

        g.hook = make_oracle_select_hook(fast_map, a.lo, a.hi, a.iters, sink)
        result = g.finish()
        book_out.write_text(json.dumps({"*": "decline", **{rid: {"prices": p} for rid, p in g.quoted.items()}}), encoding="utf-8")
        broken = sorted(rid for rid, kind in g.expect.items() if rid in g.outcome and g.outcome[rid][:2] != ("won", kind))
        won_q = sum(1 for o in g.outcome.values() if o[0] == "won")
        lost_q = sum(1 for o in g.outcome.values() if o[0] == "lost")

    tas.report(a.seed, a.name, result, {"overrides": overrides, "fast_lookup": a.fast_lookup, "broken": broken, "quotes_won": won_q, "quotes_lost": lost_q})
    if broken:
        print(f"WARNING: broken expectations ({len(broken)}): {broken[:10]}")

    if a.replay and not a.fast_lookup:
        print(f"=== Replaying {book_out} with 0 forks ===", flush=True)
        with tas.Tas(a.seed, base_params, None, f"replay-{a.name}", forks=False) as g2:
            g2.hook = tas.book_hook(json.loads(book_out.read_text(encoding="utf-8")))
            rep_res = g2.finish()
        tas.report(a.seed, f"run-book-{a.name}", rep_res, {"book": str(book_out)})
        print(f"Live={result['margin']:.2f} vs 0-fork Desk book replay={rep_res['margin']:.2f} (Δ={rep_res['margin']-result['margin']:+.2f})")


if __name__ == "__main__":
    main()
