# tas-state: Steering Hidden World State with Foresight & Savestates, and the Full 4-World TAS Waterfall

- **Agent / branch:** gemini · `exp/gemini-tas-state`
- **Date:** 2026-11-14 14:25 Helsinki
- **Track:** TAS Layer 4 (`tas-state`: hidden state steered) + Full 5-Layer TAS Ceiling Stack (`Champion → +Prices → +Fees → +Tours → +State`) + Sunday Live-Desk Rules

---

## 1. Full 4-World TAS Waterfall Summary *(updating as post-14:50 runs complete)*

*Baseline anchor across all four TAS tracks:* Champion `v5` (`exp/gemini-cp-fees`, commit `6594436`). Every TAS margin below is a real week played on `spread.bahnexpress.com` and verified via 0-fork re-recording (`tas.py run --book`).

| World | Step 0: Champion `v5` | Step 1: `+ Perfect Prices` (`tas-price`) | Step 2: `+ Perfect Fees` (`tas-fees`) | Step 3: `+ Foresight Tours` (`tas-routes`) | Step 4a: `Prices + State` (Solo `TasStateDesk`, ≥92% SAFE) | Step 4b: **Full Stack Ceiling** (`Prices + Fees + Tours + State`) | Full-Stack Math Bound |
|---|---|---|---|---|---|---|---|
| **`dev-12`** *(median)* | €10,910.49 *(246, 98.0%)* | €14,572.94 *(246, 98.0%)* | *running* | *running* | *running* | *running* | €58,326.94 |
| **`dev-01`** *(weakest)* | €8,469.14 *(254, 93.7%)* | €11,680.61 *(254, 93.7%)* | *pending* | *pending* | *pending* | *pending* | €62,446.11 |
| **`dev-08`** *(richest)* | €15,014.36 *(287, 98.3%)* | €20,518.72 *(287, 98.3%)* | *pending* | *pending* | *pending* | *pending* | €71,518.78 |
| **`dev-07`** *(northern)* | €14,410.02 *(338, 95.6%)* | *running* | *pending* | *pending* | *pending* | *pending* | €64,035.40 |

---

## 2. Journal of Controlled Fork Probes: The Exact Equations of Hidden State

Before building `TasStateDesk`, we ran two controlled savestate (`fork`) probe campaigns on `dev-12` (`experiments/scripts/tas_state_probe_mechanics.py` and `tas_state_probe_mechanics2.py`, saved in `~/.spread-lab/tas/dev-12/tas-state-mechanics-probe*.json`) to measure the exact server equations rather than guessing from handbook prose.

### Probe A — Lose-Close (`2.3×` list) vs Decline (`4.0×` list): Exact Indifference
- **Question:** Does quoting a losing price just above the limit (`2.3×` list) move the competitor differently from declining at `4.0×` list?
- **Test:** Played two Monday lines on `dev-12` differing *only* in whether unwanted Monday requests were quoted at `2.3×` list or `4.0×` list (`0%` Monday win share, `trust = 0` on both), then bisected all Tuesday morning dealer limits (`iters=9`, `tol=100` cents).
- **Result:** **`0 cents` maximum difference** across every Tuesday request (`max_diff = 0` cents). The competitor observes binary `won`/`lost` outcomes per dealer and never sees our losing quote price.
- **Warning uncovered by laptop lead (`13:50` Test Final):** While a *losing quote* (`2.3×` or `4.0×`) has zero satisfaction cost, *not quoting at all* (`silent` unquoted requests) is tested separately in Probe D (`tas_state_thu_coldstart_probe.py`).

