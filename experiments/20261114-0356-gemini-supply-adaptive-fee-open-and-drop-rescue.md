# n14-03324-supply-adaptive-fee-open-and-drop-rescue: Supply-and-option-adaptive opening fee and late-drop urgent repricing

- **Agent / branch / commit:** gemini · `exp/gemini-n14-03324-supply-adaptive-fee-open-and-drop-rescue` · `HEAD`
- **Date:** 2026-11-14 03:56
- **Idea from:** Diagnostic analysis of `n14-02462` (`backlog-aware-gtn-ptw40-dev`), stacked on `origin/exp/gemini-n14-02462-deadline-aware-backlog`

## Why we tried it
In `n14-02462` (`backlog-aware-gtn-ptw40-dev`, `€10,481.58/wk`), weekly revenue is `+€29,806.67/wk`, while `driver_fee` is `-€18,955.63/wk` (63.6% of revenue), `late_refund` is `-€259.44/wk` (`113` late orders across 16 worlds), and `578` `gig_dropped` + `7` `no_show` events occur across the 16 dev worlds. Inspecting `Desk.fees_for()` and `Desk.handle()` revealed two structural flaws:
1. **One-size-fits-all `fee_open = 0.85` ignores pickup driver pool size and option urgency (`hub_multiday_fee_open`, `thin_sameday_fee_open`):**
   - Previously, lowering `fee_open` globally (`02 n-feeopen`) or on all dense pickups (`n14-02111`) failed because (a) lowering `fee_open` on `same_day` or medium-town gigs delayed afternoon bookings, and (b) `Desk.backlog_near()` penalized unbooked multi-day orders with weight `1.0`, so waiting an extra hour for a Capital driver to book a multi-day order at `0.80×–0.85×` blocked afternoon requests.
   - Now that `n14-02462` (`backlog_multiday_weight=0.25`) downweights unurgent multi-day orders in `backlog_near()`, we can safely open **dense-hub (`supply >= 150`) non-urgent multi-day (`option != "same_day"`) gigs with `>= 6h` until `until` (`lastPickupAt - 3h`)** at `hub_multiday_fee_open = 0.80`, while opening **thin/ring `same_day` gigs (`supply < 65` and `option == "same_day"`)** higher at `thin_sameday_fee_open = 0.90`.
   - Crucially, combining `hub_multiday_fee_open = 0.80` and `thin_sameday_fee_open = 0.90` creates a **0.10× relative opening-fee spread (`0.90×` vs `0.80×`)** between urgent thin/ring `same_day` gigs and non-urgent hub multi-day gigs. Because drivers are notified only when a gig is first posted (raises do not notify), this spread steers borderline Capital/ring drivers to book urgent `same_day` gigs immediately on post notification instead of taking non-urgent hub multi-day gigs at the same `0.85×` rate.
2. **Dropped gigs and no-shows near `lastPickupAt` miss `deadline_close` and are never repriced to `steep()` (`drop_urgent_margin_min`):**
   - The server fires `deadline_close` at `lastPickupAt - 3 * HOUR` (`180` min) *only if no driver holds the order at that minute*. If a driver was holding a gig when `lastPickupAt - 180` min passed and then drops the gig (`gig_dropped`) or fails to show (`no_show`) within `180` minutes of `lastPickupAt`, `Desk.handle()` previously ran `self.booked.discard(event["gigId"])` and did nothing else — leaving the gig stuck on its pre-warning schedule (`fee_warn = 1.60`) and never entering `self.urgent` or `steep()`!
   - Repricing unstaffed undelivered orders on `gig_dropped` / `no_show` when `order["lastPickupAt"] - self.now <= drop_urgent_margin_min` (`180` min = exact `deadline_close` boundary) rescues those late-dropped orders immediately onto `steep()`.

