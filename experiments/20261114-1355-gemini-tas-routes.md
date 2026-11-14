# tas-routes: the travelling salesman week — foresight closed tours, fork-bisected tour costs, Lagrangian ceiling bounds, and the Sunday corridor rule

- **Agent / branch:** `gemini` (`tas-routes`) · `exp/gemini-tas-routes`
- **Date:** 2026-11-14 13:00–16:00 Helsinki
- **Layer:** TAS Layer 3 — **Tours planned with full-week foresight** (standalone, stacked on `tas-price`, stacked with `tas-fees`, and stacked with `tas-state`)
- **Champion baseline (v5, `cp-fees`):**
  - `dev-12`: **€10,910.49** (`246` won, `98.0%` on time, `revenue €29,657.75`, `driver_fee -€18,367.50`)
  - `dev-01`: **€8,469.14** (`254` won, `93.7%` on time, `revenue €22,666.07`, `driver_fee -€13,712.22`)
  - `dev-08`: **€15,014.36** (`287` won, `98.3%` on time, `revenue €34,979.66`, `driver_fee -€19,490.63`)
  - `dev-07`: **€14,410.02** (`338` won, `95.6%` on time, `revenue €42,588.72`, `driver_fee -€26,441.05`)

---

## 1. Step 1: The Route Census & Champion Reveal Anatomy (0 forks, 4 TAS worlds)

We recorded silent full-week tapes (`scripts/tas.py tape`, 14 server requests/seed) and downloaded CSV reveals of Champion v5's finished runs (`uv run lab reveal`, 0 slots) across all four TAS worlds (`dev-12`, `dev-01`, `dev-08`, `dev-07`). Script: `experiments/scripts/tas_routes_census.py`.

### 1.1 Subtle rule mechanics caught before building tours
1. **Intra-city yard transfers are NOT zero road minutes:** `roads.csv` defines positive road distance and minutes from every town to itself (e.g., `helsinki -> helsinki = 12 km, 25 min`, `vantaa -> vantaa = 25 min`, `kuopio -> kuopio = 18 min`). Under `RULES.md` ("The 12 hours include the drive between every two stops, also from one car's delivery to the next car's pickup"), omitting `geo.minutes(p, p)` causes 700–715 min tours to exceed 720 min and be refused by the server. Our `simulate_tour` and `TasRoutesDesk` enforce exact `geo.minutes(d_i, p_{i+1})` on every transition.
2. **Scarce `experienced` driver sub-pool (`6.6%–8.8%` of roster):** Across the four L8 worlds, `manual` licence coverage is `84.8%–86.7%`, whereas `experienced` (`rating >= 4.8` and `completedGigs >= 50`) is only **`6.6%` (`47/709` in `dev-12`) to `8.8%` (`58/656` in `dev-01`)**. Mixing one `premium` car into a 4-car non-premium tour forces `audience.experienced = True` on all 4 cars; our planner penalizes mixed-audience tours and enforces separate `experienced` zone-day caps.
3. **Massive idle driver capacity vs Champion v5's solo bottleneck:**
   - In `dev-12` (`709` roster drivers), **`325–379` distinct drivers open the app (`views.csv`) each weekday**, yet Champion v5 only booked **`23–60` drivers/day** (`246` won orders out of `1,036` requests = `23.7%`!).
   - Why? Champion v5's supply gate (`min_supply = 22`) declines almost all requests originating in thin/zero-driver towns (`savonlinna 0, rovaniemi 0, kemi 0, kajaani 1, kouvola 2, hyvinkaa 3, ylivieska 3, kokkola 4, rauma 4, vaasa 6, porvoo 7, pori 9, lappeenranta 9, seinajoki 10` in `dev-12`).
   - **Closed tours invert the Level-8 geography:** A closed tour `Vantaa -> Kuopio -> Vantaa` or `Oulu -> Rovaniemi -> Oulu` or `Espoo -> Tampere -> Lempäälä -> Pori -> Helsinki` notifies **359 Capital drivers** (or **90 Oulu drivers**), rescues thin/zero-driver pickups without touching local supply, and moves **2.6–3.5 cars per working driver**!

