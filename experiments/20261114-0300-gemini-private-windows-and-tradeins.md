# private-windows-and-tradeins: Respect narrow private-address stop windows & gate 2-leg trade-ins

- **Agent / branch / commit:** gemini · `exp/gemini-n14-02113-private-windows-and-tradeins`
- **Date:** 2026-11-14 03:00
- **Idea from:** Margin X-Ray Leak #4 (`experiments/20261114-0200-gemini-research-margin-xray.md`)

## Why we tried it
In Margin X-Ray v2 across the 16 revealed champion v2 dev worlds, **31 of 118 late orders (26.3% of all late orders = 1.94 late/wk, €86/wk in direct refunds plus halving dealer trust 31 times)** came from two structural bugs in `Desk.price()`, `Desk.fees_for()`, and `stops_for()`:
1. **2-leg trade-ins (`len(legs) == 2`, 1.50 won/wk) were 50.0% late (12/24 across 16 worlds; `next_day` trade-ins were 58.8% late, 10/17):** On a 2-leg trade-in, `leg[0]` delivers to a private customer within a 1-hour appointment window `[W, W+60]` (often midday, e.g. 11:00–12:00, 8 hours before `option["deadline"] = 20:00`), and `leg[1]` picks up the trade-in car in `[W, W+60]`. `Desk.price()` never checked if `leg[0]` could reach `leg[0]["delivery"]["window"]["to"]` on time, `Desk.fees_for()` ramped fees toward `order["lastPickupAt"] - 3h` (hours after the midday appointment expired), and `stops_for()` set `delivery_base["to"] = max(delivery["window"]["from"], order["deadline"])`, allowing notes to widen `delivery["window"]["to"]` up to `20:00`.
2. **1-leg private-address pickups and deliveries (`22.3 won/wk`, `1.19 late/wk`):** Private pickups have a 3-hour seller window `[P_from, P_to]` with `P_to << option["deadline"]`, and private deliveries have a 1-hour customer window `[D_from, D_to]` with `D_to < option["deadline"]`, both ignored by `Desk.price()` and `Desk.fees_for()`.

## What changed
Added three `Params` fields in `src/spread_lab/policy.py` (with defaults preserving champion v2 exactly):
- `respect_stop_windows: bool = False` — when `True`:
  - In `Desk.price()`: checks `leg[0]` pickup window slack (`p_win["to"] - p_ready >= min_pickup_window_slack_min` when `p_win["to"] < option["deadline"]`), checks `leg[0]` delivery window slack (`min(option["deadline"], leg[0]["delivery"]["window"]["to"]) - p_ready - leg_drive >= min_slack_min + slack_per_drive * leg_drive`), and checks full-route slack against `final_deadline = min(option["deadline"], legs[-1]["delivery"]["window"]["to"])`.
  - In `Desk.fees_for()`: computes `eff_last_pickup = min([order["lastPickupAt"]] + [min(leg["pickup"]["window"]["to"], leg["delivery"]["window"]["to"] - leg_drive) for leg in undelivered])` and ramps `self.rising(base, until)` toward the earlier stop-window deadline.
  - In `stops_for()`: clamps `delivery_base["to"] = min(delivery["window"]["to"], order["deadline"])` so a note never widens a narrow delivery window up to `order["deadline"]`.
- `min_pickup_window_slack_min: int = 180` — minimum minutes before a narrow pickup window closes (`p_win["to"] < option["deadline"]`).
- `trade_in_mode: str = "all"` — `"all"` (default), `"same_day_only"` (drops `next_day`/`within_3_days` options on 2-leg trade-ins), or `"decline"` (declines 2-leg requests).
- Added stats counters: `dropped_trade_in`, `dropped_pickup_window`, `dropped_delivery_window`, `early_window_ramp`, `won_trade_in`, `late_trade_in`.

Run with:
`uv run lab eval -s respect_stop_windows=True -s min_pickup_window_slack_min=180 -s trade_in_mode=same_day_only --name priv-win-dev`

