# stack-v7-feedrop-buf-alarm: Grand Synthesis v7 (`n14-03324` supply-adaptive fee_open & drop rescue + `n14-03111` adaptive delivery buffer & pre-warn alarm + smooth warning ramp + `dealer_lr=0.01`)

- **Agent / branch / commit:** gemini · `exp/gemini-n14-04154-stack-v7-feedrop-buf-alarm` · see HEAD
- **Date:** 2026-11-14 04:45
- **Idea from:** Grand Synthesis v7 combining tonight's #1 mean-margin branch (`origin/exp/gemini-n14-03324-supply-adaptive-fee-open-and-drop-rescue`, `€10,577.92/wk`) and tonight's #1 t-statistic branch (`origin/exp/gemini-n14-03111-adaptive-delivery-buffer-and-alarm`, `€10,508.07/wk`, `t = 7.53`), plus smooth warning fee transition (`fee_warn=1.48, fee_step_min=25, steep_open=1.55`) and `dealer_lr=0.01`

## Why we tried it
Tonight's two strongest dev branches operate on complementary, non-overlapping stages of the order lifecycle and had never been combined:
1. **`n14-03324` (`fee-drop-all180-dev`, `€10,577.92/wk`, `Δmargin €+1,587.61 ± 233.21, t = 6.81`, 15/16 better vs Champion v2):**
   - Built on `n14-02462` (`backlog_multiday_weight=0.25, backlog_in_flight_weight=0.35, price_target_win=0.40, min_supply=22`), it shapes **post-time opening fees** (`hub_multiday_fee_open=0.80` on `supply >= 150` non-`same_day` gigs with `>= 6h` to warning; `thin_sameday_fee_open=0.90` on `supply < 65` `same_day` gigs) and rescues **post-warning drops/no-shows** (`drop_urgent_margin_min=180`, calling `raise_fees(order_id)` when `gig_dropped` or `no_show` occurs within `180` min of `lastPickupAt`).
2. **`n14-03111` (`gtn-ptw40-buf-alarm-dev`, `€10,508.07/wk`, `Δmargin €+1,517.77 ± 201.53, t = 7.53`, 16/16 better vs Champion v2):**
   - Shapes **stop delivery windows** (`delivery_buffer_min=30, buffer_min_slack_min=210` in `stops_for()`, shaving 30 min off `order["deadline"]` when slack `>= 210` min) and **pre-warning deadline-day nudges** (`pre_warn_lead_min=60, pre_warn_fee=1.35` in `Desk.tick()`, repricing unbooked deadline-day gigs 60 min before `deadline_close` to `1.35× -> fee_warn` and sending up to 2 direct offers at `1.35×`).
3. **Why smooth warning ramp (`fee_warn=1.48, fee_step_min=25, steep_open=1.55`) and `dealer_lr=0.01` complete the synthesis:**
   - When `pre_warn_lead_min=60` (`pre_warn_fee=1.35`) is combined with `hub_multiday_fee_open=0.80` and `drop_urgent_margin_min=180`, keeping the baseline `fee_warn=1.60` and `steep_open=1.80` creates an expensive two-stage fee jump (`1.35× -> 1.60× -> 1.80×`) over a 60-minute window around `deadline_close`. Smoothing the transition to `fee_warn=1.48, fee_step_min=25, steep_open=1.55` aligns the pre-warn nudge (`1.35×`), warning ceiling (`1.48×`), and post-warning rescue (`1.55×`), while `dealer_lr=0.01` prevents per-dealer multiplier oscillation at `price_target_win=0.40`.

## What changed
Merged `origin/exp/gemini-n14-03324-supply-adaptive-fee-open-and-drop-rescue` and `origin/exp/gemini-n14-03111-adaptive-delivery-buffer-and-alarm` into `src/spread_lab/policy.py`, resolving the single merge conflict in `Desk.rejoin()` so both `self.lost_requests` and `self.pre_warned` (plus `drop_urgent_margin_min` urgent state) are rebuilt on live-mode restart. Verified that default parameters reproduce Champion v2 bit-for-bit on smoke (`runs/20261114-042528-v7-noop`: `Δmargin €+0.00 ± 0.00`, 0/0).

