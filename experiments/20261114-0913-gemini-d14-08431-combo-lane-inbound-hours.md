# d14-08431-combo-lane-inbound-hours: Floor-unblocked inbound lane pricing stacked with opening-hours slack

- **Agent / branch / commit:** gemini · `exp/gemini-d14-08431-combo-lane-inbound-hours` · `61982de` (built on `1a2075b`, Champion v3T)
- **Date:** 2026-11-14 09:13
- **Idea from:** `experiments/IDEAS.md` #17 ("Slack by opening hours") + #28 / R8 ("A learned lane table for the price"), combining `exp/gemini-d14-02-acceptance-model` and `exp/gemini-n14-06261-hours-on-v3`

## Why we tried it
Two complementary near-miss / safety branches on v3 / v3T each solved half of the same dispatch bottleneck:
1. **Asymmetric slope-compensated inbound lane pricing (`d14-02`):** At level 8, the competitor discounts inbound-to-Capital/Ring lanes (`eff = pk_eff + dl_eff < 0`, where abundant drivers live near the destination and work awaits there) and marks up outbound lanes (`eff > 0`). One-sided inbound discounting (`lane_prior_only_neg=True`) with online-tracker slope compensation (`lane_prior_comp_slope > 0`) gained `+€252.70 ± 142.89` (`t = 1.77`) on `dev`, winning `+€475/w` on `dev-01..08` (`~205` floored quotes/w) but stalling at `+€30/w` on `dev-09..16` (`~271` floored quotes/w, up to `341` on `dev-12`). Why? In lower-price worlds, `normal_floor = referenceFeeCents * 1.25 / (1 - 0.08) = 1.3587 * referenceFeeCents` clamped discounted slow inbound quotes back up and flipped `decision` to `"floor"`, even though `R15` (`c14-census-then-return-offer`) showed near-home / inbound gigs book near `0.85×–0.92×` `referenceFeeCents`. Lowering the floor's expected fee multiple on non-`same_day` inbound quotes (`lane_inbound_fee_mult = 1.05`, giving `floor = 1.1413 * referenceFeeCents`) unblocks these quotes in low-price worlds while keeping ~18–22% real gross margin.
2. **Exact stated-opening-hours slack (`n14-06261`):** Measuring `last_pickup` and `earliest_open_at` against stated dealer opening hours and private-seller windows (`slack_by_hours=True, min_slack_min=120`) matched `order["lastPickupAt"]` to the minute and cut `deadline_close` warnings by `-29%` (`+€7.56 ± 113.42` standalone on v3). Dropping hidden-tight 18:00/19:00-closing pickup traps frees driver capacity to absorb the `+20–25/w` extra inbound cars without congesting tight-roster weeks (`dev-07`, `dev-14`), reinforced by gating `lane_mult` on `projected_on_time() >= lane_min_proj` (`0.945`).

## What changed
In `src/spread_lab/policy.py` (all defaults neutral, `promote.sh`-compatible with inlined 30-place `LANE_PICKUP`, `LANE_DELIVERY`, and `LANE_TERCILES = (-0.03752, 0.04481)` fitted strictly on `night-01..32 + final-01..32`, zero overlap with `dev` or `holdout`):
- **Inbound lane pricing & floor unblock:**
  - `lane_prior_weight: float = 0.0` — tilts `listPriceCents` by `clamp(exp(w * (pk_eff + dl_eff)), 0.85, 1.15)`.
  - `lane_prior_only_neg: bool = False` — applies `lane_prior_weight` only when `pk_eff + dl_eff < 0` (inbound discount only; keeps `high` outbound margin intact).
  - `lane_prior_comp_slope: float = 0.0` — shifts `Desk.learn()`'s target win rate by `clamp(price_target_win - slope * log(quoted_lane_mult), 0.05, 0.90)` so higher inbound win rates do not push `self.mult` up.
  - `lane_inbound_fee_mult: float = 0.0` — when `> 0`, `lm < 1.0`, and `option["kind"] != "same_day"`, computes that option's margin floor with `referenceFeeCents * lane_inbound_fee_mult / (1 - min_margin_frac)` instead of `expected_fee_mult` (`1.25`).
  - `lane_min_proj: float = 0.0` — when `> 0` and `projected_on_time() < lane_min_proj`, forces `lane_mult = 1.0`.
  - Stores `self.quoted_lane_mult[request_id]` at quote time and normalizes `Desk.rejoin()`'s 30-order `ratios` by `raw_lane_mult` when `lane_prior_weight != 0` and `lane_min_proj` allows.
- **Opening-hours slack (`slack_by_hours: bool = False`):**
  - Adds `open_at`, `earliest_open_at`, and `last_pickup_for` and uses them in `Desk.price` for the slack gate (`last_pickup - eff_ready >= min_slack_min + slack_per_drive * drive`) and multi-day long-drive rules.