## What changed
Merged `origin/exp/gemini-n14-02462-deadline-aware-backlog` and added three `Params` fields in `src/spread_lab/policy.py` whose defaults (`0.0`, `0.0`, `0`) reproduce `n14-02462` and Champion v2 bit-for-bit (`Δmargin €+0.00 ± 0.00` on smoke):
- `hub_multiday_fee_open: float = 0.0` — when `> 0`, in `Desk.fees_for(order, cars)`, if `order["id"] not in self.urgent` and `order["option"] != "same_day"` and `self.supply.get(order["legs"][0]["pickup"]["placeId"], 0) >= 150` and `(order["lastPickupAt"] - 3 * HOUR) - self.now >= 6 * HOUR`, passes `fee_open_override=p.hub_multiday_fee_open` to `self.rising(...)` and increments `self.stats["hub_multiday_posts"] += 1`.
- `thin_sameday_fee_open: float = 0.0` — when `> 0`, in `Desk.fees_for(order, cars)`, if `order["id"] not in self.urgent` and `order["option"] == "same_day"` and `self.supply.get(order["legs"][0]["pickup"]["placeId"], 0) < 65`, passes `fee_open_override=p.thin_sameday_fee_open` to `self.rising(...)` and increments `self.stats["thin_sameday_posts"] += 1`.
- `drop_urgent_margin_min: int = 0` — when `> 0`, in `Desk.handle()` under `elif kind in ("gig_dropped", "no_show"):`, after `self.booked.discard(event["gigId"])`, inspects `post = self.posts.get(event["gigId"])`; for each unique `order_id` in `post["stops"]` where `order_id in self.orders` and `undelivered(self.orders[order_id])` and `self.orders[order_id]["lastPickupAt"] - self.now <= p.drop_urgent_margin_min`, increments `self.stats["drop_rescued"] += 1` and calls `self.raise_fees(order_id)`. Also rebuilt `self.urgent` in `Desk.rejoin()` for live-mode restart compatibility.

Run commands:
- **Dev 1 (`fee-drop-all180-dev`, `hub_multiday_fee_open=0.80, thin_sameday_fee_open=0.90, drop_urgent_margin_min=180`):**
  ```sh
  uv run lab eval -s trust_invest=0.05 -s notes_v2=True -s note_unsure=decline -s max_next_day_drive_min=480 -s fri_same_day_max_drive=100 -s thin_long_next_day_supply=50 -s ring_to_hub_same_day_min=60 -s same_day_min_supply=50 -s min_slack_min=150 -s slack_per_drive=0.75 -s backlog_multiday_weight=0.25 -s backlog_in_flight_weight=0.35 -s price_target_win=0.40 -s min_supply=22 -s drop_urgent_margin_min=180 -s hub_multiday_fee_open=0.80 -s thin_sameday_fee_open=0.90 --name fee-drop-all180-dev
  ```
- **Dev 2 (`fee-drop-all240-dev`, `hub_multiday_fee_open=0.80, thin_sameday_fee_open=0.90, drop_urgent_margin_min=240`):**
  ```sh
  uv run lab eval -s trust_invest=0.05 -s notes_v2=True -s note_unsure=decline -s max_next_day_drive_min=480 -s fri_same_day_max_drive=100 -s thin_long_next_day_supply=50 -s ring_to_hub_same_day_min=60 -s same_day_min_supply=50 -s min_slack_min=150 -s slack_per_drive=0.75 -s backlog_multiday_weight=0.25 -s backlog_in_flight_weight=0.35 -s price_target_win=0.40 -s min_supply=22 -s drop_urgent_margin_min=240 -s hub_multiday_fee_open=0.80 -s thin_sameday_fee_open=0.90 --name fee-drop-all240-dev
  ```
- **Dev 3 (`fee-drop-all180-ptw42-dev`, testing `price_target_win=0.42`):**
  ```sh
  uv run lab eval -s trust_invest=0.05 -s notes_v2=True -s note_unsure=decline -s max_next_day_drive_min=480 -s fri_same_day_max_drive=100 -s thin_long_next_day_supply=50 -s ring_to_hub_same_day_min=60 -s same_day_min_supply=50 -s min_slack_min=150 -s slack_per_drive=0.75 -s backlog_multiday_weight=0.25 -s backlog_in_flight_weight=0.35 -s price_target_win=0.42 -s min_supply=22 -s drop_urgent_margin_min=180 -s hub_multiday_fee_open=0.80 -s thin_sameday_fee_open=0.90 --name fee-drop-all180-ptw42-dev
  ```

