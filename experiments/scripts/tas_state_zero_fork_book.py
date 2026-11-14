"""Tests ROI-ranked (`(est_lim - est_fee) / ref`) + `max_next_day_drive_min=340` + State-Steered (`<30%` Mon / `<68%` Tue-Thu / `100%` Fri)
0-fork book on `dev-12` (15s, 0 fork lanes), fixing the `d+2` trust-delivery timing bug!"""
from __future__ import annotations

import json
import math
import sys
from argparse import Namespace
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from spread_lab.env import lab_home  # noqa: E402
from spread_lab.geo import Geo  # noqa: E402
from spread_lab.policy import DAY, HOUR, Desk, Params  # noqa: E402
import tas  # noqa: E402


def main() -> None:
    seed = "dev-12"
    home = lab_home()
    sdir = home / "tas" / seed
    wmap = json.loads((home / "map.json").read_text(encoding="utf-8"))
    geo = Geo(wmap)
    tape = json.loads((sdir / "tape.json").read_text(encoding="utf-8"))
    rev = json.loads((sdir / "reveal-v5.json").read_text(encoding="utf-8"))
    champ_p = json.loads((ROOT / "champion" / "champion.json").read_text(encoding="utf-8"))["params"]

    lall_rows = [json.loads(l) for l in (sdir / "limits-all.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    lim_map = {(r["rid"], r["option"]): r for r in lall_rows if r.get("lo")}

    dlr_tot = Counter((r["dealerId"], r["arrivedAt"] // DAY) for r in tape["requests"])
    v5_won = Counter()
    for rr in rev["requests"]:
        if rr.get("outcome") == "won":
            req = rr["request"]
            v5_won[(req["dealerId"], req["arrivedAt"] // DAY)] += 1

    v5_step: dict[tuple[str, int], int] = {}
    for dlr in {r["dealerId"] for r in tape["requests"]}:
        st = 0
        for d in range(5):
            v5_step[(dlr, d)] = st
            tot_d = dlr_tot[(dlr, d)]
            if tot_d >= 10:
                sh = v5_won[(dlr, d)] / tot_d
                if sh < 0.30:
                    st = min(3, st + 1)
                elif sh >= 0.70:
                    st = max(-3, st - 1)

    s30 = geo.supply(tape["roster"], 30.0)
    shadow = Desk(
        world=None,  # type: ignore[arg-type]
        params=Params(**{**champ_p, "backlog_ratio": 1.0, "max_next_day_drive_min": 310}),
        level=8,
        geo=geo,
        roster=tape["roster"],
        now=0,
    )

    cands_by_day: dict[int, list] = {d: [] for d in range(5)}
    tue_fri_tot = Counter(r["dealerId"] for r in tape["requests"] if r["arrivedAt"] // DAY >= 1)
    for r in tape["requests"]:
        rid = r["id"]
        dlr = r["dealerId"]
        d, tod = r["arrivedAt"] // DAY, r["arrivedAt"] % DAY
        if d >= 5:
            continue
        shadow.now = r["arrivedAt"]
        prices, _ = shadow.price(r)
        if not prices:
            continue
        p0 = r["legs"][0]["pickup"]["placeId"]
        d0 = r["legs"][-1]["delivery"]["placeId"]
        drv = geo.minutes(p0, d0)
        ps, ds = s30.get(p0, 0), s30.get(d0, 0)
        ref_e = max(1.0, r["referenceFeeCents"] / 100.0)

        best_opt = None
        for chosen_k in prices:
            if d == 4 and tod > 11 * HOUR and chosen_k == "same_day":
                continue
            lrow = lim_map.get((rid, chosen_k))
            if not lrow:
                continue
            base_lo_e = (lrow["lo"] / 100.0) / (1.0 + 0.01 * min(25, lrow.get("trust", 0))) / (1.0 + 0.038 * v5_step[(dlr, d)])
            est_f = ref_e * (
                (0.80 if ds >= 150 else 0.92)
                + (0.20 * max(0, drv - 130) / 130.0 if ds < 140 else 0.0)
                + (0.10 if chosen_k == "same_day" else (-0.03 if chosen_k == "within_3_days" else 0.0))
            )
            trust_bonus_e = 7.0 if (chosen_k == "same_day" and d <= 1 and tod <= 12 * HOUR and ps >= 180 and drv <= 140 and tue_fri_tot[dlr] >= 45) else 0.0
            net_eur = base_lo_e * (1.18 if d >= 2 and tue_fri_tot[dlr] >= 45 else 1.0) + trust_bonus_e - 1.06 * est_f
            if (base_lo_e - est_f) / ref_e < 0.16:
                continue
            if best_opt is None or net_eur > best_opt[0]:
                best_opt = (net_eur, chosen_k, base_lo_e, est_f, drv)

        if best_opt is not None and best_opt[0] >= 14.0:
            net_eur, chosen_k, base_lo_e, est_f, drv = best_opt
            cands_by_day[d].append((net_eur, r, chosen_k, base_lo_e, est_f, drv, ref_e))

    book: dict[str, dict | str] = {r["id"]: "decline" for r in tape["requests"]}
    our_step: Counter[str] = Counter()
    deliv_ready_morning: Counter[tuple[str, int]] = Counter()
    chosen_summary = Counter()

    for d in range(5):
        our_trust = {
            dlr: min(25, int(0.88 * sum(deliv_ready_morning[(dlr, m_d)] for m_d in range(d + 1))))
            for dlr in {r["dealerId"] for r in tape["requests"]}
        }
        ranked = sorted(cands_by_day[d], key=lambda x: -x[0])
        won_today = 0
        sd_today = 0
        dlr_won_today = Counter()
        day_cap = 90 if d == 4 else 78

        for net_eur, r, chosen_k, base_lo_e, est_f, drv, ref_e in ranked:
            if won_today >= day_cap:
                continue
            if chosen_k == "same_day" and sd_today >= 18:
                continue
            dlr = r["dealerId"]
            tot_d = dlr_tot[(dlr, d)]
            if tot_d >= 10 and d < 4:
                cap = (max(1, math.ceil(0.30 * tot_d) - 1) if (d == 0 and tue_fri_tot[dlr] >= 45) else max(1, math.ceil(0.70 * tot_d) - 1))
                if dlr_won_today[dlr] >= cap:
                    continue

            proj_lim_e = base_lo_e * (1.0 + 0.037 * our_step[dlr]) * (1.0 + 0.01 * our_trust.get(dlr, 0))
            if (proj_lim_e - est_f) / ref_e < 0.16 or (proj_lim_e - est_f) < 15.0:
                continue

            quote_cents = int(proj_lim_e * 0.980 * 100.0)
            book[r["id"]] = {"option": chosen_k, "cents": quote_cents}
            won_today += 1
            dlr_won_today[dlr] += 1
            chosen_summary[d] += 1
            if chosen_k == "same_day":
                sd_today += 1
                deliv_ready_morning[(dlr, d + 1)] += 1  # Mon same_day ready Tue 08:00!
            elif chosen_k == "next_day":
                deliv_ready_morning[(dlr, d + 2)] += 1  # Tue next_day delivers Wed eve -> ready Thu 08:00!
            else:
                deliv_ready_morning[(dlr, d + 3)] += 1

        for dlr in {r["dealerId"] for r in tape["requests"]}:
            tot_d = dlr_tot[(dlr, d)]
            if tot_d >= 10:
                sh = dlr_won_today[dlr] / tot_d
                if sh < 0.30:
                    our_step[dlr] = min(3, our_step[dlr] + 1)
                elif sh >= 0.70:
                    our_step[dlr] = max(-3, our_step[dlr] - 1)

    bpath = sdir / "book-tas-state-roi-steered-0fork.json"
    bpath.write_text(json.dumps(book, indent=2, sort_keys=True) + chr(10), encoding="utf-8")
    print(f"Wrote {bpath} with {sum(chosen_summary.values())} planned wins: {dict(chosen_summary)}", flush=True)

    tas.cmd_run(
        Namespace(
            seed=seed,
            set=["backlog_ratio=0.14", "max_next_day_drive_min=340"],
            policy="spread_lab.policy:Desk",
            name="tas-state-roi-steered-0fork",
            until=None,
            book=str(bpath),
        )
    )


if __name__ == "__main__":
    main()
