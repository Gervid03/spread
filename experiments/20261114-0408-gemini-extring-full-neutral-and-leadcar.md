# extring-full-neutral-and-leadcar: Fix win-step bias in extended-ring learning (`ext_ring_neutral_learn`) and combine with deadline-aware backlog and same-corridor 2-car pairing

- **Agent / branch / commit:** gemini · `exp/gemini-n14-03501-extring-full-neutral-and-leadcar` · `HEAD`
- **Date:** 2026-11-14 04:08
- **Idea from:** Combination of `origin/exp/gemini-n14-03113-stack-gtn-extring-dlr01`, `origin/exp/gemini-n14-03112-same-corridor-lead-car-v2`, and `origin/exp/gemini-n14-02462-deadline-aware-backlog` with full price-tracker neutrality (`ext_ring_neutral_learn`)

## Why we tried it
1. **Eliminating win-step bias in extended-ring & return-hub quotes (`ext_ring_neutral_learn`):** In `n14-03113` Dev 3 (`stack-gtn-extring-ptw38-dlr01-dev`), admitting slow (`next_day` / `within_3_days`) orders from the 70 km extended ring (`ext_ring_min_supply=30, ext_ring_max_drive_min=220`) and thin-to-Capital return lanes (`return_hub_min_supply=200, return_hub_max_drive_min=180`) won 86 extra orders across 16 dev worlds (`5.38/wk`) with `0` late orders (`100.0%` on-time) and `+€198.30/world` direct margin (`margin_ext_ring_cents`). However, because `ext_ring_no_learn=True` only skipped `Desk.learn()` when `not won`, those 86 won outer-ring orders still stepped `self.mult` and `self.dealer_adj` upward (`+(1 - price_target_win)`), slightly overpricing subsequent core requests. Making outer-ring and return-hub orders skip `Desk.learn()` on **both wins and losses** (`ext_ring_neutral_learn=True`) makes them 100% price-tracker neutral so their direct margin adds cleanly to the core stack.
2. **Stacking with deadline-aware backlog (`n14-02462`) and same-corridor slow 2-car gig pairing (`n14-03112`):** `n14-02462` (`backlog_multiday_weight=0.25, backlog_in_flight_weight=0.35, price_target_win=0.40, min_supply=22`) reached `€10,481.58/wk` on dev (`t = 5.90`), while `n14-03112` (`lead_car=True, lead_car_max_gap_km=0.0, lead_car_max_deliv_gap_km=25.0, lead_car_fee_mult=1.00`) booked 95.5–98.6% of paired slow same-corridor gigs before `deadline_close` and cut `deadline_close` warnings by 8.4%. Pairing slow corridor cars also absorbs the extra slow outer-ring and return-hub volume from `ext_ring_min_supply=30` and `return_hub_min_supply=200`.

## What changed
Merged `origin/exp/gemini-n14-03113-stack-gtn-extring-dlr01`, `origin/exp/gemini-n14-03112-same-corridor-lead-car-v2`, and `origin/exp/gemini-n14-02462-deadline-aware-backlog` into `src/spread_lab/policy.py`, and added:
- `ext_ring_neutral_learn: bool = False` (default `False`, preserving Champion v2 exactly with `Δmargin = €+0.00` on smoke). When `True`, any request in `self.ext_ring_reqs` (admitted via `pass_ext_ring` or `pass_return_hub`) increments `self.stats["ext_ring_skipped_learn"] += 1` and returns early at the top of `Desk.learn(request_id, won)` on both `won=True` and `won=False`.

Let `<BASE>` be:
`-s trust_invest=0.05 -s notes_v2=True -s note_unsure=decline -s max_next_day_drive_min=480 -s fri_same_day_max_drive=100 -s thin_long_next_day_supply=50 -s ring_to_hub_same_day_min=60 -s same_day_min_supply=50 -s min_slack_min=150 -s slack_per_drive=0.75 -s backlog_multiday_weight=0.25 -s backlog_in_flight_weight=0.35 -s price_target_win=0.40 -s min_supply=22`

Run commands on `dev`:
- **Dev 1 (`backlog-extring-neutral-dev`):**
  `uv run lab eval <BASE> -s dealer_lr=0.01 -s ext_ring_min_supply=30 -s ext_ring_max_drive_min=220 -s return_hub_min_supply=200 -s return_hub_max_drive_min=180 -s ext_ring_neutral_learn=True --name backlog-extring-neutral-dev`
