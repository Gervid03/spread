# feeclock-on-a: the fee clock runs only when it can matter (delayed ramp, weekend freeze, near-deadline opening fee)

- **Agent / branch / commit:** gemini · `exp/gemini-n14-06043-feeclock-on-a`
- **Date:** 2026-11-14 06:52 UTC
- **Idea from:** `experiments/IDEAS.md` #16 ("The fee clock runs only when it can matter"), built on top of branch A (`exp/gemini-n14-03324-supply-adaptive-fee-open-and-drop-rescue`)

## Why we tried it
In `Desk.rising()`, the fee schedule climbs linearly from `fee_open` (`0.85×`, or `0.80×` on hub multi-day and `0.90×` on thin same-day in baseline A) to `fee_warn` (`1.60×`) across every daytime half-hour (`07:00–22:00`) between posting and the deadline warning (`lastPickupAt - 3h`). As noted in `experiments/20261114-0130-fable-research-v2-results.md` (points 4 and 10):
1. A `next_day` order won in the afternoon climbs through the evening so that by the next morning it is already around `1.20×` typical fee even when more than a full business day remains.
2. A Friday order due on Monday climbs through 30 daytime half-hours on Saturday and 30 on Sunday (`07:00–22:00`), reaching `~1.48×` by Monday `07:00` even though Sunday is always closed for dealer sites and Saturday is closed whenever a site lacks Saturday opening hours.
3. Conversely, when a gig is posted or reposted close to `lastPickupAt` (`< 240` min), opening at `0.85×` may waste precious half-hours climbing through below-market fees.

We tested whether holding the fee at `fee_open` until the last `ramp_hours` daytime hours before the warning point, excluding closed weekend days (`ramp_skip_closed`), and opening tight posts at `1.00×` (`fee_open_near`) reduces `driver_fee` without costing on-time deliveries.

## What changed
In `src/spread_lab/policy.py` (`Params` and `Desk`):
- `ramp_hours: float = 0.0` (`0.0` = A's linear climb from post): when `> 0`, `Desk.rising()` keeps `self.now` at `fee_open` and places the climb only across the last `round(ramp_hours * 60 / fee_step_min)` daytime steps before `until` (`lastPickupAt - 3h`). Gigs with fewer daytime steps than `ramp_hours` climb from the post as before.
- `ramp_skip_closed: bool = False`: when `True`, `Desk.rising()` never counts Sunday (`weekday == 6`) as daytime, and counts Saturday (`weekday == 5`) only if every pickup and delivery site of the gig's legs is open on Saturday (`privateAddress` is `True`, `hours` is `None`, or `hours["saturday"]` is not `None`).
- `fee_open_near: float = 0.0` and `near_slack_min: int = 240`: when `fee_open_near > 0`, any gig posted in `Desk.fees_for()` with `lastPickupAt - self.now < near_slack_min` opens at `fee_open_near` instead of `fee_open`.
- Diagnostic counters in `Desk.stats`:
  - `feex_<option>_<same|later>_sum` and `feex_<option>_<same|later>_n`: booked fee divided by typical car fee (`×1000`) by order option and whether the booking occurred on the day of first post (`same`) or a later day (`later`).
  - `drops_near` and `drops_far`: `gig_dropped` split by whether the gig was posted with `< near_slack_min` to `lastPickupAt`.

All evaluations were run on top of baseline A's exact parameter set (`trust_invest=0.05`, `notes_v2=True`, `note_unsure=decline`, `max_next_day_drive_min=480`, `fri_same_day_max_drive=100`, `thin_long_next_day_supply=50`, `ring_to_hub_same_day_min=60`, `same_day_min_supply=50`, `min_slack_min=150`, `slack_per_drive=0.75`, `backlog_multiday_weight=0.25`, `backlog_in_flight_weight=0.35`, `price_target_win=0.40`, `min_supply=22`, `drop_urgent_margin_min=180`, `hub_multiday_fee_open=0.80`, `thin_sameday_fee_open=0.90`, with v3-only parameters disabled to match A's runs `20261114-034543-fee-drop-smoke5-all180` and `20261114-034812-fee-drop-all180-dev`).

## Results (level 8, paired with Baseline A and Champion v3)

### Paired vs Baseline A (`20261114-034543-fee-drop-smoke5-all180` / `20261114-034812-fee-drop-all180-dev`)

