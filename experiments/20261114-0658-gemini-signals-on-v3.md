# signals-on-v3: Free signals the desk throws away (ready_from_deadline, eligible_supply, use_release) on Champion v3

- **Agent / branch / commit:** gemini · `exp/gemini-n14-06262-signals-on-v3`
- **Date:** 2026-11-14 06:58 UTC
- **Idea from:** `experiments/IDEAS.md` #23, "Free signals the desk throws away", parts (a), (b), and (c)

## Why we tried it
Idea #23 targets three free world signals that v0/v2 threw away:
1. **(a) `ready_from_deadline`:** When a dealer note delays a car's readiness by a day or more, `order_won` already carries the shifted `order["deadline"]` (`shift_business_days` by the note's real delay). Moving the first pickup window's `from` forward by `delay_days * DAY` (at least `day_start` of that day) and applying any note clock time onto that moved day aims to avoid early `not_ready` failed visits before `retry_from()`.
2. **(b) `eligible_supply`:** Premium cars require experienced drivers (`rating >= 4.8 and completedGigs >= 50`), and manual-gearbox notes require manual-licence drivers (`d.get("manualLicence", True)` / `licence == "manual"`). Counting only eligible drivers in the supply tables (`supply`, `gate_supply`, `ext_supply`) for the main gate, extended ring, return hub, same-day rules, `is_ring`, and backlog cap avoids quoting premium or manual orders where general supply passes the gate but eligible driver density is too thin.
3. **(c) `use_release`:** Recording `release` events per `(orderId, leg)` in `self.release_at` (and rebuilding from `history` in `rejoin()`) ensures that any retry after a failed visit (or re-post of a leg with a known release time) aligns `pickup_from` with `release_at` (never earlier if in the future, or `self.now` if already released).

## What changed
Added three independent boolean fields to `Params` in `src/spread_lab/policy.py`, all defaulting to `False` (reproducing Champion v3 with `Δ = +0.00` across all smoke seeds):
- `ready_from_deadline: bool = False` (counter: `ready_moved`)
- `eligible_supply: bool = False` (counters recorded even when `False`: `prem_q`, `prem_won`, `prem_late`, `manual_q`, `manual_won`, `manual_late`)
- `use_release: bool = False` (counter: `release_aligned`)

Run commands:
- `uv run lab eval --seeds-from smoke --name signals-noop`
- `uv run lab eval --seeds-from smoke -s ready_from_deadline=True --name signals-s1-ready`
- `uv run lab eval --seeds-from smoke -s eligible_supply=True --name signals-s2-elig`
- `uv run lab eval --seeds-from smoke -s use_release=True --name signals-s3-release`
- `uv run lab eval --seeds-from smoke -s ready_from_deadline=True -s eligible_supply=True -s use_release=True --name signals-s4-all`
- `uv run lab eval -s ready_from_deadline=True -s eligible_supply=True -s use_release=True --name signals-all-dev`
- `uv run lab eval -s eligible_supply=True --name signals-elig-dev`

## Results (level 8, vs Champion v3, paired)
Champion v3 baseline: smoke mean margin `€10,892.44`, worst on-time `94.42%` (`96.59%` mean); dev mean margin `€10,529.42`, worst on-time `94.38%` (`97.16%` mean).

| set | run folder | flags | mean margin | Δmargin ± SE | t | better/worse | on-time min | mean on-time | SAFE |
|---|---|---|---|---|---|---|---|---|---|
| smoke | `20261114-065254-signals-noop` | defaults (`False`) | €10,892.44 | €+0.00 ± 0.00 | — | 0/0 | 94.42% | 96.59% | yes |
| smoke | `20261114-065355-signals-s1-ready` | `ready_from_deadline=True` | €10,397.83 | €-494.61 ± 422.11 | -1.17 | 1/3 | 94.53% | 95.94% | yes |
| smoke | `20261114-065420-signals-s2-elig` | `eligible_supply=True` | €10,786.91 | €-105.53 ± 202.97 | -0.52 | 2/2 | 96.30% | 97.04% | yes |
| smoke | `20261114-065500-signals-s3-release` | `use_release=True` | €10,892.44 | €+0.00 ± 0.00 | — | 0/0 | 94.42% | 96.59% | yes |
| smoke | `20261114-065509-signals-s4-all` | all three `True` | €10,353.51 | €-538.93 ± 386.98 | -1.39 | 1/3 | 95.20% | 96.26% | yes |
| dev | `20261114-065559-signals-all-dev` | all three `True` | €10,324.89 | €-204.53 ± 162.97 | -1.26 | 5/11 | 94.46% | 97.27% | yes |
| dev | `20261114-065716-signals-elig-dev` | `eligible_supply=True` | €10,478.79 | €-50.63 ± 146.36 | -0.35 | 7/9 | 95.35% | 97.50% | yes |