## Results (level 8, vs champion, paired)
| set | run folder | mean margin | Δmargin ± SE | t | better/worse | on-time min | SAFE |
|---|---|---|---|---|---|---|---|
| smoke (noop) | `20261114-023136-priv-win-noop` | €9,662.25 | €+0.00 ± 0.00 | +0.00 | 0 / 0 | 95.54% (mean 96.69%) | SAFE |
| smoke (`trade_in_mode=all`) | `20261114-023507-priv-win-all` | €9,954.93 | **€+292.68 ± 193.75** | +1.51 | 3 / 1 | 96.02% (mean 96.68%) | SAFE |
| smoke (`trade_in_mode=same_day_only`) | `20261114-023549-priv-win-sameday` | €9,850.42 | **€+188.17 ± 181.39** | +1.04 | 3 / 1 | **96.82%** (mean 97.18%, Δot +0.50%) | SAFE |
| smoke (`trade_in_mode=decline`) | `20261114-023745-priv-win-decline` | €9,758.20 | €+95.96 ± 121.93 | +0.79 | 3 / 1 | 96.70% (mean 97.03%, Δot +0.34%) | SAFE |
| smoke (`sameday` + `slack=150/0.75, sup=50`) | `20261114-023840-priv-win-sameday-slack` | €9,491.96 | €-170.29 ± 738.01 | -0.23 | 3 / 1 | 95.83% (mean 96.57%, Δot -0.11%) | SAFE |
| smoke (`sameday` + `win=0.38`) | `20261114-024020-priv-win-sameday-win38` | €9,243.15 | €-419.09 ± 308.34 | -1.36 | 1 / 3 | 96.22% (mean 97.40%, Δot +0.71%) | SAFE |
| smoke (`sameday` + `sup=50`) | `20261114-024232-priv-win-sameday-sup50` | €9,632.64 | €-29.60 ± 828.32 | -0.04 | 3 / 1 | 96.68% (mean 97.00%, Δot +0.31%) | SAFE |
| **dev** (`trade_in_mode=same_day_only`) | `20261114-024413-priv-win-dev` | €8,871.49 | **€-118.81 ± 153.55** | -0.77 | **10 / 6** | 92.65% (mean **96.88%**, Δot **+0.13%**) | **SAFE** |
| **dev** (`trade_in_mode=all`) | `20261114-025800-priv-win-slack-dev` | €8,850.97 | €-139.33 ± 169.20 | -0.82 | 9 / 7 | 92.65% (mean 96.52%, Δot -0.23%) | **SAFE** |

### Stats Counters & Ledger Breakdown Across 16 Dev Worlds (Mean / Week)

| Metric / Counter | Champion v2 (`dev`) | `priv-win-dev` (`same_day_only`) | `priv-win-slack-dev` (`all`) | Δ (`priv-win-dev` vs Champ) |
|---|---:|---:|---:|---:|
| **`won`** | 230.12 | 229.75 | 230.56 | −0.38 / wk |
| **`won_trade_in`** | 1.50 | **0.19** | 1.44 | **−1.31 / wk** |
| **`late_trade_in`** | 0.75 (50.0%) | **0.12** | 0.69 (47.8%) | **−0.63 / wk (−83%)** |
| **`dropped_trade_in`** | 0.00 | **6.94** | 0.00 | +6.94 / wk |
| **`dropped_pickup_window`** | 0.00 | **2.81** | **2.81** | +2.81 / wk |
| **`dropped_delivery_window`** | 0.00 | **1.19** | **1.19** | +1.19 / wk |
| **`early_window_ramp`** | 0.00 | **6.25** | **7.50** | +6.25 / wk |
| **`deadline_close`** | 12.06 | **11.56** | 11.88 | **−0.50 / wk** |
| **`late_ring`** | 1.06 | **0.62** | 0.69 | **−0.44 / wk (−41%)** |
| **`margin_ring` (€/wk)** | €2,114.01 | **€2,193.84** | €2,188.15 | **+€79.83 / wk** |
| **Worst-world margin (`min`)** | €6,017.30 | **€6,449.75** | **€6,484.14** | **+€432.45** (`dev-14`: +€752.43) |
| **`revenue` (€/wk)** | +€26,922.43 | **+€26,953.68** | +€26,990.52 | **+€31.24 / wk** |
| **`driver_fee` (€/wk)** | −€17,286.93 | −€17,390.80 | −€17,428.47 | −€103.87 / wk |
| **`late_refund` (€/wk)** | −€376.20 | −€399.60 | −€426.70 | −€23.40 / wk |
| **`failed_visit` (€/wk)** | −€165.44 | −€194.21 | −€192.51 | −€28.77 / wk |
| **`waiting` + `release_fee` (€/wk)** | −€92.86 | **−€81.49** | **−€75.83** | **+€11.36 / wk** |

