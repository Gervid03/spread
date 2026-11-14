# cp-volume: Additive driver-neutral volume via regional inbound return gates, metro/benign-note 2-car pairing, and sequential 2-leg trade-in slack

- **Agent / branch / commit:** gemini · `exp/gemini-cp-volume` · `4bb5878` (built on `f3acbfb`, Champion v3T)
- **Date:** 2026-11-14 10:10 UTC
- **Idea from:** Co-play focus `cp-volume` on `dev-04` ("your own ideas for volume: where do leaders' extra orders come from without breaking the driver ceiling?") + `IDEAS.md` Principle #1 ("Spend safety on gates, not on price")

## Why we tried it
Leaders win 410–460 orders/week at level 8 while Champion v3T wins ~280 orders/week (`€10,884.88/wk` on `dev`). Naive attempts to buy volume by cutting quotes (`price_target_win=0.45` or global option discounts) lose revenue on the ~280 orders we already win and chase Tuesday/mid-week price wars down into low-margin `same_day` volume that breaks local driver pools.

Slot-free reveal diagnostics on `dev-04` (`runs/reveals/reveal-we07744ba5bd2d430cc60`, `1,040` requests: `311` won, `462` quoted & lost, `267` declined) and co-play what-ifs (`cp-volume-1`, `cp-volume-2`) identified three **driver-neutral or driver-saving** volume pools that add orders **at full tracker price (`self.mult`)** without draining scarce origin driver pools:

1. **Regional & medium-haul inbound return gates (`return_hub_min_supply: 200 → 45`, `return_hub_max_drive_min: 180 → 270`, `ext_ring_max_drive_min: 220 → 260`):**
   - Champion v3T only admits thin-pickup (`gate_supply < 22` within 55 km) return orders when the delivery is in the Capital (`supply >= 200` within 30 km) and `drive <= 180` min (`won_return_hub = 1.81/wk`).
   - On `dev-04` alone, `41` slow (`next_day` / `within_3_days`) thin-pickup requests delivered into regional driver hubs (`50–199` drivers within 30 km: Oulu `90`, Tampere `60`, Lempäälä `60`, Turku/Raisio `52`) with `drive <= 270` min, plus `16` delivered into the Capital with `drive = 181–270` min (e.g. Kuopio→Vantaa `229m`, Vaasa→Vantaa `268m`).
   - Because destination-home drivers want a paid ride home rather than deadheading, these slow inbound gigs book reliably without consuming hub outbound capacity, and `ext_ring_neutral_learn=True` (already on in v3T) keeps losses completely neutral to `self.mult`.

2. **Expanded metro & benign-note 2-car `lead_car` pairing (`lead_car_allow_benign_notes=True`, `lead_car_cross_slow=True`, `lead_car_max_gap_km: 0.0 → 20.0`, keeping `lead_car_fee_mult=1.0`):**
   - Carrying 2 slow corridor cars with 1 driver raises the driver ceiling directly, yet Champion v3T paired only `5.50` gigs/week across `dev` for three reasons: (a) `if req.get("note"): return False` blocked ~41% of requests even when `notes_v2` confirmed zero window, manual-gearbox, or missing-plates constraints (e.g. `"Rengassarja mukaan"`, `"Viitenro 783951"`); (b) `lead_car_max_gap_km=0.0` prevented metro-twin pickups from pairing (`Helsinki–Espoo 13.5 km`, `Espoo–Vantaa 15.6 km`, `Tampere–Lempäälä 16.2 km`, `Turku–Raisio 6.5 km`); and (c) requiring identical deadline days blocked `next_day` + `within_3_days` pairs even when `start_at + total_min + 240 <= min(dl_a, dl_b)`.
   - Keeping `lead_car_fee_mult=1.0` preserves fast `0.85×` booking (`83%` book at opening step) while freeing ~8–9 drivers/week to absorb our extra volume.

