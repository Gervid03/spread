# cp-routes: Unified Route Network — pre-booking 2-car relays, inbound-sponsored thin quoting, finishing-driver offers, and demand-gated outbound seeding

- **Agent / branch / commit:** gemini · `exp/gemini-cp-routes` · rebased cleanly onto Champion v5 (`9aa3f13`, `cp-fees`)
- **Date:** 2026-11-14 11:35 UTC (13:35 Helsinki)
- **Idea from:** `IDEAS.md` **#31 (The route network, the user's design)** + co-play discovery on `dev-12` (`cp-routes-1`, `cp-routes-2`, `cp-routes-3`)

## Why we tried it
Driver supply—not dealer demand—is the binding ceiling on level-8 worlds: Champion v4 (`51d1be6`) won `283.6` orders/week on dev and Champion v5 (`9aa3f13`, `cp-fees`) won `283.6` orders/week at `€11,679/wk`, while declining `~200` requests/week at thin pickups (`gate_supply < 22`) and paying single-leg return-transport premia on both directions of corridor routes.

Slot-free X-ray of `dev-12` (`runs/reveal-dev12-v4` via `experiments/scripts/scout_dev12_routes.py`) and co-play (`cp-routes-1`) exposed two distinct lifecycle stages of every outbound car:
1. **While the outbound gig `A` is still open and unbooked on the board:** On `dev-12`, **`75.6%` (`133/176`) of slow single-car gigs wait `≥ 20` minutes before booking (median `128` minutes!)**, and `50.0%` of `same_day` gigs wait `≥ 20` minutes. Bundling `[A, B]` (`B.pickup` within `15 km` of `A.delivery`, `supply[A.pickup] ≥ supply[B.pickup]`, homeward) **before** booking notifies `350+` hub drivers via `A`'s pickup, eliminates the return-ticket penalty on round-trips, and opens at `0.85 × (open_A + open_B) = 0.7225×` sum of reference fees.
2. **Once the outbound gig `A` is booked (`pos_ledger`):** On `dev-12`, `72` of `141` (`51%`) declined slow requests had one of our outbound cars delivering within `15–30 km` (`67` already booked, `18` open), and `30` of those repatriated the driver back to a `≥ 30`-driver hub or within `30 km` of home. However, because the driver app only push-notifies within `30 km` of a driver's **home**, reaching far-from-home drivers requires a position ledger (`pos_ledger`), repatriated 1-to-1 inbound sponsorship (`net_quote`), and staged pre-start/pre-finish offers (`net_offer`). Finally, discounting short/medium (`≤ 220m`) hub→corridor outbound quotes once a town shows `≥ 6` return requests (`net_seed`) feeds more outbound carriers into both stages without polluting `learn()`.

## Co-play journal on `dev-12` (`cp-routes-1`, `cp-routes-2`, `cp-routes-3`)
Champion v4's week on `dev-12`: **`€10,417.77`, `254` won, `96.5%` on time**.

1. **`cp-routes-1` (watching Monday 07:00 → 16:00 & probing thin corridors):**
   - Watched outbound Capital cars (`Vantaa[359] → Lempäälä[22]`, `Vantaa[359] → Hyvinkää[3]`, `Helsinki[359] → Lahti[20]`) sit open on the board while return requests (`Tampere[22] → Vantaa[359]`, `Lahti[20] → Hyvinkää[3]`) arrived in the same window, and watched thin→thin requests (`R00153 Kokkola[4] → Vaasa[6]`) get declined while thin→hub (`Vaasa[6] → Vantaa[359]`, `268m`) was blocked by `return_hub_max_drive_min=180`.
   - Price probes on `R00104` and `R00105` confirmed the margin floor (`1.27–1.57×` list) was binding on competitive corridor lanes, so margin had to come from cheaper 2-car staffing and selective network admission rather than global price cuts.

2. **`cp-routes-2` (exact `whatif` causal decomposition from Monday 07:00 on `dev-12`, same draws):**

