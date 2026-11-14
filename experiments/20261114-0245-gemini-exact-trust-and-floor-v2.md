# exact-trust-and-floor-v2: Test explicit dealer trust gain, slower per-dealer learning (`dealer_lr=0.01`), and quote floor unblinding (`floor_all_only`, `expected_fee_mult`) on top of the `trust+notes+slack` stack

- **Agent / branch / commit:** gemini · exp/gemini-n14-02241-exact-trust-and-floor-v2
- **Date:** 2026-11-14 02:45
- **Idea from:** Margin X-Ray Leak #1 (`experiments/20261114-0200-gemini-research-margin-xray.md`, Section 2A) on top of `origin/exp/gemini-n14-01394-stack-trust-notes-slack`

## Why we tried it
Bracketing all 10,763 quotes across the 16 revealed champion v2 dev worlds in `n14-01392-margin-xray-v2` identified two potential leaks in `Desk.price()` and `Desk.learn()`:
1. **Per-dealer learning (`dealer_lr`) and explicit trust (`trust_gain`):** `D01` accounts for 31% of all quotes and 37% of all wins, accumulating up to +25% on-time trust by Wednesday/Thursday while `3_Others` (46% of quotes) stays at 0–1 trust. We tested whether slowing per-dealer step noise (`dealer_lr=0.01` vs `0.02`, which alone gave `+€154.70` in sweep `22 n-lr-fine`) and/or adding explicit `trust_gain` (`0.20`, `0.40`) on top of `n14-01394` (`trust_invest=0.05, notes_v2=True, note_unsure="decline", min_slack_min=140, slack_per_drive=0.75`) improves pricing stability and margin.
2. **Quote floor (`expected_fee_mult = 1.25`) and `floor_all_only`:** With `expected_fee_mult = 1.25` and `min_margin_frac = 0.08`, the quote floor (`1.359 × referenceFeeCents`) triggers on ~30% of quotes (`198.5/wk`), marking the whole request as `"floor"` and skipping `Desk.learn()` even when only a slower option (`within_3_days`) hit the floor while `same_day`/`next_day` were unfloored. We tested `floor_all_only=True` (only marking a quote as `"floor"` when every quoted option hits the floor) and lowering `expected_fee_mult` (`1.10`, `1.06`).

## What changed
Merged `origin/exp/gemini-n14-01394-stack-trust-notes-slack` and updated `src/spread_lab/policy.py`:
- Added `floor_all_only: bool = False` to `Params` (default `False` reproduces champion v2 and `n14-01394` identically: `Δmargin €+0.00 ± 0.00` on smoke).
- In `Desk.price()`, tracked both `any_floored` and `all_floored` across quoted options; when `p.floor_all_only` is `True`, returned `"floor"` only if `all_floored` is `True` and incremented `self.stats["quote_unblinded"]` when `any_floored and not all_floored`.
- Added `self.stats[f"price_ratio_d{day}_pct"]` in `Desk.quote()` to report daily mean quoted price ÷ list price in percent (`d0..d4`).

Run with:
- Conservative stack (`exact-trust-dlr01-dev`):
  `uv run lab eval -s trust_invest=0.05 -s notes_v2=True -s note_unsure=decline -s min_slack_min=140 -s slack_per_drive=0.75 -s dealer_lr=0.01 --name exact-trust-dlr01-dev`
- Taxback stack (`exact-trust-floor-taxback-dev`):
  `uv run lab eval -s trust_invest=0.05 -s notes_v2=True -s note_unsure=decline -s min_slack_min=140 -s slack_per_drive=0.75 -s dealer_lr=0.01 -s same_day_min_supply=50 -s price_target_win=0.40 -s min_supply=20 --name exact-trust-floor-taxback-dev`

## Results (level 8, vs champion v2, paired)
All smoke and dev runs build on top of `n14-01394` Run B (`trust_invest=0.05, notes_v2=True, note_unsure=decline, min_slack_min=140, slack_per_drive=0.75`):

