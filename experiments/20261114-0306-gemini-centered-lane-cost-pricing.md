# n14-02461-centered-lane-cost-pricing: Zero-mean destination-supply tilt (`lane_dest_tilt`) and centered cost-ratio slope (`cost_ratio_slope`) on top of `n14-02114`

- **Agent / branch / commit:** gemini · `exp/gemini-n14-02461-centered-lane-cost-pricing` · `6e02bf5` (merged `origin/exp/gemini-n14-02114-stack-gates-trust-notes`)
- **Date:** 2026-11-14 03:06
- **Idea from:** Margin X-Ray Leak #1 (`n14-01392-margin-xray-v2`, Section 2C) & refinement of `n14-01151-lane-return-pricing` on top of `origin/exp/gemini-n14-02114-stack-gates-trust-notes`

## Why we tried it
In `n14-01392-margin-xray-v2` (Section 2C and Leak #1), decomposing all 10,763 quotes across the 16 revealed dev worlds showed that the competitor's lane factor (`docs/GAME.md`: *"harder lanes: little return work, few drivers near the delivery"*) creates a 16-percentage-point win-rate split against our lane-blind multiplier `self.mult`:
- **Deliveries to thin towns (`deliv_supply < 30`, `337.4 quotes/wk`, no return work):** Our normal win rate is **43.6%** (40.1% overall) because the competitor prices thin-destination lanes ~8% higher while we do not.
- **Deliveries to dense hubs (`deliv_supply >= 100`, `204.6 quotes/wk`, easy return work) and low `referenceFeeCents / listPriceCents` lanes:** Our normal win rate is only **27.1%** (24.7% overall; and just **19%–23%** on `<100m` `next_day` in mid/ring towns), leaving over 100 safe return/short-haul orders/wk on the table.
- Earlier tonight, `n14-01151-lane-return-pricing` (`dest_thin_markup=0.06, dest_hub_discount=0.03`) achieved a near-miss `Δmargin €+194.99 ± 185.10 (t = 1.05)` on raw v2 because (1) it was uncentered (`337.4 quotes/wk` at `+6%` vs `204.6 quotes/wk` at `-3%` shifted the mean quote multiplier up by `+1.4%`, causing extra losses that stepped down `self.mult` via `Desk.learn()`), and (2) under a fixed count-based `price_target_win`, winning extra small short-haul hub-delivery orders crowds out larger orders 1-for-1 in `Desk.learn()` unless paired with a slightly higher `price_target_win` (`0.38 → 0.40`) to absorb the safe hub-bound volume.

## What changed
Merged `origin/exp/gemini-n14-02114-stack-gates-trust-notes` and added two `Params` fields in `src/spread_lab/policy.py` (defaults `0.0` reproduce `n14-02114` / Champion v2 identically):
- `lane_dest_tilt: float = 0.0` — zero-mean destination supply adjustment in `Desk.price()`:
  - Let `deliv_supply = self.supply.get(legs[-1]["delivery"]["placeId"], 0)`.
  - If `deliv_supply < 30`: multiply `option_mult` by `1.0 + p.lane_dest_tilt` (`self.stats["lane_thin_dest"] += 1`).
  - Else if `deliv_supply >= 100`: multiply `option_mult` by `1.0 - 1.5 * p.lane_dest_tilt` (`self.stats["lane_hub_dest"] += 1`).
- `cost_ratio_slope: float = 0.0` — centered cost-ratio slope in `Desk.price()` for each option:
  - Let `cost_ratio = request["referenceFeeCents"] / option["listPriceCents"]`.
  - Multiply `option_mult` by `clamp(1.0 + p.cost_ratio_slope * (cost_ratio - 0.91), 0.93, 1.07)`.
- Added `won_lane_thin_dest` and `won_lane_hub_dest` counters in `Desk.win()`.

Run commands (building on `n14-02114` Run 3):
- **Dev Run 1 (`lane-cost-gtn-dev`, `lane_dest_tilt=0.035, price_target_win=0.38`):**
  ```sh
  uv run lab eval -s trust_invest=0.05 -s notes_v2=True -s note_unsure=decline -s max_next_day_drive_min=480 -s fri_same_day_max_drive=100 -s thin_long_next_day_supply=50 -s ring_to_hub_same_day_min=60 -s same_day_min_supply=50 -s min_slack_min=150 -s slack_per_drive=0.75 -s price_target_win=0.38 -s min_supply=25 -s lane_dest_tilt=0.035 --name lane-cost-gtn-dev
  ```
- **Dev Run 2 (`lane-cost-gtn-v2-dev`, `lane_dest_tilt=0.035, price_target_win=0.40`):**
  ```sh
  uv run lab eval -s trust_invest=0.05 -s notes_v2=True -s note_unsure=decline -s max_next_day_drive_min=480 -s fri_same_day_max_drive=100 -s thin_long_next_day_supply=50 -s ring_to_hub_same_day_min=60 -s same_day_min_supply=50 -s min_slack_min=150 -s slack_per_drive=0.75 -s price_target_win=0.40 -s min_supply=25 -s lane_dest_tilt=0.035 --name lane-cost-gtn-v2-dev
  ```
- **Dev Run 3 (`lane-cost-gtn-v3-dev`, `lane_dest_tilt=0.045, price_target_win=0.40`):**
  ```sh
  uv run lab eval -s trust_invest=0.05 -s notes_v2=True -s note_unsure=decline -s max_next_day_drive_min=480 -s fri_same_day_max_drive=100 -s thin_long_next_day_supply=50 -s ring_to_hub_same_day_min=60 -s same_day_min_supply=50 -s min_slack_min=150 -s slack_per_drive=0.75 -s price_target_win=0.40 -s min_supply=25 -s lane_dest_tilt=0.045 --name lane-cost-gtn-v3-dev
  ```

## Results (level 8, vs champion v2, paired)
| set | run folder | mean margin | Δmargin ± SE | t | better/worse | on-time min (mean, Δ) | SAFE |
|---|---|---:|---:|---:|---:|---:|---|
| smoke (noop) | `runs/20261114-025348-lane-cost-noop` | €9,662.25 | €+0.00 ± 0.00 | — | 0 / 0 | 95.5% (96.7%, +0.00%) | yes |
| smoke 1 (`tilt=0.035, ptw=0.38`) | `runs/20261114-025444-lane-cost-smoke1` | €10,654.25 | €+992.00 ± 498.97 | 1.99 | 4 / 0 | 96.4% (97.5%, +0.82%) | yes |
| smoke 2 (`slope=0.20, ptw=0.38`) | `runs/20261114-025521-lane-cost-smoke2` | €10,362.25 | €+700.00 ± 609.08 | 1.15 | 3 / 1 | 96.0% (97.7%, +0.98%) | yes |
| smoke 3 (`tilt=0.03, slope=0.15`) | `runs/20261114-025552-lane-cost-smoke3` | €10,545.26 | €+883.01 ± 623.05 | 1.42 | 3 / 1 | 95.9% (97.0%, +0.34%) | yes |
| smoke 4 (`tilt=0.025, ptw=0.38`) | `runs/20261114-025614-lane-cost-smoke4` | €10,561.71 | €+899.46 ± 733.21 | 1.23 | 3 / 1 | 95.5% (97.6%, +0.88%) | yes |
| smoke 5 (`tilt=0.045, ptw=0.38`) | `runs/20261114-025634-lane-cost-smoke5` | €10,830.37 | €+1,168.13 ± 411.08 | 2.84 | 4 / 0 | 97.1% (97.8%, +1.10%) | yes |
| smoke 6 (`tilt=0.035, ptw=0.40`) | `runs/20261114-030119-lane-cost-smoke6` | **€10,992.58** | **€+1,330.33 ± 534.03** | **2.49** | **4 / 0** | **96.8% (97.6%, +0.89%)** | **yes** |
| **dev Run 1 (`lane-cost-gtn-dev`)** | `runs/20261114-025753-lane-cost-gtn-dev` | **€9,923.80** | **€+933.49 ± 212.39** | **4.40** | **15 / 1** | **95.3% (97.4%, +0.62%)** | **yes** |
| **dev Run 2 (`lane-cost-gtn-v2-dev`)** | `runs/20261114-030249-lane-cost-gtn-v2-dev` | **€10,262.15** | **€+1,271.84 ± 217.21** | **5.86** | **15 / 1** | **95.3% (97.5%, +0.80%)** | **yes** |
| **dev Run 3 (`lane-cost-gtn-v3-dev`)** | `runs/20261114-030504-lane-cost-gtn-v3-dev` | **€10,118.99** | **€+1,128.69 ± 237.81** | **4.75** | **14 / 2** | **95.4% (97.6%, +0.86%)** | **yes** |

### Direct paired comparisons (`uv run lab compare`) on 16 dev seeds
| Comparison (`B` vs `A`) | Mean Margin `B` vs `A` | Paired `Δmargin ± SE` | `t` | Better / Worse | `Δon-time` (Min `B` vs `A`) |
|---|---:|---:|---:|---:|---:|
| `lane-cost-gtn-dev` vs Champion v2 | €9,923.80 vs €8,990.31 | **€+933.49 ± 212.39** | **4.40** | **15 / 1** | **+0.62%** (**95.3%** vs 94.4%) |
| `lane-cost-gtn-v2-dev` vs Champion v2 | **€10,262.15** vs €8,990.31 | **€+1,271.84 ± 217.21** | **5.86** | **15 / 1** | **+0.80%** (**95.3%** vs 94.4%) |
| `lane-cost-gtn-v3-dev` vs Champion v2 | €10,118.99 vs €8,990.31 | **€+1,128.69 ± 237.81** | **4.75** | **14 / 2** | **+0.86%** (**95.4%** vs 94.4%) |
| **`lane-cost-gtn-v2-dev` vs `stack-gtn-ptw38-dev`** | **€10,262.15** vs €10,029.58 | **€+232.56 ± 113.31** | **2.05** | **10 / 6** | **+0.23%** (**95.3%** vs 94.3%) |
| `lane-cost-gtn-v3-dev` vs `stack-gtn-ptw38-dev` | €10,118.99 vs €10,029.58 | €+89.41 ± 148.71 | 0.60 | 9 / 7 | +0.29% (**95.4%** vs 94.3%) |
| `lane-cost-gtn-v2-dev` vs `lane-cost-gtn-dev` | **€10,262.15** vs €9,923.80 | **€+338.35 ± 122.05** | **2.77** | **12 / 4** | **+0.18%** (**95.3%** vs 95.3%) |

### Detailed stats counters and ledger breakdown on dev (16 worlds total / mean per world)
| Metric / Counter | Champion v2 | `stack-gtn-ptw38-dev` | `lane-cost-gtn-dev` (`tilt=0.035, ptw=0.38`) | **`lane-cost-gtn-v2-dev` (`tilt=0.035, ptw=0.40`)** | `lane-cost-gtn-v3-dev` (`tilt=0.045, ptw=0.40`) |
|---|---:|---:|---:|---:|---:|
| **Mean margin (€/world)** | €8,990.31 | €10,029.58 | €9,923.80 | **€10,262.15** | €10,118.99 |
| **Worst-seed margin (€)** | €6,017.30 | €7,078.06 | €7,194.90 | **€7,743.73** | €6,810.99 |
| **On-time min / mean (%)** | 94.36% / 96.75% | 94.26% / 97.32% | 95.31% / 97.36% | **95.32% / 97.54%** | **95.39% / 97.61%** |
| Active won orders (`won` /w) | 3,644 (227.75/w) | 4,096 (256.00/w) | 4,074 (254.62/w) | **4,218 (263.62/w)** | **4,237 (264.81/w)** |
| Total `stats["won"]` (total /w) | 3,682 (230.12/w) | 4,135 (258.44/w) | 4,116 (257.25/w) | **4,263 (266.44/w)** | **4,283 (267.69/w)** |
| **Total late orders (late %)** | 118 (7.38/w, 3.24%) | 112 (7.00/w, 2.73%) | 108 (6.75/w, 2.65%) | **104 (6.50/w, 2.47%)** | **101 (6.31/w, 2.38%)** |
| `won_same_day` (total /w) | 1,147 (71.69/w) | 1,606 (100.38/w) | 1,639 (102.44/w) | **1,710 (106.88/w)** | 1,746 (109.12/w) |
| `won_next_day` (total /w) | 2,362 (147.62/w) | 2,340 (146.25/w) | 2,286 (142.88/w) | **2,365 (147.81/w)** | 2,350 (146.88/w) |
| `won_within_3_days` (total /w) | 173 (10.81/w) | 189 (11.81/w) | 191 (11.94/w) | 188 (11.75/w) | 187 (11.69/w) |
| `won_ring` (total /w) | 823 (51.44/w) | 1,003 (62.69/w) | 1,072 (67.00/w) | **1,095 (68.44/w)** | **1,120 (70.00/w)** |
| `quoted_ring_hub_same_day` | 0 (0.00/w) | 654 (40.88/w) | 654 (40.88/w) | 654 (40.88/w) | 654 (40.88/w) |
| **`won_ring_hub_same_day`** | 0 (0.00/w) | 214 (13.38/w) | **289 (18.06/w)** | **298 (18.62/w)** | **330 (20.62/w)** |
| `late_ring_hub_same_day` (late %) | 0 (0.00/w) | 5 (2.34%) | 6 (2.08%) | **7 (2.35%)** | **4 (1.21%)** |
| `lane_thin_dest` (options /w) | 0 (0.00/w) | 0 (0.00/w) | 7,913 (494.56/w) | **7,889 (493.06/w)** | 7,923 (495.19/w) |
| `lane_hub_dest` (options /w) | 0 (0.00/w) | 0 (0.00/w) | 5,790 (361.88/w) | **5,781 (361.31/w)** | 5,790 (361.88/w) |
| `won_lane_thin_dest` (orders /w) | — | — | 1,950 (121.88/w) | **2,035 (127.19/w)** | 1,948 (121.75/w) |
| `won_lane_hub_dest` (orders /w) | — | — | 1,415 (88.44/w) | **1,462 (91.38/w)** | 1,555 (97.19/w) |
| **Ring margin (€/world)** | €2,114.01 | €2,333.92 | €2,399.26 | **€2,527.26 (+€413/w)** | €2,425.12 |
| `deadline_close` warnings | 193 (12.06/w) | 225 (14.06/w) | 234 (14.62/w) | **216 (13.50/w)** | 247 (15.44/w) |
| `visit_failed` (total /w) | 73 (4.56/w) | 3 (0.19/w) | 9 (0.56/w) | **6 (0.38/w)** | 5 (0.31/w) |
| Ledger `revenue` (€/world) | +26,922.43 | +28,082.93 | +27,292.95 | **+27,918.23** | +27,706.47 |
| Ledger `driver_fee` (€/world) | -17,286.92 | -17,673.60 | **-16,982.39** | **-17,318.15** | -17,227.64 |
| Ledger `late_refund` (€/world) | -376.20 | -288.22 | -244.41 | **-232.12 (-38.3%)** | **-226.79 (-39.7%)** |
| Ledger `failed_visit` (€/world) | -165.44 | -6.68 | -20.12 | **-14.12** | -11.79 |

### Key Mechanism Insights
1. **Why `lane_dest_tilt=0.035` needed `price_target_win=0.40` to unlock its full euro value (`+€338.35/w, t=2.77`):**
   - At fixed `price_target_win=0.38` (`lane-cost-gtn-dev`), discounting dense-hub deliveries (`deliv_supply >= 100`) by `-5.25%` (`-1.5 * 0.035`) and marking up thin-town deliveries (`deliv_supply < 30`) by `+3.5%` jumped `won_ring_hub_same_day` by **+35% (`214 → 289` orders, `13.38/w → 18.06/w`)**, lifted worst-seed on-time by **+1.05% (`94.26% → 95.31%`)**, and cut `driver_fee` by **€691.21/w** and `late_refund` by **€43.81/w**. However, because `Desk.learn()` counts every won order equally (`+1` regardless of euro size), winning `+4.7/w` extra small short-haul hub orders caused `Desk.learn()` to step up `self.mult` and crowd out `5.9/w` larger medium-drive orders (`won` stayed flat at `254.6/w` vs `256.0/w`, reducing revenue by `€790/w`).
   - Raising `price_target_win` from `0.38` to `0.40` (`lane-cost-gtn-v2-dev`) absorbs those extra `+7.62/w` safe hub-delivery orders **without** crowding out normal orders (`won_next_day` recovers from `142.88/w` to `147.81/w`, while `won_same_day` rises to `106.88/w` and `won_ring_hub_same_day` reaches `18.62/w`).
2. **Simultaneous improvement in both margin (`+€232.56 ± 113.31, t=2.05`) and safety (`+0.23%` mean on-time, `+1.06%` worst-seed on-time) over `stack-gtn-ptw38-dev`:**
   - Even with `price_target_win=0.40` winning **263.62 active orders/week** (`+35.87/w` over Champion v2, `+7.62/w` over `stack-gtn-ptw38-dev`), total late orders across all 16 dev worlds **drop from 112 (`stack-gtn-ptw38-dev`) to 104 (`2.47%` late rate)**, `deadline_close` warnings drop from `225` to `216`, `late_refund` drops from `-€288.22/w` to `-€232.12/w`, and **worst-seed on-time rises from `94.26%` to `95.32%`**.
3. **Why `cost_ratio_slope=0.20` underperformed `lane_dest_tilt=0.035` on smoke:**
   - On smoke, `cost_ratio_slope=0.20` achieved `€10,362.25` (vs `€10,654.25` for `lane_dest_tilt=0.035`), because `referenceFeeCents / listPriceCents` is higher on slower options (`within_3_days` has `list ≈ 0.86 × same_day` for the same `referenceFeeCents`, so `cost_ratio` is `~1.03` on `within_3_days` vs `~0.83` on `same_day`), inadvertently discounting `same_day` relative to `next_day`/`within_3_days`. By contrast, `lane_dest_tilt` depends purely on `deliv_supply`, tilting all options on the request uniformly toward return-rich hubs.

## Verdict
**adopt** — `lane-cost-gtn-v2-dev` (`lane_dest_tilt=0.035, price_target_win=0.40` on top of the `n14-02114` stack) reaches **€10,262.15 mean margin** on 16 dev seeds (`Δmargin €+1,271.84 ± 217.21, t = 5.86, 15/1 seeds better` vs Champion v2; `Δmargin €+232.56 ± 113.31, t = 2.05, 10/6 seeds better` vs `stack-gtn-ptw38-dev`), while simultaneously lifting worst-seed on-time from `94.3%` to **`95.3%`** (`97.5%` mean on-time, SAFE) and worst-seed margin from `€7,078.06` to **`€7,743.73`**.
