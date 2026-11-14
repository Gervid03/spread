"""Append a timestamped tas-price status section to ~/.spread-lab/tas/STATUS.md without overwriting other agents."""
from __future__ import annotations

import sys
from spread_lab.env import lab_home

SECTION_STEP1 = """

---

## Sat 14 Nov 14:56 Helsinki (`tas-price`, branch `exp/gemini-tas-price`): Layer 1 COMPLETE on ALL 4 TAS WORLDS!
- **Canonical Layer 1 files READY** (`~/.spread-lab/tas/<seed>/limits-won-apply.jsonl` & `book-won-apply.json`, verified via 0-fork `run --book` to the cent):
  | Seed | Champion v5 | Layer 1 (`limits-won-apply`) | Δ Margin | Won | On-time | `driver_fee` Δ | Forks |
  |---|---:|---:|---:|---:|---:|---:|---:|
  | `dev-12` | €10,910.49 | **€14,572.94** | **+€3,662.45** (+33.6%) | 246 | 98.0% | €0.00 | 1,737 |
  | `dev-01` | €8,469.14 | **€11,680.61** | **+€3,211.47** (+37.9%) | 254 | 93.7% | €0.00 | 1,600 |
  | `dev-08` | €15,014.36 | **€20,518.72** | **+€5,504.36** (+36.7%) | 287 | 98.3% | €0.00 | 1,874 |
  | `dev-07` | €14,410.02 | **€21,315.92** | **+€6,905.90** (+47.9%) | 338 | 95.6% | €0.00 | 2,180 |
  | **4-world mean** | **€12,201.00** | **€17,022.05** | **+€4,821.05** (+39.5%) | 281.3 | 96.4% | **€0.00** | 1,848 |
- **Key findings from Layer 1**:
  1. Every non-price ledger line (`driver_fee`, `release_fee`, `failed_visit`, `waiting`), order count, and on-time share is **identical to the cent** across all 4 worlds (`0 CHECK`s).
  2. On `dev-08` (3 orders) and `dev-07` (9 orders), outage+trust limits exceeded default `hi=2.6x`.
  3. **Subtle ledger edge**: On undelivered orders (`dev-01` 1 car, `dev-07` 1 car), rules charge `2 × price` penalty with `0` revenue — so raising the price of an undelivered order *hurts* margin by `-2 × Δprice` (`-€26.20` on `dev-01`, `-€76.56` on `dev-07`), whereas winning that same car at minimal price (`0.7x` or `€1`) would *save* `2 × price`!
- **Next (`tas-price`)**: Running full-week `limits-all.jsonl` (`--mode all --lo 0.6 --hi 3.4 --iters 8 --name all`) on `dev-12` right now (~6 min).
"""


def main() -> None:
    dst = lab_home() / "tas" / "STATUS.md"
    cur = dst.read_text(encoding="utf-8") if dst.exists() else "# TAS status"
    marker = "Layer 1 COMPLETE on ALL 4 TAS WORLDS!"
    if marker in cur and "--force" not in sys.argv:
        print("Section already present in STATUS.md")
        return
    dst.write_text(cur.rstrip() + SECTION_STEP1, encoding="utf-8")
    print(f"Appended section to {dst} ({dst.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
