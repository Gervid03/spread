"""Verify exact reveal stats for (1) 2-car trade-ins full P&L + late rate, (2) future-day same_day late rate + margin, (3) regional 80km outages."""
from __future__ import annotations

import csv
import json
import pathlib
from collections import Counter, defaultdict

from spread_lab.geo import Geo

DAY = 1440


def main() -> None:
    rev_root = pathlib.Path("/tmp/cp-wild-rev")
    champ_rows = {r["seed"]: r for r in (json.loads(l) for l in open("champion/results/dev-L8.jsonl"))}
    map_data = json.loads(pathlib.Path("/home/lab/.spread-lab/map.json").read_text())
    geo = Geo(map_data)

    ti_tot = Counter()
    ti_by_seed = defaultdict(lambda: [0, 0, 0.0])  # won, late, net_eur
    fut_sd_perf = defaultdict(lambda: [0, 0, 0.0, 0.0, 0.0])  # won, late, rev, fee, net

    for seed, rr in sorted(champ_rows.items(), key=lambda kv: kv[1]["margin"]):
        dd = rev_root / f"reveal-{rr['world']}"
        rqs = {row["id"]: row for row in csv.DictReader(open(dd / "requests.csv"))}
        lgs = defaultdict(list)
        for l in csv.DictReader(open(dd / "legs.csv")):
            lgs[l["requestId"]].append(l)
        evs = list(csv.DictReader(open(dd / "events.csv")))

        order_lg = defaultdict(Counter)
        late_oids = set()
        for e in evs:
            if e["kind"] == "ledger" and e["line.orderId"]:
                oid = e["line.orderId"]
                order_lg[oid][e["line.kind"]] += int(e["line.cents"])
                if e["line.kind"] in ("late_refund", "undelivered_penalty"):
                    late_oids.add(oid)

        for rid, row in rqs.items():
            if row["outcome"] != "won":
                continue
            ls = lgs[rid]
            lg = order_lg[rid]
            net = sum(lg.values()) / 100.0
            rev = lg["revenue"] / 100.0
            fee = -lg["driver_fee"] / 100.0
            is_late = rid in late_oids

            if len(ls) == 2:
                ti_tot["won"] += 1
                ti_tot["late"] += int(is_late)
                for k, v in lg.items():
                    ti_tot[f"eur_{k}"] += v / 100.0
                ti_tot["eur_net"] += net
                ti_by_seed[seed][0] += 1
                ti_by_seed[seed][1] += int(is_late)
                ti_by_seed[seed][2] += net

            if row["option"] == "same_day" and len(ls) == 1:
                arr = int(row["arrivedAt"])
                dl_sd = int(row["same_day.deadline"])
                priv = ls[0]["pickup.privateAddress"] == "True" or ls[0]["delivery.privateAddress"] == "True"
                bucket = (
                    "future_day_dealer"
                    if (dl_sd // DAY > arr // DAY and not priv)
                    else ("future_day_priv" if dl_sd // DAY > arr // DAY else "today_same_day")
                )
                fut_sd_perf[bucket][0] += 1
                fut_sd_perf[bucket][1] += int(is_late)
                fut_sd_perf[bucket][2] += rev
                fut_sd_perf[bucket][3] += fee
                fut_sd_perf[bucket][4] += net

    print("=== 1. FULL LEDGER OF 2-CAR TRADE-INS WON BY CHAMPION ACROSS 16 DEV WORLDS ===")
    for k, v in sorted(ti_tot.items()):
        print(f"  {k:25s}: {v:8.2f}")
    print("  By seed (won, late, net_eur):", dict(ti_by_seed))

    print("")
    print("=== 2. REALIZED PERFORMANCE OF WON 1-CAR 'same_day' ORDERS: FUTURE-DAY VS TODAY ===")
    for b, st in sorted(fut_sd_perf.items()):
        w, lt, rv, fe, nt = st
        print(
            f"  {b:20s}: won={w:4d} ({w/16:4.1f}/wk)  late={lt:2d} ({100*lt/max(1,w):5.2f}%)  "
            f"rev/w=€{rv/max(1,w):5.1f}  fee/w=€{fe/max(1,w):5.1f}  net/w=€{nt/max(1,w):5.1f}"
        )


if __name__ == "__main__":
    main()