### Probe B — The Exact Competitor Morning Reaction Law (`trust = 0` isolated)
- **Question:** How much and at what exact daily win-share thresholds does the competitor raise or cut its prices next morning?
- **Test:** On `dev-12`, varied Monday win share on `D01` (`46` Monday requests), `D02` (`32`), `D03` (`27`), `D09` (`6`), `D10` (`4`) while choosing only `next_day`/`within_3_days` orders so **Tuesday 08:00 `trust = 0` across every arm**, isolating the pure competitor step. Then ran a fine-grained scan on `D01` across `14/46 (30.4%)`, `16/46 (34.8%)`, `18/46 (39.1%)`, `24/46 (52.2%)`, `27/46 (58.7%)`, `31/46 (67.4%)`, plus a 4-day (`Mon..Thu`) cumulative bound probe to Friday morning.
- **Exact Measured Law:**
  1. **Small-dealer immunity (`< 10` requests/day):** Dealers with `< 10` daily requests (`D09` with 6, `D10` with 4) show **`1.0000×` (`0 cents` change)** next morning even after `100%` Monday win share. You can win **100%** of every small dealer every day with zero competitor penalty!
  2. **Exact `[30%, 70%)` Neutral Deadband on busy dealers (`≥ 10` requests/day):**
     - **Win share `< 30%`** (e.g. `0%`, `25%`, `13/46 = 28.3%`): Competitor **RAISES** prices next morning by **`+1` step (`+3.5%` to `+4.3%`, mean `+3.8%`)**.
     - **Win share `30.0% .. 69.9%`**: **Exact `0`-step flat plateau!** Across `30.4%`, `34.8%`, `39.1%`, `52.2%`, `58.7%`, and `67.4%` (`31/46`), Tuesday `D01` limits are **identical to the cent** (`0.9663×` and `0.9584×` relative to the `+1`-step `0%` arm, i.e., `1.0000×` baseline).
     - **Win share `≥ 70%`** (e.g. `75%`, `100%`): Competitor **CUTS** prices next morning by **`-1` step (`-3.4%` to `-4.3%`, mean `-3.8%`)**.
  3. **Multi-day accumulation (`±3` steps cap):** Across 4 consecutive days (`Mon..Thu` `100%` vs `0%` with `trust = 0`), Friday morning `D02` limits drop to **`0.8045×`** (`1 / 0.8045 = 1.243×`, a **`24.3%` price swing** = `±3` steps of `~3.7%` each).
  4. **Friday Endgame Free-For-All:** Friday is the final request day of the week (`arrivedAt < 7200`). Winning **`100%` of profitable requests on Friday** incurs **zero** future competitor penalty, and `next_day`/`within_3_days` Friday orders have the entire 72-hour weekend (`Sat + Sun + Mon`) to book cheap drivers!

### Probe C — Trust (`+1%`), Satisfaction (`+0.1%..+0.5%`), and Late-Delivery Timing
- **Test:** Delivered exactly **1** Monday `same_day` order on `D01` (`R00010`) under three forks: (1) on time (`deliveredAt = 785 ≤ 1200`), (2) `1h` past deadline (`still in transit at Tue 08:00`), and (3) unstaffed past deadline (`still unbooked at Tue 08:00`), plus a 7-car Monday `same_day` arm (`17%` `D01` share).
- **Exact Measured Law:**
  1. **1 on-time delivery** raises Tuesday `D01` limits by **`+1.10%` to `+1.50%`** (`+1.0%` explicit trust bonus + `+0.1%..+0.5%` dealer satisfaction).
  2. **7 Monday `same_day` on-time deliveries on `D01` (`17%` Mon share < `30%`)** raised Tuesday `D01` limits by **`+9.7%` over `+1`-step Tuesday (`+14.0%` over normal Tuesday!)** — compounding `+1` competitor hike with `+7` trust + satisfaction overnight!
  3. **Crucial Late-Penalty Timing Discovery:** An order whose deadline has *already passed* (`dl = Mon 20:00`, `now = Tue 08:00`) causes **`0` trust loss, `0` satisfaction drop, and `0` `late_refund` (`1.0001×` limits)** until the car is actually **delivered** (`deliveredAt`) or the world ends!
  4. **How mid-week halvings hurt Champion `v5`:** Auditing `limits-won-apply.jsonl` across the 4 TAS worlds revealed that Champion `v5` suffered painful mid-week trust halvings on its highest-volume dealers:
     - `dev-01`: `D01` trust halved **three times** (`10 → 5` Tue, `8 → 5` Wed, `25 → 12` Thu), plus `D03` `9 → 4`!
     - `dev-07`: `D02` trust halved `23 → 11` on Wednesday `14:10` right before Thu/Fri!
     - `dev-12`: `D01` trust halved twice on Friday (`25 → 19 → 13`)!

---

## 3. Architecture of `TasStateDesk` (`src/spread_lab/policies/tas_state.py`)

We implemented `TasStateDesk(Desk)` with neutral-by-default `TasStateParams` (verified `Δ = €0.00` to the cent against `spread_lab.policy:Desk` and `0.00` book-replay drift across all 5 modes in `tas_state_selftest_policy.py` and `tas_state_run_suite.py --phase selftest`):

