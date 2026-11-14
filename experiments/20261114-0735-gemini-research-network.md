# research-network: R15 census of driver finishes, continuations, redundancy, organic chaining, and seeding on Champion v3

- **Agent / branch / commit:** gemini-c14 · `exp/gemini-c14-census-then-return-offer`
- **Date:** 2026-11-14 07:35 UTC
- **Idea from:** `experiments/IDEAS.md` **R15 (The network census)**, feeding **Idea #31 (The route network)** and **Idea #26 (Return offer)**

## Why we tried it
Drivers—not dealer demand—are our binding constraint on level-8 worlds: top-10 teams win `410–465` orders/week while Champion v3 wins `289.8` orders/week and declines `~238` thin-pickup requests/week (`< 22`–`30` drivers within `55 km`). A driver delivering one of our cars far from home incurs zero deadhead to a nearby continuation pickup and, if that continuation returns toward their home, saves the expensive same-day public-transport return ticket (`RULES.md`). Because the drivers' app only sends push notifications for pickups within `30 km` of a driver's **home**, reaching an outbound driver requires a **direct offer**.

Extending R11 (which counted same/next-day `<= 15 km` pairs on 3 v3 worlds and 16 v2 worlds), R15 measures across **all 16 Champion v3 dev worlds (`dev-01`..`dev-16`)** the exact weekly flow of finishes by town and 2-hour block, tight-window continuations (`ready` in `[finish - 1h, finish + 3h]`), candidate redundancy (`0, 1, 2, 3, 4+` finishing drivers per pickup), organic multi-gig driver-days and in-gig browsing (`views.csv`), outbound seeding potential, and the expected order prize at offer acceptance rates `p ∈ {0.2, 0.4, 0.6}`.

## What changed
- Added standard-library scouting script `experiments/scripts/scout_network.py` (no policy changes; zero practice slots used; revealed all 16 Champion v3 dev worlds from `champion/results/dev-L8.jsonl`).
- Run command: `uv run python experiments/scripts/scout_network.py runs/reveals-v3`

---

## Results across 16 Champion v3 dev worlds (`mean [min..max]` per week)

### 1. Finishes: where and when our drivers deliver, and how many finish `> 30 km` from home

- **Total delivered cars / week:** `282.8 [246..338]` (`275.6 [240..335]` gig-final finishes).
- **Finishes `> 30 km` from the driver's home:** **`180.6 [144..228]` (`64.1%`)** (`175.6 [140..226]` = `63.9%` of gig-final finishes). Outside Helsinki/Espoo/Vantaa, **52%–100%** of our deliveries leave the driver more than `30 km` from home, invisible to local home-radius notifications.

#### Finishes by world day and by 2-hour clock block
| World Day | Finishes / wk (`mean [range]`) | 2-Hour Block | Finishes / wk (`mean [range]`) | Per Weekday (`/5`) |
|---|---:|---|---:|---:|
| **Mon** (`d=0`) | `12.4 [1..21]` | `00:00–08:00` | `1.5 [0..4]` | `0.28` |
| **Tue** (`d=1`) | `47.8 [34..67]` | `08:00–10:00` | `22.4 [13..33]` | `4.49` |
| **Wed** (`d=2`) | `53.8 [39..69]` | `10:00–12:00` | `43.5 [29..60]` | `8.70` |
| **Thu** (`d=3`) | `55.8 [34..73]` | `12:00–14:00` | `53.9 [40..66]` | `10.79` |
| **Fri** (`d=4`) | `76.1 [58..109]` | `14:00–16:00` | `46.9 [31..76]` | `9.39` |
| **Sat** (`d=5`) | `12.6 [5..22]` | `16:00–18:00` | `56.1 [47..64]` | `11.22` |
| **Sun** (`d=6`) | `0.0 [0..0]` | `18:00–20:00` | `50.4 [34..66]` | `10.09` |
| **Mon2+** (`d>=7`) | `24.2 [11..42]` | `20:00–24:00` | `8.0 [4..13]` | `1.60` |

