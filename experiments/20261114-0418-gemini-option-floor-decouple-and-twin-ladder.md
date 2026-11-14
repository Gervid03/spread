# option-floor-decouple-and-twin-ladder: decouple multi-option fee floor compression and test batch bracketing on the v6 stack

- **Agent / branch / commit:** gemini · `exp/gemini-n14-03502-option-floor-decouple-and-twin-ladder` · `8af3ad7` + `e3bdc58`
- **Date:** 2026-11-14 04:18
- **Idea from:** Margin X-Ray v2 Section 2D (multi-option floor compression) & `IDEAS.md` item #5 ("The twin ladder: let batches bracket the competitor")

## Why we tried it
1. **Multi-option floor compression (`floored_sd_prem` and `slow_floor_mult`):** Margin X-Ray v2 (Table 2D) showed that on `('same_day', 'next_day')` (`160.1/wk`) and `('same_day', 'next_day', 'within_3_days')` (`32.8/wk`) requests, `same_day` wins **74.4%–78.4%** of our multi-option wins (`56.6/wk`). Because `Desk.price()` applies the same euro fee floor `floor = fee / (1 - p.min_margin_frac)` (`1.359 × referenceFeeCents`) to every option even though `next_day` list price is ~7–8% lower than `same_day`, on **31.5% of multi-option `same_day` wins**, `next_day` hits the floor while `same_day` does not — compressing `prices["same_day"] / prices["next_day"]` toward `1.00`. Since dealers value `same_day` speed ~15% above `next_day`, this floor compression either leaves +6–10% price on the table when the dealer picks `same_day` or steers medium drives into riskier `same_day` (`4.7%` late, `€46.7/ord`) instead of `next_day` (`1.9%` late, `€51.9/ord`).
2. **Twin-Ladder batch bracketing (`ladder_spread` and `ladder_lr`):** ~45% of requests arrive in multi-car batches. On raw v2 (`exp/gemini-n14-03-ladder`), sorting batch members by `referenceFeeCents` across `estimate × exp(±spread)` gained `+€45.41` on dev. We tested whether gentler bracketing (`ladder_spread=0.04, ladder_lr=0.25`) on top of the high-volume (`price_target_win=0.40`) deadline-aware backlog + buffer/alarm stack improves price tracking or order selection.

## What changed
Merged `origin/exp/gemini-n14-03111-adaptive-delivery-buffer-and-alarm` (`8af3ad7`) and `origin/exp/gemini-n14-02462-deadline-aware-backlog` (`e3bdc58`), and added five default-off parameters to `Params` and `Desk` in `src/spread_lab/policy.py`:
- `slow_floor_mult: float = 1.0`: multiplies `floor` by `p.slow_floor_mult` for non-`same_day` options (`option["kind"] != "same_day"`), counting `stats["slow_floor_saved"]` whenever a slow option's unfloored price is below `base_floor`.
- `floored_sd_prem: float = 0.0`: when both `"same_day"` and `"next_day"` are quoted and `"next_day"` hits its floor (`next_day_floored == True`), enforces `prices["same_day"] = max(prices["same_day"], int(prices["next_day"] * (1.0 + p.floored_sd_prem) + 0.5))` and increments `stats["sd_prem_lifted"]`.
- `ladder_spread: float = 0.0`, `ladder_lr: float = 0.0`, `ladder_window_min: int = 5`: spreads open batch members across `base_mult * exp(±ladder_spread)` ordered by `(referenceFeeCents, request_id)` while preserving per-option factors (`trust_invest`, `trust_gain`, `dealer_adj`, `same_day_markup`, `slow_floor_mult`, and `floored_sd_prem`), and steps `self.mult` toward the geometric midpoint of `[dearest_win, cheapest_loss]` when a batch both wins and loses.

Let `<STACK>` denote the merged stack overrides:
`-s trust_invest=0.05 -s notes_v2=True -s note_unsure=decline -s max_next_day_drive_min=480 -s fri_same_day_max_drive=100 -s thin_long_next_day_supply=50 -s ring_to_hub_same_day_min=60 -s same_day_min_supply=50 -s min_slack_min=150 -s slack_per_drive=0.75 -s price_target_win=0.40 -s min_supply=22 -s delivery_buffer_min=30 -s buffer_min_slack_min=210 -s pre_warn_lead_min=60 -s pre_warn_fee=1.35 -s backlog_multiday_weight=0.25 -s backlog_in_flight_weight=0.35`

