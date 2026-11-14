"""Offline X-ray of dev-12 limits-won-apply.jsonl + tape.json + reveal-v5.json (zero network calls)."""
from __future__ import annotations

import json
import statistics
from collections import Counter, defaultdict

from spread_lab.env import lab_home, load_dotenv
from spread_lab.geo import Geo, load_map
from spread_lab.lab import CountingClient

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun", "Mon+", "Tue+", "Wed+"]


def main() -> None:
    load_dotenv()
    m = load_map(CountingClient())
    geo = Geo(m)
    names = {p["id"]: p.get("name", p["id"])[:10] for p in m["places"]}

    d12 = lab_home() / "tas" / "dev-12"
    tape = json.loads((d12 / "tape.json").read_text(encoding="utf-8"))
    reqs = {r["id"]: r for r in tape["requests"]}
    roster = tape["roster"]
    supply30 = {p_id: sum(1 for d in roster if geo.line_km(d["homePlaceId"], p_id) <= 30.0) for p_id in names}
    supply55 = {p_id: sum(1 for d in roster if geo.line_km(d["homePlaceId"], p_id) <= 55.0) for p_id in names}

    lines = [json.loads(line) for line in (d12 / "limits-won-apply.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    print(f"Loaded {len(lines)} won orders from limits-won-apply.jsonl on dev-12")

    # 1. Limit / list normalized by (1 + 0.01 * trust) across (day, pickup town) -> find exact Outage & War!
    print("=== 1. NORMALIZED LIMIT x / (1 + 0.01*trust) BY DAY AND REGION (08:00-18:00 vs evening) ===")
    for d in range(5):
        d_lines = [l for l in lines if l["day"] == d and l.get("x")]
        daytime = [l for l in d_lines if 480 <= (l["at"] % 1440) <= 1080]
        evening = [l for l in d_lines if not (480 <= (l["at"] % 1440) <= 1080)]
        dt_norm = [l["x"] / (1 + 0.01 * l["trust"]) for l in daytime]
        ev_norm = [l["x"] / (1 + 0.01 * l["trust"]) for l in evening]
        print(
            f"  {DAYS[d]}: daytime n={len(dt_norm):>2} med_norm={statistics.median(dt_norm) if dt_norm else 0:.3f} | "
            f"evening n={len(ev_norm):>2} med_norm={statistics.median(ev_norm) if ev_norm else 0:.3f}"
        )
        # Check each town's 80km circle during daytime
        town_scores = []
        for p_id in names:
            in_c = [l["x"] / (1 + 0.01 * l["trust"]) for l in daytime if geo.line_km(p_id, l["pickup"]) <= 80.0]
            out_c = [l["x"] / (1 + 0.01 * l["trust"]) for l in daytime if geo.line_km(p_id, l["pickup"]) > 80.0]
            if len(in_c) >= 4 and len(out_c) >= 4:
                town_scores.append((statistics.median(in_c) - statistics.median(out_c), names[p_id], len(in_c), statistics.median(in_c), statistics.median(out_c)))
        town_scores.sort(reverse=True)
        if town_scores:
            top = town_scores[0]
            bot = town_scores[-1]
            print(f"       max 80km circle: {top[1]} (n={top[2]}) med={top[3]:.3f} vs out={top[4]:.3f} (Δ={top[0]:+.3f})")
            print(f"       min 80km circle: {bot[1]} (n={bot[2]}) med={bot[3]:.3f} vs out={bot[4]:.3f} (Δ={bot[0]:+.3f})")

    # 2. Dealer win shares by day in v5 / Layer 1!
    print("=== 2. TOP DEALERS: DAILY WON / TOTAL REQUESTS & TRUST IN LAYER 1 ===")
    won_ids = {l["rid"]: l for l in lines}
    dlr_counts = Counter(r["dealerId"] for r in tape["requests"])
    for dlr, _ in dlr_counts.most_common(8):
        parts = []
        for d in range(5):
            tot_d = [r for r in tape["requests"] if r["dealerId"] == dlr and r["arrivedAt"] // 1440 == d]
            won_d = [won_ids[r["id"]] for r in tot_d if r["id"] in won_ids]
            trs = [w["trust"] for w in won_d]
            med_norm = statistics.median([w["x"] / (1 + 0.01 * w["trust"]) for w in won_d]) if won_d else 0
            tr_str = f"tr={min(trs)}..{max(trs)}" if trs else "tr=-"
            parts.append(f"{DAYS[d]}:{len(won_d)}/{len(tot_d)}({(len(won_d)/len(tot_d) if tot_d else 0):.0%},{tr_str},nx={med_norm:.2f})")
        print(f"  {dlr}: " + " | ".join(parts))

    # 3. Inspect v5's 246 won orders: which lost money or went late in reveal-v5.json?
    rev = json.loads((d12 / "reveal-v5.json").read_text(encoding="utf-8"))
    # Wait: check how booked fees map to orders in reveal-v5.json or limits-won-apply!
    # In limits-won-apply, we have exact limit `lo` and `ref` (referenceFeeCents)!
    thin_margin = []
    for l in lines:
        lim_eur = (l["lo"] or 0) / 100.0
        ref_eur = l["ref"] / 100.0
        est_margin = lim_eur - 0.90 * ref_eur
        thin_margin.append((est_margin, lim_eur, ref_eur, l))
    thin_margin.sort(key=lambda t: t[0])
    print("=== 3. WORST 12 WON ORDERS EVEN AT PERFECT LIMIT PRICE (lo - 0.90*ref) ===")
    for em, lim_e, ref_e, l in thin_margin[:12]:
        print(
            f"  {l['rid']} {DAYS[l['day']]} dlr={l['dealer']} {names[l['pickup']]}->{names[l['delivery']]} "
            f"opt={l['option']} limit=€{lim_e:.1f} ref=€{ref_e:.1f} x={l['x']:.3f} est_m=€{em:+.1f}"
        )

    # 4. Inspect UNWON requests on dev-12 (785 requests!): where is the untapped goldmine?!
    unwon = [r for r in tape["requests"] if r["id"] not in won_ids]
    print(f"=== 4. UNWON REQUESTS ON dev-12 ({len(unwon)} requests): BY SUPPLY CLASS & DAY ===")
    by_class = Counter()
    by_day_hub = Counter()
    for r in unwon:
        p_id = r["legs"][0]["pickup"]["placeId"]
        d_id = r["legs"][-1]["delivery"]["placeId"]
        s30 = supply30[p_id]
        s55 = supply55[p_id]
        ds30 = supply30[d_id]
        d = r["arrivedAt"] // 1440
        if s30 >= 200:
            cls = "capital_30km>=200"
            by_day_hub[d] += 1
        elif s55 >= 200:
            cls = "cap_ring_55km>=200"
            by_day_hub[d] += 1
        elif s30 >= 35:
            cls = "mid_hub_30km>=35"
        elif s30 >= 22:
            cls = "small_22..34"
        elif ds30 >= 200:
            cls = "thin->capital_return"
        else:
            cls = "thin_other"
        by_class[cls] += 1
    for k, v in by_class.most_common():
        print(f"  {k:<24}: {v:>4} requests")
    print("  Unwon capital + cap_ring by day:", {DAYS[d]: by_day_hub[d] for d in range(5)})


if __name__ == "__main__":
    main()
