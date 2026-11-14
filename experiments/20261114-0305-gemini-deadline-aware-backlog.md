# n14-02462-deadline-aware-backlog: Deadline-day-aware local backlog gate and in-flight batch quote cap

- **Agent / branch / commit:** gemini · `exp/gemini-n14-02462-deadline-aware-backlog` · `HEAD`
- **Date:** 2026-11-14 03:05
- **Idea from:** `n14-02111` structural finding (`backlog_multiday_weight`) + `IDEAS.md` #7 (`backlog_in_flight_weight`), stacked on `origin/exp/gemini-n14-02114-stack-gates-trust-notes`

## Why we tried it
Tonight's experiments uncovered two opposite structural bugs in `Desk.backlog_near(place)` (`src/spread_lab/policy.py`):
1. **Unurgent multi-day orders pollute today's `backlog_near(pickup)` and falsely decline afternoon requests (`n14-02111` finding):**
   - Previously, `Desk.backlog_near(place)` counted every unstaffed order within `supply_radius_km` equally (`+1`), regardless of whether the order was a `same_day` car due at 20:00 today or a `next_day` / `within_3_days` car due tomorrow or in 3 days.
   - When `next_day` or `within_3_days` orders sit unbooked on Day 1 afternoon (which is completely normal because next-day drivers book them the next morning), they fill up `backlog_near(pickup) >= max(p.backlog_min, p.backlog_ratio * gate_supply)` and cause `Desk.price()` to decline profitable afternoon requests (`74` backlog declines on the 4 smoke seeds in Champion v2, including `53` on `dev-02` and `17` on `dev-04`).
   - Weighting unurgent multi-day orders (`order["deadline"] // DAY > self.now // DAY` and `order["id"] not in self.urgent`) by `backlog_multiday_weight=0.25` stops tomorrow's cars from blocking today's intake while still bounding multi-day accumulation.
