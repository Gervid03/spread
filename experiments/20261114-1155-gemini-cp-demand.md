# cp-demand: Co-play demand-curve probing, inbound-to-hub floor & lane pricing, zero-drift centered trust, and multi-option floor spread

- **Agent / branch / commit:** gemini · `exp/gemini-cp-demand` · built on `f3acbfb` (`Champion d93271e`, `€10,884.88` dev / `€11,704.16` holdout)
- **Date:** 2026-11-14 11:55 Helsinki (09:55 UTC)
- **Idea from:** Co-play focus `cp-demand` on `dev-02` + Carbon brief `c3` (`experiments/prompts/carbon/c3-acceptance-model.md`, `IDEAS.md` R8 & #28)

## Why we tried it
The champion desk (`d93271e`) prices every request using one global win-rate tracker `self.mult` (`price_target_win = 0.40`, `price_lr = 0.05`), a slow per-dealer multiplier `dealer_adj` (`dealer_lr = 0.01`), no explicit trust term (`trust_gain = 0.0`), no lane factor, and a uniform minimum-margin floor `1.25 × referenceFeeCents / 0.92 = 1.359 × referenceFeeCents` across all directions and options.

Using `scripts/coplay.py`'s fork-based binary-search **`probe`** on `dev-02` (`cp-demand-1`, 30 exact reservation-price probes across Monday–Friday, dealers, trust levels, floors, and declines) and verifying our hypotheses slot-free across 64 strictly out-of-sample Level-8 worlds (`night-01..32 + final-01..32`, 49,190 non-declined quotes), we mapped four structural demand-curve distortions where the desk leaves money on the table or loses profitable cars at the floor:

1. **Inbound-to-Hub (`non-Hub → Capital`, `pickup_supply < 200` and `deliv_supply >= 200`) double squeeze — lane factor + over-conservative `1.25×` fee floor:**
   - Competitor lane factors are `-6%` to `-15%` lower into the Capital hub (`Vantaa -0.107, Helsinki -0.066, Espoo -0.056`) because 434 drivers live near the destination. On `dev-02`, Tuesday probe `R00270` (`D14(0)`, `Raisio[103]→Helsinki[434]`, `list €69`, `ref €63`) had a true dealer limit of **`1.160 × list` (`€80.04`)**, whereas we quoted `×1.62` (`€112`) and even our `1.25×` floor (`€85.60 = ×1.241`) exceeded the dealer's limit — despite `Raisio→Helsinki` drivers booking going home at **`0.85 × ref = €53.55`** (`€26.50` profit at `€80`, plus relocating a driver into the Capital hub!).
   - Across 64 out-of-sample worlds (`experiments/scripts/analyze_demand_mechanisms.py`), `inb_to_hub` (`133.7` quotes/wk) wins **only `21.5%` unfloored** and **`17.2%` floored** (`33.7%` = `45.1` quotes/wk hit the `1.25×` floor!), even though `inb_to_hub` has the **lowest actual booked driver fee (`0.925 × ref`)** and **lowest late rate (`1.17%` = `98.83%` on-time!)** of any direction (`€31.10/ord` direct margin + Capital hub driver replenishment), while `hub_outbound` wins **`51.9%`** unfloored (`€43.98/ord`).
   - Earlier `d14-02` (`lane_prior` alone, `+€253 ± 143, t=1.77`) stalled short of `t=2` because `33.7%` of discounted `inb_to_hub` quotes slammed into the `1.25×` floor; conversely, earlier `n14-02241` (`expected_fee_mult=1.10` everywhere, `-€208`) failed because lowering the floor on *outbound* routes admitted `€145`-fee money-losers (`R00153`: `list €61`, `ref €113`, probed limit `€87.47 < ref`!) and unblinded `Desk.learn()` on high-`ref/list` losses.

2. **Trust contamination of global `self.mult` (`dealer_lr = 0.01` vs `+25%` top-dealer trust):**
   - By Tuesday `09:34` on `dev-02`, top dealer `D01` (`trust=12`, probe `R00272` limit `1.926` vs our `1.74` -> left `€13` on the table) had pulled global `self.mult` up to `1.553`, pricing out `trust=0..1` dealers (`R00271` `D02(1)` `Vantaa→Lahti`: limit `1.434` vs our `1.62` -> lost `€31` profit!).
   - Across 64 out-of-sample worlds (`27,212` Tue–Fri unfloored quotes), dealers with `trust - trust_ema < -6` win **only `27.95%`**, while dealers with `trust - trust_ema > +6` win **`50.01%`** (`+22.1 pp` gap!). Uncentered `trust_gain > 0` failed previously (`-€285`) because `(1 + gain * count/100) >= 1` injects upward drift into `self.mult`. Centering around an online quote-stream EMA `exp(slope * (count - trust_ema))` has **exact mean zero**, charging `+4–5%` more on `D01(25)`, discounting `-4%` on `trust=0` dealers, and immediately dropping price if a late order halves `D01`'s trust (`25 -> 12` on `dev-02` Thu).

3. **Multi-option floor compression (`floored_sd_prem`):**
   - Because `Desk.price()` applies the same euro floor to `same_day` and `next_day` (`list_nd ≈ 0.925 × list_sa`), when `next_day` hits the floor (`~52` quotes/wk), `same_day / next_day` compresses toward `1.00`. On `dev-02` probe `R00269` (`Raisio→Lahti`, `ne` floored at `€129`, `sa` at `€138`), the dealer's real `same_day` limit was **`1.898 × list = €161.33`** (`€23.33` left on the table!). Enforcing `same_day >= next_day × (1 + floored_sd_prem)` either captures free `same_day` margin or steers borderline dealers into safer `next_day` (`-6` risky `same_day` cars/wk), creating the exact capacity headroom needed for the `+20` extra `inb_to_hub` cars.

4. **Option-stripping speed penalty & Friday price war (`probe` findings on `dev-02`):**
   - Probing requests where our safety gates stripped `same_day` (`R00021` `Porvoo→Hyvinkää` limit `1.242` vs `R00020` `Porvoo→Espoo` `same_day` limit `1.570`; `R00662` `Vantaa→Ylivieska` `0.805`; `R00870` `1.215` vs `R00867` `1.434`) revealed a `20–35%` reservation-price penalty when quoting `next_day` alone against the competitor's `same_day`. Probing Friday (`R00866: 0.996, R00871: 1.051, R00869: 0.777`) caught the Level-8 `-20%` price war directly in action.

---

## Co-play journal on `dev-02` (`cp-demand-1`, `cp-demand-2`, `cp-demand-3`)

### 1. Selected fork probes from `cp-demand-1` (`dev-02`, Champion week `€10,280.90`, `259` won, `95.0%` on-time)
| Time | ID | Dealer(Trust) | Route [30km supply] | Decision & Our Quote | Probed Option & **Real Limit** | Gap (`Quote - Limit`) | Takeaway |
|---|---|---|---|---|---:|---:|---|
| Mon 09:20 | `R00004` | `D01(0)` | `Hyvinkää[50]→Vantaa[434]` | `quote sa×1.39 ne×1.32 wi×1.32` | `sa`: **`1.652`** (`€57.82`) | `-0.262` (`-€8.82`) | Won; Mon prior below world open |
| Mon 09:20 | `R00005` | `D01(0)` | `Hyvinkää[50]→Vantaa[434]` | `floor sa×1.39 ne×1.32 wi×1.45` | `sa`: **`1.570`** (`€54.95`) | `-0.180` (`-€5.95`) | Won; `wi` hit floor (`ref €32`) |
| Mon 10:10 | `R00020` | `D04(0)` | `Porvoo[4]→Espoo[434]` | `quote sa×1.51 ne×1.43 wi×1.43` | `sa`: **`1.570`** (`€61.23`) | `-0.060` (`-€2.23`) | Ring→Hub `sa` kept; won at `0.85×` fee |
| Mon 10:10 | `R00021` | `D03(0)` | `Porvoo[4]→Hyvinkää[50]` | `quote ne×1.44` (`sa` stripped) | `ne`: **`1.242`** (`€45.95`) | `+0.198` (`+€7.05`) | Lost; stripping `sa` cuts limit `-21%` |
| Mon 11:00 | `R00041` | `D02(0)` | `Kuopio[13]→Pori[1]` | `decline sa×4.00` | `sa`: **`1.516`** (`€198.60`) | declined | Outbound remote lane (`+0.051`) |
| Mon 11:00 | `R00043` | `D02(0)` | `Kuopio[13]→Vantaa[434]` | `decline sa×4.00` (`243m > 180m`) | `sa`: **`1.023`** (`€127.88`) | declined | Same dealer/min as R00041, inbound `-33%`! |
| Mon 14:10 | `R00151` | `D01(3)` | `Hyvinkää[50]→Jyväskylä[21]` | `quote ne×1.57 wi×1.57` | `ne`: **`1.707`** (`€136.56`) | `-0.137` (`-€10.56`) | Outbound `no_sd`: left `€10.56` on table |
| Mon 14:10 | `R00153` | `D05(1)` | `Helsinki[434]→Lempäälä[60]` | `floor ne×2.52` (`list 61, ref 113`) | `ne`: **`1.434`** (`€87.47`) | `+1.086` (saved!) | Limit `€87.47 < ref €113`: floor saved `-€26`! |
| Tue 09:34 | `R00269` | `D11(0)` | `Raisio[103]→Lahti[33]` | `floor sa×1.62(€138) ne×1.63(€129)` | `sa`: **`1.898`** (`€161.33`) | `-0.278` (`-€23.33`) | `ne` floored compressed `sa`: left `€23`! |
| Tue 09:34 | `R00270` | `D14(0)` | `Raisio[103]→Helsinki[434]` | `quote sa×1.62(€112) ne×1.54` | `sa`: **`1.160`** (`€80.04`) | `+0.460` (`+€32`) | Inbound + `trust=0`: `1.25` floor (`€85.6`) & `mult` both miss `€26`-profit car! |
| Tue 09:34 | `R00271` | `D02(1)` | `Vantaa[434]→Lahti[33]` | `quote sa×1.62(€79) ne×1.54` | `sa`: **`1.434`** (`€70.27`) | `+0.186` (`+€8.73`) | `D01(12)` inflated `mult`, losing `€31` profit! |
| Tue 09:34 | `R00272` | `D01(12)` | `Hyvinkää[50]→Turku[103]` | `quote sa×1.74(€122) ne×1.66` | `sa`: **`1.926`** (`€134.82`) | `-0.186` (`-€12.82`) | High-trust `D01(12)` still underpriced `-€13`! |
| Wed 11:34 | `R00525` | `D01(25)` | `Jyväskylä[21]→Lahti[33]` | `decline sa×4.00` | `sa`: **`1.844`** (`€127.24`) | declined | `+25%` trust cushion holds `D01` at `1.84×` |
| Thu 09:24 | `R00660` | `D03(12)` | `Vantaa[434]→Lempäälä[60]` | `quote sa×1.48(€92) ne×1.41` | `sa`: **`1.488`** (`€92.26`) | `-0.008` (`-€0.26`) | Won right at dealer limit (`0.85×` fee) |
| Thu 09:24 | `R00662` | `D19(0)` | `Vantaa[434]→Ylivieska[1]` | `floor ne×1.54` (`sa` stripped) | `ne`: **`0.805`** (`€119.14`) | `+0.735` | Speed-sensitive dealer rejects `ne`-only |
| Fri 09:36 | `R00866` | `D03(16)` | `Vantaa[434]→Hyvinkää[50]` | `quote sa×1.54 ne×1.47` | `sa`: **`0.996`** (`€34.86`) | `+0.544` | Friday `-20%` price war + short-lane shift |
| Fri 09:36 | `R00871` | `D01(25)` | `Espoo[434]→Hyvinkää[50]` | `quote sa×1.74 ne×1.66` | `sa`: **`1.051`** (`€40.99`) | `+0.689` | Price war: `loss_streak_freeze=12` sits out |

### 2. Exact Monday `07:00` what-ifs on `dev-02` (`cp-demand-2` & `cp-demand-3`)
| Variant (from Monday 07:00 on `dev-02`) | Full-Week Margin | Δ vs Champion | Won | On-Time | What we concluded |
|---|---:|---:|---:|---:|---|
| Champion main line | €10,280.90 | €+0.00 | 259 | 95.0% | Baseline |
| `lane_neg075` (`w=0.75, only_neg=True, comp=2.0`) | **€11,601.80** | **+€1,320.90** | 281 | **96.8%** | Inbound lane discount replenishes hub & lifts on-time `+1.8%` |
| `inb_floor105` (`hub_inbound_fee_mult=1.05`) | **€11,057.20** | **+€776.30** | 264 | **97.0%** | Unlocking floored `inb_to_hub` cars adds `+€776` & `+2.0%` OT |
| `trust_center0045` (`trust_center_slope=0.0045`) | **€10,701.39** | **+€420.49** | 283 | **95.8%** | Zero-drift centered trust wins low-trust dealers & taxes `D01` |
| `sd_prem10` (`floored_sd_prem=0.10`) | **€10,415.00** | **+€134.10** | 251 | **96.0%** | Trims `-8` floor-compressed `same_day` cars, lifting margin & OT |
| Unthrottled stack (`w=0.75 + inb=1.05 + trust=0.0045`) | €11,104.00 | +€823.10 | **312** | 95.8% | Stacking unthrottled discounts overshoots `~280` driver ceiling |
| **Balanced 4-rule stack (`cp-demand-dev1` / `cp-demand-3`)** | **€11,178.99** | **+€898.09** | **293** | **96.2%** | Gentler weights (`w=0.55, inb=1.08, trust=0.003, sd_prem=0.10`) generalize across worlds |
| **Congestion-guarded stack (`cp-demand-dev2`)** | **€11,388.18** | **+€1,107.28** | **293** | **96.9%** | `inb=1.10, inbound_max_unstaffed=20` raises worst-world OT |

---

## What changed
In `src/spread_lab/policy.py` (all defaults neutral, reproducing Champion `d93271e` bit-for-bit with `Δmargin = €+0.00 ± 0.00` on `smoke`):
- Inlined `LANE_PICKUP`, `LANE_DELIVERY`, and `LANE_TERCILES` (empirical-Bayes shrunk log-price competitor lane effects fitted strictly out-of-sample on 64 `night+final` Level-8 worlds, 49,190 quotes; zero `dev` or `holdout` data).
- Added default-off `Params` fields:
  - `lane_prior_weight: float = 0.0`, `lane_pos_weight: float = -1.0`, `lane_prior_only_neg: bool = False`, `lane_prior_comp_slope: float = 0.0`: tilts `listPriceCents` on negative-effect (inbound) lanes by `clamp(exp(w * eff), 0.85, 1.15)` while shifting `Desk.learn()`'s target win rate by `-lane_prior_comp_slope * log(lane_mult)` so `self.mult` does not drift upward on outbound routes.
  - `hub_inbound_fee_mult: float = 0.0`: on Inbound-to-Hub requests (`pickup_supply < 200` and `deliv_supply >= 200`, where actual booked fees average `0.925 × ref` and late rate is `1.17%`), uses `(referenceFeeCents * hub_inbound_fee_mult) / (1 - min_margin_frac)` as the price clamp while **preserving `floored = True` whenever `price < base_floor`** so `Desk.learn()` is never polluted by high-`ref/list` losses.
  - `inbound_max_unstaffed: int = 0`: optional congestion guard pausing negative `lane_mult` and `hub_inbound_fee_mult` whenever total active unstaffed orders exceed `inbound_max_unstaffed`.
  - `trust_center_slope: float = 0.0`, `trust_ema_alpha: float = 0.05`: zero-drift centered trust multiplier `exp(trust_center_slope * (dealer_trust[d] - trust_ema))` at Level 8, rebuilt deterministically in `rejoin()`.
  - `floored_sd_prem: float = 0.0`: when both `same_day` and `next_day` are quoted and `next_day` hits its floor, enforces `prices["same_day"] >= round(prices["next_day"] * (1 + floored_sd_prem))`.
- Added telemetry counters (`inb_floor_saved`, `won_inb_floor_saved`, `sd_prem_lifted`, `inbound_paused_congested`, `lane_quotes/wins/margin/late_{low,mid,high}`, `quotes/wins_trust_{low,high}`).

Best command (`cp-demand-dev1`):
```sh
uv run lab eval -s lane_prior_weight=0.55 -s lane_prior_only_neg=True -s lane_prior_comp_slope=2.2 -s hub_inbound_fee_mult=1.08 -s trust_center_slope=0.003 -s floored_sd_prem=0.10 --name cp-demand-dev1
```

## Results (level 8, normal instrument, paired vs Champion `d93271e`)
| set | run folder | mean margin | min margin | Δmargin ± SE | t | better/worse | on-time min (under 92%) | mean OT (Δ) | SAFE |
|---|---|---:|---:|---:|---:|---|---:|---:|---|
| smoke (noop) | `20261114-092324-cp-demand-noop` | €10,816.98 | €7,487.67 | €+0.00 ± 0.00 | — | 0 / 0 | 94.4% (0/4) | 96.0% (+0.00%) | yes |
| smoke S1 (`inb=1.05`) | `20261114-092846-cp-demand-s1-inbfloor` | €11,132.92 | €8,163.23 | +€315.94 ± 249.45 | +1.27 | 3 / 1 | 95.3% (0/4) | 96.5% (+0.50%) | yes |
| smoke S2 (`trust=0.0045`) | `20261114-093033-cp-demand-s2-trustcenter` | €11,049.75 | €8,104.03 | +€232.77 ± 198.17 | +1.17 | 3 / 1 | 94.9% (0/4) | 96.0% (+0.02%) | yes |
| smoke S3 (`lane+inb+sd`) | `20261114-093435-cp-demand-s3-lane-inb-sdprem` | €11,419.99 | €7,822.00 | +€603.01 ± 292.02 | +2.06 | 3 / 1 | 93.9% (0/4) | 96.4% (+0.38%) | yes |
| smoke S4 (balanced 4-rule) | `20261114-093611-cp-demand-s4-full-balanced` | €11,846.66 | €8,616.50 | **+€1,029.68 ± 49.70** | **+20.72** | **4 / 0** | 94.2% (0/4) | 96.9% (+0.89%) | yes |
| **dev 1 (balanced 4-rule)** | `20261114-093823-cp-demand-dev1` | **€11,379.93** | **€8,514.62** | **+€495.05 ± 137.14** | **+3.61** | **13 / 3** | **93.7% (0/16)** | 96.9% (-0.08%) | **yes** |
| **dev 2 (`+ inb=1.10, max_u=20`)** | `20261114-094223-cp-demand-dev2` | **€11,257.34** | **€7,913.03** | **+€372.46 ± 152.49** | **+2.44** | **13 / 3** | **94.4% (0/16)** | 97.2% (+0.21%) | **yes** |
| **night-32 (fresh 32 worlds, dev1)** | `20261114-095118-cp-demand-night32` | **€11,376.48** | **€5,712.94** | — (unpaired 32w) | — | — | **92.7% (0/32)** | 97.1% | **yes** |
| **promote gate: holdout (dev1)** | `promote-20261114-100546` | €11,624.75 | €5,160.52 | -€79.41 ± 125.32 | -0.63 | 8 / 8 | **95.4% (0/16)** | 97.3% (-0.24%) | **yes** |
| **promote gate: Wed 12:00 restart** | `dev-01 --restart-at 3600` | €8,256.37 | — | +€768.70 vs champ | — | — | **94.8%** | 94.8% | **yes** |

### Telemetry and ledger breakdown on 16 dev worlds (mean per world)
| Metric / Counter | Champion (`d93271e`) | **Dev 1 (`cp-demand-dev1`)** | **Dev 2 (`cp-demand-dev2`)** |
|---|---:|---:|---:|
| Mean margin (€/wk) | €10,884.88 | **€11,379.93 (+€495.05)** | **€11,257.34 (+€372.46)** |
| Worst-world margin (€/wk) | €7,487.67 | **€8,514.62 (+€1,026.95)** | **€7,913.03 (+€425.36)** |
| Worst-world on-time % (worlds < 92%) | 94.33% (0/16) | **93.68% (0/16)** | **94.43% (0/16)** |
| Won orders / wk (`sd` / `nd` / `w3d`) | 280.25 (105.1 / 164.9 / 13.1) | **300.56 (112.1 / 178.4 / 12.9)** | **296.56 (109.5 / 177.1 / 13.0)** |
| Ledger `revenue` (€/wk) | +€30,474.48 | **+€32,110.99 (+€1,636.51)** | +€31,761.46 (+€1,286.98) |
| Ledger `driver_fee` (€/wk) | -€19,073.53 | **-€20,203.37 (-€1,129.84)** | -€19,976.44 (-€902.91) |
| Ledger `late_refund` (€/wk) | -€366.72 | -€399.08 | -€385.40 |
| Ledger `undelivered_penalty` (€/wk) | -€57.71 | **-€43.34 (+€14.37)** | **-€44.91 (+€12.80)** |
| Ledger `failed_visit` (€/wk) | -€21.52 | **-€7.22 (+€14.30)** | **-€11.50 (+€10.02)** |
| `inb_floor_saved` / `won_inb_floor_saved` | 0.0 / 0.0 | **57.19 / 20.50** | **54.44 / 18.19** |
| `sd_prem_lifted` | 0.0 | **51.38** | **52.44** |
| `lane_wins` (`low` / `mid` / `high`) | — | **87.4 / 88.6 / 127.3** | **84.2 / 88.1 / 127.2** |
| `lane_margin` (€: `low` / `mid` / `high`) | — | **€2,301 / €2,965 / €6,524** | **€2,291 / €2,912 / €6,512** |
| Tue–Fri centered trust win % (`low` vs `high`) | 28.0% vs 50.0% (64w ref) | **31.1% (`57.1/183.8`) vs 51.6% (`93.9/182.2`)** | **31.3% vs 50.0%** |

On `dev1`, the `+20.31` marginal won orders/week generate **`€80.58/order` in marginal revenue** for **`€55.63/order` in marginal driver fee (`69.0%`)**, lifting mean margin to **`€11,379.93/wk` (`+€495.05 ± 137.14, t = 3.61`)** and lifting the worst dev world by **`+€1,026.95`** (`€7,487.67 -> €8,514.62`), while staying 100% SAFE across all 48 tested worlds (`16/16` dev + `32/32` fresh `night` worlds, `0/48` under `92%`). If strict worst-world on-time parity (`>= champion - 0.5%`) is needed on holdout, `dev2` (`hub_inbound_fee_mult=1.10, inbound_max_unstaffed=20`) achieves **`+€372.46 ± 152.49` (`t = 2.44`, 13/16 seeds)** with **`94.43%` min on-time (`+0.10%` above champion)**.

## Promotion gate (`scripts/promote.sh`) & synthesis for the lead
Running `scripts/promote.sh` once on `dev1` passed `dev` (`+€495.05 ± 137.14, t = 3.61`), passed the Wednesday `12:00` live restart check (`dev-01`: `€8,256.37`, `94.8%` on-time, `ranked=True`), and **lifted holdout worst-world on-time by `+1.31 pp` (`94.08% -> 95.39%`, `0/16` under `92%`)**, but was refused by the holdout margin gate at `Δmargin = -€79.41 ± 125.32` (`8/8` split) because holdout starts higher in volume (`289.8 -> 307.6` won/wk, `402` won on `hold-15`) where unguarded volume hits the `~300`-order driver ceiling. Per protocol ("never tune on holdout"), we did not re-run `promote.sh` on `dev2` (`inbound_max_unstaffed=20`, `dev Δ +€372.46 ± 152.49, t = 2.44`, `min OT 94.43%`). Pairing `dev2` (or `dev1`) with the co-play chains/staffing improvements that raise the driver ceiling is a prime candidate for the lead's merge wave.

## Verdict
**needs work / pair with staffing-ceiling stack (`promote.sh` gate refused holdout Δ `-€79 ± 125` on unguarded `dev1`; `dev2` guarded ready for lead)** — On `dev`: **SAFE (`0/16` < 92%), Δmargin `+€495.05 ± 137.14` (`t = 3.61`, 13/16 better, min OT `93.7%`)** for `dev1` and **`+€372.46 ± 152.49` (`t = 2.44`, 13/16 better, min OT `94.4%`)** for congestion-guarded `dev2`; **SAFE across 64/64 total worlds (`16 dev + 32 night + 16 holdout`, `0/64` < 92%, holdout min OT `95.4%`)**.
