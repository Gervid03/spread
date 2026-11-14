"""Slot-free analysis of demand-curve mechanisms on cached out-of-sample L8 reveals (night-01..32 + final-01..32).

Measures:
1. sd_stripped vs sd_kept vs no_sd win rates and tracker bias.
2. Tue-Fri win rates by dealer trust (low trust vs high trust under dealer_lr=0.01).
3. Inbound-to-Hub vs Intra-Hub vs Outbound floor bind rates, win rates, booked fee/ref ratios, late rates, and margins.
"""
from __future__ import annotations

import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

CACHE_ROOT = Path("/home/lab/.gemini/tmp/d14-02-acceptance-model/reveals")
OPTS = ("same_day", "next_day", "within_3_days")


def analyze_world(wdir: Path) -> dict:
    # Load drivers to compute 30km supply
    places = {}
    with (wdir / "places.csv").open() as f:
        for r in csv.DictReader(f):
            places[r["id"]] = (float(r["lat"]), float(r["lon"]))
    drivers = list(csv.DictReader((wdir / "drivers.csv").open()))

    def line_km(a: str, b: str) -> float:
        lat1, lon1 = places[a]
        lat2, lon2 = places[b]
        dy = (lat2 - lat1) * 111.32
        dx = (lon2 - lon1) * 111.32 * math.cos(math.radians((lat1 + lat2) * 0.5))
        return math.hypot(dx, dy)

    supply30 = {}
    for pid in places:
        supply30[pid] = sum(1 for d in drivers if line_km(pid, d["homePlaceId"]) <= 30.0)

    legs_by_req = defaultdict(list)
    with (wdir / "legs.csv").open() as f:
        for r in csv.DictReader(f):
            legs_by_req[r["requestId"]].append(r)

    # Replay ledger/events for trust and per-order P&L
    events = list(csv.DictReader((wdir / "events.csv").open()))
    reqs = list(csv.DictReader((wdir / "requests.csv").open()))
    req_by_id = {r["id"]: r for r in reqs}

    # Sort combined timeline of requests and ledger events
    timeline = []
    for r in reqs:
        timeline.append((int(r["arrivedAt"]), 1, r))
    order_pnl = defaultdict(float)
    order_fee = defaultdict(float)
    order_rev = defaultdict(float)
    order_late = set()
    for e in events:
        at = int(e["at"])
        if e["kind"] == "ledger":
            oid = e.get("line.orderId") or ""
            cents = int(e["line.cents"]) if e.get("line.cents") else 0
            lkind = e.get("line.kind") or ""
            if oid:
                order_pnl[oid] += cents / 100.0
                if lkind == "driver_fee":
                    order_fee[oid] += -cents / 100.0
                elif lkind == "revenue":
                    order_rev[oid] += cents / 100.0
                elif lkind in ("late_refund", "undelivered_penalty"):
                    order_late.add(oid)
            timeline.append((at, 0, e))

    timeline.sort(key=lambda x: (x[0], x[1]))
    trust = Counter()
    seen_late = set()
    trust_ema = 0.0

    out = {
        "cat_quotes": Counter(),
        "cat_wins": Counter(),
        "trust_quotes": Counter(),
        "trust_wins": Counter(),
        "trust_diff_quotes": Counter(),
        "trust_diff_wins": Counter(),
        "dir_total": Counter(),
        "dir_floored": Counter(),
        "dir_floored_wins": Counter(),
        "dir_unfloored": Counter(),
        "dir_unfloored_wins": Counter(),
        "dir_won_n": Counter(),
        "dir_won_late": Counter(),
        "dir_won_margin": defaultdict(float),
        "dir_won_fee_ratio": defaultdict(list),
    }

    for at, etype, obj in timeline:
        if etype == 0:
            oid = obj.get("line.orderId") or ""
            lkind = obj.get("line.kind") or ""
            dealer = req_by_id[oid]["dealerId"] if oid in req_by_id else None
            if lkind in ("late_refund", "undelivered_penalty") and oid:
                if oid not in seen_late:
                    seen_late.add(oid)
                    if dealer:
                        trust[dealer] //= 2
            elif lkind == "revenue" and oid and dealer and oid not in seen_late and oid not in order_late:
                trust[dealer] = min(25, trust[dealer] + 1)
        else:
            r = obj
            rid = r["id"]
            # Check quoted options
            offered = [o for o in OPTS if r.get(f"{o}.listPriceCents")]
            quoted = {}
            for o in offered:
                q = r.get(f"{o}.quoteCents")
                if q:
                    quoted[o] = int(q)
            if not quoted:
                continue
            first_o = next(iter(quoted))
            lst_first = int(r[f"{first_o}.listPriceCents"])
            if quoted[first_o] >= int(lst_first * 3.8):
                continue  # decline

            ref = int(r["referenceFeeCents"])
            floor_cents = ref * 1.25 / 0.92
            any_floored = any(q <= int(floor_cents + 0.5) + 1 and q >= int(floor_cents + 0.5) - 1 for q in quoted.values())
            # More exact: check if min quoted option is at floor
            min_q = min(quoted.values())
            is_floor = abs(min_q - int(floor_cents + 0.5)) <= 1

            won = r["outcome"] == "won"
            dealer = r["dealerId"]
            t_d = trust[dealer]
            day = at // 1440

            rlegs = legs_by_req[rid]
            p_sup = supply30.get(rlegs[0]["pickup.placeId"], 0)
            d_sup = supply30.get(rlegs[-1]["delivery.placeId"], 0)
            if p_sup < 200 and d_sup >= 200:
                direction = "inb_to_hub"
            elif p_sup >= 200 and d_sup >= 200:
                direction = "intra_hub"
            elif p_sup >= 200 and d_sup < 200:
                direction = "hub_outbound"
            else:
                direction = "regional"

            out["dir_total"][direction] += 1
            if is_floor:
                out["dir_floored"][direction] += 1
                if won:
                    out["dir_floored_wins"][direction] += 1
            else:
                out["dir_unfloored"][direction] += 1
                if won:
                    out["dir_unfloored_wins"][direction] += 1

            if won:
                out["dir_won_n"][direction] += 1
                if rid in order_late:
                    out["dir_won_late"][direction] += 1
                out["dir_won_margin"][direction] += order_pnl[rid]
                if ref > 0 and order_fee[rid] > 0:
                    out["dir_won_fee_ratio"][direction].append(order_fee[rid] / (ref / 100.0))

            if not is_floor:
                had_sd = "same_day" in offered
                kept_sd = "same_day" in quoted
                cat = "sd_kept" if (had_sd and kept_sd) else ("sd_stripped" if had_sd else "no_sd")
                out["cat_quotes"][cat] += 1
                if won:
                    out["cat_wins"][cat] += 1

                if day >= 1:
                    tb = "t_0_2" if t_d <= 2 else ("t_3_14" if t_d <= 14 else "t_15_25")
                    out["trust_quotes"][tb] += 1
                    if won:
                        out["trust_wins"][tb] += 1
                    diff = t_d - trust_ema
                    db = "below_-6" if diff < -6 else ("mid_-6_+6" if diff <= 6 else "above_+6")
                    out["trust_diff_quotes"][db] += 1
                    if won:
                        out["trust_diff_wins"][db] += 1

            trust_ema += 0.05 * (t_d - trust_ema)
    return out


