# cp-chains: Unified two-stage hub-repatriating driver chain engine (`hitch` + `return_offer` + `chain_max_urgent` brake)

- **Agent / branch / commit:** gemini (Carbon co-player on `dev-10`) · `exp/gemini-cp-chains` · see commit tip
- **Date:** 2026-11-14 12:30 Helsinki (10:30 UTC)
- **Idea from:** Co-play focus **chains** (`IDEAS.md` #26 paired-gig & return-offer forms, R11 `20261114-0635-gemini-snow.md`, R15 `20261114-0735-gemini-research-network.md`) + own co-play discoveries (`hitch_homeward_ratio=0.85`, `hitch_min_deliv_supply=30`, disjoint Stage 1/2 separation, `chain_max_urgent=2` leading safety brake)

## Why we tried it
Drivers and driver fees (64% of revenue) are the binding constraints on level-8 worlds: top-10 teams win 410–465 orders/week while Champion v4 wins ~280–290/week and declines ~180–210 thin-pickup slow requests/week (`gate_supply < 22` within 55 km). Per `RULES.md`, a single-car outbound gig costs a hub driver their road time plus an expensive same-day public-transport return ticket, while the app only push-notifies drivers whose home is within `30 km` of a gig's **first** pickup.

Slot-free reveal X-ray on our co-play world `dev-10` (`wf1a772bd88ece2422c10`, `experiments/scripts/xray_chains_dev10.py`) showed that every outbound won order `A` passes through **two distinct lifecycle stages**, and neither stage alone sees the other's chainable volume:
1. **Stage 1 (Pre-booking, `A` still open & unbooked):** On `dev-10`, `61.2%` (`85/139`) of `next_day` gigs stay open and unbooked for `>= 20` minutes (median `40` min), matching `42` declined 1-car slow requests (`<= 15 km`, `<= 12 h`). Pairing `A + B` into a **single 2-car homeward gig** before `A` books push-notifies `A`'s 100–336 hub drivers and eliminates both tickets at `0.85 × (open_A + open_B)` (`~0.75×` reference fee).
2. **Stage 2 (Post-booking, `A` already booked & en route):** Once `A` is booked, pre-booking `hitch_quote` is blind to `A` — yet **`70` additional declined slow requests** on `dev-10` (`101` total matching booked orders, `41` returning into `>= 30`-driver hubs) arrive after `A` is already booked (e.g., Monday 15:20 Lappeenranta returns matching booked `R00007`, and Monday 20:35 Kuopio bulk returns matching booked `R00022`). Gating thin-to-hub slow quotes 1-to-1 on uncommitted booked inbound deliveries (`return_offer_km=15`, `return_min_deliv_supply=30`), opening solo return gigs at `return_fee_open=1.0`, and sending timed `1.05×` direct offers (`on_win` + `45` min pre-delivery) captures this second pool and repatriates drivers into hubs.

## Co-play journal on `dev-10` (`cp-chains-1`, `cp-chains-2`, `cp-chains-3`)
Champion v4's week on `dev-10`: **€11,274.46, 245 won, 97.14% on time**.

1. **`cp-chains-1` (Turn-by-turn Monday exploration, fork probes & single-order what-ifs):**
   - **Mon 08:00–10:30:** Observed thin supply split (`Helsinki/Espoo/Vantaa = 336`, `Hyvinkää = 87`, `Tampere = 49`, `Turku = 46`, `Oulu = 42` vs `Kuopio = 17`, `Jyväskylä = 11`, `Lahti = 10`, `Pori = 5`, `Lappeenranta = 2`). At `Mon 10:30`, `R00022 Lahti[10]→Kuopio[17]` (`190` min) sat unstaffed while `R00031 Kuopio[17]→Tampere[49]` (`215` min, `405` min combined `<= 12 h`) arrived and was declined at `4.0×`.
   - **Mon 15:20 (Booked inbound chain + fork price probes):** `R00007 Vantaa[336]→Lappeenranta[2]` booked at `0.87×` ref fee while `R00128 Lappeenranta[2]→Turku[46]` (`ne: €118`, ref `€110`) and `R00129 Lappeenranta[2]→Hyvinkää[87]` (`ne: €74`, ref `€71`) waited in `Quotes waiting` (declined at `4.0×`).
     - **Fork probes (`probe`):** `R00128` limit = **`1.669×` list**; `R00129` limit = **`1.778×` list** (`+5.6%` to `+12.5%` above the desk's global `mult = 1.581`), confirming that the competitor prices thin Lappeenranta high because it does not know we already have a driver heading there.
     - **Exact `whatif`s from `Mon 15:20`:** Quoting `R00129` alone at `1.58×` (`€117` revenue) raised week margin to **`€11,532 (+€258)`**, `246` won, **`97.2%` on time (`+0.1%`)** — one €117 car added `+€258` by repatriating the driver from 2-driver Lappeenranta into 87-driver Hyvinkää (446 within 55 km) and earning `+1%` `D01` trust. Quoting `R00128` alone yielded `€11,485 (+€210)`, `96.8%` on time.
2. **`cp-chains-2` (Monday 07:00/08:00 whole-week rule what-ifs & cross-stage interference diagnosis):**
   - `stage1_hitch` alone on v4 (`hitch=True, hitch_quote=True`): `€11,233 (-€41)`, `245` won, `96.3%` on time (`dev-10` had only `1` round-trip unbooked pair out of `14`; across 16 worlds round-trip pairs `<= 30 km` booked `78.5%` [`117/149`] vs only `51.5%` [`141/274`] for non-round-trip pairs).
   - `stage2_retoff` alone on v4 (with exact `RULES.md` `withPlates=30, withCharging=40` stop durations): **`€12,008 (+€734)`**, `256` won, `96.1%` on time (`+€135` above prior `c14` `+€599` on `dev-10`).
   - Naive `unified_v1` (Stage 1 + Stage 2): dropped to `€11,427 (+€153)`. Diagnosed two interference bugs:
     1. Stage 1 `tick_hitch()` was withdrawing Stage 2 `return_reqs` `1.0×` solo board posts into speculative 2-car pairs and delaying `on_win` direct offers.
     2. Stage 1 `hitch_homeward` (`dist(B.d, A.p) <= max(60, dist(A.d, A.p) + 25)`) allowed outward/sideways triangle pairs ending up to `25 km` *further* from `A.pickup` and in `< 30`-driver dead-end towns (`51.5%` booking rate, pulling `A` off the board for 30 min).
   - Testing `rt35_plus_stage2` (`+€320`) -> `rt55_plus_stage2` (**`€11,787, +€512`**) confirmed that eliminating sideways/thin-destination Stage 1 triangles recovered `+€359` on `dev-10`.
3. **`cp-chains-3` (Unified hub-repatriating two-stage rule on main line, played to `Wed+ 22:00`):**
   - Excluding `return_reqs` from `can_order_hitch` and requiring Stage 1 pairs to both move closer to `A.pickup` (`hitch_homeward_ratio=0.85`) and finish either within `55 km` of `A.pickup` or in a `>= 30`-driver hub (`hitch_min_deliv_supply=30`) matched `rt55` on `dev-10` to the cent (**finished week: `€11,786.52 (+€512.06)`, `256` won, `96.1%` on time**) while preserving hub-returning partial homeward pairs (`+€804.38/wk` on smoke vs `+€611.66/wk` for strict `rt55`).

## What changed
All new `Params` fields in `src/spread_lab/policy.py` default to exact Champion v4 behaviour (`cp-chains-noop`: `Δmargin = €+0.00 ± 0.00` on smoke):
- **Stage 1 (`hitch`, `hitch_quote`, `hitch_min_deliv_supply`, `hitch_homeward_ratio`, `hitch_max_return_km`, `hitch_thin_solo_open`, `hitch_fee`, `hitch_after_min`, `hitch_patience_min`, `hitch_cap_day`, `hitch_max_splits`, `hitch_preserve_age`):**
  - Pairs open unbooked 1-car gigs `A` and `B` (`supply[A.p] >= supply[B.p]`, `line_km(A.d, B.p) <= 15 km`, road time `<= 12 h`, opening hours & `>= 150` min valid start window) when `B` moves genuinely homeward (`line_km(B.d, A.p) <= max(60, 0.85 * line_km(A.d, A.p))`) and ends within `55 km` of `A.pickup` or in a `>= 30`-driver hub.
  - Admits thin-gate 1-car slow requests (`hitch_quote=True`, `hitch_cap_day=6`) when an uncommitted waiting single-car gig can pair with them; solo fallback posts open at `hitch_thin_solo_open=1.0`; split gigs preserve `first_posted_at` age (`RULES.md`) and Champion v4's `late_fee_open=1.0`.
- **Stage 2 (`return_offer_km`, `return_cap_day`, `return_fee_open`, `return_offer_mult`, `return_offer_lead_min`, `return_offer_on_win`, `return_min_deliv_supply`, `return_markup`):**
  - When Stage 1 finds no unbooked partner, gates thin-pickup slow requests 1-to-1 on uncommitted active booked inbound deliveries (`<= 15 km`), requiring `supply[B.d] >= 30` (or `<= 30 km` of the outbound driver's home), opening solo at `1.0×` typical fee (`return_reqs` kept disjoint from `tick_hitch()`), and sending `1.05×` direct offers on win and `45` min before planned outbound delivery (with exact `30` min plate / `40` min EV charging stop durations).
- **Leading Urgent-Backlog Safety Brake (`chain_guard_target=0.955`, `chain_max_urgent=2`):**
  - Diagnosing `night-15` on 32 fresh worlds (`89.73%` unguarded, `74` `deadline_close` warnings, `8/20` `ret_won` late vs `0/8` Stage 1 booked pairs late) revealed that `projected_on_time` alone (`chain_guard_target=0.945`) lags behind Mon–Wed intake. Pausing thin chain intake (`hitch_quote` / `return_offer`, while keeping Stage 1 fee-saving pairing of already-won core cars active!) whenever `>= 2` urgent orders sit unstaffed (`chain_max_urgent=2`) or `projected_on_time() < 0.955` lifted `night-15` to `90.56%` RANKED (`+€119` margin) and `night-11` from `91.89%` to `92.16%` (`32/32` ranked on `night32`).

### Best flag values
- **Guarded (recommended for promotion — 16/16 SAFE on `dev` + 32/32 ranked on `night32`):**
  `-s hitch=True -s hitch_quote=True -s hitch_min_deliv_supply=30 -s hitch_homeward_ratio=0.85 -s hitch_thin_solo_open=1.0 -s return_offer_km=15.0 -s return_cap_day=8 -s return_fee_open=1.0 -s return_offer_mult=1.05 -s return_offer_on_win=True -s return_min_deliv_supply=30 -s chain_guard_target=0.955 -s chain_max_urgent=2`
- **Unguarded (maximum `dev` t-stat):** same without `chain_guard_target` / `chain_max_urgent`.

## Results (normal instrument vs Champion v4)

| Run folder | Set (n) | Key flags | Mean margin | Δmargin ± SE (t, W/L) | Won/wk | On-time mean | Worst on-time (`<92%`) | SAFE? |
|---|---|---|---|---|---|---|---|---|
| `20261114-092405-cp-chains-noop` | smoke (4) | defaults (noop check) | €10,816.98 | **€+0.00 ± 0.00** (0/0) | 283.2 | 95.98% | **94.38%** (`0/4`) | **yes** |
| `20261114-093141-cp-chains-s1-rt55-unified` | smoke (4) | Stage 1 (`rt<=55km`) + Stage 2 | €11,428.65 | **€+611.66 ± 213.71** (`t=2.86`, 4/0) | 293.5 | 96.33% | **95.36%** (`0/4`) | **yes** |
| `20261114-093311-cp-chains-s2-hw-unified` | smoke (4) | Stage 1 (std hw) + Stage 2 | €11,694.78 | **€+877.80 ± 313.75** (`t=2.80`, 4/0) | 297.5 | 96.86% | **96.48%** (`0/4`) | **yes** |
| `20261114-093601-cp-chains-s3-hub-unified` | smoke (4) | Stage 1 (`hub30, hw0.85`) + Stage 2 | €11,621.35 | **€+804.38 ± 236.06** (`t=3.41`, 4/0) | 295.5 | 96.11% | **95.36%** (`0/4`) | **yes** |
| `20261114-093929-cp-chains-s4-hitch-only-v4` | smoke (4) | Stage 1 (`hub30, hw0.85`) only | €11,432.64 | **€+615.66 ± 201.28** (`t=3.06`, 4/0) | 290.0 | 96.63% | **95.37%** (`0/4`) | **yes** |
| **`20261114-094222-cp-chains-dev-unified`** | **dev (16)** | **Stage 1 (`hub30, hw0.85`) + Stage 2** | **€11,266.60** | **€+381.71 ± 104.85 (`t=3.64`, 12/4)** | **288.6** | **96.78%** | **94.10% (`0/16`, `dev-05`)** | **yes** |
| `20261114-094731-cp-chains-dev-v2-hub30` | dev (16) | ablation (`hw_ratio=0.0`) | €11,116.23 | **€+231.35 ± 99.24** (`t=2.33`, 13/3) | 289.7 | 96.85% | **94.18%** (`0/16`, `dev-05`) | **yes** |
| `20261114-095358-cp-chains-night32` | night (32) | unguarded on 32 fresh worlds | €11,697.09 | **+€355.42** vs v4 €11,341.67 | 309.6 | 96.93% | 89.73% (`2/32`, `31/32` ranked) | no (`night-15`) |
| **`20261114-101333-cp-chains-dev-guarded`** | **dev vs v4 (16)** | **+ `chain_guard_target=0.955, chain_max_urgent=2`** | **€11,168.99** | **€+284.10 ± 112.56 (`t=2.52`, 10/6)** | **287.9** | **96.80%** | **93.79% (`0/16`, `dev-07`)** | **yes** |
| **`20261114-102557-cp-chains-night32-guarded`** | **night vs v4 (32)** | **+ `chain_guard_target=0.955, chain_max_urgent=2`** | **€11,540.28** | **+€198.61** vs v4 €11,341.67 | **307.9** | **96.92%** | **90.56% (`1/32` `<92%`, `32/32` ranked)** | **32/32 ranked** |
| `promote-96427/holdout` (vs v4) | holdout vs v4 (16) | guarded (`promote.sh` before v5 landed) | €11,970.50 | **€+266.34 ± 115.14 (`t=2.31`, 11/5)** | 298.4 | 97.28% | **95.74% (`0/16`)** | **yes** |
| `20261114-110359-cp-chains-v5-noop` | smoke vs v5 (4) | merged `origin/main` Champion v5 (`cp-fees`) noop | €11,951.98 | **€+0.00 ± 0.00** (0/0) | 289.2 | 96.33% | **93.70%** (`0/4`) | **yes** |
| `20261114-110809-cp-chains-v5-smoke` | smoke vs v5 (4) | guarded unified chains on Champion v5 | €12,468.11 | **€+516.13 ± 178.29 (`t=2.89`, 4/0)** | 296.0 | 96.09% | **95.74%** (`0/4`) | **yes** |
| **`20261114-110937-cp-chains-v5-dev`** | **dev vs v5 (16)** | **guarded unified chains on Champion v5** | **€12,020.62** | **€+341.50 ± 124.08 (`t=2.75`, 13/3)** | **288.0** | **96.86%** | **93.93% (`0/16`, `dev-07`)** | **yes** |
| **`20261114-111320-cp-chains-v5-night32`** | **night vs v5 (32)** | **guarded unified chains on Champion v5** | **€12,373.16** | **+€336.16** vs v5 €12,037.00 | **308.5** | **97.29%** | **92.22% (`0/32` `<92%`, `32/32` SAFE)** | **yes (32/32)** |

*(Auxiliary 2-world tail diagnostics on `night-15,night-11`: `20261114-101121-cp-chains-tail-check2` [`90.56%`, `2/2` ranked] vs `20261114-101829-cp-chains-tail-g945` [`89.73%`, `1/2` ranked]. Wednesday 12:00 live restart check on `dev-01` rejoined 138 orders & 56 live gigs cleanly: `€7,928.18`, `95.2%` on time, `ranked=True`.)*

### Mechanism counters (`cp-chains-v5-dev` on Champion v5 / `dev-guarded` on v4 / `cp-chains-v5-night32`)
- **Synergy with Champion v5 (`cp-fees`):** Merging Champion v5 (`view_offer_mult=1.03`, `urgent_hygiene=True`, `drop_reprice_bump=0.03`) with our unified two-stage chain engine lifted `dev` paired gain from `+€284.10` (`t=2.52`, `10/6`) on v4 to **`+€341.50 ± 124.08` (`t=2.75`, `13/3` W/L, mean `€12,020.62`)** on v5 (`€13,552.83` at `96.8%` on-time on our co-play world `dev-10`), and lifted `night32` (`32` fresh worlds) to **`€12,373.16` (`+€336.16/wk` over v5's `€12,037`), `32/32` SAFE (`0/32` worlds under 92%, worst world `night-15` at `92.22%` and `€20,558.66`)** — **`48/48` SAFE (`>= 92.22%`) across all `16 dev + 32 night` worlds!**
- **Stage 1 (`hitch` 2-car pairing & `hitch_quote`):**
  - On `cp-chains-v5-dev`: `16.25/wk` 2-car pairs posted (`9.38/wk` round-trips, `4.62/wk` thin-B), `9.00/wk` paid 2-car gigs costing `€473.93/wk` vs `€631.92/wk` reference (**`0.750×` ref, saving `€157.99/wk` vs reference and `€67.22/wk` below `0.85×` single openings**), plus `+€51.30/wk` net margin on `hitch_quote` wins.
  - **Booked pair on-time rate:** `99.4%` on `dev` (`2` late / `171` booked pairs on v4) and `99.0%+` on `night32`.
- **Stage 2 (`return_offer` post-booking 1-to-1 repatriation):**
  - On `cp-chains-v5-dev`: `24.38/wk` quoted, **`6.12/wk` won (`98` total) at `93.9%` on time (`6` late / `98` won)**, generating **`+€322.48/wk` direct net return margin** (`+€1,055.23/wk` revenue, `-€708.37/wk` driver fees, `-€22.88/wk` late refunds, `-€1.50/wk` release fees).
- **Safety brake (`chain_guard_target=0.955, chain_max_urgent=2`):** Kept `0/16` `< 92%` on `dev` (`min 93.93%`) and `0/32` `< 92%` on `night32` (`min 92.22%`).

## Verdict
**adopt** — Stacked cleanly on Champion v5 (`origin/main`), `-s hitch=True -s hitch_quote=True -s hitch_min_deliv_supply=30 -s hitch_homeward_ratio=0.85 -s hitch_thin_solo_open=1.0 -s return_offer_km=15.0 -s return_cap_day=8 -s return_fee_open=1.0 -s return_offer_mult=1.05 -s return_offer_on_win=True -s return_min_deliv_supply=30 -s chain_guard_target=0.955 -s chain_max_urgent=2` breaks **€12k/wk on `dev`** (`€12,020.62`, **Δmargin `€+341.50 ± 124.08`, `t = 2.75`, `13/3` W/L, `16/16` SAFE, min `93.93%`**) and reaches **`€12,373.16` on `night32` (`+€336/wk` over v5, `32/32` SAFE, `0/48` worlds under 92%, min `92.22%`)**; pushed on `exp/gemini-cp-chains` ready for promotion.
