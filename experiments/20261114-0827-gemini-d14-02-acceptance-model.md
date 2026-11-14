# d14-02-acceptance-model: Learned acceptance model, lane table, buffer classes, and asymmetric lane-prior pricing (c3 / R8 / Idea #28)

- **Agent / branch / commit:** gemini · `exp/gemini-d14-02-acceptance-model` · built on `559da3c` (Champion v3T)
- **Date:** 2026-11-14 08:27
- **Idea from:** `experiments/IDEAS.md` R8 ("Acceptance curve and lane table") and #28 ("A learned lane table for the price"), brief `c3` / `02-acceptance-model`

## Why we tried it
At level 8, `HANDBOOK.md` states that the competitor prices each option as list price times four factors: (1) a **lane factor** by pickup and delivery place ("higher where little work comes back and where few drivers live near the delivery place; this part is almost the same in every world"), (2) a world-day busyness factor, (3) a world price level (`1.26–1.54×` list), and (4) request noise — plus dealer trust (`+1%` accepted price per on-time order up to 25, halved on a late order). Idea #18 (`n14-06042`, `-€342`) failed because `referenceFeeCents / listPriceCents` is only a noisy proxy for the lane (`price weight = +0.045` once places are controlled) and A's margin floor already handled its high-cost tail. Here we first fit exact logistic models of `won` and `late` across 224 revealed level-8 worlds (`96` independent seeds on v3T + `64` on v2 + `64` on v3) to measure the true competitor lane factor and `<2%` late buffer classes (Part 1), and then test pricing with the shrunk lane prior (Part 2).

---

## Part 1: Slot-free acceptance and lateness models (224 revealed L8 worlds)

We revealed all 224 finished level-8 worlds across v2 (`64` worlds: `dev` 16, `holdout` 16, `night` 32), v3 (`64` worlds: `dev` 16, `holdout` 16, `final` 32), and current Champion v3T (`96` independent worlds: `dev` 16, `holdout` 16, `night` 32, `final` 32; `73,718` non-decline quotes and `28,307` won orders). Using pure-Python exact Schur-complement Newton-Raphson / IRLS (`experiments/scripts/fit_acceptance_and_late.py`), we profiled out all `(world, day)` fixed effects (`480` in v3T 96w; `800` in pooled v2+v3T 160w) with exact asymptotic standard errors. To avoid post-outcome selection bias on multi-option quotes, `log(quote / list)` is measured pre-outcome (minimum quoted `quoteCents / listPriceCents`) alongside exact quoted-option-set indicators.

### 1. Acceptance slope in `log(quote / list)` and dealer trust (`+1%` rule)
| Dataset / specification | Non-decline quotes | Win share | `b_log(quote/list)` ± SE | Cost of `+1%` price in win chance | `b_trust` ± SE | Implied trust price premium (`b_trust / -b_price`) |
|---|---:|---:|---:|---:|---:|---:|
| **v3T 96w (primary)** | 73,718 | 38.8% | **−11.922 ± 0.127** (`t = -93.9`) | **−1.98 pp** avg (`−2.86 pp` at `p=0.40`) | **+0.1156 ± 0.0014** (`t = +82.6`) | **+0.97% / count** |
| v3T 96w (unfloored quotes only) | 55,300 | 42.1% | −11.996 ± 0.152 | −2.11 pp avg | +0.1157 ± 0.0016 | +0.96% / count |
| v3T 96w (`+log(typ/list) + log(km)`) | 73,718 | 38.8% | −12.320 ± 0.133 | −2.04 pp avg | +0.1174 ± 0.0014 | +0.95% / count |
| v3T 96w (`+dealer` fixed effects) | 73,718 | 38.8% | −11.860 ± 0.128 | −1.96 pp avg | +0.1098 ± 0.0020 | +0.93% / count |
| **Pooled v2 + v3T 160w** | 118,445 | 37.1% | **−11.767 ± 0.099** (`t = -118.9`) | **−1.93 pp** avg | **+0.1155 ± 0.0012** | **+0.98% / count** |

