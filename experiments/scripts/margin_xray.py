"""Margin X-Ray: Decompose champion v2's week across the 16 dev worlds and quantify margin leaks.

Standard library only. Reads reveal CSVs from /tmp/reveals-n14-01 (or path passed as argv[1]).

Usage:
    python3 experiments/scripts/margin_xray.py [/tmp/reveals-n14-01]
"""
from __future__ import annotations

import collections
import csv
import json
import math
import re
import statistics as st
import sys
from pathlib import Path

csv.field_size_limit(10**9)

CAP = {"helsinki", "espoo", "vantaa"}
OPTS = ("same_day", "next_day", "within_3_days")
DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri")
HOUR, DAY = 60, 1440

AFTER = re.compile(r"jälkeen|alkaen|aikaisintaan|\bafter\b|\bfrom\b|earliest|not before|ei ennen|valmis|\bready\b|efter|tidigast|inte före|klar", re.ASCII)
BEFORE = re.compile(r"ennen|mennessä|viim|\bbefore\b|\bby\b|latest|före|senast", re.ASCII)
DELIVERY = re.compile(r"toimit|perillä|perille|vastaanot|kohde|deliver|arrive|destination|receiv|leverera|leverans|framme|mottag", re.ASCII)
CLOCK = re.compile(r"(?:klo|kl\.?)\s*(\d{1,2})(?:[.:](\d{2}))?|\b(\d{1,2})[.:](\d{2})\b", re.ASCII)
RANGE = re.compile(r"\b(\d{1,2})(?:[.:](\d{2}))?\s*[-–]\s*(\d{1,2})(?:[.:](\d{2}))?\b", re.ASCII)


