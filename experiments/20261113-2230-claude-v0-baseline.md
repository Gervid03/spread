# v0-baseline: from the kit starter to a desk that is ranked on 32 of 32 worlds

- **Agent / branch / commit:** Claude (setup) · main · see git log of 13 Nov
- **Date:** 2026-11-13 21:40–22:30
- **Idea from:** own (setting up the lab)

## Why we tried it
The kit starter quotes the list price, wins ~950 of ~1,040 requests at level 8, and cannot staff them: 45% on
time, −€72,612.51 on `spread-1`. Level 8 has a third of the drivers, unevenly by town, and a competitor
26–54% above list. House best wins only 200–465 orders a week. So: win fewer, dearer, and only where drivers live.

## What changed (all `Params` in `src/spread_lab/policy.py`)
- **Selection:** decline (quote 4× list) when fewer than `min_supply` drivers live within 30 km of the pickup,
  when an option leaves less than 2 h of slack after the drive, or when unstaffed orders near the pickup exceed
  `backlog_ratio` × supply. Prices are raised to keep an 8% margin over 1.25 × the typical fee.
- **Pricing:** option list price × a multiplier learned online (start 1.35 at level 8; log-step 0.02 per
  outcome towards `price_target_win`; a per-dealer factor the same way; 12 straight losses freeze it for the day).
- **Fees:** rising from 1.0× to 1.6× the typical fee over daytime half-hours until the deadline warning, then
  1.8× → 3.0× plus three direct offers. Note flags set manual-licence and plates before the first visit.
- **Runner:** 10-minute steps in business hours, ~630 requests a week instead of 1,891.

## Results (level 8, paired where the seeds match)
| Version | Seeds | Mean margin | On time (worst) | Ranked |
|---|---|---|---|---|
| Kit starter | `spread-1` | −€72,612.51 | 45.5% | 0/1 |
| First desk: `min_supply` 6, `price_target_win` 0.55, `backlog_ratio` 0.12 | 5 (`spread-1`, dev-01..04) | €6,962 | 83.5% | 2/5 |
| + `min_supply` 20, `backlog_ratio` 0.06 | smoke (4) | €7,757 | 89.3% | 3/4 |
| + `price_target_win` 0.45 | dev (16) | €7,051 | 90.2% | 16/16 |
| + `price_target_win` 0.35 | dev (16) | €6,924 | 92.5% | 16/16 |
| same | holdout (16) | €7,128 | **88.6%** (hold-12) | 15/16 |
| **v0 = + `min_supply` 30** | dev (16) | **€6,447** | **93.0%** | **16/16** |
| **v0** | holdout (16) | **€6,837** | **93.2%** | **16/16** |

Tried and rejected (all on top of `min_supply` 20, `price_target_win` 0.35):
| Variant | Seeds | Effect | Verdict |
|---|---|---|---|
| On-time guard: `guard_target` 0.97, `guard_risk_weight` 1.0, `guard_band` 0.03 | dev (16) | Δ −€905 ± 565, worst on-time 90.8% (was 92.5%) | reject: it changes which orders are won and the week drifts; lateness reaches the ledger too late to steer by |
| guard + `steep_open` 2.3 | dev (16) | Δ −€1,218 ± 565, worst 90.8% | reject |
| `fee_warn` 1.9 | 4 weakest worlds | Δ −€566 ± 433, worst on-time unchanged (88.5%) | reject |
| `min_supply` 30 | 4 weakest worlds | worst on-time 88.6% → 93.3%; hold-12 margin €1,975 → €2,429 | **adopt** (became v0) |

Two levers did nearly all the work: **where drivers live** (`min_supply`) and **how much we try to win**
(`price_target_win`). Fees at the margin barely moved the on-time share. Direct offers mostly go unread
(e.g. 183 sent → 3 accepted on `spread-1`): drivers who don't work that day don't read them.

## Verdict
adopt — v0 is ranked on all 32 dev and holdout worlds with every world ≥ 93.0% on time, at €6.4–6.8k a week.
House best made €6.4k–16.4k a week on the Friday 20:01 ranking round, so there is a lot of margin left to find.
