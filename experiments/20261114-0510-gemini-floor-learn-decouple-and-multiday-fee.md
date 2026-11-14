# n14-04391-floor-learn-decouple-and-multiday-fee: Partial-option floor loss decoupling and option-specific multi-day fee schedules (`w3d_fee_open`, `multiday_fee_warn`)

- **Agent / branch / commit:** gemini · `exp/gemini-n14-04391-floor-learn-decouple-and-multiday-fee` · `HEAD`
- **Date:** 2026-11-14 05:10
- **Idea from:** Diagnostic analysis of `n14-02241`, `n14-03502`, and `n14-03324`, stacked on `origin/exp/gemini-n14-03324-supply-adaptive-fee-open-and-drop-rescue`

## Why we tried it
Building on `n14-03324` (`20261114-034812-fee-drop-all180-dev`, `€10,577.92/wk`, `97.68%` mean on-time), we investigated two mechanisms targeting quote-floor learning and multi-day driver fee schedules:
1. **Partial-option floor loss decoupling (`floor_loss_scale`, `floor_any_skip_loss`):**
   - On ~65% of quoted requests, multiple options (`same_day`, `next_day`, `within_3_days`) are quoted together. Because `next_day` list price is ~7–8% lower and `within_3_days` list price is ~14% lower than `same_day` while `referenceFeeCents` is identical across options, slower options hit the minimum margin floor (`floor = fee / (1 - min_margin_frac) = 1.359 × referenceFeeCents`) on ~48–60 multi-option quotes/world while `same_day` remains unfloored.
   - In baseline `Desk.price()`, `floored` is set to `True` whenever *any* quoted option hits the floor (`if price < floor: price, floored = floor, True`), so partial-floor multi-option requests get `self.decided[req_id] = "floor"` and `Desk.learn()` ignores both wins and losses on them. Conversely, in `n14-02241`, setting `floor_all_only=True` (`self.decided = "floor" if all(floored_list) else "quote"`) learned both wins and full `-1.0x` losses on partial-floor quotes, which dragged `self.mult` down when high-fee slow options lost.
   - We tested whether marking partial-floor requests (`0 < unfloored_frac < 1`) as `"quote"` so wins learn at `1.0x`, while either skipping partial-floor losses (`floor_any_skip_loss=True`) or scaling the downward loss step by `unfloored_frac` (`floor_loss_scale=True`), improves multiplier tracking.
2. **Extending `n14-03324` fee savings to `within_3_days` (`w3d_fee_open`) and multi-day warning ceiling (`multiday_fee_warn`):**
   - In `n14-03324`, `hub_multiday_fee_open=0.80` opened dense-hub (`supply >= 150`) multi-day gigs (`>= 6h` to warning) at `0.80×` (`76.6/wk`). Because `within_3_days` orders have `>= 24h` before `deadline_close` and `<1%` late rate even in medium/ring towns (`supply < 150`), we tested opening any `within_3_days` order with `span >= 12 * HOUR` at `min(f_open, w3d_fee_open=0.78)`.
   - We also tested capping the pre-warning rising fee schedule ceiling on non-`same_day` orders at `multiday_fee_warn=1.48` instead of `fee_warn=1.60`, and re-tested `dealer_lr=0.01` on top of the `n14-03324` v7 stack.

## What changed
Merged `origin/exp/gemini-n14-03324-supply-adaptive-fee-open-and-drop-rescue` and added four default-off parameters to `Params` and `Desk` in `src/spread_lab/policy.py` (defaults reproduce Champion v2 and `n14-03324` bit-for-bit: `Δmargin €+0.00 ± 0.00` on smoke):
- `floor_loss_scale: bool = False` and `floor_any_skip_loss: bool = False`:
  - `Desk.price()` records `self.unfloored_frac[request["id"]] = sum(1 for f in floored_list if not f) / len(floored_list)`. When either flag is `True`, `Desk.price()` returns `"floor" if all(floored_list) else "quote"`.
  - In `Desk.learn()`, when `uf = self.unfloored_frac.get(request_id, 1.0) < 1.0`:
    - If `won` is `True`, increments `stats["partial_floor_win_learned"] += 1` and learns at `1.0x`.
    - If `won` is `False` and `p.floor_any_skip_loss` is `True`, increments `stats["partial_floor_loss_skipped"] += 1` and returns before incrementing `self.loss_streak` or stepping `self.mult` / `self.dealer_adj`.
    - If `won` is `False` and `p.floor_loss_scale` is `True`, increments `stats["partial_floor_loss_scaled"] += 1` and multiplies `step` by `uf`.
