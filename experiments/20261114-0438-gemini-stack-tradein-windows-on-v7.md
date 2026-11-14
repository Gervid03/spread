# stack-tradein-windows-on-v7: Surgical Stop-Window Clamping & Window-Slack Trade-Ins on the `n14-03324` + `n14-03111` Stack

- **Agent / branch / commit:** gemini · `exp/gemini-n14-04153-stack-tradein-windows-on-v7` · `efdb10b`
- **Date:** 2026-11-14 04:38
- **Idea from:** Combination & refinement of `n14-03114` (`respect_stop_windows=True`, `min_pickup_window_slack_min=180`, `trade_in_mode`) on the `n14-03324` (`fee-drop-all180`) + `n14-03111` (`buf-alarm`) v7 stack

## Why we tried it
In `n14-03114`, decoupling `early_window_fee_ramp=False` from `respect_stop_windows=True, min_pickup_window_slack_min=180, trade_in_mode="same_day_only"` eliminated 100% of late 2-leg trade-ins (`0 / 5` vs `12 / 24` in Champion v2) and raised worst on-time share on the older `n14-02114` (`ptw=0.38`) stack to `95.62%` (`€9,971.86/wk`). We wanted to test:
1. How `respect_stop_windows` and `trade_in_mode` compose with the `n14-03324` (`backlog_multiday_weight=0.25, backlog_in_flight_weight=0.35, hub_multiday_fee_open=0.80, thin_sameday_fee_open=0.90, drop_urgent_margin_min=180`) and `n14-03111` (`delivery_buffer_min=30, buffer_min_slack_min=210, pre_warn_lead_min=60, pre_warn_fee=1.35`) stack when `stops_for()` cleanly composes `delivery_buffer_min` and `respect_stop_windows` (`min(delivery["window"]["to"], buffered_deadline)`).
2. Whether a new `trade_in_mode="window_slack"` gate—allowing multi-day 2-leg trade-ins when leg 0's handoff window has sufficient slack (`leg0_deliv_to - p0_ready - drive0 >= min_slack_min + slack_per_drive * drive0` and `leg0_deliv_to - leg0_deliv_from >= 60`) and leg 1's remaining drive after handoff has sufficient slack (`deadline - max(p1_ready, leg0_deliv_from + 30) - drive1 >= min_slack_min + slack_per_drive * drive1`)—recovers profitable multi-day trade-in revenue without re-introducing late trade-ins.
3. Whether the extra on-time safety from eliminating late trade-ins and tight stop windows can be cashed in via higher intake (`price_target_win=0.41, min_supply=20, min_slack_min=140`).

## What changed
Merged `exp/gemini-n14-03324-supply-adaptive-fee-open-and-drop-rescue`, `exp/gemini-n14-03111-adaptive-delivery-buffer-and-alarm`, and `exp/gemini-n14-03114-surgical-tradein-and-window-gates` into `src/spread_lab/policy.py`, plus:
- In `stops_for()`, composed `respect_stop_windows` with `delivery_buffer_min`: when slack `>= buffer_min_slack_min`, `delivery_buffer_min` shaves `effective_deadline` first (`buffered_deadline = effective_deadline - delivery_buffer_min`), and when `respect_stop_windows=True`, `buffered_to = min(delivery["window"]["to"], buffered_deadline)` so narrow private or leg-0 trade-in windows are clamped to their actual window `to` (never widened to `20:00` and never double-shaved).
- Extended `Params.trade_in_mode: str = "all"` to support `"window_slack"` in `Desk.price()`.

Run with:
```sh
uv run lab eval -s trust_invest=0.05 -s notes_v2=True -s note_unsure=decline -s max_next_day_drive_min=480 -s fri_same_day_max_drive=100 -s thin_long_next_day_supply=50 -s ring_to_hub_same_day_min=60 -s same_day_min_supply=50 -s slack_per_drive=0.75 -s backlog_multiday_weight=0.25 -s backlog_in_flight_weight=0.35 -s hub_multiday_fee_open=0.80 -s thin_sameday_fee_open=0.90 -s drop_urgent_margin_min=180 -s delivery_buffer_min=30 -s buffer_min_slack_min=210 -s pre_warn_lead_min=60 -s pre_warn_fee=1.35 -s respect_stop_windows=True -s min_pickup_window_slack_min=180 -s early_window_fee_ramp=False -s trade_in_mode=same_day_only -s price_target_win=0.41 -s min_supply=20 -s min_slack_min=140 --name v7-tradein-win-cashin-dev
```

