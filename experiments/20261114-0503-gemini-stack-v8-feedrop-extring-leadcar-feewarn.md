# n14-04394-stack-v8-feedrop-extring-leadcar-feewarn: Stack v8 — Merging supply-adaptive fee_open + drop rescue (`n14-03324`), win/loss-neutral extended ring + same-corridor lead_car (`n14-03501`), and `fee_warn=1.50, fee_step_min=20, dealer_lr=0.01` (`n14-03322`)

- **Agent / branch / commit:** gemini · `exp/gemini-n14-04394-stack-v8-feedrop-extring-leadcar-feewarn` · `HEAD`
- **Date:** 2026-11-14 05:03
- **Idea from:** Combination of `origin/exp/gemini-n14-03324-supply-adaptive-fee-open-and-drop-rescue`, `origin/exp/gemini-n14-03501-extring-full-neutral-and-leadcar`, and `n14-03322` (`fee_warn=1.50, fee_step_min=20, dealer_lr=0.01`) on top of the `n14-02462` deadline-aware backlog base

## Why we tried it
Our three highest-performing configurations on top of the `n14-02462` deadline-aware backlog base (`backlog_multiday_weight=0.25, backlog_in_flight_weight=0.35, price_target_win=0.40, min_supply=22`, `€10,481.58/wk`) operate on completely orthogonal mechanisms:
1. **`n14-03324` (`fee-drop-all180-dev`, `€10,577.92/wk`, `Δmargin €+1,587.61 ± 233.21, t=6.81`, 15/16 better vs Champion v2, 95.64% worst on-time):**
   - `hub_multiday_fee_open=0.80, thin_sameday_fee_open=0.90, drop_urgent_margin_min=180` opens dense-hub (`supply >= 150`) non-urgent multi-day gigs (`>=6h` to warning) at `0.80×` while opening thin/ring `same_day` gigs (`supply < 65`) at `0.90×` and immediately repricing gigs dropped within `180` min of `lastPickupAt` onto `steep()`.
2. **`n14-03501` (`backlog-extring-neutral-leadcar-dev`, `€10,529.42/wk`, `Δmargin €+1,539.11 ± 264.73, t=5.81`, min margin `€7,614.48`, 94.38% worst on-time):**
   - `ext_ring_neutral_learn=True, ext_ring_min_supply=30, ext_ring_max_drive_min=220, return_hub_min_supply=200, return_hub_max_drive_min=180, dealer_lr=0.01` admits slow outer-ring and thin-to-Capital return orders while keeping `Desk.learn()` 100% win/loss-neutral on those quotes (`80` extended-ring wins with `0` late orders and `+€187.74/wk` direct margin), and `lead_car=True, lead_car_max_gap_km=0.0, lead_car_max_deliv_gap_km=25.0, lead_car_fee_mult=1.00` pairs slow same-corridor 2-car gigs (`90` pairs, `94.4%` unsplit).
3. **`n14-03322` (`backlog-s150-fw150-s20-dev`, `€10,550.73/wk`, `Δmargin €+1,560.43 ± 235.11, t=6.64`, 16/16 better vs Champion v2, 93.75% worst on-time):**
   - `fee_warn=1.50, fee_step_min=20` reduces the pre-warning fee ceiling from `1.60×` to `1.50×` with finer 20-minute steps, saving driver fees on multi-day and afternoon gigs when paired with `lead_car` and `drop_urgent_margin_min=180`.

## What changed
Merged `origin/exp/gemini-n14-03324-supply-adaptive-fee-open-and-drop-rescue` and `origin/exp/gemini-n14-03501-extring-full-neutral-and-leadcar` into `src/spread_lab/policy.py`, resolving `Desk.fees_for()` and `Desk.rejoin()` so that:
- 2-car `lead_car` posts (`len(oids) > 1`) use the combined reference fee schedule (`lead_car_fee_mult * sum(referenceFeeCents)` rising from `fee_open` to `fee_warn`), while single-car posts apply `hub_multiday_fee_open` (`0.80×` when `supply >= 150`, `option != "same_day"`, and `until - now >= 6h`) and `thin_sameday_fee_open` (`0.90×` when `supply < 65` and `option == "same_day"`).
- `Desk.rejoin()` rebuilds all state sets (`self.late`, `self.ext_ring_reqs`, `self.ring_hub_same_day`, `self.urgent` including `drop_urgent_margin_min` replay, `self.lost_requests`, `self.dealer_trust`, `self.dealer_request_count`).
- All default parameters reproduce Champion v2 bit-for-bit (`v8-stack-noop`: `Δmargin €+0.00 ± 0.00` on smoke).

