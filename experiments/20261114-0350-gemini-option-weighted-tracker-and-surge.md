# n14-03323-option-weighted-tracker-and-surge: Revenue-weighted price learning (`learn_price_exp`) and win-streak surge (`win_streak_boost`)

- **Agent / branch / commit:** gemini · `exp/gemini-n14-03323-option-weighted-tracker-and-surge` · `HEAD`
- **Date:** 2026-11-14 03:50
- **Idea from:** Structural pricing diagnostics (`learn_price_exp`, `win_streak_boost`) stacked on `origin/exp/gemini-n14-02462-deadline-aware-backlog` (`€10,481.58/wk`)

## Why we tried it
We tested two hypotheses targeting `Desk.learn()` (`src/spread_lab/policy.py`) on top of the `n14-02462` configuration (`€10,481.58` mean dev margin):
1. **Revenue-weighted price learning (`learn_price_exp`):** In Champion v2 and `n14-02462`, `Desk.learn()` updates `self.mult` and `self.dealer_adj` using an unweighted count-based step `step = (1 - p.price_target_win) if won else -p.price_target_win`, treating a €90 short-haul car identically to a €320 long-haul car. Weighting `step` by `clamp((ref_list / 16000.0) ** p.learn_price_exp, 0.5, 1.75)` (where `ref_list = request["options"][0]["listPriceCents"]` and €160 is the median level-8 list price) makes `self.mult` and `self.dealer_adj` track revenue-weighted win share rather than order count.
2. **Win-streak surge accelerator (`win_streak_boost`):** While `loss_streak_freeze = 12` freezes `self.mult` during a `-20%` price war, there is no upward accelerator when a regional competitor outage (`+30%` backup competitor in a town + 80 km for one working day) produces a streak of consecutive wins. Adding `win_streak_boost` multiplies upward learning steps when `self.win_streak >= 3` by `1.0 + p.win_streak_boost * min(self.win_streak - 2, 4)`.

## What changed
Merged `origin/exp/gemini-n14-02462-deadline-aware-backlog` and added two `Params` fields in `src/spread_lab/policy.py` whose defaults (`0.0`) reproduce Champion v2 and `n14-02462` bit-for-bit (`Δmargin €+0.00 ± 0.00` on smoke):
- `learn_price_exp: float = 0.0` — exponent on `(ref_list / 16000.0)` clamped to `[0.5, 1.75]` scaling `step` in `Desk.learn()`.
- `win_streak_boost: float = 0.0` — surge multiplier per consecutive win for `self.win_streak >= 3` (reset daily and on any loss), tracked via `self.stats["outage_surge_steps"]`.

Base flags (`n14-02462` configuration):
```sh
BASE="-s trust_invest=0.05 -s notes_v2=True -s note_unsure=decline -s max_next_day_drive_min=480 -s fri_same_day_max_drive=100 -s thin_long_next_day_supply=50 -s ring_to_hub_same_day_min=60 -s same_day_min_supply=50 -s min_slack_min=150 -s slack_per_drive=0.75 -s backlog_multiday_weight=0.25 -s backlog_in_flight_weight=0.35 -s price_target_win=0.40 -s min_supply=22"
```
Run commands on `dev`:
```sh
uv run lab eval $BASE -s learn_price_exp=0.35 --name tracker-exp035-dev
uv run lab eval $BASE -s learn_price_exp=0.35 -s price_target_win=0.45 --name tracker-exp035-ptw45-dev
```

## Results (level 8, vs champion v2 and vs `n14-02462`, paired)
| set | run folder | mean margin | vs Champion v2 (Δ ± SE, t) | vs `n14-02462` (Δ ± SE, t) | better/worse vs `n14-02462` | on-time min (mean) | SAFE |
|---|---|---:|---:|---:|---:|---:|---|
| smoke (noop) | `runs/20261114-033649-tracker-surge-noop` | €9,662.25 | €+0.00 ± 0.00 (—) | — | — | 95.5% (96.7%) | yes |
| smoke (`n14-02462` base) | `runs/20261114-025653-backlog-smoke4-ptw40-ms22` | €10,726.20 | €+1,063.95 ± 579.41 (1.84) | €+0.00 ± 0.00 (—) | 0 / 0 | 95.7% (96.8%) | yes |
| smoke 1 (`exp=0.50`) | `runs/20261114-033842-tracker-smoke1-exp05` | €10,748.40 | €+1,086.15 ± 315.02 (3.45) | €+22.20 ± 269.23 (0.08) | 3 / 1 | 94.4% (96.4%) | yes |
| smoke 2 (`exp=0.35`) | `runs/20261114-033914-tracker-smoke2-exp035` | **€10,886.61** | **€+1,224.37 ± 424.87 (2.88)** | **€+160.41 ± 284.84 (0.56)** | **2 / 2** | **95.8% (97.3%)** | **yes** |
| smoke 3 (`surge=0.30`) | `runs/20261114-034017-tracker-smoke3-surge30` | €10,571.93 | €+909.69 ± 835.13 (1.09) | €-154.26 ± 412.60 (-0.37) | 2 / 2 | 96.5% (97.3%) | yes |
| smoke 4 (`exp=0.35, surge=0.30`) | `runs/20261114-034121-tracker-smoke4-both` | €10,474.00 | €+811.75 ± 455.83 (1.78) | €-252.20 ± 277.70 (-0.91) | 1 / 3 | 96.3% (97.0%) | yes |
| **dev (`n14-02462` base)** | `runs/20261114-030237-backlog-aware-gtn-ptw40-dev` | **€10,481.58** | **€+1,491.27 ± 252.93 (5.90)** | **€+0.00 ± 0.00 (—)** | — | **95.3% (97.4%)** | **yes** |
| **dev 1 (`tracker-exp035-dev`)** | `runs/20261114-034357-tracker-exp035-dev` | €10,154.62 | €+1,164.32 ± 225.27 (5.17) | €-326.96 ± 199.73 (-1.64) | 6 / 10 | 93.5% (97.2%) | yes |
| **dev 2 (`tracker-exp035-ptw45-dev`)** | `runs/20261114-034806-tracker-exp035-ptw45-dev` | €10,036.30 | €+1,045.99 ± 294.69 (3.55) | €-445.28 ± 190.21 (-2.34) | 4 / 12 | 92.8% (96.4%) | yes |