### Counters, failed visits, ledger breakdown, and late orders
| Run | Seeds | Won (tot / mean) | Total late (tot / mean) | `visit_failed_not_ready` | `visit_failed` (all `closed`) | Ledger `failed_visit` (sum / mean) | Ledger `waiting` (sum / mean) | `prem_q` / `prem_won` / `prem_late` | `manual_q` / `manual_won` / `manual_late` | `ready_moved` / `release_aligned` |
|---|---|---|---|---|---|---|---|---|---|---|
| Champion v3 (smoke) | 4 | 1,149 / 287.2 | 38 / 9.50 | 0 | 2 | €-76.64 / €-19.16 | €-90.00 / €-22.50 | 161 / 71 / 6 | 33 / 15 / 0 | 0 / 0 |
| `signals-s1-ready` (smoke) | 4 | 1,148 / 287.0 | 45 / 11.25 | 0 | 6 | €-211.88 / €-52.97 | €-60.00 / €-15.00 | 161 / 67 / 6 | 33 / 15 / 0 | 9 / 0 |
| `signals-s2-elig` (smoke) | 4 | 1,117 / 279.2 | 33 / 8.25 | 0 | 0 | €0.00 / €0.00 | €-120.00 / €-30.00 | 50 / 16 / 1 | 32 / 17 / 0 | 0 / 0 |
| `signals-s3-release` (smoke) | 4 | 1,149 / 287.2 | 38 / 9.50 | 0 | 2 | €-76.64 / €-19.16 | €-90.00 / €-22.50 | 161 / 71 / 6 | 33 / 15 / 0 | 0 / 0 |
| `signals-s4-all` (smoke) | 4 | 1,113 / 278.2 | 41 / 10.25 | 0 | 0 | €0.00 / €0.00 | €-90.00 / €-22.50 | 47 / 16 / 0 | 32 / 16 / 0 | 8 / 0 |
| Champion v3 (dev) | 16 | 4,498 / 281.1 | 128 / 8.00 | 0 | 5 | €-198.79 / €-12.42 | €-306.25 / €-19.14 | ~640 / ~280 / ~24* | ~130 / ~60 / 0* | 0 / 0 |
| `signals-all-dev` (dev) | 16 | 4,357 / 272.3 | 121 / 7.56 | 0 | 6 | €-291.82 / €-18.24 | €-361.75 / €-22.61 | 231 / 74 / 3 | 120 / 56 / 0 | 26 / 0 |
| `signals-elig-dev` (dev) | 16 | 4,371 / 273.2 | 111 / 6.94 | 0 | 6 | €-277.61 / €-17.35 | €-308.25 / €-19.27 | 240 / 77 / 5 | 120 / 57 / 0 | 0 / 0 |

*(\*Champion v3 dev baseline stats were recorded before adding `prem_*`/`manual_*` counters; smoke noop shows 71 `prem_won` and 6 `prem_late` across 4 seeds, ~17.8 won and 1.5 late per seed.)*

### Diagnosis of the three signals on Champion v3
1. **Why `visit_failed_not_ready` is already 0 and `use_release` is a complete no-op (`Δ = €+0.00`):**
   Idea #23 was formulated from v2's 32 worlds (which had 118 `not_ready` failed visits). However, Champion v3 already includes `notes_v2=True` and `note_unsure="decline"`. Across all 16 dev worlds on Champion v3, `visit_failed_not_ready` is **0** (all 5 failed visits on dev are `visit_failed_closed`). Because `notes_v2` already parses `ready_at` and `released_at` accurately at the first post, no visit ever fails as `not_ready`, `retry()` is never called for a `not_ready`/unreleased car, `release_aligned` is 0, and `use_release=True` produces an exact `+0.00` no-op on every seed.
2. **Why `ready_from_deadline=True` hurts slightly (`Δ = €-494.61 ± 422.11` on smoke):**
   With `notes_v2=True` already setting `ready_at` accurately, shifting `pickup["window"]["from"]` by `delay_days = (order["deadline"] - won_option["deadline"]) // DAY` (26 times across 16 dev seeds) over-shifts orders whose deadline was pushed across a weekend (`shift_business_days` adds +3 calendar days when jumping Friday → Monday for a 1-business-day ready delay). Pushing the pickup window start by 3 calendar days instead of 1 business day delays collection to Monday and increases late orders on smoke from 38 to 45.
3. **What `eligible_supply=True` does (`Δ = €-50.63 ± 146.36`, `t = -0.35` on dev — inside the noise on margin, +0.97% on worst-world on-time):**
   Because only ~15–20% of roster drivers are experienced (`rating >= 4.8` and `completedGigs >= 50`), counting only experienced drivers for `premium` cars filters out premium requests outside the capital hub (or strips `same_day` when experienced supply < 50). On dev (16 seeds), `eligible_supply=True` reduces mean won orders by 7.9/world (281.1 → 273.2, with `prem_won` at 77 across 16 seeds vs 71 across just 4 smoke seeds in the baseline) and cuts total late orders from **128 to 111** (8.00 → 6.94/world). Worst-world on-time rises from **94.38% to 95.35%** (`dev-01` lifts from 94.4% to 96.8%, `dev-07` from 94.4% to 95.3%), while mean margin changes by **€-50.63 ± 146.36 (`t = -0.35`)**, which is well inside the noise (0.35 SE).

## Verdict
**reject for standalone margin (inside the noise); `eligible_supply=True` is a pure tail-safety lever** — On Champion v3 (`notes_v2=True`), `visit_failed_not_ready` is already 0 across all 16 dev seeds, making `use_release` a literal `+0.00` no-op and `ready_from_deadline` redundant/harmful (`-€495 ± 422` on smoke due to weekend calendar-day shifts). `eligible_supply=True` is inside the noise on dev margin (`Δmargin €-50.63 ± 146.36`, `t = -0.35`) and reduces total late orders from 128 to 111 while lifting worst-world on-time from `94.38%` to `95.35%`.
