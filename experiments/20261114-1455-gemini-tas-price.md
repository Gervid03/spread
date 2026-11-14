# tas-price: The Price Oracle, the Demand Curve, Oracle Selection, and Sunday Pricing Rules

- **Agent / branch / commit:** gemini · `exp/gemini-tas-price` · in progress
- **Date:** 2026-11-14 13:02–
- **Idea from:** TAS brief (`tas-price`: Step 0 validation, Layer 1 perfect prices, full-week demand curve `limits-all`, Layer 2 `OracleDesk` selection, stacked `OracleCyclesDesk`, live forkless Sunday rules, and own fork probes)

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

---

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
  3. **Undelivered-order price inversion**: On `dev-01` and `dev-07`, 1 won car went undelivered at Wed+ 22:00. Because the rules charge **no revenue and a penalty of `2 × price`** on undelivered orders (and `100%` refund on orders `> 2` business days late), raising an undelivered order's price to its limit *reduces* margin by `2 × Δprice` (`-€26.20` on `dev-01`, `-€76.56` on `dev-07`).
  4. **Cross-policy book fragility (`run-l1-plus-v7cycles`, failure)**: Replaying v5's static `book-won-apply.json` directly on Champion v7 (`cycles:Desk`) with 0 forks dropped `won` from `246 → 157` (`€7,993.98`), because a single shift in delivery timing changes a busy dealer's `dealer_trust` by `±1%`, and since `book-won-apply.json` prices to within €0.50 of the old `trust` limit, `-1%` trust turns subsequent razor-edge quotes into losses. Stacking across staffing policies requires live fork re-bisection (or a 1–2% trust cushion).

---

### Entry 2 — The Complete Demand Curve (`limits-all.jsonl` on `dev-12`, 6,046 Forks) & Arithmetic Bounds
- **Method**: `tas.py limits --seed dev-12 --mode all --lo 0.6 --hi 3.4 --iters 8 --name all` (`6,046` forks), analyzed via `experiments/scripts/analyze_limits_all.py` and `check_menu_effect.py`.
- **Arithmetic Bounds on `dev-12` (1,036 requests, 1,833 `(request, option)` pairs)**:
  - **1,036 / 1,036 requests (100.0%)** are winnable inside `[0.6x, 3.4x]` (`1,788 exact`, `45 <0.6x`, `0 >=3.4x`).
  - **Gross revenue bound** (every request won at its highest-limit option): **€122,301.51**.
  - **Arithmetic margin bounds** (before capacity/deadline constraints):
    - `sum(max(0, limit - 1.00 * ref))` = **€42,838.56** across 963 requests.
    - `sum(max(0, limit - 0.85 * ref))` = **€54,164.45** across 1,010 requests (v5 solo opening fee).
    - `sum(max(0, limit - 0.40 * ref))` = **€90,057.46** across 1,036 requests (closed-tour fee bound).