1. **5-Day Exact `(competitor_step, trust)` Dynamic Program per Dealer (`_solve_single_dealer_dp`):**
   - For each dealer `D`, evaluates all 3 daily win-share regimes on `Mon..Thu`: `< 30%` (`step + 1`), `< 68%` (`step + 0`), and `100%` (`step - 1`), and `100%` uncapped on Friday (`d == 4`) and on immune small dealers (`n_tot < 10`).
   - Tracks exact endogenous trust accumulation (`same_day` delivers on day `d` → counts on `d + 1`; `next_day`/`within_3_days` counts on `d + 2`), capped at `25`.
2. **Lagrangian Dual Ascent over Regional Driver Pools (`_build_foresight_plan`):**
   - Clusters towns within `42 km` of major hubs (`helsinki`, `tampere`, `turku`, `oulu`, `lahti`, `kuopio`, `jyvaskyla`, `mikkeli`, `seinajoki`) so overlapping Capital suburbs (`Helsinki + Vantaa + Espoo`) share a single physical driver pool instead of triple-counting roster supply.
   - Couples all 40 per-dealer DPs via 45 iterations of subgradient ascent on both daily total pool capacity `(pool, d)` and dedicated `same_day` capacity `("sd:" + pool, d)`.
3. **Event-Calendar Steering (`_detect_events` & `_score_tape_request`):**
   - **Outage (`80 km` circle, `~1.8×–1.9×` limits):** Harvests regional hub/ring requests inside the `80 km` circle at `+22%` expected base limit and relaxed local backlog cap.
   - **Price War (`08:00–18:00`, `~1.16×–1.23×` limits):** Defers multi-option War-day requests away from `same_day` to `next_day`/`within_3_days`, freeing War-day drivers to deliver higher-margin slow orders won on earlier days, while `floor_cents = expected_fee + min_profit` automatically rejects unprofitable War quotes during `limits --mode won --apply`.
   - **Flu & Snow Days:** Scales regional pool capacity (`×0.52` on Flu, `×0.58` on Snow) and blocks risky `same_day` commitments in affected zones.
4. **Early High-Trust Rescue (`tas_early_warn_h = 5.0`):**
   - Any unbooked order belonging to a dealer with `≥ €1,500` remaining tape list value triggers proactive fee/offer escalation at `lastPickupAt - 5h` (2 hours before the standard `3h` warning), preventing mid-week trust halvings (`25 → 12`) for pennies on the dollar.
5. **Lateness Edge (`tas_late_edge`, `≥ 90%` vs `≥ 92%`):**
   - Admits tight-slack (`75–180 min`), high-margin orders *exclusively* on Friday (`d == 4`) or on dealers with `< €250` remaining future tape volume, where a 10% late refund incurs **zero** downstream trust halving cost.

---

## 4. Diagnostic Discovery on Champion `v5`: Cross-Dealer Global `mult` Contamination

Slot-free X-ray of `reveal-v5.json` (`experiments/scripts/tas_state_xray_contamination.py`) uncovered a major structural leak in the live desk (`policy.py`):
- Because `trust_gain = 0.0` in `v5`, when `D01` reaches `trust = 25` (`+25%` accepted limit) or hits a regional Outage (`dev-01` Tuesday in Helsinki), `D01` wins **`50%–52%`** of its quotes (`dev-01: 79/154 = 51.3%`, `dev-08: 97/188 = 51.6%`, `dev-07: 139/279 = 49.8%`).
- Every extra win on `D01` steps up **global `self.mult`** (`price_lr = 0.05`, 2.5× faster than `dealer_lr = 0.02`), while `dealer_adj_min = 0.85` clamps downward adjustment on low-trust dealers!
- Result: **`D01` is simultaneously underpriced by ~10% (`51%` win rate), while low-trust dealers (`D02..D40`) are overpriced out of the market** (`dev-01 D02` won only **`9/65 = 13.8%`** of quoted hub/ring requests and `0/34` on Thursday despite `+3` competitor hikes!).

---

## 5. Achieved vs Arithmetic / Lagrangian Bounds

From `experiments/scripts/tas_state_bounds_and_sunday.py` across all 4,142 requests on the 4 TAS seeds:

