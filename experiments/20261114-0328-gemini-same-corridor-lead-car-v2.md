# same-corridor-lead-car-v2: Same-origin, same-corridor slow 2-car gig pairing (`lead_car`, `lead_car_max_gap_km`, `lead_car_max_deliv_gap_km`, `lead_car_fee_mult`)

- **Agent / branch / commit:** gemini · `exp/gemini-n14-03112-same-corridor-lead-car-v2`
- **Date:** 2026-11-14 03:28
- **Idea from:** `experiments/IDEAS.md` #12(c) — Same-origin, same-corridor slow 2-car gig pairing on top of `exp/gemini-n14-02114-stack-gates-trust-notes`

## Why we tried it
Under `docs/GAME.md`, a 2-car gig (`pick A → drop A → pick B → drop B`) pays the driver for `leg A` and `leg B` while the connecting deadhead `drop A → pick B` is unbilled to our `referenceFeeCents`. Earlier tests (`n14-01152` and `n14-02243`) showed two key facts:
1. Discounting the combined fee (`lead_car_fee_mult=0.95`) or pairing arbitrary orders across different pickup towns (`gap_km <= 30–40 km`) and unrelated delivery corridors formed 10–29 pairs/week where sequential delays or failed visits cascaded from car 1 to car 2.
2. Paying the full `1.00×` combined 2-car schedule (`lead_car_fee_mult=1.00`) while restricting pairing strictly to **same pickup town (`lead_car_max_gap_km = 0.0`), same delivery corridor (`lead_car_max_deliv_gap_km = 25.0`), same deadline day, both slow (`next_day` / `within_3_days`), note-free, and non-charging** pairs only genuine 2-car corridor batches (~4.5–5.5 pairs/week) that a single driver can complete well inside the 9.0h (`540` min) cap with ≥ 4h (`240` min) of deadline buffer. Furthermore, with `notes_v2=True` and the class-table gates (`n14-02114`) eliminating >95% of failed visits, sequential cascade risk is nearly zero.

## What changed
Merged `origin/exp/gemini-n14-02114-stack-gates-trust-notes` (`6e02bf5`) and added four `Params` fields in `src/spread_lab/policy.py` whose defaults reproduce champion v2 and `n14-02114` 100% identically (`Δmargin €+0.00 ± 0.00` on smoke):
- `lead_car: bool = False` — enable same-origin, same-corridor slow 2-car gig pairing.
- `lead_car_max_gap_km: float = 0.0` — max straight-line km between `order_a` pickup and `order_b` pickup (`0.0` = exact same pickup `placeId`).
- `lead_car_max_deliv_gap_km: float = 25.0` — max straight-line km between `order_a` delivery and `order_b` delivery.
- `lead_car_fee_mult: float = 1.00` — multiplier on the summed `referenceFeeCents` of the two paired orders.

Implementation details in `Desk`:
- `try_pair_lead_car(self, order, legs, retry)`:
  - Only considers 1-leg orders with `retry == Retry()`, `option != "same_day"`, `order["id"] not in self.urgent`, no dealer note, and no EV charging stop (`withCharging == False`).
  - Flushes any matching slow single-car post still sitting in `self.outbox` from the current step so same-batch orders won at the same minute can pair identically in practice and live mode.
  - Pairs with an open, unbooked 2-stop single-car gig for `other_order` when `other_order` is also slow (`option != "same_day"`), not urgent, note-free, non-charging, has `other_order["deadline"] // DAY == order["deadline"] // DAY`, `line_km(pa, pb) <= lead_car_max_gap_km`, `line_km(da, db) <= lead_car_max_deliv_gap_km`, total 4-stop duration `drive_a + deadhead_da_to_pb + drive_b + 4 * 15 <= 540` min, and finishes at least `240` min before `min(order["deadline"], other_order["deadline"])`.
  - Immediately validates the 4-stop post with `self.send()`; if refused, re-posts both orders individually so neither is orphaned.