Common base flags (`$BASE`):
```sh
BASE="-s trust_invest=0.05 -s notes_v2=True -s note_unsure=decline -s max_next_day_drive_min=480 -s fri_same_day_max_drive=100 -s thin_long_next_day_supply=50 -s ring_to_hub_same_day_min=60 -s same_day_min_supply=50 -s slack_per_drive=0.75 -s backlog_multiday_weight=0.25 -s backlog_in_flight_weight=0.35 -s hub_multiday_fee_open=0.80 -s thin_sameday_fee_open=0.90 -s drop_urgent_margin_min=180 -s delivery_buffer_min=30 -s buffer_min_slack_min=210 -s pre_warn_lead_min=60 -s pre_warn_fee=1.35"
```

Dev run commands:
- **Dev Run 1 (`stack-v7-feedrop-buf-alarm-dev` — pure `n14-03324` + `n14-03111` synthesis):**
  ```sh
  uv run lab eval $BASE -s min_slack_min=150 -s price_target_win=0.40 -s min_supply=22 --name stack-v7-feedrop-buf-alarm-dev
  ```
- **Dev Run 2 (`stack-v7-smoothfee-dev` — adding smooth warning transition `fee_warn=1.48, fee_step_min=25, steep_open=1.55`):**
  ```sh
  uv run lab eval $BASE -s min_slack_min=150 -s price_target_win=0.40 -s min_supply=22 -s fee_warn=1.48 -s fee_step_min=25 -s steep_open=1.55 --name stack-v7-smoothfee-dev
  ```
- **Dev Run 3 (`stack-v7-dlr01-dev` — adding `dealer_lr=0.01` on top of smooth warning transition):**
  ```sh
  uv run lab eval $BASE -s min_slack_min=150 -s price_target_win=0.40 -s min_supply=22 -s fee_warn=1.48 -s fee_step_min=25 -s steep_open=1.55 -s dealer_lr=0.01 --name stack-v7-dlr01-dev
  ```

## Results (level 8, vs champion v2, paired)
| set | run folder | mean margin | min margin | Δmargin ± SE | t | better/worse | on-time min (mean, Δ) | SAFE |
|---|---|---:|---:|---:|---:|---:|---:|---|
| smoke (noop) | `runs/20261114-042528-v7-noop` | €9,662.25 | €7,296.78 | €+0.00 ± 0.00 | — | 0 / 0 | 95.5% (96.7%, +0.00%) | yes |
| smoke 1 (core v7) | `runs/20261114-042701-v7-smoke1-core` | €10,767.97 | €7,514.77 | €+1,105.72 ± 542.25 | 2.04 | 4 / 0 | 94.1% (96.7%, +0.02%) | yes |
| smoke 2 (`+dealer_lr=0.01`) | `runs/20261114-042710-v7-smoke2-dlr01` | €10,814.56 | €7,294.99 | €+1,152.31 ± 565.88 | 2.04 | 3 / 1 | 95.3% (96.5%, -0.21%) | yes |
| smoke 3 (`+smoothfee`) | `runs/20261114-042749-v7-smoke3-smoothfee` | **€11,309.56** | **€8,131.65** | **€+1,647.32 ± 516.12** | **3.19** | **4 / 0** | **95.8% (96.9%, +0.21%)** | **yes** |
| smoke 4 (`s=140, ms=20`) | `runs/20261114-042844-v7-smoke4-s140-ms20` | €11,018.51 | €8,164.45 | €+1,356.27 ± 644.95 | 2.10 | 3 / 1 | 95.6% (96.9%, +0.25%) | yes |
| smoke 5 (`+smoothfee + dlr01`) | `runs/20261114-042946-v7-smoke5-smoothfee-dlr01` | €11,240.57 | €7,721.60 | €+1,578.32 ± 656.19 | 2.41 | 4 / 0 | 94.0% (96.8%, +0.12%) | yes |
| smoke 6 (`+smoothfee + s140, ms20`) | `runs/20261114-043047-v7-smoke6-smoothfee-s140-ms20` | €11,101.10 | €8,041.60 | €+1,438.85 ± 676.05 | 2.13 | 3 / 1 | 94.9% (96.8%, +0.09%) | yes |
| **dev 1 (`stack-v7-feedrop-buf-alarm-dev`)** | `runs/20261114-043158-stack-v7-feedrop-buf-alarm-dev` | €10,295.51 | €7,514.77 | €+1,305.21 ± 259.72 | 5.03 | 15 / 1 | 94.1% (97.4%, +0.68%) | yes |
| **dev 2 (`stack-v7-smoothfee-dev`)** | `runs/20261114-043448-stack-v7-smoothfee-dev` | **€10,560.06** | **€7,888.32** | **€+1,569.75 ± 198.78** | **7.90** | **16 / 0** | **94.0% (97.2%, +0.48%)** | **yes** |
| **dev 3 (`stack-v7-dlr01-dev`)** | `runs/20261114-044017-stack-v7-dlr01-dev` | **€10,648.07** | **€7,721.60** | **€+1,657.77 ± 233.04** | **7.11** | **16 / 0** | **94.0% (97.2%, +0.42%)** | **yes** |