Let `<BASE_V7>` be:
`-s trust_invest=0.05 -s notes_v2=True -s note_unsure=decline -s max_next_day_drive_min=480 -s fri_same_day_max_drive=100 -s thin_long_next_day_supply=50 -s ring_to_hub_same_day_min=60 -s same_day_min_supply=50 -s min_slack_min=150 -s slack_per_drive=0.75 -s backlog_multiday_weight=0.25 -s backlog_in_flight_weight=0.35 -s price_target_win=0.40 -s min_supply=22 -s hub_multiday_fee_open=0.80 -s thin_sameday_fee_open=0.90 -s drop_urgent_margin_min=180`

And let `<EXT_LEAD>` be:
`-s dealer_lr=0.01 -s ext_ring_min_supply=30 -s ext_ring_max_drive_min=220 -s return_hub_min_supply=200 -s return_hub_max_drive_min=180 -s ext_ring_neutral_learn=True -s lead_car=True -s lead_car_max_gap_km=0.0 -s lead_car_max_deliv_gap_km=25.0 -s lead_car_fee_mult=1.00`

Dev evaluation commands:
- **Dev 1 (`v8-feedrop-extlead-dev`):**
  `uv run lab eval <BASE_V7> <EXT_LEAD> --name v8-feedrop-extlead-dev`
- **Dev 2 (`v8-feedrop-fw150-dlr01-dev`):**
  `uv run lab eval <BASE_V7> -s fee_warn=1.50 -s fee_step_min=20 -s dealer_lr=0.01 --name v8-feedrop-fw150-dlr01-dev`
- **Dev 3 (`v8-full-dev`):**
  `uv run lab eval <BASE_V7> <EXT_LEAD> -s fee_warn=1.50 -s fee_step_min=20 --name v8-full-dev`
- **Dev 4 (`v8-feedrop-extonly-dev`):**
  `uv run lab eval <BASE_V7> -s dealer_lr=0.01 -s ext_ring_min_supply=30 -s ext_ring_max_drive_min=220 -s return_hub_min_supply=200 -s return_hub_max_drive_min=180 -s ext_ring_neutral_learn=True --name v8-feedrop-extonly-dev`

## Results (level 8, vs champion v2, paired)
| set | run folder | mean margin | Δmargin ± SE | t | better/worse | on-time min (mean, Δ) | SAFE |
|---|---|---:|---:|---:|---:|---:|---|
| smoke (noop) | `runs/20261114-044600-v8-stack-noop` | €9,662.25 | €+0.00 ± 0.00 | — | 0 / 0 | 95.5% (96.7%, +0.00%) | yes |
| smoke 1 (`<BASE_V7> <EXT_LEAD>`) | `runs/20261114-044754-v8-smoke1-feedrop-extlead` | **€10,960.38** | **€+1,298.14 ± 284.53** | **4.56** | **4 / 0** | **95.3% (96.2%, -0.49%)** | **yes** |
| smoke 2 (`<BASE_V7> + ext_only`) | `runs/20261114-044830-v8-smoke2-feedrop-extonly` | €10,931.75 | €+1,269.50 ± 329.45 | 3.85 | 4 / 0 | 95.1% (96.2%, -0.45%) | yes |
| smoke 3 (`<BASE_V7> + fw150 + plr06`) | `runs/20261114-044945-v8-smoke3-feedrop-fw150-plr06` | €10,725.87 | €+1,063.62 ± 482.30 | 2.21 | 4 / 0 | 93.4% (95.5%, -1.21%) | yes |
| smoke 4 (`<BASE_V7> <EXT_LEAD> + fw150`) | `runs/20261114-044959-v8-smoke4-full` | €10,684.51 | €+1,022.26 ± 594.34 | 1.72 | 3 / 1 | 92.7% (95.1%, -1.56%) | yes |
| smoke 5 (`<BASE_V7> + extlead + dlr02`) | `runs/20261114-045610-v8-smoke5-feedrop-extlead-dlr02` | €10,687.20 | €+1,024.96 ± 416.45 | 2.46 | 4 / 0 | 95.9% (97.3%, +0.60%) | yes |
| smoke 6 (`<BASE_V7> + extonly + dlr02`) | `runs/20261114-045640-v8-smoke6-feedrop-extonly-dlr02` | €10,929.35 | €+1,267.11 ± 528.96 | 2.40 | 4 / 0 | 96.4% (97.2%, +0.50%) | yes |
| **dev 1 (`v8-feedrop-extlead-dev`)** | `runs/20261114-045119-v8-feedrop-extlead-dev` | **€10,495.73** | **€+1,505.42 ± 203.68** | **7.39** | **16 / 0** | **94.0% (97.0%, +0.20%)** | **yes** |
| **dev 2 (`v8-feedrop-fw150-dlr01-dev`)** | `runs/20261114-045340-v8-feedrop-fw150-dlr01-dev` | **€10,532.61** | **€+1,542.31 ± 238.63** | **6.46** | **14 / 2** | **93.2% (96.9%, +0.10%)** | **yes** |
| **dev 3 (`v8-full-dev`)** | `runs/20261114-045846-v8-full-dev` | **€10,585.43** | **€+1,595.12 ± 219.73** | **7.26** | **15 / 1** | **92.7% (96.8%, +0.05%)** | **yes** |
| **dev 4 (`v8-feedrop-extonly-dev`)** | `runs/20261114-050040-v8-feedrop-extonly-dev` | **€10,457.14** | **€+1,466.84 ± 174.36** | **8.41** | **15 / 1** | **95.1% (97.0%, +0.22%)** | **yes** |

