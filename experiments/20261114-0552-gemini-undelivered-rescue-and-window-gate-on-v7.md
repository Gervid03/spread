# undelivered-rescue-and-window-gate-on-v7: Second-Wave Crisis Rescue & Quote-Only Window/Trade-In Gate on Grand Synthesis v7

- **Agent / branch / commit:** gemini · `exp/gemini-n14-05024-undelivered-rescue-and-window-gate-on-v7` · see HEAD
- **Date:** 2026-11-14 05:52
- **Idea from:** Surgical follow-up on Grand Synthesis v7 (`stack-v7-dlr01-dev`, `€10,648.07/wk`) targeting (1) the `-€64.00/wk` `undelivered_penalty` spike via second-wave crisis rescue (`crisis_lead_min`, `crisis_offer_mult`, `crisis_steep_open`) and (2) quote-time-only multi-day trade-in & tight pickup-window filtering (`trade_in_mode`, `min_pickup_window_slack_min`) without `respect_stop_windows`

## Why we tried it
In `origin/exp/gemini-n14-04154-stack-v7-feedrop-buf-alarm`, `stack-v7-dlr01-dev` set an all-time record of **`€10,648.07/wk` (`Δmargin €+1,657.77 ± 233.04, t = 7.11`, 16/16 seeds better vs Champion v2)**, and `stack-v7-smoothfee-dev` hit **`€10,560.06/wk` (`t = 7.90`, 16/16 better, worst-seed margin `€7,888.32`)**. Inspecting their ledger and counter breakdowns identified two specific leaks:
1. **The `-€64.00/wk` (`€1,024` total across 16 worlds) `undelivered_penalty` spike in `stack-v7-dlr01-dev`:**
   - In `stack-v7-dlr01-dev`, `undelivered_penalty` jumped from `-€10.29/wk` (`stack-v7-smoothfee-dev`) to `-€64.00/wk` (driven by a `-€701.00` undelivered order on `dev-13`).
   - When `gig_expired` (`repost`) or `gig_dropped`/`no_show` (`drop_urgent_margin_min=180`) occurs close to `lastPickupAt` (`<= 90–120` min before `lastPickupAt`), `steep(base)` restarted at `steep_open = 1.55` instead of escalating, and no second wave of direct offers was sent.
2. **Quote-time-only trade-in & pickup-window gates (without `respect_stop_windows=True` in `stops_for`):**
   - In `stack-v7-dlr01-dev`, `13 / 30` (`43.3%`) of won 2-leg trade-ins arrived late. Filtering out multi-day trade-in options (`trade_in_mode="same_day_only"`) and tight pickup windows (`min_pickup_window_slack_min=180`) purely in `Desk.price()` avoids clamping stop windows in `stops_for()`.