| Set | Run folder | Overrides (on top of A) | Mean margin | Δmargin ± SE (vs A) | t | Better / worse | On-time min / mean | Δon-time | `deadline_close` | `gig_dropped` | SAFE |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| smoke (4) | `20261114-063621-feeclock-noop` | *(none — noop check)* | €10,996.27 | €+0.00 ± 0.00 | — | 0 / 0 | 96.28% / 97.16% | +0.00% | 23.5 | 39.8 | yes |
| smoke (4) | `20261114-063723-feeclock-smoke-ramp4` | `ramp_hours=4` | €10,606.51 | €-389.76 ± 482.01 | -0.81 | 1 / 3 | 93.73% / 94.94% | -2.22% | 33.0 | 30.8 | yes |
| smoke (4) | `20261114-063820-feeclock-smoke-ramp6` | `ramp_hours=6` | €11,401.08 | €+404.81 ± 413.32 | +0.98 | 3 / 1 | 93.51% / 95.62% | -1.54% | 28.2 | 33.0 | yes |
| smoke (4) | `20261114-064449-feeclock-smoke-ramp8` | `ramp_hours=8` | €11,088.92 | €+92.65 ± 386.96 | +0.24 | 3 / 1 | 93.98% / 95.42% | -1.74% | 31.5 | 30.2 | yes |
| smoke (4) | `20261114-064100-feeclock-smoke-skipclosed` | `ramp_skip_closed=True` | €10,919.52 | €-76.75 ± 196.90 | -0.39 | 2 / 2 | 96.28% / 96.98% | -0.18% | 23.2 | 39.0 | yes |
| smoke (4) | `20261114-064218-feeclock-smoke-near100` | `fee_open_near=1.0` | €10,957.17 | €-39.10 ± 71.08 | -0.55 | 3 / 1 | 96.96% / 97.42% | +0.26% | 21.2 | 38.5 | yes |
| smoke (4) | `20261114-064545-feeclock-smoke-combo` | `ramp_hours=6 ramp_skip_closed=True fee_open_near=1.0` | €11,621.71 | €+625.44 ± 375.62 | +1.67 | 3 / 1 | 94.96% / 96.35% | -0.81% | 24.0 | 31.2 | yes |
| dev (16) | *(Baseline A reference)* | *(A)* | €10,577.92 | €+0.00 ± 0.00 | — | — | 95.64% / 97.68% | +0.00% | 14.8 | 36.6 | yes |
| dev (16) | `20261114-064653-feeclock-dev-ramp6` | `ramp_hours=6` | €10,453.68 | €-124.24 ± 195.06 | -0.64 | 7 / 9 | 91.48% / 95.68% | -2.00% | 23.2 | 30.1 | **no** |
| dev (16) | `20261114-064816-feeclock-dev-skipclosed` | `ramp_skip_closed=True` | €10,277.64 | €-300.28 ± 81.32 | -3.69 | 2 / 14 | 95.15% / 97.30% | -0.38% | 17.2 | 38.2 | yes |
| dev (16) | `20261114-064946-feeclock-dev-near100` | `fee_open_near=1.0` | €10,537.27 | €-40.65 ± 36.38 | -1.12 | 5 / 7 | 95.67% / 97.77% | +0.09% | 13.8 | 36.1 | yes |
| dev (16) | `20261114-065055-feeclock-dev-combo` | `ramp_hours=6 ramp_skip_closed=True fee_open_near=1.0` | €10,697.28 | €+119.37 ± 186.64 | +0.64 | 9 / 7 | 91.25% / 95.95% | -1.74% | 20.6 | 28.9 | **no** |

### Paired vs Champion (v3 on `main`)

| Set | Run folder | Mean margin | Δmargin ± SE (vs champion) | t | Better / worse | On-time min / mean | Δon-time | SAFE |
|---|---|---:|---:|---:|---:|---:|---:|---|
| smoke (4) | `20261114-063621-feeclock-noop` (A) | €10,996.27 | €+103.83 ± 230.91 | +0.45 | 1 / 3 | 96.28% / 97.16% | +0.57% | yes |
| smoke (4) | `20261114-063723-feeclock-smoke-ramp4` | €10,606.51 | €-285.93 ± 510.22 | -0.56 | 2 / 2 | 93.73% / 94.94% | -1.65% | yes |
| smoke (4) | `20261114-063820-feeclock-smoke-ramp6` | €11,401.08 | €+508.64 ± 507.77 | +1.00 | 3 / 1 | 93.51% / 95.62% | -0.97% | yes |
| smoke (4) | `20261114-064449-feeclock-smoke-ramp8` | €11,088.92 | €+196.48 ± 492.74 | +0.40 | 3 / 1 | 93.98% / 95.42% | -1.17% | yes |
| smoke (4) | `20261114-064100-feeclock-smoke-skipclosed` | €10,919.52 | €+27.09 ± 190.65 | +0.14 | 2 / 2 | 96.28% / 96.98% | +0.39% | yes |
| smoke (4) | `20261114-064218-feeclock-smoke-near100` | €10,957.17 | €+64.73 ± 267.52 | +0.24 | 1 / 3 | 96.96% / 97.42% | +0.83% | yes |
| smoke (4) | `20261114-064545-feeclock-smoke-combo` | €11,621.71 | €+729.27 ± 452.46 | +1.61 | 3 / 1 | 94.96% / 96.35% | -0.24% | yes |
| dev (16) | *(Baseline A reference)* | €10,577.92 | €+48.50 ± 148.32 | +0.33 | 7 / 9 | 95.64% / 97.68% | +0.52% | yes |
| dev (16) | `20261114-064653-feeclock-dev-ramp6` | €10,453.68 | €-75.74 ± 183.71 | -0.41 | 6 / 10 | 91.48% / 95.68% | -1.48% | **no** |
| dev (16) | `20261114-064816-feeclock-dev-skipclosed` | €10,277.64 | €-251.78 ± 161.00 | -1.56 | 5 / 11 | 95.15% / 97.30% | +0.14% | yes |
| dev (16) | `20261114-064946-feeclock-dev-near100` | €10,537.27 | €+7.85 ± 156.95 | +0.05 | 6 / 10 | 95.67% / 97.77% | +0.61% | yes |
| dev (16) | `20261114-065055-feeclock-dev-combo` | €10,697.28 | €+167.87 ± 164.78 | +1.02 | 7 / 9 | 91.25% / 95.95% | -1.21% | **no** |

