"""Inspect counters of the 3 finished smoke seeds in r4v-v7-s1-stack vs Champion v7."""
from __future__ import annotations

import glob
import json
from pathlib import Path


def main() -> None:
    champ = {json.loads(l)["seed"]: json.loads(l) for l in Path("champion/results/dev-L8.jsonl").read_text().splitlines() if l.strip()}
    for p in sorted(glob.glob("runs/*r4v-v7-s1-stack*/results.jsonl")):
        for l in Path(p).read_text().splitlines():
            if not l.strip():
                continue
            r = json.loads(l)
            c = champ[r["seed"]]
            st = r["stats"]
            cst = c["stats"]
            print(
                f"{r['seed']}: champ={c['margin']:.2f}({c['won']}, {c['on_time']*100:.1f}%) -> "
                f"cand={r['margin']:.2f}({r['won']}, {r['on_time']*100:.1f}%) | "
                f"dMargin={r['margin']-c['margin']:+.2f} dWon={r['won']-c['won']:+d}"
            )
            print(
                f"  cyc_2/3/4: {cst.get('cyc_posted_2',0)}/{cst.get('cyc_posted_3',0)}/{cst.get('cyc_posted_4',0)} -> "
                f"{st.get('cyc_posted_2',0)}/{st.get('cyc_posted_3',0)}/{st.get('cyc_posted_4',0)} | "
                f"ret_hub={cst.get('won_return_hub',0)}->{st.get('won_return_hub',0)} "
                f"sp_won={st.get('r4v_sponsor_won',0)} cl_won={st.get('r4v_return_closing_won',0)} "
                f"ti_won={st.get('r4v_tradein_won',0)} lc_book={cst.get('lead_car_booked',0)}->{st.get('lead_car_booked',0)} "
                f"vf={st.get('visit_failed',0)}"
            )


if __name__ == "__main__":
    main()