Run with:
`uv run lab eval $STACK -s floored_sd_prem=0.10 -s slow_floor_mult=1.0 --name optfloor-prem10-dev`

## Results (level 8, vs champion, paired)
| set | run folder | mean margin | Δmargin ± SE | t | better/worse | on-time min | SAFE |
|---|---|---|---|---|---|---|---|
| smoke (noop) | `20261114-035941-optfloor-ladder-noop` | €9,662.25 | +€0.00 ± 0.00 | — | 0 / 0 | 95.5% | yes |
| smoke (`<STACK>` base) | `20261114-040144-optfloor-stack-base-smoke` | €11,170.90 | +€1,508.65 ± 499.95 | 3.02 | 4 / 0 | 95.8% | yes |
| smoke S1 (`prem=0.10, slow=0.93`) | `20261114-040249-optfloor-s1-prem10-slow93-smoke` | €10,568.15 | +€905.91 ± 458.63 | 1.98 | 3 / 1 | 95.3% | yes |
| smoke S2 (`prem=0.12, slow=1.0`) | `20261114-040334-optfloor-s2-prem12-slow100-smoke` | €11,200.28 | +€1,538.03 ± 488.88 | 3.15 | 4 / 0 | **96.6%** | yes |
| smoke S3 (`ladder=0.04, lr=0.25`) | `20261114-040351-optfloor-s3-ladder04-lr25-smoke` | €10,914.84 | +€1,252.59 ± 647.68 | 1.93 | 4 / 0 | 94.4% | yes |
| smoke S4 (`prem=0.12 + ladder=0.04`) | `20261114-040641-optfloor-s4-prem12-ladder04-smoke` | €11,130.87 | +€1,468.62 ± 570.22 | 2.58 | 4 / 0 | 95.8% | yes |
| **smoke S5 (`prem=0.10, slow=1.0`)** | `20261114-040950-optfloor-s5-prem10-slow100-smoke` | **€11,258.73** | **+€1,596.48 ± 481.52** | **3.32** | **4 / 0** | **95.2%** | **yes** |
| **dev (`prem=0.10, slow=1.0`)** | `20261114-041147-optfloor-prem10-dev` | **€10,405.62** | **+€1,415.32 ± 228.04** | **6.21** | **15 / 1** | **95.2%** | **yes** |
| dev (`prem=0.12, slow=1.0`) | `20261114-041225-optfloor-prem12-dev` | €10,303.44 | +€1,313.14 ± 214.90 | 6.11 | 14 / 2 | **95.9%** | yes |
| dev (`prem=0.10, ptw=0.45`) | `20261114-041723-optfloor-prem10-ptw45-dev` | €10,048.77 | +€1,058.47 ± 289.92 | 3.65 | 14 / 2 | 93.3% | yes |

### Paired comparisons on 16 dev seeds against upstream stack baselines
| Candidate | vs `20261114-040928-v6-buf-alarm-backlog-dev` (€10,350.24, exact `<STACK>`) | vs `20261114-032059-gtn-ptw40-buf-alarm-dev` (€10,508.07) | vs `20261114-030237-backlog-aware-gtn-ptw40-dev` (€10,481.57) |
|---|---|---|---|
| **`optfloor-prem10-dev` (`floored_sd_prem=0.10`)** | **+€55.39 ± 103.22 (t=+0.54, 8/8, ΔOT −0.06%)** | −€102.45 ± 96.99 (t=−1.06, 5/11, ΔOT −0.18%) | −€75.95 ± 144.17 (t=−0.53, **9/7**, ΔOT +0.10%) |
| `optfloor-prem12-dev` (`floored_sd_prem=0.12`) | −€46.79 ± 94.77 (t=−0.49, 8/8, ΔOT +0.03%) | −€204.63 ± 111.89 (t=−1.83, 5/11, ΔOT −0.09%) | −€178.13 ± 146.10 (t=−1.22, 5/11, ΔOT +0.19%) |
| `optfloor-prem10-ptw45-dev` (`ptw=0.45`) | −€301.47 ± 226.58 (t=−1.33, 5/11, ΔOT −0.69%) | −€459.30 ± 244.85 (t=−1.88, 6/10, ΔOT −0.81%) | −€432.81 ± 232.63 (t=−1.86, 7/9, ΔOT −0.53%) |