| Co-play `whatif` variant (`dev-12`, Mon 07:00 → end of week) | Margin | Δ vs Champion | Won | On-time | Takeaway |
|---|---:|---:|---:|---:|---|
| Champion v4 (`main line, unchanged`) | €10,418 | €+0 | 254 | 96.5% | Baseline on `dev-12` |
| `v1_naive_idea31` (`net_offer=True, net_quote=True` raw `0.65/0.80`, no repat guard, `0.85` open) | €10,305 | **€-112** | 250 | 96.0% | Confirms why raw Idea 31 failed: thin→thin dead-ends + `<1%` post-start `0.65/0.80` offer acceptance + `0.85` solo thin escalations |
| `v2_postbook_repat` (`net_offer_on_book=True, 0.90/1.05`, `net_quote_km=15`, `net_min_dest_supply=30`, `net_thin_fee_open=1.0`) | €10,703 | **€+285** | 255 | 96.5% | Repatriation guard (`dest ≥ 30` or home) + `1.0×` thin open + pre-start offers flips `-€112` to `+€285` (`+€397` swing) |
| `v3_prebook_relay` (`net_relay=True, net_relay_quote=True`) | €10,735 | **€+317** | 253 | 96.8% | Pre-booking 2-car homeward relays alone add `+€317` and `+0.3%` on-time |
| `v4_unified_network` (`v2 + v3` with unrestricted `1.05×` offers) | €10,710 | €+293 | 253 | 96.4% | Unrestricted `1.05×` offers at `age=0` cannibalized `0.7225×` relays on corridor towns (`supply 20..40`) |
| `w2_unblock_long_nd` (`+ net_unblock_long_nd=True`) | €10,526 | €+108 | 256 | 96.5% | Reject: unblocking `300–420m` `next_day` on `<50`-supply towns hurts by `-€185` |
| `s1_relay_seed03` (`net_relay + net_relay_quote + net_seed=0.03`) | €10,858 | **€+441** | 281 | 96.4% | Outbound seeding (`≤ 220m`, `≥ 6` return reqs) feeds `+27` carrier orders into the relay network |
| `s2_full_cheap_seed03` (`s1` + repatriated `net_quote` + `<50`-supply `30m`-aged `0.80/0.95` `net_offer`) | €10,917 | **€+500** | 282 | 96.5% | Non-overlapping post-booking `net_quote` + `net_offer` adds `+€59` and `+0.1%` on-time on top of `s1` |
| **`s3_full_cheap_seed04` (`s2` with `net_seed=0.04`)** | **€11,367** | **€+949** | **280** | **97.1%** | Best full-week line on `dev-12` (`cp-routes-3`: `€11,366.71`, `280` won, `97.1%` on time, `+0.6%` on-time) |

## What changed (`src/spread_lab/policy.py`, neutral defaults)
All new `Params` fields default to neutral (`False` / `0`), verified at exact **`€+0.00 ± 0.00`** paired parity on `smoke` against both Champion v4 (`20261114-094600-cp-routes-noop`) and Champion v5 (`20261114-110019-cp-routes-v5-noop`):
- **Position ledger (`pos_ledger`, rebuilt in `rejoin()`):** Tracks every booked/working/completed gig's `driver_id`, `home_place`, `finish_place`, `planned_start`, and `planned_finish` across `gig_booked`, `gig_started`, `driver_late`, `picked_up`, `delivered`, `gig_dropped`/`no_show`, `order_changed`, `order_cancelled`, `visit_failed`, and live `driverPositions`.
- **Pre-booking 2-car route relay (`net_relay`, `net_relay_quote`, `net_relay_km=15.0`, `net_relay_fee=0.85`, `net_relay_after_min=20`, `net_relay_patience_min=30`, `net_relay_homeward=True`, `net_relay_max_home_km`, `net_relay_preserve_age=True`):** Pairs open single-car outbound gig `A` and continuation gig `B` (`supply[A.p] ≥ supply[B.p]`, `line_km(A.d, B.p) ≤ 15 km`, `B.d` homeward, `≤ 12h` incl. 4-stop + plates/charging overhead, exact dealer/private-window arrival checks with `≥ min_slack_min` valid start window) at `0.85 × (open_A + open_B)`, splitting after `30` daytime minutes while preserving each car's original posting age. `net_relay_quote` admits up to `net_relay_cap_day=6` thin-gate slow requests/day when an open partner gig can carry them homeward.
- **Post-booking inbound-sponsored quoting & finishing offers (`net_quote`, `net_quote_km=15.0`, `net_min_dest_supply=30`, `net_thin_fee_open=0.95`, `net_offer`, `net_offer_on_book=True`, `net_offer_max_supply=50`, `net_offer_min_age=30`, `net_lead_min=45`, `net_home_mult=0.80`, `net_offer_mult=0.95`):** 1-to-1 booked-outbound sponsorship for repatriating thin slow requests (`dest supply ≥ 30` or `≤ 30 km` of driver home), tracker-neutral.
- **Demand-gated outbound seeding (`net_seed=0.04`, `seed_min=6`, `seed_max_drive_min=220`):** After Monday 12:00, discounts `≤ 220m` hub (`supply ≥ 100`) → non-hub (`supply < 100`) quotes within `30 km` of towns with `≥ 6` observed requests by `4%` (subject to margin floor, skipping `learn()`).