### Telemetry and ledger breakdown on dev (mean per world across 16 worlds)
| Metric / Counter | Champion v2 | `n14-02462` (`ptw=0.40`, `exp=0.0`) | `tracker-exp035-dev` (`ptw=0.40`, `exp=0.35`) | `tracker-exp035-ptw45-dev` (`ptw=0.45`, `exp=0.35`) |
|---|---:|---:|---:|---:|
| Mean margin (€/world) | €8,990.31 | **€10,481.58** | €10,154.62 | €10,036.30 |
| Won orders / world | 227.75 | **273.12** | 262.75 | 288.00 |
| Ledger `revenue` (€/world) | +26,922.43 | **+29,806.67** | +29,119.68 | +30,937.56 |
| **Revenue per won order (€/order)** | €118.21 | €109.13 | **€110.83 (+€1.70)** | €107.42 |
| Ledger `driver_fee` (€/world) | -17,286.92 | -18,955.63 | -18,489.33 | -20,350.62 |
| Driver fee per won order (€/order) | €75.90 | €69.40 | €70.37 | €70.66 |
| Ledger `late_refund` (€/world) | -376.20 | **-259.44** | -360.91 | -420.60 |
| Ledger `undelivered_penalty` (€/world) | -10.72 | -15.47 | -10.45 | -10.10 |
| `won_same_day` / `won_next_day` / `won_3d` | 71.7 / 147.6 / 10.8 | 105.2 / 158.2 / 12.6 | 100.3 / 152.6 / 12.6 | 112.8 / 166.4 / 11.8 |
| `deadline_close` / `gig_expired` | 12.06 / 7.56 | **14.06 / 6.56** | 16.25 / 8.31 | 22.62 / 10.56 |
| Daily mean `price / list` (d0 → d4) | — | 1.433 → 1.629 | 1.445 → 1.647 | — |

### What went wrong (diagnostic findings)
1. **Why `learn_price_exp=0.35` increased revenue per won order (`+€1.70/order`, from `€109.13` to `€110.83`) and won on smoke (`+€160.41/w`), but lost `-€326.96 ± 199.73` across all 16 dev seeds:**
   - In level-8 worlds, the competitor's lane factor is systematically higher on long-haul / high-`listPriceCents` routes (`ref_list > €160`, where return work is scarce) than on short-haul routes (`ref_list < €160`). Moreover, our short-haul `same_day` quotes carry `+5%` `same_day_markup`.
   - Consequently, at a flat `self.mult`, our desk wins **more than 40%** of high-`listPriceCents` quotes and **less than 40%** of low-`listPriceCents` quotes.
   - Weighting `step` by `(ref_list / 16000.0) ** 0.35` therefore amplifies positive `won=True` steps (`w > 1` on expensive routes) relative to negative `won=False` steps (`w < 1` on cheap routes). That induces an upward drift of `+1.2%` to `+1.8%` in `self.mult` (`d0: 1.445` vs `1.433`, `d4: 1.647` vs `1.629`), which acts like lowering `price_target_win` from `0.40` to `~0.38` and sacrifices `10.37` won orders/world (`262.75` vs `273.12`, `-€687/w` revenue).
   - Raising `price_target_win=0.45` (`tracker-exp035-ptw45-dev`) overcorrects in the opposite direction (`288.00` won orders/world, `deadline_close` jumping from `14.06/w` to `22.62/w`, `late_refund` rising to `€420.60/w`), leaving mean margin at `€10,036.30`.
2. **Why `win_streak_boost=0.30` hurt smoke margin (`-€154.26/w` standalone, `-€252.20/w` combined):**
   - At `price_target_win = 0.40`, streaks of `>= 3` consecutive wins across the global request stream occur **52.25 times per week** (`outage_surge_steps = 52.25/w` in `tracker-smoke3-surge30`, `55.75/w` in `tracker-smoke4-both`), mostly during ordinary daytime flow, bulk yard requests, or `trust_invest` quotes rather than regional outages.
   - Boosting `step` on global `self.mult` during those 52–56 steps/week overprices all non-outage regions, cutting smoke volume from `284.50` to `274.75` won orders/world (`258.50` when combined with `learn_price_exp=0.35`).

## Verdict
**reject** — Although `learn_price_exp=0.35` (`runs/20261114-034357-tracker-exp035-dev`) is **SAFE** (`93.5%` min on-time) and beats Champion v2 by **`Δmargin €+1,164.32 ± 225.27` (`t = 5.17`, 15/16 better)** while lifting revenue per won order by **`+€1.70` (`€110.83` vs `€109.13`)**, it trails the `n14-02462` base (`€10,481.58`) by **`Δmargin €-326.96 ± 199.73` (`t = -1.64`, 6/16 better)** on dev because higher win rates on expensive long-haul routes cause revenue-weighted learning to drift `self.mult` upward by `~1.5%`.
