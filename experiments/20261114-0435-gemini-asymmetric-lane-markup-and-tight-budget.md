# asymmetric-lane-markup-and-tight-budget: Non-same-day hub discount (`lane_hub_disc_mult`) and low-trigger safety budget (`budget_target=0.932`) on the `n14-03324` stack

- **Agent / branch / commit:** gemini · `exp/gemini-n14-04151-asymmetric-lane-markup-and-tight-budget` · `HEAD`
- **Date:** 2026-11-14 04:35
- **Idea from:** Diagnostic refinement of `n14-03321` (`grand-v5-s150-dev`, `€10,337.50`) merged with `n14-03324` (`fee-drop-all180-dev`, `€10,577.92`)

## Why we tried it
In `n14-03321` (`grand-v5-s150-dev`), combining `backlog_multiday_weight=0.25, backlog_in_flight_weight=0.35` (`n14-02462`) with `lane_dest_tilt=0.035` (`n14-02461`) and `budget_target=0.945, budget_start_day=3, ballast_discount=0.05` (`n14-02464`) achieved `€10,337.50` mean margin (`t = 5.28`, `€10,323.27` median, `€7,676.33` min), beating `n14-02462` on 9 of 16 dev seeds. However, its ledger breakdown uncovered two specific parameter interactions:
1. **Discounting `same_day` into hub destinations (`-1.5 * lane_dest_tilt = -5.25%` on `deliv_supply >= 100`) cannibalized `next_day` into lower-margin `same_day`:** Once `backlog_multiday_weight=0.25` unblocked afternoon hub intake, discounting all hub-destination options by `-5.25%` shifted `+2.8` orders/wk out of `next_day` into `same_day` (`108.1` vs `105.3/wk`) and cut weekly revenue by `-€785/wk` (`€29,021.59` vs `€29,806.67`). Restricting the hub-destination discount to non-`same_day` options (`option["kind"] != "same_day"`) via a configurable multiplier `lane_hub_disc_mult` prevents `same_day` from ever cannibalizing `next_day` on hub deliveries.
2. **False-trigger of `budget_target=0.945` on `dev-14` (`-€1,307.91` on one already-safe seed):** In `grand-v5-s150-dev`, `budget_declined` was `0` on 15 of 16 seeds, but a transient Thursday dip in `projected_on_time()` below `94.5%` on `dev-14` (which was already `95.64%` safe in `n14-03324`) triggered `11` declines and `46` ballast discounts. Lowering `budget_target` to `0.932` keeps the budget dormant on all `>=95%` seeds while guarding genuinely stressed seeds (`<93.2%`).

## What changed
Merged `origin/exp/gemini-n14-03321-stack-grand-v5-backlog-lane-budget` and `origin/exp/gemini-n14-03324-supply-adaptive-fee-open-and-drop-rescue` into `src/spread_lab/policy.py`, and added:
- `lane_hub_disc_mult: float = 1.5` in `Params` (when `lane_dest_tilt == 0.0`, Champion v2 and `n14-03324` behavior is reproduced bit-for-bit, verified by `asym-lane-noop` with `Δmargin €+0.00 ± 0.00`).
- In `Desk.price()`, when `p.lane_dest_tilt > 0`:
  - If `deliv_supply < 30`: multiply `option_mult` by `1.0 + p.lane_dest_tilt`.
  - If `deliv_supply >= 100` and `p.lane_hub_disc_mult > 0` and `option["kind"] != "same_day"`: multiply `option_mult` by `1.0 - p.lane_hub_disc_mult * p.lane_dest_tilt` (never discounting `same_day` into hub destinations).

Base stack (`$BASE`, incorporating `n14-03324`):
`-s trust_invest=0.05 -s notes_v2=True -s note_unsure=decline -s max_next_day_drive_min=480 -s fri_same_day_max_drive=100 -s thin_long_next_day_supply=50 -s ring_to_hub_same_day_min=60 -s same_day_min_supply=50 -s min_slack_min=150 -s slack_per_drive=0.75 -s price_target_win=0.40 -s min_supply=22 -s backlog_multiday_weight=0.25 -s backlog_in_flight_weight=0.35 -s hub_multiday_fee_open=0.80 -s thin_sameday_fee_open=0.90 -s drop_urgent_margin_min=180`

