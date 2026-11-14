# d14-05-eligible-supply: Combine refined `eligible_supply` (`eligible_min_supply_mult=0.75`, `eligible_backlog=True`) with Sweep 61/63/66 parameters

- **Agent / branch / commit:** gemini · `exp/gemini-d14-05-eligible-supply` · `a0825ea`
- **Date:** 2026-11-14 09:05 UTC
- **Idea from:** `experiments/IDEAS.md` #23b (`eligible_supply`) + Sweeps 61 (`n-slack-steep-feeopen`), 63 (`n-slack130-steep15`), and 66 (`n-dlr01-plr06-fine`)

## Why we tried it
In `n14-06262-signals-on-v3`, counting only eligible drivers (`rating >= 4.8 and completedGigs >= 50` for premium cars; manual-licence drivers for manual-gearbox notes) cut late orders on Champion v3 (`128 -> 111`) and lifted worst-world on-time by `+0.97 pp` (`94.38% -> 95.35%`), while leaving standalone margin flat (`Δmargin €-50.63 ± 146.36`) because the extra tail cushion was not cashed in and medium-hub premium cars were over-declined.

Before running practice worlds, slot-free reveal sizing across five finished level-8 worlds (`dev-01..04`, `dev-07`) uncovered two exact structural facts:
1. **Why `eligible_min_supply_mult=1.0` over-declined hubs:** Only `8.4%–8.8%` of roster drivers are experienced (`39–70` per world). On `dev-04`, even Helsinki/Vantaa/Espoo/Hyvinkää had only `19–20` experienced drivers within 55 km (`< min_supply = 22`), so `mult = 1.0` declined **100% of premium cars nationwide** on `dev-04`, and declined Tampere/Lempäälä (`17` experienced drivers out of `186` total) on `dev-07`. Meanwhile, across all 5 revealed worlds, **all 5 late premium cars (`5/5`) were `same_day`**, whereas **`0/48` slow (`next_day`/`within_3_days`) premium cars were late** (averaging `+€38/order` in `e55 >= 17`). Setting `eligible_min_supply_mult=0.75` (`gate_min = 16.5`) retains `dev-04` Helsinki and `dev-07` Tampere while still declining thin regional towns (`e55 = 0..10`) and still stripping `same_day` when `e30 < same_day_min_supply (50)`.
2. **Spurious regular-backlog declines (`eligible_backlog`):** In `n14-06262`, `backlog_cap = max(2, 0.06 * gate_supply_exp)` (`2.0–2.3` cars in Helsinki) was compared against `backlog_near(pickup)` summed over **all** car types (including regular non-premium cars served by `330+` drivers), spuriously declining `165–166` Helsinki/hub premium quotes across 16 dev seeds (`prem_declined_elig_backlog = 166`). Matching `backlog_near` to eligible-competing orders (`eligible_backlog=True`, while keeping the raw total backlog cap active) eliminates all 166 spurious declines.

## What changed
Merged `origin/exp/gemini-n14-06262-signals-on-v3` onto `main` (which is Champion v4 = Champion v3 + `late_fee_open=1.0` from `51d1be6`, dev mean `€10,884.88`) and added two neutral-default `Params` fields and eligibility decline counters in `src/spread_lab/policy.py`:
- `eligible_min_supply_mult: float = 1.0` — scales `gate_min` (and `ext_ring_min_supply` / `return_hub_min_supply`) when `eligible_supply=True` and the request requires `experienced` or `manual` licence.
- `eligible_backlog: bool = False` — when `True` with `eligible_supply=True`, checks `backlog_near` over orders/quotes competing for the same eligibility requirement against `eligible_cap` while checking total `backlog_near` against `raw_cap`.
- Counters in `self.stats`: `prem_Manual_declined_elig` (broken down into `prem_declined_elig_gate`, `prem_declined_elig_backlog`, `prem_declined_elig_opts`), `prem_q`, `prem_won`, `prem_late`, `manual_q`, `manual_won`, `manual_late`.

Run with:
`uv run lab eval -s eligible_supply=True -s eligible_min_supply_mult=0.75 -s eligible_backlog=True -s day_start=360 -s fee_warn=1.45 -s fee_step_min=25 -s steep_open=1.50 -s min_slack_min=135 -s price_lr=0.065 -s dealer_lr=0.009 --name elig075-eb-ds360-s135-plr065-dev`