### What the counters and ledger breakdown show
1. **Holding the fee flat (`ramp_hours=6`) does cut booked fee multiples and `driver_fee` by ~€760/week, but starves day-1 bookings and inflates `deadline_close`:**
   - On 16 dev seeds (`feeclock-dev-combo` vs `feeclock-dev-near100`), `feex_next_day_later` dropped from **`1.218×`** (`n=65.4`/week) to **`1.087×`** (`n=81.0`/week), and `feex_next_day_same` dropped from **`0.899×`** (`n=115.8`/week) to **`0.879×`** (`n=91.7`/week).
   - Consequently, mean `driver_fee` dropped by **€762/week** (`-€18,210` in `feeclock-dev-combo` and `-€18,250` in `feeclock-dev-ramp6` vs `-€18,972` in A).
   - However, notice the shift in booking timing: `24.1` fewer `next_day` orders per week were booked on the day they were posted (`91.7` vs `115.8`). Because those cars remained unbooked overnight, they competed for the same pool of drivers the next morning and pushed `deadline_close` from **`14.8`** in A up to **`23.2`** (`ramp_hours=6` alone) or **`20.6`** (`combo`).
   - That extra `deadline_close` volume increased `late_refund` from `-€271` to `-€443` (`combo`) / `-€459` (`ramp6`) and `undelivered_penalty` from `-€16` to `-€61` (`combo`) / `-€138` (`ramp6`), while extra unstaffed backlog throttled intake (`revenue` `-€409/week`), eroding most of the €762 fee savings and causing two seeds (`dev-07` at `91.80%`, `dev-14` at `91.25%`) to dip below our 92% safety floor.
2. **Why `ramp_skip_closed=True` alone hurt (`-€300.28 ± 81.32`, `t=-3.69`), yet helped `ramp_hours=6` (`+€243.60` in combo vs `ramp6` alone):**
   - Without `ramp_hours`, freezing the fee over Sunday (and Saturday when closed) kept Friday-won orders stuck around `~1.00×–1.05×` all weekend. Drivers in the simulation still view and pre-book open gigs on weekends for Monday pickup when the fee is high enough; freezing the weekend climb delayed those bookings into Monday morning (`deadline_close` rose from `14.8` to `17.2`, `driver_fee` worsened from `-€18,972` to `-€19,111`).
   - Conversely, *when `ramp_hours=6` is active*, `ramp_skip_closed=True` is essential: without it, a Friday gig due Monday wastes its 6-hour ramp window on Sunday afternoon (when sites are closed), whereas with `ramp_skip_closed=True` the 6-hour ramp occurs during open hours.
3. **`fee_open_near=1.0` (`near_slack_min=240`) slightly improves safety (`on_time_mean` `97.77%`, `deadline_close` `13.8` vs `14.8`), with near-zero effect on margin (`-€40.65 ± 36.38`):**
   - Because baseline A's slack gate (`min_slack_min=150 + 0.75 * drive`) already prevents quoting orders with `< 240` min to `lastPickupAt` except on very short drives or reposts (`near_fee_posts = 3.7`/week, `drops_near = 0.0–0.4`/week vs `drops_far = 28.6–38.1`/week), `fee_open_near=1.0` fires ~4 times per week, trimming `deadline_close` by `1.0`/week and `gig_dropped` by `0.5`/week.

## Verdict
**reject** — Holding the fee clock until the last 6 hours before warning (`ramp_hours=6` + `ramp_skip_closed=True` + `fee_open_near=1.0`) saves €762/week in `driver_fee` and gains `Δmargin €+119.37 ± 186.64` vs A (`€+167.87 ± 164.78` vs v3 champion), but starves day-1 bookings (`91.7` vs `115.8`/week), raising `deadline_close` from `14.8` to `20.6` and dropping `on_time_min` to `91.25%` (NOT SAFE); `fee_open_near=1.0` alone is SAFE (`on_time_min` `95.67%`, `deadline_close` `13.8`) with `Δmargin €-40.65 ± 36.38` vs A (`€+7.85 ± 156.95` vs champion).
