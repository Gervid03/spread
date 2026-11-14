# stack-grand-v5-backlog-lane-budget: Grand Synthesis v5 merging deadline-aware backlog, centered lane-cost pricing, and Thu–Fri safety budget

- **Agent / branch / commit:** gemini · `exp/gemini-n14-03321-stack-grand-v5-backlog-lane-budget` · `819a9dc`
- **Date:** 2026-11-14 03:46
- **Idea from:** Combination of Wave-0246 dev winners (`origin/exp/gemini-n14-02462-deadline-aware-backlog`, `origin/exp/gemini-n14-02461-centered-lane-cost-pricing`, `origin/exp/gemini-n14-02464-thursday-friday-safety-budget`, and `n14-02244` / `origin/exp/gemini-n14-02463-stack-gtn-feewarn-v4`)

## Why we tried it
In Wave 0246, four independent mechanisms built on top of the `n14-02114` GTN base (`6e02bf5`) each achieved `t = 5.19` to `6.87` on the 16 dev seeds (`+€1,177` to `+€1,491/wk` vs Champion v2) while keeping worst-seed on-time at `94.1%–95.35%` (`SAFE`):
1. **Deadline-aware & in-flight backlog (`n14-02462`):** `backlog_multiday_weight=0.25` stops unurgent multi-day orders from blocking afternoon intake, while `backlog_in_flight_weight=0.35` counts open unanswered quotes to block real-time bulk-yard bursts (`€10,481.58`, `Δmargin €+1,491.27 ± 252.93`, `95.35%` min on-time).
2. **Centered destination-supply lane tilt (`n14-02461`):** `lane_dest_tilt=0.035` adds `+3.5%` on thin destinations (`deliv_supply < 30`) and `-5.25%` on dense hub destinations (`deliv_supply >= 100`) to harvest competitor lane premia on dead-end routes and steer volume into high-return hubs (`€10,262.15`, `Δmargin €+1,271.84 ± 217.21`, `95.3%` min on-time).
3. **Thursday–Friday safety budget & ballast (`n14-02464`):** `budget_target=0.945, budget_start_day=3, ballast_discount=0.05` stays dormant (`0` quotes touched) on Mon–Wed and on already-safe worlds, activating only on Thu–Fri on stressed seeds to drop risky late-week classes and discount safe hub ballast (`€10,302.26`, `t = 6.87`, `16/16` better at `min_supply=22`; `€10,319.79` at `min_supply=20`).
4. **Tighter slack gate (`n14-02244` / `n14-02463`):** `min_slack_min=140, slack_per_drive=0.75` (`€10,432.83`, `t = 6.80`) and `fee_warn=1.50, fee_step_min=20`.

We merged all three feature branches into a single unified `Desk` policy and tested their combined interaction on `smoke` and `dev`.

## What changed
Merged `origin/exp/gemini-n14-02462-deadline-aware-backlog`, `origin/exp/gemini-n14-02461-centered-lane-cost-pricing`, and `origin/exp/gemini-n14-02464-thursday-friday-safety-budget` into `src/spread_lab/policy.py`, resolving conflicts in `Desk.__init__` (retaining both `self.lost_requests` and `self.ballast_disc`) and `Desk.price` (applying `lane_dest_tilt`, `cost_ratio_slope`, and `disc` multiplicatively to `option_mult`). All new `Params` fields default to off/v2-equivalent (`backlog_multiday_weight=1.0`, `backlog_in_flight_weight=0.0`, `lane_dest_tilt=0.0`, `cost_ratio_slope=0.0`, `budget_target=0.0`, `budget_start_day=3`, `ballast_discount=0.06`), verified by `grand-v5-noop` (`Δmargin €+0.00 ± 0.00` on smoke).

Base GTN flags (`$BASE`):
`-s trust_invest=0.05 -s notes_v2=True -s note_unsure=decline -s max_next_day_drive_min=480 -s fri_same_day_max_drive=100 -s thin_long_next_day_supply=50 -s ring_to_hub_same_day_min=60 -s same_day_min_supply=50 -s slack_per_drive=0.75`

Run best dev config with:
```sh
uv run lab eval $BASE -s min_slack_min=150 -s price_target_win=0.40 -s min_supply=22 -s backlog_multiday_weight=0.25 -s backlog_in_flight_weight=0.35 -s lane_dest_tilt=0.035 -s budget_target=0.945 -s budget_start_day=3 -s ballast_discount=0.05 --name grand-v5-s150-dev
```

