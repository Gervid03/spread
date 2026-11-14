"""Analyze feeclock-on-a runs against baseline A and champion."""
from __future__ import annotations

from pathlib import Path
from spread_lab.lab import champion_results, compare, load_results, summarize

A_SMOKE = Path("../n14-03324-supply-adaptive-fee-open-and-drop-rescue/runs/20261114-034543-fee-drop-smoke5-all180")
A_DEV = Path("../n14-03324-supply-adaptive-fee-open-and-drop-rescue/runs/20261114-034812-fee-drop-all180-dev")


def main() -> None:
    a_smoke = load_results(A_SMOKE)
    a_dev = load_results(A_DEV)
    champ = champion_results()

    for r in sorted(Path("runs").glob("20261114-*")):
        rows = load_results(r)
        if not rows:
            continue
        s = summarize(rows)
        base_a = a_smoke if len(rows) <= 4 else a_dev
        ca = compare(rows, base_a)
        cc = compare(rows, champ)
        dc = sum(row["stats"].get("deadline_close", 0) for row in rows) / len(rows)
        gd = sum(row["stats"].get("gig_dropped", 0) for row in rows) / len(rows)
        dn = sum(row["stats"].get("drops_near", 0) for row in rows) / len(rows)
        dfar = sum(row["stats"].get("drops_far", 0) for row in rows) / len(rows)
        df = sum(row["ledger"].get("driver_fee", 0) for row in rows) / len(rows)
        rev = sum(row["ledger"].get("revenue", 0) for row in rows) / len(rows)
        print(
            f"{r.name:<42} n={s['n']:<2} margin={s['margin_mean']:8.2f} "
            f"ΔA={ca['delta_mean']:+7.2f}±{ca['delta_se']:6.2f} (t={ca['t']}, {ca['better']}/{ca['worse']}, Δot={ca['on_time_delta_mean']:+.2%}) "
            f"ΔC={cc['delta_mean']:+7.2f}±{cc['delta_se']:6.2f} (t={cc['t']}, {cc['better']}/{cc['worse']}, Δot={cc['on_time_delta_mean']:+.2%}) "
            f"ot_min={s['on_time_min']:.4f} ot_mean={s['on_time_mean']:.4f} safe={s['safe']} "
            f"dc={dc:.1f} gd={gd:.1f} (near={dn:.1f}/far={dfar:.1f}) rev={rev:.0f} dfee={df:.0f}"
        )
        feex_parts = []
        for opt in ("same_day", "next_day", "within_3_days"):
            for when in ("same", "later"):
                tot_s = sum(row["stats"].get(f"feex_{opt}_{when}_sum", 0) for row in rows)
                tot_n = sum(row["stats"].get(f"feex_{opt}_{when}_n", 0) for row in rows)
                if tot_n > 0:
                    feex_parts.append(f"{opt[:4]}_{when}={tot_s / tot_n / 1000:.3f}x (n={tot_n / len(rows):.1f})")
        if feex_parts:
            print("    feex:", ", ".join(feex_parts))


if __name__ == "__main__":
    main()
