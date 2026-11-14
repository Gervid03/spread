# n14-04152-drop-repost-and-trust-cap: Fresh-notification repost on late `gig_dropped`/`no_show` and dynamic high-trust dealer cap on `n14-03324`

- **Agent / branch / commit:** gemini · `exp/gemini-n14-04152-drop-repost-and-trust-cap` · `HEAD`
- **Date:** 2026-11-14 04:35
- **Idea from:** Diagnostic extension of `n14-03324` (`fee-drop-all180-dev`), stacked on `origin/exp/gemini-n14-03324-supply-adaptive-fee-open-and-drop-rescue`

## Why we tried it
In `n14-03324` (`fee-drop-all180-dev`, mean margin **`€10,577.92/wk`**), `586` gigs are dropped (`36.62/wk`) and `10` have `no_show` (`0.62/wk`) across the 16 dev worlds. When a drop occurs within `drop_urgent_margin_min=180` minutes of `lastPickupAt`, `n14-03324` calls `self.raise_fees(order_id)`, which sends `{"type": "reprice", ...}`. We tested two structural extensions on top of `n14-03324`:
1. **Fresh-notification repost on late `gig_dropped` / `no_show` (`drop_repost_margin_min`):**
   - Per `docs/GAME.md`, *"Drivers are notified of gigs whose first pickup is within 30 km (straight line) of their home; no notifications 23:00–07:00; a raise doesn't notify."* Because `reprice` modifies an existing gig without sending a push notification, only drivers actively polling the board see the urgent `steep()` schedule. Withdrawing the dropped 1-leg gig during daytime (`07:00–22:00`) and posting a brand-new gig (`{"type": "post", ...}`) sends a fresh push notification to every driver within 30 km.
2. **Dynamic high-trust dealer cap (`trust_cap_boost` + `dealer_lr=0.01`):**
   - Top dealer `D01` accounts for ~31% of quotes and reaches `dealer_trust = 25` (`+25%` price bonus) by Wednesday/Thursday (`top_dealer_trust_d4 = 24.38/wk` on `n14-03324`). Allowing the upper clamp on `self.dealer_adj[dealer]` in `Desk.learn()` to scale with trust (`p.dealer_adj_max + p.trust_cap_boost * (self.dealer_trust[dealer] / 25.0)`) and testing slower per-dealer step size (`dealer_lr=0.01`) aims to capture more margin on `D01` without inflating global `self.mult`.

## What changed
Merged `origin/exp/gemini-n14-03324-supply-adaptive-fee-open-and-drop-rescue` and added two `Params` fields in `src/spread_lab/policy.py` whose defaults (`0`, `0.0`) reproduce Champion v2 and `n14-03324` bit-for-bit (`Δmargin €+0.00 ± 0.00` on smoke):
- `drop_repost_margin_min: int = 0` — when `> 0`, in `Desk.handle()` under `elif kind in ("gig_dropped", "no_show"):`, after `self.booked.discard(event["gigId"])` and marking `self.urgent.add(order_id)` if `rem <= p.drop_urgent_margin_min`, for each affected 1-leg `order_id` (`len(order["legs"]) == 1`, `order_id in self.orders`, `undelivered(order)`), if `order["lastPickupAt"] - self.now <= p.drop_repost_margin_min` and `7 * 60 <= self.now % DAY < 22 * 60` and `self.withdraw(order_id)` succeeds, calls `self.post(order, undelivered(order))` (and sends direct offers if `order_id in self.urgent and p.offers_per_warning > 0`) and increments `self.stats["drop_reposted"] += 1`. Falls back to `self.raise_fees(order_id)` when `is_urgent_drop and not reposted`.
- `trust_cap_boost: float = 0.0` — in `Desk.learn()`, sets the upper clamp on `self.dealer_adj[dealer]` to `p.dealer_adj_max + p.trust_cap_boost * (self.dealer_trust[dealer] / 25.0)` and increments `self.stats["trust_cap_boosted"] += 1` whenever `self.dealer_adj[dealer] > p.dealer_adj_max`.

