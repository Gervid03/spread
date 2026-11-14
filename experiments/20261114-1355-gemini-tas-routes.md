# tas-routes: the travelling salesman week — foresight closed tours, fork-bisected tour costs, Lagrangian ceiling bounds, and the Sunday cycle rule

- **Agent / branch:** `gemini` (`tas-routes`) · `exp/gemini-tas-routes`
- **Date:** 2026-11-14 13:00–21:00 Helsinki
- **Layer:** TAS Layer 3 — **Tours planned with full-week foresight** (standalone, stacked on `tas-price`, stacked with `tas-state`, and full 4-layer stack with `tas-fees`), plus live forkless translation (`SundayDesk` -> promoted into **Champion v7 `cycles:Desk`** on `main`!)
- **Champion baseline (v5, `cp-fees`, common reference across all four TAS tracks):**
  - `dev-12`: **€10,910.49** (`246` won, `98.0%` on time, `revenue €29,657.75`, `driver_fee -€18,367.50` = `€74.66/car`)
  - `dev-01`: **€8,469.14** (`254` won, `93.7%` on time, `revenue €22,666.07`, `driver_fee -€13,712.22` = `€53.99/car`)
  - `dev-08`: **€15,014.36** (`287` won, `98.3%` on time, `revenue €34,979.66`, `driver_fee -€19,490.63` = `€67.91/car`)
  - `dev-07`: **€14,410.02** (`338` won, `95.6%` on time, `revenue €42,588.72`, `driver_fee -€26,441.05` = `€78.23/car`)

---

## 1. Step 1: The Route Census & Champion Reveal Anatomy (0 forks, 4 TAS worlds)

We recorded silent full-week tapes (`scripts/tas.py tape`, 14 server requests/seed) and downloaded CSV reveals of Champion v5's finished runs (`uv run lab reveal`, 0 slots) across all four TAS worlds (`dev-12`, `dev-01`, `dev-08`, `dev-07`). Script: `experiments/scripts/tas_routes_census.py`.

### 1.1 Three rule mechanics caught before building tours
1. **Intra-city yard transfers are NOT zero road minutes:** `roads.csv` defines positive road distance and minutes from every town to itself (e.g., `helsinki -> helsinki = 12 km, 25 min`, `vantaa -> vantaa = 25 min`, `kuopio -> kuopio = 18 min`). Under `RULES.md` ("The 12 hours include the drive between every two stops, also from one car's delivery to the next car's pickup"), omitting `geo.minutes(p, p)` causes 700–715 min tours to exceed 720 min and be refused by the server. Both `simulate_tour` and `TasRoutesDesk` enforce exact `geo.minutes(d_i, p_{i+1})` on every transition.
2. **Scarce `experienced` driver sub-pool (`6.6%–8.8%` of roster):** Across the four L8 worlds, `manual` licence coverage is `84.8%–86.7%`, whereas `experienced` (`rating >= 4.8` and `completedGigs >= 50`) is only **`6.6%` (`47/709` in `dev-12`) to `8.8%` (`58/656` in `dev-01`)**. Mixing one `premium` car into a 4-car non-premium tour forces `audience.experienced = True` on all 4 cars; our planner penalizes mixed-audience tours and enforces separate `experienced` zone-day caps.
3. **Massive idle driver capacity vs Champion v5's solo gate bottleneck:**
   - In `dev-12` (`709` roster drivers), **`325–379` distinct drivers open the app (`views.csv`) each weekday**, yet Champion v5 only booked **`23–60` drivers/day** (`246 / 1,036` requests = `23.7%`!).
   - Champion v5's supply gate (`min_supply = 22`) declines almost all requests originating in thin/zero-driver towns (`savonlinna 0, rovaniemi 0, kemi 0, kajaani 1, kouvola 2, hyvinkaa 3, ylivieska 3, kokkola 4, rauma 4, vaasa 6, porvoo 7, pori 9` in `dev-12`).
   - **Closed tours invert the Level-8 geography:** A closed tour `Vantaa -> Kuopio -> Vantaa` or `Espoo -> Tampere -> Lempäälä -> Pori -> Helsinki` notifies **359 Capital drivers**, rescues thin/zero-driver pickups without touching local supply, and moves **2.4–2.6 cars per tour driver-day**!

