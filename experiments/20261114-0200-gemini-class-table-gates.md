# n14-01391-class-table-gates: Four surgical selection gates from the 16-world v2 class table

- **Agent / branch / commit:** gemini · `exp/gemini-n14-01391-class-table-gates` · pending commit
- **Date:** 2026-11-14 02:00
- **Idea from:** `n14-11-class-table` (`exp/gemini-n14-11-class-table`, R2 + R5 across all 16 revealed champion v2 dev worlds)

## Why we tried it
Revealing all 16 champion v2 dev worlds (3,644 active won orders, 118 late orders) exposed four sharp boundary errors in `Desk.price`:
1. **`next_day > 480–500 min` Lapland trap:** `long_drive_min = 300` only drops `same_day` (`option["deadline"] // DAY <= ready // DAY`), leaving `next_day` open for 500–600 min drives. Across the 16 dev worlds, `next_day` with `drive > 500 min` won 80 orders, had 23 late (28.8% late — 19.5% of all 118 late orders in v2), and lost -€45.60/order (-€3,648 total = -€228/world) before counting dealer trust halving (`drive > 480 min` had 23/89 late = 25.8%, -€2,951). Meanwhile, `within_3_days` with `drive > 500 min` had 0 late (0/13) and +€123.75/order.
2. **Thin regional hubs (`s30 ∈ [30, 49]`) on `next_day > 300 min`:** Outside the capital/ring, regional hubs with `30 <= supply < 50` had 18.4% late (9/49) on `next_day > 300 min` (`within_3_days` there was 0/10 = 0.0% late at €72.48/order), whereas hubs with `supply >= 50` had 2.4% late (5/206) and €45.77/order.
3. **Friday `same_day >= 100 min`:** On Friday (`ready // DAY >= 4`), drivers are busy completing Thursday's peak `next_day` wave, so Friday `same_day` with `drive >= 100 min` jumped to 19.0% late (4/21, fee/typ 1.28), while Friday `next_day 100-300m` was 2.1% late at €55.91/order.
4. **`ring -> capital (< 60 min)` `same_day` opening:** In Hyvinkää and Porvoo (`is_ring`), 436 of 452 declined requests were declined solely because the dealer requested `same_day` only and `far_options="slow"` dropped `same_day`. Yet won `ring -> capital (< 60 min)` orders (`n = 143`, delivering into the 300–450 driver Capital pool) had 0 late (0.0% late), €22.14/order, and 83% booked within 30 minutes of posting.

## What changed
Added four fields to `Params` in `src/spread_lab/policy.py` (all defaulting to `0` so default behaviour matches champion v2 identically):
- `max_next_day_drive_min: int = 0` — when `> 0` and `drive > p.max_next_day_drive_min`, drop any option with `option["deadline"] // DAY <= ready // DAY + 1` (`same_day` and `next_day`, steering to `within_3_days` if offered, else declining) and increment `self.stats["dropped_next_day_long"]`.
- `thin_long_next_day_supply: int = 0` — when `> 0`, for non-ring pickups (`not is_ring`) with `supply < p.thin_long_next_day_supply` and `drive > p.long_drive_min`, drop options with `option["deadline"] // DAY <= ready // DAY + 1` and increment `self.stats["dropped_thin_long_next_day"]`.
- `fri_same_day_max_drive: int = 0` — when `> 0`, on Friday (`ready // DAY >= 4`), if `option["kind"] == "same_day"` and `drive >= p.fri_same_day_max_drive`, drop the option and increment `self.stats["dropped_fri_same_day"]`.
- `ring_to_hub_same_day_min: int = 0` — when `> 0`, in the `is_ring and p.far_options == "slow" and option["kind"] == "same_day"` check, do not drop `same_day` (and bypass `same_day_min_supply` for it) if the final leg's delivery place has `self.supply.get(legs[-1]["delivery"]["placeId"], 0) >= 200` and `drive <= p.ring_to_hub_same_day_min`; increment `self.stats["quoted_ring_hub_same_day"]` (and track `won_ring_hub_same_day`, `late_ring_hub_same_day`).

Run with:
```sh
uv run lab eval -s max_next_day_drive_min=480 -s fri_same_day_max_drive=100 -s thin_long_next_day_supply=50 -s ring_to_hub_same_day_min=60 -s same_day_min_supply=50 --name gates-full-dev
```

## Results (level 8, vs champion v2, paired)
| set | run folder | mean margin | Δmargin ± SE | t | better/worse | on-time min (mean) | SAFE |
|---|---|---|---|---|---|---|---|
| smoke (noop) | `20261114-014159-gates-noop` | €9,662.25 | +€0.00 ± 0.00 | — | 0 / 0 | 95.5% (96.7%) | yes |
| smoke (`nd480`) | `20261114-014420-gates-smoke-nd480` | €9,821.59 | +€159.34 ± 292.27 | 0.55 | 2 / 2 | 94.9% (97.3%) | yes |
| smoke (`close480`) | `20261114-014535-gates-smoke-close480` | €9,512.27 | -€149.97 ± 337.44 | -0.44 | 2 / 2 | 94.9% (97.0%) | yes |
| smoke (`full480`) | `20261114-014655-gates-smoke-full480` | €9,426.30 | -€235.95 ± 366.79 | -0.64 | 2 / 2 | 95.5% (96.7%) | yes |
| smoke (`full500`) | `20261114-014736-gates-smoke-full500` | €9,701.64 | +€39.39 ± 445.26 | 0.09 | 2 / 2 | 96.0% (96.8%) | yes |
| smoke (`ring500`, `s_sd=100`) | `20261114-014828-gates-smoke-ring500` | €9,988.89 | +€326.64 ± 156.52 | 2.09 | 4 / 0 | 96.6% (97.7%) | yes |
| **dev (`gates-close-dev`)** | `20261114-014953-gates-close-dev` | **€9,258.90** | **+€268.60 ± 189.62** | **1.42** | **10 / 6** | **94.9% (97.6%)** | **yes** |
| **dev (`gates-full-dev`)** | `20261114-015204-gates-full-dev` | **€9,317.88** | **+€327.58 ± 198.04** | **1.65** | **11 / 5** | **94.1% (97.2%)** | **yes** |
| dev (`gates-taxback-dev`) | `20261114-015653-gates-taxback-dev` | €9,514.75 | +€524.45 ± 344.17 | 1.52 | 11 / 5 | 89.8% (96.5%) | no (15/16) |