## Results (level 8, vs champion, paired)
Note on baseline: `main` (`1a2075b`) promoted `late_fee_open=1.0` (`51d1be6`) on top of Champion v3, raising the champion's 16-seed dev mean from `€10,529.42` (`on-time min 94.38%`, `128` late) to **`€10,884.88`** (`on-time min 94.33%`, `136` late, `0/16` under `92%`; smoke mean `€10,816.98`, `on-time min 94.38%`, `44` late). All paired deltas below are against this current `€10,884.88` champion.

| set | run folder | flags (on top of champion) | mean margin | Δmargin ± SE | t | better/worse | on-time min | <92% | SAFE |
|---|---|---|---|---|---|---|---|---|---|
| smoke | `20261114-085402-elig-sweep-noop` | defaults (no-op check) | €10,816.98 | €+0.00 ± 0.00 | — | 0/0 | 94.38% | 0/4 | yes |
| smoke | `20261114-085454-s1-elig-ds360` | `elig=T, ds=360, fw=1.45, fs=25, so=1.50` | €11,426.11 | €+609.13 ± 200.52 | +3.04 | 4/0 | 96.88% | 0/4 | yes |
| smoke | `20261114-085503-s2-elig075-ds360` | `s1` + `elig_mult=0.75` | €11,533.74 | €+716.76 ± 185.50 | +3.86 | 4/0 | 95.68% | 0/4 | yes |
| smoke | `20261114-085531-s3-elig075-ds360-s135-plr065` | `s2` + `slack=135, plr=0.065, dlr=0.009` | €11,562.08 | €+745.10 ± 180.77 | +4.12 | 4/0 | 94.70% | 0/4 | yes |
| smoke | `20261114-085540-s4-elig075-ds360-s135-ms20` | `s3` + `min_supply=20` | €11,591.99 | €+775.01 ± 57.79 | +13.41 | 4/0 | 92.88% | 0/4 | yes |
| smoke | `20261114-085639-s5-elig075-eb-ds360-s135-plr065` | `s3` + `eligible_backlog=True` | €11,624.96 | €+807.98 ± 231.30 | +3.49 | 4/0 | 95.06% | 0/4 | yes |
| smoke | `20261114-090254-s6-elig075-eb-ds360-keeprescue-s135-plr065` | `s5` keeping `fw=1.60, so=1.80` | €11,615.74 | €+798.76 ± 223.88 | +3.57 | 4/0 | 95.08% | 0/4 | yes |
| **dev** | `20261114-085803-elig075-ds360-dev` | `s2` (`elig=T, mult=0.75, ds=360, fw=1.45, fs=25, so=1.50`) | €11,046.01 | €+161.13 ± 140.79 | +1.14 | 10/6 | 93.59% | 0/16 | yes |
| **dev** | `20261114-085903-elig075-ds360-s135-plr065-dev` | `s3` (`s2` + `slack=135, plr=0.065, dlr=0.009`) | €11,039.61 | €+154.73 ± 131.72 | +1.17 | 9/7 | 93.96% | 0/16 | yes |
| **dev** | **`20261114-090042-elig075-eb-ds360-s135-plr065-dev`** | **`s5` (`s3` + `eligible_backlog=True`)** | **€11,058.61** | **€+173.72 ± 149.32** | **+1.16** | **10/6** | **93.57%** | **0/16** | **yes** |
| **dev** | `20261114-090321-elig075-eb-ds360-keeprescue-s135-plr065-dev` | `s6` (`s5` keeping `fw=1.60, so=1.80`) | €10,892.28 | €+7.40 ± 158.57 | +0.05 | 9/7 | **94.93%** | 0/16 | yes |

### Counter & ledger diagnostics (16 dev seeds)
| Run | Won (tot / mean) | Total late (tot / mean) | `prem_Manual_declined_elig` (`gate` / `backlog` / `opts`) | `prem_q` / `prem_won` / `prem_late` | `manual_q` / `manual_won` / `manual_late` | Min world margin | Mean on-time |
|---|---|---|---|---|---|---|---|
| Champion (`v3 + late_fee_open=1.0`) | 4,484 / 280.2 | 136 / 8.50 | — | ~640 / ~276 / ~16* | ~132 / ~56 / ~1* | €7,487.67 | 96.97% |
| `elig075-ds360-dev` (`s2`) | 4,364 / 272.8 | 130 / 8.12 | 412 (204 / 165 / 43) | 242 / 72 / 3 | 124 / 55 / 1 | €7,703.27 | 97.10% |
| `elig075-ds360-s135-plr065-dev` (`s3`) | 4,427 / 276.7 | 131 / 8.19 | 414 (204 / 166 / 44) | 240 / 75 / **1** | 125 / 58 / 1 | €7,714.39 | 97.08% |
| **`elig075-eb-ds360-s135-plr065-dev` (`s5`)** | **4,462 / 278.9** | **136 / 8.50** | **266 (204 / 0 / 62)** | **384 / 128 / 9** | **126 / 60 / 1** | **€7,954.53** | **96.99%** |
| `elig075-eb-ds360-keeprescue-s135-plr065-dev` (`s6`) | 4,499 / 281.2 | **121 / 7.56** | 266 (204 / 0 / 62) | 384 / 126 / 7 | 126 / 57 / 1 | **€8,089.96** | **97.35%** |