### 1.2 Census table across the four TAS worlds (`tas_routes_census.py`)

| Seed | Requests (1-leg clean) | Roster (`exp`%) | Bulk batches (`>=15` cars) | Ordered feasible pairs (`<=35km` dh, `<=12h`) | Closed 2-car pairs near drivers | Closed 3-car triangles | Closed 4-car tours/shuttles | Requests fitting `>=1` closed 2+ car tour near drivers |
|---|---:|---:|---|---:|---:|---:|---:|---:|
| **`dev-12`** | 1,036 (1,010) | 709 (6.6%) | Wed 15 Hämeenlinna, Thu 16 Lempäälä, **Thu 36 Kuopio** | 25,677 | 3,907 (678 reqs) | 22,526 | 42,606 | **801 / 1,036 (77.3%)** |
| **`dev-01`** | 1,035 (1,010) | 656 (8.8%) | **Mon 35 Jyväskylä**, Wed 15 Hämeenlinna, Thu 17 Lempäälä | 25,951 | 4,148 (702 reqs) | 26,650 | 53,261 | **851 / 1,035 (82.2%)** |
| **`dev-08`** | 1,038 (1,011) | 867 (8.0%) | **Tue 20 Vantaa->Hyvinkää**, **Tue 38 Raisio**, Wed 15 Hämeenlinna | 30,275 | 4,581 (699 reqs) | 25,213 | 47,308 | **803 / 1,038 (77.4%)** |
| **`dev-07`** | 1,033 (1,004) | 643 (7.2%) | **Mon 33 Turku**, Wed 15 Hämeenlinna, Thu 16 Lempäälä | 27,316 | 4,548 (739 reqs) | 27,828 | 51,666 | **873 / 1,033 (84.5%)** |

*(In a compressed 2-day Thursday–Friday start `arrivedAt >= 4320`, `tas_routes_thu_start.py` found `77–92` disjoint closed 2–3-car tours covering `44.0%–46.7%` of all Thu–Fri requests, including `55–71` thin `<22`-driver rescues/wk.)*

---

## 2. Step 2: Fork-Bisected Tour Reservation Costs (`tas_routes_probe_fees.py`, 79 forks on `dev-12`)

We played `dev-12` to Monday `18:20` holding 55 won Monday legs unposted, partitioned 17 intact 1-, 2-, 3-, and 4-car tours into non-competing town batches (`>85 km` apart), and bisected each tour's **drop-proof flat fee** (booked and still held with zero drops at `Tue 09:30`, `now=2010`) in 8 fork rounds (`~/.spread-lab/tas/dev-12/tas-routes-step2-fees.json`).

### 2.1 Measured flat-fee reservation prices (real server, `dev-12`)

