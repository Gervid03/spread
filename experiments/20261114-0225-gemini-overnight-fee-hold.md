# overnight-fee-hold: Convex and delayed-start multiday fee ramps (`fee_ramp_power`, `fee_hold_frac`, `dense_fee_open`)

- **Agent / branch / commit:** gemini · `exp/gemini-n14-02111-overnight-fee-hold`
- **Date:** 2026-11-14 02:25
- **Idea from:** Margin X-Ray v2 (`experiments/20261114-0200-gemini-research-margin-xray.md`, Section 5, Leak #2: €1,477/wk excess above `0.85×` on 57.4 unwarned multi-day bookings/wk)

## Why we tried it
In champion v2, `Desk.rising(base, until)` interpolates linearly across all daytime half-hour steps between order win (`self.now`) and `lastPickupAt - 3 * HOUR`. Consequently, a `next_day` order won on Monday morning climbs through 20+ daytime steps on Monday afternoon and wakes up at 08:00 Tuesday already at `~1.17×` reference fee, paying €1,477/wk above `fee_open = 0.85` across 57.4 overnight bookings/wk even though a full day of slack remains. Meanwhile, in dense pools (`supply >= 100`) on short drives (`drive <= 150` min), 60+ orders/wk book within 5 minutes at `0.85×`. We tested holding or curving the early portion of multi-day fee ramps (`fee_hold_frac`, `fee_ramp_power` when `until // DAY > now // DAY`) so `same_day` ramps stay linear while multi-day orders stay closer to `fee_open` on Day 1, and starting dense short-drive schedules at `dense_fee_open = 0.80`.

## What changed
Added four `Params` fields in `src/spread_lab/policy.py` (with defaults preserving champion v2 bit-for-bit):
- `fee_ramp_power: float = 1.0` — exponent on the normalized step index `u ** p.fee_ramp_power` in `Desk.rising()`.
- `fee_hold_frac: float = 0.0` — fraction of steps in `Desk.rising()` held flat at `f_open` before ramping to `fee_warn` over the remaining `1 - fee_hold_frac` steps.
- `fee_hold_multiday_only: bool = True` — applies `fee_hold_frac` and `fee_ramp_power` only when `until // DAY > self.now // DAY` so `same_day` orders retain the linear ramp.
- `dense_fee_open: float = 0.0` — when `> 0`, starts `Desk.rising()` at `dense_fee_open` instead of `fee_open` when `self.supply.get(pickup, 0) >= 100` and total order `drive <= 150`.
- Added telemetry counters in `Desk.stats`: `multiday_ramped`, `dense_open_used`, `booked_fee_cents_sum`, and `booked_ref_fee_cents_sum`.

Run with:
- Standalone: `uv run lab eval -s fee_ramp_power=1.25 -s fee_hold_multiday_only=True -s dense_fee_open=0.80 --name overnight-fee-dev`
- Stacked: `uv run lab eval -s fee_ramp_power=1.25 -s fee_hold_multiday_only=True -s dense_fee_open=0.80 -s min_slack_min=150 -s slack_per_drive=0.75 -s same_day_min_supply=50 --name overnight-fee-stack-dev`

## Results (level 8, vs champion, paired)
| set | run folder | mean margin | Δmargin ± SE | t | better/worse | on-time min | SAFE |
|---|---|---|---|---|---|---|---|
| smoke (noop) | `20261114-021423-fee-hold-noop` | €9,662.25 | €+0.00 ± 0.00 | — | 0 / 0 | 95.5% | YES |
| smoke (s1: `power=2.0`) | `20261114-021503-fee-hold-s1-pow2` | €8,992.45 | €-669.79 ± 473.10 | -1.42 | 1 / 3 | 94.0% | YES |
| smoke (s2: `hold=0.35, power=1.5`) | `20261114-021601-fee-hold-s2-hold35-pow15` | €9,381.13 | €-281.12 ± 595.63 | -0.47 | 2 / 2 | 92.9% | YES |
| smoke (s3: `power=1.8, warn=1.45, step=25`) | `20261114-021653-fee-hold-s3-pow18-warn145` | €9,309.80 | €-352.45 ± 675.04 | -0.52 | 2 / 2 | 94.8% | YES |
| smoke (s4: s2 + `dense_fee_open=0.80`) | `20261114-021901-fee-hold-s4-hold35-pow15-dense80` | €9,192.05 | €-470.20 ± 580.09 | -0.81 | 1 / 3 | 91.5% | NO |
| smoke (s5: `power=1.25, dense_fee_open=0.80`) | `20261114-021946-fee-hold-s5-pow125-dense80` | €10,115.30 | €+453.05 ± 153.92 | +2.94 | 4 / 0 | 95.5% | YES |
| dev (`power=1.25, dense_fee_open=0.80`) | `20261114-022142-overnight-fee-dev` | €8,889.03 | €-101.27 ± 181.59 | -0.56 | 6 / 10 | 93.2% | YES |
| dev (stacked w/ slack+supply) | `20261114-022413-overnight-fee-stack-dev` | €9,175.71 | €+185.41 ± 202.34 | +0.92 | 8 / 8 | 93.4% | YES |

### Ledger and Counter Breakdown
1. **Why strong overnight fee holds (`fee_ramp_power >= 1.8` or `fee_hold_frac = 0.35`) hurt margin on smoke:**
   - They did lower the `booked_fee / reference_fee` ratio on smoke from `1.0312` (champion) to `1.0243` (`s1`), `1.0231` (`s2`), and `1.0081` (`s3`), reducing total `driver_fee` by €340–€710/wk.
   - However, two structural couplings erased the fee savings:
     1. **Unstaffed-backlog gating (`backlog_near`):** While multi-day orders sit unbooked on Day 1 afternoon at held-down fees, they count as unstaffed orders in `backlog_near(pickup)`. This causes `Desk.price` to hit the local backlog cap (`max(backlog_min, backlog_ratio * gate_supply)`) and decline incoming requests on Day 1 afternoon, cutting won orders from 240.2/wk to 234.2–236.0/wk and losing €640–€900/wk in revenue.
     2. **Deadline-warning cascade:** Deferring multi-day bookings from Day 1 afternoon to Day 2 leaves less absorption capacity on Day 2, pushing `deadline_close` warnings on smoke up from `14.5/wk` to `19.5–20.0/wk` (`steep` schedule `1.80×–3.00×`) and adding €120–€170/wk in `late_refund` + `undelivered_penalty`.
2. **Gentle convex + dense open (`fee_ramp_power=1.25, dense_fee_open=0.80`) on 16-seed dev:**
   - Triggered `multiday_ramped = 206.2/wk` and `dense_open_used = 103.1/wk` with `booked_fee / reference_fee = 1.0291`.
   - On `overnight-fee-dev`, `driver_fee` improved slightly from `-€17,286.92/wk` to `-€17,247.34/wk` (`+€39.58/wk`), but slightly fewer won orders (`227.1` vs `227.8`, `revenue` `-€64.20/wk`) and slightly higher `late_refund` (`-€422.95` vs `-€375.60`, `deadline_close` `12.7` vs `12.1`) produced a net `Δmargin = €-101.27 ± 181.59` (`t = -0.56`).
   - On `overnight-fee-stack-dev` (stacked with `min_slack_min=150, slack_per_drive=0.75, same_day_min_supply=50`), average driver fee per won order fell by `€0.50/order` (`€75.39` vs `€75.89`, `booked_fee / reference_fee = 1.0274`), yielding `Δmargin = €+185.41 ± 202.34` (`t = +0.92`, SAFE at `93.4%` min on-time), which underperforms the standalone slack/supply overrides due to the same unstaffed-backlog interaction.

## Verdict
**reject** — Holding or curving multi-day fees down on Day 1 delays Day-1 afternoon bookings, which clogs `backlog_near(pickup)` (costing €640–€900/wk in declined revenue on smoke) and increases `deadline_close` warnings; even the mildest setting (`fee_ramp_power=1.25, dense_fee_open=0.80`) is `-€101.27 ± 181.59` (`t = -0.56`) standalone and `+€185.41 ± 202.34` (`t = +0.92`) stacked on 16-seed dev.