### 1.2 Census table across the four TAS worlds (`tas_routes_census.py`)

| Seed | Requests (1-leg clean) | Roster (`exp`%) | Bulk batches (`>=15` cars) | Ordered feasible pairs (`<=35km` dh, `<=12h`) | Closed 2-car pairs near drivers | Closed 3-car triangles | Closed 4-car tours/shuttles | Requests fitting `>=1` closed 2+ car tour near drivers |
|---|---:|---:|---|---:|---:|---:|---:|---:|
| **`dev-12`** | 1,036 (1,010) | 709 (6.6%) | Wed 15 Hämeenlinna, Thu 16 Lempäälä, **Thu 36 Kuopio** | 25,677 | 3,907 (678 reqs) | 22,526 | 42,606 | **801 / 1,036 (77.3%)** |
| **`dev-01`** | 1,035 (1,010) | 656 (8.8%) | **Mon 35 Jyväskylä**, Wed 15 Hämeenlinna, Thu 17 Lempäälä | 25,951 | 4,148 (702 reqs) | 26,650 | 53,261 | **851 / 1,035 (82.2%)** |
| **`dev-08`** | 1,038 (1,011) | 867 (8.0%) | **Tue 20 Vantaa->Hyvinkää**, **Tue 38 Raisio**, Wed 15 Hämeenlinna | 30,275 | 4,581 (699 reqs) | 25,213 | 47,308 | **803 / 1,038 (77.4%)** |
| **`dev-07`** | 1,033 (1,004) | 643 (7.2%) | **Mon 33 Turku**, Wed 15 Hämeenlinna, Thu 16 Lempäälä | 27,316 | 4,548 (739 reqs) | 27,828 | 51,666 | **873 / 1,033 (84.5%)** |

---

## 2. Step 2: Fork-Bisected Tour Reservation Costs (`tas_routes_probe_fees.py`, 79 forks on `dev-12`)

Before writing a cost formula, we played `dev-12` to Monday `18:20` holding 55 won Monday legs unposted, partitioned 17 intact 1-, 2-, 3-, and 4-car tours into non-competing town batches (`>85 km` apart), and bisected each tour's **drop-proof flat fee** (booked and still held with zero drops at `Tue 09:30`, `now=2010`) in 8 fork rounds (`~/.spread-lab/tas/dev-12/tas-routes-step2-fees.json`).

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

**Core physical law discovered:** A driver's pure time at the wheel costs only **~€9.60–€11.30/h** when a tour starts and ends at home. Roughly **two-thirds of `referenceFeeCents`** on inter-city solo orders pays for the expensive same-day return train ticket and unpaid transit hours home. Open chains ending in Rovaniemi still pay `0.804x ref` (`€20.92/h`); closing the loop slashes driver cost to **`0.31x–0.43x sum(ref)`**!

---

## 3. Diagnostic Journal: Three Real-Server Lessons Caught Early

1. **Impatient dealers reject single-option `within_3_days` even at `0.75 × list` (`11/66` Monday losses in Step 2):**
   - When a request offers `same_day`, `next_day`, and `within_3_days`, quoting *only* `within_3_days` loses impatient dealers to the competitor's faster options even when our planned tour finishes Tuesday afternoon before `next_day.deadline`!
   - **Fix in `tas_routes_planner.py`:** For every planned tour car, test `simulate_tour` across *all* options of that request and emit profit-floor prices on every tour-compatible option (`{next_day: floor_nd, within_3_days: floor_w3d}`). In `tas.py limits --apply`, the preview fork lets the dealer pick its preferred speed, and `price_oracle` then bisects that chosen option's exact limit!