Run commands:
- **Dev 1 (`feedrop-repost-dev`, `drop_repost_margin_min=180` on `n14-03324`):**
  ```sh
  uv run lab eval -s trust_invest=0.05 -s notes_v2=True -s note_unsure=decline -s max_next_day_drive_min=480 -s fri_same_day_max_drive=100 -s thin_long_next_day_supply=50 -s ring_to_hub_same_day_min=60 -s same_day_min_supply=50 -s min_slack_min=150 -s slack_per_drive=0.75 -s backlog_multiday_weight=0.25 -s backlog_in_flight_weight=0.35 -s price_target_win=0.40 -s min_supply=22 -s drop_urgent_margin_min=180 -s hub_multiday_fee_open=0.80 -s thin_sameday_fee_open=0.90 -s drop_repost_margin_min=180 --name feedrop-repost-dev
  ```
- **Dev 2 (`feedrop-repost-trustcap-dev`, `drop_repost_margin_min=180, trust_cap_boost=0.20, dealer_lr=0.01` on `n14-03324`):**
  ```sh
  uv run lab eval -s trust_invest=0.05 -s notes_v2=True -s note_unsure=decline -s max_next_day_drive_min=480 -s fri_same_day_max_drive=100 -s thin_long_next_day_supply=50 -s ring_to_hub_same_day_min=60 -s same_day_min_supply=50 -s min_slack_min=150 -s slack_per_drive=0.75 -s backlog_multiday_weight=0.25 -s backlog_in_flight_weight=0.35 -s price_target_win=0.40 -s min_supply=22 -s drop_urgent_margin_min=180 -s hub_multiday_fee_open=0.80 -s thin_sameday_fee_open=0.90 -s drop_repost_margin_min=180 -s trust_cap_boost=0.20 -s dealer_lr=0.01 --name feedrop-repost-trustcap-dev
  ```

## Results (level 8, vs champion v2, paired)
| set | run folder | mean margin | Δmargin ± SE | t | better/worse | on-time min (mean, Δ) | SAFE |
|---|---|---:|---:|---:|---:|---:|---|
| smoke (noop) | `runs/20261114-041926-drop-repost-noop` | €9,662.25 | €+0.00 ± 0.00 | — | 0 / 0 | 95.5% (96.7%, +0.00%) | yes |
| smoke 1 (`repost=180`) | `runs/20261114-042049-drop-repost-smoke1-180` | €10,887.17 | €+1,224.92 ± 503.80 | 2.43 | 4 / 0 | 95.9% (97.2%, +0.48%) | yes |
| smoke 2 (`repost=300`) | `runs/20261114-042159-drop-repost-smoke2-300` | €10,755.19 | €+1,092.94 ± 491.81 | 2.22 | 4 / 0 | 95.5% (97.2%, +0.47%) | yes |
| smoke 3 (`trustcap=0.20, lr=0.01`) | `runs/20261114-042232-drop-repost-smoke3-trustcap` | €10,828.83 | €+1,166.59 ± 561.57 | 2.08 | 3 / 1 | 94.8% (96.1%, -0.61%) | yes |
| smoke 4 (`repost=180 + trustcap=0.20, lr=0.01`) | `runs/20261114-042324-drop-repost-smoke4-comb` | €10,902.31 | €+1,240.06 ± 590.82 | 2.10 | 4 / 0 | 95.3% (96.3%, -0.38%) | yes |
| smoke 5 (`repost=180 + trustcap=0.20, lr=0.02`) | `runs/20261114-042441-drop-repost-smoke5-trustcap-lr02` | **€10,915.17** | **€+1,252.92 ± 485.28** | **2.58** | **4 / 0** | **95.9% (97.2%, +0.48%)** | **yes** |
| **dev 1 (`feedrop-repost-dev`)** | `runs/20261114-042932-feedrop-repost-dev` | **€10,518.92** | **€+1,528.62 ± 238.56** | **6.41** | **15 / 1** | **95.6% (97.7%, +0.92%)** | **yes** |
| **dev 2 (`feedrop-repost-trustcap-dev`)** | `runs/20261114-043150-feedrop-repost-trustcap-dev` | €10,390.39 | €+1,400.08 ± 210.89 | 6.64 | 15 / 1 | 94.9% (97.0%, +0.22%) | yes |

