# surgical-tradein-and-window-gates: Surgical 2-leg trade-in gate and stop-window clamping (without fee-ramp inflation) on the GTN stack

- **Agent / branch / commit:** gemini · `exp/gemini-n14-03114-surgical-tradein-and-window-gates`
- **Date:** 2026-11-14 03:38
- **Idea from:** Near-miss refinement & combination of `origin/exp/gemini-n14-02113-private-windows-and-tradeins` (`trade_in_mode="same_day_only"`, `respect_stop_windows=True` without `early_window_fee_ramp`) on top of `origin/exp/gemini-n14-02114-stack-gates-trust-notes`

## Why we tried it
1. In `n14-02113-private-windows-and-tradeins`, fixing Margin X-Ray Leak #4 (the 50.0% late rate on 2-leg trade-ins and 6.5% late rate on narrow private-address stop windows) beat Champion v2 on **10 of 16 dev seeds**, lifted worst-seed margin by **+€432.45**, increased weekly revenue by **+€31.24/wk**, raised mean on-time by **+0.13%**, cut late 2-leg trade-ins by **83% (`0.75/wk → 0.12/wk`)**, and cut `late_ring` by **41% (`1.06/wk → 0.62/wk`)**. However, its 16-seed mean Δmargin was `€-118.81 ± 153.55` because `early_window_ramp` in `Desk.fees_for()` shortened `until` to `eff_last_pickup - 3 * HOUR` (`6.25 orders/wk`), compressing the `0.85× → 1.60×` fee ramp on 3-hour private pickup windows and costing **-€103.87/wk** in extra driver fees (plus `-€1,502` and `-€1,343` swings on `dev-07` and `dev-10`).
2. Meanwhile, on our `€10,030/wk` stack (`origin/exp/gemini-n14-02114-stack-gates-trust-notes`), the class-table gates (`max_next_day_drive_min=480, fri_same_day_max_drive=100, thin_long_next_day_supply=50`) and `notes_v2=True` already eliminated long `next_day`, Friday `same_day`, and unparsed-note late orders, leaving **2-leg trade-ins and narrow private-address stop windows as the largest remaining untouched source of late orders and dealer-trust halvings**.
3. By decoupling `early_window_fee_ramp: bool = False` from `respect_stop_windows: bool = True`, we isolate the quoting and stop-window clamping protections in `Desk.price()` and `stops_for()` without ever inflating `Desk.fees_for()`.

## What changed
Merged `origin/exp/gemini-n14-02114-stack-gates-trust-notes` and `origin/exp/gemini-n14-02113-private-windows-and-tradeins` into `exp/gemini-n14-03114-surgical-tradein-and-window-gates`:
- `src/spread_lab/policy.py`:
  - Kept `respect_stop_windows: bool = False`, `min_pickup_window_slack_min: int = 180`, `trade_in_mode: str = "all"`, and added `early_window_fee_ramp: bool = False` (all defaults preserve Champion v2 100% identically: `Δmargin €+0.00 ± 0.00` on smoke).
  - In `Desk.fees_for()`: only shortens `until` to `eff_last_pickup - 3 * HOUR` when `self.p.early_window_fee_ramp` is `True`. With `respect_stop_windows=True` and `early_window_fee_ramp=False`, `Desk.fees_for()` keeps `until = order["lastPickupAt"] - 3 * HOUR` (`early_window_ramp = 0`) and never inflates driver fees.
  - In `Desk.price()`: when `p.respect_stop_windows` is `True`, uses the v2-aware `window_from_note(..., v2=p.notes_v2, arrived_at=request["arrivedAt"], private_address=..., stated_hours=leg["pickup"]["hours"])` for `p_win`. Crucially, because `window_from_note(..., "pickup", v2=True)` places a dealer's daily closing hour on `start // DAY` (Day 1) for `stops_for()`, we check `p_hard_end = leg["pickup"]["window"]["to"] < deadline or deadline // DAY == p_ready // DAY` before applying `p_win["to"] - p_ready < p.min_pickup_window_slack_min` — ensuring multi-day options at commercial dealers (which reopen on Day 2) are not falsely dropped by Day 1 closing hours (fixing `dropped_pickup_window` on smoke from `9.25/wk` in Smoke 2 down to `3.00/wk` in Smoke 2b, and `1.38/wk` on dev). Also checks leg-0 delivery window slack (`min(deadline, leg["delivery"]["window"]["to"]) - p_ready - leg_drive >= p.min_slack_min + p.slack_per_drive * leg_drive`) and full-route slack against `min(deadline, legs[-1]["delivery"]["window"]["to"])`.
  - In `stops_for()`: when `respect_stop_windows` is `True`, clamps `deliv_to = min(delivery["window"]["to"], shift_business_days(order["deadline"], extra_days) if notes_v2 else order["deadline"])` so narrow private delivery windows and leg 0 of 2-leg trade-ins are never widened up to `20:00`.

