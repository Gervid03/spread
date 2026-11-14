# hitch-pairs: Chain waiting single-car gigs into two-car round-trip/homeward gigs and admit paired thin-town slow requests (`hitch`, `hitch_quote`)

- **Agent / branch / commit:** gemini · `exp/gemini-d14-01-hitch-pairs`
- **Date:** 2026-11-14 08:36 UTC
- **Idea from:** `experiments/IDEAS.md` item **#26 (Hitch: a stuck car rides with the next car going its way — paired-gig form)** and R11 (`experiments/20261114-0635-gemini-snow.md`)

## Why we tried it
1. **Driver notification & ticket economics:** A driver's app notifies them of a gig when its **first** pickup is within 30 km of their home, and for a driver moving two chained cars (`A` then `B`, with `B`'s pickup within 15 km of `A`'s delivery), the second car avoids both `A`'s expensive same-day public-transport return ticket and `B`'s outbound ticket. On Champion v3 (`fee_open = 0.85`), slot-free reveal analysis (`experiments/scripts/scout_hitch.py` on `/tmp/reveals-v3`) showed that 53–63% of `next_day` gigs stay open and unbooked for ≥ 20 minutes (median 24–45 min), creating a standing pool of open outbound gigs.
2. **Unlocking declined thin-town volume:** R11 showed 94 disjoint 1-to-1 outbound-won → thin-return chains per week within 15 km and ≤ 12 h of driving. A thin-town request (`gate_supply < 22`) that fails our supply gate cannot reliably attract a local driver on its own, but if an open dense-pickup gig is already delivering within 15 km of its pickup, pairing them notifies 100–400 hub drivers at `0.85 ×` the sum of the two single opening fees.

## What changed
Implemented behind neutral-default `Params` fields in `src/spread_lab/policy.py` (with subclass alias `src/spread_lab/policies/hitch.py`; noop check `20261114-081604-hitch-pairs-noop` confirmed exact `€+0.00 ± 0.00` parity on all 4 smoke seeds):