- **Price elasticity:** Every `+1%` in quote price costs **1.98 percentage points** of win probability averaged over all quotes (and **2.86 pp** right at the `40%` target win rate). At `b = -11.92` and `p = 0.40`, the unconstrained single-order Lerner markup `(p - c)/p = 1 / (-b(1 - p))` is **14.0%**.
- **Dealer trust:** Replay of account lines (`+1` capped at 25 on `revenue` without `late_refund`, `//= 2` on `late_refund` or `undelivered_penalty`) yields `+0.1156 ± 0.0014` log-odds per trust count = **+0.97% accepted price per trust count** (`log(1 + 0.01 × 12.5)/12.5 = 0.94%`), matching `RULES.md`'s `+1%` per count to within `0.03%`.
- **Other covariates (in log-price equivalent):** Late afternoon quotes (`15:00–17:59`) clear **+1.95% to +2.21%** higher than morning (`09:00–11:59`: `−0.9%`); Tuesday–Friday `(world, day)` intercepts average `+0.46 to +0.80` log-odds (`+3.8% to +6.7%` in price) above Monday; `log(batch_size)` is slightly negative (`−0.22%` per unit log batch); and once pickup/delivery places are controlled, `log(typical_fee / list)` has a log-price weight of only **`+0.045 ± 0.006`** and `log(km)` **`+0.008 ± 0.001`** — explaining why Idea #18 (`fee_weight = 0.25–0.75`) over-tilted on noise.

### 2. Cross-world stability of pickup & delivery place effects and `lane_table.json`
Splitting strictly across **disjoint seeds** so world-specific draws never leak across halves:
- **Half A (48 even seeds) vs Half B (48 odd seeds) on v3T:**
  - Delivery places (`n = 30` towns): unweighted `r = +0.966`, quote-weighted **`r = +0.987`**.
  - Pickup places: quote-weighted **`r = +0.928`** (`r = +0.783` unweighted on the 17 towns with `n ≥ 200`).
  - Combined shrunk lane effect (`pickup + delivery`): quote-weighted **`r = +0.975`**.
- **Cross-policy & cross-seed (`v2` on `night-01..32` vs `v3T` on `final-01..32`):** delivery `r = +0.967` (`+0.977` wt), pickup wt `r = +0.920`, combined lane **`r = +0.962`**.
- **Zero-leakage table export (`src/spread_lab/data/lane_table.json`):** To keep **both `dev` and `holdout` 100% strictly out-of-sample**, we exported the Empirical-Bayes SE-shrunk log-price effects (`alpha_shrunk = alpha * tau^2 / (tau^2 + se^2)`, `pickup_tau = 0.037`, `delivery_tau = 0.080`) fitted exclusively on the **64 fresh worlds** (`night-01..32` + `final-01..32`, `49,576` quotes). It correlates at **`r = +0.9961`** with the full 96-world fit, **`r = +0.9245`** out-of-sample with `dev-16`, and **`r = +0.9600`** out-of-sample with `holdout-16`.
  - **Economic structure:** Outbound from Capital (`vantaa +3.4%`, `espoo +1.5%`, `hyvinkaa +1.3%`) to remote/dead-end delivery towns (`kemi +14.4%`, `ylivieska +12.9%`, `kajaani +12.4%`, `savonlinna +11.9%`, `kokkola +11.8%`, `joensuu +9.7%`, `mikkeli +9.3%`) carries **`+10% to +18%`** higher competitor prices. Inbound from regional towns (`kouvola −6.8%`, `salo −5.3%`, `jyvaskyla −4.5%`, `lahti −4.0%`, `turku −4.0%`, `oulu −3.9%`, `lempaala −3.9%`, `tampere −3.5%`) into Capital/Ring (`vantaa −10.2%`, `helsinki −6.5%`, `hyvinkaa −5.9%`, `espoo −5.4%`) carries **`−10% to −17%`** lower competitor prices.
  - Out-of-sample on `dev + holdout` (32 untouched worlds), Champion v3T wins **23.6%** on the low tercile (`eff < −0.0375`), **37.4%** on the mid tercile, and **51.6%** on the high tercile (`eff ≥ +0.0448`).