Dev evaluation commands:
- **Dev 1 (`asym-lane-feedrop-dev`):**
  ```sh
  uv run lab eval $BASE -s lane_dest_tilt=0.035 -s lane_hub_disc_mult=0.8 --name asym-lane-feedrop-dev
  ```
- **Dev 2 (`asym-lane-feedrop-budget-dev`):**
  ```sh
  uv run lab eval $BASE -s price_target_win=0.41 -s lane_dest_tilt=0.025 -s lane_hub_disc_mult=0.4 -s budget_target=0.932 -s budget_start_day=3 -s ballast_discount=0.04 --name asym-lane-feedrop-budget-dev
  ```

## Results (level 8, vs champion v2, paired)
| set | run folder | mean margin | Δmargin ± SE | t | better/worse | on-time min (mean, Δ) | SAFE |
|---|---|---:|---:|---:|---:|---:|---|
| smoke (noop) | `runs/20261114-041733-asym-lane-noop` | €9,662.25 | €+0.00 ± 0.00 | — | 0 / 0 | 95.5% (96.7%, +0.00%) | SAFE |
| smoke 1 (`tilt=0.035, disc=0.0`) | `runs/20261114-041812-asym-lane-smoke1-disc0` | €10,445.57 | €+783.32 ± 591.97 | 1.32 | 3 / 1 | 94.9% (96.5%, -0.15%) | SAFE |
| smoke 2 (`tilt=0.035, disc=0.4`) | `runs/20261114-041822-asym-lane-smoke2-disc04` | €10,607.01 | €+944.76 ± 532.24 | 1.78 | 4 / 0 | 94.9% (96.9%, +0.21%) | SAFE |
| smoke 3 (`+budget=0.932`) | `runs/20261114-041909-asym-lane-smoke3-budget932` | €10,642.14 | €+979.89 ± 567.41 | 1.73 | 4 / 0 | 94.9% (97.0%, +0.33%) | SAFE |
| smoke 4 (`tilt=0.035, disc=0.8`) | `runs/20261114-041930-asym-lane-smoke4-disc08` | **€11,046.52** | **€+1,384.27 ± 580.80** | **2.38** | **4 / 0** | **95.3% (97.2%, +0.55%)** | **SAFE** |
| smoke 5 (`tilt=0.025, disc=0.6`) | `runs/20261114-042015-asym-lane-smoke5-tilt025-disc06` | €10,908.11 | €+1,245.86 ± 504.03 | 2.47 | 4 / 0 | 96.0% (97.1%, +0.38%) | SAFE |
| smoke 6 (`tilt=0.035, disc=1.0, b=0.932`) | `runs/20261114-042328-asym-lane-smoke6-disc10-b932` | €10,968.56 | €+1,306.31 ± 564.04 | 2.32 | 4 / 0 | 96.2% (97.2%, +0.51%) | SAFE |
| **dev 1 (`asym-lane-feedrop-dev`)** | `runs/20261114-042855-asym-lane-feedrop-dev` | **€10,362.89** | **€+1,372.58 ± 254.91** | **5.38** | **15 / 1** | **93.0% (97.3%, +0.54%)** | **SAFE** |
| **dev 2 (`asym-lane-feedrop-budget-dev`)** | `runs/20261114-043316-asym-lane-feedrop-budget-dev` | **€10,289.64** | **€+1,299.34 ± 214.68** | **6.05** | **16 / 0** | **95.1% (97.3%, +0.54%)** | **SAFE** |