- **Telemetry (`desk.stats`):** `lane_quotes_{low,mid,high}`, `lane_wins_{low,mid,high}`, `lane_late_{low,mid,high}`, `lane_margin_{low,mid,high}_cents`, `lane_floor_unblocked`, `lane_floor_lowered`, `lane_proj_gated`, `dropped_hours`, `lastpickup_n`, `lastpickup_err`.

*(Instrument note: `baselines/fast14-dev` was recorded before Champion v3T's `late_fee_open=1.0` promotion and with unmerged `busy_start_min`/`busy_end_min` params not on `main`, so the 4-arm 8-seed screen was run on `dev-01..08` directly against Champion v3T's stored results, ~20–55s/run.)*

### Best candidate flags (`combo-stack-dev`)
```text
-s slack_by_hours=True -s min_slack_min=120 -s lane_prior_weight=0.70 -s lane_prior_only_neg=True -s lane_prior_comp_slope=1.6 -s lane_inbound_fee_mult=1.05 -s lane_min_proj=0.945
```

## Numbers (paired with Champion v3T, worst world reported first)

| Run folder | Seeds | Worst on-time (`<92%` / `<91%`) | Min margin | Mean margin | Δmargin ± SE (`t`, W/L) | Mean on-time (Δ) | Won | SAFE? |
|---|---:|---|---:|---:|---|---:|---:|---|
| `champion` (v3T baseline) | dev (16) | **94.33%** `dev-13` (0 / 0) | €7,487.67 `dev-01` | €10,884.88 | — | 96.96% | 285.4 | SAFE |
| `20261114-085540-combo-lane-hours-noop` | smoke (4) | **94.38%** `dev-01` (0 / 0) | €7,487.67 `dev-01` | €10,816.98 | **+€0.00 ± 0.00** (0/0) | 95.98% (+0.00%) | 283.2 | SAFE |
| `20261114-085623-combo-s1-hours-dev8` (`hours, slack=120`) | dev-01..08 (8) | **94.65%** `dev-01` (0 / 0) | €7,495.84 `dev-01` | €11,062.77 | −€57.28 ± 185.92 (`t = -0.31`, 4/4) | 97.08% (+0.43%) | 279.6 | SAFE |
| `20261114-085733-combo-s2-lane-dev8` (`w=0.70, c=1.6, f=1.05, p=0.945`) | dev-01..08 (8) | **94.07%** `dev-07` (0 / 0) | €7,919.07 `dev-05` | €11,505.65 | +€385.60 ± 322.96 (`t = +1.19`, 5/3) | 96.71% (+0.07%) | 318.9 | SAFE |
| `20261114-085809-combo-s3-stack-dev8` (`s1 + s2`) | dev-01..08 (8) | **95.31%** `dev-02` (0 / 0) | €8,332.23 `dev-05` | €11,444.92 | **+€324.87 ± 165.71** (`t = +1.96`, 6/2) | 96.75% (+0.11%) | 304.6 | **SAFE** |
| `20261114-090323-combo-s4-tuned-dev8` (`w=0.80, c=1.85, f=1.00 + s1`) | dev-01..08 (8) | **93.91%** `dev-07` (0 / 0) | €7,451.17 `dev-01` | €11,233.81 | +€113.75 ± 190.32 (`t = +0.60`, 3/5) | 96.65% (+0.01%) | 315.9 | SAFE |
| **`20261114-090524-combo-stack-dev`** (**full stack**) | **dev (16)** | **95.31%** `dev-02` (**0 / 0**) | **€8,332.23** `dev-05` | **€11,203.91** | **+€319.02 ± 126.40 (`t = +2.52`, 11/5)** | **97.20% (+0.24%)** | **297.0** | **SAFE** |
| `20261114-090708-combo-lane-only-dev` (`s2` ablation, no hours) | dev (16) | **93.57%** `dev-14` (0 / 0) | €7,919.07 `dev-05` | €11,177.53 | +€292.65 ± 192.42 (`t = +1.52`, 10/6) | 96.89% (−0.07%) | 307.6 | SAFE |
| `fc-v3T-night32` (v3T baseline) | night (32) | **90.57%** `night-15` (2 / 1) | €5,534.80 `night-20` | €11,341.67 | — | 97.27% | 297.9 | NOT SAFE |
| **`20261114-090837-combo-stack-night32`** (**full stack**) | **night (32)** | **91.27%** `night-15` (**1 / 0**) | **€5,470.19** `night-20` | **€11,600.09** | **+€258.42 ± 100.53 (`t = +2.57`, 19/13)** | **97.33% (+0.06%)** | **321.9** | 32/32 ranked |

- **Mid-week restart check (`uv run lab play --seed dev-01 <flags> --restart-at 3600`):** Rejoined 143 orders and 57 live gigs at minute 3608 with `mult = 1.654` (vs `1.643` pre-restart), finishing at **€8,254.11, 96.6% on time, `ranked=True`**.