| Seed | Champion `v5` | Layer 1 (`tas-price`) | Solo State-Steered Bound *(45% active fleet, min solo fee)* | Unsteered Tour Dual UB (`tas-routes`) | **Full-Stack Tour + State + Fee + Price Upper Bound** |
|---|---|---|---|---|---|
| **`dev-12`** | €10,910.49 | €14,572.94 | €32,900.25 *(511 cars)* | €55,926.94 | **€58,326.94** |
| **`dev-01`** | €8,469.14 | €11,680.61 | €31,502.30 *(522 cars)* | €60,046.11 | **€62,446.11** |
| **`dev-08`** | €15,014.36 | €20,518.72 | €34,469.03 *(504 cars)* | €69,118.78 | **€71,518.78** |
| **`dev-07`** | €14,410.02 | *running* | €40,561.14 *(566 cars)* | €61,635.40 | **€64,035.40** |

---

## 6. The Rules for Sunday 08:00 (Zero Forks, Zero Foresight)

Every hidden state we steered with savestates emits a clean **live, forkless signal** by 09:30 AM:

1. **Rule 1 (Our #1 Bet for Sunday) — Early 5h Trust-Protection Rescue + Partial `trust_gain` Decoupling:**
   - **What the live desk sees:** `self.dealer_trust[dlr]` (exact from ledger) and cumulative request count per dealer so far (`Mon ≤ 13:00` top-3 request count already captures **`47%–52%` of all Wed–Fri list euros** on 3/4 worlds, and `Mon ≤ 18:00` top-3 is `100%` exact on all 4 worlds!).
   - **Action:** Whenever an unbooked order belongs to a top-3 volume dealer with `dealer_trust[dlr] ≥ 10` on Mon–Thu, escalate its fee/proactive offers at **`lastPickupAt - 5h`** instead of `- 3h` (`+€18` extra driver fee saves `25 → 12` trust halving worth **`€600–€900`** in Thu/Fri limits!). Pair with `trust_gain = 0.45` (decoupled in `learn()` or widening `dealer_adj_min = 0.78`) so `D01` at `trust = 25` stops pricing `D02..D40` out of the `< 70%` deadband.
2. **Rule 2 — Exact `[30%, 70%)` Competitor Share Band & Friday Endgame Uncork:**
   - **What the live desk sees:** Live daily win share `won_today[dlr] / total_requests_today[dlr]` and day-of-week `d = now // 1440`.
   - **Action:** Never let a busy dealer (`≥ 10` requests today) cross `68%` win share on `Mon..Thu` (nudge `dealer_adj` up `+6%` when `share > 0.60`), gently cap Monday at `< 30%` on top-2 dealers if backlog is healthy (`+3.8%` Tue–Fri hike), and **on Friday (`d == 4`) remove the competitor share ceiling and `loss_streak_freeze` on `next_day`/`within_3_days` hub/ring orders** (0 future competitor penalty + 72h Sat–Mon staffing window).
3. **Rule 3 — `09:30 AM` Live Price-War Deferral (`100%` Precision & Recall across all 4 worlds):**
   - **What the live desk sees:** Non-declined quote win share during `08:00–09:30`. Across all 4 TAS worlds, **every single Price War morning scored `0%–7%` (`0/9` on `dev-12` Fri, `0/7` on `dev-01` Thu, `0/8` on `dev-08` Tue, `1/14` on `dev-07` Tue)** with **zero false positives** on normal mornings (`≥ 7` quotes).
   - **Action:** When `08:00–09:30` quotes `≥ 7` and `win_rate ≤ 10%`: disable `loss_streak_freeze` (so `mult` adapts instead of freezing at `1.65×`), drop `same_day` on all multi-option requests until `18:00` (saving today's drivers for yesterday's `next_day` backlog), and enforce a hard `1.00× ref + €16` cost floor.
4. **Rule 4 — Thursday `00:00` Cold-Start Calibration (if a round starts mid-week like the 14:00/20:00 Test Finals):**
   - **What the live desk sees:** `now >= 3 * 1440` with `len(self.orders) == 0` and `len(snapshot["history"]) > 400` lost requests (`0%` Mon–Wed win share → busy-dealer competitors are at **`+3` steps = `+12%..+15%`**!).
   - **Action:** Initialize `self.mult = 1.52` (instead of `1.35`) and `price_target_win = 0.45` so Thursday morning quotes immediately capture the `+3`-step ceiling instead of underpricing the first 30 wins while climbing from `1.35×`.

---

## 7. Real-Server Layer 4 & Ablation Measurements *(running post-14:50)*

*(Exact tables from `tas_state_run_suite.py` and full-stack runs will be appended immediately as each world completes.)*