| set | config (on top of `n14-01394` Run B) | run folder | mean margin | Δmargin ± SE | t | better/worse | on-time min | mean on-time (Δ) | SAFE |
|---|---|---|---|---|---|---|---|---|---|
| smoke | no-op (defaults) | `runs/20261114-022638-trust-floor-noop` | €9,662.25 | €+0.00 ± 0.00 | — | 0/0 | 95.5% | 96.7% (+0.00%) | yes |
| smoke (ref) | `n14-01394` Run B baseline | `runs/20261114-015732-stack-smoke-140` | €10,060.98 | €+398.73 ± 478.25 | 0.83 | 3/1 | 96.4% | 97.8% (+1.09%) | yes |
| smoke S1 | `trust_gain=0.40, dealer_lr=0.01` | `runs/20261114-022747-trust-floor-s1` | €10,322.77 | €+660.53 ± 508.65 | 1.30 | 2/2 | 95.9% | 97.7% (+1.04%) | yes |
| smoke S2 | `dealer_lr=0.01, floor_all_only=True, expected_fee_mult=1.10` | `runs/20261114-023014-trust-floor-s2` | €10,334.10 | €+671.86 ± 136.12 | 4.94 | 4/0 | 97.3% | 98.1% (+1.44%) | yes |
| smoke S3 | `trust_gain=0.40, dealer_lr=0.01, floor_all_only=True, expected_fee_mult=1.10` | `runs/20261114-023123-trust-floor-s3` | €9,714.94 | €+52.69 ± 312.23 | 0.17 | 2/2 | 96.4% | 97.7% (+1.06%) | yes |
| smoke S4 | `trust_gain=0.20, dealer_lr=0.01, floor_all_only=True, expected_fee_mult=1.10` | `runs/20261114-023252-trust-floor-s4` | €10,140.83 | €+478.58 ± 75.51 | 6.34 | 4/0 | 97.8% | 98.2% (+1.47%) | yes |
| smoke S5 | `dealer_lr=0.01, floor_all_only=True, expected_fee_mult=1.06` | `runs/20261114-023407-trust-floor-s5` | €9,893.60 | €+231.35 ± 349.19 | 0.66 | 3/1 | 97.0% | 97.4% (+0.67%) | yes |
| smoke S6 | `dealer_lr=0.01` (`expected_fee_mult=1.25`) | `runs/20261114-023928-trust-floor-s6` | **€10,407.36** | **€+745.11 ± 291.73** | **2.55** | **4/0** | **95.9%** | **97.6% (+0.93%)** | **yes** |
| dev (ref) | `n14-01394` Run B (`dealer_lr=0.02`) | `runs/20261114-020214-stack-trust-notes-slack140-dev` | €9,478.39 | €+488.08 ± 182.33 | 2.68 | 14/2 | 95.3% | 97.8% (+1.08%) | yes |
| dev (ref) | `n14-01394` Run C (`+ taxback, dealer_lr=0.02`) | `runs/20261114-020419-stack-trust-notes-taxback-dev` | €9,626.63 | €+636.33 ± 269.13 | 2.36 | 12/4 | 93.1% | 96.0% (-0.71%) | yes |
| dev 1 | `dealer_lr=0.01, floor_all_only=True, expected_fee_mult=1.10` | `runs/20261114-023517-exact-trust-floor-dev` | €9,319.30 | €+329.00 ± 147.03 | 2.24 | 11/5 | 94.7% | 97.6% (+0.83%) | yes |
| **dev 2** | **`dealer_lr=0.01` (`expected_fee_mult=1.25`)** | `runs/20261114-024022-exact-trust-dlr01-dev` | **€9,527.77** | **€+537.47 ± 142.66** | **3.77** | **14/2** | **95.7%** | **97.4% (+0.63%)** | **yes** |
| **dev 3** | **`dealer_lr=0.01 + taxback (`sd50, win0.40, sup20`)`** | `runs/20261114-024304-exact-trust-floor-taxback-dev` | **€9,770.18** | **€+779.87 ± 316.97** | **2.46** | **12/4** | **93.7%** | **96.2% (-0.58%)** | **yes** |