#### Finishes by town (all 30 places: weekly total, `> 30 km` from home, Mon–Fri/day, and per-day 2-hour blocks)
| Town | Finishes / wk | `> 30 km` home / wk | `% >30km` | Mon–Fri / day | `08-10` | `10-12` | `12-14` | `14-16` | `16-18` | `18-20` | `20-22` |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `hyvinkaa` | `24.6 [8..51]` | `21.1 [7..46]` | `86.0%` | `4.44` | `0.49` | `1.00` | `0.75` | `0.68` | `1.04` | `0.84` | `0.11` |
| `vantaa` | `23.8 [9..42]` | `1.5 [0..8]` | `6.3%` | `4.22` | `0.76` | `0.79` | `0.53` | `0.50` | `1.25` | `0.79` | `0.07` |
| `espoo` | `21.3 [11..43]` | `1.2 [0..5]` | `5.6%` | `4.04` | `0.70` | `0.86` | `0.60` | `0.36` | `0.97` | `0.59` | `0.15` |
| `lahti` | `20.5 [11..32]` | `16.1 [7..30]` | `78.4%` | `3.68` | `0.39` | `0.78` | `0.57` | `0.42` | `0.91` | `0.90` | `0.12` |
| `helsinki` | `17.8 [5..36]` | `0.9 [0..2]` | `4.9%` | `3.38` | `0.45` | `0.65` | `0.55` | `0.41` | `0.82` | `0.54` | `0.06` |
| `jyvaskyla` | `15.1 [7..27]` | `11.1 [3..22]` | `73.9%` | `2.71` | `0.06` | `0.50` | `0.80` | `0.74` | `0.46` | `0.38` | `0.06` |
| `oulu` | `14.4 [2..28]` | `10.6 [1..28]` | `73.6%` | `2.12` | `0.00` | `0.01` | `0.28` | `1.04` | `0.69` | `0.66` | `0.19` |
| `tampere` | `14.1 [6..26]` | `7.2 [2..17]` | `51.6%` | `2.40` | `0.31` | `0.40` | `0.45` | `0.34` | `0.55` | `0.69` | `0.07` |
| `turku` | `13.3 [4..29]` | `8.9 [1..24]` | `66.7%` | `2.40` | `0.20` | `0.61` | `0.39` | `0.25` | `0.41` | `0.69` | `0.11` |
| `lempaala` | `13.1 [5..21]` | `7.5 [1..15]` | `57.4%` | `2.35` | `0.25` | `0.55` | `0.47` | `0.41` | `0.47` | `0.42` | `0.03` |
| `raisio` | `12.1 [3..25]` | `8.7 [2..21]` | `72.0%` | `2.15` | `0.25` | `0.47` | `0.53` | `0.44` | `0.33` | `0.39` | `0.01` |
| `kuopio` | `10.7 [2..19]` | `9.1 [2..18]` | `85.4%` | `1.69` | `0.00` | `0.17` | `0.65` | `0.59` | `0.44` | `0.20` | `0.05` |
| `vaasa` | `9.0 [2..17]` | `8.6 [2..16]` | `95.1%` | `1.43` | `0.00` | `0.11` | `0.75` | `0.39` | `0.31` | `0.20` | `0.04` |
| `pori` | `8.9 [4..14]` | `8.4 [4..13]` | `93.7%` | `1.66` | `0.09` | `0.16` | `0.46` | `0.34` | `0.20` | `0.46` | `0.07` |
| `porvoo` | `8.4 [3..20]` | `7.6 [2..15]` | `89.6%` | `1.45` | `0.14` | `0.41` | `0.28` | `0.21` | `0.29` | `0.29` | `0.06` |
| `mikkeli` | `7.0 [2..23]` | `6.5 [2..19]` | `92.9%` | `1.26` | `0.03` | `0.30` | `0.26` | `0.17` | `0.21` | `0.39` | `0.04` |
| `ylivieska` | `6.2 [1..11]` | `6.1 [1..11]` | `99.0%` | `1.05` | `0.01` | `0.01` | `0.38` | `0.44` | `0.26` | `0.10` | `0.03` |
| `kouvola` | `5.8 [1..15]` | `5.6 [1..15]` | `96.8%` | `0.95` | `0.14` | `0.15` | `0.21` | `0.12` | `0.19` | `0.34` | `0.01` |
| `joensuu` | `4.8 [1..13]` | `4.3 [1..10]` | `89.6%` | `0.72` | `0.00` | `0.04` | `0.34` | `0.33` | `0.16` | `0.07` | `0.01` |
| `kokkola` | `4.8 [0..13]` | `4.4 [0..10]` | `92.1%` | `0.80` | `0.01` | `0.03` | `0.31` | `0.29` | `0.19` | `0.11` | `0.01` |
| `lappeenranta` | `4.6 [1..11]` | `3.8 [1..10]` | `83.6%` | `0.78` | `0.05` | `0.16` | `0.26` | `0.16` | `0.10` | `0.16` | `0.01` |
| `salo` | `4.5 [0..9]` | `4.4 [0..9]` | `97.2%` | `0.82` | `0.06` | `0.14` | `0.12` | `0.15` | `0.20` | `0.19` | `0.04` |
| `rovaniemi` | `3.8 [0..8]` | `3.8 [0..8]` | `100.0%` | `0.36` | `0.01` | `0.00` | `0.06` | `0.05` | `0.29` | `0.25` | `0.04` |
| `seinajoki` | `3.4 [0..8]` | `2.8 [0..8]` | `83.3%` | `0.65` | `0.00` | `0.05` | `0.24` | `0.17` | `0.06` | `0.10` | `0.05` |
| `hameenlinna` | `3.2 [0..11]` | `3.0 [0..10]` | `94.1%` | `0.50` | `0.07` | `0.12` | `0.09` | `0.06` | `0.14` | `0.12` | `0.01` |
| `kemi` | `1.9 [0..6]` | `1.9 [0..6]` | `100.0%` | `0.26` | `0.00` | `0.04` | `0.04` | `0.09` | `0.09` | `0.09` | `0.01` |
| `kajaani` | `1.6 [0..7]` | `1.6 [0..6]` | `96.2%` | `0.23` | `0.00` | `0.00` | `0.11` | `0.10` | `0.07` | `0.04` | `0.00` |
| `kotka` | `1.6 [0..5]` | `1.4 [0..5]` | `92.0%` | `0.26` | `0.01` | `0.07` | `0.07` | `0.03` | `0.06` | `0.05` | `0.01` |
| `rauma` | `1.4 [0..8]` | `1.4 [0..8]` | `95.7%` | `0.26` | `0.00` | `0.07` | `0.07` | `0.07` | `0.05` | `0.01` | `0.00` |
| `savonlinna` | `1.3 [0..6]` | `1.2 [0..5]` | `90.5%` | `0.16` | `0.00` | `0.03` | `0.16` | `0.04` | `0.00` | `0.04` | `0.00` |

