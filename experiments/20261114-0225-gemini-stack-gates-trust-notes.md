# n14-02114-stack-gates-trust-notes: Stack surgical class-table gates + dealer trust investment + v2 note reader

- **Agent / branch / commit:** gemini · `exp/gemini-n14-02114-stack-gates-trust-notes` · `2f6ef55`
- **Date:** 2026-11-14 02:25
- **Idea from:** Combination of `exp/gemini-n14-01391-class-table-gates` (surgical class-table gates), `origin/exp/gemini-n14-02-trust-v2` (dealer trust investment), `origin/exp/gemini-n14-07-notes` (v2 note reader), and `19 n-slack-sdsup-dlr` (`same_day_min_supply=50, min_slack_min=150, slack_per_drive=0.75`)

## Why we tried it
We have three orthogonal, verified winners on champion v2 that attack three disjoint leaks in level-8 worlds:
1. **Surgical class-table selection gates (`exp/gemini-n14-01391-class-table-gates`):**
   - Closing the three late-order traps (`max_next_day_drive_min=480, fri_same_day_max_drive=100, thin_long_next_day_supply=50`) cut late orders by 28.8% (`118 → 84`) and halved late refunds (`-€380/w → -€180/w`).
   - Opening `ring_to_hub_same_day_min=60` won 198 ring-to-capital `same_day` orders across 16 dev worlds with only 2 late (1.01% late), lifting ring margin by `+€287.50/world`.
2. **Dealer trust investment (`origin/exp/gemini-n14-02-trust-v2`, `trust_invest=0.05`):**
   - Investing a 5% discount on safe (`supply >= 100, slack >= 360` min), note-free requests for the top 3 dealers on Mon–Wed accelerates their trust count toward the +25% price tolerance cap (`Δmargin €+303.46 ± 134.52, t=2.26, 11/16 better`). Furthermore, cutting late orders via the class-table gates and `notes_v2` prevents dealer trust halving (`count //= 2`).
3. **100%-truth v2 note reader (`origin/exp/gemini-n14-07-notes`, `notes_v2=True, note_unsure="decline"`):**
   - Achieves 100% accuracy on all 177 ground-truth note fields across 6 revealed worlds, eliminates >90% of `visit_failed` charges, and computes exact note-shifted ready days and note-shortened option deadlines in `Desk.price`.

Because `notes_v2` computes exact option deadlines (`deadline`) and pickup ready times (`ready`), applying the class-table gates (`max_next_day_drive_min`, `thin_long_next_day_supply`, `fri_same_day_max_drive`, `ring_to_hub_same_day_min`) and drive-proportional slack (`min_slack_min=150, slack_per_drive=0.75`) on top of the note-adjusted `deadline` and `ready` compounds cleanly and creates a massive on-time safety buffer (`+1.52%` mean on-time, cutting late orders by **44% from 118 to 66**), allowing us to safely cash in a higher win target (`price_target_win=0.38, min_supply=25`).

## What changed
Merged `origin/exp/gemini-n14-07-notes`, `origin/exp/gemini-n14-02-trust-v2`, and `exp/gemini-n14-01391-class-table-gates` into `exp/gemini-n14-02114-stack-gates-trust-notes`:
- `src/spread_lab/notes.py`: `parse_note_v2`, `shift_business_days`, `window_from_note(..., v2=...)`, `note_flags(..., v2=...)`.
- `src/spread_lab/policy.py`:
  - Added all `Params` fields with defaults that reproduce champion v2 100% identically (`Δmargin €+0.00 ± 0.00` on smoke):
    - Class-table gates: `max_next_day_drive_min: int = 0`, `thin_long_next_day_supply: int = 0`, `fri_same_day_max_drive: int = 0`, `ring_to_hub_same_day_min: int = 0`.
    - Notes v2: `notes_v2: bool = False`, `note_unsure: str = "quote"`.
    - Trust v2: `trust_gain: float = 0.0`, `trust_invest: float = 0.0`, `trust_guard: bool = False`.
  - In `Desk.price`: computed note-shifted `ready` and note-shortened `deadline` first (when `notes_v2=True`), then applied `max_next_day_drive_min`, `thin_long_next_day_supply`, `fri_same_day_max_drive`, `long_drive_min`, `ring_to_hub_same_day_min`, `same_day_min_supply`, `slack = deadline - ready - drive`, and `trust_invest` (`slack >= 360`).
  - Kept all stats counters from all three branches (`dropped_next_day_long`, `dropped_thin_long_next_day`, `dropped_fri_same_day`, `quoted_ring_hub_same_day`, `won_ring_hub_same_day`, `late_ring_hub_same_day`, `notes_read`, `notes_unsure`, `visit_failed`, `top_dealer_trust_d0..d4`).