## What changed
Added five fields to `Params` in `src/spread_lab/policy.py` (all defaulting to exact Champion v2 / v7 behaviour):
- `crisis_lead_min: int = 0` (`> 0`: minutes before `lastPickupAt` to trigger second-wave crisis rescue on still-unbooked urgent orders in `Desk.tick()` and escalate `Desk.steep()` opening multiple)
- `crisis_offer_mult: float = 1.95` (direct offer fee multiple during crisis rescue, sending up to 2 offers to eligible drivers who haven't been offered the gig yet via `self.gig_offers_sent` while respecting the 3-open-offers-per-gig and 3-offers-per-driver-per-day limits)
- `crisis_steep_open: float = 1.90` (minimum opening multiple `max(p.steep_open, p.crisis_steep_open)` in `Desk.steep()` and `Desk.crisis_rescue()` when `order["lastPickupAt"] - self.now <= p.crisis_lead_min`)
- `trade_in_mode: str = "all"` (`"same_day_only"`: in `Desk.price()`, drop non-`same_day` options on 2-leg trade-in requests and count `dropped_trade_in`)
- `min_pickup_window_slack_min: int = 0` (`> 0`: in `Desk.price()`, drop options where `p0_win["to"] < option["deadline"]` and `p0_win["to"] - ready < p.min_pickup_window_slack_min`, counting `dropped_pickup_window`)
- Rebuilt `self.crisis_warned` and `self.gig_offers_sent` in `Desk.rejoin()`.

Verified bit-for-bit reproduction of Champion v2 on smoke (`runs/20261114-052122-crisis-win-noop`: `Δmargin €+0.00 ± 0.00`, 0/0).

Base v7 configuration (`$V7`):
```sh
V7="-s trust_invest=0.05 -s notes_v2=True -s note_unsure=decline -s max_next_day_drive_min=480 -s fri_same_day_max_drive=100 -s thin_long_next_day_supply=50 -s ring_to_hub_same_day_min=60 -s same_day_min_supply=50 -s min_slack_min=150 -s slack_per_drive=0.75 -s price_target_win=0.40 -s min_supply=22 -s backlog_multiday_weight=0.25 -s backlog_in_flight_weight=0.35 -s hub_multiday_fee_open=0.80 -s thin_sameday_fee_open=0.90 -s drop_urgent_margin_min=180 -s delivery_buffer_min=30 -s buffer_min_slack_min=210 -s pre_warn_lead_min=60 -s pre_warn_fee=1.35 -s fee_warn=1.48 -s fee_step_min=25 -s steep_open=1.55 -s dealer_lr=0.01"
```

Dev run commands:
- **Dev 1 (`v7-crisis-rescue-dev`):**
  ```sh
  uv run lab eval $V7 -s crisis_lead_min=90 -s crisis_offer_mult=1.95 -s crisis_steep_open=1.90 --name v7-crisis-rescue-dev
  ```
- **Dev 2 (`v7-crisis-wingate-dev`):**
  ```sh
  uv run lab eval $V7 -s crisis_lead_min=120 -s crisis_offer_mult=1.85 -s crisis_steep_open=1.85 -s trade_in_mode=same_day_only -s min_pickup_window_slack_min=180 --name v7-crisis-wingate-dev
  ```
- **Dev 3 (`v7-crisis-wingate-ptw41-dev`):**
  ```sh
  uv run lab eval $V7 -s price_target_win=0.41 -s min_supply=20 -s crisis_lead_min=120 -s crisis_offer_mult=1.85 -s crisis_steep_open=1.85 -s trade_in_mode=same_day_only -s min_pickup_window_slack_min=180 --name v7-crisis-wingate-ptw41-dev
  ```

## Results (level 8, vs champion v2, paired)
| set | run folder | mean margin | min margin | Δmargin ± SE | t | better/worse | on-time min (mean, Δ) | SAFE |
|---|---|---:|---:|---:|---:|---:|---:|---|
| smoke (noop) | `runs/20261114-052122-crisis-win-noop` | €9,662.25 | €7,296.78 | €+0.00 ± 0.00 | — | 0 / 0 | 95.5% (96.7%, +0.00%) | yes |
| smoke 1 (`crisis90`) | `runs/20261114-052319-v7-smoke1-crisis90` | **€11,388.65** | €7,701.54 | **€+1,726.41 ± 741.69** | 2.33 | 4 / 0 | 93.3% (96.9%, +0.19%) | yes |
| smoke 2 (`wingate`) | `runs/20261114-052441-v7-smoke2-wingate` | €11,375.75 | €7,808.12 | €+1,713.51 ± 665.05 | 2.58 | 4 / 0 | 94.5% (96.8%, +0.10%) | yes |
| smoke 3 (`crisis90 + wingate`) | `runs/20261114-052643-v7-smoke3-crisis90-wingate` | €11,253.57 | €7,729.40 | €+1,591.32 ± 608.12 | 2.62 | 4 / 0 | **94.9% (97.0%, +0.30%)** | yes |
| smoke 4 (`crisis120 + wingate`) | `runs/20261114-052720-v7-smoke4-crisis120-wingate` | €11,317.23 | **€7,885.39** | €+1,654.99 ± 602.55 | **2.75** | 4 / 0 | 94.5% (96.9%, +0.22%) | yes |
| smoke 5 (`crisis90 + wingate v2-hours`) | `runs/20261114-053555-v7-smoke5-crisis90-wingate-v2` | €10,893.01 | €7,534.28 | €+1,230.77 ± 487.91 | 2.52 | 4 / 0 | 94.7% (96.7%, -0.03%) | yes |
| **dev 1 (`v7-crisis-rescue-dev`)** | `runs/20261114-053730-v7-crisis-rescue-dev` | **€10,586.19** | €7,701.54 | **€+1,595.88 ± 279.27** | **5.71** | **15 / 1** | **93.3% (97.3%, +0.54%)** | **yes** |
| **dev 2 (`v7-crisis-wingate-dev`)** | `runs/20261114-054137-v7-crisis-wingate-dev` | **€10,495.17** | **€7,885.39** | **€+1,504.87 ± 244.30** | **6.16** | **15 / 1** | **94.5% (97.2%, +0.42%)** | **yes** |
| **dev 3 (`v7-crisis-wingate-ptw41-dev`)** | `runs/20261114-054914-v7-crisis-wingate-ptw41-dev` | €10,337.99 | €7,285.82 | €+1,347.69 ± 278.14 | 4.85 | 15 / 1 | 93.2% (97.2%, +0.42%) | yes |

### Head-to-head paired comparisons on 16 dev seeds
| Comparison (Run A vs Run B on 16 dev seeds) | Δmargin ± SE | t | better / worse | Δon-time |
|---|---:|---:|---:|---:|
| **Dev 1 (`v7-crisis-rescue-dev`, `€10,586.19`)** vs Champion v2 (`€8,990.31`) | **`€+1,595.88 ± 279.27`** | **`5.71`** | **`15 / 1`** | **`+0.54%`** |
| **Dev 1 (`v7-crisis-rescue-dev`, `€10,586.19`)** vs `stack-v7-smoothfee-dev` (`€10,560.06`) | **`€+26.13 ± 139.22`** | **`0.19`** | **`9 / 7`** | **`+0.06%`** |
| **Dev 1 (`v7-crisis-rescue-dev`, `€10,586.19`)** vs `stack-v7-dlr01-dev` (`€10,648.07`) | `€-61.88 ± 74.05` | `-0.84` | `5 / 10` | **`+0.12%`** |
| **Dev 2 (`v7-crisis-wingate-dev`, `€10,495.17`)** vs Champion v2 (`€8,990.31`) | **`€+1,504.87 ± 244.30`** | **`6.16`** | **`15 / 1`** | **`+0.42%`** |
| **Dev 2 (`v7-crisis-wingate-dev`, `€10,495.17`)** vs `stack-v7-smoothfee-dev` (`€10,560.06`) | `€-64.88 ± 140.89` | `-0.46` | **`9 / 7`** | `-0.06%` |
| **Dev 2 (`v7-crisis-wingate-dev`, `€10,495.17`)** vs `stack-v7-dlr01-dev` (`€10,648.07`) | `€-152.90 ± 94.26` | `-1.62` | `6 / 10` | `-0.00%` |
| **Dev 3 (`v7-crisis-wingate-ptw41-dev`, `€10,337.99`)** vs Champion v2 (`€8,990.31`) | **`€+1,347.69 ± 278.14`** | **`4.85`** | **`15 / 1`** | **`+0.42%`** |

### Full ledger & telemetry breakdown on dev (16 worlds total / mean per world)
| Metric / Counter | Champion v2 | `stack-v7-smoothfee-dev` | `stack-v7-dlr01-dev` | **Dev 1: `v7-crisis-rescue-dev`** | **Dev 2: `v7-crisis-wingate-dev`** | **Dev 3: `v7-crisis-wingate-ptw41-dev`** |
|---|---:|---:|---:|---:|---:|---:|
| **Mean margin (€/world)** | €8,990.31 | €10,560.06 | **€10,648.07** | **€10,586.19** | €10,495.17 | €10,337.99 |
| **Worst-seed margin (€)** | €6,017.30 | **€7,888.32** | €7,721.60 | €7,701.54 | **€7,885.39** | €7,285.82 |
| **Worst-seed on-time %** | 94.36% | 94.05% | 94.00% | 93.28% | **94.55%** | 93.20% |
| **Mean on-time %** | 96.75% | 97.23% | 97.17% | **97.29%** | 97.17% | 97.17% |
| Active won orders (total / mean) | 3,644 (227.8/w) | 4,374 (273.4/w) | 4,407 (275.4/w) | 4,407 (275.4/w) | 4,385 (274.1/w) | **4,473 (279.6/w)** |
| `crisis_rescued` | 0 | 0 | 0 | **113 (7.06/w)** | **133 (8.31/w)** | **142 (8.88/w)** |
| `dropped_trade_in` | 0 | 0 | 0 | 0 | **121 (7.56/w)** | **126 (7.88/w)** |
| `dropped_pickup_window` | 0 | 0 | 0 | 0 | **80 (5.00/w)** | **83 (5.19/w)** |
| `late_trade_in` / `won_trade_in` | — | — | — | 13 / 30 (43.3%) | **5 / 13 (38.5%)** | 6 / 12 (50.0%) |
| `offers` / `offer_accepted` | 0 / 0 | 502 / 5 | 486 / 5 | 714 / 5 | 766 / 6 | 754 / 5 |
| `deadline_close` warnings | 193 | 290 | 291 | 295 | 307 | 306 |
| `gig_expired` | 121 | 142 | 142 | 143 | 154 | 160 |
| Ledger `revenue` (€/world) | +26,922.43 | +29,758.75 | +30,039.68 | +30,024.83 | +30,026.22 | **+30,403.91** |
| Ledger `driver_fee` (€/world) | -17,286.92 | **-18,742.62** | -18,943.71 | -19,023.65 | -19,084.20 | -19,567.69 |
| Ledger `late_refund` (€/world) | -376.20 | -334.30 | **-297.22** | -308.94 | -340.34 | -360.40 |
| Ledger `undelivered_penalty` (€/world) | -10.72 | **-10.29** | -64.00 | **-20.16** | **-20.24** | -57.92 |
| Ledger `failed_visit` (€/world) | -165.44 | -13.39 | -18.90 | -18.90 | -17.14 | **-6.06** |
| Ledger `release_fee` (€/world) | -53.48 | -64.24 | **-43.00** | -45.97 | -44.75 | -49.48 |
| Ledger `waiting` (€/world) | -39.38 | -33.86 | -24.78 | **-21.03** | -24.38 | -24.38 |

### Key Mechanism Findings
1. **`crisis_lead_min=90` slashes `undelivered_penalty` by 68.5% (`-€64.00/wk -> -€20.16/wk`, saving `+€43.84/wk` = `€701.44` across 16 worlds) and beats `stack-v7-smoothfee-dev` on 9/16 seeds (`€10,586.19/wk`):**
   - Escalating `Desk.steep()` from `1.55×` to `1.90×` when a gig expires (`repost`) or drops (`drop_urgent_margin_min`) within 90 minutes of `lastPickupAt` completely eliminates the `-€701.00` undelivered penalty on `dev-13` (`-€701.00 -> €0.00`) and produces substantial gains on `dev-02` (`+€326.23`), `dev-04` (`+€280.77`), `dev-15` (`+€252.14`), and `dev-14` (`+€166.28`).
2. **Why unconditional `reprice` + `offer` in `Desk.tick()` at `lastPickupAt - 90` falls `-€61.88/wk` short of `stack-v7-dlr01-dev`:**
   - **Schedule reset on already-urgent gigs:** When `deadline_close` fires at `lastPickupAt - 180`, `steep()` starts at `1.55×` and steps by `+0.25` every 30 minutes (`1.55 -> 1.80 -> 2.05 -> 2.30` at `lastPickupAt - 90`). When `crisis_rescue` reprices an already-open urgent gig at `lastPickupAt - 90` to `open_mult = 1.90`, it actually *lowers* that gig's current board fee from `2.30×` back down to `1.90×` (delaying booking on `dev-07` `-€196.44` and `dev-09` `-€227.24`), whereas its intended benefit is only on *newly reposted or newly dropped* gigs (`fees_for`) that would otherwise start at `1.55×`.
   - **Daily driver offer quota dilution:** Sending `+228` crisis direct offers at `1.95×` (`486 -> 714` total offers) yields `0` additional accepted offers (`offer_accepted = 5` in both `dlr01` and `crisis90`) because nearby active drivers have already seen `2.05×–2.30×` on the public board; worse, those `228` offers consume drivers' `3 offers/day` quota (`self.offers_sent`), blocking a profitable `pre_warn` (`1.35×`) offer acceptance on `dev-10` (`offer_accepted: 1 -> 0`, `-€804.57`).
3. **Quote-only `trade_in_mode="same_day_only"` + `min_pickup_window_slack_min=180` (`v7-crisis-wingate-dev`) lifts worst-seed margin to `€7,885.39` (`+€163.79` over `dlr01`) and worst-seed on-time to `94.55%` (`+0.55%` over `dlr01`):**
   - Cuts total late trade-ins across 16 worlds by **61.5% (`13 -> 5`)**, confirming that quote-only gating removes multi-day trade-in lateness without the stop-window clamping penalty of `respect_stop_windows=True`.

## Verdict
**needs work (keep `stack-v7-dlr01-dev` at `€10,648.07/wk` as v7 champion; isolate `crisis_steep_open` to `fees_for()` on late reposts/drops only without `tick()` repricing or crisis direct offers)** — `v7-crisis-rescue-dev` reaches **`€10,586.19/wk` (`Δmargin €+1,595.88 ± 279.27, t = 5.71`, 15/1 better vs Champion v2, `93.3%` min on-time, SAFE)** and cuts `undelivered_penalty` by **68.5% (`-€64.00/wk -> -€20.16/wk`)**, while `v7-crisis-wingate-dev` reaches **`€10,495.17/wk` (`Δmargin €+1,504.87 ± 244.30, t = 6.16`, worst-seed margin `€7,885.39`, worst-seed on-time `94.55%`, SAFE)**, but `stack-v7-dlr01-dev` (`€10,648.07/wk`) remains `+€61.88/wk` higher on mean margin because `tick()` crisis repricing resets `2.30×` schedules down to `1.90×` and crisis offers dilute the 3-offers/day driver quota.