- `w3d_fee_open: float = 0.0`: when `> 0`, in `Desk.fees_for()`, any non-urgent `within_3_days` order with `(order["lastPickupAt"] - 3 * HOUR) - self.now >= 12 * HOUR` sets `fee_open_override = min(f_open_curr, p.w3d_fee_open)` and increments `stats["w3d_low_open_posts"] += 1`.
- `multiday_fee_warn: float = 0.0`: when `> 0`, in `Desk.fees_for()`, any non-urgent order with `order["option"] != "same_day"` passes `fee_warn_override = p.multiday_fee_warn` to `Desk.rising()` and increments `stats["multiday_warn_capped"] += 1`.

Let `<BASE_V7>` denote `n14-03324`'s winning flags:
`-s trust_invest=0.05 -s notes_v2=True -s note_unsure=decline -s max_next_day_drive_min=480 -s fri_same_day_max_drive=100 -s thin_long_next_day_supply=50 -s ring_to_hub_same_day_min=60 -s same_day_min_supply=50 -s min_slack_min=150 -s slack_per_drive=0.75 -s backlog_multiday_weight=0.25 -s backlog_in_flight_weight=0.35 -s price_target_win=0.40 -s min_supply=22 -s hub_multiday_fee_open=0.80 -s thin_sameday_fee_open=0.90 -s drop_urgent_margin_min=180`

Run commands on dev:
- **Dev 1 (`floor-mdfee-w3d78-dev`, `<BASE_V7> -s w3d_fee_open=0.78`):**
  ```sh
  uv run lab eval -s trust_invest=0.05 -s notes_v2=True -s note_unsure=decline -s max_next_day_drive_min=480 -s fri_same_day_max_drive=100 -s thin_long_next_day_supply=50 -s ring_to_hub_same_day_min=60 -s same_day_min_supply=50 -s min_slack_min=150 -s slack_per_drive=0.75 -s backlog_multiday_weight=0.25 -s backlog_in_flight_weight=0.35 -s price_target_win=0.40 -s min_supply=22 -s hub_multiday_fee_open=0.80 -s thin_sameday_fee_open=0.90 -s drop_urgent_margin_min=180 -s w3d_fee_open=0.78 --name floor-mdfee-w3d78-dev
  ```
- **Dev 2 (`floor-mdfee-w3d78-dlr01-dev`, `<BASE_V7> -s w3d_fee_open=0.78 -s dealer_lr=0.01`):**
  ```sh
  uv run lab eval -s trust_invest=0.05 -s notes_v2=True -s note_unsure=decline -s max_next_day_drive_min=480 -s fri_same_day_max_drive=100 -s thin_long_next_day_supply=50 -s ring_to_hub_same_day_min=60 -s same_day_min_supply=50 -s min_slack_min=150 -s slack_per_drive=0.75 -s backlog_multiday_weight=0.25 -s backlog_in_flight_weight=0.35 -s price_target_win=0.40 -s min_supply=22 -s hub_multiday_fee_open=0.80 -s thin_sameday_fee_open=0.90 -s drop_urgent_margin_min=180 -s w3d_fee_open=0.78 -s dealer_lr=0.01 --name floor-mdfee-w3d78-dlr01-dev
  ```
- **Dev 3 (`floor-mdfee-w3d78-warn148-dev`, `<BASE_V7> -s w3d_fee_open=0.78 -s multiday_fee_warn=1.48`):**
  ```sh
  uv run lab eval -s trust_invest=0.05 -s notes_v2=True -s note_unsure=decline -s max_next_day_drive_min=480 -s fri_same_day_max_drive=100 -s thin_long_next_day_supply=50 -s ring_to_hub_same_day_min=60 -s same_day_min_supply=50 -s min_slack_min=150 -s slack_per_drive=0.75 -s backlog_multiday_weight=0.25 -s backlog_in_flight_weight=0.35 -s price_target_win=0.40 -s min_supply=22 -s hub_multiday_fee_open=0.80 -s thin_sameday_fee_open=0.90 -s drop_urgent_margin_min=180 -s w3d_fee_open=0.78 -s multiday_fee_warn=1.48 --name floor-mdfee-w3d78-warn148-dev
  ```