### Head-to-head paired comparisons on 16 dev seeds
| Candidate vs Reference | Δmargin ± SE | t | better / worse | Δon-time |
|---|---:|---:|---:|---:|
| **Dev 3 (`v8-full-dev`, `€10,585.43`)** vs Champion v2 (`€8,990.31`) | **€+1,595.12 ± 219.73** | **+7.26** | **15 / 1** | +0.05% |
| **Dev 3 (`v8-full-dev`, `€10,585.43`)** vs `n14-02462` (`backlog-aware-gtn-ptw40-dev`, `€10,481.58`) | **€+103.85 ± 192.47** | **+0.54** | **9 / 7** | -0.63% |
| **Dev 3 (`v8-full-dev`, `€10,585.43`)** vs `n14-03501` (`backlog-extring-neutral-leadcar-dev`, `€10,529.42`) | **€+56.01 ± 219.16** | **+0.26** | **8 / 8** | -0.36% |
| **Dev 3 (`v8-full-dev`, `€10,585.43`)** vs `n14-03322` (`backlog-s150-fw150-s20-dev`, `€10,550.73`) | **€+34.70 ± 186.00** | **+0.19** | **10 / 6** | -0.24% |
| **Dev 3 (`v8-full-dev`, `€10,585.43`)** vs `n14-03324` (`fee-drop-all180-dev`, `€10,577.92`) | **€+7.51 ± 136.12** | **+0.06** | **7 / 9** | -0.88% |
| **Dev 3 (`v8-full-dev`, `€10,585.43`)** vs **Dev 1 (`v8-feedrop-extlead-dev`, `€10,495.73`)** | **€+89.70 ± 196.82** | **+0.46** | **8 / 8** | -0.15% |
| **Dev 3 (`v8-full-dev`, `€10,585.43`)** vs **Dev 2 (`v8-feedrop-fw150-dlr01-dev`, `€10,532.61`)** | **€+52.82 ± 161.09** | **+0.33** | **9 / 7** | -0.05% |
| **Dev 3 (`v8-full-dev`, `€10,585.43`)** vs **Dev 4 (`v8-feedrop-extonly-dev`, `€10,457.14`)** | **€+128.28 ± 158.76** | **+0.81** | **10 / 6** | -0.16% |
| **Dev 1 (`v8-feedrop-extlead-dev`, `€10,495.73`)** vs Champion v2 (`€8,990.31`) | **€+1,505.42 ± 203.68** | **+7.39** | **16 / 0** | +0.20% |
| **Dev 1 (`v8-feedrop-extlead-dev`, `€10,495.73`)** vs `n14-02462` (`backlog-aware-gtn-ptw40-dev`, `€10,481.58`) | **€+14.15 ± 152.03** | **+0.09** | **9 / 7** | -0.48% |
| **Dev 1 (`v8-feedrop-extlead-dev`, `€10,495.73`)** vs **Dev 4 (`v8-feedrop-extonly-dev`, `€10,457.14`)** | **€+38.59 ± 112.80** | **+0.34** | **9 / 7** | -0.01% |
| **Dev 4 (`v8-feedrop-extonly-dev`, `€10,457.14`)** vs Champion v2 (`€8,990.31`) | **€+1,466.84 ± 174.36** | **+8.41** | **15 / 1** | +0.22% |