def window_from_note(note: dict[str, str] | None, window: dict[str, int], stop: str) -> dict[str, int]:
    if not note:
        return window
    text = note["text"].lower()
    if bool(DELIVERY.search(text)) != (stop == "delivery"):
        return window

    def minutes(hour: int, minute: int) -> int | None:
        return None if hour > 24 or minute > 59 else hour * HOUR + minute

    start, end = window["from"], window["to"]
    for match in RANGE.finditer(text):
        opens, closes = minutes(int(match[1]), int(match[2] or 0)), minutes(int(match[3]), int(match[4] or 0))
        if opens is None or closes is None or opens >= closes:
            continue
        start = max(start, start // DAY * DAY + opens)
        end = min(end, end // DAY * DAY + closes)
    text = RANGE.sub(" ", text)
    for match in CLOCK.finditer(text):
        m = minutes(int(match[1] or match[3]), int(match[2] or match[4] or 0))
        if m is None:
            continue
        time = window["from"] // DAY * DAY + m
        around = text[max(0, match.start() - 16): match.end() + 16]
        if AFTER.search(around):
            start = max(start, time)
        elif BEFORE.search(around):
            end = min(end, time)
    return {"from": start, "to": end} if start <= end else window


def rd(d: Path, name: str) -> list[dict[str, str]]:
    with open(d / f"{name}.csv", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def hav(a: tuple[float, float], b: tuple[float, float]) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(h))


def supply_band(place: str, s30: int, s55: int) -> str:
    if place in CAP or s30 >= 100:
        return "1_dense>=100"
    if s30 >= 30:
        return "2_mid_30-99"
    if s55 >= 30:
        return "3_ring_s55>=30"
    return "4_thin_s55<30"


def drive_band(drive_min: int) -> str:
    if drive_min < 100:
        return "1_<100m"
    if drive_min <= 300:
        return "2_100-300m"
    return "3_>300m"


def dealer_group(dealer_id: str, rank: int) -> str:
    if dealer_id == "D01":
        return "1_D01"
    if rank <= 3 or dealer_id in ("D02", "D03"):
        return "2_Top2-3"
    return "3_Others"


def estimate_comp_pl(pairs: list[tuple[float, bool]], target_wr: float = 0.50) -> float | None:
    """Estimate the P/L at which win rate equals target_wr using binned linear interpolation or logistic fit."""
    if len(pairs) < 10:
        return None
    # Fit a simple 1D logistic regression: P(win) = 1 / (1 + exp(-(a + b * pl)))
    # If b < 0, threshold at target_wr is (logit(target_wr) - a) / b
    w_pls = [p for p, w in pairs if w]
    l_pls = [p for p, w in pairs if not w]
    if not w_pls or not l_pls:
        return None
    # Also compute midpoint between median won P/L and median lost P/L adjusted by win rate:
    # With competitor log-noise sigma ~ 0.15, E[log(comp)] ≈ mean(log(quote)) + sigma * Φ^-1(win_rate)
    wr = len(w_pls) / len(pairs)
    med_q = st.median(p for p, _ in pairs)
    # Approximate normal quantile via logistic quantile: sigma_eff * log(wr / (1 - wr))
    # Empirical slope from batch/fork data: 10% P/L shift changes win rate by ~25 percentage points -> sigma_eff ~ 0.12
    wr_clamped = max(0.03, min(0.97, wr))
    return med_q * math.exp(0.10 * math.log(wr_clamped / (1.0 - wr_clamped)) - 0.10 * math.log(target_wr / (1.0 - target_wr)))


def main() -> None:
    default_root = Path("/tmp/reveals-n14-01")
    reveal_root = Path(sys.argv[1]) if len(sys.argv) > 1 else default_root
    dirs = sorted(p for p in reveal_root.iterdir() if p.is_dir() and p.name.startswith("reveal-"))
    print(f"Loaded {len(dirs)} reveal directories from {reveal_root}")

    total_worlds = len(dirs)
    ledger_totals = collections.Counter()
    world_margins = []
    world_revs = []
    world_wons = []
    world_lates = []

    req_records = []
    opt_records = []

    for d in dirs:
        wid = d.name.removeprefix("reveal-")
        places = {p["id"]: (float(p["lat"]), float(p["lon"])) for p in rd(d, "places")}
        line = {(a, b): hav(places[a], places[b]) for a in places for b in places}
        roads = {(r["from"], r["to"]): (float(r["km"]), int(r["minutes"])) for r in rd(d, "roads")}
        drivers = {x["id"]: x for x in rd(d, "drivers")}
        homes = collections.Counter(x["homePlaceId"] for x in drivers.values())
        s30 = {p: sum(n for h, n in homes.items() if line[(p, h)] <= 30.0) for p in places}
        s55 = {p: sum(n for h, n in homes.items() if line[(p, h)] <= 55.0) for p in places}
        s70 = {p: sum(n for h, n in homes.items() if line[(p, h)] <= 70.0) for p in places}

        reqs = {r["id"]: r for r in rd(d, "requests")}
        dealer_counts = collections.Counter(r["dealerId"] for r in reqs.values())
        dealer_ranks = {dlr: idx + 1 for idx, (dlr, _) in enumerate(dealer_counts.most_common())}

        legs_raw = rd(d, "legs")
        legs_by_req = collections.defaultdict(list)
        for l in legs_raw:
            legs_by_req[l["requestId"]].append(l)
        for rid in legs_by_req:
            legs_by_req[rid].sort(key=lambda x: int(x["leg"]))

        gigs = {g["id"]: g for g in rd(d, "gigs")}
        events = rd(d, "events")

        gig_order = {}
        first_post = {}
        first_sched_fee = {}
        for gid, g in gigs.items():
            stops = json.loads(g["stops"])
            oid = stops[0]["orderId"]
            gig_order[gid] = oid
            pat = int(g["postedAt"])
            if oid not in first_post or pat < first_post[oid]:
                first_post[oid] = pat
                sched = json.loads(g["schedule"])
                first_sched_fee[oid] = int(sched[0]["feeCents"]) if sched else 0

        order_ledger = collections.defaultdict(lambda: collections.Counter())
        order_late_mins = {}
        w_ledger = collections.Counter()
        for e in events:
            if e["kind"] == "ledger":
                cents = int(e["line.cents"])
                lkind = e["line.kind"]
                w_ledger[lkind] += cents
                ledger_totals[lkind] += cents
                oid = e["line.orderId"]
                if oid:
                    order_ledger[oid][lkind] += cents
                    if lkind == "late_refund" and e.get("line.detail"):
                        m_lt = re.search(r"Late by (\d+) minutes", e["line.detail"])
                        if m_lt:
                            order_late_mins[oid] = int(m_lt.group(1))

        w_margin = sum(w_ledger.values()) / 100.0
        world_margins.append(w_margin)
        world_revs.append(w_ledger["revenue"] / 100.0)

        bookings_by_order = collections.defaultdict(list)
        drops_by_order = collections.Counter()
        warned_orders = set()
        failed_visits_by_order = collections.defaultdict(list)
        for e in events:
            kind = e["kind"]
            if kind == "gig_booked":
                oid = gig_order[e["gigId"]]
                bookings_by_order[oid].append((int(e["at"]), int(e["feeCents"]), e["driverId"], e["gigId"]))
            elif kind == "gig_dropped":
                oid = gig_order[e["gigId"]]
                drops_by_order[oid] += 1
            elif kind == "deadline_close":
                warned_orders.add(e["orderId"])
            elif kind == "visit_failed":
                failed_visits_by_order[e["orderId"]].append(e["reason"])

        late_orders = {
            oid for oid, lc in order_ledger.items() if lc["late_refund"] < 0 or lc["undelivered_penalty"] < 0
        }
        won_orders = [r["id"] for r in reqs.values() if r["outcome"] == "won"]
        world_wons.append(len(won_orders))
        world_lates.append(len(late_orders))

        trust_changes = []
        for oid in won_orders:
            r_o = reqs[oid]
            dlr = r_o["dealerId"]
            ls = legs_by_req[oid]
            dels = [int(l["truth.deliveredAt"]) for l in ls if l.get("truth.deliveredAt")]
            if len(dels) == len(ls):
                del_at = max(dels)
                is_lt = oid in late_orders
                trust_changes.append((del_at, dlr, not is_lt))
        trust_changes.sort()

        for rid, r in sorted(reqs.items(), key=lambda kv: int(kv[1]["arrivedAt"])):
            r_legs = legs_by_req[rid]
            p0 = r_legs[0]["pickup.placeId"]
            d0 = r_legs[0]["delivery.placeId"]
            drive_min = sum(roads[(l["pickup.placeId"], l["delivery.placeId"])][1] for l in r_legs)
            drive_km = sum(roads[(l["pickup.placeId"], l["delivery.placeId"])][0] for l in r_legs)
            if len(r_legs) == 2:
                drive_min += roads[(r_legs[0]["delivery.placeId"], r_legs[1]["pickup.placeId"])][1]
                drive_km += roads[(r_legs[0]["delivery.placeId"], r_legs[1]["pickup.placeId"])][0]

            s_30 = s30[p0]
            s_55 = s55[p0]
            s_70 = s70[p0]
            d_s30 = s30[d0]
            d_s55 = s55[d0]
            sband = supply_band(p0, s_30, s_55)
            dband = drive_band(drive_min)
            typ_fee = int(r["referenceFeeCents"])
            arr = int(r["arrivedAt"])
            dlr = r["dealerId"]
            dgrp = dealer_group(dlr, dealer_ranks[dlr])

            t_cnt = 0
            for t_at, t_dlr, t_ok in trust_changes:
                if t_at > arr:
                    break
                if t_dlr == dlr:
                    if t_ok:
                        t_cnt = min(25, t_cnt + 1)
                    else:
                        t_cnt = t_cnt // 2

            offered_opts = [k for k in OPTS if r[f"{k}.deadline"]]
            quoted_opts = {}
            for k in offered_opts:
                qc_str = r[f"{k}.quoteCents"]
                if qc_str:
                    qc = int(qc_str)
                    lc = int(r[f"{k}.listPriceCents"])
                    if qc / lc <= 3.5:
                        quoted_opts[k] = (qc, lc, int(r[f"{k}.deadline"]))

            is_quoted = len(quoted_opts) > 0
            outcome = r["outcome"]
            won_opt = r["option"] if outcome == "won" else ""

            note_obj = {"text": r["note"], "language": r["language"]} if r["note"] else None
            ready = max(
                [arr]
                + [
                    window_from_note(
                        note_obj,
                        {"from": int(l["pickup.window.from"]), "to": int(l["pickup.window.to"])},
                        "pickup",
                    )["from"]
                    for l in r_legs
                ]
            )
            surviving_opts = []
            opt_drop_reasons = {}
            for k in offered_opts:
                dl = int(r[f"{k}.deadline"])
                if s_30 < 30 and k == "same_day":
                    opt_drop_reasons[k] = "ring_same_day"
                    continue
                if drive_min > 300 and dl // DAY <= ready // DAY:
                    opt_drop_reasons[k] = "long_drive_same_day"
                    continue
                if k == "same_day" and s_30 < 100:
                    opt_drop_reasons[k] = "same_day_supply<100"
                    continue
                if dl - ready - drive_min < 180 + 0.5 * drive_min:
                    opt_drop_reasons[k] = "slack"
                    continue
                surviving_opts.append(k)

            if not is_quoted:
                if s_55 < 30:
                    decline_reason = "supply_gate_s55<30"
                elif not surviving_opts:
                    decline_reason = "option_slack_or_speed_gate"
                else:
                    decline_reason = "backlog_gate"
            else:
                decline_reason = "none"

            ol = order_ledger[rid]
            rev_cents = ol["revenue"]
            fee_cents = -ol["driver_fee"]
            late_ref_cents = -ol["late_refund"]
            undeliv_cents = -ol["undelivered_penalty"]
            fail_vis_cents = -ol["failed_visit"]
            rel_cents = -ol["release_fee"]
            wait_cents = -ol["waiting"]
            fine_cents = -ol["fine"]
            net_margin_cents = sum(ol.values())

            bks = bookings_by_order[rid]
            first_book_fee = bks[0][1] if bks else 0
            last_book_fee = bks[-1][1] if bks else 0
            first_book_delay = (bks[0][0] - first_post[rid]) if (bks and rid in first_post) else None
            last_book_delay = (bks[-1][0] - first_post[rid]) if (bks and rid in first_post) else None
            post_at = first_post.get(rid)
            book_at = bks[-1][0] if bks else None

            floor_val = int(typ_fee * 1.25 / (1 - 0.08) + 0.5)
            floored = False
            floored_opts = set()
            if is_quoted:
                for k_q, (qc_q, _, _) in quoted_opts.items():
                    if abs(qc_q - floor_val) <= 2:
                        floored = True
                        floored_opts.add(k_q)

            # Ex-ante option assignment (NEVER peeks at outcome):
            # If quoted: fastest quoted option (same_day > next_day > within_3_days), because when same_day is quoted alongside next_day,
            # same_day wins 75% of the time.
            # If declined: slowest offered option (next_day > within_3_days > same_day), representing the safest option the request had.
            if is_quoted:
                for pref in ("same_day", "next_day", "within_3_days"):
                    if pref in quoted_opts:
                        ex_ante_opt = pref
                        break
            else:
                for pref in ("next_day", "within_3_days", "same_day"):
                    if pref in offered_opts:
                        ex_ante_opt = pref
                        break

            ex_ante_lc = int(r[f"{ex_ante_opt}.listPriceCents"])
            ex_ante_qc = quoted_opts[ex_ante_opt][0] if ex_ante_opt in quoted_opts else None
            ex_ante_flr = ex_ante_opt in floored_opts

            # Calculate lateness across all legs
            won_dl = int(r[f"{won_opt}.deadline"]) if (outcome == "won" and won_opt) else None
            mins_late_list = []
            if won_dl is not None:
                for lg in r_legs:
                    dat = int(lg["truth.deliveredAt"]) if lg.get("truth.deliveredAt") else None
                    ndl = int(lg["truth.noteDeadline"]) if lg.get("truth.noteDeadline") else None
                    edl = min(won_dl, ndl) if ndl else won_dl
                    if dat is not None:
                        mins_late_list.append(dat - edl)
            mins_late = order_late_mins.get(rid, max(mins_late_list) if mins_late_list else None)
            has_narrow_win = any(
                int(lg["delivery.window.to"]) < int(r[f"{k}.deadline"]) or int(lg["pickup.window.to"]) < int(r[f"{k}.deadline"])
                for lg in r_legs for k in offered_opts
            )

            rec = {
                "world": wid,
                "id": rid,
                "dealer": dlr,
                "dgrp": dgrp,
                "trust": t_cnt,
                "batch": r["batchId"],
                "arr": arr,
                "day": min(4, arr // DAY),
                "pickup": p0,
                "delivery": d0,
                "s30": s_30,
                "s55": s_55,
                "s70": s_70,
                "d_s30": d_s30,
                "d_s55": d_s55,
                "sband": sband,
                "dband": dband,
                "drive_min": drive_min,
                "drive_km": drive_km,
                "typ_fee": typ_fee,
                "offered_opts": tuple(offered_opts),
                "surviving_opts": tuple(surviving_opts),
                "opt_drop_reasons": opt_drop_reasons,
                "quoted_opts": quoted_opts,
                "is_quoted": is_quoted,
                "floored": floored,
                "floored_opts": floored_opts,
                "floor_val": floor_val,
                "decline_reason": decline_reason,
                "outcome": outcome,
                "won_opt": won_opt,
                "ex_ante_opt": ex_ante_opt,
                "ex_ante_lc": ex_ante_lc,
                "ex_ante_qc": ex_ante_qc,
                "ex_ante_flr": ex_ante_flr,
                "rev_cents": rev_cents,
                "fee_cents": fee_cents,
                "late_ref_cents": late_ref_cents,
                "undeliv_cents": undeliv_cents,
                "fail_vis_cents": fail_vis_cents,
                "rel_cents": rel_cents,
                "wait_cents": wait_cents,
                "fine_cents": fine_cents,
                "net_margin_cents": net_margin_cents,
                "is_late": rid in late_orders,
                "is_warned": rid in warned_orders,
                "n_drops": drops_by_order[rid],
                "n_fails": len(failed_visits_by_order[rid]),
                "fail_reasons": failed_visits_by_order[rid],
                "post_at": post_at,
                "book_at": book_at,
                "first_book_delay": first_book_delay,
                "last_book_delay": last_book_delay,
                "first_book_fee": first_book_fee,
                "last_book_fee": last_book_fee,
                "mins_late": mins_late,
                "has_narrow_win": has_narrow_win,
                "n_legs": len(r_legs),
                "note": r["note"],
                "truth_leg0": r_legs[0],
                "r_legs": r_legs,
                "r_raw": r,
            }
            req_records.append(rec)

            for k in offered_opts:
                dl = int(r[f"{k}.deadline"])
                lc = int(r[f"{k}.listPriceCents"])
                q_tuple = quoted_opts.get(k)
                q_cents = q_tuple[0] if q_tuple else None
                opt_records.append(
                    {
                        "world": wid,
                        "id": rid,
                        "dealer": dlr,
                        "dgrp": dgrp,
                        "trust": t_cnt,
                        "day": min(4, arr // DAY),
                        "sband": sband,
                        "opt": k,
                        "dband": dband,
                        "s30": s_30,
                        "s55": s55[p0],
                        "d_s30": d_s30,
                        "drive_min": drive_min,
                        "typ_fee": typ_fee,
                        "list_cents": lc,
                        "quote_cents": q_cents,
                        "is_quoted": q_cents is not None,
                        "is_floored": k in floored_opts,
                        "drop_reason": opt_drop_reasons.get(k, "supply_or_backlog" if not is_quoted else "none"),
                        "req_quoted": is_quoted,
                        "req_won": outcome == "won",
                        "outcome": "won"
                        if (outcome == "won" and won_opt == k)
                        else ("won_other" if outcome == "won" else "lost"),
                        "req": rec,
                    }
                )

    quoted_reqs = [r for r in req_records if r["is_quoted"]]
    won_reqs = [r for r in req_records if r["outcome"] == "won"]
    lost_reqs = [r for r in quoted_reqs if r["outcome"] == "lost"]
    dec_reqs = [r for r in req_records if not r["is_quoted"]]

    print()
    print("=== 0. OVERALL CHAMPION V2 SUMMARY ACROSS 16 DEV WORLDS ===")
    print(f"  Total requests: {len(req_records)} ({len(req_records)/total_worlds:.1f}/wk)")
    print(
        f"  Quoted: {len(quoted_reqs)} ({len(quoted_reqs)/total_worlds:.1f}/wk, {len(quoted_reqs)/len(req_records):.1%}) "
        f"[Normal: {sum(1 for r in quoted_reqs if not r['floored'])} ({sum(1 for r in quoted_reqs if not r['floored'])/total_worlds:.1f}/wk), "
        f"Any-Floored: {sum(1 for r in quoted_reqs if r['floored'])} ({sum(1 for r in quoted_reqs if r['floored'])/total_worlds:.1f}/wk), "
        f"Primary-Floored: {sum(1 for r in quoted_reqs if r['ex_ante_flr'])} ({sum(1 for r in quoted_reqs if r['ex_ante_flr'])/total_worlds:.1f}/wk)]"
    )
    print(
        f"  Declined: {len(dec_reqs)} ({len(dec_reqs)/total_worlds:.1f}/wk, {len(dec_reqs)/len(req_records):.1%}) "
        f"by reason: {dict(collections.Counter(r['decline_reason'] for r in dec_reqs))}"
    )
    print(
        f"  Won: {len(won_reqs)} ({len(won_reqs)/total_worlds:.1f}/wk, {len(won_reqs)/len(quoted_reqs):.1%} of quoted, "
        f"{len(won_reqs)/len(req_records):.1%} of all)"
    )
    print(f"  Ledger breakdown (€/wk mean across 16 worlds):")
    for k, v in sorted(ledger_totals.items(), key=lambda kv: -abs(kv[1])):
        print(f"    {k:22s}: €{v / 100.0 / total_worlds:9.2f}/wk")
    print(f"    {'NET MARGIN':22s}: €{sum(ledger_totals.values()) / 100.0 / total_worlds:9.2f}/wk")

    print()
    print("=== 1A. EX-ANTE REQUEST-LEVEL DECOMPOSITION (ALL 16,554 REQUESTS): PICKUP_CLASS x EX_ANTE_OPTION x DRIVE_BAND ===")
    header_req = (
        f"{'Pickup Class':15s} {'ExAnteOpt':13s} {'Drive':10s} | {'Req/w':>5s} {'Quot%':>5s} {'Flr%':>4s} {'Decl%':>5s} "
        f"{'Won/w':>5s} {'Lost/w':>6s} {'Win/Q':>5s} | {'P/L Won':>7s} {'P/L Lst':>7s} | "
        f"{'Fee/Typ':>7s} {'MinBk':>5s} | {'Late/w':>6s} {'Lt%':>5s} {'Lt€':>4s} {'Fl€':>4s} | {'Mrg/O':>6s} {'Mrg/Wk':>6s}"
    )
    print(header_req)
    print("-" * len(header_req))

    rgroups = collections.defaultdict(list)
    for r in req_records:
        rgroups[(r["sband"], r["ex_ante_opt"], r["dband"])].append(r)

    for (sb, opt, db), rs_ in sorted(rgroups.items()):
        req_w = len(rs_) / total_worlds
        q_rs = [r for r in rs_ if r["is_quoted"]]
        w_rs = [r for r in rs_ if r["outcome"] == "won"]
        l_rs = [r for r in q_rs if r["outcome"] == "lost"]
        quot_pct = len(q_rs) / len(rs_) if rs_ else 0
        flr_pct = sum(1 for r in q_rs if r["ex_ante_flr"]) / len(q_rs) if q_rs else 0
        decl_pct = 1.0 - quot_pct
        won_w = len(w_rs) / total_worlds
        lost_w = len(l_rs) / total_worlds
        win_q = len(w_rs) / len(q_rs) if q_rs else 0

        pl_won = [r["quoted_opts"][r["won_opt"]][0] / r["quoted_opts"][r["won_opt"]][1] for r in w_rs]
        pl_lost = [r["ex_ante_qc"] / r["ex_ante_lc"] for r in l_rs if r["ex_ante_qc"]]
        ft_won = [r["fee_cents"] / r["typ_fee"] for r in w_rs if r["fee_cents"] > 0]
        mb_won = [r["last_book_delay"] for r in w_rs if r["last_book_delay"] is not None]
        late_w = sum(1 for r in w_rs if r["is_late"]) / total_worlds
        late_pct = sum(1 for r in w_rs if r["is_late"]) / len(w_rs) if w_rs else 0
        late_eur = sum(r["late_ref_cents"] + r["undeliv_cents"] for r in w_rs) / 100.0 / total_worlds
        fail_eur = sum(r["fail_vis_cents"] for r in w_rs) / 100.0 / total_worlds
        mrg_ord = (sum(r["net_margin_cents"] for r in w_rs) / 100.0 / len(w_rs)) if w_rs else 0
        mrg_wk = sum(r["net_margin_cents"] for r in w_rs) / 100.0 / total_worlds

        pl_w_str = f"{st.median(pl_won):7.2f}" if pl_won else "      -"
        pl_l_str = f"{st.median(pl_lost):7.2f}" if pl_lost else "      -"
        ft_str = f"{st.median(ft_won):7.2f}" if ft_won else "      -"
        mb_str = f"{st.median(mb_won):5.0f}" if mb_won else "    -"
        lp_str = f"{late_pct:5.1%}" if w_rs else "    -"
        mo_str = f"{mrg_ord:6.1f}" if w_rs else "     -"

        print(
            f"{sb:15s} {opt:13s} {db:10s} | {req_w:5.1f} {quot_pct:5.0%} {flr_pct:4.0%} {decl_pct:5.0%} "
            f"{won_w:5.1f} {lost_w:6.1f} {win_q:5.0%} | {pl_w_str} {pl_l_str} | "
            f"{ft_str} {mb_str} | {late_w:6.2f} {lp_str} {late_eur:4.0f} {fail_eur:4.0f} | {mo_str} {mrg_wk:6.0f}"
        )

    print()
    print("=== 1B. OPTION-LEVEL DECOMPOSITION (ALL OFFERED OPTIONS): PICKUP_CLASS x OPTION x DRIVE_BAND ===")
    header_opt = (
        f"{'Pickup Class':15s} {'Option':13s} {'Drive':10s} | {'Off/w':>5s} {'Quot%':>5s} {'Flr%':>4s} {'Decl%':>5s} "
        f"{'Won/w':>5s} {'WOth':>4s} {'Lost/w':>6s} {'Win/Q':>5s} | {'P/L Won':>7s} {'P/L Lst':>7s} | "
        f"{'Fee/Typ':>7s} {'MinBk':>5s} {'Late%':>5s} {'Lt€':>4s} {'Fl€':>4s} | {'Mrg/O':>6s} {'Mrg/Wk':>6s}"
    )
    print(header_opt)
    print("-" * len(header_opt))

    ogroups = collections.defaultdict(list)
    for o in opt_records:
        ogroups[(o["sband"], o["opt"], o["dband"])].append(o)

    for (sb, opt, db), os_ in sorted(ogroups.items()):
        off_w = len(os_) / total_worlds
        q_os = [o for o in os_ if o["is_quoted"]]
        w_os = [o for o in os_ if o["outcome"] == "won"]
        wo_os = [o for o in q_os if o["outcome"] == "won_other"]
        l_os = [o for o in q_os if o["outcome"] == "lost"]
        quot_pct = len(q_os) / len(os_) if os_ else 0
        flr_pct = sum(1 for o in q_os if o["is_floored"]) / len(q_os) if q_os else 0
        decl_pct = 1.0 - quot_pct
        won_w = len(w_os) / total_worlds
        woth_w = len(wo_os) / total_worlds
        lost_w = len(l_os) / total_worlds
        win_q = len(w_os) / len(q_os) if q_os else 0

        pl_won = [o["quote_cents"] / o["list_cents"] for o in w_os if o["quote_cents"]]
        pl_lost = [o["quote_cents"] / o["list_cents"] for o in l_os if o["quote_cents"]]
        w_reqs = [o["req"] for o in w_os]
        ft_won = [r["fee_cents"] / r["typ_fee"] for r in w_reqs if r["fee_cents"] > 0]
        mb_won = [r["last_book_delay"] for r in w_reqs if r["last_book_delay"] is not None]
        late_pct = sum(1 for r in w_reqs if r["is_late"]) / len(w_reqs) if w_reqs else 0
        late_eur = sum(r["late_ref_cents"] + r["undeliv_cents"] for r in w_reqs) / 100.0 / total_worlds
        fail_eur = sum(r["fail_vis_cents"] for r in w_reqs) / 100.0 / total_worlds
        mrg_ord = (sum(r["net_margin_cents"] for r in w_reqs) / 100.0 / len(w_reqs)) if w_reqs else 0
        mrg_wk = sum(r["net_margin_cents"] for r in w_reqs) / 100.0 / total_worlds

        pl_w_str = f"{st.median(pl_won):7.2f}" if pl_won else "      -"
        pl_l_str = f"{st.median(pl_lost):7.2f}" if pl_lost else "      -"
        ft_str = f"{st.median(ft_won):7.2f}" if ft_won else "      -"
        mb_str = f"{st.median(mb_won):5.0f}" if mb_won else "    -"
        l_str = f"{late_pct:5.1%}" if w_reqs else "    -"
        mo_str = f"{mrg_ord:6.1f}" if w_reqs else "     -"

        print(
            f"{sb:15s} {opt:13s} {db:10s} | {off_w:5.1f} {quot_pct:5.0%} {flr_pct:4.0%} {decl_pct:5.0%} "
            f"{won_w:5.1f} {woth_w:4.1f} {lost_w:6.1f} {win_q:5.0%} | {pl_w_str} {pl_l_str} | "
            f"{ft_str} {mb_str} {l_str} {late_eur:4.0f} {fail_eur:4.0f} | {mo_str} {mrg_wk:6.0f}"
        )

    print()
    print("=== 2A. COMPETITOR BRACKETING: DEALER GROUP x WEEKDAY ===")
    print(
        f"{'Dealer Grp':11s} {'Day':4s} | {'Quot/w':>6s} {'Norm/w':>6s} {'Flr%':>4s} | "
        f"{'WinAll':>6s} {'WinNrm':>6s} {'WinFlr':>6s} | {'MedTrust':>8s} | "
        f"{'P/L Won':>7s} {'P/L Lst':>7s} {'EstCmp50':>8s}"
    )
    print("-" * 102)
    for dgrp in ("1_D01", "2_Top2-3", "3_Others"):
        for day in range(5):
            sub = [r for r in quoted_reqs if r["dgrp"] == dgrp and r["day"] == day]
            if not sub:
                continue
            nrm = [r for r in sub if not r["ex_ante_flr"]]
            flr = [r for r in sub if r["ex_ante_flr"]]
            w_all = [r for r in sub if r["outcome"] == "won"]
            l_all = [r for r in sub if r["outcome"] == "lost"]
            w_nrm = [r for r in nrm if r["outcome"] == "won"]
            w_flr = [r for r in flr if r["outcome"] == "won"]

            pl_w = [r["quoted_opts"][r["won_opt"]][0] / r["quoted_opts"][r["won_opt"]][1] for r in w_all]
            pl_l = [r["ex_ante_qc"] / r["ex_ante_lc"] for r in l_all]
            pairs = [
                ((r["quoted_opts"][r["won_opt"]][0] / r["quoted_opts"][r["won_opt"]][1]) if r["outcome"] == "won" else (r["ex_ante_qc"] / r["ex_ante_lc"]), r["outcome"] == "won")
                for r in sub
            ]
            est50 = estimate_comp_pl(pairs, 0.50)
            med_tr = st.median(r["trust"] for r in sub)

            win_flr_str = f"{len(w_flr)/len(flr):6.1%}" if flr else "     -"
            est_str = f"{est50:8.2f}" if est50 else "       -"
            print(
                f"{dgrp:11s} {DAYS[day]:4s} | {len(sub)/total_worlds:6.1f} {len(nrm)/total_worlds:6.1f} {len(flr)/len(sub):4.0%} | "
                f"{len(w_all)/len(sub):6.1%} {len(w_nrm)/len(nrm) if nrm else 0:6.1%} {win_flr_str} | {med_tr:8.1f} | "
                f"{st.median(pl_w) if pl_w else 0:7.2f} {st.median(pl_l) if pl_l else 0:7.2f} {est_str}"
            )

    print()
    print("=== 2B. COMPETITOR BRACKETING: DEALER GROUP x OPTION x DRIVE LENGTH (OPTION-LEVEL & REQ-LEVEL WIN%) ===")
    print(
        f"{'Dealer Grp':11s} {'Option':13s} {'Drive':10s} | {'Quot/w':>6s} {'Flr%':>4s} | "
        f"{'OptWin':>6s} {'WOth%':>5s} {'ReqWin':>6s} {'NrmOptW':>7s} {'NrmReqW':>7s} | {'P/L Won':>7s} {'P/L Lst':>7s} {'Typ/Lst':>7s}"
    )
    print("-" * 118)
    q_opts = [o for o in opt_records if o["is_quoted"]]
    for dgrp in ("1_D01", "2_Top2-3", "3_Others"):
        for opt in OPTS:
            for db in ("1_<100m", "2_100-300m", "3_>300m"):
                sub = [o for o in q_opts if o["dgrp"] == dgrp and o["opt"] == opt and o["dband"] == db]
                if len(sub) < 8:
                    continue
                nrm = [o for o in sub if not o["is_floored"]]
                w_opt = [o for o in sub if o["outcome"] == "won"]
                w_oth = [o for o in sub if o["outcome"] == "won_other"]
                l_all = [o for o in sub if o["outcome"] == "lost"]
                nrm_w_opt = [o for o in nrm if o["outcome"] == "won"]
                nrm_w_req = [o for o in nrm if o["req_won"]]
                pl_w = [o["quote_cents"] / o["list_cents"] for o in w_opt]
                pl_l = [o["quote_cents"] / o["list_cents"] for o in l_all]
                tl = [o["typ_fee"] / o["list_cents"] for o in sub]
                print(
                    f"{dgrp:11s} {opt:13s} {db:10s} | {len(sub)/total_worlds:6.1f} {1-len(nrm)/len(sub):4.0%} | "
                    f"{len(w_opt)/len(sub):6.1%} {len(w_oth)/len(sub):5.1%} {(len(w_opt)+len(w_oth))/len(sub):6.1%} "
                    f"{len(nrm_w_opt)/len(nrm) if nrm else 0:7.1%} {len(nrm_w_req)/len(nrm) if nrm else 0:7.1%} | "
                    f"{st.median(pl_w) if pl_w else 0:7.2f} {st.median(pl_l) if pl_l else 0:7.2f} {st.median(tl):7.2f}"
                )

    print()
    print("=== 2C. REQUEST-LEVEL 4D SLICES (DEALER x WEEKDAY x EX_ANTE_OPT x DRIVE): WIN >50% OR NORMAL WIN <25% ===")
    req_gt50 = []
    req_lt25 = []
    for dgrp in ("1_D01", "2_Top2-3", "3_Others"):
        for day in range(5):
            for opt in OPTS:
                for db in ("1_<100m", "2_100-300m", "3_>300m"):
                    sub = [r for r in quoted_reqs if r["dgrp"] == dgrp and r["day"] == day and r["ex_ante_opt"] == opt and r["dband"] == db]
                    nrm = [r for r in sub if not r["ex_ante_flr"]]
                    if len(sub) >= 12:
                        wr_all = sum(1 for r in sub if r["outcome"] == "won") / len(sub)
                        pl_w = [r["quoted_opts"][r["won_opt"]][0] / r["quoted_opts"][r["won_opt"]][1] for r in sub if r["outcome"] == "won"]
                        pl_l = [r["ex_ante_qc"] / r["ex_ante_lc"] for r in sub if r["outcome"] == "lost"]
                        if wr_all >= 0.48:
                            req_gt50.append((wr_all, len(sub) / total_worlds, dgrp, DAYS[day], opt, db, st.median(pl_w) if pl_w else 0, st.median(pl_l) if pl_l else 0))
                    if len(nrm) >= 12:
                        wr_nrm = sum(1 for r in nrm if r["outcome"] == "won") / len(nrm)
                        pl_nw = [r["quoted_opts"][r["won_opt"]][0] / r["quoted_opts"][r["won_opt"]][1] for r in nrm if r["outcome"] == "won"]
                        pl_nl = [r["ex_ante_qc"] / r["ex_ante_lc"] for r in nrm if r["outcome"] == "lost"]
                        if wr_nrm < 0.25:
                            req_lt25.append((wr_nrm, len(nrm) / total_worlds, dgrp, DAYS[day], opt, db, st.median(pl_nw) if pl_nw else 0, st.median(pl_nl) if pl_nl else 0))

    print("  Request-level 4D slices winning >=48% of quotes (min 0.75 req/wk):")
    for wr, q_wk, dgrp, day_s, opt, db, plw, pll in sorted(req_gt50, reverse=True):
        print(f"    {dgrp:10s} {day_s:3s} {opt:13s} {db:10s}: win={wr:5.1%} ({q_wk:4.1f} req/wk) | med P/L won={plw:.2f}, lost={pll:.2f}")

    print("  Request-level 4D slices winning <25% of normal quotes (min 0.75 nrm req/wk):")
    for wr, q_wk, dgrp, day_s, opt, db, plw, pll in sorted(req_lt25):
        print(f"    {dgrp:10s} {day_s:3s} {opt:13s} {db:10s}: win_nrm={wr:5.1%} ({q_wk:4.1f} nrm_req/wk) | med P/L won={plw:.2f}, lost={pll:.2f}")

    # Also check where we win >50% by regime (e.g. morning after price war, Monday morning on high-level worlds, high trust D01, etc.)
    print("  High-win (>50%) regimes across worlds/days:")
    # Identify price war days per world (lowest win-rate day if wr < 18%)
    war_day_by_world = {}
    for wid in sorted({r["world"] for r in quoted_reqs}):
        day_wrs = []
        for day in range(5):
            sub = [r for r in quoted_reqs if r["world"] == wid and r["day"] == day]
            wr = sum(1 for r in sub if r["outcome"] == "won") / len(sub) if sub else 1.0
            day_wrs.append((wr, day))
        min_wr, min_day = min(day_wrs)
        if min_wr < 0.20:
            war_day_by_world[wid] = min_day

    after_war_morn = [
        r for r in quoted_reqs
        if r["world"] in war_day_by_world and r["day"] == war_day_by_world[r["world"]] + 1 and (r["arr"] % DAY) < 11 * 60
    ]
    if after_war_morn:
        w_awm = [r for r in after_war_morn if r["outcome"] == "won"]
        print(
            f"    Morning (08-11) after price-war day (n_worlds={len( {r['world'] for r in after_war_morn} )}): "
            f"won {len(w_awm)}/{len(after_war_morn)} ({len(w_awm)/len(after_war_morn):.1%}) at med P/L={st.median(r['ex_ante_qc']/r['ex_ante_lc'] for r in after_war_morn):.2f}"
        )

    # Check world-days with morning (08-11) win rate > 50%
    high_morns = []
    for wid in sorted({r["world"] for r in quoted_reqs}):
        for day in range(5):
            sub = [r for r in quoted_reqs if r["world"] == wid and r["day"] == day and (r["arr"] % DAY) < 11 * 60]
            if len(sub) >= 10:
                wr = sum(1 for r in sub if r["outcome"] == "won") / len(sub)
                if wr > 0.50:
                    high_morns.append((wid, day, len(sub), sum(1 for r in sub if r["outcome"] == "won"), wr, st.median(r["ex_ante_qc"]/r["ex_ante_lc"] for r in sub)))
    print(f"    World-mornings (08:00-11:00) with >50% win rate: {len(high_morns)} across 80 world-mornings:")
    for wid, day, nq, nw, wr, mpl in high_morns[:12]:
        print(f"      {wid} {DAYS[day]} 08-11: won {nw}/{nq} ({wr:.1%}) at med P/L={mpl:.2f}")
    if high_morns:
        tot_hm_q = sum(x[2] for x in high_morns)
        tot_hm_w = sum(x[3] for x in high_morns)
        print(f"      Total across all {len(high_morns)} >50% mornings: won {tot_hm_w}/{tot_hm_q} ({tot_hm_w/tot_hm_q:.1%}, {tot_hm_w/total_worlds:.1f} wins/wk)")

    # Check D01 when trust >= 10 but dealer_adj hasn't caught up
    for tr_label, lo, hi in [("D01 trust 0-4", 0, 5), ("D01 trust 5-14", 5, 15), ("D01 trust 15-24", 15, 25), ("D01 trust 25 (max)", 25, 26)]:
        sub = [r for r in quoted_reqs if r["dealer"] == "D01" and lo <= r["trust"] < hi]
        if not sub:
            continue
        nrm = [r for r in sub if not r["ex_ante_flr"]]
        w_sub = [r for r in sub if r["outcome"] == "won"]
        w_nrm = [r for r in nrm if r["outcome"] == "won"]
        pls = [r["ex_ante_qc"] / r["ex_ante_lc"] for r in sub]
        print(
            f"    {tr_label:20s}: quot={len(sub)/total_worlds:5.1f}/wk, won={len(w_sub)/total_worlds:5.1f}/wk "
            f"(all={len(w_sub)/len(sub):4.1%}, nrm={len(w_nrm)/len(nrm) if nrm else 0:4.1%}) | med P/L={st.median(pls):.2f}"
        )

    print()
    print("=== 2D. MULTI-OPTION QUOTES: WHICH OPTION WINS AND AT WHAT PRICE/LIST? ===")
    multi_combos = collections.defaultdict(list)
    for r in quoted_reqs:
        q_keys = tuple(k for k in OPTS if k in r["quoted_opts"])
        multi_combos[q_keys].append(r)

    for q_keys, rs_ in sorted(multi_combos.items(), key=lambda kv: -len(kv[1])):
        q_wk = len(rs_) / total_worlds
        w_rs = [r for r in rs_ if r["outcome"] == "won"]
        win_by_opt = collections.Counter(r["won_opt"] for r in w_rs)
        win_str = ", ".join(
            f"{k}: {win_by_opt[k]/total_worlds:.1f}/wk ({win_by_opt[k]/len(rs_):.1%} of q, {win_by_opt[k]/len(w_rs):.1%} of won)"
            for k in q_keys if win_by_opt[k] > 0
        )
        pl_by_opt = []
        for k in q_keys:
            pls_q = [r["quoted_opts"][k][0] / r["quoted_opts"][k][1] for r in rs_]
            pls_w = [r["quoted_opts"][k][0] / r["quoted_opts"][k][1] for r in w_rs if r["won_opt"] == k]
            flr_k = sum(1 for r in rs_ if k in r["floored_opts"]) / len(rs_)
            pl_by_opt.append(f"{k} med_q={st.median(pls_q):.2f} (flr={flr_k:.0%}, med_won={st.median(pls_w) if pls_w else 0:.2f})")
        print(f"  Quoted {str(q_keys):42s}: {q_wk:5.1f} req/wk | Total won: {len(w_rs)/total_worlds:5.1f}/wk ({len(w_rs)/len(rs_):.1%})")
        print(f"    Wins by option: {win_str}")
        print(f"    Price/list    : {' | '.join(pl_by_opt)}")
        if len(q_keys) >= 2 and "same_day" in q_keys and "next_day" in q_keys:
            for wopt in ("same_day", "next_day"):
                sub_w = [r for r in w_rs if r["won_opt"] == wopt]
                if sub_w:
                    q_ratio = [r["quoted_opts"]["same_day"][0] / r["quoted_opts"]["next_day"][0] for r in sub_w]
                    l_ratio = [r["quoted_opts"]["same_day"][1] / r["quoted_opts"]["next_day"][1] for r in sub_w]
                    flr_nd = sum(1 for r in sub_w if "next_day" in r["floored_opts"]) / len(sub_w)
                    print(
                        f"    When {wopt:8s} wins (n={len(sub_w)}): med quote(SD)/quote(ND)={st.median(q_ratio):.3f}, "
                        f"med list(SD)/list(ND)={st.median(l_ratio):.3f}, next_day_floored={flr_nd:.1%}"
                    )

    print()
    print("=== 2E. LANE & DELIVERY-SUPPLY FACTOR (TYP_FEE/LIST & DELIVERY S30) ===")
    for d_label, d_pred in [("Delivery dense (d_s30>=100)", lambda r: r["d_s30"] >= 100),
                            ("Delivery mid (30<=d_s30<100)", lambda r: 30 <= r["d_s30"] < 100),
                            ("Delivery thin (d_s30<30)", lambda r: r["d_s30"] < 30)]:
        sub = [r for r in quoted_reqs if d_pred(r)]
        nrm = [r for r in sub if not r["ex_ante_flr"]]
        w_sub = [r for r in sub if r["outcome"] == "won"]
        w_nrm = [r for r in nrm if r["outcome"] == "won"]
        tl = [r["typ_fee"] / r["ex_ante_lc"] for r in sub]
        print(
            f"  {d_label:30s}: quot={len(sub)/total_worlds:5.1f}/wk (nrm={len(nrm)/total_worlds:5.1f}/wk, flr={1-len(nrm)/len(sub):4.0%}) | "
            f"win_all={len(w_sub)/len(sub):5.1%}, win_nrm={len(w_nrm)/len(nrm) if nrm else 0:5.1%} | med typ/list={st.median(tl):.2f} | "
            f"mrg/ord=€{sum(r['net_margin_cents'] for r in w_sub)/100/len(w_sub) if w_sub else 0:.1f}"
        )

    print()
    print("=== 3. LEAK (A): SAFE DECLINED REQUESTS WE COULD SERVE ===")
    c_dec = collections.Counter((r["sband"], r["decline_reason"], r["dband"]) for r in dec_reqs)
    for (sb, reason, db), cnt in sorted(c_dec.items()):
        print(f"  {sb:15s} {reason:28s} {db:10s}: {cnt/total_worlds:5.1f} reqs/wk")

    thin_reqs = [r for r in req_records if r["sband"] == "4_thin_s55<30"]
    thin_buckets = collections.Counter()
    for r in thin_reqs:
        has_slow = "next_day" in r["offered_opts"] or "within_3_days" in r["offered_opts"]
        if r["s55"] >= 20:
            b = "1_s55_20-29"
        elif r["s70"] >= 30:
            b = "2_s55<20_but_s70>=30"
        elif r["d_s30"] >= 100:
            b = "3_s70<30_to_CAP/dense"
        else:
            b = "4_deep_thin_other"
        thin_buckets[(b, "slow_offered" if has_slow else "same_day_only", r["dband"])] += 1
    print("  Thin pickup breakdown:")
    for k, cnt in sorted(thin_buckets.items()):
        print(f"    {str(k):55s}: {cnt/total_worlds:5.1f} reqs/wk")

    print()
    print("=== 4. LEAK (B): PRICING, FLOOR, D01 TRUST & CLOCKS ===")
    for sband in sorted({r["sband"] for r in quoted_reqs}):
        for is_flr in (False, True):
            sub = [r for r in quoted_reqs if r["sband"] == sband and r["ex_ante_flr"] == is_flr]
            if not sub:
                continue
            w_sub = [r for r in sub if r["outcome"] == "won"]
            tl = [r["typ_fee"] / r["ex_ante_lc"] for r in sub]
            pl = [r["ex_ante_qc"] / r["ex_ante_lc"] for r in sub]
            print(
                f"  {sband:15s} floored={str(is_flr):5s}: quoted={len(sub)/total_worlds:5.1f}/wk, "
                f"won={len(w_sub)/total_worlds:5.1f}/wk ({len(w_sub)/len(sub):4.1%}), "
                f"med typ/list={st.median(tl):.2f}, med quote/list={st.median(pl):.2f}"
            )

    print()
    print("=== 5. LEAK (C): DRIVER FEES ABOVE 0.85x TYPICAL (RISING RAMP VS DEADLINE_CLOSE) ===")
    warned_won = [r for r in won_reqs if r["is_warned"]]
    unwarned_overnight = [r for r in won_reqs if not r["is_warned"] and r["book_at"] is not None and (r["book_at"] // DAY > r["post_at"] // DAY)]
    unwarned_sameday_ramp = [r for r in won_reqs if not r["is_warned"] and r["book_at"] is not None and (r["book_at"] // DAY == r["post_at"] // DAY) and r["last_book_delay"] > 5]
    unwarned_fast5 = [r for r in won_reqs if not r["is_warned"] and r["book_at"] is not None and r["last_book_delay"] <= 5]
    for lbl, grp in [
        ("1. Unwarned booked <= 5 min (at 0.85x)", unwarned_fast5),
        ("2. Unwarned same-day rising ramp (>5 min)", unwarned_sameday_ramp),
        ("3. Unwarned overnight/next-day rising ramp", unwarned_overnight),
        ("4. Warned orders (deadline_close steep ramp)", warned_won),
    ]:
        ex = sum(max(0, r["fee_cents"] - 0.85 * r["typ_fee"]) for r in grp) / 100.0 / total_worlds
        tot = sum(r["fee_cents"] for r in grp) / 100.0 / total_worlds
        frs = [r["fee_cents"] / r["typ_fee"] for r in grp if r["fee_cents"] > 0]
        print(
            f"    {lbl:44s}: {len(grp)/total_worlds:5.1f} ord/wk | med fee/typ={st.median(frs) if frs else 0:.2f} "
            f"mean={st.mean(frs) if frs else 0:.2f} | total=€{tot:6.0f}/wk | >0.85x=€{ex:5.0f}/wk"
        )

    print()
    print("=== 6. LEAK (D): REFUNDS, FAILED VISITS, RELEASE FEES, WAITING ===")
    late_reqs = [r for r in won_reqs if r["is_late"]]
    print(f"  Total late/undelivered orders: {len(late_reqs)} ({len(late_reqs)/total_worlds:.2f}/wk, {len(late_reqs)/len(won_reqs):.2%} of won)")
    late_cats = collections.Counter()
    late_cost_cats = collections.Counter()
    for r in late_reqs:
        cost = (r["late_ref_cents"] + r["undeliv_cents"]) / 100.0
        l0 = r["truth_leg0"]
        has_note_dl = bool(l0.get("truth.noteDeadline")) or (
            l0.get("truth.deliveryHours.closes") and int(l0["truth.deliveryHours.closes"]) < int(l0["delivery.hours.closes"])
        )
        if r["has_narrow_win"] or r["n_legs"] == 2:
            cat = f"0_trade_in_or_narrow_stop_window (legs={r['n_legs']})"
        elif has_note_dl:
            cat = "1_note_tighter_deadline_or_hours"
        elif r["is_warned"]:
            cat = f"2_unbooked_at_deadline_close ({r['sband']}, {r['won_opt']}, {r['dband']})"
        elif r["n_drops"] > 0:
            cat = "3_driver_dropped_gig"
        elif r["n_fails"] > 0:
            cat = "4_failed_visit_delay"
        else:
            cat = "5_driver_late_no_warning"
        late_cats[cat] += 1
        late_cost_cats[cat] += cost
    for cat, cnt in late_cats.most_common():
        print(f"    {cat:65s}: {cnt/total_worlds:4.2f}/wk (€{late_cost_cats[cat]/total_worlds:6.1f}/wk)")

    ti_won = [r for r in won_reqs if r["n_legs"] == 2 or r["has_narrow_win"]]
    ti_late = [r for r in ti_won if r["is_late"]]
    print(
        f"  Trade-in / narrow-window orders won: {len(ti_won)} ({len(ti_won)/total_worlds:.2f}/wk) -> "
        f"late: {len(ti_late)} ({len(ti_late)/len(ti_won) if ti_won else 0:.1%}, {len(ti_late)/total_worlds:.2f}/wk), "
        f"net margin/wk: €{sum(r['net_margin_cents'] for r in ti_won)/100/total_worlds:.1f}/wk"
    )
    print("  Breakdown by stop address/window structure (Trade-in vs Private Pickup vs Private Delivery vs Dealer-to-Dealer):")
    addr_groups = collections.defaultdict(list)
    for r in won_reqs:
        l0 = r["truth_leg0"]
        if r["n_legs"] == 2:
            ak = f"1_trade_in_2legs_{r['won_opt']}"
        elif l0["pickup.privateAddress"] == "true":
            ak = f"2_priv_pickup_{r['won_opt']}"
        elif l0["delivery.privateAddress"] == "true":
            ak = f"3_priv_delivery_{r['won_opt']}"
        else:
            ak = f"4_dealer_to_dealer_{r['won_opt']}"
        addr_groups[ak].append(r)
    for ak, grp in sorted(addr_groups.items()):
        l_cnt = sum(1 for r in grp if r["is_late"])
        m_wk = sum(r["net_margin_cents"] for r in grp) / 100.0 / total_worlds
        print(
            f"    {ak:34s}: won={len(grp)/total_worlds:5.1f}/wk | late={l_cnt/total_worlds:4.2f}/wk ({l_cnt/len(grp):5.1%}) | "
            f"mrg/ord=€{m_wk/(len(grp)/total_worlds):5.1f} | mrg/wk=€{m_wk:6.1f}"
        )

    late_no_warn = [r for r in late_reqs if not r["is_warned"] and not r["has_narrow_win"] and r["mins_late"] is not None]
    if late_no_warn:
        mls = sorted(r["mins_late"] for r in late_no_warn)
        print(f"  Late without deadline_close or narrow window (n={len(late_no_warn)}): mins_late list: {mls[:20]} ... median={st.median(mls):.0f} min")

    fail_reqs = [r for r in won_reqs if r["n_fails"] > 0]
    fail_reasons = collections.Counter(reason for r in fail_reqs for reason in r["fail_reasons"])
    print(f"  Failed visits: {len(fail_reqs)/total_worlds:.2f} orders/wk, cost €{sum(r['fail_vis_cents'] for r in won_reqs)/100/total_worlds:.1f}/wk, reasons: {dict(fail_reasons)}")


if __name__ == "__main__":
    main()