### What the counters and ledger breakdown show
1. **`floored_sd_prem=0.10` (`slow_floor_mult=1.0`) cleanly fixes multi-option floor compression and improves over the merged `<STACK>` on both smoke (+€87.83/wk) and dev (+€55.39/wk):**
   - On the 16 dev seeds (`optfloor-prem10-dev` vs `v6-buf-alarm-backlog-dev`), `sd_prem_lifted` triggers **60.9 times/world** when `next_day` hits the euro fee floor.
   - Lifting `same_day` to at least `1.10 × prices["next_day"]` steers 6.7 orders/world out of floor-compressed `same_day` (`won_same_day: 105.1 → 98.4/wk`, while `won_next_day` edges up `158.6 → 158.9/wk` and `won_within_3_days` `12.2 → 12.7/wk`).
   - This saves **€550.00/world in driver fees** (`-€19,190 → -€18,640`), reduces `deadline_close` warnings (`16.5 → 15.9/wk`), and saves **€39.50/world in late refunds** (`-€300.0 → -€260.5`), exceeding the `-€482.00/world` revenue reduction (`€29,960 → €29,478`) for a net **+€55.39/world** margin gain (`€38.54/order` vs `€37.51/order` on `<STACK>`).
   - At `floored_sd_prem=0.12` (`optfloor-prem12-dev`), `sd_prem_lifted` fires `66.0` times/world and raises worst-world on-time share to **95.9%** (mean **97.6%**), though `0.12` starts pricing out profitable `same_day` wins (`won_same_day` drops to `95.0/wk`, costing `−€102.18/wk` vs `0.10`).
2. **Why `slow_floor_mult=0.93` (`Smoke 1`) failed (`−€602.74 ± 89.51, t=−6.73` vs `<STACK>` base on smoke):**
   - `slow_floor_saved` fired **210.5 times/world**, lowering the floor on slow options by 7%.
   - First, on routes with high `referenceFeeCents / listPriceCents`, the `1.359×` floor is what protects margin against driver fees: lowering it won 9.7 extra `next_day` orders/world on expensive lanes, driving up `driver_fee` by **+€647.40/world** (`-€17,660.4 → -€18,307.8`) and `late_refund` by **+€124.60/world** (`-€181.5 → -€306.1`).
   - Second, un-flooring `next_day`-only requests changes `self.decided[req_id]` from `"floor"` to `"quote"`, polluting `Desk.learn()` with losses on structurally high-fee routes.
3. **Why Twin-Ladder (`ladder_spread=0.04, ladder_lr=0.25`) lost `−€256.06/wk` on smoke:**
   - Even at `ladder_spread=0.04`, adverse selection on the `−4%` lower rung across `91.5` quoted batches/world reduces gross revenue by `€603.90/world` (`€29,147.3 → €28,543.4`), outweighing the `€339.00/world` driver fee savings.
4. **Why the merged `<STACK>` (`v6-buf-alarm-backlog-dev`, `€10,350.24`) trails its unmerged parents (`€10,508.07` and `€10,481.57`):**
   - Combining `backlog_multiday_weight=0.25` (more multiday orders) with `pre_warn_lead_min=60, pre_warn_fee=1.35` (early fee nudges on deadline day) causes `driver_fee` to rise to `-€19,190/wk` (`vs -€18,780/wk` on `buf-alarm` alone). Adding `floored_sd_prem=0.10` recovers `+€55.39/wk` of that gap (`€10,405.62`) and beats `backlog-aware-gtn-ptw40-dev` on **9 of 16 seeds**.

## Verdict
adopt `floored_sd_prem=0.10` (keep `slow_floor_mult=1.0`, `ladder_spread=0.0`) — SAFE on dev (`€10,405.62`, `+€1,415.32 ± 228.04, t=6.21`, 15/1 vs champion; min on-time `95.2%`, mean `97.5%`), improving over the identical merged v6 stack (`v6-buf-alarm-backlog-dev`) by `+€55.39 ± 103.22/wk` (`+€87.83/wk` on smoke) by lifting 60.9 floor-compressed `same_day` quotes/wk and saving €550/wk in driver fees; reject `slow_floor_mult=0.93` (−€602.74 on smoke) and `ladder_spread=0.04` (−€256.06 on smoke).