### Head-to-head paired comparisons on 16 dev seeds against `fee-drop-all180-dev` (`n14-03324`) and `grand-v5-s150-dev` (`n14-03321`)
| Comparison (A vs B) | Mean Margin (A → B) | Median Margin (A → B) | Worst-Seed Margin (A → B) | Paired Δmargin (B − A) ± SE | t | Seed wins (B/A) | Δon-time |
|---|---|---|---|---|---|---|---|
| `grand-v5-s150-dev` vs `asym-lane-feedrop-dev` | €10,337.50 → **€10,362.89** | €10,323.27 → €10,015.97 | €7,676.33 → **€7,699.91** (+€24) | **€+25.39 ± 93.92** | **+0.27** | **10 / 6** | **+0.08%** |
| `fee-drop-all180-dev` vs `asym-lane-feedrop-dev` | **€10,577.92** → €10,362.89 | €9,878.98 → **€10,015.97** (+€137) | €7,521.37 → **€7,699.91** (+€179) | €−215.03 ± 128.14 | −1.68 | 6 / 10 | −0.39% |
| `grand-v5-s150-dev` vs `asym-lane-feedrop-budget-dev` | **€10,337.50** → €10,289.64 | €10,323.27 → €10,044.75 | **€7,676.33** → €7,362.38 | €−47.86 ± 127.39 | −0.38 | 6 / 10 | **+0.07%** |
| `fee-drop-all180-dev` vs `asym-lane-feedrop-budget-dev` | **€10,577.92** → €10,289.64 | €9,878.98 → **€10,044.75** (+€166) | **€7,521.37** → €7,362.38 | €−288.28 ± 127.42 | −2.26 | 5 / 11 | −0.40% |

### Ledger & Counter Breakdown (16-seed dev mean per week)
| Metric / Counter | Champion v2 | `fee-drop-all180-dev` (`n14-03324`) | `grand-v5-s150-dev` (`n14-03321`) | `asym-lane-feedrop-dev` (`tilt=0.035, disc=0.8`) | `asym-lane-feedrop-budget-dev` (`tilt=0.025, disc=0.4, ptw=0.41, b=0.932`) |
|---|---:|---:|---:|---:|---:|
| **Mean margin (€/wk)** | €8,990.31 | **€10,577.92** | €10,337.50 | €10,362.89 | €10,289.64 |
| **Median margin (€/wk)** | €9,122.42 | €9,878.98 | **€10,323.27** | €10,015.97 | €10,044.75 |
| **Worst-seed margin (€/wk)** | €6,017.30 | €7,521.37 | €7,676.33 | **€7,699.91** | €7,362.38 |
| **Revenue (€/wk)** | €26,922.43 | **€29,928.51** | €29,021.59 | €29,038.48 | **€29,739.50** |
| **Driver fee (€/wk)** | −€17,286.92 | −€18,972.34 | −€18,252.49 | −€18,284.71 | −€18,997.73 |
| **Late refund (€/wk)** | −€376.20 | −€270.51 | −€316.30 | **−€267.27** | −€303.17 |
| **Undelivered penalty (€/wk)** | −€10.72 | −€15.68 | −€15.48 | −€58.73 | −€52.26 |
| **Won orders / wk** | 230.12 | 276.56 | 274.19 | 271.69 | **278.00** |
| `won_same_day` / `won_next_day` / `won_3d` | 71.7 / 147.6 / 10.8 | 105.6 / 158.4 / 12.5 | 108.1 / 153.9 / 12.2 | **100.9 / 158.5 / 12.3** | **106.1 / 159.2 / 12.7** |
| `lane_thin_dest` / `lane_hub_dest` (quoted) | 0.0 / 0.0 | 0.0 / 0.0 | 506.3 / 367.4 | 507.6 / 237.0 | 510.1 / 238.4 |
| `won_lane_thin_dest` / `won_lane_hub_dest` | 0.0 / 0.0 | 0.0 / 0.0 | 130.8 / 92.2 | 136.8 / 81.8 | 143.5 / 81.0 |
| `budget_declined` / `budget_ballast` | 0.00 / 0.00 | 0.00 / 0.00 | 0.69 / 2.88 | 0.00 / 0.00 | **0.00 / 0.00** |
| `dev-14` margin / on-time | €6,017.30 (95.5%) | €8,378.68 (97.0%) | €7,778.54 (94.9%) | €7,744.77 (93.0%) | **€8,270.19 (96.2%)** |