- **Four Structural Laws of the Demand Curve**:
  1. **Option Menu Structure Law (`same_day` vs `next_day` on the exact same request)**:
     - Across **632 paired exact requests** offering both `same_day` and `next_day`: `list(same_day)/list(next_day)` median = `1.0795`, while **`limit/list(same_day)` median = `1.4312` vs `limit/list(next_day)` median = `1.2397` (`+15.5%` multiplier gap; `+€23.56` median euro gap; `100.0%` have `L_sd > L_nd`)**!
     - **Why**: Trust-adjusted `limit/list` is **`1.3436` on `same_day` (`n=733`)**, **`1.2171` on `next_day` when `same_day` is NOT on the menu (`n=303`)**, and **`1.1574` on `next_day` when `same_day` IS on the menu (`n=632`)** — because when the request includes `same_day` and our desk drops `same_day` via supply/slack gates, our `next_day`-only quote competes head-to-head against the competitor's fast `same_day`! As a result, v5 won **`40.3%` (`91/226`)** when quoting `same_day`, vs only **`26.6%` (`99/372`)** when quoting `next_day` after dropping `same_day`!
  2. **Day, Outage & Price-War Anatomy (`dev-12` fastest option, trust-adjusted `limit/list`, 08:00–18:00)**:
     - **Mon**: `1.4093` | **Tue (Outage within 80 km of Hämeenlinna)**: `1.5425` inside (`n=55`) vs `1.4537` outside (`n=140`) | **Wed**: `1.2984` | **Thu**: `1.2928` | **Fri (Price War 08:00–18:00)**: **`1.0155` (`-21.5%` drop everywhere)**.
  3. **Cross-World Destination-Supply Competitor Lane Factor (All 4 TAS Worlds)**:
     - On `dev-12` normal days (Mon/Wed/Thu, trust-normalized), Capital-hub deliveries (`dest_supply >= 200`) have median `limit/list = 1.1023`, vs `1.2451–1.3683` (`+13%` to `+24%` higher!) in thin/regional delivery towns.
     - Across **all 4 worlds** (`limits-won-apply.jsonl`, trust- and world-median-normalized): **`helsinki 0.884x`, `vantaa 0.929x`, `turku 0.937x`, `hyvinkaa 0.949x`** vs **`ylivieska 1.159x`, `vaasa 1.092x`, `seinajoki 1.092x`, `joensuu 1.072x`, `kokkola 1.056x`, `lappeenranta 1.047x`**.
     - On `dev-12`, **94.9% (`€3,556.72` of `€3,749.04`)** of v5's won-order pricing gap was on `dest_supply < 150` (`€16.86/car` gap vs only `€4.81/car` on `dest_supply >= 150`).
  4. **Lost & Declined Opportunities (`dev-12`)**:
     - **319 requests** were quoted by v5 and **lost** despite having `limit >= 1.359 * ref` (v5's own floor), worth `€15,412` net margin at `0.95 * ref`.
     - **140 requests** were **declined** by v5 despite having `limit >= 1.359 * ref` (`€8,478` at `0.95 * ref`), primarily due to `gate_supply < 22` and `slack_or_same_day_gate`.

---

### Entry 3 — Own Fork Probes of Dealer Choice Mechanics (`probe_dealer_mechanics.py`, 11 Forks on `dev-12`)
- **Questions tested directly on Monday forks of `dev-12`**:
  1. **Decoy options**: Can quoting an unchosen second option (`next_day` at `1.01x`, `1.20x`, or `2.50x` of `nd_hi`) turn `same_day` at `sd_hi` (known losing price) into a win? → **`0/3` wins across all three decoy multipliers (`0.00` decoy boost)**.
  2. **Exact additive utility law (`V(sd) - V(nd) == L_sd - L_nd`)**: Quoting `(sd_lo - €1.50, nd_lo)` gave **`3/3` `same_day`**, while `(sd_lo, nd_lo - €1.50)` gave **`3/3` `next_day`**. Dealers maximize `V_k - p_k` deterministically against the competitor's best option; quoting multiple options can only cannibalize higher-margin options, never raise a limit.
  3. **Quote timing invariance (`arrivedAt` vs `respondBy - 1`)**: Holding quotes silent from `arrivedAt = Mon 08:10` (`490`) until `t = 503` (`respondBy - 1`) on forks gave **`3/3` wins at `lo` and `0/3` wins at `hi`** — limits are 100% invariant to quote minute before `respondBy` (meaning a live or TAS desk gets 15–30 minutes of free arrival lookahead if it waits).
  4. **`batchId` decision independence (`B0032`, 3 simultaneous cars)**: Winning half at `0.7x` vs declining half at `4.0x` gave **`2/2` wins at `lo` and `0/2` wins at `hi`** on the remaining cars — batched dealer requests are decided strictly independently, allowing car-by-car cherry-picking even inside bulk orders (`152` `batchId`s / `525` batched cars on `dev-12`).

---

### Entry 4 — Layer 2 (`OracleDesk`): Why Raw Euro Cherry-Picking Failed and Profit-per-Driver-Block Won
- **Failure 1 (`screen-l2-base` / `screen-l2-vol`, raw euro hurdle `limit - expected_fee`)**:
  - Ranking and filtering requests by raw euro profit `limit - expected_fee` **dropped margin from Layer 1's `€14,572.94` (`246` won, `98.0%` OT) down to `€11,465.16` (`193` won, `93.8%` OT)**!
  - **Root cause**: Raw euro margins are largest on 380–585 min dead-end drives (`R00368 397m`, `R00611 384m`, `R00694 585m`), which under v5 solo staffing consume an entire driver for 1–2 days, have a **9.7% late rate** (calibrated across 1,138 v5 orders in `calibrate_v5_staffing.py`, vs 3.6% for `<=180m`), escalate to `2.25x` rescue fees, and starve Monday–Wednesday trust building (`31` Monday wins vs v5's `58`).
- **Failure 2 (`screen-roi-2`, pure ROI `(limit - cost)/cost`)**:
  - Pure percentage ROI swung to the opposite extreme: favoring 15-minute `€32 limit / €13 fee = +146% ROI` micro-cars (`+€19`) over 160-minute `€155 limit / €65 fee = +138% ROI` medium corridor gems (`+€90`!).
- **Breakthrough (`tas-price-layer2`, Profit-per-Driver-Block `(net + trust_velocity) / (1 + drive/150 + 0.35*(dest<25))` + `max_next_day_drive_min=360` + `<68%` busy-dealer deadband)**:
  - Live fork bisection on `dev-12` (`4,248` forks, **unchanged Champion v5 staffing**):
    - **Margin: `€15,928.36`** (**`+€5,017.87` / `+46.0%` over Champion v5's `€10,910.49`**, and **`+€1,355.42` over Layer 1's `€14,572.94`**!)
    - **Won: `313` (`+67` orders over v5)** | **On-time: `97.1%` (`SAFE`, +5.1 pts above 92%)** | **Broken quotes: `0`**.
    - **0-fork plain `Desk` book replay (`run-book-tas-price-layer2`)**: **`€15,928.36` (`Δ = €0.00` to the cent, 0 forks)**.

---

### Entry 5 — P0 Bug Catch on `main` (`73fc729` → `cf4b987`) During Sunday Rule Validation
- Running our mandatory `Δ = €0.00` noop check (`runs/20261114-161931-tas-price-v7-noop`) right after Champion v7 (`73fc729`) landed on `main` revealed **`Δmargin = -€2,282.31 ± 539.01 (t = -4.23, 0/4)`**!
- **Diagnosis**: `lab promote` with `--policy spread_lab.policies.cycles:Desk` wrote only the 13 cycle CLI flags into `champion/champion.json`, wiping out 45 of v6's base parameters (`notes_v2`, `lead_car`, `supervisor`, `view_offer_mult`, `min_supply=22`, etc.). Restoring `V6_BASE_PARAMS` gave `Δ = €+0.00 ± 0.00` (`runs/20261114-162357-tas-price-v7-fixed-noop`); alerted `STATUS.md` immediately and fixed on `main` (`cf4b987`).
