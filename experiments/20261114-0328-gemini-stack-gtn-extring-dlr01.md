# stack-gtn-extring-dlr01: Merge €10,030/wk GTN stack with extended-ring/return-hub gates and dealer_lr=0.01

- **Agent / branch / commit:** gemini · `exp/gemini-n14-03113-stack-gtn-extring-dlr01` · `66554de`
- **Date:** 2026-11-14 03:28
- **Idea from:** Combination of `exp/gemini-n14-02114-stack-gates-trust-notes` (`+€1,039.28, t=4.53`), `exp/gemini-n14-02242-extended-ring-and-return-gate` (`+€552.22, t=2.66`), and `exp/gemini-n14-02241-exact-trust-and-floor-v2` (`dealer_lr=0.01, t=3.77`)

## Why we tried it
We have three dev-verified winners on separate branches that attack orthogonal aspects of Level 8:
1. **`n14-02114` (GTN stack):** combines `notes_v2=True, note_unsure=decline`, `trust_invest=0.05`, surgical class-table gates (`max_next_day_drive_min=480, fri_same_day_max_drive=100, thin_long_next_day_supply=50, ring_to_hub_same_day_min=60`), and `min_slack_min=150, slack_per_drive=0.75, same_day_min_supply=50`, reaching `€9,814.03` (`+€823.72, t=3.67`) at `price_target_win=0.35, min_supply=30` and `€10,029.58` (`+€1,039.28, t=4.53`) at `price_target_win=0.38, min_supply=25`.
2. **`n14-02242` (extended ring & thin-to-Capital return gate):** admits slow (`next_day`/`within_3_days`) orders outside the 55 km gate radius when `ext_ring_min_supply=30, ext_ring_max_drive_min=220` (70 km ring) or `return_hub_min_supply=200, return_hub_max_drive_min=180` (delivering into the Capital hub) with strict `backlog_near(pickup) < 2`. Diagnostic analysis on `n14-02242` showed that lost `return_hub` probes (`8.4%` win rate) stepped `self.mult` down in `Desk.learn()`. Adding `ext_ring_no_learn=True` prevents lost `ext_ring`/`return_hub` probes from depressing `self.mult` or `self.dealer_adj` on core orders.
3. **`n14-02241` (`dealer_lr=0.01`):** halving the per-dealer online multiplier step from `0.02` to `0.01` reduces per-dealer overfitting noise while `trust_invest=0.05` handles dealer trust building.

## What changed
Merged `origin/exp/gemini-n14-02114-stack-gates-trust-notes` and `origin/exp/gemini-n14-02242-extended-ring-and-return-gate` in `src/spread_lab/policy.py`, keeping all parameters and counters from both branches, and added two new `Params` fields whose defaults preserve champion v2 behavior exactly (`Δmargin = €+0.00` on smoke):
- `ext_ring_no_learn: bool = False` — when `True`, requests admitted via `pass_ext_ring` or `pass_return_hub` (tracked in `self.ext_ring_reqs`) return early in `Desk.learn(request_id, won)` when `not won`, so lost outer-ring/return-hub probes never step `self.mult` or `self.dealer_adj` down or inflate `self.loss_streak`.
- `return_hub_discount: float = 0.0` — when `> 0` and `pass_return_hub` (and `not pass_ext_ring`), multiplies `option_mult` by `1.0 - p.return_hub_discount`.

Run with:
- **Dev 1 (`stack-gtn-dlr01-ptw38-dev`):**
  `uv run lab eval -s trust_invest=0.05 -s notes_v2=True -s note_unsure=decline -s max_next_day_drive_min=480 -s fri_same_day_max_drive=100 -s thin_long_next_day_supply=50 -s ring_to_hub_same_day_min=60 -s same_day_min_supply=50 -s min_slack_min=150 -s slack_per_drive=0.75 -s price_target_win=0.38 -s min_supply=25 -s dealer_lr=0.01 --name stack-gtn-dlr01-ptw38-dev`