## Results (level 8, vs champion, paired)
| set | run folder | mean margin | Δmargin ± SE | t | better/worse | on-time min | SAFE |
|---|---|---|---|---|---|---|---|
| smoke (noop) | `20261114-033519-grand-v5-noop` | €9,662.25 | €+0.00 ± 0.00 | — | 0/0 | 95.5% | SAFE |
| smoke (s150, ms22) | `20261114-033623-grand-v5-smoke1-bl-lane` | €11,085.89 | €+1,423.64 ± 598.64 | 2.38 | 4/0 | 96.7% | SAFE |
| smoke (s140, ms22) | `20261114-033656-grand-v5-smoke2-slack140` | €10,951.16 | €+1,288.91 ± 482.60 | 2.67 | 4/0 | 96.6% | SAFE |
| smoke (s140, ms20) | `20261114-033810-grand-v5-smoke3-ms20` | €10,776.23 | €+1,113.99 ± 878.35 | 1.27 | 3/1 | 95.4% | SAFE |
| smoke (s140, ms22, fw150) | `20261114-033846-grand-v5-smoke4-fw150` | €10,592.60 | €+930.36 ± 403.14 | 2.31 | 4/0 | 95.2% | SAFE |
| **dev (s150, ms22)** | `20261114-033955-grand-v5-s150-dev` | **€10,337.50** | **€+1,347.19 ± 255.33** | **5.28** | **15/1** | **94.2%** | **SAFE** |
| **dev (s140, ms22)** | `20261114-034146-grand-v5-s140-dev` | **€10,180.61** | **€+1,190.30 ± 229.67** | **5.18** | **15/1** | **94.2%** | **SAFE** |
| **dev (s140, ms20)** | `20261114-034457-grand-v5-best-dev` | **€10,263.18** | **€+1,272.88 ± 269.32** | **4.73** | **14/2** | **95.1%** | **SAFE** |

### Head-to-head paired comparisons on 16 dev seeds against Wave-0246 single-mechanism leaders
| Comparison (`uv run lab compare A B`) | Mean Margin B | Median Margin (A vs B) | Worst-Seed Margin (A vs B) | Paired Δmargin (B − A) ± SE | t | Seed wins (B/A) | Δon-time |
|---|---|---|---|---|---|---|---|
| `backlog-aware-gtn-ptw40-dev` (€10,481.58) vs `grand-v5-s150-dev` | €10,337.50 | €9,855.85 vs **€10,323.27** (+€467) | €7,196.05 vs **€7,676.33** (+€480) | €−144.08 ± 180.87 | −0.80 | **9 / 7** | −0.22% |
| `v3-gated-taxback-dev` (€10,432.83) vs `grand-v5-s150-dev` | €10,337.50 | €9,877.26 vs **€10,323.27** (+€446) | €7,387.18 vs **€7,676.33** (+€289) | €−95.33 ± 233.27 | −0.41 | **9 / 7** | −0.01% |
| `backlog-aware-gtn-ptw40-dev` (€10,481.58) vs `grand-v5-best-dev` (ms20) | €10,263.18 | €9,855.85 vs **€10,251.38** (+€396) | €7,196.05 vs **€7,833.67** (+€638) | €−218.40 ± 192.89 | −1.13 | 7 / 9 | −0.06% |
| `v3-gated-taxback-dev` (€10,432.83) vs `grand-v5-best-dev` (ms20) | €10,263.18 | €9,877.26 vs **€10,251.38** (+€374) | €7,387.18 vs **€7,833.67** (+€446) | €−169.65 ± 200.69 | −0.85 | 8 / 8 | +0.15% |
| `backlog-aware-gtn-ptw40-dev` (€10,481.58) vs `grand-v5-s140-dev` | €10,180.61 | €9,855.85 vs **€9,936.35** (+€81) | €7,196.05 vs **€7,679.85** (+€484) | €−300.97 ± 174.95 | −1.72 | 6 / 10 | −0.25% |
| `v3-gated-taxback-dev` (€10,432.83) vs `grand-v5-s140-dev` | €10,180.61 | €9,877.26 vs **€9,936.35** (+€59) | €7,387.18 vs **€7,679.85** (+€293) | €−252.22 ± 221.99 | −1.14 | 6 / 10 | −0.04% |