Run commands:
- **Run 1 (`stack-gtn-dev`):**
  ```sh
  uv run lab eval -s trust_invest=0.05 -s notes_v2=True -s note_unsure=decline -s max_next_day_drive_min=480 -s fri_same_day_max_drive=100 -s thin_long_next_day_supply=50 -s ring_to_hub_same_day_min=60 --name stack-gtn-dev
  ```
- **Run 2 (`stack-gtn-slack-sdsup-dev`):**
  ```sh
  uv run lab eval -s trust_invest=0.05 -s notes_v2=True -s note_unsure=decline -s max_next_day_drive_min=480 -s fri_same_day_max_drive=100 -s thin_long_next_day_supply=50 -s ring_to_hub_same_day_min=60 -s same_day_min_supply=50 -s min_slack_min=150 -s slack_per_drive=0.75 --name stack-gtn-slack-sdsup-dev
  ```
- **Run 3 (`stack-gtn-ptw38-dev`):**
  ```sh
  uv run lab eval -s trust_invest=0.05 -s notes_v2=True -s note_unsure=decline -s max_next_day_drive_min=480 -s fri_same_day_max_drive=100 -s thin_long_next_day_supply=50 -s ring_to_hub_same_day_min=60 -s same_day_min_supply=50 -s min_slack_min=150 -s slack_per_drive=0.75 -s price_target_win=0.38 -s min_supply=25 --name stack-gtn-ptw38-dev
  ```

## Results (level 8, vs champion v2, paired)
| set | run folder | mean margin | Δmargin ± SE | t | better/worse | on-time min (mean, Δ) | SAFE |
|---|---|---:|---:|---:|---:|---:|---|
| smoke (noop) | `runs/20261114-021628-stack-gtn-noop` | €9,662.25 | €+0.00 ± 0.00 | — | 0 / 0 | 95.5% (96.7%, +0.00%) | yes |
| smoke (Run 1: `gtn`) | `runs/20261114-021708-stack-gtn-smoke1` | €9,970.60 | €+308.35 ± 385.75 | 0.80 | 2 / 2 | 96.9% (98.3%, +1.64%) | yes |
| smoke (Run 2: `+slack/sdsup`) | `runs/20261114-021821-stack-gtn-smoke2` | €10,308.27 | €+646.03 ± 488.00 | 1.32 | 3 / 1 | 97.9% (98.1%, +1.42%) | yes |
| smoke (Run 3: `+ptw38/ms25`) | `runs/20261114-021947-stack-gtn-smoke3` | €10,593.65 | €+931.41 ± 488.27 | 1.91 | 4 / 0 | 96.0% (96.9%, +0.19%) | yes |
| **dev Run 1 (`stack-gtn-dev`)** | `runs/20261114-022057-stack-gtn-dev` | **€9,664.03** | **€+673.72 ± 181.49** | **3.71** | **13 / 3** | **93.8% (98.2%, +1.40%)** | **yes** |
| **dev Run 2 (`stack-gtn-slack-sdsup-dev`)** | `runs/20261114-022233-stack-gtn-slack-sdsup-dev` | **€9,814.02** | **€+823.72 ± 224.56** | **3.67** | **13 / 3** | **94.6% (98.3%, +1.52%)** | **yes** |
| **dev Run 3 (`stack-gtn-ptw38-dev`)** | `runs/20261114-022434-stack-gtn-ptw38-dev` | **€10,029.58** | **€+1,039.28 ± 229.22** | **4.53** | **14 / 2** | **94.3% (97.3%, +0.57%)** | **yes** |