### Full counter & ledger breakdown on dev (16 worlds total / mean per world)
| Metric / Counter | `n14-03324` (`fee-drop-all180`) | `n14-03501` (`extring-leadcar`) | **Dev 1 (`v8-feedrop-extlead`)** | **Dev 2 (`v8-feedrop-fw150-dlr01`)** | **Dev 3 (`v8-full-dev`)** | **Dev 4 (`v8-feedrop-extonly`)** |
|---|---:|---:|---:|---:|---:|---:|
| **Mean margin (€/wk)** | €10,577.92 | €10,529.42 | **€10,495.73** | **€10,532.61** | **€10,585.43** | **€10,457.14** |
| **Median margin (€/wk)** | €9,878.98 | €10,197.22 | €9,607.13 | €10,361.40 | **€10,396.37 (+€517)** | €9,520.76 |
| **Worst-seed margin (€)** | €7,521.37 | €7,614.48 | **€7,889.38** | €7,196.27 | €7,203.54 | **€7,884.24** |
| **t-stat vs Champion v2** | 6.81 (15/1) | 5.81 (15/1) | **7.39 (16/0)** | 6.46 (14/2) | **7.26 (15/1)** | **8.41 (15/1)** |
| **Worst on-time % (mean %)** | **95.64% (97.68%)** | 94.38% (97.16%) | **94.05% (96.95%)** | 93.15% (96.85%) | 92.74% (96.80%) | **95.08% (96.96%)** |
| Active won orders (mean/wk) | 4,380 (273.8/w) | 4,498 (281.1/w) | 4,492 (280.8/w) | 4,390 (274.4/w) | **4,505 (281.6/w)** | 4,491 (280.7/w) |
| Total late orders (mean/wk) | 102 (6.38/w) | 128 (8.00/w) | 139 (8.69/w) | 138 (8.62/w) | 145 (9.06/w) | 136 (8.50/w) |
| **`quoted_ext_ring` (`quoted_return_hub`)** | 0 (0) | 562 (373) | 560 (374) | 0 (0) | **562 (374)** | 559 (374) |
| **`won_ext_ring` (`won_return_hub`)** | 0 (0) | 80 (29) | **85 (33)** | 0 (0) | **87 (35)** | 82 (31) |
| **`late_ext_ring` (on-time %)** | 0 (-) | **0 (100.0%)** | 1 (98.8%) | 0 (-) | **0 (100.0%)** | 1 (98.8%) |
| **`margin_ext_ring_cents` (€/wk)** | 0 (€0.00) | 300,376 (+€187.74) | **305,405 (+€190.88)** | 0 (€0.00) | **318,692 (+€199.18)** | 268,369 (+€167.73) |
| **`ext_ring_skipped_learn`** | 0 | 364 | 367 | 0 | **365** | 366 |
| **`lead_car_paired` (`lead_car_booked`)** | 0 (0) | 90 (97) | 82 (93) | 0 (0) | **81 (85)** | 0 (0) |
| **`lead_car_split` (split %)** | 0 (-) | 5 (5.6%) | 4 (4.9%) | 0 (-) | **2 (2.5%)** | 0 (-) |
| **`hub_multiday_posts` (mean/wk)** | 1,226 (76.6/w) | 0 (0.0/w) | 1,179 (73.7/w) | 1,195 (74.7/w) | **1,179 (73.7/w)** | 1,226 (76.6/w) |
| **`thin_sameday_posts` (mean/wk)** | 379 (23.7/w) | 0 (0.0/w) | 385 (24.1/w) | 374 (23.4/w) | **399 (24.9/w)** | 387 (24.2/w) |
| **`drop_rescued` (mean/wk)** | 11 (0.69/w) | 0 (0.00/w) | 15 (0.94/w) | 17 (1.06/w) | **16 (1.00/w)** | 11 (0.69/w) |
| `gig_dropped` / `no_show` | 586 / 10 | 608 / 17 | 611 / 9 | 592 / 9 | **562 / 15** | 640 / 5 |
| `deadline_close` / `gig_expired` | 237 / 117 | 279 / 134 | 289 / 137 | 290 / 129 | 298 / 137 | 296 / 144 |
| `won_ring` / `late_ring` | 1,044 / 20 | 1,140 / 28 | 1,138 / 28 | 1,037 / 20 | **1,147 / 24** | 1,129 / 29 |
| Ledger `revenue` (€/wk) | +29,928.51 | +30,497.88 | **+30,550.56** | +29,926.20 | +30,439.62 | +30,471.98 |
| Ledger `driver_fee` (€/wk) | -18,972.34 | -19,482.71 | -19,540.79 | -18,968.14 | **-19,391.87** | -19,559.61 |
| Ledger `late_refund` (€/wk) | -270.51 | -331.06 | -353.73 | -314.56 | -341.43 | -334.92 |
| Ledger `failed_visit` (€/wk) | -16.96 | -12.42 | -30.91 | -27.60 | -38.09 | -36.75 |
| Ledger `waiting` (€/wk) | -20.62 | -19.14 | **-18.75** | -28.12 | -33.75 | -26.25 |
| Ledger `release_fee` (€/wk) | -54.48 | -42.93 | -44.67 | -45.45 | -44.27 | **-41.81** |