### Mechanism & ledger breakdown (16-seed `dev` means)
1. **`lane_inbound_fee_mult=1.05` unblocks the low-world-price floor (`dev-09..16`):** Across the 16 `dev` seeds, `quote_floor` drops from `237.9` (v3T) to `170.5` (`combo-stack-dev`), with `lane_floor_unblocked = 80.12` options/world completely clearing the floor (`126` on `dev-12` → `+€1,025.35`; `120` on `dev-09` → `+€587.36`). Unlike `d14-02` (`+€475/w` on `dev-01..08`, `+€30/w` on `dev-09..16`), `combo-stack-dev` gains **`+€324.87/w` on `dev-01..08` and `+€313.18/w` on `dev-09..16`** (100% out-of-sample for the lane table).
2. **Synergy between inbound volume and opening-hours slack:**
   - Nudged inbound lane pricing alone (`combo-lane-only-dev`) lifts `won` from `285.4` to `307.6/w` (`+€292.65 ± 192.42`, `t = 1.52`), but without hours-aware slack it accepts hidden-tight 18:00/19:00-closing pickups that congest `dev-07` (`−€983.00`, `94.07%` OT) and `dev-14` (`−€682.18`, `93.57%` OT), raising `deadline_close` warnings (`18.31 → 21.81`) and `undelivered_penalty` (`−€57.71 → −€88.53`).
   - Stacking `slack_by_hours=True, min_slack_min=120` (`combo-stack-dev`) drops `43.75` hidden-tight options/world (`dropped_hours`), turning `dev-07` positive (`+€52.45`, `95.64%` OT) and `dev-14` positive (`+€117.61`, `96.82%` OT). Despite winning **`+11.6` more orders/world** than Champion v3T (`285.4 → 297.0`, driven by `low` inbound wins rising `~71 → 90.8/w` at `€2,408.78` margin vs `high` outbound margin preserved at `€6,278.42`), **total `driver_fee` is €13.21 lower than v3T (`−€19,060.32` vs `−€19,073.53`, `driver_fee / revenue` `62.59% → 61.99%`)**, `deadline_close` drops `18.31 → 16.00` (`−12.6%`), `gig_expired` drops `8.94 → 7.62` (`−14.8%`), `undelivered_penalty` drops `−€57.71 → −€27.11` (`−53%`), worst `dev` on-time rises **`94.33% → 95.31%` (all 16 seeds `> 95.3%`)**, and worst `dev` margin rises **`€7,487.67 → €8,332.23` (`+€844.56`)**.
   - Pushing further to `w=0.80, comp_slope=1.85, lane_inbound_fee_mult=1.00` (`s4`) added `+8.4` more `low` wins (`95.4 → 103.8`) at `-€1.95` lower margin/win (`€25.44 → €23.49`), hitting the Lerner margin plateau (`€2,427 → €2,437`) while adding fleet load (`+€113.75 ± 190.32`).
3. **32-world `night` tail check (`combo-stack-night32`):** *(Note: `night-01..32` was half of the 64-world empirical-Bayes lane fit set, whereas `dev` and `holdout` are strictly out-of-sample.)* Across all 32 `night` worlds, `combo-stack` achieves `32/32` ranked, **`+€258.42 ± 100.53` (`t = +2.57`, 19W/13L)**, `+0.06%` mean on-time (`97.33%`), **0/32 worlds under 91%** (vs 1/32 for Champion v3T), and **1/32 under 92%** (vs 2/32 for Champion v3T: `night-15` improved `90.57% → 91.27%`, `night-11` improved `91.53% → 94.22%` and `+€306.64`, and 31/32 worlds are `≥ 93.46%`).

## Verdict
**adopt (ready for `scripts/promote.sh` holdout gate)** — Stacking floor-unblocked asymmetric inbound lane pricing (`lane_prior_weight=0.70, lane_prior_only_neg=True, lane_prior_comp_slope=1.6, lane_inbound_fee_mult=1.05, lane_min_proj=0.945`) with opening-hours slack (`slack_by_hours=True, min_slack_min=120`) clears `t >= 2.0` cleanly on 100% out-of-sample `dev` (**`+€319.02 ± 126.40`, `t = +2.52`, 11W/5L, SAFE**) while simultaneously raising mean on-time (`+0.24%` to `97.20%`), lifting worst `dev` on-time from `94.33%` to **`95.31%`** (`0/16` under `95%`), lifting worst `dev` margin by **`+€844.56`**, and improving Champion v3T's 32-world `night` tail from `90.57%` (`2` under `92%`) to **`91.27%`** (`0` under `91%`, `1` under `92%`, `+€258.42 ± 100.53`, `t = +2.57`).