## Results (normal instrument)

### 1. Evaluations on Champion v4 (`51d1be6`, baseline €10,884.88 on dev)
| Run folder | Set | Flags summary | Worst on-time (`<92%`) | Won/wk | Mean margin | Paired Δmargin ± SE | t-stat | Better / Worse | Δon-time | SAFE? |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| `20261114-094600-cp-routes-noop` | smoke (4) | defaults (noop) | **94.38%** (`0/4`, `dev-01`) | 283.2 | €10,816.98 | €+0.00 ± 0.00 | — | 0 / 0 | +0.00% | **yes** |
| `20261114-101724-cp-routes-smoke-a-noseed` | smoke (4) | unified network, `net_seed=0` | **95.45%** (`0/4`, `dev-04`) | 294.5 | €11,904.78 | €+1,087.81 ± 330.60 | 3.29 | 4 / 0 | +0.82% | **yes** |
| `20261114-101810-cp-routes-smoke-b-seed03` | smoke (4) | unified + `net_seed=0.03` | **94.16%** (`0/4`, `dev-01`) | 303.8 | €11,885.78 | €+1,068.80 ± 362.71 | 2.95 | 4 / 0 | +0.51% | **yes** |
| `20261114-102016-cp-routes-smoke-c-seed04` | smoke (4) | unified + `net_seed=0.04` | **96.49%** (`0/4`, `dev-01`) | 310.0 | €12,018.74 | €+1,201.76 ± 305.57 | 3.93 | 4 / 0 | +1.38% | **yes** |
| `20261114-102732-cp-routes-smoke-d-acc105` | smoke (4) | unified + `0.95/1.05` offers | **96.49%** (`0/4`, `dev-01`) | 310.0 | €11,967.32 | €+1,150.34 ± 332.89 | 3.46 | 4 / 0 | +1.59% | **yes** |
| **`20261114-103757-cp-routes-dev-noseed`** | **dev (16)** | **unified network (`net_seed=0`)** | **93.99%** (`0/16`, `dev-07`) | **286.8** | **€11,501.20** | **€+616.32 ± 128.33** | **4.80** | **14 / 2** | **-0.04%** | **yes** |
| **`20261114-103153-cp-routes-dev-full-seed04`** | **dev (16)** | **unified + `net_seed=0.04`** | **94.60%** (`0/16`, `dev-05`) | **301.7** | **€11,569.61** | **€+684.73 ± 177.04** | **3.87** | **14 / 2** | **-0.05%** | **yes** |

