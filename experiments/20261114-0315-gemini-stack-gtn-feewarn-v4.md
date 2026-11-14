# n14-02463-stack-gtn-feewarn-v4: Combine €10,030/wk GTN stack with Sweep 25 (`min_slack_min=140, slack_per_drive=0.75, fee_warn=1.50, fee_step_min=20`) and `dealer_lr=0.01`

- **Agent / branch / commit:** gemini · `exp/gemini-n14-02463-stack-gtn-feewarn-v4` · see `git log -n 1`
- **Date:** 2026-11-14 03:15
- **Idea from:** Combination of `origin/exp/gemini-n14-02114-stack-gates-trust-notes` (`+€1,039.28 ± 229.22, t=4.53`) with Sweep 25 (`min_slack_min=140, slack_per_drive=0.75, fee_warn=1.50, fee_step_min=20`, `+€430 ± 170, t=2.5`) and `dealer_lr=0.01`

## Why we tried it
We have two major dev winners that improved completely orthogonal parts of the dispatcher:
1. **`origin/exp/gemini-n14-02114-stack-gates-trust-notes` (selection gates + dealer trust investment + v2 note reader):**
   - Run 2 (`stack-gtn-slack-sdsup-dev`: `trust_invest=0.05, notes_v2=True, note_unsure=decline, max_next_day_drive_min=480, fri_same_day_max_drive=100, thin_long_next_day_supply=50, ring_to_hub_same_day_min=60, same_day_min_supply=50, min_slack_min=150, slack_per_drive=0.75`) achieved **Δmargin €+823.72 ± 224.56 (`t = 3.67`, 13/16 better, worst on-time `94.6%` SAFE, mean margin `€9,814.02`)**, cutting late orders by 44% (`118 → 66`) and `visit_failed` by 97.3% (`73 → 2`).
   - Run 3 (`stack-gtn-ptw38-dev`: Run 2 + `price_target_win=0.38, min_supply=25`) achieved **Δmargin €+1,039.28 ± 229.22 (`t = 4.53`, 14/16 better, worst on-time `94.3%` SAFE, mean margin `€10,029.58`)**.
2. **Sweep `25 n-slack140-feewarn` (`min_slack_min=140, slack_per_drive=0.75, fee_warn=1.50, fee_step_min=20`):**
   - Lowering the pre-warning fee ceiling from `fee_warn=1.60` to `1.50` with finer `20`-minute daytime steps (`fee_step_min=20`) and `min_slack_min=140, slack_per_drive=0.75` achieved `+€430 ± 170 (t=2.5, 14/16 better)` on Champion v2 by reducing driver fee overpayment on routine daytime bookings while maintaining smooth fee progression.
   - Because `n14-02114` already eliminates the risky long-drive and note-shortened orders before posting, combining `fee_warn=1.50, fee_step_min=20, min_slack_min=140, slack_per_drive=0.75` with the full `n14-02114` stack should save over €300/wk in `driver_fee` at high volume (`price_target_win=0.38, min_supply=25`) without sacrificing on-time safety.

## What changed
Merged `origin/exp/gemini-n14-02114-stack-gates-trust-notes` into `exp/gemini-n14-02463-stack-gtn-feewarn-v4` and updated `src/spread_lab/policy.py`:
- Added optional `Params` field `multiday_fee_warn: float = 0.0` (default `0.0` reproduces Champion v2 and `n14-02114` 100% identically: `Δmargin €+0.00 ± 0.00` on smoke).
- In `Desk.rising(self, base: float, until: int)`: used `warn = p.multiday_fee_warn if (p.multiday_fee_warn > 0 and until // DAY > self.now // DAY) else p.fee_warn`.
- Added telemetry counters `booked_fee_cents_sum` and `booked_ref_fee_cents_sum` in `gig_booked` (and updated `self.posts[gig_id]["schedule"]` on `reprice` in `read_results`) to measure exact booked fee / reference fee ratios.

Run commands on dev:
- **Dev Run 1 (`stack-gtn-s140-fw150-dev`):**
  ```sh
  uv run lab eval -s trust_invest=0.05 -s notes_v2=True -s note_unsure=decline -s max_next_day_drive_min=480 -s fri_same_day_max_drive=100 -s thin_long_next_day_supply=50 -s ring_to_hub_same_day_min=60 -s same_day_min_supply=50 -s min_slack_min=140 -s slack_per_drive=0.75 -s fee_warn=1.50 -s fee_step_min=20 --name stack-gtn-s140-fw150-dev
  ```