### Paired comparisons against `n14-01394` Run B and Run C (`uv run lab compare`)
- **Dev 2 (`exact-trust-dlr01-dev`) vs Champion v2:** **`Δmargin €+537.47 ± 142.66` (`t = 3.77`, 14/16 seeds better)**, worst-seed on-time **`95.7%`** (`+1.3%` above Champion v2's `94.4%`).
- **Dev 2 (`exact-trust-dlr01-dev`) vs `n14-01394` Run B (`+€488.08`):** Adding `dealer_lr=0.01` increases mean margin by **`+€49.39/wk`** (`€9,527.77` vs `€9,478.39`), increases median margin by **`+€257.42`** (`€8,688.35` vs `€8,430.93`), reduces SE against champion from `€182.33` to **`€142.66`** (`t` jumps from `2.68` to **`3.77`**), and raises worst-seed on-time from `95.3%` to **`95.7%`**.
- **Dev 3 (`exact-trust-floor-taxback-dev`) vs `n14-01394` Run B (`+€488.08`):** **`Δmargin €+291.79 ± 263.28` (`t = 1.11`, 9/7 better)**, lifting mean margin to **`€9,770.18` (`Δmargin €+779.87 ± 316.97` vs Champion v2, `t = 2.46`, 12/4 better)**.
- **Dev 3 (`exact-trust-floor-taxback-dev`) vs `n14-01394` Run C (`+€636.33`):** Adding `dealer_lr=0.01` to the taxback stack increases mean margin by **`+€143.55/wk`** (`€9,770.18` vs `€9,626.63`), lifts median margin by **`+€266.64`** (`€9,530.10` vs `€9,263.46`), and improves worst-seed on-time by **`+0.6%` (`93.7%` vs `93.1%`)**.

### Stats counters and ledger breakdown (mean per world across 16 dev seeds)
| Metric / Counter | Champion v2 | `n14-01394` Run B | `n14-01394` Run C | Dev 1 (`floor 1.10 + dlr01`) | **Dev 2 (`dlr01`)** | **Dev 3 (`dlr01 + taxback`)** |
|---|---:|---:|---:|---:|---:|---:|
| `won` (orders/wk) | 230.12 | 231.62 | 276.06 | 239.44 | **233.81** | **278.06** |
| `quote_quote` | 470.1 | 472.9 | 479.2 | 607.0 | **478.2** | **489.9** |
| `quote_floor` | 202.6 | 198.5 | 244.1 | 64.8 | **193.5** | **231.9** |
| `quote_decline` | 361.9 | 363.2 | 311.4 | 362.9 | **362.9** | **312.9** |
| `quote_unblinded` | 0.0 | 0.0 | 0.0 | 19.1 | **0.0** | **0.0** |
| `top_dealer_trust_d0..d4` | — | 4.1/15.0/23.4/22.5/22.6 | 5.2/18.8/22.2/22.9/24.7 | 4.2/16.0/23.3/22.9/24.1 | **4.2/14.5/24.2/22.4/23.1** | **5.2/17.5/21.4/23.5/24.5** |
| `price_ratio_d0..d4_pct` (%) | — | 143.7/149.7/160.2/167.1/166.7 | 143.4/147.7/156.6/163.0/161.5 | 141.8/149.6/158.9/165.7/163.5 | **143.8/149.5/158.9/166.8/165.9** | **143.8/147.9/155.9/162.7/161.0** |
| Ledger `revenue` (€/wk) | +26,922.43 | +27,172.62 | +31,230.20 | +28,188.62 | **+27,601.76** | **+31,636.03** |
| Ledger `driver_fee` (€/wk) | -17,286.92 | -17,287.23 | -20,922.60 | -18,422.56 | **-17,597.81** | **-21,119.04** |
| Ledger `late_refund` (€/wk) | -376.20 | -298.42 | -592.73 | -341.97 | **-364.80** | **-626.85** |
| Ledger `failed_visit` (€/wk) | -165.44 | -30.02 | -10.33 | -27.06 | **-36.75** | **-43.19** |
| Ledger `waiting` (€/wk) | -39.38 | -21.98 | -24.48 | -23.02 | **-16.89** | **-16.82** |

### Diagnosis: why `dealer_lr=0.01` helps while lowering `expected_fee_mult` to `1.10` and raising `trust_gain` hurt on dev
1. **Why lowering `expected_fee_mult` (`1.25 -> 1.10`) with `floor_all_only=True` lost `€208.47/wk` vs `Dev 2` (`€9,319.30` vs `€9,527.77`):**
   - The competitor prices strictly off `listPriceCents` (`list × lane × day × level`), whereas our driver fees scale with `referenceFeeCents`. The ~198 quotes/wk that hit the `1.25` floor (`1.359 × referenceFeeCents`) are requests where `referenceFeeCents / listPriceCents` is in the upper tail (`1.00–1.18×`).
   - When `Dev 1` lowered `expected_fee_mult` to `1.10` and enabled `floor_all_only=True`, `133.7` high-fee-ratio quotes/wk moved from `"floor"` (`198.5 -> 64.8`) to `"quote"` (`472.9 -> 607.0`). This produced two negative effects across the 16 dev worlds:
     1. **Adverse selection on won orders:** `Dev 1` won `+7.8` additional previously-floored orders/wk (`231.6 -> 239.4`), generating `+€1,016/wk` in revenue (`€130/order`) but costing **`-€1,135/wk` in driver fees (`€145/order`, nearly double our `€74.6/order` normal average)**—a net loss even before late refunds.
     2. **Downward contamination of `self.mult`:** Because even a `1.196 × referenceFeeCents` floor is often expensive relative to `listPriceCents` on high-`referenceFee/list` requests, unblinding `Desk.learn()` on those quotes fed extra losses into the global multiplier, pulling `price_ratio_d0..d4_pct` down by `-1.3%` to `-3.2%` (`166.7% -> 163.5%` on Friday).
   - Thus, the `expected_fee_mult = 1.25` floor is not a bug: it acts as both an **adverse-selection filter** against high-`referenceFee/list` requests and a **learning shield** that prevents losses on structurally high-cost requests from dragging `self.mult` down.
2. **Why `trust_gain > 0` (`0.20`, `0.40`) underperformed `trust_gain = 0.0` (`Smoke 3/4` vs `Smoke 2`, `Smoke 1` vs `Smoke 6`):**
   - When `trust_gain` adds an explicit markup on high-trust dealers (`D01`), any extra quote losses at `D01` (especially on mornings after the competitor cuts its prices for dealers where we won most) still pass through `Desk.learn()` and step `self.mult` down globally by `-0.35 × 0.05 = -1.75%` per loss.
3. **Why `dealer_lr = 0.01` works on both the conservative (`+€537.47, t=3.77`) and taxback (`+€779.87, t=2.46`) stacks:**
   - Halving `dealer_lr` from `0.02` to `0.01` damps per-dealer oscillation (`dealer_adj`) while letting `self.mult` (`price_lr = 0.05`) and `trust_invest = 0.05` track the market cleanly. This shifts `5.3` quotes/wk (`Dev 2`) to `12.2` quotes/wk (`Dev 3`) out of the floor into normal quotes and wins `+2.0–2.2` profitable orders/wk (`+€429/wk` revenue for `-€311/wk` driver fee on `Dev 2`; `+€406/wk` revenue for `-€196/wk` driver fee on `Dev 3`).

## Verdict
**adopt `dealer_lr=0.01` on top of the `trust+notes+slack` stack (reject `expected_fee_mult=1.10`, `floor_all_only=True`, and `trust_gain>0`)** — Conservative stack (`Dev 2`): **Δmargin €+537.47 ± 142.66 (`t = 3.77`, 14/2 seeds better, `95.7%` min / `97.4%` mean on-time SAFE)**; Taxback stack (`Dev 3`): **Δmargin €+779.87 ± 316.97 (`t = 2.46`, 12/4 seeds better, `93.7%` min / `96.2%` mean on-time SAFE)**.