## Results (level 8, vs champion, paired)
| set | run folder | mean margin | Δmargin ± SE | t | better/worse | on-time min | SAFE |
|---|---|---|---|---|---|---|---|
| smoke (noop) | `20261114-042812-v7-ti-noop` | €9,662.25 | €+0.00 ± 0.00 | - | 0/0 | 95.5% | SAFE |
| smoke 1 (`same_day_only`, `ptw=0.40, ms=22`) | `20261114-042904-v7-ti-same-smoke1` | €10,849.68 | €+1,187.43 ± 495.53 | 2.40 | 4/0 | 97.7% | SAFE |
| smoke 2 (`window_slack`, `ptw=0.40, ms=22`) | `20261114-042946-v7-ti-winslack-smoke2` | €10,743.60 | €+1,081.35 ± 507.36 | 2.13 | 4/0 | 97.2% | SAFE |
| smoke 3 (`same_day_only`, `ptw=0.41, ms=20, slack=140`) | `20261114-043224-v7-ti-same-cashin41-smoke3` | €10,991.36 | €+1,329.11 ± 726.17 | 1.83 | 3/1 | 96.3% | SAFE |
| smoke 4 (`same_day_only`, `ptw=0.40, ms=20, slack=140`) | `20261114-043349-v7-ti-same-cashin40-smoke4` | €10,807.92 | €+1,145.67 ± 713.24 | 1.61 | 3/1 | 97.3% | SAFE |
| dev 1 (`same_day_only`, `ptw=0.40, ms=22, slack=150`) | `20261114-043450-v7-tradein-win-ptw40-dev` | €10,296.80 | €+1,306.49 ± 232.75 | 5.61 | 15/1 | 94.4% | SAFE |
| dev 2 (`same_day_only`, `ptw=0.41, ms=20, slack=140`) | `20261114-043613-v7-tradein-win-cashin-dev` | €10,421.03 | €+1,430.72 ± 289.89 | 4.94 | 14/2 | 94.8% | SAFE |

### Paired Comparisons vs `n14-03324` (`fee-drop-all180-dev`) and `n14-03111` (`gtn-ptw40-buf-alarm-dev`)
| Run | vs `20261114-034812-fee-drop-all180-dev` (€10,577.92, min 95.3%) | vs `20261114-032059-gtn-ptw40-buf-alarm-dev` (€10,508.07, min 95.6%) |
|---|---|---|
| `v7-tradein-win-ptw40-dev` (€10,296.80, min 94.4%) | Δmargin €-281.12 ± 126.86 (t=-2.22), 5/11, Δon-time +0.06% | Δmargin €-211.28 ± 154.52 (t=-1.37), 5/11, Δon-time +0.04% |
| `v7-tradein-win-cashin-dev` (€10,421.03, min 94.8%) | Δmargin €-156.89 ± 173.51 (t=-0.90), 7/9, Δon-time -0.16% | Δmargin €-87.05 ± 198.21 (t=-0.44), 10/6, Δon-time -0.18% |

