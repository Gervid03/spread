# lane-return-pricing: Destination-supply lane pricing (deadhead markup and hub-backhaul discount)

- **Agent / branch / commit:** gemini · `exp/gemini-n14-01151-lane-return-pricing`
- **Date:** 2026-11-14 01:35
- **Idea from:** `n14-08-return` and `docs/GAME.md` lane factor structure

## Why we tried it
The competitor's price is `list × lane factor × day factor × world level × noise`, where part of the lane factor is the same in every world (harder lanes have little return work and few drivers near the delivery). Meanwhile, `n14-08-return` found that 87% (`41/47`) of unbooked gigs declined by delivering drivers are outbound drives away from dense driver pools into thin destinations where the typical fee does not cover the driver's return ticket. Because `Desk.price` previously ignored `supply[delivery]`, it underpriced dead-end outbound lanes and overpriced backhaul lanes returning from ring/regional pickups into the Capital hub (`supply[delivery] >= 200`).

## What changed
Added three fields to `Params` in `src/spread_lab/policy.py` (all defaulting to `0.0` / `0` to reproduce champion v2 identically) and six stats counters (`quoted_dest_thin`, `won_dest_thin`, `late_dest_thin`, `quoted_dest_hub`, `won_dest_hub`, `late_dest_hub`):
- `dest_thin_markup: float = 0.0` — when the final leg's delivery place has `supply[delivery] < min_supply`, multiply the option quote price by `1 + dest_thin_markup * (1 - supply[delivery] / min_supply)`.
- `dest_hub_discount: float = 0.0` — when `supply[pickup] < 100` and `supply[delivery] >= 200`, multiply `next_day` and `within_3_days` quote prices by `1 - dest_hub_discount`.
- `dest_thin_slack_extra: int = 0` — extra required slack in minutes when `supply[delivery] < min_supply` and `drive > 180`.

Run with: `uv run lab eval -s dest_thin_markup=0.06 -s dest_hub_discount=0.03 --name lane-dest-dev`

## Results (level 8, vs champion, paired)
| set | run folder | mean margin | Δmargin ± SE | t | better/worse | on-time min | SAFE |
|---|---|---|---|---|---|---|---|
| smoke (no-op) | `20261114-011935-lane-dest-noop` | €9,662.25 | +€0.00 ± 0.00 | — | 0 / 0 | 95.5% | yes |
| smoke (`m=0.06, d=0.03`) | `20261114-012057-lane-dest-m06-d03` | €9,669.89 | +€7.64 ± 247.51 | 0.03 | 3 / 1 | 95.0% | yes |
| smoke (`m=0.08, d=0.04`) | `20261114-012829-lane-dest-m08-d04` | €9,665.02 | +€2.77 ± 540.34 | 0.01 | 3 / 1 | 94.8% | yes |
| smoke (`m=0.08, d=0.00`) | `20261114-013014-lane-dest-m08-d00` | €9,664.69 | +€2.44 ± 403.98 | 0.01 | 3 / 1 | 94.8% | yes |
| smoke (`m=0.06, d=0.03, s=60`) | `20261114-013149-lane-dest-m06-d03-s60` | €9,657.19 | −€5.05 ± 245.85 | −0.02 | 3 / 1 | 95.5% | yes |
| dev (`m=0.06, d=0.03`) | `20261114-013245-lane-dest-dev` | €9,185.30 | +€194.99 ± 185.10 | 1.05 | 9 / 7 | 93.5% | yes |

### Counter & ledger breakdown
- **Smoke shift (`4` worlds):** Compared to no-op, `dest_thin_markup=0.06, dest_hub_discount=0.03` reduced wins into thin destinations (`won_dest_thin`: `473 → 406`) and increased wins on hub-backhaul lanes (`won_dest_hub`: `49 → 71`, with only `2` late out of `71`).
- **Dev (`16` worlds):** Across 16 dev seeds, `quoted_dest_thin = 5,406`, `won_dest_thin = 1,941` (`late_dest_thin = 74`, 3.8% late), and `quoted_dest_hub = 1,474`, `won_dest_hub = 275` (`late_dest_hub = 5`, 1.8% late).
- **Ledger effect on dev (per world mean):** Revenue decreased by `€470.93`/world (`224` vs `228` won orders/world), while driver fees dropped by `€658.81`/world (`-€16,628` vs `-€17,287`), late refunds improved by `+€24.13`/world, and ring margin increased by `+€100.18`/world (`margin_ring_cents`: `3,382,414 → 3,542,699`).
- **Why the gain is modest (`t = 1.05`):** Because `Desk.learn` adjusts the global multiplier `self.mult` and `self.dealer_adj` to hold a fixed 35% overall win rate (`price_target_win = 0.35`), losing more quotes on thin-destination lanes (which represent ~71% of non-declined quotes) causes the online tracker to nudge `self.mult` downward on dense-destination lanes, partially giving back the markup's revenue gain on high-volume worlds like `dev-03` (`-€670`) and `dev-07` (`-€1,023`) while helping low-margin worlds like `dev-14` (`+€1,664`) and `dev-15` (`+€1,430`).

## Verdict
needs work — SAFE on dev with `+€194.99 ± 185.10` (`t = 1.05`, better on `9/16` seeds, worst on-time `93.5%`) and `+€100/world` on ring pickups, but below the `t ≥ 2` promotion bar because the global win-rate tracker offsets the thin-destination markup.