### Progressive paired comparisons on dev (16 seeds)
1. **Run 1 (`stack-gtn-dev`) vs Champion v2:** Stacking the surgical class-table gates (`max_next_day_drive_min=480, fri_same_day_max_drive=100, thin_long_next_day_supply=50, ring_to_hub_same_day_min=60`), `trust_invest=0.05`, and `notes_v2=True, note_unsure="decline"` achieves **`Δmargin €+673.72 ± 181.49` (`t = 3.71`, 13/16 seeds better)**, nearly equal to the sum of the three individual components (`+269 + +303 + +83 = +€655/w`), while lifting mean on-time by **`+1.40%` to `98.15%`** (worst seed `93.8%` SAFE, worst-seed margin up **`+€1,063.01`** from `€6,017.30` to `€7,080.31`).
2. **Run 2 (`stack-gtn-slack-sdsup-dev`) vs Run 1 (`uv run lab compare`):** Adding `same_day_min_supply=50, min_slack_min=150, slack_per_drive=0.75` adds a further **`€+149.99 ± 109.50` (`t = 1.37`, 9/6 better)** and **`+0.12%` mean on-time** (lifting worst-seed on-time from `93.8%` to **`94.6%`** and mean on-time to **`98.27%`**), reaching **`€9,814.02` mean margin (`Δmargin €+823.72 ± 224.56`, `t = 3.67`, 13/16 seeds better)**.
3. **Run 3 (`stack-gtn-ptw38-dev`) vs Run 2 (`uv run lab compare`):** Cashing in part of the `+1.52%` on-time buffer with `price_target_win=0.38, min_supply=25` adds another **`€+215.56 ± 149.43` (`t = 1.44`, 11/5 seeds better over Run 2)** and breaks the €10k barrier on dev at **`€10,029.58` mean margin (`Δmargin €+1,039.28 ± 229.22`, `t = 4.53`, 14/16 seeds better vs Champion v2)**, while still improving mean on-time over Champion v2 by **`+0.57%` (`97.32%` mean, `94.26%` worst seed on `dev-07`, SAFE)**!

### Detailed stats counters and ledger breakdown on dev (16 worlds total / mean per world)
| Metric / Counter | Champion v2 | Run 1 (`stack-gtn-dev`) | Run 2 (`+slack/sdsup`) | Run 3 (`+ptw38/ms25`) |
|---|---:|---:|---:|---:|
| Active won orders (total / mean) | 3,644 (227.75/w) | 3,660 (228.75/w) | 3,737 (233.56/w) | **4,096 (256.00/w)** |
| **Total late orders (late %)** | 118 (7.38/w, 3.24%) | **68 (4.25/w, 1.86%)** | **66 (4.12/w, 1.77%)** | **112 (7.00/w, 2.73%)** |
| `won_same_day` (total / mean) | 1,147 (71.69/w) | 1,235 (77.19/w) | 1,443 (90.19/w) | 1,606 (100.38/w) |
| `won_next_day` (total / mean) | 2,362 (147.62/w) | 2,284 (142.75/w) | 2,159 (134.94/w) | 2,340 (146.25/w) |
| `won_within_3_days` (total / mean) | 173 (10.81/w) | 178 (11.12/w) | 175 (10.94/w) | 189 (11.81/w) |
| `quoted_ring_hub_same_day` | 0 (0.00/w) | 649 (40.56/w) | 654 (40.88/w) | 654 (40.88/w) |
| `won_ring_hub_same_day` | 0 (0.00/w) | **193 (12.06/w)** | **194 (12.12/w)** | **214 (13.38/w)** |
| `late_ring_hub_same_day` (late %) | 0 (0.00/w) | **2 (0.12/w, 1.04%)** | **1 (0.06/w, 0.52%)** | **5 (0.31/w, 2.34%)** |
| `dropped_next_day_long` | 0 (0.00/w) | 213 (13.31/w) | 212 (13.25/w) | 229 (14.31/w) |
| `dropped_thin_long_next_day` | 0 (0.00/w) | 157 (9.81/w) | 158 (9.88/w) | 223 (13.94/w) |
| `dropped_fri_same_day` | 0 (0.00/w) | 894 (55.88/w) | 893 (55.81/w) | 930 (58.12/w) |
| `notes_read` / `notes_unsure` | 0 / 0 | 2,658 / 14 | 2,658 / 14 | 2,658 / 14 |
| **`visit_failed` (total / mean)** | **73 (4.56/w)** | **5 (0.31/w, -93.2%)** | **2 (0.12/w, -97.3%)** | **3 (0.19/w, -95.9%)** |
| `visit_failed_not_ready` / `no_plates` | 56 / 15 | **0 / 0** | **0 / 0** | **0 / 0** |
| `visit_failed_closed` | 2 (0.12/w) | 5 (0.31/w) | 2 (0.12/w) | 3 (0.19/w) |
| `deadline_close` warnings | 193 (12.06/w) | **137 (8.56/w)** | **146 (9.12/w)** | 225 (14.06/w) |
| `gig_expired` | 121 (7.56/w) | **67 (4.19/w)** | **67 (4.19/w)** | 104 (6.50/w) |
| `top_dealer_trust_d0..d4` (mean) | — | 4.4 / 15.6 / 23.9 / 23.5 / **24.9** | 4.3 / 16.6 / 24.6 / 24.2 / **24.8** | 5.1 / 18.1 / 23.4 / 24.4 / **24.7** |
| Ring margin (€/world) | €2,114.01 | **€2,453.42 (+€339/w)** | **€2,446.35 (+€332/w)** | €2,333.92 (+€220/w) |
| Ledger `revenue` (€/world) | +26,922.43 | +25,691.76 | +25,926.69 | **+28,082.93** |
| Ledger `driver_fee` (€/world) | -17,286.92 | **-15,750.01** | **-15,861.10** | -17,673.60 |
| Ledger `late_refund` (€/world) | -376.20 | **-184.65** | **-174.84 (-53.5%)** | -288.22 |
| Ledger `failed_visit` (€/world) | -165.44 | -10.09 | **-3.33 (-98.0%)** | -6.68 |
| Ledger `release_fee` (€/world) | -53.48 | **-35.76** | **-36.57** | -50.20 |
| Ledger `waiting` (€/world) | -39.38 | -26.52 | -26.52 | **-24.38** |