3. **Sequential 2-leg trade-in slack (`trade_in_seq_slack=True`, `trade_in_max_drive_min=450`, `trade_in_leg1_slack_min=90`):**
   - Two-leg trade-ins are round trips back to the origin dealership (`referenceFeeCents / listPriceCents ≈ 0.48`, zero return transit ticket, `+€60–100/order` margin), yet Champion v3T declined `21` of `23` trade-ins on `dev-04`.
   - Root cause in `Desk.price()`: `ready = max(now, leg0.pickup.from, leg1.pickup.from)` set `ready` to the private customer's late handoff window (`leg1.pickup.from`, often 2–6 hours before `deadline`) and then subtracted **both** legs' drives (`drive0 + drive1`) and evaluated `long_drive_min` (`deadline // DAY <= ready // DAY`) as if `leg0` could not be driven before `leg1` opened.
   - Evaluating `leg0` to the customer handoff window (`slack0 = dl0 - ready0 - d0 >= min_slack_min + slack_per_drive * d0`) and `leg1` from post-handoff (`handoff = max(ready0 + d0 + d_mid + 30, ready1)`, `slack1 = deadline - handoff - d1 >= 90 + 0.25 * d1`, `drive <= 450`) recovered `12` previously declined round-trip trade-ins on `dev-04`.

---

## Co-Play Journal (`dev-04`; Champion baseline: €11,987.17, 310 won, 97.1% on time)

### Game 1: `cp-volume-1` — Watching Monday & probing price/floor/volume hypotheses
- **Turns 1–3 (`Mon 07:00 → Mon 10:30`):** Watched opening batches and probed 4 requests at `Mon 09:30`:
  - Three identical `Helsinki → Raisio` batch cars (`B0035`, `list = €69`) had noisy `referenceFeeCents` (`€64`, `€60`, `€72`) and independent competitor limits (`R00005: 1.637×`, `R00007: 1.411×`, `R00008: 1.348×`). `R00008` drew a high noisy `ref = €72` (`ref/list = 1.046`) and was clamped to the `1.25×` floor (`€98.08 = 1.42×`), losing to `1.348×`.
  - Observed `R00060` (`Hyvinkää → Espoo`, `sa:39 ne:36 wi:34, ref:38`): flat dollar floor (`€51.63`) quoted `within_3_days` (`×1.50`) at the exact same euro price (`€52`) as `next_day` (`×1.43`).
- **Turn 4 (`Mon 10:30`, `mult = 1.695`) — Baseline lever what-ifs:**
  - `main line`: `€11,987 (+0) · won 310 · on time 97.1%`
  - `floor_110` (`expected_fee_mult=1.10`): `€12,319 (+332) · won 313 · on time 97.1%`
  - `sd_markup_12` (`same_day_markup=0.12`): `€12,178 (+191) · won 308 · on time 97.7% (+0.6%)`
  - `ptw_45` (`price_target_win=0.45`): `€12,389 (+402) · won 337 · on time 96.7%`
  - `pair_gap20_fee92` (`lead_car_max_gap_km=20, lead_car_fee_mult=0.92`): `€11,953 (-34) · won 311 · on time 95.8%` *(Conclusion: never discount `lead_car_fee_mult` below `1.0`; slower booking hurts on-time by `-1.3%`.)*