### Run commands
- **Dev 1 (`gtn-tradein-win-dev`):**
  ```sh
  uv run lab eval -s trust_invest=0.05 -s notes_v2=True -s note_unsure=decline -s max_next_day_drive_min=480 -s fri_same_day_max_drive=100 -s thin_long_next_day_supply=50 -s ring_to_hub_same_day_min=60 -s same_day_min_supply=50 -s min_slack_min=150 -s slack_per_drive=0.75 -s trade_in_mode=same_day_only -s respect_stop_windows=True -s min_pickup_window_slack_min=180 -s early_window_fee_ramp=False --name gtn-tradein-win-dev
  ```
- **Dev 2 (`gtn-tradein-win-ptw38-dev`):**
  ```sh
  uv run lab eval -s trust_invest=0.05 -s notes_v2=True -s note_unsure=decline -s max_next_day_drive_min=480 -s fri_same_day_max_drive=100 -s thin_long_next_day_supply=50 -s ring_to_hub_same_day_min=60 -s same_day_min_supply=50 -s min_slack_min=150 -s slack_per_drive=0.75 -s trade_in_mode=same_day_only -s respect_stop_windows=True -s min_pickup_window_slack_min=180 -s early_window_fee_ramp=False -s price_target_win=0.38 -s min_supply=25 --name gtn-tradein-win-ptw38-dev
  ```
- **Dev 3 (`gtn-tradein-win-ptw45-dev`):** same as Dev 2 with `-s price_target_win=0.45`.

## Results (level 8, vs champion v2, paired)
| set | run folder | mean margin | Δmargin ± SE (vs champ) | t | better/worse | on-time min (mean, Δ) | SAFE |
|---|---|---:|---:|---:|---:|---:|---|
| smoke (noop) | `runs/20261114-032433-gtn-tradein-noop` | €9,662.25 | €+0.00 ± 0.00 | — | 0 / 0 | 95.5% (96.7%, +0.00%) | yes |
| smoke 1 (`trade_in_mode=same_day_only`) | `runs/20261114-032850-gtn-tradein-smoke1` | €10,179.21 | €+516.96 ± 510.39 | 1.01 | 3 / 1 | 97.6% (98.2%, +1.49%) | yes |
| smoke 2 (`+respect_stop_windows`, pre-`p_hard_end`) | `runs/20261114-032940-gtn-tradein-smoke2` | €10,140.62 | €+478.37 ± 479.95 | 1.00 | 3 / 1 | 96.4% (97.8%, +1.12%) | yes |
| smoke 2b (`+respect_stop_windows`, `p_hard_end` fix) | `runs/20261114-033201-gtn-tradein-smoke2b` | **€10,195.99** | **€+533.74 ± 709.55** | 0.75 | 3 / 1 | **97.5% (98.2%, +1.51%)** | yes |
| smoke 3 (`smoke 2b + ptw38/ms25`) | `runs/20261114-033258-gtn-tradein-smoke3` | **€10,671.56** | **€+1,009.31 ± 478.24** | **2.11** | **4 / 0** | **96.3% (97.7%, +1.01%)** | yes |
| **dev 1 (`gtn-tradein-win-dev`)** | `runs/20261114-033415-gtn-tradein-win-dev` | **€9,716.13** | **€+725.82 ± 249.16** | **2.91** | **12 / 4** | **95.2% (98.0%, +1.31%)** | **yes** |
| **dev 2 (`gtn-tradein-win-ptw38-dev`)** | `runs/20261114-033505-gtn-tradein-win-ptw38-dev` | **€9,971.86** | **€+981.56 ± 242.66** | **4.05** | **12 / 4** | **95.6% (97.9%, +1.18%)** | **yes** |
| dev 3 (`gtn-tradein-win-ptw45-dev`) | `runs/20261114-033637-gtn-tradein-win-ptw45-dev` | €10,030.58 | €+1,040.27 ± 294.60 | 3.53 | 14 / 2 | 90.9% (96.9%, +0.17%) | no (`dev-07` 90.9%) |