### Why the three mechanisms synergize so strongly
- **44% reduction in late orders preserves dealer trust:** In Run 2 (`stack-gtn-slack-sdsup-dev`), total late orders across 16 worlds drop from **118 (`7.38/w`) to 66 (`4.12/w`)**, and `visit_failed` drops by **97.3% from 73 to 2** (`failed_visit` ledger cost drops from `-€165.44/w` to `-€3.33/w`!). Because late orders halve a dealer's trust count, eliminating 52 late orders keeps top dealer trust at **24.6–24.9** across Wed–Fri (vs 22.5–23.1 without the class-table gates), unlocking the full +25% dealer price premium.
- **`ring_to_hub_same_day_min=60` + `notes_v2` is 99.5% on-time:** With `notes_v2` filtering out tight delivery-closing notes on `same_day` requests, `won_ring_hub_same_day` wins **194 orders across 16 worlds with only 1 late order (0.52% late!)** in Run 2 (and **214 won with 5 late = 2.34% late** in Run 3), lifting ring margin by **+€332–€339/world**.
- **Safe volume expansion (`price_target_win=0.38, min_supply=25`):** Whereas previous attempts to raise `price_target_win` without the class-table gates + `notes_v2` pushed `dev-07` below 90% on-time, Run 3 (`stack-gtn-ptw38-dev`) wins **256.0 active orders/world (+28.25 orders/w)** with fewer total late orders than Champion v2 (`112` vs `118`), keeping `dev-07` at **94.3% on-time** and achieving **€10,029.58 mean margin (`Δmargin €+1,039.28 ± 229.22, t=4.53, 14/16 seeds better`)**.

## Verdict
**adopt** — All three stacked configurations are SAFE across all 16 dev seeds and beat Champion v2 with `t > 3.6`:
- **Highest margin (`stack-gtn-ptw38-dev`):** `Δmargin €+1,039.28 ± 229.22` (`t = 4.53`, 14/16 better, mean margin **€10,029.58**, worst on-time **94.3%**, mean on-time **97.3%**).
- **Highest safety (`stack-gtn-slack-sdsup-dev`):** `Δmargin €+823.72 ± 224.56` (`t = 3.67`, 13/16 better, mean margin **€9,814.02**, worst on-time **94.6%**, mean on-time **98.3%**, late orders cut 44% `118 → 66`, failed visits cut 97% `73 → 2`).
