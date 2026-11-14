# option-spread-and-d01-cap: Trust-backed dealer cap (`trust_cap_boost`) and long-haul lane price slope (`drive_price_slope`)

- **Agent / branch / commit:** gemini · exp/gemini-n14-01393-option-spread-and-d01-cap · 943012d (base)
- **Date:** 2026-11-14 01:58
- **Idea from:** IDEAS.md items #4, #5, #6 & R2 (`trust_cap_boost` and `drive_price_slope` on top of `origin/exp/gemini-n14-02-trust-v2`)

## Why we tried it
1. **Trust-backed dealer cap (`trust_cap_boost`):** Fable's scouting report (#5 & #6) showed that `D01` (one third of the market) hits the ceiling `price_mult_max × dealer_adj_max = 1.80 × 1.30 = 2.34× list` from Wednesday onward once its trust reaches 20–25 (+20% to +25% willingness to pay). Raising `dealer_adj_max` globally to `1.60` in sweep `08 n-caps` lost `-€300 ± 125 (t = -2.4)` because low-trust dealers got overpriced after random win streaks. Because `exp/gemini-n14-02-trust-v2` tracks exact ledger-based dealer trust `self.dealer_trust[dealer]` (0 to 25), we can keep `dealer_adj_max = 1.30` for untrusted dealers and raise a dealer's cap strictly in proportion to earned trust: `hi = p.dealer_adj_max + p.trust_cap_boost * (min(self.dealer_trust[dealer], 25) / 25.0)`.
2. **Long-haul lane factor (`drive_price_slope`):** In `n14-11-class-table` (R2), won orders with `drive > 300 min` pay a higher driver fee multiple (`booked_fee / typical_fee = 1.09` vs `1.01` for `<300 min`), and `docs/GAME.md` notes that the competitor's lane factor is higher on harder/longer lanes. Multiplying each option's price by `1 + p.drive_price_slope * max(0, drive - 150) / 300.0` prices long hauls higher relative to local transfers.

## What changed
Merged `origin/exp/gemini-n14-02-trust-v2` onto our branch and added two `Params` fields in `src/spread_lab/policy.py` with defaults `0.0`:
- `trust_cap_boost: float = 0.0` — in `Desk.learn`, clamps `self.dealer_adj[dealer]` at `hi = p.dealer_adj_max + p.trust_cap_boost * (min(self.dealer_trust[dealer], 25) / 25.0)` and increments `self.stats["dealer_cap_boosted"]` whenever `self.dealer_adj[dealer] > p.dealer_adj_max`.
- `drive_price_slope: float = 0.0` — in `Desk.price`, multiplies each option's price by `1 + p.drive_price_slope * max(0, drive - 150) / 300.0`.
- Also recorded `price_ratio_d0_pct..d4_pct` (mean quoted price / list price in percent per weekday) in `Desk.tick`.

Run with: `uv run lab eval -s trust_invest=0.05 -s trust_cap_boost=0.20 --name trust-cap-slope-dev`

## Results (level 8, vs champion v2, paired)
| set | run folder | overrides (on top of v2) | mean margin | Δmargin ± SE | t | better/worse | on-time min | SAFE |
|---|---|---|---|---|---|---|---|---|
| smoke | `runs/20261114-014808-trust-cap-slope-noop` | none (defaults) | €9,662.25 | €+0.00 ± 0.00 | — | 0/0 | 95.5% | yes |
| smoke | `runs/20261114-014858-trust-cap-slope-cap0.20` | `trust_invest=0.05, trust_cap_boost=0.20` | €9,900.77 | €+238.53 ± 297.54 | 0.80 | 3/1 | 94.7% | yes |
| smoke | `runs/20261114-014945-trust-cap-slope-cap0.30` | `trust_invest=0.05, trust_cap_boost=0.30` | €9,900.77 | €+238.53 ± 297.54 | 0.80 | 3/1 | 94.7% | yes |
| smoke | `runs/20261114-015012-trust-cap-slope-slope0.05` | `trust_invest=0.05, drive_price_slope=0.05` | €9,493.42 | €-168.83 ± 490.08 | -0.34 | 3/1 | 96.0% | yes |
| smoke | `runs/20261114-015149-trust-cap-slope-cap0.25-slope0.05` | `trust_invest=0.05, trust_cap_boost=0.25, drive_price_slope=0.05` | €9,297.51 | €-364.74 ± 544.51 | -0.67 | 2/2 | 96.4% | yes |
| smoke | `runs/20261114-015253-trust-cap-slope-cap0.20-slope0.02` | `trust_invest=0.05, trust_cap_boost=0.20, drive_price_slope=0.02` | €9,684.56 | €+22.31 ± 523.97 | 0.04 | 3/1 | 95.9% | yes |
| dev | `runs/20261114-015445-trust-cap-slope-dev` | `trust_invest=0.05, trust_cap_boost=0.20` | €9,253.56 | €+263.26 ± 138.74 | 1.90 | 10/6 | 94.7% | yes |
| dev | `runs/20261114-015723-trust-cap-slope-slack140-dev` | `trust_invest=0.05, trust_cap_boost=0.20, min_slack_min=140, slack_per_drive=0.75` | €9,218.58 | €+228.28 ± 146.54 | 1.56 | 11/5 | 93.5% | yes |
| *ref (dev)* | `runs/20261114-001846-trustv2-trust_invest0.05` | `trust_invest=0.05` alone (from `02-trust-v2`) | €9,293.76 | €+303.46 ± 134.52 | 2.26 | 11/5 | 94.7% | yes |

