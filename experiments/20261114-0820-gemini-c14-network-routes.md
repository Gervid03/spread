# c14-network-routes: Idea 31, the route network (position ledger, fanout direct offers, on-network quoting, and outbound seeding)

- **Agent / branch / commit:** gemini (Carbon 1) · `exp/gemini-c14-network-routes`
- **Date:** 2026-11-14 08:20 UTC
- **Idea from:** `experiments/IDEAS.md` item **31** (the user's route-network design, `prompts/carbon/c1-network-routes.md`)

## Why we tried it
At Level 8, driver capacity—not dealer demand—is our binding constraint: opening thin towns without driver continuations stole drivers from dense corridors (`n14-05162`). A driver finishing one of our gigs far from home has zero deadhead to a nearby next pickup and, when the next car goes within 30 km of their home, saves the expensive on-the-day return train/bus ticket too. Because app notifications go strictly by driver `homePlaceId` (30 km), far-from-home finishing drivers never hear about nearby return cars unless reached by a direct offer (`HANDBOOK.md` explicitly names "a driver who finishes one of your gigs far from home"). Idea 31 builds a four-part route network on Champion v3:
- **(a) Position ledger (`pos_ledger`):** Tracks every booked/working/completed gig's driver, home town, finish town, and dynamic finish minute (updated on `driver_late`, `gig_started`, `picked_up`, `delivered`, `order_changed`, `order_cancelled`, `visit_failed`, `driverPositions`, and rebuilt in `rejoin()`).
- **(b) Fanout network offers (`net_offer`):** Daytime (07:00–21:00) direct offers of open gigs to up to `net_fanout=3` eligible finishing drivers within `net_km=30` km, ranked by distance from delivery to driver home then finish to pickup, sent `net_lead_min=60` min before finish at `net_home_mult=0.65` (delivery ≤30 km from driver home) or `net_offer_mult=0.80`.
- **(c) On-network quoting (`net_quote`):** Requests with a far-from-home driver finishing within 30 km in `[ready - 3h, ready + 1h]` get `1 - net_discount` (`0.05`) on non-hub gate-passing quotes (`supply < 100`), and slow options at `1.00×` tracker price on thin-gate pickups (`gate_supply < 22`, `drive <= 300`, up to `net_cap_day` wins/day), neither moving the tracker.
- **(d) Outbound seeding (`net_seed`):** From Monday 12:00, outbound requests (`drive <= 220` min) from dense hubs (`supply >= 100`) to non-hub towns (`supply < 100`) within 30 km of a town with `>= seed_min` (`6`) requests this week are quoted at `1 - net_seed` (`0.05`) without moving the tracker.

## Diagnostic findings: why fewer than 1 in 5 offers (`0.2%–1.3%`) is accepted
Before running dev, slot-free analysis of cached v3 reveals (`/tmp/reveals-v3`) and a ground-truth reveal of smoke world `w242e665a379704c1ada3` (`experiments/scripts/diagnose_offers.py`) isolated the exact causes of low direct-offer acceptance across all four candidate explanations:

1. **"Nobody reads them" is FALSE (`43%–60%` read within 10 minutes):** In `RULES.md`, an unread offer or already-booked gig returns `expired`, whereas `declined` means the driver **read** the offer within 10 minutes, the gig fit their day, and they said **no**. On clean far-from-home offers (`c14-net-bcd-dev`), `51.3 / 85.5 = 60.0%` were read and `declined`, while `34.0 / 85.5 = 39.8%` `expired` (drivers actively driving have ~52% read rate vs 75% right after `delivered`, plus app booking races inside the 10-minute window).
2. **Timing (`net_lead_min=0` vs `60`, same-day rule, and unstarted bookings):**
   - `net_lead_min=0` dropped acceptance to **`0.0%` (`0 / 1,016` offers, `Δmargin = €0.00`)**: v3 reveal chain analysis (`inspect_chain_gaps.py`) proved `13/13` far-from-home organic chains occur on the **same day** (`0` next-day chains) and `12/13` book **before** `delivered`, because once `delivered` fires with no next booking, the driver immediately heads home.
   - Before requiring `entry.started or entry.picked_up or entry.delivered` and `pick0_open // DAY == fin_at // DAY`, `57%` (`184/322`) of naive offers fired on `holding_unstarted` bookings (evening drivers or multi-day bookings) and future-day windows, burning drivers' 3-offers/day limit prematurely.
3. **Fee vs Level-8 second-gig reservation cost (the primary cause of `99%` decline among readers):**
   - Raising `net_home_mult` from `0.65` to `0.80` tripled home-bound acceptance (`0.3% -> 1.0%`), and raising to `0.90 / 1.00` lifted total acceptance from `0.4%` to `1.3%` (`3.8/wk`).
   - Even at `0.90×–1.05×`, `98.7%` of readers declined because a driver finishing a 2–6 hour intercity gig already has high cumulative day hours ("how many gigs they want, how late they want to get home, what else their day is worth to them"). In `reveal-w242e665a379704c1ada3`, the 145 gigs where offers were declined eventually booked on the app at **`p10 = 0.85×, median = 1.01×, p90 = 1.46×`**, and all 4 accepted offers were short (`25–102` min) hops where total daily driving stayed modest.
4. **Two critical quoting guardrails discovered on smoke/dev8:**
   - Including local-home drivers (`line_km(home, pickup) <= 30` km) in `net_quote` matched `430/wk` capital requests, cutting capital prices by 5% and freezing `learn()` (`dev-01` dropped to `90.3%`, `-€426.67`). Restricting network candidates strictly to **far-from-home drivers (`> 30` km from home)** and non-hub discounts (`supply < 100`) restored `dev-01` to `95.0%` (`+€279`).
   - Uncapped `net_seed` discounted 6–8h northern long-hauls (`> 300` min) that cannot chain back same-day, causing `10` late seeded orders on `dev-07` (`-€857`). Capping `is_seed` to reachable `drive <= 220` min corridors flipped `dev-07` by **`+€1,598`** (`-€857.50 -> +€740.03`, `95.9%` on-time).

## What changed
Implemented in `src/spread_lab/policy.py` behind neutral defaults (`noop` verified `Δmargin = €+0.00` on all 4 smoke seeds):
- `Params`: `net_offer=False`, `net_km=30.0`, `net_fanout=3`, `net_offer_mult=0.80`, `net_home_mult=0.65`, `net_lead_min=60`, `net_quote=False`, `net_discount=0.05`, `net_cap_day=8`, `net_seed=0.0`, `seed_min=6`.
- `PosEntry` ledger + `rejoin()` reconstruction + `sync_driver_positions()` + all mechanism `stats` counters.

## Numbers

| Run | Set | Settings | Mean margin | Δmargin ± SE (t) | Won/wk | Worst world (on-time) | Mean on-time | Offer acc (home / non-home) | SAFE? |
|---|---|---|---|---|---|---|---|---|---|
| `20261114-075115-c14-net-noop` | smoke (4) | defaults (all off) | €10,892.44 | €+0.00 ± 0.00 | 287.2 | `dev-01` **94.42%** | 96.59% | — | YES |
| `20261114-075312-c14-net-b-hm65-lead60` | smoke (4) | `net_offer=true` (`0.65/0.80, lead=60`, pre-fix) | €10,641.74 | €-250.70 ± 288.12 (-0.87) | 289.8 | `dev-01` **94.02%** | 96.01% | 0.4% (0.3% / 0.4%) | YES |
| `20261114-075446-c14-net-b-hm80-lead60` | smoke (4) | `net_offer=true, net_home_mult=0.80` | €10,624.43 | €-268.01 ± 281.70 (-0.95) | 289.8 | `dev-01` **94.02%** | 96.01% | 0.6% (1.0% / 0.4%) | YES |
| `20261114-075458-c14-net-b-hm65-lead0` | smoke (4) | `net_offer=true, net_lead_min=0` | €10,892.44 | €+0.00 ± 0.00 (0.00) | 287.2 | `dev-01` **94.42%** | 96.59% | 0.0% (0.0% / 0.0%) | YES |
| `20261114-075612-c14-net-b-hm90-off100` | smoke (4) | `net_offer=true, hm=0.90, off=1.00` | €10,877.24 | €-15.20 ± 145.48 (-0.10) | 288.2 | `dev-01` **94.86%** | 96.68% | 1.3% (1.0% / 1.4%) | YES |
| `20261114-080302-c14-net-b-v2-hm65-lead60` | smoke (4) | `net_offer=true` (started + same-day fix) | €10,843.09 | €-49.34 ± 76.93 (-0.64) | 287.2 | `dev-01` **94.02%** | 96.33% | 0.2% (0.0% / 0.3%) | YES |
| `20261114-080345-c14-net-bc-default` | smoke (4) | `net_offer=true, net_quote=true` (no far-home filter) | €10,465.77 | €-426.67 ± 220.51 (-1.93) | 330.2 | `dev-01` **90.30%** | 94.58% | 0.5% (0.4% / 0.6%) | **NO** |
| `20261114-080634-c14-net-bc-far` | smoke (4) | `net_offer=true, net_quote=true` (far-from-home) | €10,899.93 | €+7.49 ± 186.49 (+0.04) | 294.2 | `dev-01` **95.02%** | 96.37% | 0.0% (0.0% / 0.0%) | YES |
| `20261114-080710-c14-net-bcd-far` | smoke (4) | `net_offer=true, net_quote=true, net_seed=0.05` | €11,151.13 | **€+258.69 ± 94.35 (+2.74)** | 312.0 | `dev-01` **95.19%** | 96.03% | 0.0% (0.0% / 0.0%) | YES |
| `20261114-080830-c14-net-bcd-dev8` | dev-8 | `bcd` before `<=220m` seed cap | €10,872.62 | €+22.48 ± 176.15 (+0.13) | 323.6 | `dev-05` **93.06%** | 95.94% | 0.0% (0.0% / 0.0%) | YES |
| **`20261114-081243-c14-net-bc-dev`** | **dev (16)** | **`net_offer=true, net_quote=true, net_cap_day=8`** | **€10,334.07** | **€-195.34 ± 103.88 (-1.88)** | **285.1** | **`dev-07` 93.31%** | **96.71%** | **0.2% (0.0% / 0.2%)** | **YES** |
| **`20261114-081438-c14-net-bcd-dev`** | **dev (16)** | **`net_offer=true, net_quote=true, net_seed=0.05, cap=8`** | **€10,551.48** | **€+22.06 ± 151.73 (+0.15)** | **303.1** | **`dev-01` 93.94%** | **96.71%** | **0.2% (0.0% / 0.2%)** | **YES** |
| **`20261114-081552-c14-net-bcd-cap16-dev`** | **dev (16)** | **`net_offer=true, net_quote=true, net_seed=0.05, cap=16`** | **€10,551.48** | **€+22.06 ± 151.73 (+0.15)** | **303.1** | **`dev-01` 93.94%** | **96.71%** | **0.2% (0.0% / 0.2%)** | **YES** |

### Mechanism counters on `dev` (`20261114-081438-c14-net-bcd-dev`, 16-world means)
- **Worst world:** `dev-01` at **93.94%** on-time (margin €7,410.07, 264 won; 0 worlds under 92%).
- **Volume & ledger vs Champion v3:** Won orders rose **281.1 → 303.1/wk (+22.0/wk)**; revenue rose **€30,497.9 → €32,262.4/wk (+€1,764.5)**, offset by driver fees **-€19,482.7 → -€21,170.8/wk (-€1,688.1)** and late refunds **-€381.9/wk**, netting **€+22.06 ± 151.73/wk** (8/16 seeds positive).
- **Direct offers (`net_offer`):** `85.5/wk` sent (`10.2` home-bound, `75.3` non-home) across `40.2` offered gigs/wk; `0.2/wk` (`0.2%`) accepted at `0.800 × typical`, `51.3/wk` (`60.0%`) read and `declined`, `34.0/wk` (`39.8%`) `expired`.
- **Candidate redundancy (`net_cands_*`):** `0` candidates on `227.5` gigs/wk, `1` on `37.1`, `2` on `23.1`, `3+` on `32.5` (among `40.2` offered gigs/wk: `10.1` had 1 candidate, `9.9` had 2, `20.2` [50%] had `3+` candidates).
- **Multi-gig chaining:** `driver_days_2plus = 53.6/wk` (and up to `60.0/wk` on smoke).
- **On-network quoting (`net_quote`):** `78.3/wk` quoted (`18.2/wk` thin-gate), `27.6/wk` won (`4.9/wk` thin-gate — why `net_cap_day=16` is identical to `8`), `1.00/wk` late (`0.38/wk` thin-gate = **92.2% on-time on thin towns!**), sub-ledger margin **+€715.6/wk** (`+€96.4/wk` thin-gate).
- **Seeding (`net_seed=0.05`, `<=220m`):** `161.2/wk` quoted, `84.4/wk` won, only `1.44/wk` late (**98.3% on-time**), sub-ledger margin **+€2,436.9/wk** (lifting dev paired margin by **+€217.40/wk** over `(b)+(c)` alone).

## Verdict
reject for promotion (`t = 0.15 < 2.0`, statistical tie with Champion v3) — `(b)+(c)+(d)` (`net_offer=true, net_quote=true, net_seed=0.05`) is **16/16 SAFE** (worst world `dev-01` 93.94%) and lifts volume by +22 won orders/week (`+€22.06 ± 151.73`), but post-hoc `0.65×/0.80×` continuation offers are 99.7% declined by readers (`0.2%` accepted) because second-gig day-duration reservation costs at Level 8 average ~`1.01×` typical fee, so pre-commitment two-car pairing (Idea 26) is structurally better suited to capture thin return legs.