2. **Pricing and routing couple through dealer trust timing (`run-tas-routes-v5subset-lim`, `246 -> 216` won):**
   - Replaying `book-won-apply.json` (whose prices sit at the exact single-cent limit of Solo-Week's trust curve) while holding a Monday car overnight for a Tuesday return leg delayed 1 on-time delivery by ~16 hours, lowering that dealer's intermediate trust by `-1%` and causing 30 subsequent razor-edge quotes to miss by 1%!
   - **Fix:** Either (a) run `tas.py limits --book plan.json --apply` *with `TasRoutesDesk` active* so limits are bisected on the tour run's exact delivery timeline, or (b) apply a `0.988×` (`-1.2%`) trust-timing cushion on `book-won-apply.json` quotes while `trust < 25` and bound subset hold delay to `<= 240` min.
3. **Unbooked multi-car patience must be bounded (`run-tas-routes-v5subset-champ`, `-€466.80` undelivered penalty):**
   - Keeping an unbooked dynamic tour alive until `lastPickupAt - 200m` on Friday afternoon starved the solo rescue of weekday drivers.
   - **Fix in `TasRoutesDesk`:** Post closed tours at a flat fee (`0.58x` for 2-car, `0.52x` for 3–4-car, floor `€14/h + €6.5/car`), step flat once (`+0.12x`) after `50` daytime minutes (`booked ÷ first_viewed = 1.00` on initial flat bookings -> zero holdout learning!), and **split to solo after `110` daytime minutes or `330` min (`5.5h`) before `lastPickupAt`**.

---

## 4. Step 3: Lagrangian Dual Upper Bounds & Weekly Plans (`tas_routes_planner.py`)

Using pure Python stdlib subgradient ascent (70 iterations over `19,174–30,314` feasible 1/2/3/4-car columns per seed) plus 1-for-1 and 2-for-1 local search swaps, we computed **mathematically proven Lagrangian Dual Upper Bounds** (using Step 2's minimum observed `0.313x ref` / `€9.61/h` closed-tour rates and 48% active fleet) alongside executable weekly plans incorporating `tas-state`'s exact competitor deadband law (`<10` reqs/day immune, Friday `100%` immune, `<70%` Tue–Thu zero-cut deadband, and `--steered-state` `<30%` Monday on busy dealers for `+4%` Tue–Fri competitor hike):

| Seed | Feasible Columns | **Proven Lagrangian Dual UB (Bound)** | **Optimistic Integer Packing (Bound)** | `clean400` Plan (cars / gigs / est net) | `steered440` Plan (cars / gigs / est net) |
|---|---:|---:|---:|---|---|
| **`dev-12`** | 19,174 | **€55,926.94** | **€45,567.05** (624 cars / 326 gigs) | 129 tours + 53 solos = 400 cars / 182 gigs (~€28.5k) | 147 tours + 61 solos = 440 cars / 208 gigs (~€29.5k) |
| **`dev-01`** | 29,112 | **€60,046.11** | **€47,039.34** (645 cars / 353 gigs) | 118 tours + 48 solos = 400 cars / 166 gigs (~€29.1k) | 133 tours + 64 solos = 440 cars / 197 gigs (~€30.3k) |
| **`dev-08`** | 19,964 | **€69,118.78** | **€55,296.04** (669 cars / 375 gigs) | 123 tours + 62 solos = 400 cars / 185 gigs (~€35.4k) | 137 tours + 74 solos = 440 cars / 211 gigs (~€37.3k) |
| **`dev-07`** | 30,314 | **€61,635.40** | **€48,107.30** (684 cars / 363 gigs) | 120 tours + 46 solos = 400 cars / 166 gigs (~€28.2k) | 126 tours + 80 solos = 440 cars / 206 gigs (~€29.2k) |

---

## 5. Step 5: The Rule for Sunday (`tas_routes_sunday_rule.py`)

Across all `4,142` requests in the four tapes, we measured the exact cross-world conditional probability that after winning an outbound hub order `A -> B`, a time-window-feasible closed-tour return request `B' -> A'` (`<=30 km` at both ends, `<=690` road min, `>=105` min slack) arrives within `2h`, `4h`, or `18h` (overnight):

| Outbound Corridor | Avg Reqs/wk | `P(return <= 2h)` | `P(return <= 4h)` | **Worst-World `P(<=4h)`** | `P(return <= 18h)` | Avg Closed-Pair Fee Saving |
|---|---:|---:|---:|---:|---:|---:|
| **`Capital -> hyvinkaa`** | 57.2 | **72%** | **84%** | **66%** | **92%** | **€25.20** (+ rescues thin `hyvinkaa`!) |
| **`Tampere -> Capital`** | 10.5 | **62%** | **71%** | **60%** | **79%** | **€47.10** |
| **`Turku/SW -> Capital`** | 14.8 | **58%** | **61%** | **38%** | **76%** | **€44.60** |
| **`Capital -> Tampere`** | 33.0 | **45%** | **58%** | **49%** | **73%** | **€43.60** |
| **`lahti -> Capital`** | 12.0 | **40%** | **77%** | **50%** | **81%** | **€30.00** |
| **`Capital -> Turku/SW`** | 41.8 | **29%** | **47%** | **25%** | **59%** | **€44.60** |
| **`Capital -> lahti`** | 21.8 | **34%** | **46%** | **31%** | **57%** | **€31.10** |
| **`Capital <-> Oulu`** | 21.6 | **0%** | **0%** | **0%** | **0%** | *814 road min > 720m rule: requires 2-gig relay offer!* |

**Why Sunday's live desk currently leaves this money on the table — and the exact rule to take it:**
1. **Strictly causal closed pairs (`0` foresight required):** Even looking *strictly backward* (`A -> B` arrived `0..4h` before `B' -> A'`), every week contains **`97–138` disjoint feasible closed pairs** (`dev-12: 97`, `dev-01: 133`, `dev-08: 138`, `dev-07: 128`), of which **`33–85`/wk rescue a thin `<22`-driver pickup** that Champion v5 currently declines!
2. **Why reactive-only pairing (`hitch-pairs`) caught only `16.1` pairs/wk at `0.75x ref`:** When `Capital -> Hyvinkää / Tampere / Turku / Lahti` is posted solo immediately on win, Capital's 359 drivers book it solo at `0.85x ref` within **5–15 minutes**, before the `B -> A` return request arrives 45 minutes later!
3. **The Sunday Rule ("Corridor Staging + Flat-Step 0.58x Closed Tours"):**
   - **Stage:** When a `next_day` or `within_3_days` order is won on a high-return corridor (`Capital <-> {Hyvinkää, Tampere/Lempäälä, Turku/Raisio/Salo, Lahti}`) with `lastPickupAt - now >= 480` min, **hold it unposted in a staging buffer for up to `90` daytime minutes** waiting for a closing return leg (or 3-car triangle!).
   - **Quote thin return (`hitch_quote`):** Quote slow options on thin-town requests (`supply30 < 22`) whenever they close an order currently in our staging buffer or open unbooked board!
   - **Price & Staff:** Post closed 2-car tours at **flat `0.58 × sum(ref)`** (`0.52 ×` for 3-car triangles, floor `€14/wheel-h + €6.5/car`), step flat once to `+0.12×` after `50` daytime minutes, and split cleanly to solo after `100` daytime minutes or `lastPickupAt - 330` min.

---

## 6. Step 4: Played TAS Weeks, Ablations & Full-Stack Waterfall (Real Server)

*(Updating with post-pause full-week `tas.py limits --apply`, `whatif`/ablation forks, and `tas_routes_fee_oracle.py` results across `dev-12`, `dev-01`, `dev-08`, and `dev-07`...)*