---

### 2. Continuations: requests ready in `[finish - 1h, finish + 3h]`, deliverable on time by road minutes

Requests (not pairs) Partitioned into **Home-bound** (`delivery <= 30 km` of at least one candidate driver's home), **Capital (non-HB)** (`delivery in {helsinki, espoo, vantaa}` and not home-bound), and **Other (non-HB)**; plus exact maximum-cardinality **1-to-1 disjoint pairs** matching home-bound edges first:

| Metric | Pickup `<= 15 km` of finish | Pickup `<= 30 km` of finish |
|---|---:|---:|
| **Unique continuation requests (all outcomes)** | **`446.2 [346..544]`** | **`505.1 [393..567]`** |
| └─ with `>= 180 min` slack & audience match | `428.6 [334..518]` | `486.8 [379..545]` |
| **Split 1: Home-bound (`<= 30 km` of driver home)** | **`113.1 [86..141]`** *(102.4 also Capital)* | **`131.8 [99..155]`** *(117.1 also Capital)* |
| **Split 2: Capital delivery (non-HB)** | **`13.8 [3..24]`** *(116.2 total Cap)* | **`14.8 [4..26]`** *(131.8 total Cap)* |
| **Split 3: Other delivery (non-HB)** | **`319.2 [249..401]`** | **`358.5 [278..407]`** |
| Outcome = `won` (all / HB) | `151.8 [98..204]` / `34.2 [12..68]` | `176.1 [103..223]` / `40.8 [12..72]` |
| Outcome = `lost`, competitively quoted (all / HB) | `225.8 [165..278]` / `67.8 [39..97]` | `255.8 [188..296]` / `78.9 [57..108]` |
| Outcome = `declined`, 4× list gate (all / HB) | `68.6 [41..108]` / `11.2 [3..22]` | `73.1 [42..113]` / `12.2 [3..23]` |
| **Disjoint 1-to-1 pairs (all outcomes, HB first)** | **`131.4 [104..170]`** | **`140.0 [110..185]`** |
| ├─ Home-bound disjoint | `63.5 [48..82]` | `72.9 [52..99]` |
| ├─ Capital (non-HB) disjoint | `11.8 [5..24]` | `12.6 [6..26]` |
| └─ Other (non-HB) disjoint | `56.1 [45..69]` | `54.5 [43..71]` |
| **Disjoint 1-to-1 pairs (`lost + declined` only, HB first)** | **`117.1 [90..157]`** *(HB `49.7`)* | **`127.3 [97..176]`** *(HB `56.8`)* |
| **Disjoint 1-to-1 pairs (`declined` thin only, HB first)** | **`44.3 [27..58]`** *(HB `9.5`)* | **`47.4 [28..62]`** *(HB `10.6`)* |

---

### 3. Redundancy: distinct candidate finishing drivers per request (`0, 1, 2, 3, 4+`)

| Candidates | `<= 15 km` All Reqs | `<= 15 km` HB | `<= 15 km` Declined | `<= 30 km` All Reqs | `<= 30 km` HB | `<= 30 km` Non-Won | `<= 30 km` Declined | `<= 30 km` Outside Cap+Hyvinkää |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **`0`** | `588.4 [487..688]` | — | — | `529.6 [468..641]` | — | — | — | — |
| **`1`** | `213.4 [146..310]` | `45.6 [29..58]` | `39.6 [20..63]` | `180.8 [129..236]` | `39.1 [28..56]` | `127.7 [98..158]` | `38.9 [21..60]` | `73.4 [40..112]` |
| **`2`** | `106.3 [69..158]` | `30.1 [14..57]` | `16.2 [9..32]` | `122.4 [70..185]` | `33.4 [18..47]` | `78.6 [41..112]` | `17.2 [5..30]` | `41.8 [25..63]` |
| **`3`** | `57.0 [24..104]` | `16.3 [7..25]` | `7.1 [1..18]` | `75.2 [31..133]` | `20.6 [10..38]` | `49.4 [23..79]` | `7.8 [0..18]` | `15.6 [2..38]` |
| **`4+`** | `69.4 [22..147]` | `21.1 [5..47]` | `5.7 [1..14]` | `126.6 [32..251]` | `38.7 [8..78]` | `73.2 [24..127]` | `9.2 [1..20]` | `13.8 [2..33]` |

**Key redundancy finding:** Aggregate redundancy looks high (`324.2 / 505.1 = 64.2%` have `>= 2` candidates and `40.0%` have `>= 3` within `30 km`), **but it is sharply bimodal**:
- In the Capital + Hyvinkää ring and major corridors (`lahti`, `tampere`/`lempaala`, `turku`/`raisio`), `2–4+` candidates are common.
- On **declined thin-gate requests**, **`53.2%` (`38.9 / 73.1` at `<= 30 km`) and `57.7%` (`39.6 / 68.6` at `<= 15 km`) have only a single candidate driver**, and `76.7%` have at most 2. Thus 3-driver fanout helps strongly on dense/corridor continuations, while thin-town pickups usually depend on **1 (occasionally 2) driver**, making offer timing and fee critical.

---

### 4. Organic chaining and views from working drivers

| Metric | Per Week (`mean [range]`) / Pooled Value |
|---|---:|
| Driver-days with `>= 2` executed gigs of ours | `49.6 [36..65]` |
| Consecutive same-day gig pairs / week (`922` pooled pairs) | `57.6 [42..74]` |
| ├─ 2nd pickup `<= 30 km` of driver's home (notification-reachable) | `32.2 [19..48]` (`55.9%`) |
| └─ 2nd pickup `> 30 km` of driver's home (found via app browsing) | `25.4 [19..37]` (`44.1%`) |
| ├─ 1st delivery `->` 2nd pickup `<= 15 km` / `<= 30 km` | `12.2 [4..25]` / `18.4 [9..38]` |
| └─ **2nd gig booked AFTER 1st delivery completed** | **`1.0 [0..3]` (`1.7%`!)** |
| Distance 1st delivery `->` 2nd pickup (all / `<=30km` home / `>30km` home) | mean `106.7 km`, med `84.1 km` (med `38.8 km` near home vs `113.1 km` far) |
| Minutes between 1st delivery and 2nd pickup (all / near / far) | mean `120.8 min`, med `105 min` (med `82 min` near home vs `123 min` far) |
| `booked_fee / typical_fee`: 1st gig `->` 2nd gig (all `922` pairs) | `0.934` (med `0.850`) `->` **`0.989`** (med `0.882`) |
| `booked_fee / typical_fee`: when 2nd pickup `> 30 km` from home (`n=407`) | `0.952 ->` **`1.027`** *(vs `0.920 -> 0.958` when `<= 30 km` from home)* |
| Total gig views / week (`views.csv`) | `10,321.9 [6729..14879]` |
| **Views from drivers actively working one of our gigs (`gig_started..done`)** | **`803.2 [422..1380]` (`7.78%` of all views; `799.8` on *other* gigs, `88.2` drivers/wk)** |
| Views from drivers holding a pre-start booking of ours (`booked..started`) | `1,628.4 [1214..2587]` (`15.8%` of all views) |

**Critical operational finding from Q4:** **`98.3%` (`56.6 / 57.6`) of organic same-day chains are booked BEFORE the driver finishes delivering the first car!** Working drivers actively browse (`803` views/wk while driving, `1,628` while holding a pre-start booking), and once a gig finishes far from home without a pre-arranged next gig, the driver buys their ticket home. Therefore **direct offers must be sent BEFORE planned finish (e.g. `net_lead_min = 60` min or as soon as the gig is open while the driver is en route)**—waiting until `delivered` is too late.

---

### 5. Seeding: lost/declined requests from `>= 100`-driver hubs delivering within `30 km` of towns with `>= 6` requests/wk

*(Active `>= 6`-request towns per week: `23.4 [21..25]` of 30 places; median hub pickup lag from `max(respondBy, ready)`: `206.6 [152..312]` min.)*

| Seeding Slice | Requests / wk | Our `quote ÷ list` | Continuations / win (`<= 15 km` total / **new `0->1`**) | Continuations / win (`<= 30 km` total / **new `0->1`**) |
|---|---:|---:|---:|---:|
| **All (`pickup >= 100`, deliv `<= 30 km` of `>=6`-req town)** | `218.2 [159..298]` | `1.798 [1.648..2.165]` | `4.20 [2.72..6.03]` / **`0.88`** | `5.65 [4.12..7.26]` / **`0.77`** |
| ├─ **Lost (competitively quoted)** | `197.8 [141..278]` | **`1.564 [1.444..1.667]`** | `4.38 [3.17..6.20]` / **`0.92`** | `5.88 [4.18..7.29]` / **`0.81`** |
| ├─ **Declined (`4×` list gate)** | `20.4 [10..52]` | `4.000 [4.000..4.000]` | `2.63 [0.50..5.73]` / `0.50` | `3.84 [0.56..6.73]` / `0.35` |
| ├─ **Outbound to non-Capital (`< 100` drv at deliv)** | `146.5 [111..187]` | `1.800 [1.626..2.249]` | `2.99 [1.54..6.17]` / **`0.95`** | `3.16 [1.96..6.73]` / **`0.95`** |
| └─ **Outbound to thin (`< 30` in `55 km`) & competitively lost** | `53.5 [13..113]` | **`1.574 [1.480..1.718]`** | `0.88 [0.17..2.23]` / **`0.27`** | `0.97 [0.17..2.72]` / **`0.26`** |

**Seeding takeaway:** Each outbound non-Capital win opens `~3.0` continuations, of which `~0.95` are *brand-new* (`0 -> 1` candidate) and `~2.0` add `1 -> 2+` redundancy; however, for truly thin towns (`< 30` in `55 km`), each seeded win unlocks only `0.26` brand-new thin continuations because Champion v3 already delivers `180.6` cars/week `> 30 km` from home (`47.4` disjoint thin continuations/week already sit uncaptured!). Capture (`net_offer` + `net_quote`) matters much more than `net_seed`.

---

### 6. Size of the prize (fanout `min(k, 3)`, offer acceptance `p ∈ {0.2, 0.4, 0.6}`)

Expected orders/week where `P(accepted) = 1 - (1 - p)^min(k, 3)`, shown both as the `100%` quote-win ceiling on non-won continuations and at a realistic **`40%` dealer quote win rate** (capped by disjoint finishes so no driver is double-counted), plus already-won orders staffed cheaply via direct offer:

| Radius | Offer `p` | Declined Thin `@40%` win (Total / **HB** / not-HB) | All Non-Won `@40%` win, Disjoint-Capped (Total / **HB** / not-HB) | Non-Won `100%` Ceiling (Total / **HB** / not-HB) | Already-Won Staffed Cheaper (Total / **HB** / not-HB) |
|---|---:|---:|---:|---:|---:|
| **`<= 15 km`** | **`0.2`** | **`8.0`** (`1.5` / `6.5`) | **`36.9`** (`10.4` / `26.5`) | `92.3` (`26.1` / `66.2`) | `50.3` (`12.1` / `38.2`) |
| **`<= 15 km`** | **`0.4`** | **`14.5`** (`2.6` / `11.9`) | **`65.4`** (`18.4` / `47.0`) | `164.2` (`45.9` / `118.3`) | `88.3` (`20.9` / `67.4`) |
| **`<= 15 km`** | **`0.6`** | **`19.7`** (`3.4` / `16.3`) | **`83.1`** (`24.2` / `58.9`) | `219.4` (`60.6` / `158.8`) | `116.4` (`27.1` / `89.2`) |
| **`<= 30 km`** | **`0.2`** | **`8.9`** (`1.7` / `7.2`) | **`45.5`** (`13.3` / `32.1`) | `113.7` (`33.4` / `80.3`) | `65.0` (`15.4` / `49.6`) |
| **`<= 30 km`** | **`0.4`** | **`16.0`** (`3.0` / `13.0`) | **`78.3`** (`22.9` / `55.4`) | `197.5` (`57.3` / `140.3`) | `111.4` (`26.2` / `85.1`) |
| **`<= 30 km`** | **`0.6`** | **`21.5`** (`3.9` / `17.6`) | **`92.9`** (`29.4` / `63.4`) | `257.4` (`73.6` / `183.9`) | `142.8` (`33.5` / `109.4`) |

## Verdict
**research (strong go for Idea #31 `net_offer` + `net_quote`, cautious/small on `net_seed`)** —
1. **The network is large enough to matter:** `180.6` of our `282.8` weekly deliveries (`64.1%`) finish `> 30 km` from the driver's home, creating `505.1` continuation requests/week within `30 km` (`140.0` disjoint 1-to-1 chains/week, `127.3` on lost+declined, `47.4` on declined thin requests), worth **`+45 to +93` extra orders/week** across all non-won continuations (`+9 to +22`/wk on declined thin alone) plus fee savings on **`65 to 143` already-won orders/week** at `p = 0.2–0.6`.
2. **Redundancy is bimodal:** Common in Capital/Ring/corridors (`64.2%` overall have `2+` candidates, `40.0%` have `3+` at `<= 30 km`), **rare on thin-gate pickups** (`53.2%` at `<= 30 km` and `57.7%` at `<= 15 km` have **only 1 candidate**)—so send offers **before finish** (`98.3%` of organic chains book before the 1st delivery completes!).
3. **Home-bound continuations exist in very useful numbers (`131.8/wk` requests, `72.9/wk` disjoint pairs at `<= 30 km`; `89%` of them return Capital-based outbound drivers back to the Capital)**, though on *declined thin* requests specifically only `12.2 / 73.1` (`16.7%`, `10.6` disjoint/wk) are home-bound to the outbound driver—so non-home-bound offers (`0.80×–0.90×` typical fee) carry 4× the thin-pickup volume of home-bound-only offers.