- **Dev Run 2 (`stack-gtn-s140-fw150-ptw38-dev`):**
  ```sh
  uv run lab eval -s trust_invest=0.05 -s notes_v2=True -s note_unsure=decline -s max_next_day_drive_min=480 -s fri_same_day_max_drive=100 -s thin_long_next_day_supply=50 -s ring_to_hub_same_day_min=60 -s same_day_min_supply=50 -s min_slack_min=140 -s slack_per_drive=0.75 -s fee_warn=1.50 -s fee_step_min=20 -s price_target_win=0.38 -s min_supply=25 --name stack-gtn-s140-fw150-ptw38-dev
  ```
- **Dev Run 3 (`stack-gtn-s140-fw150-dlr01-dev`):**
  ```sh
  uv run lab eval -s trust_invest=0.05 -s notes_v2=True -s note_unsure=decline -s max_next_day_drive_min=480 -s fri_same_day_max_drive=100 -s thin_long_next_day_supply=50 -s ring_to_hub_same_day_min=60 -s same_day_min_supply=50 -s min_slack_min=140 -s slack_per_drive=0.75 -s fee_warn=1.50 -s fee_step_min=20 -s price_target_win=0.38 -s min_supply=25 -s dealer_lr=0.01 --name stack-gtn-s140-fw150-dlr01-dev
  ```
- **Dev Run 4 (`stack-gtn-v4-best-dev`):**
  ```sh
  uv run lab eval -s trust_invest=0.05 -s notes_v2=True -s note_unsure=decline -s max_next_day_drive_min=480 -s fri_same_day_max_drive=100 -s thin_long_next_day_supply=50 -s ring_to_hub_same_day_min=60 -s same_day_min_supply=50 -s min_slack_min=140 -s slack_per_drive=0.75 -s fee_warn=1.50 -s fee_step_min=20 -s price_target_win=0.38 -s min_supply=25 -s multiday_fee_warn=1.45 --name stack-gtn-v4-best-dev
  ```

## Results (level 8, vs champion v2, paired)
| set | run folder | mean margin | Δmargin ± SE | t | better/worse | on-time min (mean, Δ) | SAFE |
|---|---|---:|---:|---:|---:|---:|---|
| smoke (noop) | `runs/20261114-025916-gtn-fw-noop` | €9,662.25 | €+0.00 ± 0.00 | — | 0 / 0 | 95.5% (96.7%, +0.00%) | yes |
| smoke 1 (`s140+fw150`) | `runs/20261114-030018-gtn-fw-smoke1` | €10,649.84 | €+987.59 ± 473.45 | 2.09 | 4 / 0 | 96.2% (97.6%, +0.88%) | yes |
| smoke 2 (`+ptw38/ms25`) | `runs/20261114-030123-gtn-fw-smoke2` | €10,763.09 | €+1,100.85 ± 510.98 | 2.15 | 4 / 0 | 94.9% (96.7%, -0.03%) | yes |
| smoke 3 (`+dlr01`) | `runs/20261114-030216-gtn-fw-smoke3` | €10,591.62 | €+929.38 ± 438.44 | 2.12 | 3 / 1 | 96.0% (96.5%, -0.16%) | yes |
| smoke 4 (`+mdfw145`) | `runs/20261114-030508-gtn-fw-smoke4` | €10,868.37 | €+1,206.12 ± 453.30 | 2.66 | 4 / 0 | 94.2% (96.5%, -0.19%) | yes |
| **dev Run 1 (`stack-gtn-s140-fw150-dev`)** | `runs/20261114-030654-stack-gtn-s140-fw150-dev` | **€9,911.44** | **€+921.14 ± 218.45** | **4.22** | **15 / 1** | **93.4% (97.8%, +1.05%)** | **yes** |
| **dev Run 2 (`stack-gtn-s140-fw150-ptw38-dev`)** | `runs/20261114-030811-stack-gtn-s140-fw150-ptw38-dev` | **€10,167.52** | **€+1,177.22 ± 226.75** | **5.19** | **15 / 1** | **94.1% (97.2%, +0.48%)** | **yes** |
| **dev Run 3 (`stack-gtn-s140-fw150-dlr01-dev`)** | `runs/20261114-031027-stack-gtn-s140-fw150-dlr01-dev` | **€10,161.80** | **€+1,171.49 ± 239.53** | **4.89** | **13 / 3** | **93.6% (97.3%, +0.54%)** | **yes** |
| **dev Run 4 (`stack-gtn-v4-best-dev`, `mdfw145`)** | `runs/20261114-031337-stack-gtn-v4-best-dev` | **€10,142.58** | **€+1,152.28 ± 228.03** | **5.05** | **13 / 3** | **93.6% (97.0%, +0.27%)** | **yes** |