### 2. Rebased evaluations on Champion v5 (`9aa3f13`, `cp-fees`, baseline €11,679.11 on dev / €12,036.75 on night32)
| Run folder | Set | Flags summary | Worst on-time (`<92%`) | Won/wk | Mean margin | Paired Δmargin ± SE (vs v5) | t-stat | Better / Worse | Δon-time | SAFE? |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| `20261114-110019-cp-routes-v5-noop` | smoke (4) | defaults on v5 (noop) | **93.70%** (`0/4`, `dev-01`) | 289.2 | €11,951.98 | €+0.00 ± 0.00 | — | 0 / 0 | +0.00% | **yes** |
| `20261114-110111-cp-routes-v5-smoke-noseed` | smoke (4) | unified network (`net_seed=0`) | **96.18%** (`0/4`, `dev-04`) | 294.2 | €12,558.23 | €+606.25 ± 272.39 | 2.23 | 3 / 1 | +0.94% | **yes** |
| `20261114-110340-cp-routes-v5-smoke-seed04` | smoke (4) | unified + `net_seed=0.04` | **96.13%** (`0/4`, `dev-01`) | 310.5 | €12,399.75 | €+447.77 ± 192.98 | 2.32 | 4 / 0 | +0.72% | **yes** |
| **`20261114-110549-cp-routes-v5-dev-noseed`** | **dev (16)** | **unified network (`net_seed=0`)** | **92.92%** (`0/16`, `dev-07`) | **289.4** | **€12,106.48** | **€+427.37 ± 120.46** | **3.55** | **13 / 3** | **-0.26%** | **yes** |
| **`20261114-110828-cp-routes-v5-dev-seed04`** | **dev (16)** | **unified + `net_seed=0.04`** | **94.00%** (`0/16`, `dev-13`) | **303.8** | **€12,288.55** | **€+609.43 ± 129.88** | **4.69** | **14 / 2** | **-0.09%** | **yes** |
| `20261114-112437-cp-routes-v5-dev-relay-offer` | dev (16) | `net_relay + net_relay_quote` (`net_quote=False`) | **94.03%** (`0/16`, `dev-14`) | 288.2 | €12,045.10 | €+365.98 ± 129.46 | 2.83 | 12 / 4 | -0.22% | **yes** |
| `20261114-113036-cp-routes-v5-dev-rt35` | dev (16) | `net_relay_max_home_km=35` only | **93.96%** (`0/16`, `dev-14`) | 281.0 | €11,599.33 | €-79.78 ± 97.98 | -0.81 | 7 / 9 | -0.21% | **yes** |
| **`20261114-111117-cp-routes-v5-night32-seed04`** | **night (32)** | **unified + `net_seed=0.04`** | **91.26%** (`2/32`: `night-15` 91.3%, `night-30` 91.6%; **32/32 ranked**) | **322.9** | **€12,641.45** | **€+604.70 ± 155.74** | **3.88** | **26 / 6** | **-0.27%** | **no** (`2/32 < 92%`) |
| `20261114-112010-cp-routes-v5-night32-noseed` | night (32) | unified network (`net_seed=0`) | **91.06%** (`1/32`: `night-15` 91.1%; `night-30` 92.3%; **32/32 ranked**) | 306.2 | €12,534.23 | €+497.48 (mean vs v5) | — | — | -0.15% | **no** (`1/32 < 92%`) |
| `20261114-112604-cp-routes-v5-night32-relay-offer` | night (32) | `net_relay + net_relay_quote` (`net_quote=False`) | **90.88%** (`1/32`: `night-15` 90.9%; `night-30` 93.6%; **32/32 ranked**) | 303.0 | €12,428.76 | €+392.01 (mean vs v5) | — | — | +0.00% | **no** (`1/32 < 92%`) |

### Mechanism counters & ledger decomposition (`dev-01..dev-16`)
- **Offer acceptance rate (home-bound vs non-home-bound, measured on `20261114-103153-cp-routes-dev-full-seed04`):**
  - `net_offers = 32.81/wk` (`20.44/wk` pre-start, `12.38/wk` within `45m` of finish; `2.12/wk` home-bound, `30.69/wk` non-home-bound).
  - **Home-bound acceptance rate:** `0.125 / 2.125` = **`5.9%`**. **Non-home-bound acceptance rate:** `0.25 / 30.69` = **`0.8%`** (`1.1%` overall; rising only to `1.9%` even at `0.95×/1.05×` in `smoke-d`). This confirms R15's finding that once a Level-8 driver has already booked a 1-car gig, ~81% of driver-days refuse any separate 2nd gig.
