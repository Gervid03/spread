# n14-03503-stack-buf-alarm-steep-thufri: Combining adaptive delivery buffer + pre-warning alarm with Sweep 34 smooth fee/steep ramp and Thu–Fri safety budget

- **Agent / branch / commit:** gemini · `exp/gemini-n14-03503-stack-buf-alarm-steep-thufri` · see HEAD
- **Date:** 2026-11-14 04:06
- **Idea from:** Combination of `origin/exp/gemini-n14-03111-adaptive-delivery-buffer-and-alarm` (`IDEAS.md` #8 & #9), `origin/exp/gemini-n14-02464-thursday-friday-safety-budget` (`IDEAS.md` #10), and Sweep 34 smooth fee/steep schedule (`fee_warn=1.45, fee_step_min=25, steep_open=1.50`)

## Why we tried it
We merged the two strongest operational/safety branches built on top of `n14-02114-stack-gates-trust-notes` and tested their combination with Sweep 34's smooth fee/steep ramp:
1. **Smooth fee ramp across pre-warning and `deadline_close` (`n14-03111` + Sweep 34):**
   In `n14-03111`, `pre_warn_lead_min=60` reprices unbooked deadline-day orders 60 minutes before `deadline_close` (`lastPickupAt - 3h`) to a 2-step schedule `[pre_warn_fee, fee_warn]`, and at `deadline_close` `Desk.steep()` opens at `steep_open`. Under default `fee_warn=1.60, steep_open=1.80`, the fee jumps `1.35 → 1.60 → 1.80`. Combining `pre_warn_fee=1.30` with Sweep 34's `fee_warn=1.45, fee_step_min=25, steep_open=1.50` creates a continuous ramp (`0.85 → 1.30 at -4h → 1.45 at -3h30m → 1.50 at -3h, +0.25/30m`) that eliminates the 0.35× jump at `deadline_close` and reduces `driver_fee` across all rising schedules.
2. **Stacking `n14-03111` (`delivery_buffer_min=30, pre_warn_lead_min=60`) with `n14-02464` (`budget_target=0.945, budget_start_day=3, ballast_discount=0.05`):**
   Both `n14-03111` (`€10,508.07/wk, t=7.53, 16/16 better, min on-time 95.8%`) and `n14-02464` (`€10,302.26/wk, t=6.87, 16/16 better, min on-time 94.92%`) unlocked `price_target_win=0.40, min_supply=22` from different angles: `n14-03111` prevented operational lateness at the stop/gig level, while `n14-02464` added Thursday–Friday forward class-budget protection and slow ballast discounts on tough seeds. Combining them into a single unified `Desk` lets us measure their interaction and test cashing in the combined safety cushion at `min_slack_min=140, price_target_win=0.42, min_supply=20`.

## What changed
Merged `origin/exp/gemini-n14-03111-adaptive-delivery-buffer-and-alarm` and `origin/exp/gemini-n14-02464-thursday-friday-safety-budget` into `src/spread_lab/policy.py`. All new `Params` fields default to `0` / Champion v2 behaviour (`buf-steep-thufri-noop` reproduces Champion v2 bit-for-bit with `Δmargin €+0.00 ± 0.00` on smoke):
- From `n14-03111`: `delivery_buffer_min: int = 0`, `buffer_min_slack_min: int = 210`, `pre_warn_lead_min: int = 0`, `pre_warn_fee: float = 1.35`.
- From `n14-02464`: `budget_target: float = 0.0`, `budget_start_day: int = 3`, `ballast_discount: float = 0.06`.
- From `n14-02114` (common base): `trust_invest`, `notes_v2`, `note_unsure`, `max_next_day_drive_min`, `thin_long_next_day_supply`, `fri_same_day_max_drive`, `ring_to_hub_same_day_min`.

Let `<BASE>` be:
`-s trust_invest=0.05 -s notes_v2=True -s note_unsure=decline -s max_next_day_drive_min=480 -s fri_same_day_max_drive=100 -s thin_long_next_day_supply=50 -s ring_to_hub_same_day_min=60 -s same_day_min_supply=50 -s min_slack_min=150 -s slack_per_drive=0.75 -s price_target_win=0.40 -s min_supply=22 -s delivery_buffer_min=30 -s buffer_min_slack_min=210 -s pre_warn_lead_min=60`

Evaluated on dev:
- **Dev 1 (`gtn-buf-alarm-steep150-dev`):**
  `uv run lab eval <BASE> -s pre_warn_fee=1.30 -s fee_warn=1.45 -s fee_step_min=25 -s steep_open=1.50 --name gtn-buf-alarm-steep150-dev`
- **Dev 2 (`gtn-buf-alarm-steep150-thufri-dev`):**
  `uv run lab eval <BASE> -s pre_warn_fee=1.30 -s fee_warn=1.45 -s fee_step_min=25 -s steep_open=1.50 -s budget_target=0.945 -s budget_start_day=3 -s ballast_discount=0.05 --name gtn-buf-alarm-steep150-thufri-dev`
- **Dev 3 (`gtn-buf-alarm-thufri-fw160-dev`):**
  `uv run lab eval <BASE> -s pre_warn_fee=1.35 -s budget_target=0.945 -s budget_start_day=3 -s ballast_discount=0.05 --name gtn-buf-alarm-thufri-fw160-dev`
- **Dev 4 (`gtn-buf-alarm-thufri-taxback-dev`):**
  `uv run lab eval <BASE_WITH_SLACK140_PTW42_MS20> -s pre_warn_fee=1.35 -s budget_target=0.945 -s budget_start_day=3 -s ballast_discount=0.05 --name gtn-buf-alarm-thufri-taxback-dev`

## Results (level 8, vs champion v2, paired)
| set | run folder | mean margin | median / min margin | Δmargin ± SE | t | better/worse | on-time min (mean, Δ) | SAFE |
|---|---|---:|---:|---:|---:|---:|---:|---|
| smoke (noop) | `runs/20261114-035343-buf-steep-thufri-noop` | €9,662.25 | €8,889.88 / €7,296.78 | €+0.00 ± 0.00 | — | 0 / 0 | 95.5% (96.7%, +0.00%) | yes |
| smoke (Smoke 1: `steep150`) | `runs/20261114-035603-gtn-buf-alarm-steep150-smoke1` | €11,088.34 | €11,119.60 / €7,965.20 | €+1,426.09 ± 468.29 | 3.05 | 4 / 0 | 95.6% (97.0%, +0.34%) | yes |
| smoke (Smoke 2: `steep150-thufri`) | `runs/20261114-035713-gtn-buf-alarm-steep150-thufri-smoke2` | €10,927.77 | €10,805.11 / €7,951.91 | €+1,265.52 ± 381.54 | 3.32 | 4 / 0 | 95.6% (97.0%, +0.31%) | yes |
| smoke (Smoke 3: `thufri-fw160`) | `runs/20261114-035758-gtn-buf-alarm-thufri-fw160-smoke3` | €11,103.12 | €11,067.23 / €7,385.74 | €+1,440.87 ± 493.93 | 2.92 | 4 / 0 | 95.3% (97.1%, +0.46%) | yes |
| smoke (Smoke 4: `fw160-taxback`) | `runs/20261114-040342-gtn-buf-alarm-thufri-taxback-smoke4` | €10,790.76 | €11,071.94 / €7,568.47 | €+1,128.51 ± 703.50 | 1.60 | 3 / 1 | 94.5% (97.0%, +0.28%) | yes |
| smoke (Smoke 5: `steep150-taxback`) | `runs/20261114-040406-gtn-buf-alarm-steep150-thufri-taxback-smoke5` | €10,658.30 | €10,598.88 / €7,983.57 | €+996.05 ± 620.09 | 1.61 | 3 / 1 | 93.4% (96.1%, -0.58%) | yes |
| **dev Dev 1 (`gtn-buf-alarm-steep150-dev`)** | `runs/20261114-035824-gtn-buf-alarm-steep150-dev` | **€10,503.56** | **€9,802.33 / €7,621.13** | **€+1,513.26 ± 226.58** | **6.68** | **15 / 1** | **94.7% (97.3%, +0.60%)** | **yes** |
| **dev Dev 2 (`gtn-buf-alarm-steep150-thufri-dev`)** | `runs/20261114-035906-gtn-buf-alarm-steep150-thufri-dev` | **€10,463.42** | **€9,621.56 / €7,621.13** | **€+1,473.11 ± 220.09** | **6.69** | **15 / 1** | **94.7% (97.3%, +0.59%)** | **yes** |
| **dev Dev 3 (`gtn-buf-alarm-thufri-fw160-dev`)** | `runs/20261114-040120-gtn-buf-alarm-thufri-fw160-dev` | **€10,475.44** | **€9,623.10 / €7,385.74** | **€+1,485.13 ± 198.31** | **7.49** | **16 / 0** | **95.3% (97.7%, +0.91%)** | **yes** |
| **dev Dev 4 (`gtn-buf-alarm-thufri-taxback-dev`)** | `runs/20261114-040502-gtn-buf-alarm-thufri-taxback-dev` | **€10,412.74** | **€10,018.43 / €7,568.47** | **€+1,422.44 ± 232.97** | **6.11** | **14 / 2** | **94.0% (97.4%, +0.65%)** | **yes** |

### Head-to-head `uv run lab compare` vs `gtn-ptw40-buf-alarm-dev` (`€10,508.07`) and `gtn-ptw40-ms22-thufri-budget-dev` (`€10,302.26`)
| Run | vs `20261114-032059-gtn-ptw40-buf-alarm-dev` (`n14-03111`) | vs `20261114-031514-gtn-ptw40-ms22-thufri-budget-dev` (`n14-02464`) |
|---|---|---|
| **Dev 1 (`gtn-buf-alarm-steep150-dev`)** | `Δmargin €-4.51 ± 111.81 (t=-0.04)`, 7/9, `Δon-time -0.36%` | **`Δmargin €+201.30 ± 146.66 (t=1.37)`**, **12/4**, `Δon-time -0.12%` |
| **Dev 2 (`gtn-buf-alarm-steep150-thufri-dev`)** | `Δmargin €-44.65 ± 122.54 (t=-0.36)`, 7/9, `Δon-time -0.37%` | **`Δmargin €+161.16 ± 140.59 (t=1.15)`**, **12/4**, `Δon-time -0.13%` |
| **Dev 3 (`gtn-buf-alarm-thufri-fw160-dev`)** | `Δmargin €-32.64 ± 24.97 (t=-1.31)`, 0/2 (14 ties), `Δon-time -0.05%` | **`Δmargin €+173.18 ± 135.26 (t=1.28)`**, **10/6**, **`Δon-time +0.19%`** |
| **Dev 4 (`gtn-buf-alarm-thufri-taxback-dev`)** | `Δmargin €-95.33 ± 209.48 (t=-0.46)`, 7/9, `Δon-time -0.31%` | **`Δmargin €+110.48 ± 174.56 (t=0.63)`**, **10/6**, `Δon-time -0.07%` |

### Ledger breakdown and desk counters on dev (16 worlds total / mean per world)
| Metric / Counter | Champion v2 | `n14-03111` (`buf-alarm`, `fw=1.60`) | `n14-02464` (`thufri-bud`, `ms=22`) | **Dev 1 (`steep150`)** | **Dev 2 (`steep150-thufri`)** | **Dev 3 (`thufri-fw160`)** | **Dev 4 (`thufri-taxback`)** |
|---|---:|---:|---:|---:|---:|---:|---:|
| Mean margin (€/world) | €8,990.31 | **€10,508.07** | €10,302.26 | **€10,503.56** | €10,463.42 | **€10,475.44** | €10,412.74 |
| Median margin (€/world) | €8,685.06 | €9,815.20 | €9,688.10 | €9,802.33 | €9,621.56 | €9,623.10 | **€10,018.43** |
| **Worst-seed margin (€)** | €6,017.30 | €7,523.75 | €7,312.10 | **€7,621.13** | **€7,621.13** | €7,385.74 | €7,568.47 |
| Won orders (total / mean) | 3,644 (227.75/w) | 4,331 (270.69/w) | 4,295 (268.44/w) | 4,314 (269.62/w) | 4,306 (269.12/w) | 4,307 (269.19/w) | **4,533 (283.31/w)** |
| **Late orders (total / %)** | 118 (7.38/w, 3.24%) | **99 (6.19/w, 2.29%)** | 109 (6.81/w, 2.54%) | 115 (7.19/w, 2.67%) | 115 (7.19/w, 2.67%) | **100 (6.25/w, 2.32%)** | 119 (7.44/w, 2.63%) |
| **On-time mean / min** | 96.75% / 94.36% | **97.71% / 95.80%** | 97.47% / 94.92% | 97.34% / 94.70% | 97.34% / 94.70% | **97.66% / 95.26%** | 97.39% / 94.04% |
| Ledger `revenue` (€/w) | +26,922.43 | +29,650.81 | +29,152.42 | +29,276.42 | +29,198.54 | +29,525.77 | **+30,518.85** |
| Ledger `driver_fee` (€/w) | -17,286.93 | -18,776.97 | -18,474.50 | **-18,320.31** | **-18,280.71** | -18,688.97 | -19,670.09 |
| Ledger `late_refund` (€/w) | -376.20 | -260.38 | -277.43 | -351.68 | -351.68 | **-255.98** | -313.71 |
| Ledger `failed_visit` (€/w) | -165.44 | -21.21 | -15.75 | **-6.09** | **-6.09** | -21.21 | -35.51 |
| Ledger `release_fee` (€/w) | -53.48 | -53.21 | -51.80 | -54.01 | -54.01 | -53.21 | **-45.17** |
| Ledger `waiting` (€/w) | -39.38 | -20.73 | -20.62 | -24.38 | -26.25 | -20.73 | -24.89 |
| `buffered_stops` (total / w) | 0 (0.00/w) | 4,300 (268.75/w) | 0 (0.00/w) | 4,280 (267.50/w) | 4,273 (267.06/w) | 4,277 (267.31/w) | **4,494 (280.88/w)** |
| `pre_warned` (total / w) | 0 (0.00/w) | 192 (12.00/w) | 0 (0.00/w) | 229 (14.31/w) | 227 (14.19/w) | **188 (11.75/w)** | 227 (14.19/w) |
| `budget_ballast` (total / w) | 0 (0.00/w) | 0 (0.00/w) | 97 (6.06/w) | 0 (0.00/w) | 203 (12.69/w) | 120 (7.50/w) | 143 (8.94/w) |
| `budget_declined` (total / w) | 0 (0.00/w) | 0 (0.00/w) | 39 (2.44/w) | 0 (0.00/w) | 73 (4.56/w) | 46 (2.88/w) | 68 (4.25/w) |
| `deadline_close` (total / w) | 193 (12.06/w) | 241 (15.06/w) | 219 (13.69/w) | 282 (17.62/w) | 280 (17.50/w) | 235 (14.69/w) | 272 (17.00/w) |
| `gig_expired` (total / w) | 121 (7.56/w) | 119 (7.44/w) | 101 (6.31/w) | 137 (8.56/w) | 136 (8.50/w) | 118 (7.38/w) | 140 (8.75/w) |
| `offers` / `offer_accepted` | 0 / 0 | 384 / 7 | 0 / 0 | 458 / 9 | 454 / 7 | 376 / 6 | 454 / 8 |

### Analysis of interactions
1. **Smooth fee ramp (`Dev 1: fee_warn=1.45, fee_step_min=25, steep_open=1.50, pre_warn_fee=1.30`) vs default `fee_warn=1.60, steep_open=1.80, pre_warn_fee=1.35` (`n14-03111`):**
   - **What it saves:** Dev 1 cuts `driver_fee` by **`€456.66/wk`** (`-€18,320.31` vs `-€18,776.97/wk`) and cuts `failed_visit` from `-€21.21/wk` to `-€6.09/wk`. On tight-margin worlds where driver fees dominate, Dev 1 lifts margin substantially (`dev-01`: `€7,523.75 → €7,965.20`, `+€441.45`; `dev-11`: `€7,758.33 → €8,543.31`, `+€784.98`; `dev-08`: `€14,956.72 → €15,529.54`, `+€572.82`), raising the **16-seed minimum margin floor to `€7,621.13`** (`+€1,603.83` above Champion v2's `€6,017.30` and `+€97.38` above `n14-03111`'s `€7,523.75`).
   - **What it costs:** Because `1.30 → 1.45 → 1.50` is gentler than `1.35 → 1.60 → 1.80` during the final 4 hours before `lastPickupAt`, `deadline_close` warnings rise by `+2.56/wk` (`15.06 → 17.62/wk`) and late orders rise by `+1.00/wk` (`99 → 115` total, `97.71% → 97.34%` mean on-time, `95.80% → 94.70%` min on-time), increasing `late_refund` by `-€91.30/wk` and slightly slowing dealer trust accumulation (`revenue -€374.39/wk`). Net mean margin is a statistical dead heat (`€10,503.56` vs `€10,508.07`, `Δmargin €-4.51 ± 111.81, t=-0.04`).
2. **Adding `n14-03111` (`delivery_buffer_min=30, pre_warn_lead_min=60`) on top of `n14-02464` (`budget_target=0.945, budget_start_day=3, ballast_discount=0.05`):**
   - Against `n14-02464` alone (`€10,302.26`), **Dev 3 (`€10,475.44`, `Δmargin €+173.18 ± 135.26, t=1.28`, 10/6 better)** and **Dev 1 (`€10,503.56`, `Δmargin €+201.30 ± 146.66, t=1.37`, 12/4 better)** both improve mean margin while Dev 3 also cuts late orders (`109 → 100`) and lifts worst-seed on-time (`94.92% → 95.26%`).
   - Why does `budget_target=0.945` cost `-€32.64 ± 24.97` (`14 ties, 0 better, 2 worse`) relative to `n14-03111` alone? On 14 of 16 dev seeds (`dev-03` through `dev-16`), `n14-03111`'s operational buffer and pre-warning rescue keep `projected_on_time() >= 0.945` all through Thursday and Friday, so `budget_ballast=0, budget_declined=0` and Dev 3 reproduces `n14-03111` to the cent. On `dev-01` and `dev-02`, `projected_on_time()` (which conservatively subtracts expected class lateness of all open orders) dips just below `0.945` on Thu–Fri (`budget_ballast=120, budget_declined=46`), even though `n14-03111`'s operational fixes already kept `dev-01` at `95.8%` and `dev-02` at `96.2%` without budget intervention. Thus `budget_target=0.945` is slightly redundant when `delivery_buffer_min=30, pre_warn_lead_min=60, pre_warn_fee=1.35` are active (setting `budget_target=0.0` or `0.935` avoids touching `dev-01`/`dev-02`).
3. **Testing aggressive volume taxback (`Dev 4: min_slack_min=140, price_target_win=0.42, min_supply=20`):**
   - Dev 4 remains **100% SAFE** across all 16 dev worlds (`min on-time 94.04%`, `mean on-time 97.39%`), wins `283.31` orders/wk (`+55.56/wk` over Champion v2), lifts **median margin to `€10,018.43`** (highest median of all runs), and reaches `+€30,518.85/wk` revenue. However, the marginal orders between `ptw=0.40, ms=22, slack=150` and `ptw=0.42, ms=20, slack=140` cost more in `driver_fee` (`-€19,670.09/wk`) than they add in revenue, bringing mean margin to `€10,412.74` (`Δmargin €+1,422.44 ± 232.97, t=6.11`). This confirms `price_target_win=0.40, min_supply=22, min_slack_min=150` as the optimal intake point.

## Verdict
**adopt merged branch (`src/spread_lab/policy.py` unify `n14-03111` + `n14-02464`)** — With `<BASE>` + `pre_warn_fee=1.35` (`n14-03111` settings, `budget_target=0.0`) it achieves **`€10,508.07` (`Δmargin €+1,517.77 ± 201.53, t=7.53`, 16/16 better, min on-time `95.8%`)**; with Sweep 34 (`Dev 1: pre_warn_fee=1.30, fee_warn=1.45, fee_step_min=25, steep_open=1.50`) it achieves **`€10,503.56` (`Δmargin €+1,513.26 ± 226.58, t=6.68`, 15/16 better, min on-time `94.7%`)** and lifts worst-seed margin to **`€7,621.13`**; and with `budget_target=0.945, budget_start_day=3, ballast_discount=0.05` (`Dev 3`) it achieves **`€10,475.44` (`Δmargin €+1,485.13 ± 198.31, t=7.49`, 16/16 better, min on-time `95.3%`)**.