- **Flags & parameters:**
  - `hitch: bool = False` (enable `(1)` chain pairing of open unbooked single-car gigs)
  - `hitch_after_min: int = 20` (re-scan open single-car gigs after 20 daytime minutes unbooked, in addition to pairing when an order is won)
  - `hitch_km: float = 15.0` (max straight-line km from `A.delivery` to `B.pickup`)
  - `hitch_fee: float = 0.85` (pair gig opens at `0.85 × (open_A + open_B)`, rising per-gig to `until = min(lastPickupAt_A, lastPickupAt_B) - 3h`)
  - `hitch_patience_min: int = 30` (split unbooked pair after 30 daytime minutes or immediately on `deadline_close` / infeasible drop)
  - `hitch_quote: bool = False` (enable `(2)` quoting slow options at the tracker's price for 1-leg requests failing the supply gate when a feasible waiting partner gig exists, tracker-neutral under `ext_ring_neutral_learn`)
  - `hitch_cap_day: int = 6` (max `hitch_quote` wins per day, with in-flight guard and $\le 3$ in-flight quotes per waiting gig)
  - `hitch_homeward: bool = True`, `hitch_preserve_age: bool = True`, `hitch_max_splits: int = 2` (three safety/acceptance refinements derived from counter x-ray on `dev-07`, detailed below)
- **Exact hours, rules & live-mode mechanics:**
  - Verified server opening-hours semantics against 196 `order.lastPickupAt` timestamps in v3 reveals (`opens <= tod < closes` for dealer `OpeningHours`, `from <= t <= to` for private slots; Rule 4 immediate drop-off at closed dealer deliveries counting at next open). `chain_feasible` requires `supply[A.pickup] >= supply[B.pickup]` (first pickup at the end with more drivers), road driving `drive_A + deadhead + drive_B <= 720` min (12 h, excluding plates/charging per Rule 2), `B`'s pickup open & inside window on arrival, and ≥ `min_slack_min` (150 min) both before the latest valid start minute and in total valid open start minutes.
  - Handled per-gig `driver_fee` ledger accounting (`line.orderId` is `None` on 2-order gigs, keyed by `line.gigId`), all four `order_cancelled` outcomes (`withdrawn`, `released`, `shortened`, `continues` — keeping the booked driver and remaining car's stops on `shortened`/`continues`), `visit_failed` in a 2-car gig (driver continues with the other car while the failed leg retries solo with accumulated `Retry` flags), post-step `tick_hitch()` pairing so `self.booked` reflects all events in the batch before withdrawing, and full `rejoin()` reconstruction of pairs, timers, split history, and daily `hitch_quote` caps (`dev-01` `--restart-at 3600` verified: `€8,734.42`, `95.6%` on time, `ranked=True`).
- **Counter-driven `dev-07` diagnosis & fix:**
  - On our initial unguarded 16-world dev run (`20261114-082644-hitch-pairs-dev-cap6`), 15/16 worlds beat Champion v3 and stayed $\ge 95.0\%$ on time (`Δmargin €+764.58 ± 232.26, t=3.29`), but `dev-07` dropped to `90.65%` on time.
  - Counter x-ray (`analyze_hitch_runs.py`) revealed why: `dev-07` posted **185 pairs with only 3 round trips** (`64.2%` outward-diverging northern chains such as `Capital -> Ring/Mid` + `Ring/Mid -> Oulu`), causing **158 splits (85.4%)**, `hq_paired = 50` on `hq_won = 20`, and `late_pair = 19` (`1` booked vs **18 split**). Worse, per `RULES.md` ("A car that you post again keeps the age of its first posting"), re-posting a split car at `0.85×` reset its rising schedule on an aged car!
  - Adding `hitch_homeward` (`line_km(B.delivery, A.pickup) <= max(60 km, line_km(A.delivery, A.pickup) + 25 km)`, blocking outward-diverging chains), `hitch_preserve_age` (resuming split single-car schedules at `first_posted_at` age), and universal `hitch_max_splits = 2` lifted `dev-07` from `90.65%` / `€8,698.60` to **`95.32%` on time / `€12,569.01` (`+€1,900` over Champion v3)** and raised pair booking rate on dev from `27%` to **`61.0%`**.

## Result

### Worst world, volume, and margin on 16 dev worlds (headline summary)
- **Best configuration (`-s hitch=True -s hitch_quote=True`, `hitch_cap_day=6`, run `20261114-083310-hitch-pairs-dev-v2-cap6`):**
  1. **Worst world:** **`dev-14` at `93.92%` on time** (`€8,679.54` margin, `263` won); **0 of 16 worlds under 92%** (`SAFE`, `16/16` ranked). Worst margin world is **`dev-05` at `€8,087.53`** (`97.87%` on time), up **`+€473.05`** over Champion v3's worst margin (`dev-01` at `€7,614.48`, worst on-time `dev-07` at `94.38%`).
  2. **Won orders a week:** **`285.3` won/wk** vs **`281.1` won/wk** on Champion v3 (**`+4.2` orders/wk**, driven by `4.8` thin-town `hitch_quote` wins/wk).
  3. **Margin against the champion:** **`€11,173.67/wk`** vs **`€10,529.42/wk`** -> **`Δmargin €+644.26 ± 147.02 (SE), t = 4.38`, better on `14/16` seeds, worse on `2/16`, `Δon-time +0.01%`**.
- **With `hitch_cap_day=12` (`-s hitch=True -s hitch_quote=True -s hitch_cap_day=12`, run `20261114-083407-hitch-pairs-dev-v2-cap12`):**
  1. **Worst world:** **`dev-14` at `93.92%` on time** (`0/16` worlds under 92%, `SAFE`); worst margin **`dev-05` at `€8,087.53`**.
  2. **Won orders a week:** **`285.2` won/wk** (`+4.1`/wk vs Champion v3).
  3. **Margin against the champion:** **`€11,154.44/wk`** -> **`Δmargin €+625.02 ± 136.98 (SE), t = 4.56`, better on `14/16` seeds, worse on `2/16`, `Δon-time +0.03%`**. (Identical on 15/16 seeds because homeward `hitch_quote` wins naturally average `0–5`/day; on `dev-07`, `cap=6` saved `+€307.76` during heavy northern volume.)

### Full evaluation table (`summary.json` & paired comparison vs Champion v3)

| Run / Set | Seeds | Flags (on Champion v3) | Mean Margin | Δmargin ± SE | t-stat | Win/Loss | Won/wk | Mean OT | Worst OT (under 92%) | SAFE? |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---|
| `hitch-pairs-noop` | smoke (4) | *(defaults)* | €10,892.44 | €+0.00 ± 0.00 | — | 0 / 0 | 287.2 | 96.59% | 94.42% (`0/4`) | yes |
| `s1-pair-only` | smoke (4) | `hitch=True` *(pre-batch/homeward)* | €11,742.45 | €+850.01 ± 349.67 | 2.43 | 4 / 0 | 289.8 | 96.73% | 93.98% (`0/4`) | yes |
| `s3-pair-only-v2` | smoke (4) | `hitch=True` *(pre-homeward)* | €12,023.02 | €+1,130.58 ± 408.42 | 2.77 | 4 / 0 | 288.2 | 96.59% | 95.60% (`0/4`) | yes |
| `s2-pair-and-quote` | smoke (4) | `hitch=True, hitch_quote=True` *(pre-homeward)* | €12,368.08 | €+1,475.65 ± 291.27 | 5.07 | 4 / 0 | 295.5 | 96.41% | 95.02% (`0/4`) | yes |
| `s4-guard` | smoke (4) | `+ hitch_max_splits=1, min_saving_floor=True` | €11,769.66 | €+877.22 ± 221.70 | 3.96 | 4 / 0 | 296.8 | 96.73% | 95.00% (`0/4`) | yes |
| `dev-cap6` *(v1)* | dev (16) | `hitch=True, hitch_quote=True` *(no homeward)* | €11,294.00 | €+764.58 ± 232.26 | 3.29 | 15 / 1 | 289.4 | 96.65% | **90.65% (`1/16`, `dev-07`)** | **no** |
| `s6-pair-only-homeward` | smoke (4) | `hitch=True` *(with homeward + age)* | €11,368.59 | €+476.15 ± 183.78 | 2.59 | 4 / 0 | 288.8 | 96.80% | 95.29% (`0/4`) | yes |
| `s5-homeward` | smoke (4) | `hitch=True, hitch_quote=True` *(cap 6)* | €11,787.18 | €+894.74 ± 80.95 | 11.05 | 4 / 0 | 293.2 | 96.72% | 95.82% (`0/4`) | yes |
| **`dev-v2-cap6`** | **dev (16)** | **`hitch=True, hitch_quote=True`** *(cap 6)* | **€11,173.67** | **€+644.26 ± 147.02** | **4.38** | **14 / 2** | **285.3** | **97.17%** | **93.92% (`0/16`, `dev-14`)** | **yes** |
| **`dev-v2-cap12`** | **dev (16)** | **`hitch=True, hitch_quote=True, hitch_cap_day=12`** | **€11,154.44** | **€+625.02 ± 136.98** | **4.56** | **14 / 2** | **285.2** | **97.19%** | **93.92% (`0/16`, `dev-14`)** | **yes** |

### Mechanism counters on 16 dev worlds (`20261114-083310-hitch-pairs-dev-v2-cap6`)
- **Pairs posted, booked, split:** `26.4` pairs posted/wk (`423` total across 16 worlds; `160` with thin `B` pickup, `149` round trips within 30 km) · **`16.1` booked/wk (`257` total, `60.8%` booking rate)** · `13.1` split/wk (`209` total: `204` patience, `3` deadline warning, `2` post-drop).
- **Quoted and won through `hitch_quote`:** `18.1` thin-gate slow requests quoted/wk (`290` total) · **`4.8` won/wk (`77` total, `26.6%` win rate)** · `5.1` pair postings involving `hitch_quote` orders/wk (`82` total) · **only `1` late order out of `77` `hitch_quote` wins (`98.7%` on time)**.
- **Late orders in pairs:** Across all 16 worlds (`4,565` won orders), **only `1` order in a booked hitch pair was late** (`hitch_late_booked = 1` across `257` booked pair gigs, **`99.8%` on time**; `hitch_late = 18` total including orders whose pair split after 30 min and ran solo).
- **Pair fee against the two single fees:** On `13.9` completed 2-car hitch gigs paid per week (`222` completed pair gigs), realized `driver_fee` averaged **`€970.7/wk`**, compared with **`€1,105.4/wk`** for the sum of the two single opening fees (**`0.878×`**, saving `€134.7/wk` below `0.85×` openings) and **`€1,300.4/wk`** for the sum of the two reference fees (**`0.746×`**, saving `€329.7/wk` vs reference).

## Verdict
**adopt** (`-s hitch=True -s hitch_quote=True`) — SAFE across all 16 dev worlds (`0/16` under 92%, worst world `dev-14` at `93.92%` on time, worst margin `€8,087.53`), lifting won volume to `285.3`/wk (`+4.2`/wk) and paired margin by **`€+644.26 ± 147.02` (`t = 4.38`, `14/16` seeds better, `Δon-time +0.01%`)** with `99.8%` on-time delivery on booked pairs.