## Results (level 8, vs champion v2, paired)
| set | config (on top of `<BASE_V7>`) | run folder | mean margin | Δmargin ± SE (vs champ) | t | better/worse | on-time min (mean, Δ) | SAFE |
|---|---|---|---:|---:|---:|---:|---:|---|
| smoke | no-op (defaults) | `runs/20261114-044721-floor-mdfee-noop` | €9,662.25 | €+0.00 ± 0.00 | — | 0 / 0 | 95.5% (96.7%, +0.00%) | yes |
| smoke (ref) | `<BASE_V7>` (`n14-03324`) | `runs/20261114-034543-fee-drop-smoke5-all180` | €10,996.27 | €+1,334.02 ± 652.57 | 2.04 | 4 / 0 | 96.3% (97.2%, +0.47%) | yes |
| smoke 1 | `floor_loss_scale=True` | `runs/20261114-044836-floor-mdfee-s1-scale` | €9,845.69 | €+183.44 ± 557.71 | 0.33 | 2 / 2 | 94.2% (96.0%, -0.67%) | yes |
| smoke 2 | `floor_any_skip_loss=True` | `runs/20261114-044949-floor-mdfee-s2-skiploss` | €10,170.54 | €+508.30 ± 534.84 | 0.95 | 2 / 2 | 95.7% (96.5%, -0.14%) | yes |
| smoke 3 | `w3d_fee_open=0.78, multiday_fee_warn=1.48` | `runs/20261114-045111-floor-mdfee-s3-mdfee` | €10,740.08 | €+1,077.84 ± 481.59 | 2.24 | 4 / 0 | 94.6% (95.9%, -0.80%) | yes |
| smoke 4 | `floor_any_skip_loss=True, w3d=0.78, warn=1.48, dlr=0.01` | `runs/20261114-045634-floor-mdfee-s4-combo-dlr01` | €10,591.59 | €+929.35 ± 547.75 | 1.70 | 2 / 2 | 95.2% (96.5%, -0.17%) | yes |
| smoke 5 | `w3d_fee_open=0.78, dealer_lr=0.01` | `runs/20261114-045822-floor-mdfee-s5-w3d-dlr01` | €10,830.15 | €+1,167.90 ± 614.42 | 1.90 | 3 / 1 | 95.2% (96.3%, -0.37%) | yes |
| **smoke 6** | **`w3d_fee_open=0.78` only** | `runs/20261114-045845-floor-mdfee-s6-w3d-only` | **€11,116.64** | **€+1,454.39 ± 509.70** | **2.85** | **4 / 0** | **96.2% (97.2%, +0.52%)** | **yes** |
| dev (ref) | `<BASE_V7>` (`n14-03324`) | `runs/20261114-034812-fee-drop-all180-dev` | **€10,577.92** | **€+1,587.61 ± 233.21** | **6.81** | **15 / 1** | **95.6% (97.7%, +0.94%)** | **yes** |
| **dev 1** | **`w3d_fee_open=0.78` (`floor-mdfee-w3d78-dev`)** | `runs/20261114-050012-floor-mdfee-w3d78-dev` | **€10,477.21** | **€+1,486.90 ± 218.47** | **6.81** | **15 / 1** | **95.4% (97.6%, +0.82%)** | **yes** |
| dev 2 | `w3d_fee_open=0.78, dealer_lr=0.01` | `runs/20261114-050510-floor-mdfee-w3d78-dlr01-dev` | €10,186.13 | €+1,195.82 ± 235.25 | 5.08 | 13 / 3 | 93.9% (96.8%, +0.04%) | yes |
| dev 3 | `w3d_fee_open=0.78, multiday_fee_warn=1.48` | `runs/20261114-050709-floor-mdfee-w3d78-warn148-dev` | €10,383.72 | €+1,393.42 ± 262.02 | 5.32 | 15 / 1 | 94.1% (97.2%, +0.40%) | yes |

### Paired comparisons against `n14-03324` (`20261114-034812-fee-drop-all180-dev`, `€10,577.92`)
| Run | vs `<BASE_V7>` (`n14-03324`) Δmargin ± SE | t | better / worse | Δon-time | Min margin (€/wk) |
|---|---:|---:|---:|---:|---:|
| Smoke 1 (`floor_loss_scale=True`) | €-1,150.58 ± 151.93 | -7.57 | 0 / 4 | -1.14% | €6,770.30 |
| Smoke 2 (`floor_any_skip_loss=True`) | €-825.73 ± 175.90 | -4.69 | 0 / 4 | -0.61% | €6,711.45 |
| Smoke 3 (`w3d=0.78, warn=1.48`) | €-256.18 ± 212.72 | -1.20 | 1 / 3 | -1.27% | €7,620.60 |
| Smoke 4 (`skip_loss + w3d=0.78 + warn=1.48 + dlr=0.01`) | €-404.68 ± 345.55 | -1.17 | 1 / 3 | -0.64% | €7,268.83 |
| Smoke 5 (`w3d=0.78, dealer_lr=0.01`) | €-166.12 ± 249.00 | -0.67 | 2 / 2 | -0.84% | €7,835.15 |
| **Smoke 6 (`w3d_fee_open=0.78` only)** | **€+120.37 ± 223.20** | **+0.54** | **2 / 2** | **+0.04%** | **€7,756.17** |
| **Dev 1 (`floor-mdfee-w3d78-dev`)** | **€-100.71 ± 96.75** | **-1.04** | **8 / 8** | **-0.11%** | **€7,756.17 (+€234.80)** |
| Dev 2 (`floor-mdfee-w3d78-dlr01-dev`) | €-391.79 ± 122.08 | -3.21 | 4 / 12 | -0.89% | **€7,824.84 (+€303.47)** |
| Dev 3 (`floor-mdfee-w3d78-warn148-dev`) | €-194.20 ± 133.34 | -1.46 | 5 / 11 | -0.53% | €7,606.76 (+€85.39) |

