# tas-price: The Price Oracle, the Demand Curve, Oracle Selection, and Sunday Pricing Rules

- **Agent / branch / commit:** gemini · `exp/gemini-tas-price` · in progress
- **Date:** 2026-11-14 13:02–
- **Idea from:** TAS brief (`tas-price` layer: price oracle, demand curve, oracle selection, Sunday rules + own fork experiments)

## Journal

### Entry 0 — Instrument Validation on the Real Server (`dev-12`, Champion v5 `cp-fees`)
- **Question**: Does `scripts/tas.py` reproduce champion v5 (`cp-fees`) to the cent, does `tape.json` have exact foresight of the week's requests, and does batch bisection on forks leave the parent world untouched with zero cross-request interference (`CHECK`)?
- **Method**: `experiments/scripts/tas_selftest.py` (toy world) followed by `experiments/scripts/step0_tas_price.py` on the real server (`dev-12`).
- **Results**:
  1. `tas_selftest.py` passed all checks.
  2. `run --seed dev-12` (`run-v5-week`) gave **€10,910.49**, 246 won (`251` won before 5 dealer cancellations), **98.0% on time (`0.979675`)** in 642 server requests and 0 forks — matching champion v5 **to the cent**.
  3. `tape --seed dev-12` recorded **1,036 requests** and **709 drivers**. Comparing all 1,036 requests against `Desk.requests` from `run-v5-week` showed `same_order_ids=True` and **0 differences** across `arrivedAt`, `respondBy`, `dealerId`, `referenceFeeCents`, `note`, `options` (`kind`, `listPriceCents`, `deadline`), and `legs`. Foresight is exact.
  4. `limits --seed dev-12 --until "Tue 07:00"` vs `run --seed dev-12 --until "Tue 07:00"`: both ended at `Tue 07:19` with margin **€288.74**, revenue **€840.93**, `driver_fee` **-€552.19**, 58 won, 100.0% on time — **identical to the cent**, with **zero `CHECK`s** (`repriced_but_lost=[]`, `preview_differs_from_main_line=[]`). All 59 Monday won orders bracketed `exact` (`€5,910.40` taken vs `€6,609.47` at limits = `+€699.07` left on the table on Monday alone).
  5. **Fork speed**: Monday morning (`<= 14:00`) took **0.058 s/fork** (198 forks in 11.6 s, ~1,027 forks/min); Monday afternoon (`14:00–18:00`) took **0.100 s/fork** (194 forks in 19.5 s, ~597 forks/min).

### Entry 1 — Layer 1: Champion v5's Week at Perfect Prices (`dev-12`, `dev-01`, `dev-08`, `dev-07`)
- **Question**: How much money does v5 leave on the table purely in quote prices on the exact orders it already wins, and does repricing won quotes to each dealer's exact limit leave the rest of the week (`driver_fee`, staffing, lateness, competitor reaction, trust) completely unchanged?
- **Method**: `tas.py limits --seed <seed> --apply` followed by 0-fork re-recording verification `tas.py run --seed <seed> --book book-won-apply.json` on all four TAS worlds (`dev-12`, `dev-01`, `dev-08`, `dev-07`).
- **Results**:
  | World | Champion v5 | Layer 1 (`limits-won-apply`) | 0-Fork Replay | Δ Margin | Won | On-time | `driver_fee` (v5 vs L1) | Forks |
  |---|---:|---:|---:|---:|---:|---:|---|---:|
  | `dev-12` | €10,910.49 | **€14,572.94** | €14,572.94 | **+€3,662.45** (+33.6%) | 246 | 98.0% | -€18,367.50 / -€18,367.50 | 1,737 |
  | `dev-01` | €8,469.14 | **€11,680.61** | €11,680.61 | **+€3,211.47** (+37.9%) | 254 | 93.7% | -€13,712.22 / -€13,712.22 | 1,600 |
  | `dev-08` | €15,014.36 | **€20,518.72** | €20,518.72 | **+€5,504.36** (+36.7%) | 287 | 98.3% | -€19,490.63 / -€19,490.63 | 1,874 |
  | `dev-07` | €14,410.02 | **€21,315.92** | €21,315.92 | **+€6,905.90** (+47.9%) | 338 | 95.6% | -€26,441.05 / -€26,441.05 | 2,180 |
  | **Mean (4)** | **€12,201.00** | **€17,022.05** | **€17,022.05** | **+€4,821.05** (+39.5%) | **281.3** | **96.4%** | **€0.00 diff on all 4** | **1,848** |
- **Conclusions & Surprises**:
  1. **Exact invariance**: Across all 4 worlds (1,125 won orders), `won`, `on_time`, `driver_fee`, `release_fee`, `failed_visit`, and `waiting` moved by **€0.00**, with **0 `CHECK`s**, and every `book-won-apply.json` replayed to the cent with 0 forks.
  2. **Outage + trust ceiling exceeds `2.6×` list**: On `dev-08` (3 orders) and `dev-07` (9 orders), the dealer still bought at `2.60 × list` (`>=hi`).
  3. **Undelivered-order price inversion**: On `dev-01` and `dev-07`, 1 won car went undelivered at Wed+ 22:00. Because the rules charge **no revenue and a penalty of `2 × price`** on undelivered orders (and `100%` refund on orders `> 2` business days late), raising an undelivered order's price to its limit *reduces* margin by `2 × Δprice` (`-€26.20` on `dev-01`, `-€76.56` on `dev-07`). Conversely, winning an undelivered order at `€0.01` instead of its limit would save `2 × limit` (~`+€185` on `dev-01`, `+€426` on `dev-07`) even without changing selection!
