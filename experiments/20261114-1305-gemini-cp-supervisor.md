# cp-supervisor: 08:00 Morning Day Supervisor reading backlog, free drivers, on-time surplus, and weekday

- **Agent / branch / commit:** gemini · `exp/gemini-cp-supervisor` · `d33e414` (stacked on Champion `9aa3f13`, also measured standalone on v3T `d93271e`)
- **Date:** 2026-11-14 13:05 EET
- **Idea from:** Co-play focus `cp-supervisor` on `dev-15` + Carbon brief `c5` (`experiments/prompts/carbon/c5-day-supervisor.md`) + `IDEAS.md` items 14 (regional same-day towns) & 21 (Friday surplus)

## Why we tried it
A static `Params` vector treats a calm high-surplus morning (`0` unstaffed orders, `0` warnings, `98.5%+` on time) identically to a congested post-snow/flu morning (`12+` unstaffed orders, `8+` deadline warnings), and treats Friday slow options (due **Monday 20:00**, 72–84 hours away with two full weekend days of uncompeting driver supply) identically to Tuesday 24-hour `next_day` orders.

An earlier non-coplay attempt at `c5` (`exp/gemini-d14-04-day-supervisor`) lost `−€93/world` on dev because it adjusted the wrong dials (`price_target_win +0.02`, `min_supply -2` Mon–Thu, `fee_open`) without checking exact counterfactuals. Using `scripts/coplay.py` on **`dev-15`** (champion v3T: `€9,775.77`, `270` won, `98.15%` on time), we stepped morning-by-morning with exact `whatif` forks and `probe` binary searches to discover which morning levers actually create margin without risking the 92% safety floor, then distilled those exact choices into a deterministic 08:00 state rule in `Desk.maybe_supervise()`.

## Co-play journal on `dev-15` (`cp-supervisor-1`, `cp-supervisor-2`, `cp-supervisor-3`)