### 3. Lateness model over won orders (`n = 28,307`, `732` late = `2.59%`) and `<2%` buffer classes
In `late ~ won_log_price + pickup + delivery + option + weekday + hour + log_bsize + trust + drive_hr + (world, day)`:
- Strongest drivers of lateness (log-odds): `is_same_day` (`+0.69 ± 0.11`, `2.0×` odds vs `next_day`), `is_within_3_days` (`−1.13 ± 0.25`, `0.32×` odds vs `next_day`), `drive_hr` (`+0.190 ± 0.030` per drive hour), weekday progression (`Thu +0.47`, `Fri +0.76` = `2.15×` Mon), and afternoon arrival (`12:00+` `+0.38`). `trust` (`−0.001 ± 0.005`) and `batch_size` (`−0.03 ± 0.04`) are zero on lateness.
- **Buffer classes (`< 2.0%` empirical late rate AND `< 2.3%` 95% Wilson upper bound across 96 v3T worlds):**

| Buffer class (won orders on v3T, 96 worlds) | Orders / wk | Late % (95% Wilson UB) | Margin / order |
|---|---:|---:|---:|
| `within_3_days` & `drive < 300 min` (any pickup) | 11.5 / w | **0.54%** (1.18%) | €46.82 |
| `within_3_days` (all drives, incl. `300m+`) | 17.2 / w | **1.15%** (1.79%) | €58.13 |
| Ring (`sup30 < 30, sup55 ≥ 30`) → Capital (`drive < 60m`, any option) | 16.5 / w | **0.95%** (1.56%) | €25.35 |
| Capital (`helsinki/espoo/vantaa`) `next_day`, `60 ≤ drive < 300m` | 47.0 / w | **1.20%** (1.56%) | €48.55 |
| Capital `next_day`, `drive < 300m` (all `<300m`) | 65.0 / w | **1.49%** (1.82%) | €41.54 |
| Capital `same_day`, `drive < 180m`, no note, Mon–Thu, `hour < 13` | 17.8 / w | **1.58%** (2.29%) | €29.02 |
| Inbound to Capital (any pickup → Capital), `next_day`, `drive < 300m` | 25.5 / w | **1.67%** (2.26%) | €29.99 |
| Non-capital `next_day`, `60 ≤ drive < 180m` | 53.9 / w | **1.76%** (2.15%) | €39.06 |
| `c4` default rule (`sup30 ≥ 100, drive ≤ 120m, !(sd & hr≥13), !note`) | 45.0 / w | **1.78%** (2.22%) | €31.79 |
| **Combined clean buffer union** (`w3d<300` OR `nd<300 & !note & (cap_pk | cap_dl | 60≤drv<180)` OR `sd<180 & !note & Mon–Thu & (cap_pk | cap_dl)`) | **125.0 / w** | **1.36%** (**1.58%**) | **€38.33** |

