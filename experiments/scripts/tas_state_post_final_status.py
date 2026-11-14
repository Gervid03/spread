"""Post final tas-state 4-world waterfall, limit files inventory, and Sunday rule summary to ~/.spread-lab/tas/STATUS.md."""
from __future__ import annotations

from spread_lab.env import lab_home

FINAL_BLOCK = """
## Sat 14 Nov 19:39 Helsinki (`tas-state`, branch `exp/gemini-tas-state` PUSHED): Full 4-World TAS Waterfall + `fri_endgame=true` (`t=2.04` SAFE) Complete!
- **Full 4-World TAS Waterfall & Note Committed & Pushed:** `experiments/20261114-1425-gemini-tas-state.md` on `origin/exp/gemini-tas-state`.
  - **4-World Mean Waterfall (anchored on `v5`):** Champion `v5` **€12,201.00** (min OT `93.7%`) → `+Perfect Prices` **€17,022.05** (`+39.5%`) → `+Foresight Tours` **€16,824.11** → `+Hidden State Steered` **€18,160.39** (`+€1,336/wk` pure state-steering lift on tours: `+€534` on `dev-12`, **`+€1,805.67` on `dev-08`**, and **`+€684.32` & `+4.09%` OT rescue (`90.8% → 94.9%`) on `dev-07`**) → **Best Achieved TAS Ceiling: `€18,573.27` (`≥92%` SAFE, `+52.2%`) / `€18,828.69` (`≥90%` Edge, `+54.3%`)**, peaking at **`€25,084.71` (`+€10,070.35`, `96.7%` OT)** on `dev-08`!
- **New Canonical `limits-*.jsonl` Files Available for `r4-limits`:**
  - `dev-12`: `limits-tas-state-{L1-trust,L2-comp,L3-events,dp-safe,dp-edge,disc90-safe}.jsonl`
  - `dev-01, dev-08, dev-07`: `limits-tas-state-{dp-safe,dp-edge}.jsonl`
- **Live Merge Candidate for `exp/stack-v7` (`src/spread_lab/policy.py`, `-s fri_endgame=true`):**
  - 14 lines in `Desk.price()` & `Desk.learn()` (`O(1)`, 0 forks, 0 extra state, `rejoin()`-safe): on Friday (`day >= 4`, 0 future competitor cuts + 72h Sat–Mon buffer), bypass `loss_streak_freeze`, target `price_target_win=0.52`, and allow `1.60x` `backlog_cap` exclusively on `next_day`/`within_3_days`.
  - **16 `dev` worlds (`runs/20261114-130229-sun-fri-endgame-dev16`):** **SAFE (`16/16` ranked, min OT `94.0%` up from `93.7%`), `Δmargin €+89.63 ± 43.94 (t = 2.04, 11W / 5L)`**, `+€449.01` on tail world `dev-01`!
"""


def main() -> None:
    p = lab_home() / "tas" / "STATUS.md"
    txt = p.read_text(encoding="utf-8")
    if "19:39 Helsinki (`tas-state`" not in txt:
        p.write_text(txt.rstrip() + chr(10) + chr(10) + "---" + chr(10) + FINAL_BLOCK.strip() + chr(10), encoding="utf-8")
        print("Posted final tas-state summary to STATUS.md!")


if __name__ == "__main__":
    main()