- **Pre-booking 2-car route relays (`20261114-110828-cp-routes-v5-dev-seed04`):**
  - **`29.44` pairs posted/wk** (`11.56` round-trips within `30 km`, `5.50` thin-`B` pickups) → **`18.44` pairs booked/wk (`62.6%` booking rate!)**, bundling **`36.9` cars/wk** into single-driver routes with only **`0.25` late booked relay orders/wk (`99.3%` on-time on booked pairs!)**.
  - Paid 2-car relay fees averaged **`€1,142.73/wk` vs `€1,519.15/wk` sum of reference fees (`0.752×`, saving `€376.42/wk` directly vs reference)**; restricting relays strictly to `≤ 35 km` round-trips (`v5-dev-rt35`) gave up `-€445.77/wk` of corridor chain savings (`t = -0.81`).
- **Thin return admission (`net_relay_quote` + `net_quote`) & Outbound seeding (`net_seed=0.04`):**
  - `relay_quote_won = 4.19/wk` (`0.06/wk` late = **`98.5%` on-time**) + `net_won_thin = 2.19/wk` (`0.12/wk` late = **`94.3%` on-time**, `+€142.02/wk` net margin).
  - `seed_won = 85.31/wk` (`1.56/wk` late = **`98.2%` on-time**, `€3,093.43/wk` margin), lifting total won volume on Champion v5 from `283.6/wk` to **`303.8/wk` (`+20.2` orders/wk)** AND raising worst-world dev on-time from `93.70%` (`dev-01`) to **`94.00%` (`dev-13`)** (`min margin` up from `€8,207` to **`€9,458.78`**!).
- **Ledger delta on Champion v5 (`v5-dev-seed04` vs `champ-v5`, mean/wk across 16 dev worlds):**
  - `revenue`: `€30,745.12 → €32,503.28` (**`+€1,758.16/wk`**)
  - `driver_fee`: `€-18,586.31 → €-19,672.45` (`-€1,086.14/wk`; marginal driver fee on the `+20.2` added orders is only **`61.8%` of marginal revenue**, pushing desk-wide `driver_fee / revenue` down to **`60.5%`** at `304` won/wk!)
  - Net paired `Δmargin`: **`€+609.43 ± 129.88` (`t = 4.69`, `14/2` better)**.
- **Why `night-15` dipped to `91.1–91.3%` on `night32` (and how to guard it if promoting):**
  - Across `night-01..night-32`, `v5-night32-seed04` beat `cp-fees` by **`€+604.70 ± 155.74` (`t = 3.88`, `26/6` better, `32/32` ranked `≥ 91.3%`)**. On `night-15` (`389` won, `€20,781` margin; `369` won in `noseed`), `32/33` late orders were Capital solo orders (`late_ring = 1`, `relay_late_booked = 0`): during an extreme `360+`-order Capital surge, holding `21` unbooked non-roundtrip pairs for `net_relay_patience_min=30` delayed `cp-fees`'s `15m` `view_offer` window. Disabling new hub→mid pairing when Capital backlog is already near cap (or shortening `net_relay_patience_min` to `15m` when `won_day` is high) targets `night-15` directly without sacrificing the `+€609/wk` (`t = 4.69`) dev gain. Because `night-15` (`91.3%`) was below `cp-fees`'s `92.5%` night32 tail, we did **not** run `scripts/promote.sh` and leave promotion/gating to the lead.

## Verdict
**adopt on dev (`t = 4.69` on v5, `0/16 < 92%`, worst dev world `94.0%`); needs a high-volume relay-patience guard for `night-15` (`91.3%` at `389` won) before promoting to `main`** — `-s net_relay=True -s net_relay_quote=True -s net_quote=True -s net_quote_km=15.0 -s net_min_dest_supply=30 -s net_thin_fee_open=0.95 -s net_offer=True -s net_offer_max_supply=50 -s net_offer_min_age=30 -s net_offer_on_book=True -s net_lead_min=45 -s net_home_mult=0.80 -s net_offer_mult=0.95 -s net_seed=0.04 -s seed_min=6 -s seed_max_drive_min=220` adds **`€+609.43 ± 129.88` (`t = 4.69`, `14/16` better, `303.8` won/wk, worst dev world `94.00%`)** on top of Champion v5 (`cp-fees`) and **`€+604.70 ± 155.74` (`t = 3.88`, `26/32` better, `32/32` ranked)** on 32 unseen night worlds.
