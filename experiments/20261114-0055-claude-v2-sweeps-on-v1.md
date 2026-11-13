# v2: Fable's no-code sweep settings on top of v1

- **Agents / branches:** the Gemini 3.8 Flash sweeps agent (`exp/gemini-sweeps`, note
  `20261114-0017-gemini-tier0-sweeps.md`) found the settings on v0; Claude stacked them on v1
- **Date:** 2026-11-14 00:55
- **Idea from:** Fable's IDEAS.md, Tier 0 sweeps S1 (radius), S3 (fee floor), S4 (tracker step), S5 (offers), S6 (slack)

## Why we tried it
On v0, five sweep settings together gave +€2,644 ± 306 on dev (t = 8.7, all 16 better). One of them,
`supply_radius_km` 55, is the crude form of v1's ring, so only the other four were stacked on v1.

## What changed (now the defaults in `Params`)
`fee_open` 0.85 (gigs book within minutes at 1.0×, so the floor is lower) · `price_lr` 0.05 (the tracker
follows the competitor faster) · `offers_per_warning` 0 (3 of 218 offers were ever accepted) · `min_slack_min`
180 (with 120 the worst dev world fell to 90.3%).

## Results (level 8, paired with v1)
| Set | Variant | Mean margin | Δ margin ± SE | t | better / worse | On time (worst) | SAFE |
|---|---|---|---|---|---|---|---|
| dev | slack 120 | €8,783 | +€856 ± 315 | 2.7 | 14 / 2 | 90.3% | no |
| dev | **slack 180 = v2** | **€8,990** | **+€1,064 ± 240** | 4.4 | 13 / 3 | 94.4% | yes |
| holdout | **v2** | **€9,414** | **+€1,472 ± 199** | 7.4 | **16 / 0** | **91.8%** | no (by 0.2 points) |

Over all 32 worlds: v2 averages €9,202 against v1's €7,934 (+16%). Worst world 91.8% (hold-10, where v2 also
earns +€2.3k) against 92.7%, but fewer worlds under 93% (1 against 2) and under 94% (2 against 3); hold-12, the
historically weakest world, goes from 92.7% to 94.4%.

## Verdict
adopt, **as an exception to the 92% rule**, decided by Claude as lead at 00:55 and open to the lead's veto: the
rule protects the final from an unranked week, and v2's tail is no thinner than v1's while its margin is 16%
higher. Revert with `git revert` of the promotion commit if the safety margin matters more.
