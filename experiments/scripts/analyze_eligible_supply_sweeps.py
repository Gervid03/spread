"""Summarize run metrics, paired comparisons vs champion, and eligibility counters."""
from __future__ import annotations

import glob
import json
from pathlib import Path

from spread_lab.lab import champion_results, compare, load_results


def main() -> None:
    champ = champion_results()
    for rdir in sorted(glob.glob("runs/20261114-*")):
        p = Path(rdir)
        rows = load_results(p)
        s = json.loads((p / "summary.json").read_text(encoding="utf-8"))
        c = compare(rows, champ)
        tot_won = sum(r["won"] for r in rows)
        tot_late = sum(round(r["won"] * (1 - r["on_time"])) for r in rows)
        under92 = sum(1 for r in rows if r["on_time"] < 0.92)
        st = lambda k: sum(r["stats"].get(k, 0) for r in rows)
        print(
            f"{p.name:<56} n={s['n']:<2} mean=€{s['margin_mean']:>9,.2f} "
            f"Δ=€{c['delta_mean']:+7.2f}±{c['delta_se']:6.2f} t={str(c['t']):>5} "
            f"b/w={c['better']}/{c['worse']} ot_min={s['on_time_min']*100:5.2f}% u92={under92} "
            f"won={tot_won:>4} late={tot_late:>3} "
            f"decl_elig={st('prem_Manual_declined_elig'):>3}"
            f"(g={st('prem_declined_elig_gate')},b={st('prem_declined_elig_backlog')},o={st('prem_declined_elig_opts')}) "
            f"prem={st('prem_q')}/{st('prem_won')}/{st('prem_late')} "
            f"man={st('manual_q')}/{st('manual_won')}/{st('manual_late')}"
        )


if __name__ == "__main__":
    main()
