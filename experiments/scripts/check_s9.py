"""Check counters in r4v-s9-volstack on smoke."""
from __future__ import annotations

import json
from pathlib import Path


def main() -> None:
    noop = {json.loads(l)["seed"]: json.loads(l) for l in Path("runs/20261114-142131-r4-volume-noop/results.jsonl").read_text().splitlines() if l.strip()}
    s9 = {json.loads(l)["seed"]: json.loads(l) for l in Path("runs/20261114-160540-r4v-s9-volstack/results.jsonl").read_text().splitlines() if l.strip()}
    for seed in sorted(noop):
        a, b = noop[seed], s9[seed]
        st = b["stats"]
        ast = a["stats"]
        print(f"{seed}: dM={b['margin']-a['margin']:+.1f} dW={b['won']-a['won']:+d} | ret_hub={ast.get('won_return_hub',0)}->{st.get('won_return_hub',0)} ext={ast.get('won_ext_ring',0)}->{st.get('won_ext_ring',0)} guarded={st.get('r4v_ret_hub_guarded',0)} lcBook={ast.get('lead_car_booked',0)}->{st.get('lead_car_booked',0)} tBook={st.get('r4v_tour_booked',0)} tiWon={st.get('r4v_tradein_won',0)}")


if __name__ == "__main__":
    main()
