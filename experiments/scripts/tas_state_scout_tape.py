"""Slot-free reconnaissance on the 4 TAS seeds using tape.json and v5's finished world reveals."""
from __future__ import annotations

import json
import pathlib
from collections import Counter, defaultdict

from spread_lab.env import lab_home, load_dotenv
from spread_lab.geo import Geo, load_map
from spread_lab.lab import CountingClient

TAS_SEEDS = ("dev-12", "dev-01", "dev-08", "dev-07")
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun", "Mon+", "Tue+", "Wed+"]


def get_champ_rows() -> dict[str, dict]:
    out = {}
    for line in pathlib.Path("champion/results/dev-L8.jsonl").read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        if r["seed"] in TAS_SEEDS:
            out[r["seed"]] = r
    return out


def ensure_reveal(client: CountingClient, seed: str, world_id: str) -> dict:
    p = lab_home() / "tas" / seed / "reveal-v5.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    rev = client.world(world_id).reveal()
    p.write_text(json.dumps(rev), encoding="utf-8")
    return rev


def analyze_seed(seed: str, champ_row: dict, geo: Geo, names: dict[str, str], rev: dict) -> None:
    tas_seed = lab_home() / "tas" / seed
    tape = json.loads((tas_seed / "tape.json").read_text(encoding="utf-8"))
    reqs = tape["requests"]
    req_by_id = {r["id"]: r for r in reqs}
    roster = tape["roster"]

    print("=" * 95)
    print(
        f"SEED {seed} | champ margin €{champ_row['margin']:,.2f} | rev €{champ_row['revenue']:,.2f} | "
        f"won {champ_row['won']}/{len(reqs)} | on_time {champ_row['on_time']:.2%} | "
        f"world {champ_row.get('world')}"
    )
    if seed == "dev-12":
        print("Reveal top-level keys:", sorted(rev.keys()))
        for k in sorted(rev.keys()):
            val = rev[k]
            if isinstance(val, list) and val:
                print(f"  rev[{k!r}][0] keys:", sorted(val[0].keys()) if isinstance(val[0], dict) else type(val[0]))

    print(f"Roster: {len(roster)} drivers | Forecasts in tape: {len(tape['forecasts'])}")
    for fc in tape["forecasts"]:
        print(f"  Forecast at {DAYS[fc['at']//1440]} {(fc['at']%1440)//60:02d}:00 -> {fc['text']}")

    supply30 = {p_id: sum(1 for d in roster if geo.line_km(d["homePlaceId"], p_id) <= 30.0) for p_id in names}
    supply55 = {p_id: sum(1 for d in roster if geo.line_km(d["homePlaceId"], p_id) <= 55.0) for p_id in names}
    top_towns = sorted(supply30.items(), key=lambda kv: -kv[1])[:8]
    print("Top driver pools (30km):", ", ".join(f"{names[k]}:{v}" for k, v in top_towns))

    batches = defaultdict(list)
    for r in reqs:
        if r.get("batchId"):
            batches[r["batchId"]].append(r)
    big_batches = sorted((b for b in batches.values() if len(b) >= 12), key=lambda b: -len(b))
    print("Large batches (>=12 cars):")
    for b in big_batches:
        r0 = b[0]
        d_idx = r0["arrivedAt"] // 1440
        hh = (r0["arrivedAt"] % 1440) // 60
        mm = r0["arrivedAt"] % 60
        pick_id = r0["legs"][0]["pickup"]["placeId"]
        opts = Counter(o["kind"] for r in b for o in r["options"])
        print(
            f"  batch {r0['batchId']}: {len(b)} cars at {DAYS[d_idx]} {hh:02d}:{mm:02d} "
            f"dealer={r0['dealerId']} pickup={names[pick_id]}({supply30[pick_id]}/{supply55[pick_id]}) opts={dict(opts)}"
        )

    # Reveal requests / quotes
    rev_reqs = {}
    for rr in rev.get("requests", []):
        rid = rr.get("requestId") or rr.get("id")
        if rid:
            rev_reqs[rid] = rr

    # Views -> Flu day detector!
    views = rev.get("views", [])
    viewers_by_day = defaultdict(set)
    views_count_by_day = Counter()
    for v in views:
        at = v.get("at") if v.get("at") is not None else v.get("viewedAt", 0)
        did = v.get("driverId") or v.get("driver")
        d = at // 1440
        if d < 7 and did:
            viewers_by_day[d].add(did)
            views_count_by_day[d] += 1
    print(
        "Unique viewing drivers by day (Flu detector):",
        ", ".join(f"{DAYS[d]}:{len(viewers_by_day[d])} ({views_count_by_day[d]}v)" for d in range(6)),
    )

    # Quotes & outcomes -> War & Outage detector!
    day_quoted = Counter()
    day_won = Counter()
    day_won_mults = defaultdict(list)
    day_lost_mults = defaultdict(list)
    place_day_won = defaultdict(Counter)
    place_day_tot = defaultdict(Counter)

    for r in reqs:
        rid = r["id"]
        rr = rev_reqs.get(rid, {})
        outcome = rr.get("outcome") or rr.get("status")
        quote = rr.get("prices") or rr.get("quote") or {}
        d = r["arrivedAt"] // 1440
        tod = r["arrivedAt"] % 1440
        if not (480 <= tod <= 1080) or not quote:
            continue
        by_k = {o["kind"]: o["listPriceCents"] for o in r["options"]}
        first_k = next(iter(quote))
        if first_k not in by_k:
            continue
        mult = quote[first_k] / by_k[first_k]
        if mult >= 3.5:
            continue
        day_quoted[d] += 1
        pick = r["legs"][0]["pickup"]["placeId"]
        place_day_tot[d][pick] += 1
        if outcome == "won":
            day_won[d] += 1
            place_day_won[d][pick] += 1
            won_opt = rr.get("wonOption") or rr.get("option") or first_k
            if won_opt in quote and won_opt in by_k:
                day_won_mults[d].append(quote[won_opt] / by_k[won_opt])
        elif outcome == "lost":
            day_lost_mults[d].append(mult)

    print("Daytime non-decline quotes & win share (War / Outage detector):")
    for d in range(5):
        q, w = day_quoted[d], day_won[d]
        wm = sum(day_won_mults[d]) / len(day_won_mults[d]) if day_won_mults[d] else 0
        lm = sum(day_lost_mults[d]) / len(day_lost_mults[d]) if day_lost_mults[d] else 0
        best_reg = None
        for p_id in names:
            rw = sum(place_day_won[d][p2] for p2 in names if geo.line_km(p_id, p2) <= 80.0)
            rt = sum(place_day_tot[d][p2] for p2 in names if geo.line_km(p_id, p2) <= 80.0)
            if rt >= 12:
                cand = (rw / rt, rw, rt, names[p_id])
                if best_reg is None or cand[0] > best_reg[0]:
                    best_reg = cand
        reg_str = f"top80km={best_reg[3]} {best_reg[1]}/{best_reg[2]} ({best_reg[0]:.0%})" if best_reg else ""
        print(f"  {DAYS[d]}: won {w:>3}/{q:<3} ({(w/q if q else 0):5.1%}) | avg won mult {wm:.3f} | lost mult {lm:.3f} | {reg_str}")

    # Dealer volume
    dealer_reqs_by_day = defaultdict(Counter)
    dealer_list_by_day = defaultdict(Counter)
    for r in reqs:
        d = r["arrivedAt"] // 1440
        dlr = r["dealerId"]
        dealer_reqs_by_day[dlr][d] += 1
        dealer_list_by_day[dlr][d] += max(o["listPriceCents"] for o in r["options"]) / 100.0

    top_dealers = sorted(dealer_reqs_by_day.keys(), key=lambda d: -sum(dealer_reqs_by_day[d].values()))[:8]
    print("Top 8 dealers (requests Mon..Fri | total list €):")
    for dlr in top_dealers:
        counts = [dealer_reqs_by_day[dlr][d] for d in range(5)]
        tot_list = sum(dealer_list_by_day[dlr].values())
        print(f"  {dlr}: {counts} (tot {sum(counts):>3}) | list €{tot_list:>8,.0f}")

    # Orders / ledger from reveal
    orders = rev.get("orders", [])
    late_orders = []
    for o in orders:
        oid = o.get("orderId") or o.get("id")
        dl = o.get("deadline")
        deliv = o.get("deliveredAt")
        if isinstance(deliv, list):
            done = [x for x in deliv if x is not None]
            last_deliv = max(done) if len(done) == len(deliv) and done else None
        else:
            last_deliv = deliv
        if last_deliv is None or (dl is not None and last_deliv > dl):
            late_orders.append((oid, o, last_deliv, dl))
    if late_orders:
        print(f"Late / undelivered orders in reveal ({len(late_orders)}):")
        for oid, o, last_deliv, dl in late_orders[:18]:
            r = req_by_id.get(oid, {})
            pick = names.get(r.get("legs", [{}])[0].get("pickup", {}).get("placeId", ""), "?")
            dest = names.get(r.get("legs", [{}])[-1].get("delivery", {}).get("placeId", ""), "?")
            late_h = ((last_deliv - dl) / 60.0) if (last_deliv is not None and dl is not None) else -1
            print(
                f"  {oid} dlr={r.get('dealerId')} {pick}->{dest} opt={o.get('option')} "
                f"price=€{(o.get('priceCents') or 0)/100:.0f} late_h={late_h:.1f} note={bool(r.get('note'))}"
            )


def main() -> None:
    load_dotenv()
    client = CountingClient()
    m = load_map(client)
    geo = Geo(m)
    names = {p["id"]: p.get("name", p["id"])[:10] for p in m["places"]}
    champ_rows = get_champ_rows()
    for seed in TAS_SEEDS:
        rev = ensure_reveal(client, seed, champ_rows[seed]["world"])
        analyze_seed(seed, champ_rows[seed], geo, names, rev)

    rpath = lab_home() / "tas" / "dev-12" / "runs.jsonl"
    if rpath.exists():
        print("=== dev-12/runs.jsonl ===")
        print(rpath.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
