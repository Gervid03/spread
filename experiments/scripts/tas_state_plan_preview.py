"""Offline preview of TasStateDesk's event detection, dealer daily caps, and DP selection on all 4 TAS seeds."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from spread_lab.geo import Geo
from spread_lab.policies.tas_state import TasStateDesk, TasStateParams

DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri")


def main() -> None:
    home = Path.home() / ".spread-lab"
    wmap = json.loads((home / "map.json").read_text(encoding="utf-8"))
    geo = Geo(wmap)

    for seed in ("dev-12", "dev-01", "dev-08", "dev-07"):
        tape = json.loads((home / "tas" / seed / "tape.json").read_text(encoding="utf-8"))
        params = TasStateParams(
            tas_seed=seed,
            tas_dp_select=True,
            tas_trust_farm=True,
            tas_comp_steer=True,
            tas_event_plan=True,
            tas_late_edge=False,
        )
        desk = TasStateDesk(world=None, params=params, level=8, geo=geo, roster=tape["roster"], now=0)  # type: ignore[arg-type]
        ev = desk.events_info
        print(f"=== {seed} ===")
        print(
            f"  Detected events: war_day={DAYS[ev['war_day']] if ev['war_day'] is not None else None}, "
            f"flu_day={DAYS[ev['flu_day']] if ev['flu_day'] is not None else None}, "
            f"outage={(DAYS[ev['outage'][0]], ev['outage'][1]) if ev['outage'] else None}, "
            f"snow_n={len(ev['snow'])}"
        )

        chosen = [v for v in desk.req_plan.values() if v["chosen_by_dp"]]
        by_day = Counter()
        by_opt = Counter()
        by_dlr_day = Counter()
        reqs_by_id = {r["id"]: r for r in tape["requests"]}
        est_gross = 0.0
        for item in chosen:
            r = reqs_by_id[item["rid"]]
            d = r["arrivedAt"] // 1440
            by_day[d] += 1
            by_opt[item["kind"]] += 1
            by_dlr_day[(r["dealerId"], d)] += 1
            est_gross += item["gross_m"]

        print(f"  DP chosen total = {len(chosen)} (est gross margin €{est_gross:,.0f})")
        print("  By day:", {DAYS[d]: by_day[d] for d in range(5)})
        print("  By option:", dict(by_opt))
        for dlr in ("D01", "D02", "D03", "D04"):
            tot_s = [desk.dlr_day_total[(dlr, d)] for d in range(5)]
            if sum(tot_s) >= 40:
                cap_s = [desk.dlr_day_cap.get((dlr, d), 0) for d in range(5)]
                ch_s = [by_dlr_day[(dlr, d)] for d in range(5)]
                sh_s = [f"{ch_s[d]}/{tot_s[d]}({ch_s[d]/max(1,tot_s[d])*100:.0f}%,cap={cap_s[d]})" for d in range(5)]
                print(f"    {dlr}: " + "  ".join(f"{DAYS[d]}:{sh_s[d]}" for d in range(5)))


if __name__ == "__main__":
    main()