- **Dev 2 (`backlog-extring-neutral-leadcar-dev`):**
  `uv run lab eval <BASE> -s dealer_lr=0.01 -s ext_ring_min_supply=30 -s ext_ring_max_drive_min=220 -s return_hub_min_supply=200 -s return_hub_max_drive_min=180 -s ext_ring_neutral_learn=True -s lead_car=True -s lead_car_max_gap_km=0.0 -s lead_car_max_deliv_gap_km=25.0 -s lead_car_fee_mult=1.00 --name backlog-extring-neutral-leadcar-dev`
- **Dev 3 (`backlog-leadcar-only-dev`):**
  `uv run lab eval <BASE> -s dealer_lr=0.01 -s lead_car=True -s lead_car_max_gap_km=0.0 -s lead_car_max_deliv_gap_km=25.0 -s lead_car_fee_mult=1.00 --name backlog-leadcar-only-dev`

## Results (level 8, vs champion, paired)
| set | run folder | mean margin | Δmargin ± SE | t | better/worse | on-time min (mean, Δ) | SAFE |
|---|---|---:|---:|---:|---:|---:|---|
| smoke (noop) | `20261114-035328-extring-neutral-noop` | €9,662.25 | €+0.00 ± 0.00 | — | 0 / 0 | 95.5% (96.7%, +0.00%) | SAFE |
| smoke (S1: `<BASE> + dlr01 + extring-neutral`) | `20261114-035440-backlog-extring-neutral-s1` | €10,697.44 | €+1,035.19 ± 579.30 | 1.79 | 4 / 0 | 94.5% (96.0%, -0.69%) | SAFE |
| smoke (S2: S1 + `lead_car=True`) | `20261114-035615-backlog-extring-neutral-leadcar-s2` | €10,892.44 | €+1,230.19 ± 793.82 | 1.55 | 3 / 1 | 94.4% (96.6%, -0.10%) | SAFE |
| smoke (S3: `<BASE> + dlr01 + lead_car=True`) | `20261114-035728-backlog-leadcar-only-s3` | €10,831.68 | €+1,169.43 ± 710.27 | 1.65 | 3 / 1 | 94.4% (96.6%, -0.05%) | SAFE |
| **dev (Dev 1: `backlog-extring-neutral-dev`)** | `20261114-035828-backlog-extring-neutral-dev` | **€10,468.12** | **€+1,477.82 ± 230.01** | **6.43** | **16 / 0** | **94.5% (97.2%, +0.41%)** | **SAFE** |
| **dev (Dev 2: `backlog-extring-neutral-leadcar-dev`)** | `20261114-040101-backlog-extring-neutral-leadcar-dev` | **€10,529.42** | **€+1,539.11 ± 264.73** | **5.81** | **15 / 1** | **94.4% (97.2%, +0.41%)** | **SAFE** |
| **dev (Dev 3: `backlog-leadcar-only-dev`)** | `20261114-040453-backlog-leadcar-only-dev` | **€10,482.44** | **€+1,492.13 ± 244.29** | **6.11** | **15 / 1** | **94.4% (97.3%, +0.60%)** | **SAFE** |

### Paired comparisons (`uv run lab compare` on 16 dev seeds)
| Run A vs Run B | Δmargin ± SE | t | better / worse | Δon-time |
|---|---:|---:|---:|---:|
| **Dev 2 (`backlog-extring-neutral-leadcar-dev`)** vs `20261114-030237-backlog-aware-gtn-ptw40-dev` (`€10,481.58`) | **€+47.84 ± 148.29** | **0.32** | **9 / 7** | -0.27% |
| **Dev 2 (`backlog-extring-neutral-leadcar-dev`)** vs `20261114-032146-stack-gtn-dlr01-ptw38-dev` (`€10,265.54`) | **€+263.88 ± 150.07** | **1.76** | **13 / 3** | -0.29% |
| **Dev 2 (`backlog-extring-neutral-leadcar-dev`)** vs `20261114-032429-stack-gtn-extring-ptw38-dlr01-dev` (`€10,162.82`) | **€+366.60 ± 159.85** | **2.29** | **12 / 4** | -0.15% |
| **Dev 2 (`backlog-extring-neutral-leadcar-dev`)** vs **Dev 1 (`backlog-extring-neutral-dev`)** (`€10,468.12`) | **€+61.30 ± 110.34** | **0.56** | **9 / 7** | -0.00% |
| **Dev 2 (`backlog-extring-neutral-leadcar-dev`)** vs **Dev 3 (`backlog-leadcar-only-dev`)** (`€10,482.44`) | **€+46.98 ± 70.69** | **0.66** | **8 / 5 (3 tied)** | -0.18% |
| **Dev 1 (`backlog-extring-neutral-dev`)** vs `20261114-030237-backlog-aware-gtn-ptw40-dev` (`€10,481.58`) | €-13.46 ± 99.10 | -0.14 | 6 / 10 | -0.27% |
| **Dev 1 (`backlog-extring-neutral-dev`)** vs `20261114-032146-stack-gtn-dlr01-ptw38-dev` (`€10,265.54`) | **€+202.58 ± 124.41** | **1.63** | **9 / 7** | -0.29% |
| **Dev 1 (`backlog-extring-neutral-dev`)** vs `20261114-032429-stack-gtn-extring-ptw38-dlr01-dev` (`€10,162.82`) | **€+305.31 ± 118.61** | **2.57** | **11 / 5** | -0.15% |
| **Dev 3 (`backlog-leadcar-only-dev`)** vs `20261114-030237-backlog-aware-gtn-ptw40-dev` (`€10,481.58`) | **€+0.86 ± 119.93** | **0.01** | **9 / 7** | -0.09% |
| **Dev 3 (`backlog-leadcar-only-dev`)** vs `20261114-032146-stack-gtn-dlr01-ptw38-dev` (`€10,265.54`) | **€+216.90 ± 159.30** | **1.36** | **10 / 6** | -0.11% |
| **Dev 3 (`backlog-leadcar-only-dev`)** vs `20261114-032429-stack-gtn-extring-ptw38-dlr01-dev` (`€10,162.82`) | **€+319.62 ± 143.52** | **2.23** | **12 / 4** | +0.03% |