### New stats counters and ledger breakdown on dev (16 worlds total / mean per world)
| Metric | Champion v2 | `gates-close-dev` | `gates-full-dev` | `gates-taxback-dev` |
|---|---|---|---|---|
| `dropped_next_day_long` | 0 (0.00/w) | 213 (13.31/w) | 213 (13.31/w) | 244 (15.25/w) |
| `dropped_thin_long_next_day` | 0 (0.00/w) | 161 (10.06/w) | 156 (9.75/w) | 318 (19.88/w) |
| `dropped_fri_same_day` | 0 (0.00/w) | 890 (55.62/w) | 894 (55.88/w) | 1,036 (64.75/w) |
| `quoted_ring_hub_same_day` | 0 (0.00/w) | 0 (0.00/w) | 657 (41.06/w) | 556 (34.75/w) |
| `won_ring_hub_same_day` | 0 (0.00/w) | 0 (0.00/w) | 198 (12.38/w) | 195 (12.19/w) |
| `late_ring_hub_same_day` | 0 (0.00/w) | 0 (0.00/w) | 2 (0.12/w, **1.01% late**) | 4 (0.25/w, **2.05% late**) |
| Total active won orders | 3,644 (227.8/w) | 3,582 (223.9/w) | 3,743 (233.9/w) | 4,383 (273.9/w) |
| Total late orders (late %) | 118 (3.24%) | **84 (2.35%)** | **107 (2.86%)** | 159 (3.63%) |
| `deadline_close` warnings | 193 (12.1/w) | **131 (8.2/w, -32%)** | 196 (12.2/w) | 309 (19.3/w) |
| Ring margin (€/world) | €2,114.0 | €2,143.9 | **€2,401.5 (+€287.5/w)** | €2,067.9 |
| Late refunds (€/world) | -€380 | **-€180 (+€200/w)** | -€260 (+€120/w) | -€420 |
| Driver fees (€/world) | -€17,290 | -€15,910 | -€16,090 | -€19,290 |
| Revenue (€/world) | €26,920 | €25,590 | €25,950 | €29,540 |

Key findings from the counters:
1. **Closing gates (`gates-close-dev`) cut late orders by 28.8% (from 118 to 84 across 16 worlds)** and cut `deadline_close` warnings by 32% (from 193 to 131), halving late refunds from €380/world to €180/world and lifting mean on-time share by +0.87% (to 97.6%, worst world 94.9%) while adding +€268.60 ± 189.62/world (10/6 worlds better).
2. **`ring -> capital (< 60 min)` `same_day` (`ring_to_hub_same_day_min=60`) is rock-solid in live closed-loop evaluation:** In `gates-full-dev`, it quoted 657 `same_day` options on ring-to-capital requests, won **198 orders (12.4/world)**, and had **only 2 late orders across all 16 worlds (1.01% late!)**, lifting ring margin by **+€287.50/world** (from €2,114 to €2,401.5/world) and raising overall Δmargin to **+€327.58 ± 198.04 (t=1.65, 11/5 better, SAFE, worst on-time 94.1%)**. Note that on smoke, keeping `same_day_min_supply=100` (`gates-smoke-ring500`) instead of lowering it to 50 gave an even cleaner result (+€326.64 ± 156.52, t=2.09, 4/4 better, +1.05% on-time) because `same_day_min_supply=50` opens regional `same_day` in 50–99 driver towns (which caused the extra `deadline_close` warnings in `gates-full-dev`, especially on `dev-07`).
3. **Aggressive tax-back (`gates-taxback-dev`) overloads `dev-07`:** Combining `price_target_win=0.40`, `min_supply=20`, `same_day_min_supply=50`, and `min_slack_min=140` pushed volume to 273.9 won/world (+€524.45 ± 344.17, 11/5 better), but `dev-07` surged to 323 won orders and dipped to 89.8% on-time (unranked by 1 order).

## Verdict
**adopt (`gates-full-dev` or `gates-close-dev` + `ring_to_hub_same_day_min=60` with `same_day_min_supply=100`)** — `gates-full-dev` is SAFE across all 16 dev worlds (min on-time 94.1%, mean 97.2%, +0.42% Δon-time) and improves mean margin by **+€327.58 ± 198.04 (t=1.65, better on 11/16 seeds)**; `gates-close-dev` cuts late orders by 29% (118 → 84, mean on-time 97.6%, min 94.9%) with **+€268.60 ± 189.62 (t=1.42, 10/16)**.
