"""Parse cached tape.json + reveal-v5.json on all 4 TAS worlds (zero server requests)."""
from __future__ import annotations

import json
from collections import Counter, defaultdict

from spread_lab.env import lab_home, load_dotenv
from spread_lab.geo import Geo, load_map
from spread_lab.lab import CountingClient

TAS_SEEDS = ("dev-12", "dev-01", "dev-08", "dev-07")
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun", "Mon+", "Tue+", "Wed+"]


def analyze_seed(seed: str, geo: Geo, names: dict[str, str]) -> None:
    tas_seed = lab_home() / "tas" / seed
    tape = json.loads((tas_seed / "tape.json").read_text(encoding="utf-8"))
    rev = json.loads((tas_seed / "reveal-v5.json").read_text(encoding="utf-8"))
    reqs = tape["requests"]
    req_by_id = {r["id"]: r for r in reqs}
    roster = tape["roster"]

    if seed == "dev-12":
        print("Sample rev['requests'][0]:", json.dumps(rev["requests"][0])[:300])
        print("Sample rev['orders'][0]:", json.dumps(rev["orders"][0])[:300])

    supply30 = {p_id: sum(1 for d in roster if geo.line_km(d["homePlaceId"], p_id) <= 30.0) for p_id in names}

    # Parse reveal requests
    rev_reqs = {}
    for rr in rev["requests"]:
        rid = rr["request"]["id"] if isinstance(rr.get("request"), dict) else rr.get("request")
        rev_reqs[rid] = rr

    # Day / hour win rate & quote/list ratio (08:00-18:00) -> War & Outage detector!
    day_quoted = Counter()
    day_won = Counter()
    day_won_mults = defaultdict(list)
    day_lost_mults = defaultdict(list)
    place_day_won = defaultdict(Counter)
    place_day_tot = defaultdict(Counter)
    hour_block_stats = defaultdict(lambda: [0, 0])  # (d, h2) -> [won, tot]

    for r in reqs:
        rid = r["id"]
        rr = rev_reqs.get(rid)
        if not rr:
            continue
        outcome = rr.get("outcome")
        quote = rr.get("quote") or {}
        if isinstance(quote, dict) and "prices" in quote:
            quote = quote["prices"]
        d = r["arrivedAt"] // 1440
        tod = r["arrivedAt"] % 1440
        if not quote or not isinstance(quote, dict):
            continue
        by_k = {o["kind"]: o["listPriceCents"] for o in r["options"]}
        first_k = next(iter(quote))
        if first_k not in by_k:
            continue
        mult = quote[first_k] / by_k[first_k]
        if mult >= 3.5:
            continue
        if 480 <= tod <= 1080:
            day_quoted[d] += 1
            pick = r["legs"][0]["pickup"]["placeId"]
            place_day_tot[d][pick] += 1
            hb = (tod - 480) // 120
            hour_block_stats[(d, hb)][1] += 1
            if outcome == "won":
                day_won[d] += 1
                place_day_won[d][pick] += 1
                hour_block_stats[(d, hb)][0] += 1
                won_opt = rr.get("option") or first_k
                if won_opt in quote and won_opt in by_k:
                    day_won_mults[d].append(quote[won_opt] / by_k[won_opt])
            elif outcome == "lost":
                day_lost_mults[d].append(mult)

    print("=" * 95)
    print(f"SEED {seed}: Event Days, Dealers, and Market Structure")
    for d in range(5):
        q, w = day_quoted[d], day_won[d]
        wm = sum(day_won_mults[d]) / len(day_won_mults[d]) if day_won_mults[d] else 0
        lm = sum(day_lost_mults[d]) / len(day_lost_mults[d]) if day_lost_mults[d] else 0
        blocks = " ".join(f"{hour_block_stats[(d,b)][0]}/{hour_block_stats[(d,b)][1]}" for b in range(5))
        # Check regional win-share spike (80km circle around each town) vs rest of country
        best_reg = None
        for p_id in names:
            rw = sum(place_day_won[d][p2] for p2 in names if geo.line_km(p_id, p2) <= 80.0)
            rt = sum(place_day_tot[d][p2] for p2 in names if geo.line_km(p_id, p2) <= 80.0)
            ow = w - rw
            ot = q - rt
            if rt >= 8 and ot >= 8:
                diff = (rw / rt) - (ow / ot)
                cand = (diff, rw, rt, rw / rt, ow / ot, names[p_id])
                if best_reg is None or cand[0] > best_reg[0]:
                    best_reg = cand
        reg_str = (
            f"max80kmΔ={best_reg[5]} {best_reg[1]}/{best_reg[2]}({best_reg[3]:.0%}) vs rest {best_reg[4]:.0%}"
            if best_reg
            else ""
        )
        print(
            f"  {DAYS[d]}: won {w:>3}/{q:<3} ({(w/q if q else 0):5.1%}) [{blocks}] "
            f"won_x={wm:.3f} lost_x={lm:.3f} | {reg_str}"
        )

    # First-morning viewers (drivers viewing between 07:00 and 12:00, fresh active pool) -> better Flu detector!
    views = rev.get("views", [])
    morn_viewers = defaultdict(set)
    all_viewers = defaultdict(set)
    for v in views:
        at = v["at"]
        d = at // 1440
        tod = at % 1440
        if d < 5:
            all_viewers[d].add(v["driverId"])
            if 420 <= tod <= 720:
                morn_viewers[d].add(v["driverId"])
    print(
        "  Active viewers Mon..Fri (all / 07-12h):",
        ", ".join(f"{DAYS[d]}:{len(all_viewers[d])}/{len(morn_viewers[d])}" for d in range(5)),
    )

    # Dealer early vs late volume (Trust investment ROI!)
    print("  Top 6 dealers: Mon+Tue easy(sup>=100,no-note) vs Wed..Fri total list €:")
    dlr_tot = Counter(r["dealerId"] for r in reqs)
    for dlr, tot in dlr_tot.most_common(6):
        d_reqs = [r for r in reqs if r["dealerId"] == dlr]
        mon_tue_all = sum(1 for r in d_reqs if r["arrivedAt"] // 1440 <= 1)
        mon_tue_easy = sum(
            1
            for r in d_reqs
            if r["arrivedAt"] // 1440 <= 1
            and supply30[r["legs"][0]["pickup"]["placeId"]] >= 100
            and not r.get("note")
        )
        wed_fri_list = sum(
            max(o["listPriceCents"] for o in r["options"]) / 100.0
            for r in d_reqs
            if r["arrivedAt"] // 1440 >= 2
        )
        v5_won = sum(1 for r in d_reqs if rev_reqs.get(r["id"], {}).get("outcome") == "won")
        v5_won_mt = sum(
            1
            for r in d_reqs
            if r["arrivedAt"] // 1440 <= 1 and rev_reqs.get(r["id"], {}).get("outcome") == "won"
        )
        main_pick = Counter(names[r["legs"][0]["pickup"]["placeId"]] for r in d_reqs).most_common(2)
        print(
            f"    {dlr} (tot {tot:>3}, v5_won {v5_won:>3}, v5_MonTue_won {v5_won_mt:>2}): "
            f"MonTue={mon_tue_all:>3} (hub_nonote={mon_tue_easy:>2}) | Wed..Fri list=€{wed_fri_list:>8,.0f} | yards={main_pick}"
        )


def main() -> None:
    load_dotenv()
    m = load_map(CountingClient())
    geo = Geo(m)
    names = {p["id"]: p.get("name", p["id"])[:10] for p in m["places"]}
    for seed in TAS_SEEDS:
        analyze_seed(seed, geo, names)


if __name__ == "__main__":
    main()