- **Dev 2 (`stack-gtn-extring-dlr01-dev`):**
  `uv run lab eval -s trust_invest=0.05 -s notes_v2=True -s note_unsure=decline -s max_next_day_drive_min=480 -s fri_same_day_max_drive=100 -s thin_long_next_day_supply=50 -s ring_to_hub_same_day_min=60 -s same_day_min_supply=50 -s min_slack_min=150 -s slack_per_drive=0.75 -s dealer_lr=0.01 -s ext_ring_min_supply=30 -s ext_ring_max_drive_min=220 -s return_hub_min_supply=200 -s return_hub_max_drive_min=180 -s ext_ring_no_learn=True --name stack-gtn-extring-dlr01-dev`
- **Dev 3 (`stack-gtn-extring-ptw38-dlr01-dev`):**
  `uv run lab eval -s trust_invest=0.05 -s notes_v2=True -s note_unsure=decline -s max_next_day_drive_min=480 -s fri_same_day_max_drive=100 -s thin_long_next_day_supply=50 -s ring_to_hub_same_day_min=60 -s same_day_min_supply=50 -s min_slack_min=150 -s slack_per_drive=0.75 -s price_target_win=0.38 -s min_supply=25 -s dealer_lr=0.01 -s ext_ring_min_supply=30 -s ext_ring_max_drive_min=220 -s return_hub_min_supply=200 -s return_hub_max_drive_min=180 -s ext_ring_no_learn=True --name stack-gtn-extring-ptw38-dlr01-dev`

## Results (level 8, vs champion, paired)
| set | run folder | mean margin | Δmargin ± SE | t | better/worse | on-time min | SAFE |
|---|---|---|---|---|---|---|---|
| smoke (noop) | `20261114-031651-stack-gtn-ext-noop` | €9,662.25 | €+0.00 ± 0.00 | - | 0/0 | 95.5% | SAFE |
| smoke (S1: GTN Run 2 + extring + dlr01 + no_learn) | `20261114-031737-stack-gtn-extring-dlr01-s1` | €10,683.60 | €+1,021.36 ± 502.60 | 2.03 | 4/0 | 96.4% | SAFE |
| smoke (S2: S1 + return_hub_discount=0.04) | `20261114-031926-stack-gtn-extring-dlr01-s2` | €10,683.08 | €+1,020.83 ± 500.95 | 2.04 | 4/0 | 96.4% | SAFE |
| smoke (S3: S1 + ptw=0.38, min_supply=25) | `20261114-032031-stack-gtn-extring-ptw38-dlr01-s3` | €10,576.23 | €+913.98 ± 496.50 | 1.84 | 3/1 | 92.2% | SAFE |
| **dev (Dev 1: GTN Run 3 + dlr01)** | `20261114-032146-stack-gtn-dlr01-ptw38-dev` | **€10,265.54** | **€+1,275.23 ± 225.86** | **5.65** | **14/2** | **92.2%** | **SAFE** |
| **dev (Dev 2: GTN Run 2 + extring + dlr01 + no_learn)** | `20261114-032329-stack-gtn-extring-dlr01-dev` | **€9,952.51** | **€+962.21 ± 219.56** | **4.38** | **15/1** | **94.8%** | **SAFE** |
| **dev (Dev 3: Full stack Dev 1 + extring + no_learn)** | `20261114-032429-stack-gtn-extring-ptw38-dlr01-dev` | **€10,162.82** | **€+1,172.51 ± 244.32** | **4.80** | **14/2** | **92.2%** | **SAFE** |

### Paired comparisons against `n14-02114` dev runs
- **Dev 1 (`20261114-032146-stack-gtn-dlr01-ptw38-dev`) vs `20261114-022434-stack-gtn-ptw38-dev` (`€10,029.58`):**
  - **Δmargin €+235.96 ± 120.09 (`t = 1.96`, 10 better, 6 worse, Δon-time `+0.13%`)**
  - Adding `dealer_lr=0.01` alone on top of our €10,030/wk stack adds **+€235.96/wk** and improves mean on-time share by `+0.13%` (to `97.5%`), reaching **€10,265.54/wk** (`+€1,275.23 ± 225.86, t=5.65` vs champion).
- **Dev 1 (`20261114-032146-stack-gtn-dlr01-ptw38-dev`) vs `20261114-022233-stack-gtn-slack-sdsup-dev` (`€9,814.03`):**
  - **Δmargin €+451.52 ± 205.07 (`t = 2.20`, 12 better, 4 worse, Δon-time `-0.82%`)**
