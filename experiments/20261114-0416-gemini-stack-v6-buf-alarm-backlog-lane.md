# n14-03504-stack-v6-buf-alarm-backlog-lane: Unified v6 branch merging adaptive delivery buffer/alarm (`n14-03111`), deadline-aware backlog (`n14-02462`), and centered lane-cost pricing (`n14-02461`)

- **Agent / branch / commit:** gemini · `exp/gemini-n14-03504-stack-v6-buf-alarm-backlog-lane` · see HEAD
- **Date:** 2026-11-14 04:16
- **Idea from:** Combination experiment merging our two €10.5k/wk dev champions (`origin/exp/gemini-n14-03111-adaptive-delivery-buffer-and-alarm` and `origin/exp/gemini-n14-02462-deadline-aware-backlog`) with `origin/exp/gemini-n14-02461-centered-lane-cost-pricing` and `dealer_lr=0.01` (`n14-03113`)

## Why we tried it
Tonight produced three winning branches on top of `origin/exp/gemini-n14-02114-stack-gates-trust-notes` (`stack-gtn-ptw38-dev`, `€10,029.58/wk`):
1. **`origin/exp/gemini-n14-03111-adaptive-delivery-buffer-and-alarm` (`€10,508.07/wk`, `Δmargin €+1,517.77 ± 201.53, t = 7.53`, 16/16 better, worst on-time 95.8% SAFE):**
   - `delivery_buffer_min=30, buffer_min_slack_min=210` shaves 30 min off delivery stop windows only when slack >= 210 min (cutting late arrivals without increasing `gig_expired`), and `pre_warn_lead_min=60, pre_warn_fee=1.35` nudges unstaffed orders on their deadline day 60 min before `deadline_close`.
2. **`origin/exp/gemini-n14-02462-deadline-aware-backlog` (`€10,481.58/wk`, `Δmargin €+1,491.27 ± 252.93, t = 5.90`, 15/16 better, worst on-time 95.35% SAFE):**
   - `backlog_multiday_weight=0.25` stops unurgent multi-day orders from blocking afternoon intake while `backlog_in_flight_weight=0.35` caps simultaneous bulk yard batches.
3. **`origin/exp/gemini-n14-02461-centered-lane-cost-pricing` (`€10,262.15/wk`, `Δmargin €+1,271.84 ± 217.21, t = 5.86`, `+€232.56 ± 113.31` vs `stack-gtn-ptw38-dev`) & `dealer_lr=0.01` (`n14-03113` Dev 1, `+€235.96 ± 120.09, t = 1.96` vs `stack-gtn-ptw38-dev`):**
   - `lane_dest_tilt=0.035` marks up thin-destination lanes (`+3.5%`) and discounts dense-hub deliveries (`-5.25%`), while `dealer_lr=0.01` reduces per-dealer step noise.

We merged all three branches into a single unified codebase so every mechanism is available via `Params` overrides (with defaults reproducing Champion v2 bit-for-bit) and tested whether their gains stack additively at `price_target_win=0.40, min_supply=22` or interact through local driver capacity and `Desk.learn()` win-count crowding.

## What changed
Merged `origin/exp/gemini-n14-03111-adaptive-delivery-buffer-and-alarm`, `origin/exp/gemini-n14-02462-deadline-aware-backlog`, and `origin/exp/gemini-n14-02461-centered-lane-cost-pricing` into `exp/gemini-n14-03504-stack-v6-buf-alarm-backlog-lane`, resolving the single merge conflict in `Desk.rejoin()` (`src/spread_lab/policy.py`) so that `rejoin()` cleanly reconstructs both `self.pre_warned` and `self.lost_requests` alongside `self.dealer_trust`, `self.dealer_request_count`, and `self.urgent`. All new `Params` fields default to `0` / `1.0` / `False` and reproduce Champion v2 with `Δmargin €+0.00 ± 0.00` on smoke (`runs/20261114-040358-v6-grand-noop`).

Let `<BASE>` be:
`-s trust_invest=0.05 -s notes_v2=True -s note_unsure=decline -s max_next_day_drive_min=480 -s fri_same_day_max_drive=100 -s thin_long_next_day_supply=50 -s ring_to_hub_same_day_min=60 -s same_day_min_supply=50 -s min_slack_min=150 -s slack_per_drive=0.75 -s price_target_win=0.40 -s min_supply=22`