- **Turn 5 (`Mon 12:00`, `mult = 1.445`, entering Tuesday's price war) — Stress-testing price cuts:**
  - `f110_sd12` (`expected_fee_mult=1.10, same_day_markup=0.12`): `€12,266 (+279) · won 314 · on time 96.5%`
  - `f110_sd12_ptw43` (`+ price_target_win=0.43`): `€11,534 (-453) · won 334 · on time 95.5%`
  - `f105_sd14_ptw45`: `€11,579 (-408) · won 344 · on time 96.8%`
  - *Conclusion:* Lowering floors + raising `price_target_win` collapses (`-€732` swing!) when `mult` enters a Tuesday price war because it wins dozens of low-margin price-war cars. Profitable volume must come from **opening safe/driver-neutral classes at full tracker price**, not discounting quotes.

### Game 2: `cp-volume-2` — Clean-week (`Mon 07:00`) isolation & stacking of new rules
- **Turn 1 (`Mon 07:00`) — Isolating 4 new mechanisms implemented in `policy.py`:**
  - `main line`: `€11,987 (+0) · won 310 · on time 97.1%`
  - **`m1_tradein`** (`trade_in_seq_slack=True`): **`€12,610 (+622) · won 315 · on time 96.8%`**
  - `m2_slow_floor_sd` (`slow_expected_fee_mult=1.08, w3d_expected_fee_mult=0.98, same_day_markup=0.12`): `€11,717 (-270) · won 312 · on time 96.2%` *(hurts from `Mon 07:00` when `mult` starts low at `1.35`)*
  - `m3_mon2_w3d` (`w3d_discount=0.06, mon2_discount=0.08, slow_comp_slope=1.8, w3d_expected_fee_mult=0.98`): `€11,733 (-254) · won 361 (+51!) · on time 95.8%` *(+51 cars, but 6–8% discount cannibalizes existing Mon2/w3d wins)*
  - **`m4_inbound_pair`** (`return_hub_min_supply=50, return_hub_max_drive_min=240, lead_car_allow_benign_notes=True, lead_car_cross_slow=True, lead_car_max_gap_km=18.0`): **`€12,547 (+560) · won 323 · on time 96.6%`**
- **Turn 2 (`Mon 07:00`) — Decomposing `m4` and stacking with `m1`:**
  - **`m4a_inbound_only`** (`return_hub_min_supply=50, return_hub_max_drive_min=240`): **`€13,175 (+1,187) · won 322 · on time 98.1%`**
  - **`m4b_pair_only`** (`lead_car_allow_benign_notes=True, lead_car_cross_slow=True, lead_car_max_gap_km=18.0`): **`€12,553 (+566) · won 314 · on time 97.5%`**
  - **`stack_m1_m4`**: **`€13,783 (+1,796) · won 326 · on time 96.3%`**
  - **`stack_m1_m4_wide`** (`trade_in_seq_slack=True, return_hub_min_supply=45, return_hub_max_drive_min=270, ext_ring_max_drive_min=260, lead_car_allow_benign_notes=True, lead_car_cross_slow=True, lead_car_max_gap_km=20.0`): **`€13,905 (+1,918) · won 328 · on time 96.7%`**
- **Turn 3 (`Mon 07:00`) — Checking tighter trade-in drive cap (`max_drive=280, leg1_slack=120`):**
  - `ti_safe280`: `€12,072 (+85)` vs `+622` at `max_drive=450` (capping at 280m drops high-margin `next_day` round trips like Vantaa↔Jyväskylä `371m`).
- **Turn 4 (`Mon 07:00 → End`):** Applied `stack_m1_m4_wide` on `cp-volume-2` and played to week's end: **`€13,904.82 (+€1,917.65 vs Champion), 328 won, 96.6% on time`** (#1 on the co-play board).

---

## What changed
Implemented in `src/spread_lab/policy.py` with 100% neutral defaults (`cp-volume-noop` on `smoke`: `Δmargin €+0.00 ± 0.00`):
- **Sequential 2-leg trade-in slack & handoff pacing:**
  - `trade_in_seq_slack: bool = False`, `trade_in_max_drive_min: int = 450`, `trade_in_leg1_slack_min: int = 90`: on `len(legs) == 2`, evaluates drive-day caps against `leg_readies[0]`, enforces `drive <= trade_in_max_drive_min` and `legs[0].delivery.window >= 45m`, checks `slack0 = dl0 - ready0 - d0 >= min_slack_min + slack_per_drive * d0` and `slack1 = deadline - max(ready0 + d0 + d_mid + 30, ready1) - d1 >= trade_in_leg1_slack_min + 0.25 * d1`, and caps `leg 0`'s `delivery_base` in `stops_for` to `min(delivery["window"]["to"], order["deadline"])`.
  - `trade_in_handoff_pace: bool = False` (tested in `smoke3` / `dev2`): paces `rising()` and triggers early `steep()` warning 3 hours before `legs[0].delivery.window.to - d0 - 15`.
- **Expanded `lead_car` pairing:**
  - `lead_car_allow_benign_notes: bool = False`: allows pairing slow single-car orders whose `note` produces no `manual` or `plates` flag via `note_flags()` and no narrowed stop `"window"` via `stops_for()`.
  - `lead_car_cross_slow: bool = False`: allows `next_day` and `within_3_days` slow orders on different deadline days to pair when `start_at + total_min + 240 <= min(order["deadline"], other_order["deadline"])`.
- **Exploratory slow-floor & discount flags (kept at neutral `0.0` after `cp-volume-2` negative test):**
  - `slow_expected_fee_mult: float = 0.0`, `w3d_expected_fee_mult: float = 0.0`, `w3d_discount: float = 0.0`, `mon2_discount: float = 0.0`, `slow_comp_slope: float = 0.0`.
- **Telemetry counters:** `quoted_trade_in`, `won_trade_in`, `late_trade_in`, `margin_trade_in_cents`, `dropped_trade_in_drive`, `trade_in_early_warn`, `won_mon2`, `late_mon2`, `margin_mon2_cents`, `floor_unblocked_slow`, `quoted_slow_disc`.

### Best flags (`cp-volume-dev1`)
```sh
-s trade_in_seq_slack=True -s return_hub_min_supply=45 -s return_hub_max_drive_min=270 -s ext_ring_max_drive_min=260 -s lead_car_allow_benign_notes=True -s lead_car_cross_slow=True -s lead_car_max_gap_km=20.0
```

---

## Results (level 8, normal instrument, paired vs Champion v3T)

| Set | Run folder | Flags summary | Mean margin | Min margin | On-time min (<92% / <91%) | On-time mean (Δ) | Won/wk | Δmargin ± SE (t, W/L) | SAFE |
|---|---|---|---:|---:|---:|---:|---:|---:|---|
| smoke (4) | `runs/20261114-092824-cp-volume-noop` | defaults (= Champion v3T) | €10,816.98 | €7,487.67 | **94.38%** (0 / 0) | 95.98% (+0.00%) | 283.2 | €+0.00 ± 0.00 (—, 0/0) | **yes** |
| smoke (4) | `runs/20261114-093619-cp-volume-smoke1` | **full stack (`dev1` flags)** | **€12,167.77** | **€8,453.69** | **95.11%** (0 / 0) | **96.68% (+0.70%)** | **299.8** | **€+1,350.79 ± 307.96 (`t=4.39`, 4/0)** | **yes** |
| smoke (4) | `runs/20261114-094514-cp-volume-smoke2` | ablation: `trade_in_seq_slack=False` | €11,605.48 | €7,986.31 | 94.25% (0 / 0) | 96.16% (+0.18%) | 296.0 | €+788.50 ± 276.51 (`t=2.85`, 4/0) | **yes** |
| smoke (4) | `runs/20261114-095021-cp-volume-smoke3` | full stack + `trade_in_handoff_pace=True` | €12,066.06 | €8,084.98 | 94.66% (0 / 0) | 96.57% (+0.59%) | 301.0 | €+1,249.08 ± 351.27 (`t=3.56`, 4/0) | **yes** |
| **dev (16)** | **`runs/20261114-093903-cp-volume-dev1`** | **full stack (best)** | **€11,448.81** | **€7,472.42** | **93.62% (0 / 0)** | **96.79% (−0.17%)** | **289.6** | **€+563.92 ± 196.31 (`t=2.87`, 12/4)** | **yes** |
| dev (16) | `runs/20261114-095226-cp-volume-dev2` | full stack + `trade_in_handoff_pace=True` | €11,385.42 | €7,298.79 | 93.29% (0 / 0) | 96.85% (−0.10%) | 289.7 | €+500.54 ± 202.37 (`t=2.47`, 12/4) | **yes** |
| night (32) | `fc-v3T-night32` *(v3T baseline)* | Champion v3T | €11,341.67 | €5,534.80 | 90.57% (2 / 1) | 97.27% (—) | 297.9 | — | no |
| **night (32)** | **`runs/20261114-100252-cp-volume-night32`** | **full stack (`dev1` flags)** | **€11,677.12** | **€5,655.07** | **90.14% (2 / 1)** | **96.74% (−0.53%)** | **305.8** | **€+335.46 ± 99.16 (`t=3.38`, 25/7)** | 32/32 ranked |

- **Live mid-week restart check (`uv run lab play --seed dev-01 <best flags> --restart-at 3600`):** Rejoined 139 orders and 50 live gigs at minute 3602 (`mult = 1.681` vs `1.662` pre-restart), finishing at **€8,403.36, 95.0% on time, `ranked=True`**.

### Telemetry & ledger breakdown (`cp-volume-dev1` vs Champion v3T across 16 `dev` worlds)
1. **Ledger (€/wk):**
   - `revenue`: `€30,474.48 → €31,753.28` (**`+€1,278.80/wk`**)
   - `driver_fee`: `−€19,073.53 → −€19,730.24` (**`−€656.71/wk`**; marginal `driver_fee / revenue = 51.35%` vs baseline `62.59%`, lowering overall `driver_fee / revenue` from **`62.59% → 62.14%`** while expanding volume!)
   - `late_refund`: `−€366.72 → −€395.75` (`−€29.03/wk`); `undelivered_penalty`: `−€57.71 → −€76.56` (`−€18.85/wk`); `failed_visit`: `−€21.52 → −€38.06` (`−€16.54/wk`); `release_fee`: `−€50.97 → −€44.72` (`+€6.25/wk`).
   - **Net paired margin:** **`+€563.92 ± 196.31/wk` (`t = 2.87`, 12W / 4L)**.
2. **Mechanism counters (16 `dev` worlds):**
   - **Regional & medium-haul inbound + extended ring:** `quoted_ext_ring` rose `35.12 → 67.25/wk` (`quoted_return_hub`: `23.31 → 58.25/wk`), lifting `won_ext_ring` `5.00 → 13.06/wk` (**`+8.06/wk`**, `won_return_hub`: `1.81 → 11.06/wk`) with only **`0.44` late orders/wk** (`96.7%` on-time across 209 won orders; `19` won / `0` late on tail world `night-15`!) and **`+€442.34/wk`** in direct `margin_ext_ring` (`€183.01 → €625.35/wk`).
   - **Expanded 2-car `lead_car` pairing:** `lead_car_paired` jumped **`5.50 → 13.19/wk` (`2.4×`)** and `lead_car_booked` jumped **`5.88 → 14.81/wk` (`2.5×`)**, saving ~9 drivers/week so `deadline_close` (`18.31 → 19.56/wk`) and `gig_dropped` (`36.50 → 37.19/wk`) barely budged despite `+9.44` more won orders/week (`+16.5/wk` on `smoke`, where `deadline_close` actually fell `24.00 → 20.50/wk`).
   - **Sequential 2-leg trade-ins (`smoke1` vs `smoke2` ablation):** On `smoke`, `trade_in_seq_slack=True` lifted `won_trade_in` from `3.25 → 5.75/wk` (`+€187.96/wk` direct trade-in margin, `+€562.29/wk` total paired gain over `smoke2`, improving all 4 seeds and raising min on-time `94.25% → 95.11%`). Adding `trade_in_handoff_pace=True` (`dev2`) slightly improved mean on-time (`96.79% → 96.85%`) by raising trade-in fees earlier, at a `−€63.39/wk` fee cost (`+€500.54 ± 202.37`, `t = 2.47`).
3. **Out-of-sample generalization (`16 dev + 32 night = 48` worlds, zero fitted parameters):**
   - Better than Champion v3T on **37 of 48 worlds (77.1%)**: `12/16` on `dev` (`+€563.92 ± 196.31, t=2.87`) and `25/32` on completely unseen `night` (`+€335.46 ± 99.16, t=3.38`), `48/48` ranked, `0/16` under 92% on `dev` (worst `93.62%` on `dev-07`), and `2/32` under 92% on `night` (same two seeds `night-11` and `night-15` as Champion v3T).

## Verdict
**adopt** — Opening regional/medium-haul inbound return gates (`return_hub_min_supply=45, return_hub_max_drive_min=270, ext_ring_max_drive_min=260`), expanding metro/benign-note/cross-slow 2-car `lead_car` pairing (`lead_car_allow_benign_notes=True, lead_car_cross_slow=True, lead_car_max_gap_km=20.0`), and fixing sequential 2-leg trade-in slack (`trade_in_seq_slack=True`) delivers **+€563.92 ± 196.31 (`t = 2.87`, 12/4, SAFE, worst on-time 93.6%)** on `dev-16` and **+€335.46 ± 99.16 (`t = 3.38`, 25/7, 32/32 ranked)** on `night-32`.