### Ledger & Counter Breakdown (16-seed dev mean per week)
| Metric | Champion v2 | `v3-gated-taxback-dev` | `backlog-aware-gtn-ptw40-dev` | `grand-v5-s150-dev` | `grand-v5-s140-dev` | `grand-v5-best-dev` (ms20) |
|---|---|---|---|---|---|---|
| **Mean margin (€/wk)** | €8,990.31 | €10,432.83 | **€10,481.58** | €10,337.50 | €10,180.61 | €10,263.18 |
| **Median margin (€/wk)** | €9,122.42 | €9,877.26 | €9,855.85 | **€10,323.27** | €9,936.35 | €10,251.38 |
| **Worst-seed margin (€/wk)** | €6,017.30 | €7,387.18 | €7,196.05 | €7,676.33 | €7,679.85 | **€7,833.67** |
| **Revenue (€/wk)** | €26,922.43 | €29,895.42 | €29,806.67 | €29,021.59 | €29,017.70 | €29,139.37 |
| **Driver fee (€/wk)** | −€17,286.92 | −€19,070.55 | −€18,955.63 | −€18,252.49 | −€18,413.52 | −€18,438.45 |
| **Late refund (€/wk)** | −€376.20 | −€293.35 | −€259.44 | −€316.30 | −€317.60 | −€290.30 |
| **Undelivered penalty (€/wk)** | −€10.72 | −€20.14 | −€15.47 | −€15.48 | −€10.07 | −€53.40 |
| **Release fee (€/wk)** | −€53.48 | −€40.11 | −€57.55 | −€48.69 | −€46.85 | −€39.95 |
| **Won orders / wk** | 230.12 | 277.75 | 276.06 | 274.19 | 274.62 | 275.69 |
| `won_same_day` / `won_next_day` / `won_3d` | 71.7 / 147.6 / 10.8 | 103.3 / 162.4 / 12.1 | 105.3 / 158.2 / 12.6 | 108.1 / 153.9 / 12.2 | 108.7 / 153.6 / 12.3 | 105.2 / 158.3 / 12.2 |
| `won_ring` / `late_ring` (ring late %) | 51.44 / 1.06 (2.06%) | 55.56 / 0.94 (1.69%) | 65.75 / 1.25 (1.90%) | 68.94 / 1.56 (2.26%) | 69.19 / 1.62 (2.34%) | 59.12 / 0.94 (1.59%) |
| `declined_backlog` / `in_flight_blocked` | 0.0 / 0.0 | 0.0 / 0.0 | 3.88 / 3.06 | 3.25 / 2.06 | 3.50 / 2.56 | 4.00 / 2.56 |
| `won_lane_thin_dest` / `won_lane_hub_dest` | 0 / 0 | 0 / 0 | 0 / 0 | 130.81 / 92.19 | 131.44 / 92.69 | 132.88 / 91.19 |
| `budget_declined` / `budget_ballast` | 0 / 0 | 0 / 0 | 0 / 0 | 0.69 / 2.88 | 2.44 / 4.81 | 2.50 / 5.31 |
| `deadline_close` / `gig_expired` | 12.06 / 7.56 | 14.69 / 7.56 | 14.06 / 6.56 | 16.25 / 7.81 | 16.50 / 7.75 | 15.81 / 7.62 |

### Key diagnostic insight: why the mechanisms overlap on high-volume seeds
1. **`grand-v5-s150-dev` wins 9/16 seeds head-to-head against both `backlog-aware-gtn-ptw40-dev` and `v3-gated-taxback-dev`, and raises median margin by `+€467/wk` (`€10,323.27`) and worst-seed margin by `+€480/wk` (`€7,676.33`)**:
   - On tough/medium seeds (`dev-01 +€988`, `dev-02 +€374`, `dev-04 +€253`, `dev-05 +€480`, `dev-09 +€528`, `dev-12 +€681`), combining `lane_dest_tilt=0.035` with `backlog_multiday_weight=0.25, backlog_in_flight_weight=0.35` lifts `dev-01` and `dev-02` on-time to `96.9%` and `97.8%` without even needing `budget_pressure()` (`budget_declined=0` on 15 of 16 seeds).
2. **Why mean margin is `€144/wk` lower (`t = -0.80`) than pure `backlog-aware-gtn-ptw40-dev`:**
   - When `backlog_multiday_weight=0.25` unblocks afternoon intake in dense hubs, our desk already captures full hub volume at full price (`€29,806.67` revenue vs `€29,021.59`). Adding `lane_dest_tilt=0.035` (`-5.25%` discount on `deliv_supply >= 100`) discounts `92.19` won hub-destination orders/wk and shifts `+2.8` orders/wk from `next_day` into `same_day` (`108.06` vs `105.25`), reducing revenue by `-€785/wk` while saving `+€703/wk` in driver fees.
   - In addition, `budget_target=0.945` triggered on only one seed (`dev-14`, `b_dec=11, b_bal=46`), where discounting 46 ballast quotes and declining 11 options cost `-€1,307.91` on that single seed (`dev-14` was already `95.35%` safe in `backlog-aware-gtn-ptw40-dev`).

## Verdict
**adopt merge (`policy.py` synthesis) / keep `backlog-aware-gtn-ptw40-dev` flags for max mean or `grand-v5-s150-dev` for max median/min** — Merging all three Wave-0246 branches into `policy.py` is clean (`+€0.00` noop) and gives **€10,337.50 mean margin (`Δmargin €+1,347.19 ± 255.33, t = 5.28, 15/16 better`, `94.2%` min on-time, `SAFE`)** in `grand-v5-s150-dev` (beating both `backlog-aware-gtn-ptw40-dev` and `v3-gated-taxback-dev` on **9/16 seeds** with **€10,323.27 median** and **€7,676.33 min**), while `grand-v5-best-dev` (`min_supply=20`) reaches **€10,263.18 (`95.1%` min on-time, €7,833.67 worst-seed margin)**.