Evaluated configurations on `dev` (16 level-8 seeds):
- **Dev 1 (`v6-buf-alarm-backlog-dev`):** `<BASE> -s delivery_buffer_min=30 -s buffer_min_slack_min=210 -s pre_warn_lead_min=60 -s pre_warn_fee=1.35 -s backlog_multiday_weight=0.25 -s backlog_in_flight_weight=0.35`
- **Dev 2 (`v6-buf-alarm-backlog-lane-dev`):** Dev 1 + `-s lane_dest_tilt=0.035`
- **Dev 3 (`v6-buf-alarm-backlog-lane-dlr01-dev`):** Dev 2 + `-s dealer_lr=0.01`
- **Dev 4 (`v6-grand-slack140-dev`):** Dev 1 + `-s min_slack_min=140`

## Results (level 8, vs champion v2, paired)
| set | run folder | mean margin | Δmargin ± SE | t | better/worse | on-time min (mean, Δ) | SAFE |
|---|---|---:|---:|---:|---:|---:|---|
| smoke (noop) | `runs/20261114-040358-v6-grand-noop` | €9,662.25 | €+0.00 ± 0.00 | — | 0 / 0 | 95.5% (96.7%, +0.00%) | yes |
| smoke 1 (`buf+alarm+backlog`) | `runs/20261114-040518-v6-buf-alarm-backlog-smoke` | €11,170.90 | €+1,508.65 ± 499.95 | 3.02 | 4 / 0 | 95.8% (97.5%, +0.80%) | yes |
| smoke 2 (`+lane_dest_tilt=0.035`) | `runs/20261114-040658-v6-buf-alarm-backlog-lane-smoke` | €11,028.36 | €+1,366.11 ± 479.15 | 2.85 | 4 / 0 | 96.2% (97.1%, +0.44%) | yes |
| smoke 3 (`+ptw=0.42, ms=20`) | `runs/20261114-040723-v6-grand-ptw42-ms20-smoke` | €10,867.31 | €+1,205.06 ± 713.40 | 1.69 | 3 / 1 | 93.4% (96.7%, +0.00%) | yes |
| **dev Dev 1 (`v6-buf-alarm-backlog-dev`)** | `runs/20261114-040928-v6-buf-alarm-backlog-dev` | **€10,350.24** | **€+1,359.93 ± 191.35** | **7.11** | **15 / 1** | **95.8% (97.6%, +0.84%)** | **yes** |
| **dev Dev 2 (`v6-buf-alarm-backlog-lane-dev`)** | `runs/20261114-041052-v6-buf-alarm-backlog-lane-dev` | **€10,066.84** | **€+1,076.53 ± 293.82** | **3.66** | **12 / 4** | **94.9% (97.2%, +0.47%)** | **yes** |
| **dev Dev 3 (`v6-buf-alarm-backlog-lane-dlr01-dev`)** | `runs/20261114-041202-v6-buf-alarm-backlog-lane-dlr01-dev` | **€10,313.10** | **€+1,322.79 ± 205.90** | **6.42** | **15 / 1** | **94.6% (97.4%, +0.62%)** | **yes** |
| **dev Dev 4 (`v6-grand-slack140-dev`)** | `runs/20261114-041400-v6-grand-slack140-dev` | **€10,389.38** | **€+1,399.07 ± 207.52** | **6.74** | **15 / 1** | **95.8% (97.4%, +0.68%)** | **yes** |