def main() -> None:
    idx_path = CACHE_ROOT / "index.json"
    if idx_path.exists():
        entries = json.loads(idx_path.read_text())
        dirs = [
            Path(e["dir"])
            for e in entries
            if e.get("version") == "v3T" and (e.get("seed", "").startswith("night-") or e.get("seed", "").startswith("final-"))
        ]
    else:
        dirs = sorted(d for d in CACHE_ROOT.iterdir() if d.is_dir())[:64]
    print(f"Found {len(dirs)} v3T night/final reveal dirs")

    agg = {
        "cat_quotes": Counter(),
        "cat_wins": Counter(),
        "trust_quotes": Counter(),
        "trust_wins": Counter(),
        "trust_diff_quotes": Counter(),
        "trust_diff_wins": Counter(),
        "dir_total": Counter(),
        "dir_floored": Counter(),
        "dir_floored_wins": Counter(),
        "dir_unfloored": Counter(),
        "dir_unfloored_wins": Counter(),
        "dir_won_n": Counter(),
        "dir_won_late": Counter(),
        "dir_won_margin": Counter(),
        "dir_won_fee_ratio": defaultdict(list),
    }
    used = 0
    for d in dirs:
        if not (d / "requests.csv").exists():
            continue
        # Only use night-* and final-* seeds (strictly out-of-sample on dev and holdout)
        meta_p = d / "meta.json"
        if meta_p.exists():
            m = json.loads(meta_p.read_text())
            seed = m.get("seed", "")
            if seed.startswith("hold-") or seed.startswith("dev-"):
                continue
        res = analyze_world(d)
        used += 1
        for k in ("cat_quotes", "cat_wins", "trust_quotes", "trust_wins", "trust_diff_quotes", "trust_diff_wins",
                  "dir_total", "dir_floored", "dir_floored_wins", "dir_unfloored", "dir_unfloored_wins",
                  "dir_won_n", "dir_won_late"):
            agg[k].update(res[k])
        for dir_k, v in res["dir_won_margin"].items():
            agg["dir_won_margin"][dir_k] += v
        for dir_k, lst in res["dir_won_fee_ratio"].items():
            agg["dir_won_fee_ratio"][dir_k].extend(lst)

    print(f"Analyzed {used} strictly out-of-sample worlds (night/final):")
    print("--- 1. Unfloored Win Rate by same_day Status ---")
    for cat in ("sd_kept", "sd_stripped", "no_sd"):
        q = agg["cat_quotes"][cat]
        w = agg["cat_wins"][cat]
        print(f"  {cat:14s}: {w:6d} / {q:6d} = {100*w/max(1,q):5.2f}%  ({q/max(1,used):5.1f} quotes/wk)")

    print("--- 2. Tue-Fri Unfloored Win Rate by Dealer Trust & Centered Trust (t - trust_ema) ---")
    for tb in ("t_0_2", "t_3_14", "t_15_25"):
        q = agg["trust_quotes"][tb]
        w = agg["trust_wins"][tb]
        print(f"  {tb:14s}: {w:6d} / {q:6d} = {100*w/max(1,q):5.2f}%")
    for db in ("below_-6", "mid_-6_+6", "above_+6"):
        q = agg["trust_diff_quotes"][db]
        w = agg["trust_diff_wins"][db]
        print(f"  {db:14s}: {w:6d} / {q:6d} = {100*w/max(1,q):5.2f}%")

    print("--- 3. Direction Breakdown (Floor Bind Rate, Win Rates, Booked Fee/Ref, Late %, €/Order) ---")
    for dk in ("inb_to_hub", "intra_hub", "hub_outbound", "regional"):
        tot = agg["dir_total"][dk]
        fl = agg["dir_floored"][dk]
        flw = agg["dir_floored_wins"][dk]
        uf = agg["dir_unfloored"][dk]
        ufw = agg["dir_unfloored_wins"][dk]
        wn = agg["dir_won_n"][dk]
        wl = agg["dir_won_late"][dk]
        wm = agg["dir_won_margin"][dk]
        fr = agg["dir_won_fee_ratio"][dk]
        mean_fr = sum(fr) / len(fr) if fr else 0.0
        print(
            f"  {dk:14s}: quotes={tot/max(1,used):5.1f}/wk | floor_share={100*fl/max(1,tot):4.1f}% "
            f"| unfloored_win={100*ufw/max(1,uf):5.1f}% | floor_win={100*flw/max(1,fl):5.1f}% "
            f"| fee/ref={mean_fr:.3f} | late={100*wl/max(1,wn):4.2f}% | margin=€{wm/max(1,wn):5.2f}/ord"
        )


if __name__ == "__main__":
    main()
