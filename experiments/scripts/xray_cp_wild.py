"""Slot-free reveal X-ray for cp-wild (dev-11 & all 16 dev worlds)."""
from __future__ import annotations

import csv
import json
import pathlib
import statistics
from collections import Counter, defaultdict

from spread_lab.geo import Geo

DAY = 1440


def main() -> None:
    rev_root = pathlib.Path("/tmp/cp-wild-rev")
    champ_rows = {r["seed"]: r for r in (json.loads(l) for l in open("champion/results/dev-L8.jsonl"))}
    map_data = json.loads(pathlib.Path("/home/lab/.spread-lab/map.json").read_text())
    geo = Geo(map_data)

    fut_sd_kinds: Counter = Counter()
    fut_sd_samples = []
    tradein_outcomes = Counter()
    ret_hub_counts_by_seed: dict[str, int] = Counter()

    for seed, rr in sorted(champ_rows.items(), key=lambda kv: kv[1]["margin"]):
        dd = rev_root / f"reveal-{rr['world']}"
        rqs = {row["id"]: row for row in csv.DictReader(open(dd / "requests.csv"))}
        lgs = defaultdict(list)
        for l in csv.DictReader(open(dd / "legs.csv")):
            lgs[l["requestId"]].append(l)
        evs = list(csv.DictReader(open(dd / "events.csv")))
        drvs = list(csv.DictReader(open(dd / "drivers.csv")))
        s30 = geo.supply(drvs, 30.0)
        s55 = geo.supply(drvs, 55.0)
        s70 = geo.supply(drvs, 70.0)

        late_oids = {
            e["line.orderId"]
            for e in evs
            if e["kind"] == "ledger" and e["line.kind"] in ("late_refund", "undelivered_penalty") and e["line.orderId"]
        }

        for rid, row in rqs.items():
            arr = int(row["arrivedAt"])
            avail = [o for o in ("same_day", "next_day", "within_3_days") if row[f"{o}.listPriceCents"]]
            opts = [
                (o, int(row[f"{o}.listPriceCents"]), int(row[f"{o}.quoteCents"]))
                for o in avail
                if row[f"{o}.quoteCents"]
            ]
            non_decl = bool(opts and min(qc / lc for _, lc, qc in opts) < 3.5)
            ls = lgs[rid]
            pk, dl = ls[0]["pickup.placeId"], ls[-1]["delivery.placeId"]
            drv = sum(geo.minutes(l["pickup.placeId"], l["delivery.placeId"]) for l in ls)
            if len(ls) == 2:
                drv += geo.minutes(ls[0]["delivery.placeId"], ls[1]["pickup.placeId"])

            # 1. Check future-day same_day
            if "same_day" in avail:
                dl_sd = int(row["same_day.deadline"])
                if dl_sd // DAY > arr // DAY and not non_decl and s55.get(pk, 0) >= 22:
                    priv = any(
                        l["pickup.privateAddress"] == "True" or l["delivery.privateAddress"] == "True" for l in ls
                    )
                    pk_from = int(ls[0]["pickup.window.from"])
                    slk = dl_sd - max(arr, pk_from) - drv
                    pass_slk = slk >= 150 + 0.75 * drv
                    fut_sd_kinds[(avail == ["same_day"], priv, len(ls), pass_slk, s30.get(pk, 0) < 50)] += 1
                    if len(fut_sd_samples) < 12 and pass_slk and len(ls) == 1:
                        fut_sd_samples.append(
                            (
                                seed,
                                rid,
                                f"{pk}({s30.get(pk,0)})->{dl}({s30.get(dl,0)})",
                                drv,
                                avail,
                                priv,
                                f"arr_d{arr//DAY}h{(arr%DAY)//60}",
                                f"pk_d{pk_from//DAY}h{(pk_from%DAY)//60}",
                                f"dl_d{dl_sd//DAY}h{(dl_sd%DAY)//60}",
                                slk,
                                int(row["same_day.listPriceCents"]) / 100,
                                int(row["referenceFeeCents"]) / 100,
                            )
                        )

            # 2. Check 2-car trade-in performance and true sequential feasibility
            if len(ls) == 2:
                if row["outcome"] == "won":
                    tradein_outcomes[("WON", rid in late_oids)] += 1
                elif non_decl:
                    tradein_outcomes[("LOST_QUOTED", False)] += 1
                else:
                    d0 = geo.minutes(ls[0]["pickup.placeId"], ls[0]["delivery.placeId"])
                    gap = geo.minutes(ls[0]["delivery.placeId"], ls[1]["pickup.placeId"])
                    d1 = geo.minutes(ls[1]["pickup.placeId"], ls[1]["delivery.placeId"])
                    p0_from = max(arr, int(ls[0]["pickup.window.from"]))
                    arr_leg1 = p0_from + d0 + gap
                    p1_from = max(arr_leg1, int(ls[1]["pickup.window.from"]))
                    p1_to = int(ls[1]["pickup.window.to"])
                    best_o = avail[-1]
                    best_dl = int(row[f"{best_o}.deadline"])
                    seq_slack = best_dl - (p1_from + d1)
                    in_win1 = arr_leg1 <= p1_to
                    tradein_outcomes[
                        (
                            "DECLINED",
                            s55.get(pk, 0) >= 22,
                            in_win1 and seq_slack >= 150 + 0.5 * d1,
                            best_dl // DAY > p0_from // DAY,
                        )
                    ] += 1

            # 3. Count newly admitted requests under ret_hub35_d300 (slow options only)
            if not non_decl and s55.get(pk, 0) < 22:
                already_ext = s70.get(pk, 0) >= 30 and drv <= 220
                already_ret = s30.get(dl, 0) >= 200 and drv <= 180
                new_ret = s30.get(dl, 0) >= 35 and drv <= 300
                has_slow = any(o in avail for o in ("next_day", "within_3_days"))
                if new_ret and not (already_ext or already_ret) and has_slow:
                    ret_hub_counts_by_seed[seed] += 1

    print("=== 1. DECLINED FUTURE-DAY SAME_DAY IN s55>=22 (only_sd, priv, nlegs, pass_slack, s30<50) ===")
    for k, v in fut_sd_kinds.most_common():
        print(f"  {k}: {v} ({v/16:.1f}/wk)")
    print("Samples (1-leg, pass_slack):")
    for s in fut_sd_samples:
        print(" ", s)

    print("")
    print("=== 2. 2-CAR TRADE-IN OUTCOMES & SEQUENTIAL FEASIBILITY ACROSS 16 WORLDS ===")
    for k, v in tradein_outcomes.most_common():
        print(f"  {k}: {v} ({v/16:.1f}/wk)")

    print("")
    print("=== 3. NEWLY QUOTED THIN->REGIONAL-HUB SLOW REQUESTS (s30_dest>=35, drv<=300) BY SEED ===")
    for seed, rr in sorted(champ_rows.items(), key=lambda kv: kv[1]["margin"]):
        print(f"  {seed}: champ_margin=€{rr['margin']:7.0f} champ_ot={rr['on_time']:.3f} new_ret_hub_quotes={ret_hub_counts_by_seed[seed]:3d}")


if __name__ == "__main__":
    main()