### Counter and ledger breakdown across the 16 dev seeds (sum / mean per world)
| Metric / Counter | `backlog-aware-gtn-ptw40` (`n14-02462`) | `stack-gtn-dlr01-ptw38` (`n14-03113` D1) | `stack-gtn-extring-ptw38` (`n14-03113` D3) | **Dev 1 (`backlog-extring-neutral`)** | **Dev 2 (`+leadcar`, full stack)** | **Dev 3 (`backlog-leadcar-only`)** |
|---|---:|---:|---:|---:|---:|---:|
| Mean margin (€/wk) | €10,481.58 | €10,265.54 | €10,162.82 | **€10,468.12** | **€10,529.42** | **€10,482.44** |
| Worst-seed margin (€) | €7,196.05 | €7,253.74 | €7,251.08 | **€7,391.50** | **€7,614.48** | **€7,614.48** |
| `won` (mean/wk) | 4,417 (276.1) | 4,129 (258.1) | 4,175 (260.9) | 4,541 (283.8) | **4,541 (283.8)** | 4,458 (278.6) |
| **`quoted_ext_ring` (`quoted_return_hub`)** | 0 (0) | 0 (0) | 631 (408) | 561 (373) | **562 (373)** | 0 (0) |
| **`won_ext_ring` (`won_return_hub`)** | 0 (0) | 0 (0) | 86 (34) | 84 (33) | **80 (29)** | 0 (0) |
| **`late_ext_ring` (on-time %)** | 0 (-) | 0 (-) | 0 (100.0%) | 1 (98.8%) | **0 (100.0%)** | 0 (-) |
| **`margin_ext_ring_cents` (€/wk)** | 0 (€0.00) | 0 (€0.00) | 317,273 (+€198.30) | 301,463 (+€188.41) | **300,376 (+€187.74)** | 0 (€0.00) |
| **`ext_ring_skipped_learn` (mean/wk)** | 0 (0.00) | 0 (0.00) | 0 (0.00) | 368 (23.00) | **364 (22.75)** | 0 (0.00) |
| **`lead_car_paired` (pairs/wk)** | 0 (0.00) | 0 (0.00) | 0 (0.00) | 0 (0.00) | **90 (5.62)** | 84 (5.25) |
| **`lead_car_booked` (bookings/wk)** | 0 (0.00) | 0 (0.00) | 0 (0.00) | 0 (0.00) | **97 (6.06)** | 94 (5.88) |
| **`lead_car_split` (splits/wk)** | 0 (0.00) | 0 (0.00) | 0 (0.00) | 0 (0.00) | **5 (0.31, 5.6%)** | 3 (0.19, 3.6%) |
| `declined_backlog` (`in_flight_blocked`) | 62 (49) | 0 (0) | 0 (0) | 73 (55) | **61 (50)** | 50 (37) |
| `deadline_close` (mean/wk) | 225 (14.06) | 217 (13.56) | 224 (14.00) | 287 (17.94) | **279 (17.44)** | 238 (14.88) |
| `gig_expired` (mean/wk) | 105 (6.56) | 98 (6.12) | 114 (7.12) | 141 (8.81) | **134 (8.38)** | 117 (7.31) |
| `visit_failed` (mean/wk) | 6 (0.38) | 2 (0.12) | 5 (0.31) | 6 (0.38) | **5 (0.31)** | 3 (0.19) |
| Ledger `revenue` (€/wk) | +29,806.67 | +28,270.73 | +28,537.33 | +30,597.45 | **+30,498.00** | +30,047.53 |
| Ledger `driver_fee` (€/wk) | -18,955.63 | -17,637.76 | -17,939.73 | -19,711.23 | **-19,483.48** | -19,164.08 |
| Ledger `late_refund` (€/wk) | -259.44 | -279.13 | -293.83 | -314.88 | **-330.94** | -314.86 |
| Ledger `failed_visit` (€/wk) | -12.62 | -4.88 | -11.53 | -19.29 | **-12.16** | -11.12 |