*(Note for `c4`: raw `Capital same_day < 60m` without day/hour/note filters is `2.36%` late and `Capital next_day < 60m` with notes is `2.74%` late; excluding notes and Friday keeps the 125-order/week buffer union at **1.36% late** and €38.33/order vs €31.79/order on `c4`'s default rule.)*

---

## Part 2: Pricing with the lane table (`lane_prior_weight`)

### What changed
- Added `src/spread_lab/data/lane_table.json` (fitted strictly on the 64 fresh worlds `night-01..32` + `final-01..32`; note for lead: `scripts/promote.sh`'s `allow` regex currently lists `policy.py`, `notes.py`, and `policies/`, so promoting a branch with `src/spread_lab/data/` would need `data/` in `allow` or inlining the 60-float dict).
- Added to `Params` in `src/spread_lab/policy.py` (all defaults neutral, reproducing Champion v3T to `€0.00`):
  - `lane_prior_weight: float = 0.0`: scales `listPriceCents` by `clamp(exp(weight * (pk_eff + dl_eff)), 0.85, 1.15)` before `option_mult` and before `floor`; `rejoin()` normalizes win ratios by `lane_mult`.
  - `lane_prior_only_neg: bool = False`: when `True`, applies the prior only when `pk_eff + dl_eff < 0` (discounting inbound-to-Capital/Ring lanes where the competitor undercuts us, without hiking outbound Capital lanes).
  - `lane_prior_comp_slope: float = 0.0`: when `> 0`, shifts `Desk.learn()`'s target win rate on tilted quotes by `-comp_slope * log(lane_mult)` so extra inbound wins do not ratchet `self.mult` upward across untitled lanes.
- Added telemetry counters `lane_quotes_{low,mid,high}`, `lane_wins_{low,mid,high}`, `lane_late_{low,mid,high}`, and `lane_margin_{low,mid,high}_cents`.

### Results (normal instrument vs Champion v3T; worst world reported first)
| Run | Seed set | Worst world on-time (<92% count) | Mean margin | Δmargin ± SE (t, W/L) | Mean on-time (Δ) | Won / wk | SAFE? |
|---|---|---|---|---|---|---|---|
| `20261114-081116-lane-prior-noop` | smoke (4) | **94.38%** `dev-01` (0/4) | €10,816.98 | **+€0.00 ± 0.00** (0/0) | 95.98% (+0.00%) | 283.2 | SAFE |
| `20261114-081150-lane-prior-w05-dev8` (`w=0.5`) | dev-01..08 (8) | **93.14%** `dev-07` (0/8) | €10,982.96 | **−€137.09 ± 240.03** (`t = -0.57`, 4/4) | 96.83% (+0.19%) | 291.4 | SAFE |
| `20261114-081257-lane-prior-w10-dev8` (`w=1.0`) | dev-01..08 (8) | **93.95%** `dev-07` (0/8) | €10,814.60 | **−€305.45 ± 127.16** (`t = -2.40`, 2/6) | 96.86% (+0.21%) | 292.0 | SAFE |
| `20261114-081846-lane-prior-neg075-comp-dev8` (`w=0.75, neg, c=2.0`) | dev-01..08 (8) | **94.24%** `dev-01` (0/8) | €11,595.20 | **+€475.15 ± 228.30** (`t = +2.08`, 6/2) | 96.80% (+0.15%) | 317.9 | SAFE |
| `20261114-082000-lane-prior-neg100-comp-dev8` (`w=1.0, neg, c=2.0`) | dev-01..08 (8) | **90.33%** `dev-07` (**1/8**) | €11,372.65 | **+€252.60 ± 267.13** (`t = +0.95`, 6/2) | 95.99% (−0.65%) | 330.4 | NOT SAFE |
| **`20261114-082118-lane-prior-neg075-comp-dev`** (`w=0.75, neg, c=2.0`) | **dev (16)** | **94.06%** `dev-13` (**0/16**) | **€11,137.58** | **+€252.70 ± 142.89** (`t = +1.77`, **10/6**) | 96.77% (−0.19%) | 303.2 | **SAFE** |
| **`20261114-082448-lane-prior-neg060-c14-dev`** (`w=0.60, neg, c=1.4`) | **dev (16)** | **94.31%** `dev-07` (**0/16**) | **€11,047.84** | **+€162.95 ± 91.38** (`t = +1.78`, **11/5**) | 96.85% (−0.11%) | 295.2 | **SAFE** |

### Why symmetric `lane_prior_weight` lost (`−€305`), and why asymmetric slope-compensated inbound discounting flipped it (`+€253`)
The tercile counters on `dev-01..08` expose the exact mechanism:
1. **Symmetric `lane_prior_weight = 1.0` equalized win rates across lanes with pinpoint accuracy (`28.8% / 39.4% / 48.2%` → `41.9% / 41.1% / 36.4%`) and cut `driver_fee / revenue` by `−1.45 pp` (`61.32% → 59.87%`), yet lost `−€305.45 ± 127.16/w`:**
   - `low` tercile (`eff < −0.0375`, short/inbound to Capital): wins rose `72.5 → 105.2/w` (`+32.7`), adding **`+€556.71/w`** (`€1,986.53 → €2,543.24`).
   - `mid` tercile: wins rose `91.6 → 95.9/w`, adding **`+€72.35/w`**.
   - `high` tercile (`eff ≥ +0.0448`, long-ticket outbound from Capital, where 300–450 drivers live and v3's gates already removed risky >480m next-day trips): gross margin is **35% (`€52.40/win`)** — already `2.5×` above the `14.0%` unconstrained Lerner optimum! Hiking `high` by `+8.5%` raised margin/win by `+€7.09` (`€52.40 → €59.49`) on the `93.8` retained cars (`+€665/w`) while losing `30.6` `€52.40/win` orders (`−€1,605/w`), for a net **`−€939.78/w`** loss on `high`! Because `Desk.learn()` holds total win share fixed at `40%` (`291 → 295/w`), a symmetric lane prior swaps `31` `€52/car` outbound wins 1-for-1 for `33` `€24/car` inbound wins.
2. **One-sided slope-compensated inbound discounting (`lane_prior_only_neg=True, lane_prior_comp_slope > 0`) turns the inbound gain into additive volume without cannibalizing `high`:**
   - Leaving `eff > 0` untouched (`only_neg=True`) AND shifting `learn()`'s target win rate on discounted `low` quotes by `-comp_slope * log(lane_mult)` keeps `self.mult` anchored at the champion's equilibrium.
   - On all 16 `dev` worlds (100% out-of-sample for `lane_table.json`), `w=0.75, only_neg=True, comp_slope=2.0` (`lane-prior-neg075-comp-dev`) lifts `low` wins `65.4 → 88.2/w` (**`+€368.69/w`**) and `mid` wins `87.7 → 90.1/w` (**`+€71.44/w`**) while keeping `high` wins intact (`127.1 → 127.8/w`), raising total weekly margin by **`+€252.70 ± 142.89` (`t = 1.77`, 10/16 seeds, worst world `94.06%` SAFE)** and lifting worst-world margin by **`+€448.85`** (`€7,487.67 → €7,936.52`).
   - Tightening compensation to the exact `low`-tercile slope `w=0.60, only_neg=True, comp_slope=1.4` (`lane-prior-neg060-c14-dev`) holds `high` wins identical to the tenth of a car (`127.1 vs 127.1/w`), improves worst-world on-time above the champion (**`94.31%` vs `94.26%`**), and wins on **11/16 seeds** (`+€162.95 ± 91.38`, `t = 1.78`, SAFE). Pushing to `w=1.0, neg, comp_slope=2.0` (`330` wins/w) hits fleet congestion on `dev-07` (`393` wins, `90.33%` on time).

## Verdict
**needs work / borderline positive (keep defaults off; `lane_table.json` and buffer classes ready)** — Pure symmetric `lane_prior_weight` (`0.5`: `−€137 ± 240`; `1.0`: `−€305 ± 127`, `t = -2.40`) is **rejected** because equalizing win rates across lanes under a fixed-win-rate tracker swaps €52/win Capital-outbound orders for €24/win inbound orders; one-sided slope-compensated inbound discounting flips this to **SAFE `+€252.70 ± 142.89` (`t = 1.77`, 10/16, worst on-time `94.06%`)** at `w=0.75, only_neg=True, comp_slope=2.0` and **SAFE `+€162.95 ± 91.38` (`t = 1.78`, 11/16, worst on-time `94.31%`)** at `w=0.60, only_neg=True, comp_slope=1.4`, just shy of the standalone `t ≥ 2.0` / `12/16` promotion bar unless gated by `projected_on_time` (`c4`).
