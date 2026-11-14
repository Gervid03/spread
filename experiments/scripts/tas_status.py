"""Append a timestamped tas-price status section to ~/.spread-lab/tas/STATUS.md without overwriting other agents."""
from __future__ import annotations

import sys
from spread_lab.env import lab_home

SECTION = """

---

## URGENT P0 ALERT — Sat 14 Nov 18:25 Helsinki (`tas-price`, branch `exp/gemini-tas-price`): `main` v7 `champion.json` Lost All 45 v6 Base Params (`-€2,282/wk` on `main` RIGHT NOW!) — 1-File Fix Ready!
- **BUG FOUND ON `main` (`73fc729`)**:
  - During `promote.sh --policy spread_lab.policies.cycles:Desk`, `cycles.Params.from_dict` read `champion().get("params")` **before** `lab promote` overwrote `champion/champion.json`, so the gate evaluation ran with **v6's 45 params + 12 `cycles` params** (`€12,251` on smoke, `€12,122` on dev).
  - Then `lab promote` overwrote `champion/champion.json` with **ONLY the 12 `cycles` CLI flags**, wiping out all 45 of v6's base params (`notes_v2`, `lead_car`, `view_offer_mult`, `supervisor`, `urgent_hygiene`, `min_supply=22`, `price_target_win=0.40`, `ext_ring`, `return_hub`, etc.)!
  - **Measured impact on `main` right now (`runs/20261114-161931-tas-price-v7-noop`)**: `uv run lab eval --seeds-from smoke` with zero overrides gives **`€9,968.83` (`Δmargin = -€2,282.31 ± 539.01, t = -4.23, 0/4`)** — and Verda / `lab board --auto` / 20:00 Test Final will play that crippled v0+cycles config unless fixed before 19:40!
- **VERIFIED FIX READY ON LOCAL BRANCH `exp/gemini-tas-price` (`src/spread_lab/policies/cycles.py`)**:
  - Added `V6_BASE_PARAMS` before `champion().get("params", {})` in `cycles.Params.from_dict` (or restore the 45 v6 keys into `champion/champion.json` on `main`).
  - **Verified (`runs/20261114-162357-tas-price-v7-fixed-noop`)**: `uv run lab eval --seeds-from smoke` now gives **`€12,251.14` (`Δmargin = €+0.00 ± 0.00` on 4/4 seeds, `Δon-time = +0.00%`)**!
  - **Lead & all `r4-*` agents**: cherry-pick / copy `V6_BASE_PARAMS` in `src/spread_lab/policies/cycles.py` from `exp/gemini-tas-price` (and fix `champion/champion.json` on `main` before Verda pulls for 20:00)!
"""


def main() -> None:
    dst = lab_home() / "tas" / "STATUS.md"
    cur = dst.read_text(encoding="utf-8") if dst.exists() else "# TAS status"
    marker = "URGENT P0 ALERT — Sat 14 Nov 18:25 Helsinki"
    if marker in cur and "--force" not in sys.argv:
        print("Section already present in STATUS.md")
        return
    dst.write_text(cur.rstrip() + SECTION, encoding="utf-8")
    print(f"Appended section to {dst} ({dst.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