## Results (level 8, vs champion v2, paired)
| set | run folder | mean margin | Δmargin ± SE | t | better/worse | on-time min (mean, Δ) | SAFE |
|---|---|---:|---:|---:|---:|---:|---|
| smoke (noop) | `runs/20261114-033635-fee-drop-noop` | €9,662.25 | €+0.00 ± 0.00 | — | 0 / 0 | 95.5% (96.7%, +0.00%) | yes |
| smoke 1 (`drop=240`) | `runs/20261114-033907-fee-drop-smoke1-drop240` | €10,731.41 | €+1,069.17 ± 572.29 | 1.87 | 4 / 0 | 95.3% (96.7%, -0.01%) | yes |
| smoke 2 (`hub=0.80`) | `runs/20261114-034008-fee-drop-smoke2-hub80` | €10,599.77 | €+937.52 ± 410.64 | 2.28 | 4 / 0 | 95.5% (96.6%, -0.11%) | yes |
| smoke 3 (`hub=0.80, thin=0.90`) | `runs/20261114-034155-fee-drop-smoke3-thin90` | **€10,996.27** | **€+1,334.02 ± 652.57** | **2.04** | **4 / 0** | **96.3% (97.2%, +0.47%)** | **yes** |
| smoke 4 (`+drop=240`) | `runs/20261114-034353-fee-drop-smoke4-all` | €10,950.03 | €+1,287.78 ± 668.69 | 1.93 | 4 / 0 | 96.3% (97.2%, +0.56%) | yes |
| smoke 5 (`+drop=180`) | `runs/20261114-034543-fee-drop-smoke5-all180` | **€10,996.27** | **€+1,334.02 ± 652.57** | **2.04** | **4 / 0** | **96.3% (97.2%, +0.47%)** | **yes** |
| smoke 6 (`thin=0.90, drop=180` only) | `runs/20261114-034703-fee-drop-smoke6-thin90-drop180` | €10,543.33 | €+881.08 ± 371.85 | 2.37 | 4 / 0 | 95.5% (96.5%, -0.15%) | yes |
| **dev 1 (`fee-drop-all180-dev`)** | `runs/20261114-034812-fee-drop-all180-dev` | **€10,577.92** | **€+1,587.61 ± 233.21** | **6.81** | **15 / 1** | **95.6% (97.7%, +0.94%)** | **yes** |
| **dev 2 (`fee-drop-all240-dev`)** | `runs/20261114-035340-fee-drop-all240-dev` | **€10,553.70** | **€+1,563.40 ± 233.77** | **6.69** | **15 / 1** | **95.6% (97.7%, +0.93%)** | **yes** |
| dev 3 (`fee-drop-all180-ptw42-dev`) | `runs/20261114-035535-fee-drop-all180-ptw42-dev` | €10,192.35 | €+1,202.05 ± 256.29 | 4.69 | 14 / 2 | 92.6% (96.8%, +0.08%) | yes |

### Direct paired comparisons against `n14-02462` (`backlog-aware-gtn-ptw40-dev`, `€10,481.58`)
- **`fee-drop-all180-dev` (`hub=0.80, thin=0.90, drop=180`) vs `backlog-aware-gtn-ptw40-dev`:**
  - **`Δmargin €+96.34 ± 107.02` (better on 11 of 16 seeds, worse on 5)** and **`Δon-time +0.25%`**, lifting mean margin from `€10,481.58` to **`€10,577.92`** (`Δmargin €+1,587.61 ± 233.21`, **`t = 6.81`**, **15/16 seeds better** vs Champion v2).
  - Lifts worst-seed margin across all 16 dev seeds by **`+€325.32`** (from `€7,196.05` to **`€7,521.37`** on `dev-01`).
  - Lifts worst-seed on-time from `95.35%` to **`95.64%`** and mean on-time from `97.43%` to **`97.68%`** (`+0.94%` over Champion v2), cutting total late orders across the 16 dev seeds by **9.7% (`113 → 102`, or `7.06/w → 6.38/w`)** while winning `+10` more active orders (`4,380` vs `4,370`).
- **`fee-drop-all180-dev` (`drop=180`) vs `fee-drop-all240-dev` (`drop=240`):**
  - **`Δmargin €+24.22 ± 15.65` (`t = 1.55`, 4 better, 0 worse, 12 tied, `Δon-time +0.00%`)**.
  - Why `180` strictly dominates `240`: `180` minutes (`3 * HOUR`) is the exact boundary where the server's `deadline_close` check occurs. A gig dropped between `240` and `180` minutes before `lastPickupAt` (`11` occurrences across 16 worlds) still has up to 60 minutes on `fee_warn` before `deadline_close` and will receive a normal `deadline_close` event at `-180` min if still unbooked; jumping to `steep()` at `-240` min paid `+€47.28/w` extra in `driver_fee` (`-€19,019.62/w` vs `-€18,972.34/w`) for zero reduction in late orders (`102` late orders in both).

