"""Slot-free analysis of the 9 (pickup supply: hub/mid/thin x drive: short/mid/long) classes
on revealed champion v3T worlds (dev-06 alone and all 16 dev worlds).
"""
from __future__ import annotations

import collections
import csv
import json
import math
import statistics as st
import sys
from pathlib import Path

csv.field_size_limit(10**9)


def rd(d: Path, name: str) -> list[dict]:
    with open(d / f"{name}.csv", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def hav(a: tuple[float, float], b: tuple[float, float]) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(h))


def sup_cls(n: int) -> str:
    return "hub" if n >= 200 else ("mid" if n >= 30 else "thin")


def drv_cls(m: int) -> str:
    return "short" if m < 60 else ("mid" if m <= 180 else "long")


def ensure_dev_reveals(out_root: Path) -> list[Path]:
    from spread import reveal_csv
    from spread_lab.env import load_dotenv

    load_dotenv()
    out_root.mkdir(parents=True, exist_ok=True)
    folders = []
    for line in Path("champion/results/dev-L8.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        folder = out_root / f"{row['seed']}-{row['world']}"
        if not (folder / "requests.csv").exists():
            sys.argv = ["spread-reveal-csv", row["world"], "--out", str(folder)]
            reveal_csv.main()
        folders.append(folder)
    return sorted(folders)


def analyze(folders: list[Path], label: str, show_days: bool = False) -> None:
    n_worlds = len(folders)
    stats = collections.defaultdict(lambda: collections.Counter())
    pl_won = collections.defaultdict(list)
    pl_lost = collections.defaultdict(list)
    fee_rat = collections.defaultdict(list)
    typ_list = collections.defaultdict(list)
    sub_stats = collections.defaultdict(lambda: collections.Counter())
    day_stats = collections.defaultdict(lambda: collections.Counter())

    for d in folders:
        places = {p["id"]: (float(p["lat"]), float(p["lon"])) for p in rd(d, "places")}
        line = {(a, b): hav(places[a], places[b]) for a in places for b in places}
        roads = {(r["from"], r["to"]): (float(r["km"]), int(r["minutes"])) for r in rd(d, "roads")}
        drivers = {x["id"]: x for x in rd(d, "drivers")}
        homes = collections.Counter(x["homePlaceId"] for x in drivers.values())
        supply = {p: sum(n for h, n in homes.items() if line[(p, h)] <= 30.0) for p in places}
        gate_supply = {p: sum(n for h, n in homes.items() if line[(p, h)] <= 55.0) for p in places}

        reqs = {r["id"]: r for r in rd(d, "requests")}
        legs_by_req = collections.defaultdict(list)
        for l in rd(d, "legs"):
            legs_by_req[l["requestId"]].append(l)
        for rid in legs_by_req:
            legs_by_req[rid].sort(key=lambda x: int(x["leg"]))

        events = rd(d, "events")
        gigs = {g["id"]: g for g in rd(d, "gigs")}
        gig_orders = {gid: json.loads(g["stops"]) for gid, g in gigs.items()}

        late_orders = set()
        ledger_by_order = collections.defaultdict(lambda: collections.Counter())
        for e in events:
            if e["kind"] == "ledger" and e.get("line.orderId"):
                oid = e["line.orderId"]
                k = e["line.kind"]
                c = int(e["line.cents"])
                ledger_by_order[oid][k] += c
                if k in ("late_refund", "undelivered_penalty"):
                    late_orders.add(oid)

        last_book_fee = {}
        for e in events:
            if e["kind"] == "gig_booked":
                stops = gig_orders.get(e["gigId"], [])
                oids = list(dict.fromkeys(s["orderId"] for s in stops))
                if len(oids) == 1:
                    last_book_fee[oids[0]] = int(e["feeCents"])

        for rid, r in reqs.items():
            rlegs = legs_by_req[rid]
            pick = rlegs[0]["pickup.placeId"]
            dest = rlegs[-1]["delivery.placeId"]
            drive = sum(roads[(l["pickup.placeId"], l["delivery.placeId"])][1] for l in rlegs)
            if len(rlegs) == 2:
                drive += roads[(rlegs[0]["delivery.placeId"], rlegs[1]["pickup.placeId"])][1]

            sc = sup_cls(supply[pick])
            dc = drv_cls(drive)
            dest_sc = sup_cls(supply[dest])
            c9 = f"{sc}-{dc}"
            c_sub = f"{sc}->{dest_sc} {dc}"
            day = int(r["arrivedAt"]) // 1440
            is_ext_ring = gate_supply[pick] < 22

            ref_fee = int(r["referenceFeeCents"])
            floor_cents = ref_fee * 1.25 / (1.0 - 0.08)

            quoted_opts = []
            for ok in ("same_day", "next_day", "within_3_days"):
                qc = r.get(f"{ok}.quoteCents")
                lc = r.get(f"{ok}.listPriceCents")
                if qc and lc:
                    q_val, l_val = int(qc), int(lc)
                    quoted_opts.append((ok, q_val, l_val))

            is_decline = (not quoted_opts) or (len(quoted_opts) == 1 and abs(quoted_opts[0][1] / quoted_opts[0][2] - 4.0) < 0.02)
            is_floored = False
            min_pl = None
            if not is_decline:
                for ok, q_val, l_val in quoted_opts:
                    if abs(q_val - int(floor_cents + 0.5)) <= 2:
                        is_floored = True
                min_pl = min(q_val / l_val for _, q_val, l_val in quoted_opts)
                first_l = quoted_opts[0][2]
                typ_list[c9].append(ref_fee / first_l)

            for bucket in (stats[c9], sub_stats[c_sub], stats["ALL"]):
                bucket["reqs"] += 1
                if is_decline:
                    bucket["decl"] += 1
                else:
                    bucket["quot"] += 1
                    if is_floored:
                        bucket["flr"] += 1
                    else:
                        bucket["nrm"] += 1
                        if not is_ext_ring:
                            bucket["learn_q"] += 1

            if not is_decline:
                day_stats[day]["quot"] += 1
                if not is_floored:
                    day_stats[day]["nrm"] += 1
                if r["outcome"] == "won":
                    day_stats[day]["won"] += 1
                    if not is_floored:
                        day_stats[day]["won_nrm"] += 1
                    for bucket in (stats[c9], sub_stats[c_sub], stats["ALL"]):
                        bucket["won"] += 1
                        if is_floored:
                            bucket["won_flr"] += 1
                        else:
                            bucket["won_nrm"] += 1
                            if not is_ext_ring:
                                bucket["learn_w"] += 1
                        if rid in late_orders:
                            bucket["late"] += 1
                        for lk, lv in ledger_by_order[rid].items():
                            bucket[f"L_{lk}"] += lv
                            bucket["L_net"] += lv
                    if min_pl is not None:
                        pl_won[c9].append(min_pl)
                    if rid in last_book_fee and ref_fee > 0:
                        fee_rat[c9].append(last_book_fee[rid] / ref_fee)
                elif r["outcome"] == "lost":
                    if min_pl is not None:
                        pl_lost[c9].append(min_pl)

    print()
    print(f"=== {label} ({n_worlds} world(s)) ===")
    if show_days:
        for day in sorted(day_stats):
            ds = day_stats[day]
            print(
                f"  Day {day}: quot={ds['quot']} won={ds['won']} ({100*ds['won']/max(1,ds['quot']):.1f}%) "
                f"nrm={ds['nrm']} won_nrm={ds['won_nrm']} ({100*ds['won_nrm']/max(1,ds['nrm']):.1f}%)"
            )
    hdr = (
        f"{'Class':<11} {'Req/w':>6} {'Quot/w':>6} {'Nrm/w':>6} {'Lrn/w':>6} {'Flr%':>5} "
        f"{'Won/w':>6} {'WinQ%':>6} {'WinN%':>6} {'WinF%':>6} "
        f"{'P/L_W':>5} {'P/L_L':>5} {'Typ/L':>5} {'Fee/T':>5} "
        f"{'Rev/w':>7} {'Fee/w':>7} {'Mrg/w':>7} {'Mrg%':>5} {'Mrg/O':>6} {'Late%':>6}"
    )
    print(hdr)
    print("-" * len(hdr))
    order_9 = [f"{s}-{d}" for s in ("hub", "mid", "thin") for d in ("short", "mid", "long")] + ["ALL"]
    for c in order_9:
        b = stats[c]
        if not b["reqs"]:
            continue
        qw = b["quot"] / n_worlds
        nw = b["nrm"] / n_worlds
        lw = b["learn_q"] / n_worlds
        ww = b["won"] / n_worlds
        flr_pct = 100 * b["flr"] / max(1, b["quot"])
        win_q = 100 * b["won"] / max(1, b["quot"])
        win_n = 100 * b["won_nrm"] / max(1, b["nrm"])
        win_f = 100 * b["won_flr"] / max(1, b["flr"])
        plw = st.median(pl_won[c]) if pl_won[c] else 0.0
        pll = st.median(pl_lost[c]) if pl_lost[c] else 0.0
        tl = st.median(typ_list[c]) if typ_list[c] else 0.0
        ft = st.median(fee_rat[c]) if fee_rat[c] else 0.0
        rev_w = b["L_revenue"] / 100 / n_worlds
        fee_w = -b["L_driver_fee"] / 100 / n_worlds
        mrg_w = b["L_net"] / 100 / n_worlds
        mrg_pct = 100 * b["L_net"] / max(1, b["L_revenue"])
        mrg_o = (b["L_net"] / 100) / max(1, b["won"])
        late_pct = 100 * b["late"] / max(1, b["won"])
        print(
            f"{c:<11} {b['reqs']/n_worlds:6.1f} {qw:6.1f} {nw:6.1f} {lw:6.1f} {flr_pct:4.0f}% "
            f"{ww:6.1f} {win_q:5.1f}% {win_n:5.1f}% {win_f:5.1f}% "
            f"{plw:5.2f} {pll:5.2f} {tl:5.2f} {ft:5.2f} "
            f"{rev_w:7.0f} {fee_w:7.0f} {mrg_w:7.0f} {mrg_pct:4.1f}% {mrg_o:6.1f} {late_pct:5.1f}%"
        )

    print()
    print(f"--- Sub-classes (pickup->dest drive) on {label}, sorted by Quot/w ---")
    print(
        f"{'SubClass':<18} {'Req/w':>6} {'Quot/w':>6} {'Nrm/w':>6} {'Flr%':>5} "
        f"{'Won/w':>6} {'WinQ%':>6} {'WinN%':>6} {'Mrg/w':>7} {'Mrg%':>5} {'Mrg/O':>6} {'Late%':>6}"
    )
    for c, b in sorted(sub_stats.items(), key=lambda kv: -kv[1]["quot"]):
        if b["quot"] / n_worlds < 2.0:
            continue
        print(
            f"{c:<18} {b['reqs']/n_worlds:6.1f} {b['quot']/n_worlds:6.1f} {b['nrm']/n_worlds:6.1f} "
            f"{100*b['flr']/max(1,b['quot']):4.0f}% {b['won']/n_worlds:6.1f} "
            f"{100*b['won']/max(1,b['quot']):5.1f}% {100*b['won_nrm']/max(1,b['nrm']):5.1f}% "
            f"{b['L_net']/100/n_worlds:7.0f} {100*b['L_net']/max(1,b['L_revenue']):4.1f}% "
            f"{(b['L_net']/100)/max(1,b['won']):6.1f} {100*b['late']/max(1,b['won']):5.1f}%"
        )


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--all-dev":
        dev_folders = ensure_dev_reveals(Path("runs/reveals/dev16"))
        dev06 = [f for f in dev_folders if f.name.startswith("dev-06-")]
        if dev06:
            analyze(dev06, "dev-06 (champion v3T)", show_days=True)
        analyze(dev_folders, "All 16 dev worlds (champion v3T)", show_days=True)
    else:
        paths = [Path(p) for p in sys.argv[1:]]
        analyze(paths, f"{len(paths)} world(s)", show_days=True)