### Head-to-head `uv run lab compare` against parent dev champions (16 paired seeds)
| Run (`A`) vs Baseline (`B`) | Mean Margin `A` vs `B` | Paired `Δmargin ± SE` | `t` | Better / Worse | `Δon-time` |
|---|---:|---:|---:|---:|---:|
| **Dev 1 (`v6-buf-alarm-backlog-dev`)** vs `stack-gtn-ptw38-dev` (`€10,029.58`) | €10,350.24 vs €10,029.58 | **€+320.66 ± 177.27** | **1.81** | **11 / 5** | **+0.27%** |
| **Dev 4 (`v6-grand-slack140-dev`)** vs `stack-gtn-ptw38-dev` (`€10,029.58`) | €10,389.38 vs €10,029.58 | **€+359.80 ± 178.47** | **2.02** | **11 / 5** | **+0.12%** |
| **Dev 1 (`v6-buf-alarm-backlog-dev`)** vs `gtn-ptw40-buf-alarm-dev` (`€10,508.07`) | €10,350.24 vs €10,508.07 | €-157.84 ± 77.10 | -2.05 | 3 / 12 | -0.12% |
| **Dev 4 (`v6-grand-slack140-dev`)** vs `gtn-ptw40-buf-alarm-dev` (`€10,508.07`) | €10,389.38 vs €10,508.07 | €-118.70 ± 81.92 | -1.45 | 4 / 11 | -0.27% |
| **Dev 1 (`v6-buf-alarm-backlog-dev`)** vs `backlog-aware-gtn-ptw40-dev` (`€10,481.58`) | €10,350.24 vs €10,481.58 | €-131.34 ± 154.15 | -0.85 | 6 / 10 | **+0.16%** |
| **Dev 4 (`v6-grand-slack140-dev`)** vs `backlog-aware-gtn-ptw40-dev` (`€10,481.58`) | €10,389.38 vs €10,481.58 | €-92.20 ± 144.71 | -0.64 | 6 / 10 | **+0.00%** |
| **Dev 2 (`v6-buf-alarm-backlog-lane-dev`)** vs `gtn-ptw40-buf-alarm-dev` (`€10,508.07`) | €10,066.84 vs €10,508.07 | €-441.24 ± 189.14 | -2.33 | 5 / 11 | -0.49% |
| **Dev 2 (`v6-buf-alarm-backlog-lane-dev`)** vs `backlog-aware-gtn-ptw40-dev` (`€10,481.58`) | €10,066.84 vs €10,481.58 | €-414.74 ± 179.09 | -2.32 | 5 / 11 | -0.22% |
| **Dev 3 (`v6-buf-alarm-backlog-lane-dlr01-dev`)** vs `gtn-ptw40-buf-alarm-dev` (`€10,508.07`) | €10,313.10 vs €10,508.07 | €-194.98 ± 129.11 | -1.51 | 6 / 10 | -0.34% |
| **Dev 3 (`v6-buf-alarm-backlog-lane-dlr01-dev`)** vs `backlog-aware-gtn-ptw40-dev` (`€10,481.58`) | €10,313.10 vs €10,481.58 | €-168.48 ± 166.88 | -1.01 | 6 / 10 | -0.06% |
| **Dev 3 (`+dealer_lr=0.01`)** vs **Dev 2 (`lane_dest_tilt=0.035`)** | €10,313.10 vs €10,066.84 | **€+246.26 ± 149.38** | **1.65** | **12 / 4** | **+0.15%** |

