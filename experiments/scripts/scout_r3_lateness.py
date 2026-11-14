"""R3: How late is late.

Measures minutes late per late order across revealed worlds, split by whether
a driver held the order at the deadline warning (no deadline_close event).
Reports both ledger lateness (truth.deliveredAt - deadline, which includes overnight
closure if a driver arrives after 20:00 closing) and driver arrival lateness
(delivered event timestamp - deadline).
"""
import csv
import re
import statistics as st
import sys
from pathlib import Path

csv.field_size_limit(10**9)


def rd(d: Path, name: str) -> list[dict[str, str]]:
    with open(d / f"{name}.csv", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def main() -> None:
    dirs = [Path(p) for p in sys.argv[1:]]
    if len(dirs) == 1 and not (dirs[0] / "events.csv").exists():
        dirs = sorted(dirs[0].glob("reveal-*"))

    held_ledger_late = []
    held_arrival_late = []
    held_single_leg_arrival = []
    warned_ledger_late = []
    warned_arrival_late = []
    undelivered_count = 0
    total_won = 0
    total_late = 0

    for d in dirs:
        events = rd(d, "events")
        legs = rd(d, "legs")
        reqs = {r["id"]: r for r in rd(d, "requests")}
        roads = {(r["from"], r["to"]): int(r["minutes"]) for r in rd(d, "roads")}

        orders = {}
        warned = set()
        late_ledger = {}
        failed_visits = set()
        deliv_events = {}
        for e in events:
            if e["kind"] == "order_won":
                orders[e["order.id"]] = {
                    "deadline": int(e["order.deadline"]),
                    "lastPickupAt": int(e["order.lastPickupAt"]),
                    "option": e["order.option"],
                }
            elif e["kind"] == "deadline_close":
                warned.add(e["orderId"])
            elif e["kind"] == "visit_failed":
                failed_visits.add(e["orderId"])
            elif e["kind"] == "delivered":
                deliv_events.setdefault(e["orderId"], {})[int(e["leg"])] = int(e["at"])
            elif e["kind"] == "ledger" and e["line.kind"] in ("late_refund", "undelivered_penalty"):
                oid = e["line.orderId"]
                late_ledger[oid] = (e["line.kind"], int(e["line.cents"]), e["line.detail"])

        legs_by_order = {}
        for l in legs:
            legs_by_order.setdefault(l["requestId"], []).append(l)

        total_won += len(orders)
        total_late += len(late_ledger)
        print(f"=== {d.name}: won={len(orders)}, late={len(late_ledger)}, warned={len(warned)} ===")

        for oid in sorted(late_ledger):
            o = orders[oid]
            olegs = legs_by_order[oid]
            dl = o["deadline"]
            note_dls = [int(l["truth.noteDeadline"]) for l in olegs if l.get("truth.noteDeadline")]
            leg_dls = [min(dl, int(l["delivery.window.to"])) for l in olegs]
            eff_dl = min(leg_dls + note_dls)
            deliv_ats = [int(l["truth.deliveredAt"]) for l in olegs if l.get("truth.deliveredAt")]
            pickup_ats = [int(l["truth.pickedUpAt"]) for l in olegs if l.get("truth.pickedUpAt")]
            drive_min = sum(roads[(l["pickup.placeId"], l["delivery.placeId"])] for l in olegs)
            had_warn = oid in warned

            if len(deliv_ats) < len(olegs):
                undelivered_count += 1
                print(f"  {oid} ({o['option']:<13}) warn={str(had_warn):<5} UNDELIVERED (drive={drive_min}m) {late_ledger[oid][2]}")
                continue

            m = re.search(r"Late by (\d+) minutes", late_ledger[oid][2])
            ledger_min = int(m.group(1)) if m else max(deliv_ats) - eff_dl
            ev_deliv = max(deliv_events.get(oid, {}).values(), default=max(deliv_ats))
            arr_late_vs_dl = ev_deliv - dl
            arr_late_vs_eff = max(
                deliv_events.get(oid, {}).get(int(l["leg"]), int(l["truth.deliveredAt"]))
                - min([dl, int(l["delivery.window.to"])] + ([int(l["truth.noteDeadline"])] if l.get("truth.noteDeadline") else []))
                for l in olegs
            )

            if had_warn:
                warned_ledger_late.append(ledger_min)
                warned_arrival_late.append(arr_late_vs_eff)
            else:
                held_ledger_late.append(ledger_min)
                held_arrival_late.append(arr_late_vs_eff)
                if len(olegs) == 1 and not note_dls:
                    held_single_leg_arrival.append((arr_late_vs_dl, ledger_min, drive_min, oid, reqs[oid]["note"]))

            print(
                f"  {oid} ({o['option']:<13} legs={len(olegs)}) warn={str(had_warn):<5} "
                f"ledger_late={ledger_min:>4}m arr_vs_dl={arr_late_vs_dl:>5}m arr_vs_eff={arr_late_vs_eff:>5}m "
                f"pick={min(pickup_ats)} ev_deliv={ev_deliv} truth_deliv={max(deliv_ats)} dl={dl} eff_dl={eff_dl} drive={drive_min:>3}m "
                f"| {reqs[oid]['note'][:40]}"
            )

    print("")
    print(f"=== SUMMARY ACROSS {len(dirs)} WORLDS ===")
    print(f"Total won: {total_won}, Total late: {total_late} ({undelivered_count} undelivered)")
    for label, xs in [
        ("Held at warning (n=17): ledger lateness (truth.deliveredAt - eff_dl)", held_ledger_late),
        ("Held at warning (n=17): driver arrival lateness (delivered_event - eff_dl)", held_arrival_late),
        ("Unstaffed at warning (n=22): ledger lateness", warned_ledger_late),
        ("Unstaffed at warning (n=22): driver arrival lateness", warned_arrival_late),
    ]:
        if xs:
            xs_s = sorted(xs)
            print(f"  {label}:")
            print(
                f"    n={len(xs_s)}, min={xs_s[0]}m, med={st.median(xs_s):.1f}m, "
                f"mean={st.mean(xs_s):.1f}m, max={xs_s[-1]}m, "
                f"<=30m: {sum(1 for x in xs_s if 0 < x <= 30)}, "
                f"<=60m: {sum(1 for x in xs_s if 0 < x <= 60)}, "
                f"<=120m: {sum(1 for x in xs_s if 0 < x <= 120)}, "
                f"values={xs_s}"
            )
    print("  Held single-leg no-note-dl (arr_vs_dl, ledger_late, drive_min, oid, note):")
    for row in sorted(held_single_leg_arrival):
        print("   ", row)


if __name__ == "__main__":
    main()