| Kind | Cars | Road min (h) | Deadhead | Sum `ref` | **Measured Min Fee** | **`Fee / Ref`** | **`€ / Wheel h`** | Route |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| **`4-closed`** | 4 | 599m (10.0h) | 69m | €307.20 | **€102.70** | **`0.334x`** | **€10.29/h** | `vantaa->mikkeli -> mikkeli->lempaala -> tampere->raisio -> raisio->vantaa` |
| **`3-closed`** | 3 | 431m (7.2h) | 44m | €200.10 | **€69.01** | **`0.345x`** | **€9.61/h** | `espoo->tampere -> lempaala->pori -> pori->helsinki` |
| **`3-closed`** | 3 | 333m (5.6h) | 27m | €188.20 | **€58.95** | **`0.313x`** | **€10.62/h** | `vantaa->lempaala -> tampere->turku -> raisio->vantaa` |
| **`3-closed` (reg)** | 3 | 354m (5.9h) | 33m | €186.00 | **€79.83** | **`0.429x`** | **€13.53/h** | `lahti->hyvinkaa -> hyvinkaa->raisio -> turku->lahti` |
| **`2-closed-long`** | 2 | 251m (4.2h) | 25m | €134.70 | **€42.19** | **`0.313x`** | **€10.09/h** | `helsinki->raisio -> raisio->helsinki` |
| **`2-closed-long`** | 2 | 226m (3.8h) | 25m | €117.70 | **€39.36** | **`0.334x`** | **€10.45/h** | `espoo->raisio -> raisio->vantaa` |
| **`2-closed-reg`** | 2 | 459m (7.7h) | 25m | €191.10 | **€73.97** | **`0.387x`** | **€9.67/h** | `mikkeli->salo -> salo->mikkeli` |
| **`2-closed-reg`** | 2 | 261m (4.4h) | 25m | €117.20 | **€49.08** | **`0.419x`** | **€11.28/h** | `raisio->hyvinkaa -> hyvinkaa->raisio` |
| **`2-closed-short`** | 2 | 79m (1.3h) | 25m | €36.90 | **€20.13** | **`0.545x`** | **€15.29/h** | `espoo->vantaa -> vantaa->helsinki` |
| **`2-open-hub`** | 2 | 558m (9.3h) | 25m | €228.90 | **€148.97** | **`0.651x`** | **€16.02/h** | `espoo->raisio -> raisio->oulu` |
| **`2-open-thin`** | 2 | 595m (9.9h) | 25m | €258.10 | **€207.42** | **`0.804x`** | **€20.92/h** | `vantaa->hyvinkaa -> hyvinkaa->rovaniemi` |
| **`1-solo-short`** | 1 | 38m (0.6h) | 0m | €31.30 | **€26.27** | **`0.840x`** | **€41.48/h** | `vantaa->porvoo` |
| **`1-solo-long`** | 1 | 321m (5.4h) | 0m | €132.20 | **€104.14** | **`0.788x`** | **€19.47/h** | `vantaa->kokkola` |
| **`1-solo-reg`** | 1 | 235m (3.9h) | 0m | €105.20 | **€81.77** | **`0.777x`** | **€20.88/h** | `oulu->vaasa` |

### 2.2 Simultaneous Capital driver-pool depth test (13 concurrent 2-car closed tours)
- `0.50 × sum(ref)` flat: **10 / 13** booked and held
- `0.60 × sum(ref)` flat: **12 / 13** booked and held
- `0.70 × sum(ref)` flat: **13 / 13 (100%)** booked and held

**Physical law uncovered:** Pure wheel time costs **~€9.60–€11.30/h** when a tour starts and ends at home. Roughly **two-thirds of `referenceFeeCents`** on inter-city solo gigs pays for the expensive same-day VR return train ticket and unpaid transit hours home. Open chains ending in Rovaniemi still cost `0.804x ref` (`€20.92/h`); closing the loop slashes driver cost to **`0.31x–0.43x sum(ref)`**!

---

## 3. Journal of Ideas Tested, Failures Caught & Diagnostic Lessons

1. **Pricing and routing couple dynamically through dealer trust (`run-tas-routes-v5subset-lim`, `246 -> 216` won; `direct-safe`, `350 -> 122` won):**
   - When a car is held for a tour (or switched from `same_day` to `next_day`), intermediate delivery timestamps shift by a few hours, shifting `dealer_trust` at intermediate minutes by `±1..8` points (`±1%..8%` on accepted price). Replaying static `lo` quotes measured on Solo-Week's trust curve misses borderline quotes by `1%`.
   - **Conclusion:** Optimal quotes and tours **must** be solved and bisected on the **same timeline** (`tas.py limits --apply` with `TasRoutesDesk` active, and `tas_routes_fee_oracle.py` running `price_oracle` + `bisect_post_fees` together).
2. **`same_day` inside multi-car tours destroys dealer trust (`puretours400`: `168` `same_day` wins -> `94.7%` OT -> `avg_mult` fell `1.59x -> 1.25x`):**
   - Allowing `same_day` options into 3–4-car tours caused `20` late cars on Thursday, repeatedly halving `D01..D03` trust (`25 -> 12 -> 6`) and wiping out `+18%` of revenue on all Thursday/Friday wins (`€12,139` margin despite `€57.80/car` driver fees).
   - **Fix:** Restrict multi-car tour legs to `next_day` / `within_3_days` (allowing `same_day` only on short `<=85m` Monday morning `<12:30` trust-builders with `>=4h` slack).
