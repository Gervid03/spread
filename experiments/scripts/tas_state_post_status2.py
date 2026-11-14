"""Append Thursday Cold-Start Probe + sun_fri_endgame (dev16 t=2.04 SAFE) update to ~/.spread-lab/tas/STATUS.md."""
from __future__ import annotations

from spread_lab.env import lab_home


UPDATE_BLOCK = """
## Sat 14 Nov 15:06 Helsinki (`tas-state`, branch `exp/gemini-tas-state`): Thu 00:00 Cold-Start Law + Live `sun_fri_endgame` (`t=2.04` SAFE on dev-16!)
- **Thursday `00:00` Cold-Start Probe on `dev-12` (`tas-state-thu-coldstart.json`, 22 forks)**:
  - **Exact unquoted satisfaction penalty (`silent` 614 unquoted Mon–Wed requests vs `4.0x` explicit declines)**: Thursday `08:00` limits are **`0.9900x`–`0.9916x` (`-0.84%` to `-1.00%` total satisfaction cost across 3 silent days!)**. Because 3 days of `0%` win share simultaneously push busy-dealer competitors up **`+3` steps (`+12%`–`+15%`)**, net Thursday morning limits on busy dealers sit **`+11%`–`+14%` above normal Monday**!
  - **Exact `branch()` from `Thu 00:00` to `Wed+ 22:00` (replica of the 14:00 / 20:00 Test Final)**:
    - Standard cold-join (`mult=1.35, price_target_win=0.40, backlog_ratio=0.06`): **`€2,481.71`** (`73` won, `100.0%` OT)
    - `mult=1.52, price_target_win=0.44`: **`€2,568.96 (+€87.25, +3.5%)`** (`75` won, `98.7%` OT)
    - `mult=1.54, price_target_win=0.46, backlog_ratio=0.135, trust_invest=0.05`: **`€2,667.81 (+€186.10, +7.5% in 2 days!)`** (`77` won, `98.7%` OT)
- **Blind Flat-Fee Driver-Learning Test (`run-tas-state-flatfees-L1` on `dev-12`, 0 forks)**:
  - Posting static flat `0.85x` schedules without fork bisection on `book-won-apply.json` dropped `on_time` `98.0% -> 90.6%` (`€8,058.88`, `-€6,514` vs Layer 1): eliminating viewer holdout learning ONLY pays when paired with fork-bisected reservation fees (`tas-fees`), never with a blind flat schedule.
- **Live Forkless Sunday Rule Confirmed on 16 `dev` Worlds (`runs/20261114-130229-sun-fri-endgame-dev16`)**:
  - `SundayStateDesk` with `sun_fri_endgame=true` (derived from `tas-state`'s Friday `100%` competitor-immunity law: bypass `loss_streak_freeze` on Friday, target `price_target_win=0.52` on Friday, and `1.60x` Friday slow-option weekend backlog):
  - **16 `dev` seeds (normal instrument, vs Champion v5): `Δmargin €+89.63 ± 43.94 (SE), t = 2.04` (`11` better, `5` worse), `SAFE` (`16/16` ranked, min on-time `94.0%` up from `93.7%` — `dev-01` jumped `+€449.01` from `€8,469.14 -> €8,918.15`!)**.
"""


def main() -> None:
    p = lab_home() / "tas" / "STATUS.md"
    txt = p.read_text(encoding="utf-8")
    if "15:06 Helsinki (`tas-state`" not in txt:
        p.write_text(txt.rstrip() + chr(10) + chr(10) + UPDATE_BLOCK.strip() + chr(10), encoding="utf-8")
        print("Updated STATUS.md!")


if __name__ == "__main__":
    main()
