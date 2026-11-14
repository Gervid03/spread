# return-offer: Inbound-car-gated thin return quoting (`return_offer_km=15`) with delivery-pool repatriation guard (`return_min_deliv_supply=30`)

- **Agent / branch / commit:** gemini-c14 · `exp/gemini-c14-census-then-return-offer` · `9151a8c`
- **Date:** 2026-11-14 08:35 UTC
- **Idea from:** `IDEAS.md` #26 (return-offer form) & #12(a), building on R11 (`20261114-0635-gemini-snow.md`) and R15 (`20261114-0735-gemini-research-network.md`)

## Why we tried it
Leaders win ~430 orders/week while Champion v4 wins `280.2`/week on `dev`, declining `183.4` slow requests/week in thin towns (`gate_supply < 22` within 55 km, outside the 70 km extended ring and outside `<= 180` min thin-to-Capital). Unconditional thin-town quoting (`n14-05162`) cannibalized core drivers and hurt safety on tight rosters (`dev-07`), whereas R11 and R15 showed that `100.4` declined thin slow requests/week arrive while one of our **already-booked outbound gigs** is on its way to deliver within `15 km` of the thin pickup, including `38.9`/week that return into a `>= 30`-driver pool (Tampere, Turku/Raisio, or `> 180` min to Capital) or within `30 km` of the outbound driver's home. Gating thin slow quotes 1-to-1 on active inbound deliveries (`return_offer_km=15`), opening their board schedule at `return_fee_open=1.0`, and sending timed direct offers (`return_offer_mult`, `return_offer_on_win`, `return_offer_lead_min`) tests whether outbound traffic can unlock thin return volume without stranding scarce drivers.

## What changed
- `src/spread_lab/policy.py` (`Desk`, `Params`):
  - **Booked-gig delivery tracker (`booked_deliveries`, `update_gig_deliveries`, `rejoin`):** Tracks every booked gig's driver and the planned delivery minute and place of each of its cars from `gig_booked`, `gig_started`, `driver_late`, `picked_up`, `delivered`, `gig_dropped`/`no_show`, `order_changed`, and `order_cancelled`, accounting for earlier same-day bookings, site opening hours (`next_open_minute`), stop windows, and EV charging (`+30` min), and reconstructs the state on live-mode `rejoin()`.
  - **1-to-1 inbound-gated thin quoting (`return_offer_km: float = 0.0`, `return_markup: float = 0.0`, `return_cap_day: int = 8`, `return_min_deliv_supply: int = 0`, `return_toward_home: bool = False`, `return_max_wait_min: int = 0`):** When a request fails the supply gate (`gate_supply < min_supply` and neither `ext_ring` nor `return_hub`), quotes its feasible slow options (`next_day`, `within_3_days`) at tracker price × `(1 + return_markup)` if an uncommitted active booked gig delivers within `return_offer_km` before pickup close with `>= min_slack_min` slack after reaching pickup, subject to `backlog_near < backlog_min`, `return_cap_day` wins/day, and (when `return_min_deliv_supply > 0`) delivery `30 km` supply `>= return_min_deliv_supply` or `<= 30 km` of the outbound driver's home. Quotes are tracker-neutral (`ret_skipped_learn`).
  - **Board opening & direct offers (`return_fee_open: float = 0.75`, `return_offer_mult: float = 0.90`, `return_offer_lead_min: int = 45`, `return_offer_on_win: bool = False`):** Posts won return orders as single-car gigs opening at `return_fee_open × typical` and dispatches direct offers at `return_offer_mult × typical` during `07:00–22:30` (`return_offer_lead_min` before planned delivery, plus on `order_won` when `return_offer_on_win=True`), strictly respecting `<= 3` offers/driver/day, `<= 3` open offers/gig (`0` `refused_offer` across all runs), and audience rules.
  - **Telemetry counters:** `ret_quoted`, `ret_won`, `ret_offered`, `ret_offered_orders`, `ret_accepted`, `ret_declined`, `ret_expired`, `ret_booked`, `ret_gone_home`, `ret_gone_home_at_win`, `ret_limit_driver`, `ret_limit_gig`, `ret_late`, and `ret_margin_cents` (plus per-ledger-kind breakdowns).
- `experiments/scripts/analyze_return_offers.py`, `experiments/scripts/diagnose_dev07_return.py`: Paired comparison, counter aggregation, and `dev-07` reveal diagnostic scripts.

## Numbers