- **Dev 2 (`20261114-032329-stack-gtn-extring-dlr01-dev`) vs `20261114-022233-stack-gtn-slack-sdsup-dev` (`€9,814.03`):**
  - **Δmargin €+138.49 ± 135.55 (`t = 1.02`, 11 better, 5 worse, Δon-time `-0.59%`, worst on-time up from `94.6%` to `94.8%`)**
  - Beats the champion on **15 of 16 seeds** (`t = 4.38`) with a `94.8%` worst-seed on-time floor (`97.7%` mean on-time).
- **Dev 3 (`20261114-032429-stack-gtn-extring-ptw38-dlr01-dev`) vs `20261114-022434-stack-gtn-ptw38-dev` (`€10,029.58`):**
  - **Δmargin €+133.23 ± 152.98 (`t = 0.87`, 10 better, 6 worse, Δon-time `-0.00%`)**
- **Dev 3 (`20261114-032429-stack-gtn-extring-ptw38-dlr01-dev`) vs `20261114-022233-stack-gtn-slack-sdsup-dev` (`€9,814.03`):**
  - **Δmargin €+348.79 ± 211.10 (`t = 1.65`, 12 better, 4 worse, Δon-time `-0.95%`)**

### Counter and ledger breakdown across the 16 dev seeds
| metric (16-seed sum) | `Dev 1 (dlr01-ptw38)` | `Dev 2 (extring-dlr01)` | `Dev 3 (extring-ptw38-dlr01)` |
|---|---:|---:|---:|
| `won` (mean/world) | 4,129 (255.7) | 3,858 (238.8) | 4,175 (258.6) |
| `quoted_ext_ring` (`quoted_return_hub`) | 0 (0) | 715 (435) | 631 (408) |
| `won_ext_ring` (`won_return_hub`) | 0 (0) | 89 (28) | 86 (34) |
| `late_ext_ring` (on-time %) | 0 (-) | 2 (97.8%) | **0 (100.0%)** |
| `margin_ext_ring_cents` (mean/world) | 0 (€0.00) | 318,855 (+€199.28) | 317,273 (+€198.30) |
| `quoted_ring_hub_same_day` | 654 | 654 | 654 |
| `won_ring_hub_same_day` (`late`) | 203 (3) | 191 (2) | 203 (3) |
| `visit_failed` | 2 | 2 | 5 |
| `deadline_close` | 217 | 180 | 224 |

Why does `Dev 1` (`min_supply=25, price_target_win=0.38` without `ext_ring`) edge out `Dev 3` (`€10,265.54` vs `€10,162.82`) even though `Dev 3` wins 86 extended-ring orders with **0 late orders (`100.0%` on-time)** and `+€198.30/world` direct margin? Because when `min_supply=25` is already active (lowering the 55 km gate threshold from 30 to 25), part of the inner extended ring is already captured by `min_supply=25`, and because `ext_ring_no_learn=True` only skips `learn()` on losses (`not won`), the 86 won outer-ring orders still step `self.mult` upward (`+(1 - price_target_win)`), slightly raising prices on subsequent core orders. When `min_supply=30, price_target_win=0.35` (`Dev 2`), `ext_ring + dealer_lr=0.01` lifts mean margin to `€9,952.51` (`+€962.21, t=4.38`, 15/16 better, worst on-time `94.8%`).

## Verdict
**adopt** — `Dev 1` (`stack-gtn-dlr01-ptw38-dev`) sets a new dev high of **€10,265.54/wk** (**Δmargin €+1,275.23 ± 225.86, t=5.65**, 14/16 better, min on-time `92.2%` SAFE, `+€235.96/wk` over `n14-02114` Run 3), while `Dev 2` (`stack-gtn-extring-dlr01-dev`) provides an ultra-safe **€9,952.51/wk** option (**Δmargin €+962.21 ± 219.56, t=4.38**, **15/16 better**, min on-time `94.8%` SAFE), and `Dev 3` (`stack-gtn-extring-ptw38-dlr01-dev`) reaches **€10,162.82/wk** (**Δmargin €+1,172.51 ± 244.32, t=4.80**, 14/16 better, `0` late orders on 86 extended-ring wins).