1. **Monday 08:30–09:30 (`cp-supervisor-1`, turns 1–6) — Why naive `c5` loosening fails:**
   - Inspection of town driver supplies on `dev-15` revealed Capital `[365]`, `Hyvinkää[70]`, `Tampere/Lempäälä[59]`, **`Lahti[44]`** (D01's busy yard, blocked from `same_day` by `same_day_min_supply=50`!), `Turku/Raisio[31]`, and bulk-order yard `Vaasa[11]`.
   - `probe` on waiting quotes (`R00008 Lempäälä→Espoo limit 1.147×`, `R00010 Hyvinkää→Helsinki limit 1.10×`) showed `dev-15` is a low competitor-multiplier world (`mult` settled to `1.234` by Tue 08:00, with 338 floor quotes).
   - **16 exact whole-week `whatif` forks at Monday 09:30 all lost against keeping Champion (`€9,776`):**
     - Loosening `price_target_win=0.45`: **`€8,972 (−€804)`**, `301` won (`+31` cars, giveaway on inframarginal quotes + extra driver fees).
     - Tightening `price_target_win=0.35`: **`€8,657 (−€1,119)`**, `243` won.
     - Loosening Mon–Thu `min_supply=18, min_slack_min=120`: **`€8,912 (−€864)`**, `96.7%` OT.
     - Cutting `fee_open=0.78`: **`€8,658 (−€1,118)`**; raising `fee_open=0.90`: **`€8,557 (−€1,219)`**.
     - Raising `price_mult_min=1.32 / 1.40` or `loss_streak_freeze=4`: **`−€350 to −€599`** (`dev-15` has a genuinely low world price level and a Friday price war down to `1.09×`).
   - **Monday decision:** Keep Champion defaults on Monday while `mult` learns the world price level and builds initial dealer trust (`58` won on Monday, all `58` booked immediately at `0.85×` ref fee, `0` warnings, `0` unstaffed by Tue 08:00).

2. **Tuesday 08:00 (`cp-supervisor-1`, turns 8–10) — Calm-board mid-hub option & slack opening (`+€212`):**
   - State at `Tue 08:00`: `won=58`, `unstaffed=0`, `warnings=0`, `late=0` (`100.0%` OT), `mult=1.234`.
   - `whatif` forks from `Tue 08:00`:
     - `same_day_min_supply=35` alone: **`€9,921 (+€146)`**, `271` won, `98.2%` OT (unlocks `Lahti[44]` `same_day`, earning `+13%` higher revenue per car on D01's main yard!).
     - `min_slack_min=135` alone: **`€9,834 (+€58)`**, `98.1%` OT.
     - **Combined `same_day_min_supply=35, min_slack_min=135`: `€9,988 (+€212)`**, `270` won, `98.2%` OT!
     - By contrast, opening `same_day_min_supply=35, min_slack_min=135` blindly at `Mon 07:00` (`cp-supervisor-2`) gained much less because Monday's uncalibrated `mult=1.35` interacted poorly before Monday settled.

3. **Wednesday 08:01 & Thursday 08:01 (`cp-supervisor-1`, turns 11–16) — Hold steady through the Wednesday outage:**
   - Wednesday was a regional outage (`73` wins in one day, `mult` rose to `1.462`).
   - Testing `price_target_win=0.45` (`−€203`), `0.36` (`−€408`), `min_supply=15` (`−€514`, OT `97.4%`), `trust_invest=0` (`−€353`), and capping `fee_warn=1.25` (`−€72`, slower bookings blocked local `backlog_near`) all confirmed keeping the calm-morning `same_day_min_supply=35, min_slack_min=135` settings through Wednesday and Thursday (`€9,988`).

4. **Friday 08:00 (`cp-supervisor-1` turns 17–20 vs `cp-supervisor-2` turns 5–6) — State-dependent Friday surplus endgame (`+€131` vs `−€93`):**
   - In **`cp-supervisor-1`** at `Fri 08:03`: `won=232`, `late=3` (`98.7%` OT), and **`unstaffed=4`** (only `1` weekend order). Weekend drivers were free! Opening Monday-due slow thin-town gates (`min_supply=3`, bypassing `thin_long_next_day` / `max_next_day_drive` for Monday-due slow options, while `same_day_min_supply=35` still blocked thin `same_day`) + `fri_same_day_max_drive=180` jumped to **`€10,119.00 (+€131 today, +€343.23 vs Champion)`**, `277` won, **`98.2%` on time (`0` extra late orders!)**. Meanwhile cutting Friday price (`price_target_win=0.48`) lost `−€22`, and capping weekend `fee_warn=1.25` lost `−€198` because thin-town gigs needed the normal `0.85→1.60` ramp to attract regional drivers.
   - **Crucial counterfactual in `cp-supervisor-2` at `Fri 08:00`:** When Monday–Thursday had `return_hub_min_supply=50, return_hub_max_drive_min=280`, Friday 08:00 arrived with **`unstaffed=7`** (`5` long Northern weekend orders already waiting for drivers). Applying the *exact same* Friday opening at `unstaffed=7` **lost `−€93` (`€9,899 → €9,806`)** because 5 new thin-town orders competed for already-committed weekend drivers! This proved Friday opening must be gated on **`unstaffed_all <= 5`**.

5. **Zero-fork reproduction from Monday 07:00 (`cp-supervisor-3`):**
   - Implemented `Desk.maybe_supervise()` in `src/spread_lab/policy.py` and ran `cp-supervisor-3` from `Mon 07:00` with zero manual turns or forks: it reproduced **`€10,119.00 (+€343.23), 277 won, 98.2% on time`** to the exact cent.

## What changed
Added `Desk.maybe_supervise()` in `src/spread_lab/policy.py` (neutral default `supervisor: bool = False`), evaluated once each weekday morning (`Mon–Fri`) at `08:00` (and reconstructed cleanly in `rejoin()` without altering `mult`):
- **Monday `08:00`:** Keep Champion defaults while learning world price level and building dealer trust.
- **Tuesday–Friday `08:00` board readout:** Reads `proj_ot = projected_on_time()`, `unstaffed_all`, `unstaffed_soon` (`lastPickupAt - now <= 24h`), `free_share = (len(drivers) - active_booked_gigs) / len(drivers)`, and `warns_yday` (`deadline_close` in prior 24h):
  - **`CALM` morning** (`proj_ot >= 0.965`, `warns_yday <= 3`, `unstaffed_soon <= 3`, `free_share >= 0.80`): sets `same_day_min_supply = sup_calm_sd_supply` (`35`) and `min_slack_min = min_slack_min - sup_calm_slack_sub` (`135`).
  - **`STRESSED` morning** (`proj_ot < 0.955`, `warns_yday >= 6`, or `unstaffed_soon >= 6`): on v3T (`d93271e`), tightening `same_day_min_supply=70, min_slack_min=170` saved warnings and raised tail on-time; once stacked on the newly promoted `cp-fees` champion (`9aa3f13`, which already solves urgent/dropped staffing via viewer offers and drop repricing), disabling stress intake-choking (`sup_stress_sd_supply=0, sup_stress_slack_add=0`) avoided turning away profitable Wednesday/Friday orders (`+€50/world` better, lifting `t` from `1.45` to `2.11`).
  - **`FRIDAY_SURPLUS` (`day == 4`)**: when not stressed, `proj_ot >= 0.965`, **`unstaffed_all <= 5`**, `warns_yday <= 4`, and `free_share >= 0.80`, opens **Monday-due (`deadline // DAY >= 7`)** slow options down to `gate_supply >= sup_fri_slow_min_supply` (`3`, strictly excluding `same_day` and Friday-deadline notes) and relaxes `fri_same_day_max_drive` to `sup_fri_sd_max_drive` (`180`).

Best stacked flags (on current Champion `9aa3f13`):
`-s supervisor=True -s sup_stress_sd_supply=0 -s sup_stress_slack_add=0 -s sup_fri_slow_min_supply=3 -s sup_fri_sd_max_drive=180`

## Results (vs the champion on the same seeds)

### A. Stacked on current Champion `9aa3f13` (`cp-fees`, dev mean `€11,679.12`, night32 mean `€12,036.75` / min OT `92.49%`)
| Set | Run folder | Mean margin | Δmargin ± SE | t | Better / worse | On-time mean (Δ) | On-time min | Worlds <92% | SAFE? |
|---|---|---:|---:|---:|---|---:|---:|---:|---|
| smoke noop (4) | `20261114-105225-cp-supervisor-v5-noop` | €11,951.98 | €+0.00 ± 0.00 | 0.00 | 0 / 0 | 96.33% (+0.00%) | 93.70% | 0 / 4 | yes |
| dev w/ stress choke (16) | `20261114-105539-cp-supervisor-v5-dev2` | €11,824.45 | €+145.34 ± 100.10 | 1.45 | 10 / 4 (2 tied) | 96.89% (-0.31%) | 93.28% | 0 / 16 | yes |
| **dev best (16)** | `20261114-105817-cp-supervisor-v5-nostress-dev` | **€11,874.36** | **€+195.25 ± 92.65** | **2.11** | **10 / 4 (2 tied)** | **96.98% (-0.21%)** | **93.36%** | **0 / 16** | **yes** |
| **night32 fresh (32)** | `20261114-110023-cp-supervisor-v5-nostress-night32` | **€12,272.90** | **€+236.15** vs `cp-fees` | — | — | **97.16%** | **92.49%** | **0 / 32** | **yes** |

### B. Standalone on starting Champion v3T `d93271e` (dev mean `€10,884.88`, night32 mean `€11,341.67` / min OT `90.57%`)
| Set | Run folder | Mean margin | Δmargin ± SE | t | Better / worse | On-time mean (Δ) | On-time min | Worlds <92% | SAFE? |
|---|---|---:|---:|---:|---|---:|---:|---:|---|
| smoke noop (4) | `20261114-094432-cp-supervisor-noop` | €10,816.98 | €+0.00 ± 0.00 | 0.00 | 0 / 0 | 95.98% (+0.00%) | 94.38% | 0 / 4 | yes |
| smoke gates (4) | `20261114-095208-cp-sup-gates-smoke` | €10,966.05 | €+149.07 ± 93.04 | 1.60 | 3 / 1 | 96.03% (+0.05%) | 94.44% | 0 / 4 | yes |
| smoke + mult recover (4) | `20261114-095410-cp-sup-full-rec85-smoke` | €10,782.10 | €-34.88 ± 30.65 | -1.14 | 2 / 2 | 96.01% (+0.03%) | 93.95% | 0 / 4 | yes |
| smoke no fri sd (4) | `20261114-100358-cp-sup-nofrisd-smoke` | €10,913.84 | €+96.86 ± 97.98 | 0.99 | 3 / 1 | 96.19% (+0.21%) | 94.44% | 0 / 4 | yes |
| smoke calm ret45 (4) | `20261114-100914-cp-sup-calmret-smoke` | €10,838.17 | €+21.19 ± 163.57 | 0.13 | 3 / 1 | 95.89% (-0.08%) | 94.44% | 0 / 4 | yes |
| **dev v3T (16)** | `20261114-102824-cp-supervisor-dev` | **€11,228.60** | **€+343.71 ± 100.49** | **3.42** | **13 / 2 (1 tied)** | **97.23% (+0.27%)** | **94.44%** | **0 / 16** | **yes** |
| night32 v3T (32) | `20261114-103535-cp-supervisor-night32` | €11,520.43 | €+178.76 vs v3T | — | — | 97.13% | 90.54% | 1 / 32 (`night-15`) | no (v3T also 90.57%) |

### Telemetry & negative findings (for the jury)
- **Friday surplus precision (`sup_fri_thin_*`):** On `cp-supervisor-v5-nostress-dev` (16 worlds), `sup_fri_surplus_fired` triggered on **8 / 16** worlds (`unstaffed <= 5` at Fri 08:00) and stayed off on the 8 heavier-backlog Fridays, winning **39 thin-town Monday-due orders** that earned **`€+3,248` net margin (`+€203/world` averaged across all 16 worlds)** with **only 1 late car (`97.4%` on-time)**.
- **Why post-freeze morning `mult` recovery (`sup_recover_frac=0.85`) failed (`−€184` vs gate supervisor on smoke):** After an **outage** day (e.g. Tuesday on `dev-01` and `dev-02`, where `mult` climbed to `1.64–1.70`), returning to normal market prices the next day hit 13 losses on the way down; `sup_recover_frac` mistook post-outage mean-reversion for a price war and pumped Thursday morning `mult` back up by `+0.23` to `+0.33`, starving Thursday wins.
- **Why emergency Thursday/Friday intake shutdown (`sup_emerg_unstaffed=12`, `20261114-104653-cp-sup-emerg-check4`) failed:** Shutting slow hub/return intake when 12–24 orders were unstaffed shrank the `won` denominator (`349 → 329` on `night-15`, `243 → 240` on `night-11`) while already-won backlog orders still went late, lowering `night-11` on-time from `93.0%` to `90.8%` and losing `−€958` on `night-15`.

## Verdict
**adopt / promote** — SAFE on both 16 dev worlds (`93.36%` min OT, `0` under 92%) and all 32 fresh `night` worlds (`32/32 SAFE`, `92.49%` min OT, `0` under 92%), adding **`€+195.25 ± 92.65` (`t = 2.11`)** on dev and **`€+236.15`** (`€12,272.90` mean margin) on 32 unseen `night` worlds on top of `cp-fees` (`€+343.71 ± 100.49`, `t = 3.42` standalone on v3T).
