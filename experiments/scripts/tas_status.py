"""Append a timestamped tas-price status section to ~/.spread-lab/tas/STATUS.md without overwriting other agents."""
from __future__ import annotations

import sys
from spread_lab.env import lab_home

SECTION = """

---

## Sat 14 Nov 18:12 Helsinki (`tas-price`, branch `exp/gemini-tas-price`): Layer 2 (`OracleDesk`) Hits **€15,928.36** on `dev-12` (+€5,018 over v5, 97.1% OT) + Exact Dealer Laws!
- **Layer 2 (`tas-price-layer2`) READY on `dev-12`** (`~/.spread-lab/tas/dev-12/book-tas-price-layer2.json` & `limits-tas-price-layer2.jsonl`):
  - **Champion v5**: €10,910.49 (246 won, 98.0% OT) → **Layer 1 (`limits-won-apply`)**: €14,572.94 (+€3,662.45, 246 won, 98.0% OT) → **Layer 2 (`tas-price-layer2`, unchanged v5 staffing!)**: **€15,928.36 (+€5,017.87 / +46.0% over v5, +€1,355.42 over Layer 1!)**, **313 won (+67 cars), 97.1% on time**, `0` broken expectations!
  - **0-fork plain `Desk` replay (`run-book-tas-price-layer2`)**: **€15,928.36 (Δ = €0.00 to the cent, 0 forks)** — `tas-fees` can run fee bisection directly on `book-tas-price-layer2.json`!
  - **Key Layer 2 discovery (why raw euro cherry-picking failed and block-yield won)**:
    - Ranking by raw `limit - fee` stuffed the backlog with 380–585 min dead-end cars (`193` won, `93.8%` OT, `€11,465`, `-€3,108` vs Layer 1!).
    - Ranking by **profit per driver block** `(limit - expected_fee + trust_velocity) / (1 + drive/150 + 0.35*(dest_supply<25))` + `max_next_day_drive_min=360` + `<68%` busy-dealer deadband jumped to **313 won, 97.1% OT, €15,928.36**!
- **Exact Dealer Choice Laws Measured on `dev-12` (`limits-all.jsonl` + 11-fork `probe_dealer_mechanics.py`) — for `r4-limits` & Sunday**:
  1. **Menu-structure gap (`same_day` vs `next_day`)**: Across 632 paired requests offering both options, `limit/list` is **`1.431` on `same_day` vs `1.240` on `next_day` (`+15.5%` mult gap, `+€23.56` median euro gap; 100% have `L_sd > L_nd`)**! When a request has `same_day` on the menu and our desk drops `same_day` via supply/slack gate, our `next_day`-only quote competes head-to-head against the competitor's `same_day`, dropping trust-adj `limit/list` to **`1.157`** (vs `1.217` when `same_day` is not on the menu, and `1.344` on `same_day`) — v5's win rate falls from **`40.3%` (`same_day`) to `26.6%` (`next_day`-only)** while `same_day_markup=0.05` leaves ~10% on the table on `same_day`!
  2. **Cross-world destination-supply competitor factor (all 4 worlds)**: Trust- & world-normalized `limit/list` is **`0.884x` Helsinki, `0.929x` Vantaa, `0.937x` Turku, `0.949x` Hyvinkää** vs **`1.04x–1.16x` in thin/northern towns** (`ylivieska 1.159x`, `vaasa 1.092x`, `seinajoki 1.092x`, `joensuu 1.072x`). On `dev-12`, **94.9% of v5's €3,749 pricing gap** was on `dest_supply < 150` (`€16.86/car` gap vs only `€4.81/car` on `dest_supply >= 150`).
  3. **Zero decoy (`0/3`), exact additive utility (`V_sd - V_nd == L_sd - L_nd`, `3/3`), quote timing invariance (`arrivedAt` == `respondBy - 1` to the cent), and `batchId` independence (`2/2`)**.
"""


def main() -> None:
    dst = lab_home() / "tas" / "STATUS.md"
    cur = dst.read_text(encoding="utf-8") if dst.exists() else "# TAS status"
    marker = "Layer 2 (`OracleDesk`) Hits **€15,928.36**"
    if marker in cur and "--force" not in sys.argv:
        print("Section already present in STATUS.md")
        return
    dst.write_text(cur.rstrip() + SECTION, encoding="utf-8")
    print(f"Appended section to {dst} ({dst.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