### Paired comparisons against `n14-02114` dev runs (16 seeds)
| Comparison | Paired Δmargin ± SE | t | better / worse | Paired Δon-time |
|---|---:|---:|---:|---:|
| **Dev Run 1 (`stack-gtn-s140-fw150-dev`) vs `stack-gtn-slack-sdsup-dev` (`n14-02114` Run 2)** | **€+97.42 ± 82.66** | **1.18** | **10 / 6** | -0.47% |
| **Dev Run 2 (`stack-gtn-s140-fw150-ptw38-dev`) vs `stack-gtn-ptw38-dev` (`n14-02114` Run 3)** | **€+137.94 ± 116.06** | **1.19** | **12 / 4** | -0.09% |
| **Dev Run 3 (`stack-gtn-s140-fw150-dlr01-dev`) vs `stack-gtn-ptw38-dev` (`n14-02114` Run 3)** | **€+132.22 ± 178.47** | 0.74 | 8 / 8 | -0.03% |
| **Dev Run 4 (`stack-gtn-v4-best-dev`) vs `stack-gtn-ptw38-dev` (`n14-02114` Run 3)** | **€+113.00 ± 130.27** | 0.87 | 8 / 8 | -0.30% |
| **Dev Run 2 (`+ptw38/ms25`) vs Dev Run 1 (`stack-gtn-s140-fw150-dev`)** | **€+256.08 ± 128.71** | **1.99** | **10 / 6** | -0.57% |
| **Dev Run 3 (`+dlr01`) vs Dev Run 2 (`stack-gtn-s140-fw150-ptw38-dev`)** | €-5.73 ± 170.48 | -0.03 | 7 / 9 | +0.06% |
| **Dev Run 4 (`+mdfw145`) vs Dev Run 2 (`stack-gtn-s140-fw150-ptw38-dev`)** | €-24.94 ± 85.40 | -0.29 | 7 / 9 | -0.21% |

### Detailed stats counters and ledger breakdown on dev (16 worlds total / mean per world)
| Metric / Counter | Champion v2 | `n14-02114` Run 2 (`slack150`) | `n14-02114` Run 3 (`+ptw38`) | **Dev Run 1 (`s140+fw150`)** | **Dev Run 2 (`s140+fw150+ptw38`)** | **Dev Run 3 (`+dlr01`)** | **Dev Run 4 (`+mdfw145`)** |
|---|---:|---:|---:|---:|---:|---:|---:|
| **Mean margin (€/w)** | €8,990.31 | €9,814.02 | €10,029.58 | **€9,911.44** | **€10,167.52** | **€10,161.80** | **€10,142.58** |
| **Median margin (€/w)** | €8,685.06 | €9,252.71 | €9,308.37 | **€9,510.40** | **€9,841.70** | €9,307.87 | €9,794.95 |
| **Min (worst-seed) margin** | €6,017.30 | €6,885.73 | €7,078.06 | **€7,142.81** | **€7,158.70** | **€7,619.25** | €7,019.44 |
| Active won orders (total / /w) | 3,644 (227.75/w) | 3,737 (233.56/w) | 4,096 (256.00/w) | 3,720 (232.50/w) | **4,073 (254.56/w)** | **4,126 (257.88/w)** | 4,088 (255.50/w) |
| **Total late orders (late %)** | 118 (7.38/w, 3.24%) | 66 (4.12/w, 1.77%) | 112 (7.00/w, 2.73%) | **83 (5.19/w, 2.23%)** | **114 (7.12/w, 2.80%)** | 115 (7.19/w, 2.79%) | 124 (7.75/w, 3.03%) |
| `won_same_day` (total) | 1,147 | 1,443 | 1,606 | 1,440 | 1,619 | 1,604 | 1,619 |
| `won_next_day` (total) | 2,362 | 2,159 | 2,340 | 2,137 | 2,310 | 2,375 | 2,321 |
| `won_within_3_days` (total) | 173 | 175 | 189 | 183 | 184 | 186 | 191 |
| `won_ring_hub_same_day` / late | 0 / 0 | 194 / 1 | 214 / 5 | 199 / 3 | 212 / 9 | 216 / 4 | 216 / 7 |
| **`visit_failed` (total)** | **73** | **2** | **3** | **1** | **1** | 12 | 7 |
| `deadline_close` warnings | 193 | 146 | 225 | 159 | 230 | 260 | 261 |
| `gig_expired` | 121 | 67 | 104 | 79 | 107 | 121 | 123 |
| `gig_dropped` | 487 | 430 | 519 | 442 | 537 | 506 | 510 |
| `booked_fee / ref_fee` | — | — | — | 0.9888 | 1.0028 | 1.0063 | 1.0006 |
| Ring margin (€/world) | €2,114.01 | €2,446.34 | €2,333.92 | **€2,494.12** | **€2,361.92** | **€2,404.24** | €2,333.17 |
| **Ledger `revenue` (€/w)** | +26,922.43 | +25,926.69 | +28,082.93 | +25,948.97 | **+27,858.73** | **+28,292.91** | +27,931.70 |
| **Ledger `driver_fee` (€/w)** | -17,286.93 | -15,861.10 | -17,673.60 | **-15,752.84** | **-17,349.33** | -17,682.68 | -17,366.66 |
| **Ledger `late_refund` (€/w)** | -376.20 | -174.84 | -288.22 | -206.10 | **-251.72** | -288.53 | -313.26 |
| **Ledger `failed_visit` (€/w)** | -165.44 | -3.33 | -6.68 | **-1.56** | **-3.56** | -33.49 | -19.82 |
| **Ledger `release_fee` (€/w)** | -53.48 | -36.57 | -50.20 | **-34.41** | **-45.71** | -42.78 | -43.58 |
| **Ledger `waiting` (€/w)** | -39.38 | -26.52 | -24.38 | -26.25 | -26.25 | -24.38 | -30.00 |