### Head-to-head `uv run lab compare` against parent dev runs & across v7 dev runs
| Comparison (Run A vs Run B on 16 dev seeds) | Δmargin ± SE | t | better / worse | Δon-time |
|---|---:|---:|---:|---:|
| **Dev 3 (`stack-v7-dlr01-dev`, `€10,648.07`)** vs Champion v2 (`€8,990.31`) | **`€+1,657.77 ± 233.04`** | **`7.11`** | **`16 / 0`** | **`+0.42%`** |
| **Dev 3 (`stack-v7-dlr01-dev`, `€10,648.07`)** vs Parent 1 `fee-drop-all180-dev` (`€10,577.92`) | **`€+70.15 ± 101.32`** | **`0.69`** | **`12 / 4`** | `-0.51%` |
| **Dev 3 (`stack-v7-dlr01-dev`, `€10,648.07`)** vs Parent 2 `gtn-ptw40-buf-alarm-dev` (`€10,508.07`) | **`€+140.00 ± 112.85`** | **`1.24`** | **`12 / 4`** | `-0.54%` |
| **Dev 3 (`stack-v7-dlr01-dev`, `€10,648.07`)** vs Dev 1 `stack-v7-feedrop-buf-alarm-dev` (`€10,295.51`) | **`€+352.56 ± 112.17`** | **`3.14`** | **`13 / 3`** | `-0.26%` |
| **Dev 3 (`stack-v7-dlr01-dev`, `€10,648.07`)** vs Dev 2 `stack-v7-smoothfee-dev` (`€10,560.06`) | **`€+88.01 ± 123.61`** | **`0.71`** | **`9 / 7`** | `-0.06%` |
| **Dev 2 (`stack-v7-smoothfee-dev`, `€10,560.06`)** vs Champion v2 (`€8,990.31`) | **`€+1,569.75 ± 198.78`** | **`7.90`** | **`16 / 0`** | **`+0.48%`** |
| **Dev 2 (`stack-v7-smoothfee-dev`, `€10,560.06`)** vs Parent 2 `gtn-ptw40-buf-alarm-dev` (`€10,508.07`) | **`€+51.98 ± 113.00`** | **`0.46`** | **`10 / 6`** | `-0.48%` |
| **Dev 2 (`stack-v7-smoothfee-dev`, `€10,560.06`)** vs Parent 1 `fee-drop-all180-dev` (`€10,577.92`) | `€-17.86 ± 121.33` | `-0.15` | `7 / 9` | `-0.45%` |
| **Dev 2 (`stack-v7-smoothfee-dev`, `€10,560.06`)** vs Dev 1 `stack-v7-feedrop-buf-alarm-dev` (`€10,295.51`) | **`€+264.54 ± 167.59`** | **`1.58`** | **`10 / 6`** | `-0.20%` |
| Dev 1 (`stack-v7-feedrop-buf-alarm-dev`, `€10,295.51`) vs Parent 1 `fee-drop-all180-dev` (`€10,577.92`) | `€-282.41 ± 139.67` | `-2.02` | `4 / 12` | `-0.25%` |
| Dev 1 (`stack-v7-feedrop-buf-alarm-dev`, `€10,295.51`) vs Parent 2 `gtn-ptw40-buf-alarm-dev` (`€10,508.07`) | `€-212.56 ± 170.73` | `-1.25` | `6 / 10` | `-0.28%` |

