"""Slot-free diagnostic of staffing costs, views, hold-out, drops, and batching on dev-09 reveal + dev-L8."""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
REV = REPO / "runs" / "reveal-dev09"


def main() -> None:
    rows = [json.loads(line) for line in (REPO / "champion" / "results" / "dev-L8.jsonl").read_text().splitlines() if line.strip()]
    d09 = next(r for r in rows if r["seed"] == "dev-09")
    print("=== CHAMPION DEV-09 SUMMARY ===")
    print(f"margin: €{d09['margin']:,.2f} | won: {d09['won']} | on_time: {d09['on_time']:.2%}")
    print("ledger (€):", {k: round(v, 2) for k, v in d09["ledger"].items()})
    rev_mean = sum(r["ledger"].get("revenue", 0) for r in rows) / len(rows)
    fee_mean = sum(r["ledger"].get("driver_fee", 0) for r in rows) / len(rows)
    print(f"16-dev mean: revenue €{rev_mean:,.2f}, driver_fee €{fee_mean:,.2f} ({-fee_mean/rev_mean:.1%})")
    print(f"dev-09:      revenue €{d09['ledger']['revenue']:,.2f}, driver_fee €{d09['ledger']['driver_fee']:,.2f} ({-d09['ledger']['driver_fee']/d09['ledger']['revenue']:.1%})")
    print("dev-09 key stats:", {k: d09["stats"][k] for k in sorted(d09["stats"]) if any(w in k for w in ("book", "drop", "warn", "deadline", "late", "lost", "visit", "lead", "won"))})

    reqs = {r["id"]: r for r in csv.DictReader((REV / "requests.csv").open())}
    gigs = {g["id"]: g for g in csv.DictReader((REV / "gigs.csv").open())}
    events = list(csv.DictReader((REV / "events.csv").open()))
    views = list(csv.DictReader((REV / "views.csv").open()))

    warned_at = {}
    won_at = {}
    won_option = {}
    bookings = []
    for e in events:
        at = int(e["at"])
        k = e["kind"]
        if k == "order_won":
            won_at[e["orderId"]] = at
            won_option[e["orderId"]] = e.get("option", "")
        elif k == "deadline_close":
            warned_at.setdefault(e["orderId"], at)
        elif k == "gig_booked":
            bookings.append(e)

    views_by_gig = defaultdict(list)
    driver_gig_views = defaultdict(list)
    for v in views:
        gid = v["gigId"]
        did = v["driverId"]
        at = int(v["at"])
        fee = int(v["feeCents"])
        views_by_gig[gid].append((at, did, fee))
        driver_gig_views[(gid, did)].append((at, fee))

    print()
    print(f"=== GIGS & BOOKINGS ON DEV-09 (gigs={len(gigs)}, bookings={len(bookings)}, views={len(views)}) ===")
    print("sample gig keys:", list(next(iter(gigs.values())).keys()))
    by_status = Counter(g["status"] for g in gigs.values())
    print("gig statuses:", dict(by_status))

    done_gigs = [g for g in gigs.values() if g["status"] == "done"]
    total_done_fee = 0
    total_done_ref = 0
    bucket_stats = defaultdict(lambda: [0, 0.0, 0.0])
    day_mults = defaultdict(list)
    wait_buckets = Counter()
    booker_prior_views = Counter()
    booker_first_saw_ratio = []
    mult_hist = Counter()

    for g in done_gigs:
        gid = g["id"]
        fee = int(g["feeCents"])
        oids = json.loads(g["orders"]) if g.get("orders", "").startswith("[") else [s.strip() for s in g.get("orders", "").split(",") if s.strip()]
        if not oids and "stops" in g:
            stops = json.loads(g["stops"])
            oids = list(dict.fromkeys(s["orderId"] for s in stops))
        ref = sum(int(reqs[o]["referenceFeeCents"]) for o in oids if o in reqs)
        if ref == 0:
            continue
        total_done_fee += fee
        total_done_ref += ref
        mult = fee / ref
        if mult <= 0.86:
            mult_hist["<=0.86"] += 1
        elif mult <= 0.95:
            mult_hist["0.87-0.95"] += 1
        elif mult <= 1.10:
            mult_hist["0.96-1.10"] += 1
        elif mult <= 1.30:
            mult_hist["1.11-1.30"] += 1
        elif mult <= 1.61:
            mult_hist["1.31-1.60"] += 1
        else:
            mult_hist[">1.60"] += 1

        o0 = oids[0]
        opt = reqs[o0].get("option") or won_option.get(o0, "?")
        posted_at = int(g["postedAt"])
        b_ev = [e for e in bookings if e["gigId"] == gid]
        booked_at = int(b_ev[-1]["at"]) if b_ev else posted_at
        booker = g.get("driverId") or (b_ev[-1].get("driverId") if b_ev else "")
        wait = booked_at - posted_at
        if wait <= 5:
            wb = "0-5m"
        elif wait <= 30:
            wb = "6-30m"
        elif wait <= 120:
            wb = "31-120m"
        elif wait <= 360:
            wb = "2-6h"
        else:
            wb = ">6h"
        wait_buckets[wb] += 1

        is_warn = any(o in warned_at and warned_at[o] <= booked_at for o in oids)
        is_pair = len(oids) > 1
        cat = "pair" if is_pair else (f"{opt}_warn" if is_warn else f"{opt}_norm")
        bucket_stats[cat][0] += 1
        bucket_stats[cat][1] += fee / 100
        bucket_stats[cat][2] += ref / 100

        day = posted_at // 1440
        if not is_warn and not is_pair:
            day_mults[day].append(mult)

        pv = [x for x in driver_gig_views.get((gid, booker), []) if x[0] <= booked_at]
        booker_prior_views[len(pv)] += 1
        if len(pv) >= 2:
            first_fee = pv[0][1]
            booker_first_saw_ratio.append((first_fee / ref, fee / ref, booked_at - pv[0][0], opt))

    print(f"Done gigs total: n={len(done_gigs)}, paid €{total_done_fee/100:,.2f}, ref €{total_done_ref/100:,.2f}, ratio={total_done_fee/total_done_ref:.3f}x")
    print(f"Fee mult histogram: {dict(mult_hist)}")
    print("Excess above 0.85x reference = €{:,.2f}".format((total_done_fee - 0.85 * total_done_ref) / 100))
    print("Excess above 0.75x reference = €{:,.2f}".format((total_done_fee - 0.75 * total_done_ref) / 100))
    print("10% of driver_fee = €{:,.2f}".format(-d09["ledger"]["driver_fee"] * 0.10))
    print()
    print("Breakdown by category (done gigs):")
    for cat, (n, fe, re_) in sorted(bucket_stats.items()):
        print(f"  {cat:<22} n={n:>3}  fee=€{fe:>8,.1f}  ref=€{re_:>8,.1f}  mult={fe/re_:.3f}x  excess_vs_0.85=€{fe - 0.85*re_:>7,.1f}")

    print()
    print("Wait from post to final booking (done gigs):", dict(wait_buckets))
    print("Non-warn single-car mult by post day (0=Mon..4=Fri):")
    for d in sorted(day_mults):
        ms = day_mults[d]
        print(f"  day {d}: n={len(ms):>3}, mean={sum(ms)/len(ms):.3f}x, median={sorted(ms)[len(ms)//2]:.3f}x, >1.05x={sum(1 for x in ms if x > 1.05)}")

    print()
    print("How many times did the eventual booker view the gig before booking?", dict(sorted(booker_prior_views.items())))
    if booker_first_saw_ratio:
        extra_paid = sum((b - f) for f, b, _, _ in booker_first_saw_ratio) / len(booker_first_saw_ratio)
        extra_eur = sum((b - f) * 75 for f, b, _, _ in booker_first_saw_ratio)
        print(f"Repeat-viewer bookers: n={len(booker_first_saw_ratio)}, mean first_saw={sum(f for f,_,_,_ in booker_first_saw_ratio)/len(booker_first_saw_ratio):.3f}x -> booked={sum(b for _,b,_,_ in booker_first_saw_ratio)/len(booker_first_saw_ratio):.3f}x (hold-out delta +{extra_paid:.3f}x, ~€{extra_eur:,.0f})")
        for sample in booker_first_saw_ratio[:12]:
            print(f"    first_saw={sample[0]:.2f}x -> booked={sample[1]:.2f}x after {sample[2]}m ({sample[3]})")

    drop_evs = [e for e in events if e["kind"] == "gig_dropped"]
    drop_mults = []
    for e in drop_evs:
        gid = e["gigId"]
        g = gigs.get(gid)
        if not g:
            continue
        oids = json.loads(g["orders"]) if g.get("orders", "").startswith("[") else [s.strip() for s in g.get("orders", "").split(",") if s.strip()]
        ref = sum(int(reqs[o]["referenceFeeCents"]) for o in oids if o in reqs)
        bs = [b for b in bookings if b["gigId"] == gid and int(b["at"]) <= int(e["at"])]
        if bs and ref > 0:
            b = bs[-1]
            drop_mults.append((int(b["feeCents"]) / ref, int(e["at"]) - int(b["at"]), reqs[oids[0]].get("option", "?")))
    print()
    print(f"Drops on dev-09: n={len(drop_mults)}")
    if drop_mults:
        print(f"  mean mult at booking before drop: {sum(x[0] for x in drop_mults)/len(drop_mults):.3f}x, median hold={sorted(x[1] for x in drop_mults)[len(drop_mults)//2]}m")
        print("  by option:", dict(Counter(x[2] for x in drop_mults)))

    won_by_min = Counter(won_at.values())
    batches = {m: c for m, c in won_by_min.items() if c >= 2}
    print()
    print(f"Batch wins (minutes with >=2 order_won): {len(batches)} minutes covering {sum(batches.values())}/{len(won_at)} won orders")


if __name__ == "__main__":
    main()