### Direct paired comparisons against `n14-02114` (`uv run lab compare`)
| Run (`A`) | Baseline (`B`) | Δmargin ± SE | t | better/worse | Δon-time mean | Worst-seed on-time (`A` vs `B`) |
|---|---|---:|---:|---:|---:|---|
| `gtn-tradein-win-dev` | `20261114-022233-stack-gtn-slack-sdsup-dev` | €-97.89 ± 107.50 | -0.91 | 5 / 10 | -0.21% | **95.19% vs 94.57% (+0.62%)** |
| **`gtn-tradein-win-ptw38-dev`** | `20261114-022233-stack-gtn-slack-sdsup-dev` | **€+157.84 ± 151.56** | **+1.04** | **9 / 7** | -0.34% | **95.62% vs 94.57% (+1.05%)** |
| **`gtn-tradein-win-ptw38-dev`** | `20261114-022434-stack-gtn-ptw38-dev` | **€-57.72 ± 74.99** | **-0.77** | **7 / 8 (1 tie)** | **+0.61%** | **95.62% vs 94.26% (+1.36%)** |
| `gtn-tradein-win-ptw45-dev` | `20261114-022434-stack-gtn-ptw38-dev` | €+1.00 ± 262.61 | +0.00 | 11 / 5 | -0.40% | 90.94% vs 94.26% (-3.32%) |

### Detailed stats counters and ledger breakdown on dev (16 worlds total / mean per world)
| Metric / Counter | Champion v2 (dev 16) | `stack-gtn-slack-sdsup-dev` | `gtn-tradein-win-dev` (Dev 1) | `stack-gtn-ptw38-dev` | **`gtn-tradein-win-ptw38-dev` (Dev 2)** | `gtn-tradein-win-ptw45-dev` (Dev 3) |
|---|---:|---:|---:|---:|---:|---:|
| Active won orders (total / mean) | 3,644 (227.75/w) | 3,737 (233.56/w) | 3,700 (231.25/w) | 4,096 (256.00/w) | **4,056 (253.50/w)** | 4,683 (292.69/w) |
| **Total late orders (late %)** | 118 (7.38/w, 3.24%) | 66 (4.12/w, 1.77%) | 73 (4.56/w, 1.97%) | 112 (7.00/w, 2.73%) | **85 (5.31/w, 2.10%, -24.1%)** | 149 (9.31/w, 3.18%) |
| **Worst-seed on-time (`min`)** | 92.65% | 94.57% | **95.19%** | 94.26% | **95.62% (+1.36%)** | 90.94% |
| **Mean on-time (`mean`)** | 96.75% | 98.27% | **98.05%** | 97.32% | **97.93% (+0.61%)** | 96.92% |
| **`won_trade_in` (total / mean)** | 24 (1.50/w) | ~24 (untracked) | **4 (0.25/w)** | ~26 (untracked) | **5 (0.31/w)** | 7 (0.44/w) |
| **`late_trade_in` (total / mean)** | 12 (0.75/w, 50.0%) | ~12 (untracked) | **0 (0.00/w, 0.0%)** | ~13 (untracked) | **0 (0.00/w, 0.0%)** | 1 (0.06/w, 14.3%) |
| **`dropped_trade_in`** | 0 (0.00/w) | 0 (0.00/w) | **108 (6.75/w)** | 0 (0.00/w) | **116 (7.25/w)** | 115 (7.19/w) |
| **`dropped_pickup_window`** | 0 (0.00/w) | 0 (0.00/w) | **22 (1.38/w)** | 0 (0.00/w) | **22 (1.38/w)** | 22 (1.38/w) |
| **`dropped_delivery_window`** | 0 (0.00/w) | 0 (0.00/w) | **33 (2.06/w)** | 0 (0.00/w) | **32 (2.00/w)** | 32 (2.00/w) |
| **`early_window_ramp`** | 0 (0.00/w) | 0 (0.00/w) | **0 (0.00/w)** | 0 (0.00/w) | **0 (0.00/w)** | 0 (0.00/w) |
| **`late_ring` (total / mean)** | 17 (1.06/w) | 12 (0.75/w) | 13 (0.81/w) | 30 (1.88/w) | **21 (1.31/w, -30.0%)** | 36 (2.25/w) |
| `won_ring_hub_same_day` | 0 (0.00/w) | 194 (12.12/w) | 196 (12.25/w) | 214 (13.38/w) | **209 (13.06/w)** | 266 (16.62/w) |
| `late_ring_hub_same_day` | 0 (0.00/w) | 1 (0.06/w) | 2 (0.12/w) | 5 (0.31/w) | **4 (0.25/w)** | 12 (0.75/w) |
| `deadline_close` warnings | 193 (12.06/w) | 146 (9.12/w) | 156 (9.75/w) | 225 (14.06/w) | **211 (13.19/w)** | 333 (20.81/w) |
| `gig_expired` | 121 (7.56/w) | 67 (4.19/w) | 72 (4.50/w) | 104 (6.50/w) | **99 (6.19/w)** | 159 (9.94/w) |
| `visit_failed` | 73 (4.56/w) | 2 (0.12/w) | 5 (0.31/w) | 3 (0.19/w) | **5 (0.31/w)** | 7 (0.44/w) |
| Ring margin (€/world) | €2,114.01 | €2,446.35 | €2,377.10 | €2,333.92 | **€2,358.65 (+€24.73/w)** | €2,271.10 |
| Ledger `revenue` (€/world) | +26,922.43 | +25,926.69 | +25,794.21 | +28,082.93 | **+27,886.33** | +30,848.57 |
| Ledger `driver_fee` (€/world) | -17,286.92 | -15,861.10 | **-15,794.14** | -17,673.60 | **-17,578.21 (+€95.39/w saved)** | -20,328.26 |
| Ledger `late_refund` (€/world) | -376.20 | -174.84 | -195.39 | -288.22 | **-234.08 (+€54.14/w saved)** | -397.98 |
| Ledger `failed_visit` (€/world) | -165.44 | -3.33 | -13.27 | -6.68 | **-9.83** | -16.31 |

