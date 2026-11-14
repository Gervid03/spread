# n14-01154-trust-refined-and-guard: Fine sweep, tapered investment, and trust guard on Idea #4

- **Agent / branch / commit:** gemini · exp/gemini-n14-01154-trust-refined-and-guard · 943012d
- **Date:** 2026-11-14 01:46
- **Idea from:** IDEAS.md item #4 (`trust_invest` fine sweep + `trust_invest_cap` + `trust_taper` + `trust_guard` on champion v2)

## Why we tried it
In `n14-02-trust-v2`, a flat 5% discount (`trust_invest=0.05`) on safe requests (`supply >= 100`, no note, `slack >= 360` min) for the top 3 dealers on Monday–Wednesday achieved **Δmargin €+303.46 ± 134.52 (t = +2.26, 11/16 better), worst on-time 94.7% (SAFE)** on dev, whereas `trust_invest=0.10` dropped to **€-290.55 ± 195.82 (t = -1.48)** because over-discounting once a dealer's trust count is already high sacrifices revenue and triggers stronger morning competitor price cuts. We tested:
1. A fine dev sweep (`trust_invest=0.03, 0.06`) bracketing `0.05`.
2. Stopping or tapering the investment discount earlier via `trust_invest_cap` and `trust_taper` (multiplying `trust_invest` by `(trust_invest_cap - count) / trust_invest_cap` so the discount is largest on Monday at count 0 and fades to 0 as trust approaches the cap).
3. `trust_guard` (Idea #4c: declining thin-town `same_day`-offered requests or drives > 300 min once a dealer's trust reaches ≥ 13, to avoid halving accumulated trust).

## What changed
Merged `origin/exp/gemini-n14-02-trust-v2` and added two refinement fields to `Params` (with defaults preserving champion v2 and `trust-v2` behaviour) plus stats counters (`trust_invest_quotes`, `trust_invest_won`, `dropped_trust_guard`, and `top_dealer_trust_d0..d4`):
- `trust_invest_cap: int = 25` — stop applying the `trust_invest` discount to a dealer once `self.dealer_trust[dealer] >= trust_invest_cap`.
- `trust_taper: bool = False` — when `True`, scale `trust_invest` by `(trust_invest_cap - count) / trust_invest_cap`.

Run with:
- `uv run lab sweep --seeds-from dev -g trust_invest=0.03,0.06 --name trust-fine-dev`
- `uv run lab eval -s trust_invest=0.07 -s trust_taper=True --name trust-taper-guard-dev`

## Results (level 8, vs champion v2, paired)
| set | run folder | overrides | mean margin | Δmargin ± SE | t | better/worse | on-time min | SAFE |
|---|---|---|---|---|---|---|---|---|
| smoke | `runs/20261114-013721-trust-refined-noop` | default (no-op) | €9,662.25 | €+0.00 ± 0.00 | — | 0/0 | 95.5% | yes |
| smoke | `runs/20261114-013915-trust-taper0.07-smoke` | `trust_invest=0.07, trust_taper=True` | €10,021.40 | €+359.15 ± 287.03 | +1.25 | 3/1 | 95.6% | yes |
| smoke | `runs/20261114-013927-trust-cap18-smoke` | `trust_invest=0.05, trust_invest_cap=18` | €9,922.88 | €+260.63 ± 219.31 | +1.19 | 3/1 | 95.7% | yes |
| smoke | `runs/20261114-014022-trust-guard-smoke` | `trust_invest=0.05, trust_guard=True` | €9,191.17 | €-471.07 ± 660.64 | -0.71 | 2/2 | 96.3% | yes |
| dev | `runs/20261114-014051-trust-fine-dev-trust_invest0.03` | `trust_invest=0.03` | €8,896.86 | €-93.44 ± 192.89 | -0.48 | 7/9 | 94.4% | yes |
| dev | *(from `n14-02-trust-v2`)* `runs/20261114-001846-trustv2-trust_invest0.05` | `trust_invest=0.05` | €9,293.76 | €+303.46 ± 134.52 | +2.26 | 11/5 | 94.7% | yes |
| dev | `runs/20261114-014310-trust-fine-dev-trust_invest0.06` | `trust_invest=0.06` | €9,088.48 | €+98.17 ± 178.72 | +0.55 | 10/6 | 95.0% | yes |
| dev | `runs/20261114-014445-trust-taper-guard-dev` | `trust_invest=0.07, trust_taper=True` | €8,965.33 | €-24.97 ± 151.32 | -0.17 | 7/9 | 94.9% | yes |

### Counter and mechanism analysis
- **Why `trust_guard=True` hurts (`Δmargin €-471.07` on smoke):** On smoke, `trust_guard` dropped an average of `56.0` requests per world (`dropped_trust_guard=56.0`), reducing won orders from `240` to `230` (on `dev-03` margin fell from `€13,572` to `€11,647`). Because champion v2 already enforces `far_options="slow"` (declining `same_day` on ring pickups while quoting `next_day`/`within_3_days`) and `long_drive_min=300` (forcing next-day deadlines on long drives), the requests that `trust_guard` declines outright are already steered to safe slow options where high dealer trust yields high margins.
- **Fine curve around `trust_invest=0.05`:** Across the dev set:
  - `trust_invest=0.03` quotes `69.9` investment requests and wins `31.6` (`45.2%`), reaching `top_dealer_trust` of `3.94` (Mon), `14.38` (Tue), `23.50` (Wed) — too small a nudge on Monday/Tuesday to improve over the baseline trajectory (`Δmargin €-93.44 ± 192.89`).
  - `trust_invest=0.05` (from `n14-02-trust-v2`) hits the sweet spot (`Δmargin €+303.46 ± 134.52, t = +2.26, 11/16 better`), reaching `top_dealer_trust` `4.2` (Mon), `14.6` (Tue), `24.6` (Wed).
  - `trust_invest=0.06` quotes `68.4` investment requests and wins `34.3` (`50.2%`), remaining positive (`Δmargin €+98.17 ± 178.72, t = +0.55`, better on `10/16` seeds, worst on-time `95.0%`), but begins to show the diminishing returns of winning over half the top dealers' safe orders and triggering stronger morning competitor reactions (`top_dealer_trust_d2` `21.19`).
  - `trust_invest=0.07, trust_taper=True` quotes `67.6` investment requests and wins `33.25` (`49.2%`), with `top_dealer_trust` `4.44` (Mon), `15.56` (Tue), `22.62` (Wed). While strong on smoke (`+€359.15`), on the full 16-seed dev set the 7% initial discount on Monday gives away slightly too much margin early and underperforms flat `0.05`/`0.06` (`Δmargin €-24.97 ± 151.32`).

## Verdict
adopt flat `trust_invest=0.05` (from `n14-02-trust-v2`: **Δmargin €+303.46 ± 134.52, t = +2.26, 11/16 better, min on-time 94.7% SAFE**), with `trust_invest=0.06` (**Δmargin €+98.17 ± 178.72, 10/16 better, min on-time 95.0% SAFE**) confirming the positive neighborhood; reject `trust_guard=True` (`-€471` on smoke from dropping profitable slow-steered orders) and `trust_taper=True` (`€-24.97 ± 151.32` on dev).