### Detailed telemetry and ledger breakdown on dev (16 worlds total / mean per world)
| Metric / Counter | Champion v2 | `<BASE_V7>` (`n14-03324`) | **Dev 1 (`w3d_fee_open=0.78`)** | Dev 2 (`w3d=0.78, dlr=0.01`) | Dev 3 (`w3d=0.78, warn=1.48`) |
|---|---:|---:|---:|---:|---:|
| **Mean margin (€/world)** | €8,990.31 | **€10,577.92** | €10,477.21 | €10,186.13 | €10,383.72 |
| **Min margin (€/world)** | €6,017.30 | €7,521.37 | **€7,756.17** | **€7,824.84** | €7,606.76 |
| Active won orders (total / mean) | 3,644 (227.75/w) | 4,380 (273.75/w) | 4,369 (273.06/w) | 4,390 (274.38/w) | 4,354 (272.12/w) |
| `stats.won` (`sd` / `nd` / `w3d` per wk) | 71.7 / 147.6 / 10.8 | 105.6 / 158.4 / 12.5 | 104.9 / 158.3 / 12.6 | 107.0 / 157.9 / 12.0 | 104.6 / 157.8 / 12.7 |
| **Total late orders (late %)** | 118 (7.38/w, 3.24%) | **102 (6.38/w, 2.33%)** | 107 (6.69/w, 2.45%) | 142 (8.88/w, 3.23%) | 126 (7.88/w, 2.89%) |
| **Worst seed on-time %** | 94.36% | **95.64%** | 95.41% | 93.87% | 94.12% |
| **Mean on-time %** | 96.75% | **97.68%** | 97.57% | 96.79% | 97.15% |
| `quote_quote` / `quote_floor` / `quote_decline` (/wk) | 470.1 / 202.6 / 361.9 | 481.8 / 227.4 / 325.4 | 480.9 / 228.4 / 325.3 | 484.7 / 224.9 / 325.1 | 477.1 / 232.1 / 325.4 |
| `hub_multiday_posts` (total / mean) | 0 (0.00/w) | 1,226 (76.62/w) | 1,220 (76.25/w) | 1,201 (75.06/w) | 1,225 (76.56/w) |
| `thin_sameday_posts` (total / mean) | 0 (0.00/w) | 379 (23.69/w) | 376 (23.50/w) | 391 (24.44/w) | 379 (23.69/w) |
| `w3d_low_open_posts` (total / mean) | 0 (0.00/w) | 0 (0.00/w) | **203 (12.69/w)** | 190 (11.88/w) | 202 (12.62/w) |
| `multiday_warn_capped` (total / mean) | 0 (0.00/w) | 0 (0.00/w) | 0 (0.00/w) | 0 (0.00/w) | **2,775 (173.44/w)** |
| `drop_rescued` (total / mean) | 0 (0.00/w) | 11 (0.69/w) | 13 (0.81/w) | 15 (0.94/w) | 15 (0.94/w) |
| `deadline_close` warnings | 193 (12.06/w) | 237 (14.81/w) | **234 (14.62/w)** | 283 (17.69/w) | 284 (17.75/w) |
| `gig_dropped` / `no_show` | 487 / 11 | 586 / 10 | **564 / 9** | 592 / 11 | 535 / 8 |
| `won_ring` / `late_ring` | 823 / 17 | 1,044 / 20 | 1,032 / 20 | 1,048 / 24 | 1,038 / 30 |
| Ledger `revenue` (€/world) | +26,922.43 | **+29,928.51** | +29,849.23 | +29,832.88 | +29,670.49 |
| Ledger `driver_fee` (€/world) | -17,286.92 | -18,972.34 | -18,976.05 | -19,211.55 | **-18,838.71** |
| Ledger `late_refund` (€/world) | -376.20 | -270.51 | **-250.17** | -329.96 | -343.72 |
| Ledger `failed_visit` (€/world) | -165.44 | -16.96 | -19.66 | -27.55 | -5.82 |
| Ledger `waiting` (€/world) | -39.38 | -20.62 | **-16.88** | -20.62 | -24.38 |
| Ledger `release_fee` (€/world) | -53.48 | -54.48 | -53.48 | -41.12 | -54.73 |
| Ledger `undelivered_penalty` (€/world) | -10.72 | **-15.68** | -55.78 | -15.94 | -19.41 |