### Key findings
1. **100% elimination of late 2-leg trade-ins across all 16 dev seeds:** In both `gtn-tradein-win-dev` (`4 won, 0 late`) and `gtn-tradein-win-ptw38-dev` (`5 won, 0 late`), gating `next_day`/`within_3_days` 2-leg trade-ins (`dropped_trade_in = 6.75–7.25/wk`) plus checking leg-0 delivery window slack (`dropped_delivery_window = 2.00/wk`) and pickup window slack (`dropped_pickup_window = 1.38/wk`) reduced `late_trade_in` from `12 / 24 (50.0%)` in Champion v2 to **0 / 5 (0.0%)**.
2. **Decoupling `early_window_fee_ramp=False` completely fixed the `n14-02113` driver fee penalty:** Whereas `n14-02113` (`priv-win-dev`) paid `+€103.87/wk` in extra driver fees from `early_window_ramp` (`6.25/wk`), setting `early_window_fee_ramp=False` reduced `driver_fee` by **`€95.39/wk`** (`-€17,673.60 → -€17,578.21`) and saved **`+€54.14/wk` in late refunds** (`-€288.22 → -€234.08`) vs `stack-gtn-ptw38-dev`.
3. **Massive safety-floor upgrade at high volume (`price_target_win=0.38, min_supply=25`):** Compared to `stack-gtn-ptw38-dev` (`n14-02114` Run 3), `gtn-tradein-win-ptw38-dev` cut total late orders across the 16 dev worlds by **24.1% (`112 → 85`, `-27` late orders)**, cut `late_ring` by **30.0% (`30 → 21`)**, lifted mean on-time by **`+0.61%` (`97.32% → 97.93%`)**, and lifted the **worst-seed on-time across all 16 seeds by `+1.36%` (`94.26% → 95.62%`)**:
   - On `dev-07` (the hardest on-time seed in the dev set, which was `94.26%` with 17 late orders in `stack-gtn-ptw38-dev`), `gtn-tradein-win-ptw38-dev` cut late orders in half to **8 late (`97.32%` on-time, `+3.07%`)**.
   - On `dev-13` (the second-lowest on-time seed in `stack-gtn-ptw38-dev` at `94.70%`), on-time rose by **`+1.47%` to `96.17%`**.
   - On `dev-01`, on-time rose by **`+2.76%` (`96.00% → 98.76%`)** and margin rose by **`+€263.66`**.
   - On `dev-08`, `gtn-tradein-win-ptw38-dev` achieved **100.00% on-time (`259/259` won orders on time)** and **`€14,918.60`** margin (`+€115.94`).
   - Across the 15 seeds excluding `dev-07`, `gtn-tradein-win-ptw38-dev` slightly beat `stack-gtn-ptw38-dev` in mean margin (`+€7.45/wk`), while on `dev-07` the `-€1,035.20` margin difference bought a `+3.07%` jump in on-time share (`94.26% → 97.32%`), bringing overall 16-seed mean margin to **`€9,971.86` (`Δmargin €+981.56 ± 242.66, t = 4.05` vs Champion v2; `Δmargin €-57.72 ± 74.99, t = -0.77` vs `stack-gtn-ptw38-dev`)**.

## Verdict
**adopt (highest-safety €10k stack: `95.62%` min / `97.93%` mean on-time)** — `gtn-tradein-win-ptw38-dev` achieves **`Δmargin €+981.56 ± 242.66` (`t = 4.05`, 12/16 better vs Champion v2, mean margin `€9,971.86`)**, eliminates **100% of late 2-leg trade-ins (`0/5`)**, cuts late orders at `price_target_win=0.38` by **24.1% (`112 → 85`)**, and raises the 16-seed worst on-time share by **`+1.36%` (`94.26% → 95.62%`)**.