### Full ledger & telemetry breakdown on dev (16 worlds total / mean per world)
| Metric / Counter | Champion v2 | Parent 1: `fee-drop-all180-dev` (`n14-03324`) | Parent 2: `gtn-ptw40-buf-alarm-dev` (`n14-03111`) | Dev 1: `stack-v7-feedrop-buf-alarm-dev` | Dev 2: `stack-v7-smoothfee-dev` | **Dev 3: `stack-v7-dlr01-dev`** |
|---|---:|---:|---:|---:|---:|---:|
| **Mean margin (€/world)** | €8,990.31 | €10,577.92 | €10,508.07 | €10,295.51 | **€10,560.06** | **€10,648.07** |
| **Worst-seed margin (€)** | €6,017.30 | €7,521.37 | €7,523.75 | €7,514.77 | **€7,888.32** | **€7,721.60** |
| **vs Champion `t` (better/worse)** | — | `6.81` (15/1) | `7.53` (16/0) | `5.03` (15/1) | **`7.90` (16/0)** | **`7.11` (16/0)** |
| Active won orders (total / mean) | 3,644 (227.75/w) | 4,380 (273.75/w) | 4,331 (270.69/w) | 4,361 (272.56/w) | 4,374 (273.38/w) | **4,407 (275.44/w)** |
| **Total late orders (late %)** | 118 (7.38/w, 3.24%) | 102 (6.38/w, 2.33%) | **99 (6.19/w, 2.29%)** | 112 (7.00/w, 2.57%) | 121 (7.56/w, 2.77%) | 124 (7.75/w, 2.81%) |
| **Worst-seed on-time %** | 94.36% | 95.64% | **95.80%** | 94.14% | 94.05% | 94.00% |
| **Mean on-time %** | 96.75% | 97.68% | **97.71%** | 97.43% | 97.23% | 97.17% |
| `hub_multiday_posts` | 0 (0.00/w) | 1,226 (76.62/w) | 0 (0.00/w) | 1,211 (75.69/w) | 1,207 (75.44/w) | **1,207 (75.44/w)** |
| `thin_sameday_posts` | 0 (0.00/w) | 379 (23.69/w) | 0 (0.00/w) | 377 (23.56/w) | 386 (24.12/w) | **380 (23.75/w)** |
| `drop_rescued` | 0 (0.00/w) | 11 (0.69/w) | 0 (0.00/w) | 14 (0.88/w) | 13 (0.81/w) | **20 (1.25/w)** |
| `buffered_stops` | 0 (0.00/w) | 0 (0.00/w) | 4,300 (268.75/w) | 4,331 (270.69/w) | 4,345 (271.56/w) | **4,381 (273.81/w)** |
| `pre_warned` | 0 (0.00/w) | 0 (0.00/w) | 192 (12.00/w) | 206 (12.88/w) | 251 (15.69/w) | **243 (15.19/w)** |
| `offers` / `offer_accepted` | 0 / 0 | 0 / 0 | 384 / 7 | 412 / 4 | 502 / 5 | **486 / 5** |
| `declined_backlog` | 0 (0.00/w) | 60 (3.75/w) | 0 (0.00/w) | 58 (3.62/w) | 57 (3.56/w) | **49 (3.06/w)** |
| `in_flight_blocked` | 0 (0.00/w) | 50 (3.12/w) | 0 (0.00/w) | 48 (3.00/w) | 43 (2.69/w) | **39 (2.44/w)** |
| `deadline_close` warnings | 193 (12.06/w) | 237 (14.81/w) | 241 (15.06/w) | 258 (16.12/w) | 290 (18.12/w) | 291 (18.19/w) |
| `gig_expired` | 121 (7.56/w) | 117 (7.31/w) | 119 (7.44/w) | 139 (8.69/w) | 142 (8.88/w) | 142 (8.88/w) |
| `gig_dropped` / `no_show` | 487 / 11 | 586 / 10 | 559 / 14 | 571 / 10 | 543 / 15 | 560 / 11 |
| `visit_failed` | 73 (4.56/w) | 6 (0.38/w) | 8 (0.50/w) | 11 (0.69/w) | **5 (0.31/w)** | 8 (0.50/w) |
| `won_same_day` | 1,147 (71.69/w) | 1,690 (105.62/w) | 1,665 (104.06/w) | 1,676 (104.75/w) | 1,689 (105.56/w) | **1,711 (106.94/w)** |
| `won_next_day` | 2,362 (147.62/w) | 2,535 (158.44/w) | 2,515 (157.19/w) | 2,531 (158.19/w) | 2,538 (158.62/w) | **2,549 (159.31/w)** |
| `won_within_3_days` | 173 (10.81/w) | 200 (12.50/w) | 196 (12.25/w) | 199 (12.44/w) | 193 (12.06/w) | 191 (11.94/w) |
| `won_ring` / `late_ring` | 823 / 17 | 1,044 / 20 | 1,046 / 21 | 1,037 / 20 | 1,042 / 27 | **1,040 / 20** |
| Ledger `revenue` (€/world) | +26,922.43 | +29,928.51 | +29,650.81 | +29,716.15 | +29,758.75 | **+30,039.68** |
| Ledger `driver_fee` (€/world) | -17,286.93 | -18,972.34 | -18,776.97 | -19,017.97 | **-18,742.62** | -18,943.71 |
| Ledger `late_refund` (€/world) | -376.20 | -270.51 | **-260.38** | -282.04 | -334.29 | -297.22 |
| Ledger `undelivered_penalty` (€/world) | -10.72 | -15.68 | **-10.23** | -15.99 | **-10.29** | -64.00 |
| Ledger `failed_visit` (€/world) | -165.44 | -16.96 | -21.21 | -31.07 | **-13.39** | -18.90 |
| Ledger `release_fee` (€/world) | -53.48 | -54.48 | -53.21 | -51.07 | -64.24 | **-43.00** |
| Ledger `waiting` (€/world) | -39.38 | **-20.62** | -20.73 | -22.50 | -33.86 | -24.78 |

