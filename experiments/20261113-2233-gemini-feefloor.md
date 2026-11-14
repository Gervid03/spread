# feefloor: Find the fee floor with the same tracker on the drivers' side

- **Agent / branch / commit:** gemini · exp/gemini-feefloor · (to be committed)
- **Date:** 2026-11-13 22:33
- **Idea from:** IDEAS.md #6

## Why we tried it
The typical fee is the cost of a typical driver from the pickup town, but with hundreds of drivers notified in dense areas, the cheapest available driver often requires less. Most gigs book in minutes at 1.0x typical fee. By finding a lower starting fee (`fee_open_dense`) and slowly ramping it up to the typical fee, we save on driver costs. Additionally, gigs posted after 17:00 for the next day don't need to rise overnight since drivers aren't typically booking then; a `night_hold` delays the step-up until 08:00 the next morning.

## What changed
Added fields to `Params` under `# --- fees ---`:
- `fee_open_dense` (default `-1.0` = off) for pickups with at least `dense_supply` (200) drivers notified.
- `dense_supply` (default `200`) threshold.
- `open_ramp_min_same_day` (default `45`) minutes to ramp to 1.0x for `same_day`.
- `open_ramp_min_other` (default `120`) minutes to ramp to 1.0x for other options.
- `night_hold` (default `False`) holds the fee constant overnight (17:00 to 08:00) for gigs due on a later day.
Run with: `uv run lab eval -s fee_open_dense=0.85 -s night_hold=True --name feefloor-dev`

## Results (level 8, vs champion, paired)
| set | run folder | mean margin | Δmargin ± SE | t | better/worse | on-time min | SAFE |
|---|---|---|---|---|---|---|---|
| smoke | 20261113-222859-feefloor-sweep2-fee_open_dense0.85-night_holdTrue | €9,114 | €+490 ± 415 | 1.18 | 2/2 | 95.3% | yes |
| dev | 20261113-223115-feefloor-dev | €8,030 | €+104 ± 196 | 0.53 | 8/8 | 92.9% | yes |
| dev (taxback) | 20261113-223306-feefloor-dev-taxback | €8,021 | €+95 ± 304 | 0.31 | 10/6 | 92.2% | yes |

Also added tracking stats for `fee_multiple_sum`, `fee_multiple_count`, `minutes_to_book_sum`, `minutes_to_book_count`, which helps confirm that fees start lower and some gigs are secured below the typical fee.

## Verdict
adopt — €+104 ± 196 margin on dev without risking the 92% minimum on-time share. Giving the tax back did not result in a significant change.