### Direct paired comparisons against `n14-03324` (`runs/20261114-034812-fee-drop-all180-dev`, `€10,577.92`)
- **`feedrop-repost-dev` (`drop_repost_margin_min=180`) vs `fee-drop-all180-dev` (`drop_repost_margin_min=0`):**
  - **`Δmargin €-59.00 ± 62.48` (`t = -0.94`, better on 2 seeds, worse on 3 seeds, tied on 11 seeds, `Δon-time -0.02%`)**.
  - On the positive side, `drop_repost_margin_min=180` lifts the **worst-seed margin across all 16 dev seeds by `+€136.06`** (from `€7,521.37` to **`€7,657.43`** on `dev-01`, while lifting `dev-01` on-time from `96.92%` to **`97.32%`**) and gains **`+€441.50`** on `dev-08` (`€14,799.64 → €15,241.14`).
  - On the negative side, it loses `-€572.47` on `dev-02`, `-€449.90` on `dev-06`, and `-€499.16` on `dev-13` (and is bit-for-bit identical on the remaining 11 seeds, including 4 seeds where a drop was reposted with zero downstream change: `dev-04`, `dev-07`, `dev-10`, `dev-12`).
- **`feedrop-repost-trustcap-dev` (`drop_repost_margin_min=180, trust_cap_boost=0.20, dealer_lr=0.01`) vs `fee-drop-all180-dev`:**
  - **`Δmargin €-187.53 ± 96.51` (`t = -1.94`, better on 3 seeds, worse on 13 seeds, `Δon-time -0.71%`)**.
  - Lifts worst-seed margin to **`€7,761.92`** (`+€240.55` above `n14-03324`) and median margin to **`€9,989.74`** (`+€110.76` above `n14-03324`), but lowers mean margin by `-€187.53/w` and mean on-time by `-0.71%` (`97.68% → 96.97%`, increasing total late orders from `102` to `133`).

### Detailed telemetry and ledger breakdown on dev (16 worlds total / mean per world)
| Metric / Counter | Champion v2 | `fee-drop-all180-dev` (`n14-03324` base) | `feedrop-repost-dev` (`+drop_repost=180`) | `feedrop-repost-trustcap-dev` (`+repost=180, tc=0.20, lr=0.01`) |
|---|---:|---:|---:|---:|
| **Mean margin (€/world)** | €8,990.31 | **€10,577.92** | €10,518.92 | €10,390.39 |
| **Median margin (€/world)** | €8,685.06 | €9,878.98 | €9,826.17 | **€9,989.74** |
| **Min margin (€/world)** | €6,017.30 | €7,521.37 | €7,657.43 | **€7,761.92** |
| Active won orders (total / mean) | 3,644 (227.75/w) | 4,380 (273.75/w) | 4,382 (273.88/w) | 4,389 (274.31/w) |
| **Total late orders (late %)** | 118 (7.38/w, 3.24%) | **102 (6.38/w, 2.33%)** | 103 (6.44/w, 2.35%) | 133 (8.31/w, 3.03%) |
| **Worst seed on-time %** | 94.36% | **95.64%** | **95.64%** | 94.92% |
| **Mean on-time %** | 96.75% | **97.68%** | 97.66% | 96.97% |
| `drop_rescued` (total / mean) | 0 (0.00/w) | 11 (0.69/w) | 12 (0.75/w) | 11 (0.69/w) |
| `drop_reposted` (total / mean) | 0 (0.00/w) | 0 (0.00/w) | **12 (0.75/w)** | **10 (0.62/w)** |
| `trust_cap_boosted` (total / mean) | 0 (0.00/w) | 0 (0.00/w) | 0 (0.00/w) | 0 (0.00/w) *(54 / 13.50/w on smoke5 with `lr=0.02`)* |
| `top_dealer_trust_d4` (mean) | 24.12 | 24.38 | 24.31 | **24.44** |
| `gig_dropped` / `no_show` | 462 / 8 | 586 / 10 | 587 / 10 | 581 / 7 |
| `deadline_close` warnings | 193 (12.06/w) | **237 (14.81/w)** | 245 (15.31/w) | 268 (16.75/w) |
| `hub_multiday_posts` / `thin_sameday_posts` | 0 / 0 | 1,226 / 379 | 1,227 / 384 | 1,202 / 384 |
| `posts` / `booked` (total) | 3,795 / 4,218 | 4,496 / 5,018 | 4,512 / 5,022 | 4,522 / 5,018 |
| `won_ring` / `late_ring` | 823 / 17 | **1,044 / 20** | 1,047 / 20 | 1,054 / 25 |
| Ledger `revenue` (€/world) | +26,922.43 | **+29,928.51** | +29,898.74 | +29,871.28 |
| Ledger `driver_fee` (€/world) | -17,286.93 | **-18,972.34** | -18,997.49 | -19,078.32 |
| Ledger `late_refund` (€/world) | -376.20 | **-270.51** | -270.91 | -292.62 |
| Ledger `failed_visit` (€/world) | -165.44 | **-16.96** | -18.83 | -30.32 |
| Ledger `release_fee` (€/world) | -53.48 | -54.48 | -54.42 | **-43.19** |
| Ledger `undelivered_penalty` (€/world) | -10.72 | -15.68 | -15.68 | -15.82 |
| Ledger `waiting` (€/world) | -39.38 | **-20.62** | -22.50 | **-20.62** |