### Stats counters breakdown (mean `[min, max]` across seeds)
| Run | `dealer_cap_boosted` | `won` (score / stat) | `top_dealer_trust_d0..d4` (mean) | `price_ratio_d0_pct..d4_pct` (mean %) |
|---|---|---|---|---|
| `trust-cap-slope-noop` (smoke, 4) | `0.0 [0, 0]` | `240.2 / 243.0` | `3.8, 18.0, 22.5, 21.8, 24.8` | `145.6, 158.6, 164.5, 172.2, 162.7` |
| `trust-cap-slope-cap0.20` (smoke, 4) | `36.5 [0, 89]` | `241.2 / 243.5` | `4.5, 18.5, 22.3, 22.0, 25.0` | `146.2, 158.0, 165.9, 175.4, 165.1` |
| `trust-cap-slope-slope0.05` (smoke, 4) | `0.0 [0, 0]` | `240.8 / 243.5` | `4.3, 19.5, 23.5, 23.0, 24.8` | `146.8, 157.0, 166.5, 173.3, 166.2` |
| `trust-cap-slope-cap0.25-slope0.05` (smoke, 4) | `27.8 [0, 59]` | `238.5 / 241.5` | `4.3, 19.5, 25.0, 20.8, 25.0` | `146.8, 156.9, 167.0, 174.0, 165.8` |
| `trust-cap-slope-dev` (dev, 16) | `17.9 [0, 89]` | `230.7 / 233.0` | `4.3, 14.6, 23.9, 22.7, 23.8` | `143.9, 150.2, 159.1, 167.9, 165.1` |
| `trust-cap-slope-slack140-dev` (dev, 16) | `16.2 [0, 89]` | `231.2 / 233.4` | `4.2, 15.0, 23.3, 23.2, 24.1` | `143.9, 149.4, 159.2, 167.3, 165.4` |

### What we learned
1. **Why `trust_cap_boost=0.20` and `0.30` were identical (`dealer_cap_boosted = 17.9` on dev):** With `dealer_lr = 0.02` and `price_target_win = 0.35`, even the highest-volume dealer (`D01`, ~300 requests/week) can only move `dealer_adj` above `1.30` up to roughly `1.42–1.46` by Friday, so `0.20` (ceiling `1.50` at trust 25) never binds differently from `0.30` (ceiling `1.60`).
2. **Why `trust_cap_boost=0.20` slightly underperforms `trust_invest=0.05` alone (`+€263.26 ± 138.74` vs `+€303.46 ± 134.52` on dev):** When `D01`'s `dealer_adj` climbs above `1.30` on Wednesday–Friday (`dealer_cap_boosted > 0`, raising Thursday/Friday `price_ratio_d3_pct` from `167.5%` to `167.9%` and `price_ratio_d4_pct` from `163.3%` to `165.1%`), two adverse feedback loops occur: (a) lost quotes at `>2.34× list` on `D01` step down the shared global multiplier `self.mult` (`price_lr = 0.05`), underpricing all other dealers, and (b) the competitor's morning per-dealer adaptation cuts prices where we won most earlier in the week, so pushing `dealer_adj` above `1.30` late in the week loses high-margin `D01` orders (e.g., on `dev-03`, `dealer_cap_boosted = 89` cost `-€598.72` vs `noop`).
3. **Why `drive_price_slope` failed (`-€168.83 ± 490.08` on smoke):** Just like `trust_gain` in `exp/gemini-trust`, adding an uncentered positive multiplier on `drive > 150 min` causes long-haul quotes to lose more often, which drags down the single global multiplier `self.mult` via `Desk.learn` and makes short/medium hauls too cheap.
4. **Stacking with `min_slack_min=140, slack_per_drive=0.75` (`trust-cap-slope-slack140-dev`):** Safely maintained 16/16 ranked (`min on-time = 93.5%`, `Δmargin €+228.28 ± 146.54`, `t = 1.56`, 11/5 better/worse), confirming the slack tilt is safe on v2, though slightly lower margin than `min_slack_min=180, slack_per_drive=0.5`.

## Verdict
reject `trust_cap_boost` and `drive_price_slope` (keep `trust_invest=0.05` alone from `02-trust-v2`) — `trust_invest=0.05, trust_cap_boost=0.20` is SAFE with **Δmargin €+263.26 ± 138.74 (t = 1.90, min on-time 94.7%)**, which is €40.20/week below `trust_invest=0.05` alone (**€+303.46 ± 134.52, t = 2.26**), and `drive_price_slope=0.05` loses **€-168.83 ± 490.08** on smoke due to global multiplier feedback.
