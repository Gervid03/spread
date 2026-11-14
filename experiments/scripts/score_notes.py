"""Score src/spread_lab/notes.py (v0 vs v2) field by field on revealed worlds."""
from __future__ import annotations

import csv
import sys
from collections import Counter
from pathlib import Path
from typing import Optional

from spread_lab.notes import DAY, HOUR, note_flags, parse_note_v2, window_from_note


def b(val: str) -> bool:
    return val.lower() == "true"


def i_or_none(val: str) -> Optional[int]:
    return int(val) if val != "" else None


def main() -> None:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("runs/reveals")
    reveals = sorted(root.glob("reveal-*"))
    won_legs = []
    all_reqs = []
    for d in reveals:
        reqs = {r["id"]: r for r in csv.DictReader(open(d / "requests.csv", encoding="utf-8"))}
        all_reqs.extend(reqs.values())
        for l in csv.DictReader(open(d / "legs.csv", encoding="utf-8")):
            r = reqs[l["requestId"]]
            if r["outcome"] == "won":
                won_legs.append((d.name, r, l))

    fields = [
        "readyAt", "releasedAt", "pickupHours.opens", "pickupHours.closes",
        "deliveryHours.opens", "deliveryHours.closes", "noteDeadline",
        "manualGearbox", "needsPlates", "summerTyres",
    ]
    v0_stats = {f: Counter() for f in fields}
    v2_stats = {f: Counter() for f in fields}
    v2_errors = []

    for wname, r, l in won_legs:
        note_obj = {"text": r["note"], "language": r["language"]} if r["note"] else None
        arr = int(r["arrivedAt"])
        p_from, p_to = int(l["pickup.window.from"]), int(l["pickup.window.to"])
        d_from = int(l["delivery.window.from"])
        opt_dl = int(r[r["option"] + ".deadline"])
        p_opens, p_closes = i_or_none(l["pickup.hours.opens"]), i_or_none(l["pickup.hours.closes"])
        d_opens, d_closes = i_or_none(l["delivery.hours.opens"]), i_or_none(l["delivery.hours.closes"])

        gt = {
            "readyAt": i_or_none(l["truth.readyAt"]) if i_or_none(l["truth.readyAt"]) != p_from else None,
            "releasedAt": i_or_none(l["truth.releasedAt"]),
            "pickupHours.opens": i_or_none(l["truth.pickupHours.opens"]) if l["truth.pickupHours.opens"] != l["pickup.hours.opens"] else None,
            "pickupHours.closes": i_or_none(l["truth.pickupHours.closes"]) if l["truth.pickupHours.closes"] != l["pickup.hours.closes"] else None,
            "deliveryHours.opens": i_or_none(l["truth.deliveryHours.opens"]) if l["truth.deliveryHours.opens"] != l["delivery.hours.opens"] else None,
            "deliveryHours.closes": i_or_none(l["truth.deliveryHours.closes"]) if l["truth.deliveryHours.closes"] != l["delivery.hours.closes"] else None,
            "noteDeadline": i_or_none(l["truth.noteDeadline"]),
            "manualGearbox": b(l["truth.manualGearbox"]) or None,
            "needsPlates": b(l["truth.needsPlates"]) or None,
            "summerTyres": b(l["truth.summerTyres"]) or None,
        }

        pn = parse_note_v2(note_obj, arr)
        is_priv_p = b(l["pickup.privateAddress"])
        is_priv_d = b(l["delivery.privateAddress"])
        v2_pred = {
            "readyAt": pn.ready_at if (not is_priv_p and pn.ready_at is not None and pn.ready_at != p_from) else None,
            "releasedAt": pn.released_at if (not is_priv_p and pn.released_at is not None) else None,
            "pickupHours.opens": pn.pickup_opens if (not is_priv_p and pn.pickup_opens is not None and pn.pickup_opens != p_opens) else None,
            "pickupHours.closes": pn.pickup_closes if (not is_priv_p and pn.pickup_closes is not None and pn.pickup_closes != p_closes) else None,
            "deliveryHours.opens": pn.delivery_opens if (not is_priv_d and pn.delivery_opens is not None and pn.delivery_opens != d_opens) else None,
            "deliveryHours.closes": pn.delivery_closes if (not is_priv_d and pn.delivery_closes is not None and pn.delivery_closes != d_closes) else None,
            "noteDeadline": pn.note_deadline if (not is_priv_d and pn.note_deadline is not None and pn.note_deadline % DAY < 20 * HOUR) else None,
            "manualGearbox": True if pn.manual else None,
            "needsPlates": True if pn.plates else None,
            "summerTyres": True if pn.summer_tyres else None,
        }

        f0 = note_flags(note_obj, v2=False)
        pw0 = window_from_note(note_obj, {"from": p_from, "to": p_to}, "pickup", v2=False)
        dw0 = window_from_note(note_obj, {"from": d_from, "to": opt_dl}, "delivery", v2=False)
        v0_pred = {
            "readyAt": pw0["from"] if pw0["from"] > p_from and gt["releasedAt"] is None else None,
            "releasedAt": pw0["from"] if pw0["from"] > p_from and gt["releasedAt"] is not None else None,
            "pickupHours.opens": pw0["from"] % DAY if pw0["from"] > p_from and gt["pickupHours.opens"] is not None else None,
            "pickupHours.closes": pw0["to"] % DAY if pw0["to"] < p_to else None,
            "deliveryHours.opens": dw0["from"] % DAY if dw0["from"] > d_from else None,
            "deliveryHours.closes": dw0["to"] % DAY if dw0["to"] < opt_dl and gt["noteDeadline"] is None else None,
            "noteDeadline": dw0["to"] if dw0["to"] < opt_dl and gt["deliveryHours.closes"] is None else None,
            "manualGearbox": True if f0.manual else None,
            "needsPlates": True if f0.plates else None,
            "summerTyres": True if f0.summer_tyres else None,
        }

        for f in fields:
            for stats, pred in ((v0_stats[f], v0_pred[f]), (v2_stats[f], v2_pred[f])):
                t_val = gt[f]
                if t_val is not None and pred == t_val:
                    stats["TP"] += 1
                elif t_val is not None and pred is None:
                    stats["FN"] += 1
                elif t_val is not None and pred != t_val:
                    stats["WRONG_VAL"] += 1
                elif t_val is None and pred is not None:
                    stats["FP"] += 1
                else:
                    stats["TN"] += 1
            if v2_pred[f] != gt[f]:
                v2_errors.append((wname[-4:], r["id"], l["leg"], f, gt[f], v2_pred[f], r["language"], r["note"]))

    print(f"Reveals: {len(reveals)} | Won legs: {len(won_legs)} (with notes: {sum(1 for _, r, _ in won_legs if r['note'])})")
    print(f"{'Field':<22} | {'GT+':>4} | {'v0 TP/WRONG/FN/FP':<22} | {'v2 TP/WRONG/FN/FP':<22}")
    print("-" * 80)
    for f in fields:
        s0, s2 = v0_stats[f], v2_stats[f]
        gt_pos = s2["TP"] + s2["FN"] + s2["WRONG_VAL"]
        print(
            f"{f:<22} | {gt_pos:>4} | "
            f"{s0['TP']:>3}/{s0['WRONG_VAL']:>2}/{s0['FN']:>2}/{s0['FP']:>3}         | "
            f"{s2['TP']:>3}/{s2['WRONG_VAL']:>2}/{s2['FN']:>2}/{s2['FP']:>3}"
        )

    print(f"v2 errors ({len(v2_errors)}):")
    for err in v2_errors:
        print(" ", err)

    notes_read = 0
    unsure_notes = []
    for r in all_reqs:
        if r["note"]:
            pn = parse_note_v2({"text": r["note"], "language": r["language"]}, int(r["arrivedAt"]))
            if pn.has_info:
                notes_read += 1
            if pn.unsure:
                unsure_notes.append((r["language"], r["note"]))
    total_notes = sum(1 for r in all_reqs if r["note"])
    print(f"Total notes: {total_notes} | Notes with constraints read: {notes_read} | Unsure: {len(unsure_notes)}")


if __name__ == "__main__":
    main()
