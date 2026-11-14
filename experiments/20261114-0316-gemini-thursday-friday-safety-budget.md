# n14-02464-thursday-friday-safety-budget: Late-week (Thu–Fri) on-time budget & Friday repair ballast on top of `stack-gates-trust-notes`

- **Agent / branch / commit:** gemini · `exp/gemini-n14-02464-thursday-friday-safety-budget` · `6e02bf5`
- **Date:** 2026-11-14 03:16
- **Idea from:** `IDEAS.md` #10 (`n14-06-budget` near-miss refinement: `budget_target`, `budget_start_day=3`, `ballast_discount`) on top of `origin/exp/gemini-n14-02114-stack-gates-trust-notes`

## Why we tried it
Earlier tonight, `n14-06-budget` (`IDEAS.md` #10: projecting on-time share from open orders and discounting safe slow ballast options when tight) achieved a promising near-miss on raw Champion v2 (`Δmargin €+93.76 ± 64.88, t = 1.45, worst on-time 94.38% SAFE`), repairing the champion's worst dev seed `dev-10` by `+1.45%` on-time and `+€496.51` margin, and lifting worst-world on-time to `94.94%` even under aggressive intake (`price_target_win=0.42, min_supply=20`).

However, in `n14-01153-stack-trust-slack-budget`, stacking `budget_target=0.95` with `trust_invest=0.05` underperformed `trust_invest=0.05` alone for two clear reasons:
1. **Mon–Wed double-discounting:** `budget_target=0.95` was active on Mon–Wed (`day <= 2`), applying a ballast discount on top of `trust_invest=0.05` when the denominator of won orders was small and noisy.
2. **Threshold too high (`0.95`) on already-safe worlds:** With `n14-02114-stack-gates-trust-notes` already achieving `97.3%–98.3%` mean on-time, a budget guard should have **zero effect (`0` quotes touched) on safe worlds** and only step in on Thursday–Friday (`day >= 3`, after `trust_invest=0.05` has completely finished at `day <= 2`) when a tough world has projected on-time below `0.945`–`0.95`.

Restricting the budget mechanism to `budget_start_day = 3` (Thu–Fri) eliminates all overlap with Mon–Wed `trust_invest=0.05`, leaves safe worlds 100% untouched, and gives tough worlds automatic Thursday–Friday repair (including a `1.25×` Friday ballast boost on `next_day` / `within_3_days` orders that have weekend drivers), allowing us to safely push `n14-02114` intake to `price_target_win=0.40, min_supply=20` and `min_supply=22`.

## What changed
Merged `origin/exp/gemini-n14-02114-stack-gates-trust-notes` and added the refined late-week budget mechanism in `src/spread_lab/policy.py` behind three `Params` fields whose defaults reproduce `n14-02114` / Champion v2 100% identically (`Δmargin €+0.00 ± 0.00` on smoke):
- `budget_target: float = 0.0` (0 = off; target projected on-time share to defend on `day >= budget_start_day`, tested `0.945` and `0.95`)
- `budget_start_day: int = 3` (only activate `budget_pressure()` when `self.now // DAY >= p.budget_start_day`, i.e., Thu–Fri, so Mon–Wed `trust_invest` is never touched)
- `ballast_discount: float = 0.06` (max discount on safe slow ballast options: `gate_supply >= 200`, `option["kind"] != "same_day"`, `drive <= 260` when `pressure > 0`)

When `pressure > 0` (on `day >= budget_start_day` when `projected_on_time() < budget_target`):
- Drop risky options (`option["kind"] == "same_day"` with `supply < 200`, `option["kind"] == "next_day"` with `drive > 300`, or `class_late_rate > 0.15 - 0.08 * pressure`), incrementing `self.stats["budget_declined"]`.
- On safe slow ballast options (`gate_supply >= 200`, `option["kind"] != "same_day"`, `drive <= 260`), multiply `option_mult` and `floor` by `1.0 - disc`, where `disc = (1.25 if day == 4 else 1.0) * p.ballast_discount * pressure`, incrementing `self.stats["budget_ballast"]`, and shift `learn()` target win rate by `disc` so the global tracker does not fight the ballast discount.

Run commands (on top of `n14-02114` Run 3 base flags `-s trust_invest=0.05 -s notes_v2=True -s note_unsure=decline -s max_next_day_drive_min=480 -s fri_same_day_max_drive=100 -s thin_long_next_day_supply=50 -s ring_to_hub_same_day_min=60 -s same_day_min_supply=50 -s min_slack_min=150 -s slack_per_drive=0.75`):
- **Dev Run 1 (`gtn-ptw38-thufri-budget-dev`):**
  ```sh
  uv run lab eval -s trust_invest=0.05 -s notes_v2=True -s note_unsure=decline -s max_next_day_drive_min=480 -s fri_same_day_max_drive=100 -s thin_long_next_day_supply=50 -s ring_to_hub_same_day_min=60 -s same_day_min_supply=50 -s min_slack_min=150 -s slack_per_drive=0.75 -s price_target_win=0.38 -s min_supply=25 -s budget_target=0.95 -s budget_start_day=3 -s ballast_discount=0.06 --name gtn-ptw38-thufri-budget-dev
  ```
- **Dev Run 2 (`gtn-ptw40-thufri-budget-dev`):**
  ```sh
  uv run lab eval -s trust_invest=0.05 -s notes_v2=True -s note_unsure=decline -s max_next_day_drive_min=480 -s fri_same_day_max_drive=100 -s thin_long_next_day_supply=50 -s ring_to_hub_same_day_min=60 -s same_day_min_supply=50 -s min_slack_min=150 -s slack_per_drive=0.75 -s price_target_win=0.40 -s min_supply=20 -s budget_target=0.945 -s budget_start_day=3 -s ballast_discount=0.05 --name gtn-ptw40-thufri-budget-dev
  ```
- **Dev Run 3 (`gtn-ptw40-ms22-thufri-budget-dev`):**
  ```sh
  uv run lab eval -s trust_invest=0.05 -s notes_v2=True -s note_unsure=decline -s max_next_day_drive_min=480 -s fri_same_day_max_drive=100 -s thin_long_next_day_supply=50 -s ring_to_hub_same_day_min=60 -s same_day_min_supply=50 -s min_slack_min=150 -s slack_per_drive=0.75 -s price_target_win=0.40 -s min_supply=22 -s budget_target=0.945 -s budget_start_day=3 -s ballast_discount=0.05 --name gtn-ptw40-ms22-thufri-budget-dev
  ```

## Results (level 8, vs champion v2, paired)
| set | run folder | variant | mean margin | Δmargin ± SE | t | better/worse | on-time min (mean, Δ) | SAFE |
|---|---|---|---:|---:|---:|---:|---:|---|
| smoke | `runs/20261114-030532-thufri-budget-noop` | defaults (noop) | €9,662.25 | €+0.00 ± 0.00 | — | 0 / 0 | 95.5% (96.7%, +0.00%) | yes |
| smoke | `runs/20261114-030646-thufri-budget-smoke1` | `ptw=0.38, ms=25, bt=0.95, bd=0.06` | €10,593.09 | €+930.85 ± 486.53 | 1.91 | 4 / 0 | 96.0% (97.1%, +0.37%) | yes |
| smoke | `runs/20261114-030757-thufri-budget-smoke2` | `ptw=0.40, ms=20, bt=0.95, bd=0.06` | €10,449.48 | €+787.23 ± 629.97 | 1.25 | 3 / 1 | 94.9% (96.7%, +0.05%) | yes |
| smoke | `runs/20261114-030844-thufri-budget-smoke3` | `ptw=0.40, ms=20, bt=0.945, bd=0.05` | €10,566.60 | €+904.35 ± 683.29 | 1.32 | 3 / 1 | 94.9% (96.8%, +0.14%) | yes |
| smoke | `runs/20261114-030932-thufri-budget-smoke4` | `ptw=0.40, ms=22, bt=0.945, bd=0.05` | €10,501.48 | €+839.24 ± 407.55 | 2.06 | 4 / 0 | 94.9% (96.7%, -0.02%) | yes |
| **dev Run 1** | `runs/20261114-031023-gtn-ptw38-thufri-budget-dev` | `ptw=0.38, ms=25, bt=0.95, bd=0.06` | **€10,014.00** | **€+1,023.70 ± 234.41** | **4.37** | **14 / 2** | **94.3% (97.4%, +0.66%)** | **yes** |
| **dev Run 2** | `runs/20261114-031243-gtn-ptw40-thufri-budget-dev` | **`ptw=0.40, ms=20, bt=0.945, bd=0.05`** | **€10,319.79** | **€+1,329.48 ± 234.44** | **5.67** | **15 / 1** | **94.9% (97.4%, +0.65%)** | **yes** |
| **dev Run 3** | `runs/20261114-031514-gtn-ptw40-ms22-thufri-budget-dev` | **`ptw=0.40, ms=22, bt=0.945, bd=0.05`** | **€10,302.26** | **€+1,311.96 ± 190.86** | **6.87** | **16 / 0** | **94.9% (97.5%, +0.72%)** | **yes** |

### Head-to-head paired comparisons vs `runs/20261114-022434-stack-gtn-ptw38-dev` (`€10,029.58` mean margin)
| Run | vs `stack-gtn-ptw38-dev` Δmargin ± SE | t | better / worse | Δon-time | Worst seed on-time |
|---|---:|---:|---:|---:|---:|
| **Dev Run 1 (`ptw=0.38, ms=25, bt=0.95, bd=0.06`)** | `€-15.58 ± 20.91` | `-0.75` | `1 / 2` (13 ties) | `+0.09%` | `94.26%` (`dev-07`) |
| **Dev Run 2 (`ptw=0.40, ms=20, bt=0.945, bd=0.05`)** | **`€+290.21 ± 190.97`** | **`+1.52`** | **`12 / 4`** | **`+0.08%`** | **`94.94%` (`dev-01`)** |
| **Dev Run 3 (`ptw=0.40, ms=22, bt=0.945, bd=0.05`)** | **`€+272.68 ± 156.71`** | **`+1.74`** | **`10 / 6`** | **`+0.15%`** | **`94.92%` (`dev-01`)** |

### Detailed stats counters and ledger breakdown on dev (16 worlds total / mean per world)
| Metric / Counter | Champion v2 | `stack-gtn-ptw38-dev` | Dev Run 1 (`ptw38, bt=0.95`) | Dev Run 2 (`ptw40, ms20, bt=0.945`) | Dev Run 3 (`ptw40, ms22, bt=0.945`) |
|---|---:|---:|---:|---:|---:|
| Active won orders (total / mean) | 3,644 (227.75/w) | 4,096 (256.00/w) | 4,093 (255.81/w) | **4,369 (273.06/w)** | **4,295 (268.44/w)** |
| **Total late orders (late %)** | 118 (7.38/w, 3.24%) | 112 (7.00/w, 2.73%) | **108 (6.75/w, 2.64%)** | 114 (7.12/w, 2.61%) | **109 (6.81/w, 2.54%)** |
| **Worst seed on-time** | 94.36% (`dev-10`) | 94.26% (`dev-07`) | 94.26% (`dev-07`) | **94.94% (`dev-01`)** | **94.92% (`dev-01`)** |
| Seeds where Thu–Fri budget activated | 0 / 16 | 0 / 16 | **3 / 16** (`dev-01, 04, 13`) | **2 / 16** (`dev-01, 02`) | **2 / 16** (`dev-01, 02`) |
| `budget_declined` (total / mean) | 0 (0.00/w) | 0 (0.00/w) | 32 (2.00/w) | 60 (3.75/w) | 39 (2.44/w) |
| `budget_ballast` (total / mean) | 0 (0.00/w) | 0 (0.00/w) | 106 (6.62/w) | 142 (8.88/w) | 97 (6.06/w) |
| `deadline_close` warnings | 193 (12.06/w) | 225 (14.06/w) | 216 (13.50/w) | 233 (14.56/w) | 219 (13.69/w) |
| `gig_expired` | 121 (7.56/w) | 104 (6.50/w) | 101 (6.31/w) | 115 (7.19/w) | 101 (6.31/w) |
| Ledger `revenue` (€/world) | +26,922.43 | +28,082.93 | +27,989.11 | **+29,842.06** | **+29,152.33** |
| Ledger `driver_fee` (€/world) | -17,286.92 | -17,673.60 | -17,578.00 | -19,118.42 | -18,473.84 |
| Ledger `late_refund` (€/world) | -376.20 | -288.22 | **-269.04** | -314.01 | **-277.06** |
| Ledger `failed_visit` (€/world) | -165.44 | -6.68 | -6.68 | -11.98 | -15.66 |

### Key findings
1. **Zero interference on safe worlds, surgical repair on tight worlds:**
   - In **Dev Run 1 (`ptw=0.38, ms=25, budget_target=0.95, budget_start_day=3, ballast_discount=0.06`)**, 13 of 16 seeds have `budget_declined = 0` and `budget_ballast = 0` and reproduce `stack-gtn-ptw38-dev` to the cent! On the 3 seeds where Thursday–Friday projected on-time dipped below `0.95`:
     - `dev-01`: `budget_declined=2, budget_ballast=25` lifted margin by **`+€153.44`** (`€7,775.27 → €7,928.71`) and on-time from `96.00%` to `96.03%`.
     - `dev-04`: `budget_declined=10, budget_ballast=26` lifted on-time by **`+0.69%`** (`96.35% → 97.04%`, `-€155.67` margin).
     - `dev-13`: `budget_declined=20, budget_ballast=55` lifted on-time by **`+0.74%`** (`94.70% → 95.44%`, `-€247.04` margin).
     - Note on `dev-07` (`94.26%` final on-time): on `dev-07`, `projected_on_time()` stayed above `0.95` during Thursday–Friday quoting hours (because the class-table gates had already eliminated the early-week `deadline_close` warnings, and the late deliveries occurred Friday evening after quoting closed).
2. **Unlocking `price_target_win=0.40` safely (`+€1,329.48` vs Champion v2, `+€290.21` vs `stack-gtn-ptw38-dev`):**
   - With `budget_target=0.945, budget_start_day=3, ballast_discount=0.05` guarding the tail on Thursday–Friday (`dev-01` and `dev-02` protected with `budget_declined=60, budget_ballast=142`, keeping `dev-01` at **`94.94%`** and lifting `dev-02` to **`97.08%`** and `€9,778.12`), **Dev Run 2 (`gtn-ptw40-thufri-budget-dev`, `ptw=0.40, ms=20`)** reaches **`€10,319.79` mean margin (`Δmargin €+1,329.48 ± 234.44`, `t = 5.67`, 15/16 seeds better vs Champion v2)** and beats `stack-gtn-ptw38-dev` by **`€+290.21 ± 190.97` (`t = 1.52`, 12/16 seeds better)** while lifting the worst seed across all 16 dev worlds from `94.26%` (`dev-07`) to **`94.94%` (`dev-01`)** (`dev-07` itself jumps to `97.08%` on-time and `€11,584.10` margin!).
   - **Dev Run 3 (`gtn-ptw40-ms22-thufri-budget-dev`, `ptw=0.40, ms=22`)** is even cleaner: it wins on **16 of 16 seeds (`16 / 0`!) vs Champion v2** with **`Δmargin €+1,311.96 ± 190.86` (`t = 6.87`)**, beats `stack-gtn-ptw38-dev` by **`€+272.68 ± 156.71` (`t = 1.74`, 10/6 better, `+0.15%` mean on-time)**, has fewer total late orders than both Champion v2 and `stack-gtn-ptw38-dev` (`109` vs `118` and `112`), and holds a worst-world on-time of **`94.92%`** (`97.5%` mean on-time).

## Verdict
**adopt** — Restricting the forward class budget and ballast discount to Thursday–Friday (`budget_start_day=3, budget_target=0.945, ballast_discount=0.05`) completely eliminates Mon–Wed double-discounting with `trust_invest=0.05`, leaves 14 of 16 already-safe dev worlds 100% untouched, and protects the tail on tight worlds (`worst on-time 94.9%`), enabling `price_target_win=0.40` on `n14-02114` to reach **€10,319.79 mean margin (`Δmargin €+1,329.48 ± 234.44, t = 5.67, 15/16 better` at `min_supply=20`)** and **€10,302.26 mean margin (`Δmargin €+1,311.96 ± 190.86, t = 6.87, 16/16 better` at `min_supply=22`)**.