### Key findings
1. **New all-time dev high (`stack-gtn-s140-fw150-ptw38-dev`):** Combining the `n14-02114` stack (`trust_invest=0.05, notes_v2=True, note_unsure=decline, max_next_day_drive_min=480, fri_same_day_max_drive=100, thin_long_next_day_supply=50, ring_to_hub_same_day_min=60, same_day_min_supply=50, price_target_win=0.38, min_supply=25`) with `min_slack_min=140, slack_per_drive=0.75, fee_warn=1.50, fee_step_min=20` reaches **`€10,167.52` mean margin (`median €9,841.70, min €7,158.70`)** — beating Champion v2 by **`Δmargin €+1,177.22 ± 226.75` (`t = 5.19`, 15/16 seeds better, worst on-time `94.1%` SAFE, mean on-time `97.2%`, `Δon-time +0.48%`)** and beating `n14-02114` Run 3 (`stack-gtn-ptw38-dev`) on **12 of 16 seeds by `€+137.94 ± 116.06` (`t = 1.19`)** while raising median margin by **`+€533.33/wk`** (`€9,308.37 → €9,841.70`).
2. **Driver fee and late refund both drop vs `stack-gtn-ptw38-dev`:** Compared to `n14-02114` Run 3 (`stack-gtn-ptw38-dev`), `stack-gtn-s140-fw150-ptw38-dev` cuts `driver_fee` by **`-€324.27/world`** (`-€17,673.60/w → -€17,349.33/w`), cuts `late_refund` by **`-€36.50/world`** (`-€288.22/w → -€251.72/w`), and reduces `visit_failed` to **1 across all 16 worlds** (`-€3.56/w`, a **98.6% reduction** vs Champion v2's `73` failed visits).
3. **Conservative `price_target_win=0.35` variant (`stack-gtn-s140-fw150-dev`) also improves to 15/16 seeds:** Without `price_target_win=0.38, min_supply=25`, `stack-gtn-s140-fw150-dev` reaches **`€9,911.44` mean margin (`Δmargin €+921.14 ± 218.45, t=4.22, 15/16 better`, worst on-time `93.4%`, mean on-time `97.8%`)**, improving over `stack-gtn-slack-sdsup-dev` by **`€+97.42 ± 82.66` (10/6 better)**.
4. **`dealer_lr=0.01` (`stack-gtn-s140-fw150-dlr01-dev`) and `multiday_fee_warn=1.45` (`stack-gtn-v4-best-dev`):** Both are strong (`+€1,171.49 ± 239.53, t=4.89` and `+€1,152.28 ± 228.03, t=5.05`, both 13/3 better vs Champion v2), with `dealer_lr=0.01` achieving the highest worst-seed margin (`€7,619.25`), but neither beats `stack-gtn-s140-fw150-ptw38-dev` (`€10,167.52`, `t=5.19`, `15/1` better, `94.1%` min on-time) on mean/median margin or seed win consistency.

## Verdict
**adopt `stack-gtn-s140-fw150-ptw38-dev`** — Achieves **`€10,167.52` mean margin (`Δmargin €+1,177.22 ± 226.75`, `t = 5.19`, 15/16 seeds better vs Champion v2; `€+137.94 ± 116.06`, 12/16 seeds better vs `stack-gtn-ptw38-dev`)** with **94.1% worst-seed on-time (97.2% mean, SAFE)**, 114 total late orders (vs 118 in Champion v2), and only 1 `visit_failed` across 16 worlds.