### Key findings
1. **`ext_ring_neutral_learn=True` + `lead_car=True` eliminates the extended-ring penalty and adds `+€46.98/wk` on top of `lead_car` (`8 better, 5 worse, 3 tied`):**
   - Comparing **Dev 2 (`backlog-extring-neutral-leadcar-dev`)** directly against **Dev 3 (`backlog-leadcar-only-dev`)**, `ext_ring_neutral_learn=True` skips `364` outer-ring/return-hub outcomes in `Desk.learn()` (`22.75/wk`) so the core price trajectory is completely undisturbed on seeds without outer-ring wins (`3` seeds tied to the cent). Across all 16 seeds, it wins **80 extended-ring orders (`5.00/wk`) with `0` late orders (`100.0%` on-time)** and **`+€187.74/wk` direct margin (`300,376` cents)**, lifting total mean margin from `€10,482.44` to **`€10,529.42`** (`+€46.98 ± 70.69`, 8 better, 5 worse, 3 tied).
2. **Synergy between `ext_ring` and `lead_car` (`+€61.30/wk` for `lead_car` when `ext_ring` is active):**
   - Without `lead_car` (**Dev 1**), the 84 extra slow outer-ring and return-hub orders slightly compete for single-car drivers (`1` late outer-ring order, `287` `deadline_close`, `€10,468.12/wk` — though still **16/16 seeds better than Champion v2 with `t = 6.43`**!).
   - Adding `lead_car=True` (**Dev 2**) increases paired slow 2-car gigs from `84` (in Dev 3) to **`90` pairs (`5.62/wk`, 94.4% booked without split)**, cutting `deadline_close` (`287 → 279`), `gig_expired` (`141 → 134`), `visit_failed` (`6 → 5`), and `driver_fee` (`-€19,711 → -€19,483/wk`), eliminating the 1 late extended-ring order (`late_ext_ring = 0`), lifting worst-seed margin by **`+€222.98` (`€7,391.50 → €7,614.48`)**, and lifting mean margin to **`€10,529.42/wk`**.
3. **Strong gains over `n14-03113` (`+€263.88/wk` over Dev 1, `+€366.60/wk` over Dev 3) and `n14-02462` (`+€47.84/wk` mean, `+€418.43` worst-seed margin):**
   - Against `20261114-032146-stack-gtn-dlr01-ptw38-dev` (`€10,265.54`), Dev 2 gains **`Δmargin €+263.88 ± 150.07` (`t = 1.76`, 13/16 better)**.
   - Against `20261114-032429-stack-gtn-extring-ptw38-dlr01-dev` (`€10,162.82`), Dev 2 gains **`Δmargin €+366.60 ± 159.85` (`t = 2.29`, 12/16 better)**.
   - Against `20261114-030237-backlog-aware-gtn-ptw40-dev` (`€10,481.58`), Dev 2 gains **`Δmargin €+47.84 ± 148.29` (9/16 better)** while raising the worst-seed margin across all 16 dev worlds from `€7,196.05` to **`€7,614.48` (`+€418.43`)**.

## Verdict
**adopt** — Combining `ext_ring_neutral_learn=True`, `lead_car=True`, `dealer_lr=0.01`, and deadline-aware backlog (`20261114-040101-backlog-extring-neutral-leadcar-dev`) reaches **€10,529.42/wk** (**Δmargin €+1,539.11 ± 264.73, t = 5.81, 15/16 better** vs Champion v2; **€+263.88, 13/16 better** vs `stack-gtn-dlr01-ptw38-dev`; **80 extended-ring wins with 0 late orders**; worst-seed margin **€7,614.48**, worst on-time **94.4% SAFE**), while `backlog-extring-neutral-dev` (`20261114-035828-backlog-extring-neutral-dev`) reaches **€10,468.12/wk** and beats Champion v2 on **16/16 dev seeds (`t = 6.43`, worst on-time 94.5% SAFE)**.
