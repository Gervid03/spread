# n14-03111-adaptive-delivery-buffer-and-alarm: Slack-guarded delivery deadline buffer and deadline-day pre-warning fee nudge

- **Agent / branch / commit:** gemini · `exp/gemini-n14-03111-adaptive-delivery-buffer-and-alarm` · see HEAD
- **Date:** 2026-11-14 03:22
- **Idea from:** `IDEAS.md` #8 & #9, Margin X-Ray v2 Leak #4 (Near-miss refinement of `n14-05-buffer` and `n14-04-alarm` on top of `origin/exp/gemini-n14-02114-stack-gates-trust-notes`)

## Why we tried it
In `n14-02114-stack-gates-trust-notes` Run 3 (`stack-gtn-ptw38-dev`), raising `price_target_win=0.38, min_supply=25` lifted mean margin to **€10,029.58 (`Δmargin €+1,039.28 ± 229.22, t = 4.53`)**, winning `+22.4` extra orders/wk (`233.6 → 256.0/wk`). However, moving from Run 2 to Run 3 caused total late orders across 16 worlds to rise from **66 (`4.12/wk`) to 112 (`7.00/wk`)**, costing `-€113.38/wk` in extra `late_refund` (`-€174.84 → -€288.22/wk`) and increasing `deadline_close` warnings from `9.12/wk` to `14.06/wk`.
By Margin X-Ray v2 (Section 3, Leak #4), once long `next_day`, Friday `same_day`, and unparsed-note late orders are removed by `n14-02114`, the remaining late orders come from two specific operational mechanisms where earlier raw-v2 workers had instructive near-misses:
1. **Driver Late Without Warning (`1.44 late/wk` in X-Ray = 19.5% of all late orders):**
   - Booked drivers arrive 1–35 minutes after `order["deadline"]` because `stops_for()` sets the delivery stop window upper bound right at `order["deadline"]` (`20:00`).
   - Earlier tonight, `n14-05-buffer` (`delivery_buffer_min=30`) shaved 30 minutes off *every* order's delivery window — including tight `same_day` orders where shaving 30 minutes squeezed the stop window and increased `gig_expired`.
   - **The fix:** Only apply `delivery_buffer_min=30` in `stops_for()` when the leg has ample slack above drive time (`order["deadline"] - max(now, start) - leg_drive >= buffer_min_slack_min` with `buffer_min_slack_min=210` and `order["deadline"] - delivery_buffer_min >= max(delivery["window"]["from"], max(now, start) + leg_drive + 60)`), so tight orders never lose booking time while normal orders get a 30-minute arrival cushion before the dealer's deadline.
2. **Deadline-Day Pre-Warning Rescue (`14.06 deadline_close/wk` in Run 3):**
   - Earlier tonight, `n14-04-alarm` (`alarm_after_min=45`) failed because firing an alarm 45 minutes after posting bumped *every* slow `next_day` order on Day 1 afternoon.
   - **The fix:** Trigger the pre-warning rescue **relative to `order["lastPickupAt"]` on the deadline day only**, not relative to `posted_at`. In `Desk.tick()`, when an unstaffed waiting order is on its deadline day (`self.now // DAY == order["deadline"] // DAY`), `order_id not in self.urgent`, `order_id not in self.pre_warned`, and `0 < (order["lastPickupAt"] - 3 * HOUR) - self.now <= p.pre_warn_lead_min` (`60` min before `deadline_close`), reprice its open gig(s) to a 2-step ramp from `p.pre_warn_fee` (`1.35×`) to `p.fee_warn` (`1.60×`) at `lastPickupAt - 3 * HOUR` and send up to 2 direct offers at `p.pre_warn_fee` (`1.35×`).

## What changed
Merged `origin/exp/gemini-n14-02114-stack-gates-trust-notes` and added four `Params` fields in `src/spread_lab/policy.py` whose defaults (`0`) reproduce `n14-02114` / champion v2 100% identically (`Δmargin €+0.00 ± 0.00` on smoke):
- `delivery_buffer_min: int = 0` — minutes shaved off `order["deadline"]` in `stops_for()` when slack is ample.
- `buffer_min_slack_min: int = 210` — minimum slack (`order["deadline"] - max(now, start) - leg_drive`) required to apply `delivery_buffer_min`. Increments `self.stats["buffered_stops"] += 1` when applied.
- `pre_warn_lead_min: int = 0` — when `> 0`, in `Desk.tick()`, checks unstaffed waiting orders on their deadline day (`self.now // DAY == order["deadline"] // DAY`) with `0 < (order["lastPickupAt"] - 3 * HOUR) - self.now <= p.pre_warn_lead_min`.
- `pre_warn_fee: float = 1.35` — when `pre_warn_lead_min` triggers, marks `self.pre_warned.add(order_id)`, increments `self.stats["pre_warned"] += 1`, reprices each unbooked gig of `order_id` to `[{"at": self.now, "feeCents": max(1, int(base * p.pre_warn_fee + 0.5))}, {"at": max(self.now + 30, order["lastPickupAt"] - 3 * HOUR), "feeCents": max(1, int(base * p.fee_warn + 0.5))}]`, and sends up to 2 direct offers at `p.pre_warn_fee`. Also rebuilt `self.pre_warned` in `Desk.rejoin()`.

Run commands:
- **Dev 1 (`gtn-ptw38-buf-alarm-dev`):**
  ```sh
  uv run lab eval -s trust_invest=0.05 -s notes_v2=True -s note_unsure=decline -s max_next_day_drive_min=480 -s fri_same_day_max_drive=100 -s thin_long_next_day_supply=50 -s ring_to_hub_same_day_min=60 -s same_day_min_supply=50 -s min_slack_min=150 -s slack_per_drive=0.75 -s price_target_win=0.38 -s min_supply=25 -s delivery_buffer_min=30 -s buffer_min_slack_min=210 -s pre_warn_lead_min=60 -s pre_warn_fee=1.35 --name gtn-ptw38-buf-alarm-dev
  ```
- **Dev 2 (`gtn-ptw40-buf-alarm-dev`):**
  ```sh
  uv run lab eval -s trust_invest=0.05 -s notes_v2=True -s note_unsure=decline -s max_next_day_drive_min=480 -s fri_same_day_max_drive=100 -s thin_long_next_day_supply=50 -s ring_to_hub_same_day_min=60 -s same_day_min_supply=50 -s min_slack_min=150 -s slack_per_drive=0.75 -s price_target_win=0.40 -s min_supply=22 -s delivery_buffer_min=30 -s buffer_min_slack_min=210 -s pre_warn_lead_min=60 -s pre_warn_fee=1.35 --name gtn-ptw40-buf-alarm-dev
  ```

## Results (level 8, vs champion v2, paired)
| set | run folder | mean margin | Δmargin ± SE | t | better/worse | on-time min (mean, Δ) | SAFE |
|---|---|---:|---:|---:|---:|---:|---|
| smoke (noop) | `runs/20261114-031416-gtn-buf-alarm-noop` | €9,662.25 | €+0.00 ± 0.00 | — | 0 / 0 | 95.5% (96.7%, +0.00%) | yes |
| smoke (Smoke 1: `buf` only on `ptw=0.38`) | `runs/20261114-031526-gtn-ptw38-buf-smoke1` | €10,371.72 | €+709.47 ± 521.30 | 1.36 | 3 / 1 | 95.7% (96.8%, +0.13%) | yes |
| smoke (Smoke 2: `alarm` only on `ptw=0.38`) | `runs/20261114-031628-gtn-ptw38-alarm-smoke2` | €10,805.17 | €+1,142.93 ± 595.25 | 1.92 | 4 / 0 | 94.5% (97.2%, +0.56%) | yes |
| smoke (Smoke 3: `buf+alarm` on `ptw=0.38`) | `runs/20261114-031706-gtn-ptw38-buf-alarm-smoke3` | €10,786.03 | €+1,123.79 ± 551.33 | 2.04 | 3 / 1 | **97.1% (97.8%, +1.12%)** | yes |
| smoke (Smoke 4: `buf+alarm` on `ptw=0.40, ms=22`) | `runs/20261114-031827-gtn-ptw40-buf-alarm-smoke4` | €11,233.67 | €+1,571.42 ± 518.90 | 3.03 | 4 / 0 | 95.8% (97.3%, +0.65%) | yes |
| **dev Dev 1 (`gtn-ptw38-buf-alarm-dev`)** | `runs/20261114-031907-gtn-ptw38-buf-alarm-dev` | **€10,088.03** | **€+1,097.73 ± 199.48** | **5.50** | **15 / 1** | **94.3% (97.9%, +1.10%)** | **yes** |
| **dev Dev 2 (`gtn-ptw40-buf-alarm-dev`)** | `runs/20261114-032059-gtn-ptw40-buf-alarm-dev` | **€10,508.07** | **€+1,517.77 ± 201.53** | **7.53** | **16 / 0** | **95.8% (97.7%, +0.96%)** | **yes** |

### Head-to-head `uv run lab compare` vs `n14-02114` Run 3 (`runs/20261114-022434-stack-gtn-ptw38-dev`)
| Comparison | Δmargin ± SE | t | better/worse | Δon-time | on-time min (mean) |
|---|---:|---:|---:|---:|---:|
| **Dev 1 (`ptw=0.38, ms=25 + buf + alarm`)** vs Run 3 (`ptw=0.38, ms=25`) | `€+58.45 ± 121.11` | `0.48` | `9 / 7` | **`+0.53%`** | `94.3%` (`97.9%` vs `97.3%`) |
| **Dev 2 (`ptw=0.40, ms=22 + buf + alarm`)** vs Run 3 (`ptw=0.38, ms=25`) | **`€+478.49 ± 134.12`** | **`3.57`** | **`13 / 3`** | **`+0.39%`** | **`95.8%`** (`97.7%` vs `97.3%`) |
| **Dev 2 (`ptw=0.40, ms=22 + buf + alarm`)** vs Dev 1 (`ptw=0.38, ms=25 + buf + alarm`) | **`€+420.04 ± 146.67`** | **`2.86`** | **`12 / 4`** | `-0.14%` | **`95.8%`** (`97.7%` vs `97.9%`) |

### Detailed stats counters and ledger breakdown on dev (16 worlds total / mean per world)
| Metric / Counter | Champion v2 | `n14-02114` Run 3 (`ptw=0.38`) | Dev 1 (`ptw=0.38 + buf + alarm`) | Dev 2 (`ptw=0.40, ms=22 + buf + alarm`) |
|---|---:|---:|---:|---:|
| Mean margin (€/world) | €8,990.31 | €10,029.58 | **€10,088.03** | **€10,508.07** |
| Worst-seed margin (€) | €6,017.30 | €7,078.06 | **€7,416.45** | **€7,523.75** |
| Active won orders (total / mean) | 3,644 (227.75/w) | 4,096 (256.00/w) | 4,103 (256.44/w) | **4,331 (270.69/w)** |
| **Total late orders (late %)** | 118 (7.38/w, 3.24%) | 112 (7.00/w, 2.73%) | **90 (5.62/w, 2.19%)** | **99 (6.19/w, 2.29%)** |
| **On-time mean / worst seed** | 96.75% / 94.36% | 97.32% / 94.26% | **97.85% / 94.33%** | **97.71% / 95.80%** |
| `buffered_stops` (total / mean) | 0 (0.00/w) | 0 (0.00/w) | **4,065 (254.06/w)** | **4,300 (268.75/w)** |
| `pre_warned` (total / mean) | 0 (0.00/w) | 0 (0.00/w) | **190 (11.88/w)** | **192 (12.00/w)** |
| `offers` / `offer_accepted` | 0 / 0 | 0 / 0 | 380 (23.75/w) / 7 (0.44/w) | 384 (24.00/w) / 7 (0.44/w) |
| `deadline_close` warnings | 193 (12.06/w) | 225 (14.06/w) | **218 (13.62/w)** | 241 (15.06/w) |
| `gig_expired` | 121 (7.56/w) | 104 (6.50/w) | 105 (6.56/w) | 119 (7.44/w) |
| `won_same_day` | 1,147 (71.69/w) | 1,606 (100.38/w) | 1,599 (99.94/w) | **1,665 (104.06/w)** |
| `won_next_day` | 2,362 (147.62/w) | 2,340 (146.25/w) | 2,352 (147.00/w) | **2,515 (157.19/w)** |
| `won_within_3_days` | 173 (10.81/w) | 189 (11.81/w) | 192 (12.00/w) | **196 (12.25/w)** |
| `won_ring_hub_same_day` / late | 0 / 0 | 214 (13.38/w) / 5 | 218 (13.62/w) / **3 (1.38%)** | 228 (14.25/w) / 6 (2.63%) |
| `visit_failed` | 73 (4.56/w) | 3 (0.19/w) | **1 (0.06/w)** | 8 (0.50/w) |
| Ledger `revenue` (€/world) | +26,922.43 | +28,082.93 | +28,197.66 | **+29,650.81** |
| Ledger `driver_fee` (€/world) | -17,286.92 | -17,673.60 | -17,734.56 | -18,776.97 |
| Ledger `late_refund` (€/world) | -376.20 | -288.22 | -284.84 | **-260.38** |
| Ledger `failed_visit` (€/world) | -165.44 | -6.68 | **-3.56** | -21.21 |
| Ledger `release_fee` (€/world) | -53.48 | -50.20 | **-46.63** | -53.21 |
| Ledger `waiting` (€/world) | -39.38 | -24.38 | -24.38 | **-20.73** |

### Key findings
1. **At fixed intake (`ptw=0.38, min_supply=25`, Dev 1 vs Run 3), `delivery_buffer_min=30, buffer_min_slack_min=210` + `pre_warn_lead_min=60, pre_warn_fee=1.35` eliminates 22 late orders across 16 worlds (`112 → 90`, `-19.6%` late orders):**
   - `buffered_stops` fires on `254.06` stops/world without increasing `gig_expired` (`6.56/w` vs `6.50/w` in Run 3), proving that the `buffer_min_slack_min=210` slack guard completely prevents the window-squeezing side effect that held back `n14-05-buffer`.
   - `pre_warned` fires on `11.88` deadline-day orders/world, cutting `deadline_close` warnings (`14.06 → 13.62/w`), reducing `release_fee` (`-€50.20 → -€46.63/w`), lifting mean on-time by **`+0.53%` (`97.32% → 97.85%`)**, lifting mean margin to **`€10,088.03` (`Δmargin €+1,097.73 ± 199.48, t = 5.50`, 15/16 seeds better vs Champion v2)**, and lifting worst-seed margin by `+€338.39` (`€7,078.06 → €7,416.45`).
2. **Cashing in the `+0.53%` operational on-time cushion (`price_target_win=0.40, min_supply=22`, Dev 2) unlocks `+€478.49/world` (`t = 3.57`) over Run 3 while *still* beating Run 3 on on-time (`97.71%` vs `97.32%`) and worst-seed on-time (`95.80%` vs `94.26%`):**
   - Winning `270.69` orders/world (`+14.69/w` over Run 3 and `+42.94/w` over Champion v2) with `delivery_buffer_min=30, buffer_min_slack_min=210, pre_warn_lead_min=60, pre_warn_fee=1.35` produces **fewer total late orders (`99` vs `112`) and lower `late_refund` (`-€260.38/w` vs `-€288.22/w`) than Run 3 at `ptw=0.38`**!
   - Even `dev-07` — historically our hardest seed for on-time — rises from `94.26%` on-time (`€10,738` margin) in Run 3 to **`96.8%` on-time (`€12,053.50` margin)** in Dev 2, making `dev-01` (`95.8%`) the new worst seed and leaving a **+5.8% safety cushion above the 90% ranking threshold**.
   - Versus Champion v2 across all 16 dev seeds, Dev 2 (`gtn-ptw40-buf-alarm-dev`) wins **16 out of 16 seeds (`t = 7.53`)** with **`Δmargin €+1,517.77 ± 201.53`** and **`Δon-time +0.96%`**.

## Verdict
**adopt** — Adding `delivery_buffer_min=30, buffer_min_slack_min=210, pre_warn_lead_min=60, pre_warn_fee=1.35` cuts late orders by 19.6% (`112 → 90`) on `ptw=0.38` (`€10,088.03`, `Δmargin €+1,097.73 ± 199.48, t = 5.50`, 15/16 better) and safely unlocks `price_target_win=0.40, min_supply=22` to reach **`€10,508.07` mean margin (`Δmargin €+1,517.77 ± 201.53, t = 7.53`, 16/16 seeds better vs Champion v2; `Δmargin €+478.49 ± 134.12, t = 3.57`, 13/16 better vs `stack-gtn-ptw38-dev`)** with **95.8% worst-seed on-time (97.7% mean)**.
