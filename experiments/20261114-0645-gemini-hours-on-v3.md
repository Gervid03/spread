# hours-on-v3: Slack by opening hours: measure slack as the world does

- **Agent / branch / commit:** gemini · `exp/gemini-n14-06261-hours-on-v3` · `b37f3aa` (base)
- **Date:** 2026-11-14 06:45
- **Idea from:** `experiments/IDEAS.md` item #17 ("Slack by opening hours: measure slack as the world does")

## Why we tried it
Every delivery option has `deadline = 20:00` (`1200`), and `Desk.price` previously measured slack as `deadline - ready - drive`. However, `RULES.md` states that `lastPickupAt` is the last minute to collect the car when the pickup site's stated hours show it open (or inside a private seller's slot) and still reach the delivery site inside its stated opening hours and by `deadline`. When a pickup dealer closes at `18:00` (`1080`) or `19:00` (`1140`), a short drive has up to 1–2 hours less real pickup slack than `deadline - ready - drive` assumes, and a private seller's 3-hour slot can end many hours (or days) before `deadline - drive`.

### 1. Ten-minute reveal check (`legs.csv`)
Tabulating stated weekday and Saturday hours from `/tmp/reveals-n14-01` (both single world `w0c23053fd89b352e58f7` and all 16 dev reveal worlds):

| Stop kind | Scope | Total dealer stops | Opens `07:00` (`420`) | Opens `08:00` (`480`) | Opens `09:00` (`540`) | Closes `18:00` (`1080`) | Closes `19:00` (`1140`) | Closes `20:00` (`1200`) | Closes `21:00` (`1260`) | Share closing `< 20:00` | Saturday `09:00–14:00` (`540–840`) | Saturday closed (`null`) |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Pickup (dealer) | 1 world (`w0c2305...`) | 962 | 227 (23.6%) | 602 (62.6%) | 133 (13.8%) | 576 (59.9%) | 290 (30.1%) | 96 (10.0%) | 0 (0.0%) | **90.0%** | 778 (80.9%) | 184 (19.1%) |
| Delivery (dealer) | 1 world (`w0c2305...`) | 1,003 | 316 (31.5%) | 344 (34.3%) | 343 (34.2%) | 0 (0.0%) | 0 (0.0%) | 511 (50.9%) | 492 (49.1%) | **0.0%** | 1,003 (100.0%) | 0 (0.0%) |
| Pickup (dealer) | All 16 worlds | 15,322 | 4,767 (31.1%) | 5,984 (39.1%) | 4,571 (29.8%) | 4,390 (28.7%) | 5,508 (35.9%) | 5,424 (35.4%) | 0 (0.0%) | **64.6%** | 11,626 (75.9%) | 3,696 (24.1%) |
| Delivery (dealer) | All 16 worlds | 15,905 | 5,288 (33.2%) | 5,295 (33.3%) | 5,322 (33.5%) | 0 (0.0%) | 0 (0.0%) | 7,920 (49.8%) | 7,985 (50.2%) | **0.0%** | 15,905 (100.0%) | 0 (0.0%) |

All dealer stops have `hours.weekdays = [0, 1, 2, 3, 4]`. Because **64.6%** of dealer pickup sites across the 16 worlds (and **90.0%** in world `w0c23053fd89b352e58f7`) close before `20:00` on weekdays (only 10.0%–35.4% are open until `20:00`, well below the 90% stop threshold), the stated pickup closing hours strongly bind.

## What changed
Added `slack_by_hours: bool = False` to `Params` in `src/spread_lab/policy.py`, along with helpers:
- `open_at(stop, minute)`: checks that `minute` is inside `stop["window"]` and, for dealer sites (`not stop["privateAddress"]` with `stop["hours"]`), inside `opens <= minute % DAY < closes` on `hours["weekdays"]` or Saturday (`wd == 5` when `hours["saturday"]` is present; Sunday closed).
- `earliest_open_at(stop, start_min)`: first minute `>= max(self.now + 15, ready)` at which the pickup stop is open and inside its window.
- `last_pickup_for(p_stop, d_stop, drive, deadline)`: searches backward day by day from `deadline` to find the last minute `t` where `p_stop` is open at `t`, `d_stop` is open at `t + drive` (for dealer deliveries; private address deliveries require `t + drive <= deadline`, and private pickup slots require `t <= min(window["to"], deadline - drive)`), and `t + drive <= deadline`.
- **World proof (`lastpickup_n`, `lastpickup_err`):** On `order_won`, for every 1-leg order without a note and without a low EV battery on a >200 km route, we compare `last_pickup_for` against `order["lastPickupAt"]`. Across 2,092 won orders in the 16 reveal worlds and 2,480 won orders in `hours-dev`, `lastpickup_err == 0` (exact match on every order; in `hours-slack120-dev`, `lastpickup_err == 2` minutes total across 2,545 orders, i.e. 0.0008 min/order).
- When `slack_by_hours=True`, `Desk.price` uses `earliest` and `slack = last_pickup - earliest` for the slack gate (`slack < p.min_slack_min + p.slack_per_drive * drive`) and the long-drive rules, counting options that pass the old slack rule and fail the hours-aware slack rule in `self.stats["dropped_hours"]`.