2. **Bulk batches bypass `backlog_near(pickup)` because in-flight quotes are ignored (`IDEAS.md` #7):**
   - Conversely, when a bulk order of 10–35 cars arrives from one yard at the same minute (e.g. 20 `same_day` cars from Lempäälä on `dev-04`), all 20 requests are quoted before `respondBy` (+15 min), when `self.orders` has `0` of them.
   - Counting currently open, unanswered non-declined quotes (`req_id not in self.orders`, `req_id not in self.lost_requests`, `self.decided.get(req_id) in ("quote", "floor")`, `self.now <= req["respondBy"]`) near `place` weighted by `backlog_in_flight_weight=0.35` (our expected win rate) caps bulk yard intake in real time as the batch is being quoted, allowing us to safely raise `price_target_win=0.40` and lower `min_supply=22`.

## What changed
Merged `origin/exp/gemini-n14-02114-stack-gates-trust-notes` and added two `Params` fields in `src/spread_lab/policy.py` whose defaults (`backlog_multiday_weight=1.0`, `backlog_in_flight_weight=0.0`) reproduce `n14-02114` and Champion v2 bit-for-bit (`Δmargin €+0.00 ± 0.00` on smoke):
- `backlog_multiday_weight: float = 1.0` — weight in `backlog_near(place)` for an unstaffed order whose `order["deadline"] // DAY > self.now // DAY` and `order["id"] not in self.urgent`.
- `backlog_in_flight_weight: float = 0.0` — weight in `backlog_near(place)` for each open, unanswered non-declined quote (`req_id not in self.orders` and `req_id not in self.lost_requests` and `self.decided.get(req_id) in ("quote", "floor")` and `self.now <= req["respondBy"]`) whose first pickup is within `supply_radius_km` of `place`. Tracked `self.lost_requests` on `order_lost` and rebuilt in `rejoin()`.
- Added telemetry counters in `Desk.price()`: `self.stats["declined_backlog"] += 1` whenever `backlog_near(pickup)` declines a request, and `self.stats["in_flight_blocked"] += 1` when `backlog_in_flight_weight > 0` caused the cap to bind.

Run commands:
- **Dev 1 (`backlog-aware-gtn-dev`, `backlog_multiday_weight=0.25` on `n14-02114` Run 3):**
  ```sh
  uv run lab eval -s trust_invest=0.05 -s notes_v2=True -s note_unsure=decline -s max_next_day_drive_min=480 -s fri_same_day_max_drive=100 -s thin_long_next_day_supply=50 -s ring_to_hub_same_day_min=60 -s same_day_min_supply=50 -s min_slack_min=150 -s slack_per_drive=0.75 -s price_target_win=0.38 -s min_supply=25 -s backlog_multiday_weight=0.25 --name backlog-aware-gtn-dev
  ```
- **Dev 2 (`backlog-aware-gtn-v2-dev`, `backlog_multiday_weight=0.25, backlog_in_flight_weight=0.35` on `n14-02114` Run 3):**
  ```sh
  uv run lab eval -s trust_invest=0.05 -s notes_v2=True -s note_unsure=decline -s max_next_day_drive_min=480 -s fri_same_day_max_drive=100 -s thin_long_next_day_supply=50 -s ring_to_hub_same_day_min=60 -s same_day_min_supply=50 -s min_slack_min=150 -s slack_per_drive=0.75 -s price_target_win=0.38 -s min_supply=25 -s backlog_multiday_weight=0.25 -s backlog_in_flight_weight=0.35 --name backlog-aware-gtn-v2-dev
  ```
- **Dev 3 (`backlog-aware-gtn-ptw40-dev`, `backlog_multiday_weight=0.25, backlog_in_flight_weight=0.35, price_target_win=0.40, min_supply=22`):**
  ```sh
  uv run lab eval -s trust_invest=0.05 -s notes_v2=True -s note_unsure=decline -s max_next_day_drive_min=480 -s fri_same_day_max_drive=100 -s thin_long_next_day_supply=50 -s ring_to_hub_same_day_min=60 -s same_day_min_supply=50 -s min_slack_min=150 -s slack_per_drive=0.75 -s price_target_win=0.40 -s min_supply=22 -s backlog_multiday_weight=0.25 -s backlog_in_flight_weight=0.35 --name backlog-aware-gtn-ptw40-dev
  ```

## Results (level 8, vs champion v2, paired)
| set | run folder | mean margin | Δmargin ± SE | t | better/worse | on-time min (mean, Δ) | SAFE |
|---|---|---:|---:|---:|---:|---:|---|
| smoke (noop) | `runs/20261114-025300-backlog-v2-noop` | €9,662.25 | €+0.00 ± 0.00 | — | 0 / 0 | 95.5% (96.7%, +0.00%) | yes |
| smoke 1 (`mw=0.25`) | `runs/20261114-025324-backlog-smoke1-mw25` | €10,597.41 | €+935.17 ± 416.66 | 2.24 | 4 / 0 | 95.3% (96.6%, -0.10%) | yes |
| smoke 2 (`ifw=0.35`) | `runs/20261114-025526-backlog-smoke2-ifw35` | €10,649.35 | €+987.11 ± 587.06 | 1.68 | 4 / 0 | 96.0% (97.0%, +0.34%) | yes |
| smoke 3 (`mw=0.25, ifw=0.35`) | `runs/20261114-025601-backlog-smoke3-both` | €10,259.83 | €+597.58 ± 189.99 | 3.15 | 4 / 0 | 94.4% (96.3%, -0.41%) | yes |
| smoke 4 (`+ptw=0.40, ms=22`) | `runs/20261114-025653-backlog-smoke4-ptw40-ms22` | €10,726.20 | €+1,063.95 ± 579.41 | 1.84 | 4 / 0 | 95.7% (96.8%, +0.09%) | yes |
| **dev 1 (`backlog-aware-gtn-dev`)** | `runs/20261114-025739-backlog-aware-gtn-dev` | **€10,125.87** | **€+1,135.57 ± 203.93** | **5.57** | **15 / 1** | **94.0% (97.3%, +0.55%)** | **yes** |
| **dev 2 (`backlog-aware-gtn-v2-dev`)** | `runs/20261114-030038-backlog-aware-gtn-v2-dev` | **€10,034.71** | **€+1,044.40 ± 188.36** | **5.54** | **15 / 1** | **94.0% (97.3%, +0.52%)** | **yes** |
| **dev 3 (`backlog-aware-gtn-ptw40-dev`)** | `runs/20261114-030237-backlog-aware-gtn-ptw40-dev` | **€10,481.58** | **€+1,491.27 ± 252.93** | **5.90** | **15 / 1** | **95.3% (97.4%, +0.68%)** | **yes** |

### Direct paired comparisons against `n14-02114` (`stack-gtn-ptw38-dev`, `€10,029.58`)
- **`backlog-aware-gtn-dev` (`mw=0.25`) vs `stack-gtn-ptw38-dev`:** **`Δmargin €+96.29 ± 73.47` (`t = 1.31`, 7 better, 6 worse, 3 tied)**, lifting mean margin from `€10,029.58` to **`€10,125.87`** (`€+1,135.57 ± 203.93`, `t = 5.57`, **15/16 better** vs Champion v2). Unblocking unurgent multi-day orders reduces `declined_backlog` to just `14` across 16 worlds (`0.88/w`, down from `74` on just 4 smoke seeds in Champion v2!) and wins `+35` additional `next_day` and `+11` `within_3_days` orders (`+€404/w` revenue) while reducing `late_refund` by `€14.00/w`.
- **`backlog-aware-gtn-v2-dev` (`mw=0.25, ifw=0.35`) vs `stack-gtn-ptw38-dev`:** **`Δmargin €+5.13 ± 112.05` (`t = 0.05`, 7 better, 7 worse, 2 tied)**, mean margin **`€10,034.71`** (`€+1,044.40 ± 188.36`, `t = 5.54`, **15/16 better** vs Champion v2), with `declined_backlog = 47` (`2.94/w`) and `in_flight_blocked = 29` (`1.81/w`), lifting worst-seed margin from `€7,078.06` to **`€7,274.97`**.
- **`backlog-aware-gtn-ptw40-dev` (`mw=0.25, ifw=0.35, ptw=0.40, ms=22`) vs `stack-gtn-ptw38-dev`:** **`Δmargin €+452.00 ± 124.81` (`t = 3.62`, 13/16 seeds better!)** and **`Δon-time +0.11%`** (lifting worst-seed on-time from `94.26%` to **`95.35%`** and mean on-time to **`97.43%`**). Against `backlog-aware-gtn-dev`, it adds **`Δmargin €+355.71 ± 103.56` (`t = 3.43`, 14/16 seeds better)**. Against Champion v2, it achieves **`Δmargin €+1,491.27 ± 252.93` (`t = 5.90`, 15/16 seeds better)**, reaching **`€10,481.58` mean margin**!

### Detailed telemetry and ledger breakdown on dev (16 worlds total / mean per world)
| Metric / Counter | Champion v2 | `stack-gtn-ptw38-dev` | `backlog-aware-gtn-dev` (`mw=0.25`) | `backlog-aware-gtn-v2-dev` (`mw=0.25, ifw=0.35`) | `backlog-aware-gtn-ptw40-dev` (`+ptw=0.40, ms=22`) |
|---|---:|---:|---:|---:|---:|
| Mean margin (€/world) | €8,990.31 | €10,029.58 | **€10,125.87** | **€10,034.71** | **€10,481.58** |
| Active won orders (total / mean) | 3,644 (227.75/w) | 4,096 (256.00/w) | 4,116 (257.25/w) | 4,116 (257.25/w) | **4,370 (273.12/w)** |
| **Total late orders (late %)** | 118 (7.38/w, 3.24%) | 112 (7.00/w, 2.73%) | 113 (7.06/w, 2.75%) | 114 (7.12/w, 2.77%) | **113 (7.06/w, 2.59%)** |
| **Worst seed on-time %** | 94.36% | 94.26% | 94.03% | 94.03% | **95.35%** |
| **Mean on-time %** | 96.75% | 97.32% | 97.30% | 97.27% | **97.43%** |
| `declined_backlog` (total / mean) | 74 on 4 smoke | — | 14 (0.88/w) | 47 (2.94/w) | **62 (3.88/w)** |
| `in_flight_blocked` (total / mean) | 0 (0.00/w) | 0 (0.00/w) | 0 (0.00/w) | 29 (1.81/w) | **49 (3.06/w)** |
| `won_same_day` (total / mean) | 1,147 (71.69/w) | 1,606 (100.38/w) | 1,580 (98.75/w) | 1,577 (98.56/w) | **1,684 (105.25/w)** |
| `won_next_day` (total / mean) | 2,362 (147.62/w) | 2,340 (146.25/w) | 2,375 (148.44/w) | 2,378 (148.62/w) | **2,531 (158.19/w)** |
| `won_within_3_days` (total / mean) | 173 (10.81/w) | 189 (11.81/w) | 200 (12.50/w) | 199 (12.44/w) | **202 (12.62/w)** |
| `won_ring` / `late_ring` | 823 / 17 | 1,003 / 30 | 1,005 / 27 | 1,008 / 26 | **1,052 / 20 (1.90%!)** |
| Ring margin (€/world) | €2,114.01 | €2,333.92 | €2,368.68 | €2,363.05 | **€2,508.18 (+€394/w)** |
| `deadline_close` warnings | 193 (12.06/w) | 225 (14.06/w) | 226 (14.12/w) | 242 (15.12/w) | 225 (14.06/w) |
| `gig_expired` | 121 (7.56/w) | 104 (6.50/w) | 107 (6.69/w) | 112 (7.00/w) | 105 (6.56/w) |
| `visit_failed` | 73 (4.56/w) | 3 (0.19/w) | 5 (0.31/w) | 11 (0.69/w) | 6 (0.38/w) |
| Ledger `revenue` (€/world) | +26,922.43 | +28,082.93 | +28,486.92 | +28,416.09 | **+29,806.67** |
| Ledger `driver_fee` (€/world) | -17,286.92 | -17,673.60 | -17,939.78 | -17,945.82 | -18,955.63 |
| Ledger `late_refund` (€/world) | -376.20 | -288.22 | -274.22 | -284.15 | **-259.44 (-31.0%)** |
| Ledger `failed_visit` (€/world) | -165.44 | -6.68 | -23.06 | -29.36 | -12.62 |

### Key Insights
- **Why `backlog_multiday_weight=0.25` + `backlog_in_flight_weight=0.35` unlocks `price_target_win=0.40, min_supply=22`:** Previously, raising `price_target_win` to `0.40` and lowering `min_supply` to `22` caused two failure modes: (a) afternoon `next_day` bookings filled up `backlog_near(pickup)` in medium/thin towns and choked off steady afternoon intake, while (b) simultaneous 15–30 car bulk batches in thinner towns (`min_supply=22..30`) slipped through `backlog_near(pickup)` all at once before any quote was answered.
- With `backlog_multiday_weight=0.25` unblocking normal multi-day afternoon intake and `backlog_in_flight_weight=0.35` blocking `49` excess in-flight batch quotes across the 16 dev seeds (`3.06/w`), `backlog-aware-gtn-ptw40-dev` wins **273.12 orders/world (+45.4 orders/w over Champion v2, +17.1 orders/w over `stack-gtn-ptw38-dev`)** while keeping total late orders at **113 (`2.59%` late, fewer than Champion v2's `118`)**, cutting ring late orders from `30` to **`20` (`1.90%` late)**, and raising the worst seed on-time share across all 16 dev seeds to **`95.35%`**!

## Verdict
**adopt** — `backlog_multiday_weight=0.25` and `backlog_in_flight_weight=0.35` with `price_target_win=0.40, min_supply=22` on top of the `n14-02114` stack (`runs/20261114-030237-backlog-aware-gtn-ptw40-dev`) achieves **`€10,481.58` mean margin (`Δmargin €+1,491.27 ± 252.93`, `t = 5.90`, 15/16 better vs Champion v2; `Δmargin €+452.00 ± 124.81`, `t = 3.62`, 13/16 better vs `stack-gtn-ptw38-dev`)** with **worst on-time 95.35%** and **mean on-time 97.43% (SAFE)**.