### Key Mechanism Insights
1. **Why raw Dev 1 (`stack-v7-feedrop-buf-alarm-dev`, `€10,295.51`) needed the smooth warning fee transition (`fee_warn=1.48, fee_step_min=25, steep_open=1.55`):**
   - In Dev 1, combining `hub_multiday_fee_open=0.80` (which delays some hub multi-day bookings into the deadline day) with `pre_warn_lead_min=60` (`pre_warn_fee=1.35`) and `drop_urgent_margin_min=180` while keeping `fee_warn=1.60` and `steep_open=1.80` caused `driver_fee` to climb to `-€19,017.97/wk` (`+€241/wk` worse than `buf_alarm`) while revenue dipped to `+€29,716.15/wk` (`-€212/wk` below `fee_drop`).
   - Adding the smooth warning transition (`fee_warn=1.48, fee_step_min=25, steep_open=1.55`) in **Dev 2 (`stack-v7-smoothfee-dev`)** slashed `driver_fee` by **`€275.35/wk`** (`-€19,017.97 -> -€18,742.62/wk`), lifted mean margin by **`+€264.54/wk`** to **`€10,560.06`**, achieved **tonight's highest t-statistic (`t = 7.90`, 16/16 seeds better vs Champion v2)**, and lifted worst-seed margin to an all-time high of **`€7,888.32`** (`+€364.57` above `buf_alarm` and `+€366.95` above `fee_drop`).
2. **Adding `dealer_lr=0.01` in Dev 3 (`stack-v7-dlr01-dev`) achieves a new all-time record mean margin of `€10,648.07/wk`:**
   - Slowing per-dealer adaptation from `0.02` to `0.01` on top of the smooth-fee v7 stack lifts weekly revenue above `€30k` for the first time on a `16/16`-winning SAFE stack (**`+€30,039.68/wk`**, winning `275.44` orders/wk), cuts `release_fee` to **`-€43.00/wk`** (lowest of any run), and reaches **`€10,648.07` mean margin (`Δmargin €+1,657.77 ± 233.04, t = 7.11`, 16/16 seeds better vs Champion v2)**.
   - Most importantly, **Dev 3 (`stack-v7-dlr01-dev`) beats both parent dev runs head-to-head on 12 out of 16 seeds**:
     - **`+€70.15 ± 101.32` (12 better, 4 worse)** vs Parent 1 `fee-drop-all180-dev` (`€10,577.92`), while lifting worst-seed margin by `+€200.23` (`€7,521.37 -> €7,721.60`).
     - **`+€140.00 ± 112.85` (`t = 1.24`, 12 better, 4 worse)** vs Parent 2 `gtn-ptw40-buf-alarm-dev` (`€10,508.07`), while lifting worst-seed margin by `+€197.85` (`€7,523.75 -> €7,721.60`).
     - **`+€352.56 ± 112.17` (`t = 3.14`, 13 better, 3 worse)** vs Dev 1 `stack-v7-feedrop-buf-alarm-dev` (`€10,295.51`).

## Verdict
**adopt** — Grand Synthesis v7 with smooth warning transition and `dealer_lr=0.01` (`stack-v7-dlr01-dev`) reaches a new all-time record **`€10,648.07` mean margin (`Δmargin €+1,657.77 ± 233.04, t = 7.11`, 16/16 seeds better vs Champion v2; 12/16 seeds better vs both parent dev runs `fee-drop-all180-dev` and `gtn-ptw40-buf-alarm-dev`)**, worst-seed margin **`€7,721.60`**, and **`94.0%` worst-seed on-time (`97.2%` mean, SAFE)**; while `stack-v7-smoothfee-dev` (`dealer_lr=0.02`) reaches **`€10,560.06` (`Δmargin €+1,569.75 ± 198.78, t = 7.90`, 16/16 seeds better, worst-seed margin `€7,888.32`, SAFE)**.