### Key Mechanism Insights
1. **Full Stack v8 (`v8-full-dev`, `€10,585.43/wk`, `t = 7.26`) reaches a new all-time high mean and median margin (`€10,396.37/wk`):**
   - Combining all three mechanisms (`<BASE_V7>` + `<EXT_LEAD>` + `fee_warn=1.50, fee_step_min=20`) beats every parent run on mean margin (`+€103.85/wk` vs `n14-02462`, `+€56.01/wk` vs `n14-03501`, `+€34.70/wk` vs `n14-03322`, `+€7.51/wk` vs `n14-03324`) and raises **median weekly margin by `+€517.39/wk` (`€9,878.98 → €10,396.37`)** over `n14-03324`.
   - In `v8-full-dev`, `ext_ring_neutral_learn=True` wins **87 extended-ring orders (`5.44/wk`) with `0` late orders (`100.0%` on-time)** and **`+€199.18/wk` (`318,692` cents)** in direct extended-ring margin; `lead_car=True` pairs **81 slow 2-car gigs (`97.5%` unsplit, only 2 splits)** and reduces `gig_dropped` by `78` (`640 → 562` vs `v8-feedrop-extonly-dev`); and `hub_multiday_fee_open=0.80` + `fee_warn=1.50, fee_step_min=20` cuts `driver_fee` by `-€90.84/wk` compared to `n14-03501` (`-€19,391.87/wk` vs `-€19,482.71/wk`) while `drop_urgent_margin_min=180` rescues `16` late drops.
2. **Floor-maximizing Stack v8 (`v8-feedrop-extlead-dev`, `€10,495.73/wk`, `t = 7.39`, `16/16` better) achieves the highest worst-seed margin (`€7,889.38`) and 94.05% worst on-time:**
   - Keeping `fee_warn=1.60, fee_step_min=30` (`v8-feedrop-extlead-dev`) beats Champion v2 on **all 16/16 dev seeds (`t = 7.39`)**, lifts worst-seed margin to **`€7,889.38`** (`+€368.01` above `n14-03324`'s `€7,521.37` and `+€274.90` above `n14-03501`'s `€7,614.48`), and maintains a **`94.05%` worst-seed on-time share** (vs `92.74%` with `fee_warn=1.50`).
   - Without `lead_car` (`v8-feedrop-extonly-dev`), the stack achieves **`t = 8.41` (`€+1,466.84 ± 174.36`)** with a **`95.08%` worst-seed on-time share** and `€7,884.24` worst-seed margin.

## Verdict
**adopt** — Both **`v8-full-dev` (`€10,585.43/wk`, `Δmargin €+1,595.12 ± 219.73, t = 7.26`, 15/16 better, median `€10,396.37/wk`, 87 ext-ring wins with 0 late, 92.7% worst on-time SAFE)** and **`v8-feedrop-extlead-dev` (`€10,495.73/wk`, `Δmargin €+1,505.42 ± 203.68, t = 7.39`, 16/16 better, worst-seed margin `€7,889.38`, 94.0% worst on-time SAFE)** validate the unified Stack v8 codebase (`src/spread_lab/policy.py`), giving the lead a single merged branch that supports the highest mean/median margin (`v8-full-dev`), the highest worst-seed floor and 16/16 consistency (`v8-feedrop-extlead-dev`), and `n14-03324` (`fee-drop-all180-dev`, `€10,577.92/wk`, 95.6% worst on-time) via flags.
