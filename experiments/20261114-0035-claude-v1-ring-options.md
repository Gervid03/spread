# v1: the ring and option steering together

- **Agents / branches:** Gemini 3.1 Pro agents `exp/gemini-ring` (idea 1) and `exp/gemini-options` (idea 2);
  merged by Claude in `exp/v1-ring-options` (the only conflict: both added rules to the same loop; all kept)
- **Date:** 2026-11-14 00:35
- **Idea from:** Fable's IDEAS.md, ideas 1 and 2

## Why we tried it
Alone, the ring was the bigger win but made the worst world thinner (holdout 90.4% on time), and option
steering was the safer one but a smaller gain. They act on different orders: the ring adds Hyvinkää-type
pickups through slow options only; steering removes same-day and long-drive orders where drivers are few.

## What changed (now the defaults in `Params`)
`gate_radius_km` 55 · `far_options` "slow" · `same_day_min_supply` 100 · `slack_per_drive` 0.5 ·
`long_drive_min` 300 (v0's `min_supply` 30 and 35% win target unchanged).

## Results (level 8, paired with v0)
| Set | Version | Mean margin | Δ margin ± SE | t | better / worse | On time (worst) | SAFE |
|---|---|---|---|---|---|---|---|
| dev | ring alone (55, slow) | | +€1,587 ± 258 | 6.2 | | 92.4% | yes |
| dev | steering alone + `min_supply` 20 | | +€336 ± 196 | 1.7 | | 95.1% | yes |
| holdout | ring alone | €8,299 | +€1,462 ± 448 | 3.3 | 14 / 2 | **90.4%** | no |
| dev | **v1 = both** | **€7,926** | **+€1,479 ± 296** | **5.0** | 15 / 1 | **94.9%** | **yes** |
| holdout | **v1 = both** | **€7,942** | **+€1,106 ± 411** | **2.7** | 13 / 3 | **92.7%** | **yes** |

## Verdict
adopt: +€1.1–1.5k a week on both seed sets, ranked on all 32 worlds, and the worst world is back above 92%.
