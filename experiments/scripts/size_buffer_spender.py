"""Slot-free sizing for c4 (buffer spender) on revealed champion dev worlds."""
from __future__ import annotations

import collections
import csv
import json
import math
import sys
from pathlib import Path

from spread_lab.notes import parse_note_v2

csv.field_size_limit(10**9)
DAY = 1440
HOUR = 60


def rd(d: Path, name: str) -> list[dict[str, str]]:
    with open(d / f"{name}.csv", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def hav(a: tuple[float, float], b: tuple[float, float]) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(h))


def main() -> None:
    dirs = [Path(p) for p in sys.argv[1:]]
    if not dirs:
        print("Usage: python experiments/scripts/size_buffer_spender.py <reveal-dir>...")
        return
    print("requests.csv columns:", list(rd(dirs[0], "requests")[0].keys()))

    tot = collections.Counter()
    for d in dirs:
        places = {p["id"]: (float(p["lat"]), float(p["lon"])) for p in rd(d, "places")}
        line = {(a, b): hav(places[a], places[b]) for a in places for b in places}
        roads = {(r["from"], r["to"]): int(r["minutes"]) for r in rd(d, "roads")}
        drivers = rd(d, "drivers")
        homes = collections.Counter(x["homePlaceId"] for x in drivers)
        sup30 = {p: sum(n for h, n in homes.items() if line[(p, h)] <= 30.0) for p in places}

        legs_by_req = collections.defaultdict(list)
        for leg in rd(d, "legs"):
            legs_by_req[leg["requestId"]].append(leg)

        events = rd(d, "events")
        late = {
            e["line.orderId"]
            for e in events
            if e["kind"] == "ledger" and e["line.kind"] in ("late_refund", "undelivered_penalty")
        }
        margin_cents = collections.defaultdict(int)
        for e in events:
            if e["kind"] == "ledger" and e["line.orderId"]:
                margin_cents[e["line.orderId"]] += int(e["line.cents"])

        reqs = rd(d, "requests")
        c = collections.Counter()
        for r in reqs:
            rid = r["id"]
            ls = sorted(legs_by_req[rid], key=lambda x: int(x["leg"]))
            pk = ls[0]["pickup.placeId"]
            s = sup30[pk]
            drv = sum(roads[(l["pickup.placeId"], l["delivery.placeId"])] for l in ls)
            if len(ls) == 2:
                drv += roads[(ls[0]["delivery.placeId"], ls[1]["pickup.placeId"])]
            arr = int(r["arrivedAt"])
            tod = arr % DAY
            note_ok = True
            if r["note"]:
                pn = parse_note_v2({"text": r["note"]}, arr)
                note_ok = not pn.unsure
            base_easy = s >= 100 and drv <= 120 and note_ok
            opts = [k for k in ("same_day", "next_day", "within_3_days") if r[f"{k}.deadline"]]
            quoted = [
                k
                for k in opts
                if r.get(f"{k}.quoteCents") and int(r[f"{k}.quoteCents"]) < 3 * int(r[f"{k}.listPriceCents"])
            ]
            if base_easy:
                c["base_easy_all"] += 1
                if quoted:
                    c["base_easy_quoted"] += 1
                    has_easy_opt = any(not (k == "same_day" and tod >= 13 * HOUR) for k in quoted)
                    if has_easy_opt:
                        c["easy_opt_quoted"] += 1
                    if r["outcome"] == "won":
                        opt = r["option"]
                        is_sd_after13 = opt == "same_day" and tod >= 13 * HOUR
                        tag = "sd_after13" if is_sd_after13 else "easy_opt"
                        c[f"won_{tag}"] += 1
                        c[f"margin_{tag}"] += margin_cents[rid]
                        if rid in late:
                            c[f"late_{tag}"] += 1
                        else:
                            c[f"ontime_{tag}"] += 1
                    elif r["outcome"] == "lost":
                        c["lost_quoted_easy"] += 1
        tot.update(c)
        won_all = sum(1 for r in reqs if r["outcome"] == "won")
        print(
            f"{d.name}: won={won_all} late={len(late)} ontime={1 - len(late)/won_all:.3f} | "
            f"easy_quoted={c['easy_opt_quoted']} won_easy={c['won_easy_opt']} (late={c['late_easy_opt']}, "
            f"avg_margin=€{c['margin_easy_opt']/max(1,c['won_easy_opt'])/100:.1f}) "
            f"lost_easy={c['lost_quoted_easy']} | won_sd_after13={c['won_sd_after13']} (late={c['late_sd_after13']})"
        )
    print(
        f"TOTAL (4 worlds): easy_quoted={tot['easy_opt_quoted']} ({tot['easy_opt_quoted']/4:.1f}/w), "
        f"won_easy={tot['won_easy_opt']} ({tot['won_easy_opt']/4:.1f}/w), "
        f"late_easy={tot['late_easy_opt']}/{tot['won_easy_opt']} ({tot['late_easy_opt']/max(1,tot['won_easy_opt']):.2%}), "
        f"lost_easy={tot['lost_quoted_easy']} ({tot['lost_quoted_easy']/4:.1f}/w), "
        f"won_sd_after13={tot['won_sd_after13']} (late={tot['late_sd_after13']}/{tot['won_sd_after13']})"
    )


if __name__ == "__main__":
    main()
