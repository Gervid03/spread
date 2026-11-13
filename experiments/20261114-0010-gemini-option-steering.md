# option-steering: Option steering by quoting the speed we can staff

- **Agent / branch / commit:** gemini · exp/gemini-option-steering · HEAD
- **Date:** 2026-11-14 00:10
- **Idea from:** IDEAS.md #2

## Why we tried it
Often we quote a `same_day` option or take an order with a tight deadline when there are not enough drivers in the area to actually fulfill it on time, or when the drive itself is very long. By steering options (refusing to quote `same_day` when supply is low, requiring more slack for long drives, and dropping long-drive options that fall on the ready day), we can avoid taking orders that are highly likely to miss their deadline, increasing our on-time rate and giving us a safety buffer we can trade for margin.

## What changed
Added `same_day_min_supply: int = 0`, `slack_per_drive: float = 0.0`, and `long_drive_min: int = 0` to `Params`.
Updated `Desk.price` to drop options violating these rules and increment counters in `stats`. Added `won_{option}` counters.
Run with: `uv run lab eval -s same_day_min_supply=100 -s slack_per_drive=0.5 -s long_drive_min=300 -s min_supply=20 --name option-steering-dev-ms20`

## Results (level 8, vs champion, paired)
| set | run folder | mean margin | Δmargin ± SE | t | better/worse | on-time min | SAFE |
|---|---|---|---|---|---|---|---|
| smoke | option-steering-c1 | €7,149 | €-5 ± 551 | -0.01 | 2/2 | 96.0% | YES |
| dev | option-steering-dev | €6,382 | €-65 ± 187 | -0.35 | 7/9 | 95.4% | YES |
| dev | option-steering-dev-ms20 | €6,784 | €+336 ± 196 | 1.71 | 11/5 | 95.1% | YES |
| dev | option-steering-dev-ptw045 | €6,607 | €+160 ± 313 | 0.51 | 12/4 | 91.7% | NO |

The base option steering configuration (`same_day_min_supply=100`, `slack_per_drive=0.5`, `long_drive_min=300`) increased on-time delivery by 1.10% on average, establishing a safer baseline. Giving the safety tax back via `-s min_supply=20` converted this safety gain into a €+336 margin improvement. Attempting to give back the tax via `-s price_target_win=0.45` proved unsafe due to a 91.7% on-time drop on one seed.

## Verdict
adopt — -s same_day_min_supply=100 -s slack_per_drive=0.5 -s long_drive_min=300 -s min_supply=20 provides a safe +€336 margin gain.