### Complete `stats` counters and ledger breakdown on dev (16 worlds total / mean per world)
| Metric / Counter | Champion v2 | `gtn-ptw40-buf-alarm-dev` (`n14-03111`) | `backlog-aware-gtn-ptw40-dev` (`n14-02462`) | **Dev 1 (`v6-buf-alarm-backlog-dev`)** | Dev 2 (`+lane_dest_tilt=0.035`) | Dev 3 (`+lane + dealer_lr=0.01`) | **Dev 4 (`v6-grand-slack140-dev`)** |
|---|---:|---:|---:|---:|---:|---:|---:|
| **Mean margin (€/world)** | €8,990.31 | **€10,508.07** | **€10,481.58** | **€10,350.24** | €10,066.84 | €10,313.10 | **€10,389.38** |
| **Worst-seed margin (€)** | €6,017.30 | **€7,523.75** | €7,196.05 | €7,166.73 | €6,874.27 | **€7,353.05** | €6,733.04 |
| **On-time min / mean (%)** | 94.36% / 96.75% | **95.80% / 97.71%** | 95.35% / 97.43% | **95.77% / 97.59%** | 94.87% / 97.21% | 94.64% / 97.37% | **95.82% / 97.43%** |
| Active won orders (`won` /w) | 3,644 (227.75/w) | 4,331 (270.69/w) | 4,370 (273.12/w) | **4,370 (273.12/w)** | 4,323 (270.19/w) | 4,353 (272.06/w) | **4,371 (273.19/w)** |
| Total `stats["won"]` (total /w) | 3,682 (230.12/w) | 4,376 (273.50/w) | 4,417 (276.06/w) | **4,414 (275.88/w)** | 4,367 (272.94/w) | 4,396 (274.75/w) | **4,415 (275.94/w)** |
| **Total late orders (late %)** | 118 (7.38/w, 3.24%) | **99 (6.19/w, 2.29%)** | 113 (7.06/w, 2.59%) | **105 (6.56/w, 2.40%)** | 121 (7.56/w, 2.80%) | 115 (7.19/w, 2.64%) | **112 (7.00/w, 2.56%)** |
| `buffered_stops` (total /w) | 0 (0.00/w) | 4,300 (268.75/w) | 0 (0.00/w) | **4,338 (271.12/w)** | 4,293 (268.31/w) | 4,325 (270.31/w) | **4,325 (270.31/w)** |
| `pre_warned` (total /w) | 0 (0.00/w) | 192 (12.00/w) | 0 (0.00/w) | **204 (12.75/w)** | 221 (13.81/w) | 219 (13.69/w) | **211 (13.19/w)** |
| `offers` / `offer_accepted` | 0 / 0 | 384 / 7 | 0 / 0 | **408 / 5** | 442 / 8 | 438 / 4 | **422 / 3** |
| `declined_backlog` (total /w) | — | — | 62 (3.88/w) | **50 (3.12/w)** | 49 (3.06/w) | 59 (3.69/w) | **57 (3.56/w)** |
| `in_flight_blocked` (total /w) | 0 (0.00/w) | 0 (0.00/w) | 49 (3.06/w) | **43 (2.69/w)** | 37 (2.31/w) | 54 (3.38/w) | **42 (2.62/w)** |
| `lane_thin_dest` (options /w) | 0 (0.00/w) | 0 (0.00/w) | 0 (0.00/w) | 0 (0.00/w) | 8,109 (506.81/w) | 8,114 (507.12/w) | 0 (0.00/w) |
| `lane_hub_dest` (options /w) | 0 (0.00/w) | 0 (0.00/w) | 0 (0.00/w) | 0 (0.00/w) | 5,881 (367.56/w) | 5,868 (366.75/w) | 0 (0.00/w) |
| `won_lane_thin_dest` (orders /w) | — | — | — | **2,391 (149.44/w)** | 2,087 (130.44/w) | 2,086 (130.38/w) | **2,402 (150.12/w)** |
| `won_lane_hub_dest` (orders /w) | — | — | — | **1,204 (75.25/w)** | 1,485 (92.81/w) | 1,496 (93.50/w) | **1,191 (74.44/w)** |
| `won_same_day` (total /w) | 1,147 (71.69/w) | 1,665 (104.06/w) | 1,684 (105.25/w) | **1,681 (105.06/w)** | 1,729 (108.06/w) | 1,747 (109.19/w) | **1,687 (105.44/w)** |
| `won_next_day` (total /w) | 2,362 (147.62/w) | 2,515 (157.19/w) | 2,531 (158.19/w) | **2,537 (158.56/w)** | 2,440 (152.50/w) | 2,450 (153.12/w) | **2,538 (158.62/w)** |
| `won_within_3_days` (total /w) | 173 (10.81/w) | 196 (12.25/w) | 202 (12.62/w) | **196 (12.25/w)** | 198 (12.38/w) | 199 (12.44/w) | **190 (11.88/w)** |
| `won_ring` / `late_ring` | 823 / 17 | 1,046 / 21 | 1,052 / 20 | **1,045 / 18 (1.72%)** | 1,089 / 30 | 1,096 / 26 | **1,037 / 21** |
| `won_ring_hub_same_day` / late | 0 / 0 | 228 / 6 | 233 / 6 | **228 / 2 (0.88%!)** | 304 / 7 | 302 / 9 | **227 / 4 (1.76%)** |
| `deadline_close` warnings | 193 (12.06/w) | 241 (15.06/w) | 225 (14.06/w) | **264 (16.50/w)** | 292 (18.25/w) | 294 (18.38/w) | **259 (16.19/w)** |
| `gig_expired` | 121 (7.56/w) | 119 (7.44/w) | 105 (6.56/w) | **132 (8.25/w)** | 140 (8.75/w) | 138 (8.62/w) | **132 (8.25/w)** |
| `visit_failed` | 73 (4.56/w) | 8 (0.50/w) | 6 (0.38/w) | 12 (0.75/w) | 3 (0.19/w) | 11 (0.69/w) | 11 (0.69/w) |
| Ledger `revenue` (€/world) | +26,922.43 | +29,650.81 | +29,806.67 | **+29,960.46** | +28,914.64 | +29,186.53 | **+29,994.78** |
| Ledger `driver_fee` (€/world) | -17,286.92 | -18,776.97 | -18,955.63 | -19,194.68 | -18,326.83 | -18,425.44 | -19,174.69 |
| Ledger `late_refund` (€/world) | -376.20 | **-260.38** | **-259.44** | -304.11 | -373.64 | -293.05 | -324.69 |
| Ledger `failed_visit` (€/world) | -165.44 | -21.21 | -12.62 | -29.49 | -9.61 | -29.48 | -29.28 |
| Ledger `release_fee` (€/world) | -53.48 | -53.21 | -57.55 | -52.85 | -48.59 | **-41.83** | -49.14 |
| Ledger `waiting` (€/world) | -39.38 | -20.73 | -24.38 | -18.86 | -32.28 | -22.50 | **-17.38** |