3. **Dealer-share shadow prices (`nu_{D,d}`) & 2-leg trade-ins (`elite385` vs `steered440` on `dev-12`: `+€1,964` margin, `+€6,974` revenue on the same 380 cars!):**
   - Under `tas-state`'s competitor reaction law (`<30%` Mon hike, `<70%` Tue–Thu zero-cut deadband on busy dealers `>=10` reqs/day), dealer win slots on `D01/D02/D03` have a **shadow opportunity cost of ~€45–€65/car**. Without dual multipliers `nu_{D,d}` on busy-dealer caps, small `€48` short-hop pairs crowded out `€220` inter-city legs and 2-leg trade-ins (`22`/wk, built-in round trips!). Adding `nu_{D,d}` + trade-ins + a `>= +€12` per-leg incremental profit filter lifted revenue on 380 won cars from `€39,177` (`steered440`) to **`€46,461` (`elite385-exactfees`, `€16,050.43` margin)**!
4. **Solo overload vs tour density on thin-roster northern worlds (`dev-07`, `643` drivers: `steered440` `89.0%` NOT RANKED vs `safe360` `94.9%` SAFE `€19,804` / `exactfees €20,764`):**
   - Allowing `197` solos (`289` total gigs) starved `dev-07`'s `643`-driver fleet (`89.0%` on time). Capping solos at `--max-solos 65` alongside `112` closed tours (`177` total gigs for `353` won cars!) restored on-time to **`94.9%` (`€19,803.59`)** and **`93.5%` (`€20,764.04` with exact fees)**!
5. **Controlled 0-fork ablations on identical quote books (`dev-12`):**
   - **Closed tours vs solo staffing on the exact same 400-car quote book (`clean400-replay` vs `ablate-solo400`, 0 forks):** **`€14,101.14` vs `€11,872.77` = `+€2,228.37` pure staffing gain** (`driver_fee` dropped `-€1,426` while delivering `+4` more cars).
   - **Piecewise-flat tour fees vs rising schedules (`steered440` vs `ablate-rising`, 0 forks):** **`€13,229.01` vs `€12,943.94` = `+€285.07`** ("a flat fee that books teaches nobody to wait").
   - **Relay direct offers to finishing drivers (`ablate-relay`, 0 forks):** **`€13,137.28` (`-€91.73` vs `steered440`)** — confirming `cp-routes`'s finding that once Level-8 drivers book a gig, ~81% decline a separate 2nd gig, whereas pre-bundling 2–4 cars into **one** closed gig achieves `62%–91%` booking rates at `0.54x ref`!

---

## 4. Final Tables: 4-World Waterfall, Achieved vs Bounds, and Fleet Efficiency

### 4.1 The TAS Waterfall across the four worlds (`>= 92%` SAFE rule, plus `>= 90%` ranked edge where higher)