### Headline Summary (Worst World First, Won Orders/Week, Paired Margin vs Champion v4)
- **Best setting (`d2`: `-s return_offer_km=15 -s return_cap_day=8 -s return_fee_open=1.0 -s return_offer_mult=1.05 -s return_offer_on_win=True -s return_min_deliv_supply=30`):**
  - **Worst `dev` world:** **93.63% on-time** (`dev-01`, `0` worlds under `92%`, **16/16 SAFE**; worst-world margin lifted **`+€534.41`** from `€7,487.67` to **`€8,022.08`**; `dev-07` stays **`93.66%` on-time** with `0/16` late return orders and `+€1,031.84` direct return margin).
  - **Won orders/week:** **`287.7`** on `dev` (vs Champion `280.2`, **`+7.5` won/wk**; `ret_won = 7.62/wk` at **`95.1%` on-time**, `6` late of `122`); **`308.6`** on `night32` (vs Champion `298.0`, **`+10.6` won/wk**).
  - **Paired margin vs Champion v4:**
    - **`dev` (16 worlds):** **`Δmargin = €+307.29 ± 108.65` (`t = 2.83`, better on `12`, tied on `1`, worse on `3`)**, `Δon-time = -0.34%`.
    - **`night32` (32 fresh unseen worlds, vs `20261114-073207-fc-v3T-night32`):** **`Δmargin = €+163.45 ± 92.48` (`t = 1.77`, better on `22`, worse on `10`)**, `32/32` ranked, worst on-time `90.43%` vs Champion `90.57%` (`night-11` improved `91.5% -> 91.8%` `+€245`; `night-15` `90.43%` vs `90.57%` `+€487`; `night-30` `91.97%` rounds to `92.0%`).
    - **Combined 48 paired worlds (`dev16 + night32`):** **`Δmargin = €+211.40 ± 71.15` (`t = 2.97`, better on `34 / 48 = 70.8%`)**.

### Run Table
| Set | Run | Flags (on top of Champion v4) | Mean margin | Δmargin ± SE (t, W/L) | Mean on-time (Δ) | Worst on-time (u92) | Won/wk | SAFE? |
|---|---|---|---|---|---|---|---|---|
| smoke (4) | `20261114-081205-c14-ret-noop` | *(none)* | €10,816.98 | €+0.00 ± 0.00 (0/0) | 96.0% (+0.00%) | 94.38% (0) | 283.2 | yes |
| smoke (4) | `20261114-081334-c14-ret-s1-cap4` | `km=15, cap=4` (`open=0.75, mult=0.9`) | €11,078.27 | €+261.29 ± 283.23 (0.92, 2/2) | 95.5% (-0.48%) | 92.78% (0) | 298.8 | yes |
| smoke (4) | `20261114-081456-c14-ret-s2-cap8` | `km=15, cap=8` (`open=0.75, mult=0.9`) | €11,330.48 | €+513.50 ± 435.11 (1.18, 2/2) | 95.8% (-0.21%) | 92.78% (0) | 300.5 | yes |
| smoke (4) | `20261114-081554-c14-ret-s3-cap8-open10` | `km=15, cap=8, fee_open=1.0` | €11,558.09 | €+741.11 ± 370.90 (2.00, 4/0) | 95.9% (-0.05%) | 93.05% (0) | 298.0 | yes |
| smoke (4) | `20261114-081820-c14-ret-s4-open10-off105-onwin` | `km=15, cap=8, fee_open=1.0, mult=1.05, on_win=True` | €11,643.88 | €+826.90 ± 381.81 (2.17, 4/0) | 96.0% (+0.03%) | 93.05% (0) | 299.0 | yes |
| smoke (4) | `20261114-081902-c14-ret-s5-open10-off115-onwin` | `km=15, cap=8, fee_open=1.0, mult=1.15, on_win=True` | €11,611.53 | €+794.56 ± 397.79 (2.00, 4/0) | 95.9% (-0.07%) | 92.64% (0) | 298.8 | yes |
| smoke (4) | `20261114-082710-c14-ret-s6-deliv30` | `s4` + `return_min_deliv_supply=30` | €11,538.00 | €+721.02 ± 224.11 (3.22, 4/0) | 96.1% (+0.09%) | 93.63% (0) | 294.0 | yes |
| **dev (16)** | `20261114-082004-c14-ret-d1-cap8-open10-off105-onwin` | `km=15, cap=8, fee_open=1.0, mult=1.05, on_win=True` | €11,439.95 | €+555.06 ± 188.11 (2.95, 13/3) | 96.7% (-0.31%) | 90.63% (1: `dev-07`) | 302.3 | **no** |
| **dev (16)** | **`20261114-082804-c14-ret-d2-cap8-open10-deliv30`** | **`d1` + `return_min_deliv_supply=30`** | **€11,192.17** | **€+307.29 ± 108.65 (2.83, 12/3)** | **96.6% (-0.34%)** | **93.63% (0)** | **287.7** | **YES** |
| **night (32)** | **`20261114-083024-c14-ret-night32-deliv30`** | **`d2` flags (vs Champion `fc-v3T-night32`)** | **€11,505.12** | **€+163.45 ± 92.48 (1.77, 22/10)** | **97.0% (-0.29%)** | **90.43% (vs 90.57%)** | **308.6** | **32/32 ranked** |