### Key Mechanistic Insights
1. **Why `buf_alarm` (`€10,508.07/w`) and `backlog` (`€10,481.58/w`) are sub-additive (`€10,350.24/w` in Dev 1, `€10,389.38/w` in Dev 4) when enabled simultaneously:**
   - Both `n14-03111` (`buf_alarm`) and `n14-02462` (`backlog`) achieved their `~+€450–€480/w` gain over `stack-gtn-ptw38-dev` (`€10,029.58/w`) primarily by **unlocking `price_target_win=0.40, min_supply=22`**, raising active won orders from `256.00/w` to `270.69/w` (`buf_alarm`) and `273.12/w` (`backlog`).
   - When combined in **Dev 1 (`v6-buf-alarm-backlog-dev`)**, `backlog_multiday_weight=0.25` admits `+2.44/w` additional multi-day afternoon orders in busy pickup yards (`won` rises from `270.69/w` to `273.12/w`, and `revenue` reaches **`€29,960.46/w`**, `+€309.65/w` above `buf_alarm`). However, adding those extra orders into local pickup yards where existing orders have **30-minute tighter delivery stop windows (`delivery_buffer_min=30`)** and **pre-warning fee nudges (`pre_warn_lead_min=60, pre_warn_fee=1.35`)** increases local driver contention:
     - `pre_warned` rises from `192` (`12.00/w`) to `204` (`12.75/w`),
     - `deadline_close` warnings rise from `241` (`15.06/w`) to `264` (`16.50/w`),
     - `gig_expired` rises from `119` (`7.44/w`) to `132` (`8.25/w`),
     - and `driver_fee` rises by `-€417.71/w` (`-€18,776.97 → -€19,194.68/w`), outweighing the `+€309.65/w` revenue gain (`Δmargin = €-157.84 ± 77.10` vs `gtn-ptw40-buf-alarm-dev`).
   - Lowering `min_slack_min=140` in **Dev 4 (`v6-grand-slack140-dev`)** reaches **`€29,994.78/w` revenue** and **`€10,389.38/w` margin (`Δmargin €+1,399.07 ± 207.52, t = 6.74`, 15/16 better vs Champion v2; `Δmargin €+359.80 ± 178.47, t = 2.02` vs `stack-gtn-ptw38-dev`, worst on-time `95.8%`)**.
2. **Why `lane_dest_tilt=0.035` crowded out high-revenue orders at fixed `ptw=0.40` (Dev 2), and how `dealer_lr=0.01` (Dev 3) recovered `+€246.26/w`:**
   - In Dev 2 (`v6-buf-alarm-backlog-lane-dev`), `lane_dest_tilt=0.035` shifted `won_lane_hub_dest` up by `+17.56/w` (`75.25/w → 92.81/w`) and `won_ring_hub_same_day` up by `+4.75/w` (`14.25/w → 19.00/w`), while reducing `won_lane_thin_dest` by `-19.00/w` (`149.44/w → 130.44/w`). Because `price_target_win=0.40` counts every won order equally (`+1` in `Desk.learn()`), trading 19 larger thin-destination orders for 18 smaller short-haul hub orders lowered `revenue` by `-€1,045.82/w` (`€29,960.46 → €28,914.64/w`).
   - Adding `dealer_lr=0.01` in **Dev 3 (`v6-buf-alarm-backlog-lane-dlr01-dev`)** damped per-dealer step noise and recovered **`+€246.26 ± 149.38/w` (`t = 1.65`, 12/16 seeds better than Dev 2)**, cutting `late_refund` by `€80.59/w` (`-€373.64 → -€293.05/w`) and lifting worst-seed margin from `€6,874.27` to **`€7,353.05`**.

## Verdict
**adopt unified codebase (`src/spread_lab/policy.py`), promote with `gtn-ptw40-buf-alarm-dev` (`€10,508.07/w`) params** — The unified v6 codebase cleanly supports all three branches' flags with zero-diff defaults (`Δ = +0.00`), while on 16 dev seeds `v6-grand-slack140-dev` (`€10,389.38/w, Δmargin €+1,399.07 ± 207.52, t = 6.74, 15/16 better, worst on-time 95.8%`) and `v6-buf-alarm-backlog-dev` (`€10,350.24/w, Δmargin €+1,359.93 ± 191.35, t = 7.11, 15/16 better, worst on-time 95.8%`) show that `n14-03111` alone (`gtn-ptw40-buf-alarm-dev`, `€10,508.07/w, Δmargin €+1,517.77 ± 201.53, t = 7.53, 16/16 better, worst on-time 95.8%`) remains +€118.70 to +€157.84/w stronger than enabling `backlog_multiday_weight=0.25` simultaneously.