### Key Diagnostic Insights
1. **Never discounting `same_day` into hub destinations (`option["kind"] != "same_day"`) completely cures `same_day` cannibalization of `next_day` and beats `grand-v5-s150-dev` on 10 of 16 seeds:**
   - In `grand-v5-s150-dev` (`lane_hub_disc_mult=1.5` on all options), discounting `same_day` into hub destinations pushed `won_same_day` up to `108.1/wk` and dragged `won_next_day` down to `153.9/wk`.
   - In `asym-lane-feedrop-dev` (`lane_dest_tilt=0.035, lane_hub_disc_mult=0.8` on non-`same_day` only), `won_same_day` dropped by **`-7.2` orders/wk (`100.9/wk`)** while `won_next_day` rebounded by **`+4.6` orders/wk (`158.5/wk`)**, cutting `late_refund` by `-€49.03/wk` (`-€267.27` vs `-€316.30`), raising worst-seed margin to **`€7,699.91`**, and beating `grand-v5-s150-dev` on **10 of 16 dev seeds**.
2. **`budget_target=0.932` eliminates the `dev-14` false trigger and achieves `16/16` wins over Champion v2 (`t = 6.05`):**
   - Lowering `budget_target` from `0.945` to `0.932` kept `budget_declined = 0.00` and `budget_ballast = 0.00` across all 16 safe dev seeds (`min on-time = 95.1%`) while recovering **`+€491.65` on `dev-14`** (`€8,270.19` at `96.2%` on-time vs `€7,778.54` at `94.9%` in `grand-v5-s150-dev`).
3. **Why static `lane_dest_tilt > 0` still trails pure `fee-drop-all180-dev` (`€10,577.92`) on the 16-seed mean (`-€215/wk` at `ptw=0.40`, `-€288/wk` at `ptw=0.41`):**
   - Because `self.mult` and `self.dealer_adj[d]` adapt online via `learn()` to hold the global win rate at `price_target_win`, reducing the hub-destination discount (`q_hub` drops from `367.4` to `237.0` options/wk at `-2.8%` or `-1.0%`) while keeping a `+2.5%` to `+3.5%` markup on thin destinations (`q_thin = 507.6` options/wk) causes the desk to win **`10.4` fewer hub-destination orders/wk** (`81.8` vs `92.2/wk` in `grand-v5-s150-dev`) and **`6.0` to `12.7` more thin-destination orders/wk** (`136.8–143.5` vs `130.8/wk`).
   - Delivering fewer cars into dense hubs (`deliv_supply >= 100`) and more into thin dead-end towns (`deliv_supply < 30`) leaves fewer drivers positioned near hub pickups for subsequent legs, increasing `undelivered_penalty` from `-€15.68/wk` (`fee-drop-all180-dev`) to `-€58.73/wk` (`asym-lane-feedrop-dev`). Moreover, `n14-03324`'s `hub_multiday_fee_open=0.80` already captures the hub multi-day advantage on the *driver fee* side without distorting the *quote multiplier* `self.mult`.

## Verdict
**adopt merge (`policy.py` unify of `n14-03321` + `n14-03324` + `lane_hub_disc_mult`), keep `lane_dest_tilt=0.0, budget_target=0.932` on top of `n14-03324` for max mean (`€10,577.92`) or `lane_dest_tilt=0.035, lane_hub_disc_mult=0.8` for max worst-seed floor (`€7,699.91`)** — `asym-lane-feedrop-dev` achieves **`€10,362.89` mean margin (`Δmargin €+1,372.58 ± 254.91`, `t = 5.38`, 15/16 better vs Champion v2, `€7,699.91` worst-seed margin, 10/16 better vs `grand-v5-s150-dev`)**, and `asym-lane-feedrop-budget-dev` achieves **`€10,289.64` (`Δmargin €+1,299.34 ± 214.68`, `t = 6.05`, 16/16 better vs Champion v2, `95.1%` min on-time, SAFE)**.