*(Live-mode restart verification on `dev-01 --restart-at 3600` finished cleanly: `margin €7,780.99, on time 93.7%, ranked True, 0 refused_offer`.)*

### Mechanism Telemetry & Why Direct Offers Themselves Are Rarely Accepted
1. **Why direct offers have a ~1.5–2.6% acceptance rate (`4/152 = 2.6%` on `d2`, `10/579 = 1.7%` on `d1`):**
   - **Driver daily multi-gig appetite & direction (dominant factor):** At level 8, each working driver chooses in the morning *how many gigs to take* and *how late to get home*; R15 Q4 showed only `~19%` of working driver-days ever take `>= 2` gigs. Consequently, even when the targeted outbound driver reads the offer, `55%–59%` explicitly answer `declined` (`s4`: `48` declined vs `1` accepted at `1.05×`; `s5`: `47` declined vs `2` accepted at `1.15×`, showing low fee elasticity between `0.90×` and `1.15×`).
   - **Timing (secondary factor):** Waiting until `delivered` (`lead = 0`) gets `0%` acceptance because drivers immediately commit to their trip home upon finishing (`ret_gone_home` caught `0.31/wk` on `d2` and `1.56/wk` on `d1` finishing during the 15-min quote window alone). Offering `45` min before delivery (`s3`) left `55.6%` (`20/36`) `expired` unread while driving; adding `return_offer_on_win=True` (`s4`, catching pre-start free hours where 84% of organic chains occur) lifted the offer read rate from `44.4%` to `59.8%` (`49/82` read) and added `+€85.79/wk` on smoke.
   - **Limits (minor factor):** On `d2`, the 3-offers/driver/day cap blocked only `0.75/wk` (`12` total) and 3-open-offers/gig blocked `0.12/wk` (`2` total), with `0` `refused_offer`.
2. **Why `return_fee_open=1.0` + `return_min_deliv_supply=30` wins strongly and safely anyway:**
   - Opening return gigs at `0.75×` (`s2`) forced `59%` of won return orders to wait for late climbs (`€112.42/car` paid + `14.3%` late), whereas opening at `return_fee_open=1.0` (`s3`) booked **`63.6%` immediately on the board** during morning pre-start browsing at a *lower* realized cost (`€108.85/car`) and halved `ret_late` (`14.3% -> 7.3%`).
   - Revealing `dev-07` from `d1` (`w81bb413bdc617b5ab524`) showed that **9 out of 9 (`100%`)** late return orders on `dev-07` were thin-to-thin dead ends (`s30_deliv < 20`: `kuopio->oulu`, `kemi->jyvaskyla`, `rovaniemi->pori`, `lahti->oulu`) that stranded scarce drivers far north and doubled `dev-07`'s `deadline_close` (`38 -> 76`), while **11 out of 11 (`100%`)** orders delivering into `s30_deliv >= 30` hubs (`Tampere 173`, `Turku/Raisio 44`, `Capital 325`) delivered on time.
   - Adding `return_min_deliv_supply=30` (allowing `s30_deliv >= 30` or `<= 30 km` of the outbound driver's home) eliminated all `9` `dev-07` return late orders (`dev-07` on-time `90.6% -> 93.7%`), generated **`+€393.53/wk` direct net return margin** on `dev` (`+€411.57/wk` on `night32`), and **reduced** system-wide `deadline_close` (`324 -> 318`), `gig_dropped` (`620 -> 612`), and `gig_expired` (`157 -> 154`) across `dev` by repatriating drivers into core hubs.

## Verdict
**adopt** — `-s return_offer_km=15 -s return_cap_day=8 -s return_fee_open=1.0 -s return_offer_mult=1.05 -s return_offer_on_win=True -s return_min_deliv_supply=30` is **16/16 SAFE on `dev`** (worst on-time **93.63%**, worst-world margin **+€534.41**), gains **€+307.29 ± 108.65/wk (`t = 2.83`, 12/3 W/L, +7.5 won/wk)** on `dev` and **€+163.45 ± 92.48/wk (`t = 1.77`, 22/10 W/L, +10.6 won/wk, 32/32 ranked)** on 32 fresh `night` worlds (**€+211.40 ± 71.15/wk, `t = 2.97`, 34/48 W/L** combined).