### Diagnosis: Why `<BASE_V7>` (`n14-03324`) remains superior
1. **Why `floor_loss_scale=True` (`-€1,150.58/wk` on smoke) and `floor_any_skip_loss=True` (`-€825.73/wk` on smoke) degraded pricing:**
   - Code audit showed that baseline `Desk.price()` sets `floored = True` whenever *any* quoted option hits `floor = fee / (1 - p.min_margin_frac)`, returning `decision = "floor"`. Thus, in `<BASE_V7>`, partial-floor multi-option quotes (`0 < unfloored_frac < 1`, ~48–55 quotes/wk on smoke) are **already** marked `"floor"`, so `Desk.learn()` **already skips both wins and losses** on them.
   - When `floor_any_skip_loss=True` or `floor_loss_scale=True` changes `decision` to `"quote"` on partial-floor requests and learns wins at `1.0x` (`partial_floor_win_learned = 24.0–26.8/wk` on smoke) while skipping (`partial_floor_loss_skipped = 26.8/wk`) or down-scaling (`partial_floor_loss_scaled = 21.8/wk`) losses, it introduces a severe **upward drift in `self.mult` and `self.dealer_adj`** (`+24 × 0.60 × 0.05 = +0.72` log-units/wk under `floor_any_skip_loss=True`). That upward bias overprices subsequent quotes and sheds `15–19` won orders/wk (`285.2 -> 266.8/wk` on smoke). Keeping `decision = "floor" if any(floored) else "quote"` is symmetric and unbiased.
2. **Why `multiday_fee_warn=1.48` (`Dev 3`, `-€194.20 ± 133.34/wk`, `5/11` vs `<BASE_V7>`) hurt on dev:**
   - Lowering the pre-warning fee ceiling from `1.60×` to `1.48×` across `2,775` multi-day posts (`173.44/wk`) saved `€133.63/wk` in `driver_fee`, but caused **`+47` more multi-day orders to reach `deadline_close` unbooked** (`237 -> 284`, `+19.8%`). Those extra warnings led to **+24 additional late orders** (`102 -> 126`, `late_ring: 20 -> 30`, `Δon-time -0.53%`), costing `-€73.21/wk` in `late_refund` and `-€258.02/wk` in lost dealer-trust revenue.
3. **Why `w3d_fee_open=0.78` (`Dev 1`, `-€100.71 ± 96.75/wk`, `8/8` split vs `<BASE_V7>`) is neutral-to-slightly-negative on dev:**
   - `w3d_low_open_posts` fired only `12.69/wk` (`203` across 16 worlds), and since `hub_multiday_fee_open=0.80` already opens dense-hub `within_3_days` gigs at `0.80×`, the incremental `0.02×` reduction in hubs (`0.80× -> 0.78×`) and `0.07×` in non-hubs (`0.85× -> 0.78×`) yielded minimal fee savings while perturbing driver booking trajectories (`8` seeds better, `8` seeds worse, with one extra undelivered car costing `-€40.10/wk` in `undelivered_penalty`, though worst-seed margin rose `+€234.80` to `€7,756.17`).

## Verdict
**reject (`floor_loss_scale`, `floor_any_skip_loss`, `w3d_fee_open`, `multiday_fee_warn` all default to off; keep `<BASE_V7>` / `n14-03324` as best)** — Best tested extension on dev (`floor-mdfee-w3d78-dev`, `w3d_fee_open=0.78` on `<BASE_V7>`) is SAFE at **`€10,477.21/wk` (`Δmargin €+1,486.90 ± 218.47, t = 6.81`, 15/1 vs Champion v2, min margin `€7,756.17`, min on-time `95.4%`)**, tying `<BASE_V7>` 8/8 on seeds but trailing `<BASE_V7>`'s `€10,577.92/wk` by `Δmargin €-100.71 ± 96.75 (t = -1.04)`.