### Key Mechanism Insights (Why `reprice` beats `withdraw + post` on drops, and why `dealer_lr=0.01` blocks `trust_cap_boost`)
1. **Why `reprice` (`n14-03324`) beats `withdraw + post` (`drop_repost_margin_min=180`) on average (`+€59.00 ± 62.48`):**
   - When an urgent drop (`rem <= 180` min) is withdrawn and reposted as a brand-new gig (`{"type": "post", ...}`) starting at `steep_open = 1.80×`, every driver within 30 km receives a push notification at `1.80×`. While this rescues a car on `dev-01` (`+€136.06`, lifting min margin to `€7,657.43`) and `dev-08` (`+€441.50`), on `dev-02` (`-€572.47`), `dev-06` (`-€449.90`), and `dev-13` (`-€499.16`) the `1.80×` push notification **cannibalizes a nearby driver** who otherwise would have booked an adjacent gig rising on its normal `1.00×–1.30×` schedule (`deadline_close` warnings rise from `237` to `245`, and `driver_fee` rises by `+€25.15/w`).
   - Furthermore, on Smoke 2 (`drop_repost_margin_min=300`), reposting non-urgent drops (`180 < rem <= 300` min) calls `self.rising(base, until)` starting at `self.now`, which **resets the gig's opening fee back down to `fee_open = 0.85×`** (`0.80×–0.90×`) even though the dropped gig had already climbed to `~1.35×–1.50×`. Because *"a dropper rebooks only for more"*, resetting to `fee_open` increased `gig_dropped` from `157` to `172` on smoke and cost `-€131.98/w` vs `drop_repost_margin_min=180`.
2. **Why `dealer_lr=0.01` makes `trust_cap_boost=0.20` a complete no-op (`trust_cap_boosted = 0`):**
   - Reaching `dealer_adj = 1.30` from `1.00` requires cumulative log-steps of `ln(1.30) = 0.2624`. At `price_target_win = 0.40`, each win adds `+0.60 * dealer_lr` and each loss subtracts `-0.40 * dealer_lr`. With `dealer_lr = 0.01`, reaching `1.30` requires `+26.24` net excess wins above the 40% target (a `>66%` win rate over 100 quotes), which never happens on any of the 16 dev seeds (`trust_cap_boosted = 0`). Instead, halving `dealer_lr` from `0.02` to `0.01` slows per-dealer price adaptation on high-trust dealers, causing mid-week over-winning and congestion (`133` late orders vs `102`, `deadline_close` `268` vs `237`, `-€187.53/w` vs `n14-03324`). By contrast, keeping `dealer_lr = 0.02` (Smoke 5) triggered `trust_cap_boosted = 54` (`13.5/w`) and reached `€10,915.17` on smoke.

## Verdict
**reject against `n14-03324` (`fee-drop-all180-dev` stays #1 at `€10,577.92`)** — While `feedrop-repost-dev` (`drop_repost_margin_min=180`) is SAFE, strongly beats Champion v2 (`€10,518.92`, `Δmargin €+1,528.62 ± 238.56, t = 6.41`, 15/16 better), and lifts worst-seed margin to **`€7,657.43`** (`+€136.06` over `n14-03324`), it trails `n14-03324`'s `reprice`-only drop rescue by `€-59.00 ± 62.48` (`t = -0.94`) on the full 16-seed dev set because `1.80×` push notifications cannibalize drivers from adjacent normal-schedule gigs.