*(\*Champion dev baseline ran prior to adding `prem_*`/`manual_*` counters; smoke no-op had `prem = 161/69/4` and `man = 33/14/0` across 4 seeds, which dropped to `prem_late = 0/34` across all 6 active smoke runs `s1..s6`.)*

### Key findings
1. **Why Sweep 61's `+€399` shrank to `+€161..+€174` on current `main`:** Sweep 61 (`day_start=360, fee_warn=1.45, fee_step_min=25, steep_open=1.50`) was measured on Champion v3 (`€10,529.42`, `late_fee_open=0.0`), where `steep_open=1.50` lowered fees on **both** pre-deadline warned orders and post-deadline already-lost orders. After `51d1be6` promoted `late_fee_open=1.0` (`+€355 ± 169` to `€10,884.88`), lost-order fees were already cut to `1.0x–1.3x` (`fee_lost` `€1,096/world`), absorbing `~€225/world` of Sweep 61's gain. Against Champion v3 (`€10,529.42`), `s5` (`€11,058.61`) is **`+€529.19/world`**; against Champion v4 (`€10,884.88`), the incremental gain is **`€+173.72 ± 149.32 (t = +1.16, 10/16 better)`**.
2. **Pre-deadline fee vs tail-safety trade-off (`s5` vs `s6`):** Comparing `s5` (`fee_warn=1.45, steep_open=1.50`) against `s6` (`fee_warn=1.60, steep_open=1.80`) isolates the exact effect of lowering pre-deadline warning fees once `late_fee_open=1.0` is active: `fee_warn=1.45, steep_open=1.50` saves `+€166.33/world` in pre-deadline driver fees (`€11,058.61` vs `€10,892.28`) in exchange for `15` fewer warning rescues (`136` vs `121` late orders, worst-world on-time `93.57%` vs `94.93%`). Conversely, `s6` (`eligible_supply=True, eligible_min_supply_mult=0.75, eligible_backlog=True, day_start=360, fee_step_min=25, min_slack_min=135, price_lr=0.065, dealer_lr=0.009`) wins slightly more volume (`281.2` vs `280.2/world`), cuts late orders by **`-11.0%` (`136 -> 121`)**, lifts worst-world on-time by **`+0.60 pp` (`94.33% -> 94.93%`)**, and raises worst-world margin by **`+€602` (`€7,488 -> €8,090`)** at mean-margin parity (`+€7.40`).
3. **`eligible_min_supply_mult=0.75` + `eligible_backlog=True` fixes both over-declining bugs in `n14-06262`:** On smoke, `mult=0.75` improved over `mult=1.0` by `+€107.63/world` (`s2` vs `s1`), and `eligible_backlog=True` eliminated all `166` spurious regular-backlog declines on dev (`prem_won` `75 -> 128`), lifting mean margin from `€11,039.61` (`s3`) to `€11,058.61` (`s5`) and lifting worst-world margin from `€7,714` to `€7,955`.

## Verdict
**needs work (positive `+€174`, SAFE, `10/16` better, but `t = 1.16 < 2.0` on top of `late_fee_open=1.0`)** — Because `main` already promoted `late_fee_open=1.0` (`+€355` over v3), most of Sweep 61's `steep_open=1.50` lost-order fee saving is already in the champion; the combined stack (`s5`) reaches `€11,058.61` (`Δmargin €+173.72 ± 149.32, t = 1.16, 10/16 better`, worst on-time `93.57%`, `0/16` under `92%`, SAFE), while keeping full warning rescue (`s6`) delivers a pure tail-safety upgrade (`94.93%` worst on-time, `121` vs `136` late, `+€602` worst-world margin, `Δmargin €+7.40 ± 158.57`).