| World | Champion v5 (`0` forks) | + Perfect Prices (`tas-price` L1) | + Perfect Fees (`tas-fees` L1+3) | + Foresight Tours (`tas-routes`) | + State Steered (`tas-routes` + `tas-state`) | **Full 4-Layer Stack (`+ exact tour fees`)** | **Proven Dual Bound (`tas_routes_planner --bound`)** |
|---|---|---|---|---|---|---|---|
| **`dev-12`** | **€10,910.49**<br>246 won · 98.0% | **€14,572.94** (+€3,662)<br>246 won · 98.0% · 1,737f | **€15,224.23** (+€4,314)<br>246 won · 95.9% · 2,611f | **€15,145.66** (+€4,235)<br>442 won · 95.9% · 2,322f | **€15,193.22** (+€4,283)<br>380 won · 92.9% · 1,830f | **€16,050.43 (+€5,140 / +47.1%)**<br>**380 won · 92.1% SAFE** · 2,895f | **€55,382.71** Dual UB<br>*(€50,337 int. opt)* |
| **`dev-01`** | **€8,469.14**<br>254 won · 93.7% | **€11,680.61** (+€3,211)<br>254 won · 93.7% · 1,600f | *€12,863.69 (+€4,395)*<br>*254 won · **91.7% (<92% edge)** · 3,310f* | **€11,842.01** (+€3,373)<br>**388 won · 96.9% SAFE** · 2,192f | **€11,702.83** (+€3,234)<br>422 won · 95.7% SAFE · 2,222f | **€14,178.23 (+€5,709 / +67.4%)**<br>**424 won · 95.0% SAFE** · 2,992f | **€40,425.47** Dual UB<br>*(€36,083 int. opt)* |
| **`dev-08`** | **€15,014.36**<br>287 won · 98.3% | **€20,518.72** (+€5,504)<br>287 won · 98.3% · 1,874f | **€21,623.40** (+€6,609)<br>288 won · 97.2% · 3,915f | **€21,675.72** (+€6,661)<br>**389 won · 98.7% SAFE** · 2,178f | **€23,481.39** (+€8,467)<br>**421 won · 97.4% SAFE** · 2,238f | **€25,084.71 (+€10,070 / +67.1%)**<br>**421 won · 96.7% SAFE** · 3,015f | **€62,641.85** Dual UB<br>*(€50,231 int. opt)* |
| **`dev-07`** | **€14,410.02**<br>338 won · 95.6% | **€21,315.92** (+€6,906)<br>338 won · 95.6% · 2,180f | **€12,738.96** (-€1,671)<br>273 won · 93.4% · 3,551f | **€17,204.12** (+€2,794, `92.6%` SAFE)<br>*Edge (`90.8%`): **€19,119.27** (+€4,709, 381 won)* | **€19,803.59** (+€5,394)<br>**353 won · 94.9% SAFE** · 1,761f | **€20,764.04 (+€6,354 / +44.1%)**<br>**353 won · 93.5% SAFE** · 2,786f | **€70,297.61** Dual UB<br>*(€59,465 int. opt)* |
| **4-World Mean** | **€12,201.00**<br>281.3 won · 96.4% | **€17,022.05** (+€4,821)<br>281.3 won · 96.4% | **€15,612.57** (+€3,412)<br>265.3 won · 94.6% | **€16,466.88** (+€4,266)<br>392.0 won · 96.0% SAFE | **€17,545.26** (+€5,344)<br>394.0 won · 95.2% SAFE | **€19,019.35 (+€6,818 / +55.9%)**<br>**394.5 won · 94.3% SAFE** | **€57,186.91** Dual UB<br>*(€49,029 int. opt)* |