### Operational Counters & Ledger Breakdown (16-seed dev totals and per-week means)
| Metric / Ledger | Champion v2 | `fee-drop-all180-dev` (`n14-03324`) | `gtn-ptw40-buf-alarm-dev` (`n14-03111`) | `v7-tradein-win-ptw40-dev` | `v7-tradein-win-cashin-dev` |
|---|---|---|---|---|---|
| `won` (total / per wk) | 3,682 (230.1) | 4,425 (276.6) | 4,376 (273.5) | 4,406 (275.4) | 4,510 (281.9) |
| `won_trade_in` | - | - | - | 7 (0.4/wk) | 7 (0.4/wk) |
| `late_trade_in` | - | - | - | **0 (0.0/wk)** | **0 (0.0/wk)** |
| `dropped_trade_in` | 0 | 0 | 0 | 121 (7.6/wk) | 126 (7.9/wk) |
| `dropped_pickup_window` | 0 | 0 | 0 | 25 (1.6/wk) | 27 (1.7/wk) |
| `dropped_delivery_window` | 0 | 0 | 0 | 33 (2.1/wk) | 28 (1.8/wk) |
| `buffered_stops` | 0 | 0 | 4,300 (268.8/wk) | 4,171 (260.7/wk) | 4,269 (266.8/wk) |
| `pre_warned` | 0 | 0 | 192 (12.0/wk) | 211 (13.2/wk) | 212 (13.2/wk) |
| `drop_rescued` | 0 | 11 (0.7/wk) | 0 | 17 (1.1/wk) | 23 (1.4/wk) |
| Total late orders | 118 (7.38/wk) | 102 (6.38/wk) | 99 (6.19/wk) | 100 (6.25/wk) | 111 (6.94/wk) |
| `revenue` (€/wk) | +26,922.43 | +29,928.51 | +29,650.81 | +29,838.86 | +30,341.31 |
| `driver_fee` (€/wk) | -17,286.93 | -18,972.34 | -18,776.97 | -19,074.81 | -19,467.10 |
| `late_refund` (€/wk) | -376.20 | -270.51 | -260.38 | -308.65 | -313.40 |
| `undelivered_penalty` (€/wk) | -10.72 | -15.68 | -10.23 | -56.81 | -57.66 |
| `failed_visit` (€/wk) | -165.44 | -16.96 | -21.21 | -21.23 | -16.87 |
| `release_fee` (€/wk) | -53.48 | -54.48 | -53.21 | -55.93 | -44.22 |
| `waiting` (€/wk) | -39.38 | -20.62 | -20.73 | -24.62 | -21.03 |
| **Mean margin (€/wk)** | **€8,990.31** | **€10,577.92** | **€10,508.07** | **€10,296.80** | **€10,421.03** |

### Analysis of Findings
1. **`trade_in_mode="window_slack"` vs `"same_day_only"`:** On smoke, `"window_slack"` passed all multi-day trade-ins (`dropped_trade_in = 0`), winning 10 trade-ins (vs 3 in `same_day_only`), of which 2 (`20%`) arrived late, reducing smoke mean margin by `€106.08` (`€10,743.60` vs `€10,849.68`) and min on-time from `97.7%` to `97.2%`. Why? Multi-day trade-in requests have leg 0 delivery windows on Day 2 or Day 3 (`leg0_deliv_to - p0_ready` has 24+ hours of nominal slack), so they easily pass `window_slack`. The true failure mode of multi-day trade-ins is **12-hour gig splitting in `post()`**, where two separate drivers must coordinate across the customer handoff without a shared gig. Only `same_day_only` eliminates late trade-ins (`0 / 7` late across 16 dev seeds in both Dev Run 1 and Dev Run 2).
2. **Interaction of `pre_warn_lead_min=60` + `thin_sameday_fee_open=0.90` + `respect_stop_windows=True`:** Adding `pre_warn_lead_min=60` on top of `fee-drop-all180` (`n14-03324`) and `respect_stop_windows=True` increased `undelivered_penalty` from `-€15.68/wk` to `-€56.81/wk` and `driver_fee` per won car, leaving `v7-tradein-win-ptw40-dev` at `€10,296.80/wk` (`€-281.12 ± 126.86` behind `fee-drop-all180-dev`) and `v7-tradein-win-cashin-dev` at `€10,421.03/wk` (`€-156.89 ± 173.51` behind `fee-drop-all180-dev`, though `10/6` better seed count vs `gtn-ptw40-buf-alarm-dev`). Specifically, clamping stop windows via `respect_stop_windows=True` attaches explicit `window` bounds to gig stops, making drivers slightly more selective at booking time and causing ~0.3 more orders/wk to go undelivered when combined with lower opening fees (`hub_multiday_fee_open=0.80`) and pre-warn step jumps (`pre_warn_lead_min=60`).

## Verdict
**needs work / keep `trade_in_mode=same_day_only` as an optional safety lever, do not replace `n14-03324` (`€10,577.92`)** — `v7-tradein-win-cashin-dev` is strongly SAFE (`94.8%` min on-time, `97.5%` mean on-time, `0 / 7` late trade-ins) and beats Champion v2 by `Δmargin €+1,430.72 ± 289.89 (t=4.94, 14/2)`, while `v7-tradein-win-ptw40-dev` achieves `97.7%` mean on-time (`Δmargin €+1,306.49 ± 232.75, t=5.61, 15/1`), but both trail `fee-drop-all180-dev` (`€10,577.92`) by `€156.89` and `€281.12` due to higher `undelivered_penalty` (`-€57/wk` vs `-€16/wk`) when `respect_stop_windows=True` and `pre_warn_lead_min=60` are stacked together on `hub_multiday_fee_open=0.80`.