### Diagnostic Findings: Why 10/16 Dev Seeds Improved While 2 Seeds (`dev-07`, `dev-10`) Pulled Down the Mean
1. **Selection gates (`trade_in_mode="same_day_only"`, `dropped_pickup_window`, `dropped_delivery_window`) worked as intended:**
   - Dropping `next_day`/`within_3_days` 2-leg trade-ins (`6.94/wk`) and narrow stop windows (`4.00/wk`) cut late trade-ins by **83%** (`0.75/wk → 0.12/wk`), raised mean on-time share by **+0.13%** (`96.88%` vs `96.75%`, and `+0.36%` over `trade_in_mode="all"`), reduced `deadline_close` warnings by `0.50/wk`, increased weekly revenue by **`+€31.24/wk`** (via preserved dealer trust), lifted worst-world margin by **`+€432.45`** (`€6,017.30 → €6,449.75`), and **beat the champion on 10 of 16 dev seeds** (`dev-14` `+€752.43`, `dev-01` `+€619.86`, `dev-15` `+€413.16`, `dev-04` `+€318.64`, `dev-16` `+€158.02`).
   - By contrast, keeping `next_day` trade-ins (`trade_in_mode="all"` in `priv-win-slack-dev`) still suffered a **47.8% late rate on won trade-ins (`0.69/1.44/wk`)** even with `stops_for()` and `Desk.price()` fixed, confirming that multi-leg next-day swaps with a 1-hour midday appointment should be gated out in `Desk.price()`.
2. **Why `early_window_ramp` in `Desk.fees_for()` hurt on `dev-07` (−€1,501.57) and `dev-10` (−€1,342.84):**
   - When `Desk.fees_for()` shortens `until` from `order["lastPickupAt"] - 3h` to `eff_last_pickup - 3h` (`6.25 orders/wk`), a 3-hour private pickup window (`[09:00, 12:00]`) compresses the `0.85× → 1.60×` fee ramp into just 1–2 hours.
   - This had two adverse side effects: (a) it increased `driver_fee` by **`€103.87/wk`** (`-€1,045` on `dev-07` alone) and taught nearby drivers who viewed at `0.85×` and booked 1 hour later at `1.50×` to wait for raises (`deadline_close` on `dev-07` rose from 25 to 32); and (b) on `next_day` orders with a Day-1 morning private pickup window (`dev-10`), ramping the fee urgently on Day 1 morning caused drivers to pick up early on Day 1 and arrive at the delivery dealer after closing hours on Day 1 evening (`visit_failed_closed` rose from `0.12/wk` to `0.38/wk`, costing `-€552` in failed visits and `-€653` in cascading late refunds on `dev-10`).
   - **Takeaway for combination:** Keep the **quoting gates** (`trade_in_mode="same_day_only"`, `dropped_pickup_window`, `dropped_delivery_window`) and `stops_for()` fix, which win on 10/16 seeds and eliminate 83% of late trade-ins, but **do not ramp `Desk.fees_for()` early to `1.60×` on Day 1 of a `next_day` private pickup**.

## Verdict
**needs work (keep selection gates, drop `early_window_ramp` fee compression)** — `respect_stop_windows=True` with `trade_in_mode=same_day_only` is SAFE, beats the champion on **10 of 16 dev seeds**, improves worst-seed margin by **+€432.45** (`€6,017.30 → €6,449.75`), and improves mean on-time by **+0.13%** (`96.88%`, cutting late trade-ins by 83%), but compressing `Desk.fees_for()` onto `eff_last_pickup` costs **+€103.87/wk** in higher driver fees and pulls 16-seed mean Δmargin to **€-118.81 ± 153.55 (t = -0.77)**.