Run with:
- `uv run lab eval -s slack_by_hours=True --name hours-dev`
- `uv run lab eval -s slack_by_hours=True -s min_slack_min=120 --name hours-slack120-dev`

## Results (level 8, vs Champion v3, paired)
| set | run folder | overrides | mean margin | Δmargin ± SE | t | better/worse | on-time min | on-time mean | SAFE |
|---|---|---|---:|---:|---:|---|---:|---:|---|
| smoke | `20261114-063952-hours-noop` | none (default `False`) | €10,892.44 | €+0.00 ± 0.00 | — | 0 / 0 | 94.42% | 96.59% | SAFE |
| smoke | `20261114-064034-hours-s1` | `slack_by_hours=True` (`min_slack_min=150`) | €10,694.70 | €-197.74 ± 301.58 | -0.66 | 1 / 3 | 95.28% | 97.11% | SAFE |
| smoke | `20261114-064101-hours-s2-slack135` | `slack_by_hours=True, min_slack_min=135` | €10,818.02 | €-74.41 ± 277.63 | -0.27 | 2 / 2 | 93.80% | 96.58% | SAFE |
| smoke | `20261114-064155-hours-s3-slack120` | `slack_by_hours=True, min_slack_min=120` | €10,911.91 | €+19.47 ± 273.11 | +0.07 | 2 / 2 | 95.04% | 96.92% | SAFE |
| dev | `20261114-064309-hours-dev` | `slack_by_hours=True` (`min_slack_min=150`) | €10,340.31 | €-189.11 ± 125.01 | -1.51 | 5 / 11 | **95.24%** | **97.70%** | SAFE |
| dev | `20261114-064348-hours-slack120-dev` | `slack_by_hours=True, min_slack_min=120` | €10,536.98 | **€+7.56 ± 113.42** | +0.07 | 8 / 8 | **94.39%** | **97.38%** | SAFE |

### Counter and ledger breakdown (16 dev seeds, totals / per-world means)
| Metric | Champion v3 (`min_slack_min=150`) | `hours-dev` (`slack_by_hours=True, 150`) | `hours-slack120-dev` (`slack_by_hours=True, 120`) |
|---|---:|---:|---:|
| Won orders (total / mean per world) | 4,498 (281.1) | 4,242 (265.1) | 4,347 (271.7) |
| Late orders (total / mean per world) | 128 (8.00) | **98 (6.12)** | **114 (7.12)** |
| `deadline_close` warnings (total) | 279 | **182** | **198** |
| `dropped_slack` (total) | 463 | 459 | 351 |
| `dropped_hours` (total / per world) | 0 (0.0) | 1,104 (69.0) | 782 (48.9) |
| `lastpickup_n` / `lastpickup_err` (min) | — | 2,480 / **0** | 2,545 / **2** |
| Mean revenue / world | €30,498 | €28,449 | €29,030 |
| Mean `driver_fee` / world | -€19,483 | -€17,718 | -€18,075 |
| Mean `late_refund` / world | -€331 | -€259 | -€262 |
| Mean `undelivered_penalty` / world | -€80 | -€27 | -€73 |

### Analysis
1. **Exact world model verified:** `last_pickup_for` matches `order["lastPickupAt"]` with `0` error across all 2,480 eligible won orders on `hours-dev` (and 2,092 orders in the 16 reveals).
2. **Strong safety & warning reduction:** With `min_slack_min=150`, `slack_by_hours=True` drops 69.0 options/world that previously passed `deadline - ready - drive >= 150 + 0.75 * drive` only because `20:00` was used instead of the pickup site's `18:00` or `19:00` closing time (or private seller slot end). This cuts `deadline_close` warnings by **35%** (from 279 to 182), cuts late orders by **23%** (from 128 to 98), and raises worst on-time share from **94.38% to 95.24%** (+0.54% mean on-time), at the cost of 16 fewer won orders/world (-€189.11 ± 125.01 margin).
3. **Tax-back (`min_slack_min=120`) is margin-neutral and safer:** Lowering `min_slack_min` from `150` to `120` while keeping `slack_by_hours=True` recovers half the volume, cutting `deadline_close` warnings by **29%** (279 → 198) and late orders by **11%** (128 → 114), improving mean on-time (+0.22% to 97.38%, min 94.39% SAFE) and mean margin by **€+7.56 ± 113.42** (`t = +0.07`, 8 better / 8 worse vs Champion v3).

## Verdict
needs work (safety upgrade / margin-neutral) — `slack_by_hours=True` with `min_slack_min=120` matches Champion v3 margin (`€+7.56 ± 113.42`, `t=0.07`) while cutting `deadline_close` warnings from 279 to 198 (-29%) and late orders from 128 to 114 (+0.22% mean on-time, 94.39% min); with `min_slack_min=150` it raises worst on-time to 95.24% (+0.54% mean on-time, 98 late vs 128) for `€-189.11 ± 125.01`.