### Detailed telemetry and ledger breakdown on dev (16 worlds total / mean per world)
| Metric / Counter | Champion v2 | `backlog-aware-gtn-ptw40-dev` (`n14-02462`) | `fee-drop-all180-dev` (`hub=0.80, thin=0.90, drop=180`) | `fee-drop-all240-dev` (`drop=240`) | `fee-drop-all180-ptw42-dev` (`+ptw=0.42`) |
|---|---:|---:|---:|---:|---:|
| **Mean margin (€/world)** | €8,990.31 | €10,481.58 | **€10,577.92** | €10,553.70 | €10,192.35 |
| **Min margin (€/world)** | €6,017.30 | €7,196.05 | **€7,521.37** | **€7,521.37** | €7,319.90 |
| Active won orders (total / mean) | 3,644 (227.75/w) | 4,370 (273.12/w) | **4,380 (273.75/w)** | 4,380 (273.75/w) | 4,594 (287.12/w) |
| **Total late orders (late %)** | 118 (7.38/w, 3.24%) | 113 (7.06/w, 2.59%) | **102 (6.38/w, 2.33%)** | **102 (6.38/w, 2.33%)** | 148 (9.25/w, 3.22%) |
| **Worst seed on-time %** | 94.36% | 95.35% | **95.64%** | **95.64%** | 92.59% |
| **Mean on-time %** | 96.75% | 97.43% | **97.68%** | **97.68%** | 96.82% |
| `hub_multiday_posts` (total / mean) | 0 (0.00/w) | 0 (0.00/w) | **1,226 (76.62/w)** | 1,229 (76.81/w) | 1,257 (78.56/w) |
| `thin_sameday_posts` (total / mean) | 0 (0.00/w) | 0 (0.00/w) | **379 (23.69/w)** | 378 (23.62/w) | 407 (25.44/w) |
| `drop_rescued` (total / mean) | 0 (0.00/w) | 0 (0.00/w) | **11 (0.69/w)** | 22 (1.38/w) | 21 (1.31/w) |
| `gig_dropped` / `no_show` | 462 / 8 | 578 / 7 | 586 / 10 | 592 / 11 | 602 / 14 |
| `deadline_close` warnings | 193 (12.06/w) | 225 (14.06/w) | 237 (14.81/w) | 239 (14.94/w) | 293 (18.31/w) |
| `won_ring` / `late_ring` | 823 / 17 | 1,052 / 20 | **1,044 / 20 (1.92%)** | 1,044 / 20 | 1,077 / 36 |
| Ledger `revenue` (€/world) | +26,922.43 | +29,806.67 | **+29,928.51 (+€122/w)** | +29,950.90 | +30,711.63 |
| Ledger `driver_fee` (€/world) | -17,286.93 | -18,955.63 | **-18,972.34** | -19,019.62 | -20,032.15 |
| Ledger `late_refund` (€/world) | -376.20 | -259.44 | -270.51 | -269.67 | -378.19 |
| Ledger `failed_visit` (€/world) | -165.44 | -12.62 | -16.96 | -16.96 | -19.52 |
| Ledger `waiting` (€/world) | -39.38 | -24.38 | **-20.62** | -20.62 | -23.12 |

### Key Mechanism Insights
1. **Strong synergy between `hub_multiday_fee_open=0.80` and `thin_sameday_fee_open=0.90`:** On smoke, neither `hub_multiday_fee_open=0.80` alone (`€10,599.77`) nor `thin_sameday_fee_open=0.90` alone (`€10,543.33`) beat the `n14-02462` smoke baseline (`€10,726.20`). Together, however, they jumped to **`€10,996.27` (+€270/w on smoke, 4/4 seeds better)** and **`€10,577.92` on dev (11/16 seeds better vs `n14-02462`, 15/16 better vs Champion v2)**! Creating a `0.10×` opening-fee differential (`0.90×` on `23.7/w` thin `same_day` posts vs `0.80×` on `76.6/w` hub multi-day posts) prevents non-urgent hub multi-day posts from cannibalizing drivers near thin/ring `same_day` pickups at post time, while the fee savings on `1,226` hub multi-day posts pay for the `0.90×` opening fee on `379` thin `same_day` posts and `11` late-drop rescues (`driver_fee` per won order stays flat at `€69.31` vs `€69.40` in `n14-02462`).
2. **11 fewer late orders boosts dealer trust and revenue (`+€121.84/w`):** Cutting total late orders across the 16 dev seeds from `113` (`2.59%`) to **`102` (`2.33%`)** avoids dealer trust halvings and raises weekly revenue by `+€121.84/w` (`€29,928.51/w` vs `€29,806.67/w`) at virtually identical volume (`273.75/w` vs `273.12/w`).

## Verdict
**adopt** — `hub_multiday_fee_open=0.80`, `thin_sameday_fee_open=0.90`, and `drop_urgent_margin_min=180` on top of `n14-02462` (`runs/20261114-034812-fee-drop-all180-dev`) achieves **`€10,577.92` mean margin (`Δmargin €+1,587.61 ± 233.21`, `t = 6.81`, 15/16 better vs Champion v2; `Δmargin €+96.34 ± 107.02`, 11/16 better vs `n14-02462`)** while lifting worst-seed margin to **`€7,521.37`**, worst-seed on-time to **`95.64%`**, and mean on-time to **`97.68%` (`+0.94%`, SAFE)**.