*(Achieved vs Bound note: Our played TAS weeks are 100% realized server trajectories — strict lower bounds on the true theoretical ceiling. The **Proven Lagrangian Dual Upper Bounds** (`€40.4k–€70.3k`) assume zero stochastic cancellations/drops, 48% active driver availability every weekday, max dealer trust without intermediate timing friction, and every closed tour booking at Step 2's minimum `0.313x ref` / `€9.61/h` floor.)*

### 4.2 Step 4 Fleet Efficiency: Cars per Driver-Day & Tour Fee vs Solo Fee (`extract_tour_metrics.py`)

| World (`Full Stack Run`) | Won Cars | Tours Posted (`2c / 3c / 4c`) | Tours Booked (Cars) | **Cars / Tour Driver-Day** | **Overall Cars / Driver-Day** (vs v5 `0.97`) | **Realized Booked Tour Fee / Car (`× ref`)** | **Realized Booked Solo Fee / Car (`× ref`)** |
|---|---:|---|---:|---:|---:|---:|---:|
| **`dev-12` (`elite385-exactfees`)** | 380 | 102 (`62 / 25 / 15`) | 63 (148 cars) | **2.35** | **1.01** (`442`-car `push540`: **1.28**) | **€33.26 / car (`0.544× ref`)** | €120.49 / car (`0.979× ref`) |
| **`dev-01` (`steered440-exactfees`)** | 424 | 93 (`47 / 21 / 25`) | 68 (188 cars) | **2.76** | **1.15** (`424` cars in `369` gigs!) | **€26.96 / car (`0.496× ref`)** | €73.58 / car (`0.958× ref`) |
| **`dev-08` (`steered440-exactfees`)** | 421 | 102 (`56 / 30 / 16`) | 93 (243 cars) | **2.61** | **1.30** (`421` cars in `323` gigs!) | **€31.85 / car (`0.536× ref`)** | €85.51 / car (`0.907× ref`) |
| **`dev-07` (`safe360-exactfees`)** | 353 | 95 (`52 / 29 / 14`) | 61 (146 cars) | **2.39** | **1.09** (`353` cars in `325` gigs) | **€35.38 / car (`0.544× ref`)** | €105.78 / car (`0.943× ref`) |

---

## 5. Step 5: The Rule for Sunday — What Shipped (`Champion v7`) and the One Rule to Bet On Next

### 5.1 Cross-world corridor return predictability (`tas_routes_sunday_rule.py`, 4,142 requests, 0 forks)

| Outbound Corridor | Avg Reqs/wk | `P(return <= 2h)` | `P(return <= 4h)` | **Worst-World `P(<=4h)`** | `P(return <= 18h)` | Avg Closed-Pair Fee Saving |
|---|---:|---:|---:|---:|---:|---:|
| **`Capital -> hyvinkaa`** | 57.2 | **72%** | **84%** | **66%** | **92%** | **€25.20** (+ rescues thin `hyvinkaa`) |
| **`Tampere -> Capital`** | 10.5 | **62%** | **71%** | **60%** | **79%** | **€47.10** |
| **`Turku/SW -> Capital`** | 14.8 | **58%** | **61%** | **38%** | **76%** | **€44.60** |
| **`Capital -> Tampere`** | 33.0 | **45%** | **58%** | **49%** | **73%** | **€43.60** |
| **`lahti -> Capital`** | 12.0 | **40%** | **77%** | **50%** | **81%** | **€30.00** |
| **`Capital -> Turku/SW`** | 41.8 | **29%** | **47%** | **25%** | **59%** | **€44.60** |
| **`Capital -> lahti`** | 21.8 | **34%** | **46%** | **31%** | **57%** | **€31.10** |
| **`Capital <-> Oulu`** | 21.6 | **0%** | **0%** | **0%** | **0%** | *814m > 720m rule -> impossible in 1 gig!* |

### 5.2 Live Forkless Translation & Measured Impact
1. **Our prototype (`src/spread_lab/policies/sunday_tours.py`):**
   - Smoke noop: `Δ = €+0.00 ± 0.00` vs Champion v5.
   - Smoke active (`sunday_tours=True, sunday_stage_min=60, sunday_tour_quote=True`): **`Δmargin €+329.63 ± 137.26 (t = 2.40, 4/4 better, worst on-time 93.7% -> 95.1%)`**; 16-world `dev` (`sunday-tours-dev` + `smoke2` `dev-01`): **`+€203.52 ± 112.18 (12/4 better, worst on-time 95.1%)`**.
2. **Promoted to `main` as Champion v7 (`spread_lab.policies.cycles:Desk`, commit `73fc729`):**
   - Built directly on our Step 2 `0.31x–0.43x` fork bisections + `sunday_tours` + `tas_routes`, adding 15-minute start-town rotation and a `97.5%` projected-on-time hold brake: **`dev +€247 ± 82 (t = 3.01), holdout +€410 ± 126 (t = 3.25), holdout min on-time 94.4%`**.
3. **The ONE Rule Still Left to Bet On Before Sunday 06:00 Freeze ("Sponsored Slow-Closer Pricing on the Southern Triangle"):**
   - Why Champion v7 took `+€410/wk` instead of `+€2,000+/wk`: v7 only forms cycles among the ~25% of requests we *already* win (`~13%` of won cars enter cycles), declining or losing the thin-town return leg (`hyvinkaa/lempaala/raisio/pori/kuopio -> Capital`) 75% of the time!
   - **Rule:** When an unbooked hub order `A -> B` (`supply[A] >= 35`, `lastPickupAt - now >= 480m`) is currently held in v7's cycle buffer, and a clean 1-leg `next_day` / `within_3_days` request `B' -> A'` (`<=30 km` at both ends, road total `<= 680m`) arrives:
     1. **Bypass `min_supply` (`1-to-1` sponsored closer)**, and
     2. **Credit `-0.28 × ref` of expected closed-tour fee savings into its quote floor & target multiplier (`× 0.92` discount on slow options only, capped at `8` closer wins/day, disabled below `96.5%` projected on-time)** — winning the missing half of the loop without ever buying `same_day` lateness risk!
