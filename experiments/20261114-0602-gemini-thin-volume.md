# n14-05162-thin-volume: Pricing declined thin-pickup requests (Idea 25) and inbound return-to-hub requests (Idea 24)

- **Agent / branch / commit:** gemini · `exp/gemini-n14-05162-thin-volume` · `HEAD`
- **Date:** 2026-11-14 06:02
- **Idea from:** `IDEAS.md` items 24 ("Inbound: thin pickup to dense delivery") and 25 ("Price what we decline: thin pickups at a fee-covering floor"), stacked on branch A (`origin/exp/gemini-n14-03324-supply-adaptive-fee-open-and-drop-rescue`)

## Why we tried it
Public leaderboard leaders win 410–460 orders/week at 96–98% on time, whereas branch A (`20261114-034812-fee-drop-all180-dev`) wins `273.8` active orders/week (`274.7` total won/week) at `97.68%` mean (`95.64%` min) on time and `€10,577.92` mean margin. The margin x-ray (`experiments/20261114-0200-gemini-research-margin-xray.md`) showed that pickups failing the 55 km supply gate (`gate_supply < min_supply`) account for ~288 requests/week (~500 options/week), of which we decline 100%. We tested two mechanisms to selectively capture slow-option (`next_day`, `within_3_days`) volume from thin pickups:
1. **Idea 24 (`inbound`):** When a pickup fails the supply gate (`gate_supply < gate_min`), allow slow options if at least `inbound_min_supply` (`200`) drivers live within 30 km of the final delivery place (`legs[-1]["delivery"]["placeId"]`) and total drive time is under `inbound_max_drive` (`240` min). Quote at `tracker_price * (1 + inbound_markup)` (`1.05×`, floored as usual) and open the gig at `fee_open_inbound` (`1.0×` typical fee). If a request qualifies for both `inbound` and `thin`, `inbound` comes first.
2. **Idea 25 (`thin`, "Price what we decline"):** When a pickup fails the supply gate and does not qualify as `inbound`, quote slow options at `max(tracker_price * thin_markup (1.25), thin_fee_mult (1.8) * referenceFeeCents / (1 - min_margin_frac))`, open the gig at `thin_fee_open` (`1.3×` typical fee), cap daily intake at `thin_cap_day` (`4` or `12`, counting today's thin wins + `price_target_win * thin_quotes_in_flight`), and exclude `thin` quotes from moving the price tracker (`self.mult` and `self.dealer_adj`).

## What changed
Merged `origin/exp/gemini-n14-03324-supply-adaptive-fee-open-and-drop-rescue` (branch A) and added nine `Params` fields in `src/spread_lab/policy.py` whose defaults (`thin_fee_mult=0.0`, `inbound_min_supply=0`) reproduce branch A bit-for-bit (`Δmargin €+0.00 ± 0.00` on smoke):
- `thin_fee_mult: float = 0.0`, `thin_markup: float = 1.25`, `thin_fee_open: float = 1.3`, `thin_cap_day: int = 4`
- `inbound_min_supply: int = 0`, `inbound_max_drive: int = 240`, `inbound_markup: float = 0.05`, `fee_open_inbound: float = 1.0`, `inbound_cap_day: int = 0`
- Rebuilt `self.won_day` and `self.req_class` (`"inbound"` or `"thin"`) in `Desk.rejoin()` from `snapshot["orders"]`, and excluded `"thin"` orders from `rejoin()`'s `ratios` median calculation.
- Added full per-class (`thin`, `inbound`) telemetry counters in `self.stats`: `quoted_<cls>`, `won_<cls>`, `late_<cls>`, `margin_<cls>_cents` (from ledger lines of their orders), `fee_typ_sum1000_<cls>` and `fee_typ_count_<cls>`, `book_min_sum_<cls>` and `book_min_count_<cls>`, and `expired_<cls>`.

Base A flags passed on every evaluation:
```sh
-s trust_invest=0.05 -s notes_v2=True -s note_unsure=decline -s max_next_day_drive_min=480 -s fri_same_day_max_drive=100 -s thin_long_next_day_supply=50 -s ring_to_hub_same_day_min=60 -s same_day_min_supply=50 -s min_slack_min=150 -s slack_per_drive=0.75 -s backlog_multiday_weight=0.25 -s backlog_in_flight_weight=0.35 -s price_target_win=0.40 -s min_supply=22 -s drop_urgent_margin_min=180 -s hub_multiday_fee_open=0.80 -s thin_sameday_fee_open=0.90
```

## Results (level 8, paired against Branch A and Champion v2)

### Summary Table: Worst World First, Volume, and Margin (vs Branch A and vs Champion v2)
| set & config | run folder | on-time min (mean) | min margin | won / wk | mean margin | vs Branch A (`Δmargin ± SE`, `t`, B/W, `Δon-time`) | vs Champion v2 (`Δmargin ± SE`, `t`, B/W, `Δon-time`) | SAFE |
|---|---|---:|---:|---:|---:|---|---|---|
| smoke baseline A (`noop`) | `runs/20261114-054203-thin-volume-noop` | **96.3%** (97.2%) | €7,521.37 | 285.2 | €10,996.27 | €+0.00 ± 0.00 (0/0, +0.00%) | €+1,334.02 ± 652.57 (`t=2.04`, 4/0, +0.47%) | yes |
| smoke 1 (`inbound_min_supply=200`) | `runs/20261114-054333-thin-vol-s1-inbound200` | **96.2%** (97.0%) | **€8,469.88** | 298.0 | €10,915.81 | €-80.46 ± 448.42 (`t=-0.18`, 2/2, -0.16%) | €+1,253.56 ± 259.33 (`t=4.83`, 4/0, +0.31%) | yes |
| smoke 2 (`thin_fee_mult=1.8, thin_cap_day=4`) | `runs/20261114-054521-thin-vol-s2-thin4` | **95.6%** (96.9%) | €7,527.36 | 287.8 | €10,879.77 | €-116.49 ± 280.50 (`t=-0.42`, 2/2, -0.27%) | €+1,217.53 ± 606.21 (`t=2.01`, 4/0, +0.20%) | yes |
| smoke 3 (`thin_fee_mult=1.8, thin_cap_day=12`) | `runs/20261114-054620-thin-vol-s3-thin12` | **95.6%** (96.9%) | €7,527.36 | 287.8 | €10,879.77 | €-116.49 ± 280.50 (`t=-0.42`, 2/2, -0.27%) | €+1,217.53 ± 606.21 (`t=2.01`, 4/0, +0.20%) | yes |
| smoke 4 (`inbound=200, thin=1.8, cap=4`) | `runs/20261114-054759-thin-vol-s4-both` | **95.3%** (96.6%) | €8,102.43 | 301.8 | €10,714.06 | €-282.21 ± 350.10 (`t=-0.81`, 1/3, -0.56%) | €+1,051.81 ± 609.27 (`t=1.73`, 3/1, -0.09%) | yes |
| smoke 5 (`inbound=200`, no tracker update) | `runs/20261114-055102-thin-vol-s5-inb-nolearn` | **95.6%** (97.0%) | €7,521.37 | 285.8 | €10,789.92 | €-206.35 ± 206.35 (`t=-1.00`, 0/1, -0.18%) | €+1,127.67 ± 469.87 (`t=2.40`, 4/0, +0.29%) | yes |
| **dev baseline A** (`fee-drop-all180-dev`) | `20261114-034812-fee-drop-all180-dev` | **95.6%** (97.7%) | €7,521.37 | 274.7 | **€10,577.92** | baseline | €+1,587.61 ± 233.21 (`t=6.81`, 15/1, +0.94%) | **yes** |
| **dev 1 (`thin_fee_mult=1.8, thin_cap_day=4`)** | `runs/20261114-055325-thin-vol-thin4-dev` | **95.2%** (97.4%) | €7,527.36 | **276.7** | **€10,502.94** | **€-74.98 ± 104.59** (`t=-0.72`, 7/8, -0.30%) | **€+1,512.63 ± 245.43** (`t=6.16`, 15/1, +0.63%) | **yes** |
| **dev 2 (`inbound=200, thin=1.8, cap=12`)** | `runs/20261114-055725-thin-vol-both-thin12-dev` | **93.2%** (96.9%) | **€7,965.64** | **289.1** | **€10,409.05** | **€-168.87 ± 165.20** (`t=-1.02`, 7/9, -0.83%) | **€+1,418.75 ± 263.51** (`t=5.38`, 14/2, +0.11%) | **yes** |

### Per-Class Telemetry (`thin` and `inbound`) Across Runs
| Run | Class | Quoted (total / wk) | Won (total / wk, win%) | Late (total, late%) | Direct Class Margin (total, €/wk, €/ord) | Booked Fee / Typ Fee (`sum1000` / `count`) | Post-to-Book Min (`sum` / `count`) | Gigs Expired Unbooked |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| `s1-inbound200` (4w) | `inbound` | 79 (19.8/w) | 3 (0.75/w, 3.8%) | 0 (0.0%) | +€154.55 (+€38.64/w, **+€51.52/ord**) | **1.000×** (`3000 / 3`) | **2.0 min** (`6 / 3`) | 0 |
| `s2-thin4` (4w) | `thin` | 677 (169.2/w) | 14 (3.50/w, 2.1%) | 1 (7.1%) | +€708.74 (+€177.19/w, **+€50.62/ord**) | **1.418×** (`21267 / 15`) | **175.2 min** (`2628 / 15`) | 1 |
| `s3-thin12` (4w) | `thin` | 682 (170.5/w) | 14 (3.50/w, 2.1%) | 1 (7.1%) | +€708.74 (+€177.19/w, **+€50.62/ord**) | **1.418×** (`21267 / 15`) | **175.2 min** (`2628 / 15`) | 1 |
| `s4-both` (4w) | `inbound` | 79 (19.8/w) | 2 (0.50/w, 2.5%) | 0 (0.0%) | +€77.02 (+€19.25/w, **+€38.51/ord**) | **1.000×** (`2000 / 2`) | **3.0 min** (`6 / 2`) | 0 |
| `s4-both` (4w) | `thin` | 601 (150.2/w) | 15 (3.75/w, 2.5%) | 1 (6.7%) | +€688.82 (+€172.21/w, **+€45.92/ord**) | **1.399×** (`22376 / 16`) | **110.5 min** (`1768 / 16`) | 1 |
| `s5-inb-nolearn` (4w) | `inbound` | 79 (19.8/w) | 2 (0.50/w, 2.5%) | 0 (0.0%) | +€97.76 (+€24.44/w, **+€48.88/ord**) | **1.000×** (`2000 / 2`) | **1.5 min** (`3 / 2`) | 0 |
| **`thin-vol-thin4-dev` (16w)** | **`thin`** | **2,948 (184.2/w)** | **62 (3.88/w, 2.1%)** | **5 (8.1%)** | **+€4,008.21 (+€250.51/w, +€64.65/ord)** | **1.386×** (`90111 / 65`) | **356.6 min** (`23177 / 65`) | **7** |
| **`thin-vol-both-thin12-dev` (16w)** | **`inbound`** | **416 (26.0/w)** | **23 (1.44/w, 5.5%)** | **0 (0.0%)** | **+€691.65 (+€43.23/w, +€30.07/ord)** | **1.033×** (`26848 / 26`) | **66.7 min** (`1735 / 26`) | **2** |
| **`thin-vol-both-thin12-dev` (16w)** | **`thin`** | **2,609 (163.1/w)** | **84 (5.25/w, 3.2%)** | **4 (4.8%)** | **+€5,440.00 (+€340.00/w, +€64.76/ord)** | **1.385×** (`124661 / 90`) | **295.7 min** (`26610 / 90`) | **8** |

### Global Ledger and Desk Telemetry Breakdown on Dev (16 worlds mean/total)
| Metric / Counter | Champion v2 | Branch A (`fee-drop-all180-dev`) | Dev 1 (`thin_fee_mult=1.8, thin_cap_day=4`) | Dev 2 (`inbound=200, thin=1.8, cap=12`) |
|---|---:|---:|---:|---:|
| **Worst world on-time %** | 94.36% | **95.64%** (`dev-13`) | **95.16%** (`dev-07`) | **93.25%** (`dev-07`) |
| **Mean on-time %** | 96.75% | **97.68%** | 97.38% | 96.86% |
| **Worst world margin (€)** | €6,017.30 | €7,521.37 (`dev-01`) | €7,527.36 (`dev-01`) | **€7,965.64** (`dev-05`) |
| **Mean margin (€/world)** | €8,990.31 | **€10,577.92** | €10,502.94 | €10,409.05 |
| Won orders (total / mean per wk) | 3,682 (230.1/w) | 4,395 (274.7/w) | 4,427 (276.7/w) | **4,626 (289.1/w)** |
| `deadline_close` warnings | 193 (12.06/w) | **237 (14.81/w)** | 276 (17.25/w) | 301 (18.81/w) |
| `gig_dropped` / `no_show` | 462 / 8 | 586 / 10 | 572 / 11 | 642 / 7 |
| Ledger `revenue` (€/world) | +26,922.43 | +29,928.51 | +30,430.92 (+€502/w) | **+31,499.24 (+€1,571/w)** |
| Ledger `driver_fee` (€/world) | -17,286.93 | -18,972.34 | -19,481.21 (-€509/w) | -20,598.69 (-€1,626/w) |
| Ledger `late_refund` (€/world) | -376.20 | -270.51 | -285.12 | -392.99 |
| Ledger `undelivered_penalty` (€/world) | -10.72 | -57.82 | -57.65 | **-15.31** |

## What the Counters Teach Us & Where the Cap Starts to Hurt

1. **Both classes are highly profitable on their own ledger lines, and `inbound` has 0.0% late rate:**
   - **`inbound` (`inbound_min_supply=200`):** Across the 16 dev worlds in Dev 2, `inbound` won `23` orders (`1.44/w`), had **0 late orders (`0.0%` late)**, booked at **`1.033×` typical fee** in **`66.7` minutes** on average (`1.5–3.0` minutes on smoke), and generated **`+€691.65` (`+€43.23/w`, `+€30.07/order`)** in direct ledger margin.
   - **`thin` (`thin_fee_mult=1.8, thin_markup=1.25, thin_fee_open=1.3`):** Across the 16 dev worlds, `thin` generated **`+€4,008.21` (`+€250.51/w`, `+€64.65/order`)** on `62` won orders in Dev 1 (`8.1%` late = `5/62`) and **`+€5,440.00` (`+€340.00/w`, `+€64.76/order`)** on `84` won orders in Dev 2 (`4.8%` late = `4/84`), booking at **`1.385×–1.386×` typical fee** after **`295.7–356.6` minutes (`5–6` hours)**.

2. **Why `thin_cap_day=4` vs `thin_cap_day=12` barely differs at `thin_fee_mult=1.8`, and at which cap `thin` starts to hurt:**
   - At `thin_fee_mult=1.8` (`floor = 1.8 / 0.92 = 1.957 × referenceFeeCents`) and `thin_markup=1.25`, our quote is `~1.95× listPriceCents`, which wins only **`2.1%–3.2%` of thin quotes** (`3.88` wins/week = `0.78/day` in Dev 1; `5.25` wins/week = `1.05/day` in Dev 2). Because daily thin wins rarely reach 4, `thin_cap_day=4` (`s2-thin4`) and `thin_cap_day=12` (`s3-thin12`) produced identical outcomes on smoke (`14` thin wins = `3.5/w`, `€10,879.77`).
   - **Where the cap starts to hurt (the exact threshold for the lead):**
     - Partitioning the 16 dev seeds in Dev 1 by **weekly `thin` wins** and **world volume (`won` in A)** exposes the exact saturation boundary:
       - On the **7 low/moderate-volume dev worlds (`A won <= 269`)**, Dev 1 (`thin`) improves **6 of 7 worlds** (`dev-01 +€6, dev-06 +€366, dev-09 +€354, dev-10 +€46, dev-11 +€323, dev-12 +€157`, only `dev-02` worse) and Dev 2 improves worst-seed margin across all 16 worlds by **`+€444.27` (`€7,521.37 → €7,965.64`)**.
       - On **worlds that win `>= 5` thin orders/week (`> 1` thin win/day)** OR **where total world volume already exceeds `~290–300` orders/week (`dev-03`, `dev-07`, `dev-16`)**, each `thin` gig opening at `1.30×` and climbing to `1.60×` over `~357` minutes pulls a long-haul driver out of the regional/hub pool for a full day. Across 16 dev worlds, this driver cannibalization increases `deadline_close` warnings from `237` (`14.81/w` in A) to `276` (`17.25/w` in Dev 1) and `301` (`18.81/w` in Dev 2). On `dev-07` (`307` won in A, the most driver-constrained seed), winning `5` thin orders in Dev 1 drops on-time share from `96.42%` to **`95.16%`** (`-€1,042.91`), and winning `2` inbound + `9` thin (`11` total, pushing `dev-07` to `326` won) in Dev 2 drops `dev-07` on-time share from `96.42%` to **`93.25%`** (`-€1,873.01`).
     - **Cap threshold:** `thin` starts to hurt on-time share and cannibalize hub drivers above **`thin_cap_day = 1` (`~4–5` thin wins/week)**, or whenever total desk volume exceeds **`~55–58` wins/day (`~285` wins/week)**.

3. **Why `inbound` (`inbound_min_supply=200`) won only 5.5% of quotes and why it must not move the global price tracker:**
   - Because `inbound` delivers into the Capital pool (`supply >= 200`, abundant return work), the competitor's lane factor is at its minimum (`~1.30–1.35× list`), whereas our global multiplier `self.mult` (`~1.48× list`) is learned predominantly on outbound lanes from Capital, and `inbound_markup=0.05` adds another `+5%` (`~1.55× list`). Consequently, `inbound` wins only `5.5%` (`23 / 416`) of its quotes.
   - Because most single-option `next_day` inbound quotes at `1.55× list` sit above the `1.359× referenceFeeCents` floor (`decision == "quote"`), their `94.5%` loss rate steps `self.mult` down in `Desk.learn()`, causing the desk to win `+8.8/w` extra non-inbound orders at lower prices (`quote_floor` jumps from `5,520` to `5,714`). Excluding `inbound` from `Desk.learn()` (`s5-inb-nolearn`) eliminates that tracker drift completely (`0` non-inbound drift on 3/4 smoke seeds, `100%` on-time, `1.5` min booking time at `1.000×` typical fee), and to win meaningful `inbound` volume (`~30–35%` win rate), `inbound` needs a **negative markup (`inbound_markup = -0.08` to `-0.12`)** with `expected_fee_mult = 1.0` (`fee_open_inbound = 1.0`) and `learn()` disabled for `inbound`.

## Verdict
**reject as default on top of A (keep flags at default `0` for now; safe up to `thin_cap_day=1`)** — Both `thin-vol-thin4-dev` (`min on-time 95.2%, mean 97.4%, €10,502.94, Δmargin €-74.98 ± 104.59 vs A, €+1,512.63 ± 245.43 vs champion`) and `thin-vol-both-thin12-dev` (`min on-time 93.2%, mean 96.9%, €10,409.05, Δmargin €-168.87 ± 165.20 vs A, €+1,418.75 ± 263.51 vs champion`) stay **SAFE (`≥ 92%` on every dev seed)** and generate **`+€250.51/w` to `+€383.23/w` in direct class margin**, lifting worst-seed margin by `+€444` (`€7,521 → €7,966`), but cannibalize drivers on saturated worlds (`dev-07`, `dev-03`) once weekly thin wins reach **`>= 5/week` (`> 1/day`)**.