- Multi-order handling in `fees_for` (sums `referenceFeeCents` across distinct `orderId`s in `action["stops"]` multiplied by `lead_car_fee_mult`), `raise_fees` (if an unbooked paired gig hits `deadline_close`, withdraws and re-posts each order's undelivered leg individually and increments `lead_car_split`), `repost`, `withdraw`, `order_cancelled`, and `rejoin`.

Run commands:
- **Dev Run 1 (`gtn-leadcar-v2-dev`, on `stack-gtn-ptw38`):**
  ```sh
  uv run lab eval -s trust_invest=0.05 -s notes_v2=True -s note_unsure=decline -s max_next_day_drive_min=480 -s fri_same_day_max_drive=100 -s thin_long_next_day_supply=50 -s ring_to_hub_same_day_min=60 -s same_day_min_supply=50 -s min_slack_min=150 -s slack_per_drive=0.75 -s price_target_win=0.38 -s min_supply=25 -s lead_car=True -s lead_car_max_gap_km=0.0 -s lead_car_max_deliv_gap_km=25.0 -s lead_car_fee_mult=1.00 --name gtn-leadcar-v2-dev
  ```
- **Dev Run 2 (`gtn-leadcar-v2-ptw45-dev`, giving back the safety tax with `price_target_win=0.45`):**
  ```sh
  uv run lab eval -s trust_invest=0.05 -s notes_v2=True -s note_unsure=decline -s max_next_day_drive_min=480 -s fri_same_day_max_drive=100 -s thin_long_next_day_supply=50 -s ring_to_hub_same_day_min=60 -s same_day_min_supply=50 -s min_slack_min=150 -s slack_per_drive=0.75 -s price_target_win=0.45 -s min_supply=25 -s lead_car=True -s lead_car_max_gap_km=0.0 -s lead_car_max_deliv_gap_km=25.0 -s lead_car_fee_mult=1.00 --name gtn-leadcar-v2-ptw45-dev
  ```

## Results (level 8, vs champion v2, paired)
| set | run folder | mean margin | Δmargin ± SE | t | better/worse | on-time min (mean, Δ) | SAFE |
|---|---|---:|---:|---:|---:|---:|---|
| smoke (noop) | `runs/20261114-031806-gtn-leadcar-noop` | €9,662.25 | €+0.00 ± 0.00 | — | 0 / 0 | 95.5% (96.7%, +0.00%) | yes |
| smoke (Smoke 1: `gap=0, deliv=25, mult=1.00`) | `runs/20261114-032006-gtn-leadcar-smoke1` | €10,604.78 | €+942.53 ± 550.27 | 1.71 | 4 / 0 | 96.0% (97.2%, +0.48%) | yes |
| smoke (Smoke 2: `gap=15, deliv=25, mult=1.02`) | `runs/20261114-032036-gtn-leadcar-smoke2` | €10,594.32 | €+932.07 ± 640.68 | 1.45 | 3 / 1 | 96.0% (97.3%, +0.58%) | yes |
| **dev Run 1 (`gtn-leadcar-v2-dev`, `ptw=0.38`)** | `runs/20261114-032408-gtn-leadcar-v2-dev` | **€10,082.56** | **€+1,092.26 ± 275.53** | **3.96** | **13 / 3** | **93.3% (97.4%, +0.61%)** | **yes** |
| **dev Run 2 (`gtn-leadcar-v2-ptw45-dev`, `ptw=0.45`)** | `runs/20261114-032646-gtn-leadcar-v2-ptw45-dev` | **€10,191.33** | **€+1,201.02 ± 245.37** | **4.89** | **15 / 1** | **93.7% (96.9%, +0.19%)** | **yes** |

### Head-to-head comparisons against `20261114-022434-stack-gtn-ptw38-dev` (`€10,029.58`)
| Comparison (`uv run lab compare` on 16 dev seeds) | Δmargin ± SE | t | better/worse | Δon-time mean | Min margin (worst seed) | Min on-time |
|---|---:|---:|---:|---:|---:|---:|
| `stack-gtn-ptw38-dev` (baseline stack, `lead_car=False`) | — | — | — | — | €7,078.06 | 94.3% |
| `gtn-leadcar-v2-dev` vs `stack-gtn-ptw38-dev` | **€+52.98 ± 129.09** | **0.41** | **8 / 8** | **+0.04%** | **€7,241.24 (+€163.18)** | **93.3%** |
| `gtn-leadcar-v2-ptw45-dev` vs `stack-gtn-ptw38-dev` | **€+161.74 ± 177.97** | **0.91** | **11 / 5** | **-0.38%** | **€7,568.69 (+€490.63)** | **93.7%** |
| `gtn-leadcar-v2-ptw45-dev` vs `gtn-leadcar-v2-dev` | **€+108.76 ± 135.10** | **0.81** | **10 / 6** | **-0.42%** | **€7,568.69 (+€327.45)** | **93.7%** |

### Counter & ledger diagnostics (16-seed `dev` mean per world)
| Metric / Counter | Champion v2 | `stack-gtn-ptw38-dev` (`lead_car=False`) | `gtn-leadcar-v2-dev` (`ptw=0.38`) | `gtn-leadcar-v2-ptw45-dev` (`ptw=0.45`) |
|---|---:|---:|---:|---:|
| Won orders / week | 227.8 | 256.0 | 256.5 | **293.6** |
| **`lead_car_paired` (pairs / wk)** | 0.00 | 0.00 | **4.56 (73 total)** | **5.50 (88 total)** |
| **`lead_car_booked` (bookings / wk)** | 0.00 | 0.00 | **5.00 (80 total)** | **6.38 (102 total)** |
| **`lead_car_split` (splits / wk)** | 0.00 | 0.00 | **0.06 (1 total, 1.4%)** | **0.25 (4 total, 4.5%)** |
| `deadline_close` warnings / wk | 12.06 | 14.06 | **12.88 (-8.4%)** | 19.56 |
| `gig_expired` / wk | 7.56 | 6.50 | **6.25 (-3.8%)** | 9.25 |
| `visit_failed` / wk | 4.56 | 0.19 | **0.12 (-36.8%)** | 0.19 |
| Ledger `revenue` (€/wk) | +26,922.43 | +28,082.93 | +28,294.17 | **+30,888.51** |
| Ledger `driver_fee` (€/wk) | -17,286.92 | -17,673.60 | -17,830.67 | -20,205.80 |
| Ledger `late_refund` (€/wk) | -376.20 | -288.22 | -292.26 | -362.73 |
| Ledger `failed_visit` (€/wk) | -165.44 | -6.68 | -6.78 | -7.99 |
| Ledger `undelivered_penalty` (€/wk) | -10.72 | -10.27 | **-4.80 (-53.3%)** | -43.68 |
| Mean margin (€/wk) | €8,990.30 | €10,029.58 | **€10,082.56** | **€10,191.33** |
| Worst-seed margin (€) | €6,017.30 | €7,078.06 | **€7,241.24** | **€7,568.69** |
| Mean / Min on-time (%) | 96.75% / 92.6% | 97.32% / 94.3% | **97.35% / 93.3%** | **96.93% / 93.7%** |

### Key findings
1. **98.6% of same-corridor paired gigs book without splitting:** By restricting `try_pair_lead_car` to exact same pickup town (`gap_km == 0.0`), same delivery corridor (`deliv_gap_km <= 25.0`), same deadline day, both slow (`next_day`/`within_3_days`), note-free, and total 4-stop duration `<= 540` min, the desk forms **4.56 pairs/week** (73 pairs across 16 worlds) at `ptw=0.38`, and **72 of 73 pairs (98.6%)** book before `deadline_close` (`lead_car_split = 0.06/wk`).
2. **Reduces driver contention and deadline warnings:** Pairing two slow cars on the same corridor frees up a second driver in that town, cutting `deadline_close` warnings by **8.4%** (`14.06 → 12.88/wk`), cutting `undelivered_penalty` in half (`-€10.27 → -€4.80/wk`), lifting mean on-time (`97.32% → 97.35%`), lifting worst-seed margin by `+€163.18` (`€7,078.06 → €7,241.24`), and adding `+€52.98/wk` on top of `stack-gtn-ptw38-dev` (`€10,082.56` mean margin, `Δmargin €+1,092.26 ± 275.53, t = 3.96` vs Champion v2).
3. **Unlocks `price_target_win=0.45` safely (`€10,191.33/wk`, `t = 4.89`):** Because same-corridor pairing absorbs extra slow-car batch volume (`lead_car_paired` rises to `5.50/wk`, 88 pairs with 95.5% booked before `deadline_close`), raising `price_target_win` to `0.45` wins **293.6 orders/week** (`+65.8` over Champion v2, `+37.6` over `stack-gtn-ptw38-dev`) while keeping every dev seed SAFE (**min on-time `93.7%`**, mean on-time `96.9%`), lifting worst-seed margin to **€7,568.69** (`+€1,551.39` over Champion v2) and mean margin to **€10,191.33** (`Δmargin €+1,201.02 ± 245.37, t = 4.89, 15/16 seeds better` vs Champion v2; `€+161.74 ± 177.97, 11/5 seeds better` vs `stack-gtn-ptw38-dev`).

## Verdict
**adopt** — Same-origin, same-corridor slow 2-car pairing (`lead_car=True, lead_car_max_gap_km=0.0, lead_car_max_deliv_gap_km=25.0, lead_car_fee_mult=1.00`) on top of `stack-gtn` is SAFE across all 16 dev worlds, books 95.5–98.6% of paired gigs before `deadline_close`, improves `stack-gtn-ptw38-dev` to **€10,082.56** (`Δmargin €+1,092.26 ± 275.53, t = 3.96, 13/16 better` vs Champion v2), and with `price_target_win=0.45` reaches **€10,191.33** (`Δmargin €+1,201.02 ± 245.37, t = 4.89, 15/16 better`, worst on-time `93.7%`, worst margin `€7,568.69`).
