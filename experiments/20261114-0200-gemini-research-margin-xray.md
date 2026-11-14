# research-margin-xray: where champion v2 loses €4.5k–€6.0k/wk against the leaderboard leaders

- **Agent / branch / commit:** gemini · `exp/gemini-n14-01392-margin-xray-v2` · `66554de`
- **Date:** 2026-11-14 02:00
- **Idea from:** `IDEAS.md` research items R2/R3 + night lead prompt `01-margin-xray.md`

## Question & Instrument
In Ranking Round 4, champion v2 earned ~€10.8k/world on the same level-8 worlds where House best earned ~€14.4k and the leaderboard leader earned ~€16.0k. Across the **16 champion v2 dev worlds** (`champion/results/dev-L8.jsonl`, revealed into `/tmp/reveals-n14-01` and analyzed with `experiments/scripts/margin_xray.py`), we decompose all **16,554 requests** (`1,034.6/wk`) and **3,682 won orders** (`230.1/wk`) to answer:
1. How do requests decompose by `pickup_class × option × drive_band` across share quoted, floored, declined, won, lost, `price / list`, `booked_fee / typical_fee`, minutes to book, late refunds, and failed visits?
2. How is our quote `price / list` positioned against the competitor across `dealer (D01 vs Top 2-3 vs Others) × weekday (Mon..Fri) × option × drive_band (<100, 100-300, >300 min)`, and what happens on multi-option requests?
3. What are the **top 4 ranked euro-per-week leaks**, and which exact `Params` or mechanisms close them?

---

## 0. Executive Summary: Champion v2's Weekly Ledger & Intake

| Metric / Ledger Line | 16-World Total | Mean per Week | Share of Requests / Revenue |
|---|---:|---:|---:|
| **Total requests** | 16,554 | **1,034.6 / wk** | 100.0% of requests |
| **Quoted requests** | 10,763 | **672.7 / wk** | 65.0% of requests |
| — *Normal quotes (no option floored)* | 7,518 | **469.9 / wk** | 45.4% of requests (69.8% of quoted) |
| — *Any-option floored (`floor = 1.359 × typ_fee`)* | 3,245 | **202.8 / wk** | 19.6% of requests (30.2% of quoted) |
| — *Primary-option floored* | 2,578 | **161.1 / wk** | 15.6% of requests (24.0% of quoted) |
| **Declined requests (`4.0 × list`)** | 5,791 | **361.9 / wk** | 35.0% of requests |
| — *Declined by `supply_gate` (`s55 < 30`)* | 4,614 | **288.4 / wk** | 79.7% of declines |
| — *Declined by `option_slack_or_speed_gate`* | 1,028 | **64.2 / wk** | 17.8% of declines |
| — *Declined by `backlog_gate`* | 149 | **9.3 / wk** | 2.6% of declines |
| **Won orders** | 3,682 | **230.1 / wk** | **34.2% of quoted** (22.2% of all) |
| **Late / undelivered orders** | 118 | **7.38 / wk** | **3.20% late** (96.80% mean on-time, 94.36% min) |
| **Revenue** (`revenue`) | +€430,759 | **+€26,922.43 / wk** | 100.0% of revenue (€117.0/order) |
| **Driver fees** (`driver_fee`) | −€276,591 | **−€17,286.92 / wk** | −64.2% of revenue (€75.1/order, med `0.904× typ`) |
| **Late refunds + undelivered** | −€6,191 | **−€386.92 / wk** | −1.4% of revenue (`late_refund` −€376.20, `undeliv` −€10.72) |
| **Failed visits** (`failed_visit`) | −€2,647 | **−€165.44 / wk** | −0.6% of revenue (3.75 orders/wk; 56 `not_ready`, 15 `no_plates`, 2 `closed`) |
| **Release fees & waiting** | −€1,486 | **−€92.86 / wk** | −0.3% of revenue (`release_fee` −€53.48, `waiting` −€39.38) |
| **Net Margin** | **+€143,845** | **+€8,990.31 / wk** | **33.4% net margin** (€39.07/won order) |

---

## 1. Decomposition of All 16,554 Requests by Class (`pickup_class × option × drive_band`)

We define the four pickup supply classes aligned with champion v2's gates (`same_day_min_supply=100`, `min_supply=30`, `gate_radius_km=55`):
- `1_dense>=100`: `s30 >= 100` or Capital (`helsinki`, `espoo`, `vantaa`) — where `same_day` is permitted.
- `2_mid_30-99`: `30 <= s30 < 100` — passes `s30 >= 30`, but `same_day` is blocked by `same_day_min_supply=100`.
- `3_ring_s55>=30`: `s30 < 30` and `s55 >= 30` (Hyvinkää, Porvoo, etc.) — passes the 55 km ring gate; `far_options="slow"` blocks `same_day`.
- `4_thin_s55<30`: `s55 < 30` — 100% declined by `gate_supply < 30`.

Drive bands follow the prompt's three brackets: `1_<100m` (`<100 min`), `2_100-300m` (`100–300 min`), `3_>300m` (`>300 min`).

### Table 1A: Ex-Ante Request-Level Decomposition (All 16,554 Requests = 1,034.6/wk)
*Each request is assigned its primary ex-ante option without peeking at win/loss outcome: fastest quoted option (`same_day > next_day > within_3_days`) if quoted, or slowest offered option (`next_day > within_3_days > same_day`) if declined.*

| Pickup Class | Ex-Ante Option | Drive Band | Req/wk | Quot% | Flr% | Decl% | Won/wk | Lost/wk | Win/Q | P/L Won | P/L Lost | Fee/Typ | MinBk | Late/wk | Late% | Late €/wk | Fail €/wk | Mrg/Ord | Mrg €/wk |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `1_dense>=100` | `same_day` | `1_<100m` | 167.8 | 98% | 7% | 2% | 56.1 | 109.0 | 34% | 1.47 | 1.56 | 0.90 | 24 | 1.00 | 1.8% | €17 | €43 | €26.8 | **€1,502** |
| `1_dense>=100` | `same_day` | `2_100-300m` | 74.1 | 94% | 10% | 6% | 34.2 | 35.7 | 49% | 1.48 | 1.56 | 0.88 | 33 | 1.00 | 2.9% | €32 | €28 | €52.3 | **€1,792** |
| `1_dense>=100` | `same_day` | `3_>300m` | 3.4 | 0% | 0% | 100% | 0.0 | 0.0 | 0% | — | — | — | — | 0.00 | — | €0 | €0 | — | €0 |
| `1_dense>=100` | `next_day` | `1_<100m` | 53.6 | 99% | 19% | 1% | 19.7 | 33.6 | 37% | 1.48 | 1.56 | 0.94 | 146 | 0.44 | 2.2% | €14 | €2 | €21.5 | **€424** |
| `1_dense>=100` | `next_day` | `2_100-300m` | 45.6 | 97% | 37% | 3% | 18.2 | 26.1 | 41% | 1.51 | 1.56 | 0.97 | 254 | 0.50 | 2.7% | €17 | €0 | €45.2 | **€822** |
| `1_dense>=100` | `next_day` | `3_>300m` | 41.2 | 97% | 36% | 3% | 17.9 | 22.1 | 45% | 1.52 | 1.58 | 0.93 | 188 | **1.69** | **9.4%** | **€155** | €27 | €65.7 | **€1,175** |
| `1_dense>=100` | `within_3_days` | `3_>300m` | 0.1 | 0% | 0% | 100% | 0.0 | 0.0 | 0% | — | — | — | — | 0.00 | — | €0 | €0 | — | €0 |
| `2_mid_30-99` | `same_day` | `1_<100m` | 6.6 | 0% | 0% | 100% | 0.0 | 0.0 | 0% | — | — | — | — | 0.00 | — | €0 | €0 | — | €0 |
| `2_mid_30-99` | `same_day` | `2_100-300m` | 12.9 | 0% | 0% | 100% | 0.0 | 0.0 | 0% | — | — | — | — | 0.00 | — | €0 | €0 | — | €0 |
| `2_mid_30-99` | `same_day` | `3_>300m` | 1.2 | 0% | 0% | 100% | 0.0 | 0.0 | 0% | — | — | — | — | 0.00 | — | €0 | €0 | — | €0 |
| `2_mid_30-99` | `next_day` | `1_<100m` | 50.3 | 94% | 29% | 6% | 8.9 | 38.6 | **19%** | 1.48 | 1.47 | 0.91 | 86 | 0.31 | 3.5% | €4 | €0 | €22.3 | **€198** |
| `2_mid_30-99` | `next_day` | `2_100-300m` | 68.2 | 92% | 36% | 8% | 15.7 | 47.4 | **25%** | 1.44 | 1.51 | 0.91 | 115 | 0.81 | 5.2% | €23 | €26 | €35.2 | **€552** |
| `2_mid_30-99` | `next_day` | `3_>300m` | 24.4 | 91% | 37% | 9% | 8.0 | 14.2 | 36% | 1.48 | 1.56 | 0.93 | 116 | 0.56 | 7.0% | €70 | €4 | €53.3 | **€427** |
| `3_ring_s55>=30` | `same_day` | `1_<100m` | 18.4 | 0% | 0% | 100% | 0.0 | 0.0 | 0% | — | — | — | — | 0.00 | — | €0 | €0 | — | €0 |
| `3_ring_s55>=30` | `same_day` | `2_100-300m` | 8.2 | 0% | 0% | 100% | 0.0 | 0.0 | 0% | — | — | — | — | 0.00 | — | €0 | €0 | — | €0 |
| `3_ring_s55>=30` | `same_day` | `3_>300m` | 1.6 | 0% | 0% | 100% | 0.0 | 0.0 | 0% | — | — | — | — | 0.00 | — | €0 | €0 | — | €0 |
| `3_ring_s55>=30` | `next_day` | `1_<100m` | 96.6 | 100% | 33% | 0% | 22.3 | 74.1 | **23%** | 1.54 | 1.49 | 0.87 | 32 | 0.25 | **1.1%** | €7 | €14 | €23.3 | **€520** |
| `3_ring_s55>=30` | `next_day` | `2_100-300m` | 54.9 | 99% | 38% | 1% | 21.4 | 32.9 | 39% | 1.48 | 1.52 | 0.90 | 100 | 0.25 | **1.2%** | €8 | €15 | €47.1 | **€1,009** |
| `3_ring_s55>=30` | `next_day` | `3_>300m` | 17.2 | 96% | 35% | 4% | 7.7 | 8.9 | 46% | 1.56 | 1.59 | 0.93 | 181 | 0.56 | **7.3%** | €40 | €7 | €74.1 | **€569** |
| `4_thin_s55<30` | `same_day` | `1_<100m` | 6.1 | 0% | 0% | 100% | 0.0 | 0.0 | 0% | — | — | — | — | 0.00 | — | €0 | €0 | — | €0 |
| `4_thin_s55<30` | `same_day` | `2_100-300m` | 21.9 | 0% | 0% | 100% | 0.0 | 0.0 | 0% | — | — | — | — | 0.00 | — | €0 | €0 | — | €0 |
| `4_thin_s55<30` | `same_day` | `3_>300m` | 5.2 | 0% | 0% | 100% | 0.0 | 0.0 | 0% | — | — | — | — | 0.00 | — | €0 | €0 | — | €0 |
| `4_thin_s55<30` | `next_day` | `1_<100m` | 45.3 | 0% | 0% | 100% | 0.0 | 0.0 | 0% | — | — | — | — | 0.00 | — | €0 | €0 | — | €0 |
| `4_thin_s55<30` | `next_day` | `2_100-300m` | 153.8 | 0% | 0% | 100% | 0.0 | 0.0 | 0% | — | — | — | — | 0.00 | — | €0 | €0 | — | €0 |
| `4_thin_s55<30` | `next_day` | `3_>300m` | 55.8 | 0% | 0% | 100% | 0.0 | 0.0 | 0% | — | — | — | — | 0.00 | — | €0 | €0 | — | €0 |
| `4_thin_s55<30` | `within_3_days` | `3_>300m` | 0.2 | 0% | 0% | 100% | 0.0 | 0.0 | 0% | — | — | — | — | 0.00 | — | €0 | €0 | — | €0 |

### Table 1B: Option-Level Decomposition (All 1,797.9 Offered Options/wk Across the 16,554 Requests)
*Here `WOth` = requests/wk where this option was quoted, we won the request, but the dealer selected a faster/different quoted option of ours.*

| Pickup Class | Option | Drive Band | Off/wk | Quot% | Flr% | Decl% | Won/wk | WOth/wk | Lost/wk | OptWin/Q | P/L Won | P/L Lost | Fee/Typ | MinBk | Late% | Late €/wk | Fail €/wk | Mrg/Ord | Mrg €/wk |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `1_dense>=100` | `same_day` | `1_<100m` | 171.4 | 96% | 7% | 4% | 51.6 | 4.6 | 109.0 | 31% | 1.46 | 1.56 | 0.91 | 24 | 1.8% | €14 | €38 | €26.0 | €1,341 |
| `1_dense>=100` | `same_day` | `2_100-300m` | 85.9 | 81% | 10% | 19% | 20.1 | 14.1 | 35.7 | 29% | 1.46 | 1.56 | 0.89 | 28 | 4.7% | €30 | €19 | €46.7 | €939 |
| `1_dense>=100` | `same_day` | `3_>300m` | 22.6 | 0% | 0% | 100% | 0.0 | 0.0 | 0.0 | 0% | — | — | — | — | — | €0 | €0 | — | €0 |
| `1_dense>=100` | `next_day` | `1_<100m` | 189.2 | 100% | 20% | 0% | 22.8 | **42.9** | 123.2 | 12% | 1.50 | 1.52 | 0.92 | 101 | 1.9% | €14 | €6 | €24.4 | €558 |
| `1_dense>=100` | `next_day` | `2_100-300m` | 102.8 | 99% | 31% | 1% | 30.1 | **17.3** | 54.1 | 30% | 1.53 | 1.53 | 0.91 | 110 | 1.9% | €19 | €9 | €51.9 | €1,564 |
| `1_dense>=100` | `next_day` | `3_>300m` | 41.2 | 97% | 36% | 3% | 16.0 | 1.9 | 22.1 | 40% | 1.52 | 1.58 | 0.95 | 180 | **10.5%** | **€155** | €27 | €63.0 | €1,008 |
| `1_dense>=100` | `within_3_days` | `1_<100m` | 35.3 | 100% | 31% | 0% | 1.4 | **12.6** | 21.3 | 4% | 1.50 | 1.51 | 0.87 | 147 | 4.3% | €3 | €0 | €19.0 | €27 |
| `1_dense>=100` | `within_3_days` | `2_100-300m` | 17.2 | 100% | 53% | 0% | 2.2 | **6.2** | 8.8 | 13% | 1.47 | 1.56 | 0.87 | 94 | 0.0% | €0 | €0 | €50.9 | €111 |
| `1_dense>=100` | `within_3_days` | `3_>300m` | 7.0 | 99% | 54% | 1% | 1.9 | 1.3 | 3.8 | 27% | 1.49 | 1.57 | 0.91 | 329 | 0.0% | €0 | €0 | €88.8 | €166 |
| `2_mid_30-99` | `same_day` | `All` | 110.4 | 0% | 0% | 100% | 0.0 | 0.0 | 0.0 | 0% | — | — | — | — | — | €0 | €0 | — | €0 |
| `2_mid_30-99` | `next_day` | `1_<100m` | 50.3 | 94% | 29% | 6% | 8.9 | 0.0 | 38.6 | 19% | 1.48 | 1.47 | 0.91 | 86 | 3.5% | €4 | €0 | €22.3 | €198 |
| `2_mid_30-99` | `next_day` | `2_100-300m` | 68.2 | 92% | 36% | 8% | 14.6 | 1.1 | 47.4 | 23% | 1.43 | 1.51 | 0.92 | 126 | 5.6% | €23 | €23 | €34.5 | €503 |
| `2_mid_30-99` | `next_day` | `3_>300m` | 24.4 | 91% | 37% | 9% | 7.3 | 0.7 | 14.2 | 33% | 1.47 | 1.56 | 0.91 | 95 | **7.7%** | **€70** | €4 | €50.8 | €372 |
| `2_mid_30-99` | `within_3_days` | `1_<100m` | 11.6 | 95% | 38% | 5% | 0.0 | 1.9 | 9.0 | 0% | — | 1.51 | — | — | — | €0 | €0 | — | €0 |
| `2_mid_30-99` | `within_3_days` | `2_100-300m` | 14.8 | 95% | 53% | 5% | 1.1 | 3.0 | 9.9 | 8% | 1.56 | 1.57 | 0.86 | 56 | 0.0% | €0 | €3 | €43.8 | €49 |
| `2_mid_30-99` | `within_3_days` | `3_>300m` | 3.9 | 92% | 57% | 8% | 0.7 | 0.4 | 2.5 | 19% | 1.49 | 1.58 | 0.98 | 1165 | 0.0% | €0 | €0 | €79.8 | €55 |
| `3_ring_s55>=30` | `same_day` | `All` | 139.7 | 0% | 0% | 100% | 0.0 | 0.0 | 0.0 | 0% | — | — | — | — | — | €0 | €0 | — | €0 |
| `3_ring_s55>=30` | `next_day` | `1_<100m` | 96.6 | 100% | 33% | 0% | 21.6 | 0.7 | 74.1 | 22% | 1.53 | 1.49 | 0.87 | 30 | 1.2% | €7 | €12 | €23.1 | €500 |
| `3_ring_s55>=30` | `next_day` | `2_100-300m` | 54.9 | 99% | 38% | 1% | 19.8 | 1.6 | 32.9 | 36% | 1.47 | 1.52 | 0.91 | 118 | 1.3% | €8 | €9 | €46.4 | €919 |
| `3_ring_s55>=30` | `next_day` | `3_>300m` | 17.2 | 96% | 35% | 4% | 6.5 | 1.2 | 8.9 | 39% | 1.54 | 1.59 | 0.93 | 176 | **7.7%** | **€37** | €7 | €68.4 | €445 |
| `3_ring_s55>=30` | `within_3_days` | `1_<100m` | 17.8 | 100% | 51% | 0% | 0.7 | 3.5 | 13.6 | 4% | 1.64 | 1.51 | 0.87 | 48 | 0.0% | €0 | €2 | €30.1 | €21 |
| `3_ring_s55>=30` | `within_3_days` | `2_100-300m` | 10.1 | 99% | 60% | 1% | 1.6 | 2.4 | 6.1 | 16% | 1.60 | 1.59 | 0.85 | 24 | 0.0% | €0 | €5 | €55.0 | €89 |
| `3_ring_s55>=30` | `within_3_days` | `3_>300m` | 3.4 | 100% | 53% | 0% | 1.2 | 0.5 | 1.8 | 35% | 1.73 | 1.58 | 0.91 | 234 | 5.3% | €4 | €0 | €105.1 | €125 |
| `4_thin_s55<30` | `All options` | `All` | 498.7 | 0% | 0% | 100% | 0.0 | 0.0 | 0.0 | 0% | — | — | — | — | — | €0 | €0 | — | €0 |

---

## 2. Bracketing the Competitor Across Dealers, Weekdays, Options & Drive Lengths

### Table 2A: Competitor Bracketing by `Dealer Group × Weekday`
*`MedTrust` = exact median on-time trust count `[0..25]` held with that dealer at request arrival. `EstCmp50` = implied `price / list` where our win rate against the competitor is 50%.*

| Dealer Group | Day | Quot/wk | Norm/wk | Flr% | WinAll% | WinNrm% | WinFlr% | MedTrust | P/L Won | P/L Lost | EstCmp50 (P/L) |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **`1_D01`** (31% of quotes) | Mon | 45.8 | 30.1 | 34% | 33.4% | 39.9% | 21.0% | 0.0 | 1.38 | 1.41 | **1.31** |
| **`1_D01`** | Tue | 43.9 | 33.3 | 24% | **45.6%** | **48.6%** | 36.1% | 8.0 | 1.45 | 1.54 | **1.49** |
| **`1_D01`** | Wed | 42.2 | 38.1 | 10% | **45.1%** | **46.1%** | 35.8% | 20.5 | 1.67 | 1.78 | **1.70** |
| **`1_D01`** | Thu | 39.4 | 37.8 | 4% | **42.9%** | **43.1%** | 38.5% | 25.0 | 1.73 | 1.90 | **1.78** |
| **`1_D01`** | Fri | 38.6 | 32.2 | 17% | 34.2% | 35.9% | 25.5% | 25.0 | 1.80 | 1.88 | **1.71** |
| **`2_Top2-3`** (23% of quotes) | Mon | 42.1 | 27.9 | 34% | 29.5% | 32.7% | 23.2% | 0.0 | 1.38 | 1.46 | **1.31** |
| **`2_Top2-3`** | Tue | 28.4 | 19.9 | 30% | 38.1% | 41.5% | 30.1% | 2.0 | 1.46 | 1.50 | **1.41** |
| **`2_Top2-3`** | Wed | 25.9 | 21.9 | 16% | 39.3% | 40.0% | 35.4% | 5.0 | 1.48 | 1.55 | **1.46** |
| **`2_Top2-3`** | Thu | 31.9 | 26.2 | 18% | 39.5% | 42.7% | 25.0% | 8.0 | 1.57 | 1.56 | **1.50** |
| **`2_Top2-3`** | Fri | 25.1 | 18.9 | 25% | 37.3% | 41.6% | 24.2% | 11.0 | 1.55 | 1.60 | **1.49** |
| **`3_Others`** (46% of quotes) | Mon | 66.5 | 42.3 | 36% | 31.0% | 38.3% | 18.3% | 0.0 | 1.37 | 1.42 | **1.29** |
| **`3_Others`** | Tue | 60.6 | 42.4 | 30% | **26.5%** | 30.0% | **18.3%** | 0.0 | 1.40 | 1.46 | **1.31** |
| **`3_Others`** | Wed | 61.1 | 48.1 | 21% | **26.7%** | 29.5% | **16.3%** | 1.0 | 1.45 | 1.52 | **1.36** |
| **`3_Others`** | Thu | 67.1 | 54.3 | 19% | 33.1% | 33.9% | 29.4% | 1.0 | 1.49 | 1.56 | **1.43** |
| **`3_Others`** | Fri | 54.1 | 38.2 | 29% | **27.7%** | 33.7% | **13.4%** | 2.0 | 1.50 | 1.54 | **1.39** |

**What Table 2A reveals:**
1. **`D01` trust climbs far faster than `dealer_lr = 0.02`:** By Tuesday median trust at `D01` is `8.0` (+8%), by Wednesday `20.5` (+20.5%), and by Thursday `25.0` (+25% cap). Because `dealer_lr = 0.02` takes +1.3% steps per win and −0.7% per loss, `dealer_adj["D01"]` lags 8–12% behind `D01`'s true trust on Tue–Thu, causing our `D01` normal win rate to jump to **48.6% on Tue, 46.1% on Wed, and 43.1% on Thu** instead of the 35% target!
2. **Global `mult` is dragged upward by `D01` wins, pricing out `3_Others`:** Because `D01` and `Top2-3` have high trust and win 40–49% on Tue–Wed, they push the shared global multiplier `self.mult` up by ~8–10%. That contaminates quotes for `3_Others` (where median trust is `0–1`), pushing `3_Others` win rate down to **26.5% on Tue and 26.7% on Wed** (and **13.4–18.3% on floored quotes**). Decoupling known dealer trust (`1 + 0.01 * trust_count`) from `self.mult` fixes both sides simultaneously!

### Table 2B: Competitor Bracketing by `Dealer Group × Option × Drive Length`
*Shows both `OptWin` (share of quotes where this specific option won), `WOth%` (share of quotes where we won the request via a faster option), and `ReqWin = OptWin + WOth%` (share of quotes where we beat the competitor on the request).*

| Dealer Group | Option | Drive Band | Quot/wk | Flr% | OptWin% | WOth% | ReqWin% | NrmOptW% | NrmReqW% | P/L Won | P/L Lost | Med Typ/List |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **`1_D01`** | `same_day` | `1_<100m` | 67.8 | 7% | 35.9% | 2.8% | 38.7% | 36.1% | 39.1% | 1.56 | 1.70 | 0.80 |
| **`1_D01`** | `same_day` | `2_100-300m` | 26.0 | 8% | 29.3% | 26.9% | **56.2%** | 28.0% | **57.3%** | 1.52 | 1.77 | 0.88 |
| **`1_D01`** | `next_day` | `1_<100m` | 106.0 | 21% | 15.4% | 18.4% | 33.8% | 16.9% | 34.9% | 1.64 | 1.61 | 0.92 |
| **`1_D01`** | `next_day` | `2_100-300m` | 60.7 | 29% | 38.0% | 11.2% | **49.2%** | 42.7% | **53.2%** | 1.60 | 1.72 | 0.97 |
| **`1_D01`** | `next_day` | `3_>300m` | 24.6 | 24% | 40.1% | 6.6% | **46.7%** | 42.7% | **51.3%** | 1.63 | 1.68 | 0.97 |
| **`1_D01`** | `within_3_days` | `1_<100m` | 26.8 | 34% | **1.6%** | 33.3% | 35.0% | **2.5%** | 34.8% | 1.78 | 1.57 | 0.99 |
| **`1_D01`** | `within_3_days` | `2_100-300m` | 12.6 | 50% | **9.9%** | 46.0% | **55.9%** | **17.8%** | **57.4%** | 1.61 | 1.59 | 1.03 |
| **`1_D01`** | `within_3_days` | `3_>300m` | 4.5 | 39% | 36.1% | 15.3% | **51.4%** | **56.8%** | **56.8%** | 1.50 | 1.54 | 1.02 |
| **`2_Top2-3`** | `same_day` | `1_<100m` | 31.1 | 7% | 34.0% | 1.4% | 35.4% | 34.2% | 35.7% | 1.43 | 1.54 | 0.83 |
| **`2_Top2-3`** | `same_day` | `2_100-300m` | 14.6 | 8% | 30.9% | 20.2% | **51.1%** | 28.5% | **50.5%** | 1.45 | 1.56 | 0.87 |
| **`2_Top2-3`** | `next_day` | `1_<100m` | 78.2 | 27% | 17.1% | 11.9% | 29.0% | 18.6% | 28.9% | 1.52 | 1.48 | 0.93 |
| **`2_Top2-3`** | `next_day` | `2_100-300m` | 51.6 | 34% | 32.0% | 9.7% | 41.7% | 35.8% | 45.3% | 1.47 | 1.52 | 0.95 |
| **`2_Top2-3`** | `next_day` | `3_>300m` | 18.4 | 35% | 43.4% | 5.4% | **48.8%** | **50.0%** | **58.3%** | 1.48 | 1.56 | 0.99 |
| **`2_Top2-3`** | `within_3_days` | `1_<100m` | 11.3 | 40% | **2.8%** | 29.3% | 32.0% | **4.6%** | 31.2% | 1.54 | 1.51 | 1.01 |
| **`2_Top2-3`** | `within_3_days` | `2_100-300m` | 6.0 | 59% | 19.8% | 24.0% | 43.8% | 41.0% | 48.7% | 1.54 | 1.61 | 1.04 |
| **`2_Top2-3`** | `within_3_days` | `3_>300m` | 2.7 | 51% | 37.2% | 11.6% | **48.8%** | **76.2%** | **76.2%** | 1.56 | 1.64 | 1.04 |
| **`3_Others`** | `same_day` | `1_<100m` | 66.3 | 7% | 25.2% | 3.4% | 28.6% | **24.9%** | 28.5% | 1.41 | 1.52 | 0.81 |
| **`3_Others`** | `same_day` | `2_100-300m` | 29.4 | 12% | 27.2% | 14.3% | 41.5% | 28.3% | 44.6% | 1.42 | 1.48 | 0.88 |
| **`3_Others`** | `next_day` | `1_<100m` | 148.5 | 26% | 15.9% | 10.0% | 25.9% | **17.9%** | 28.1% | 1.46 | 1.47 | 0.93 |
| **`3_Others`** | `next_day` | `2_100-300m` | 106.8 | 38% | 23.4% | 7.7% | 31.1% | 28.3% | 36.8% | 1.44 | 1.48 | 0.97 |
| **`3_Others`** | `next_day` | `3_>300m` | 35.7 | 45% | 33.5% | 3.2% | 36.6% | 38.1% | 43.8% | 1.47 | 1.52 | 0.99 |
| **`3_Others`** | `within_3_days` | `1_<100m` | 25.9 | 41% | **5.3%** | 22.2% | 27.5% | **7.4%** | 29.5% | 1.48 | 1.49 | 0.99 |
| **`3_Others`** | `within_3_days` | `2_100-300m` | 22.6 | 56% | **11.0%** | 19.1% | 30.1% | **20.6%** | 34.4% | 1.45 | 1.56 | 1.05 |
| **`3_Others`** | `within_3_days` | `3_>300m` | 6.8 | 66% | 16.5% | 18.3% | 34.9% | 43.2% | 43.2% | 1.61 | 1.56 | 1.09 |

### 2C. Where Are We Winning >50% of Quotes vs <25% of Normal Quotes?

1. **Slices winning >50% of quotes (pricing too cheap relative to competitor lane factor, trust, or morning shift):**
   - **Morning after a price-war day (08:00–11:00 across 6 war worlds):** We win **69.2% of all quotes (`137 / 198`)** at median `P/L = 1.37` because `self.mult` stepped down 12 times on the war day before `loss_streak_freeze = 12` engaged, starting the next morning ~15% below the restored competitor price.
   - **13 of 80 world-mornings (08:00–11:00):** Win rate exceeds 50%, averaging **66.2% (`261 / 394` quotes = `16.3` wins/wk)** at median `P/L = 1.42` (e.g., `wa5d0041ba245f34be266` Wed 08–11: `21/21 = 100%` at `1.36×`; `w97ea2b32b71ef8c90316` Wed 08–11: `15/18 = 83.3%` at `1.39×`; `w9a9532e7be8f4171ae76` Thu 08–11: `31/39 = 79.5%` at `1.31×`).
   - **`D01` & `Top2-3` medium/long drives (`100–300m` and `>300m`) on Tue–Fri:**
     - `1_D01 × Tue × same_day × 100-300m`: **72.4% request win** (`66.1%` option win, `4.8 req/wk`) at med won `P/L = 1.46`.
     - `2_Top2-3 × Tue × same_day × 100-300m`: **64.8% request win** (`3.4 req/wk`) at med won `P/L = 1.53`.
     - `2_Top2-3 × Thu × next_day × >300m`: **61.5% request win** (`59.7%` option win, `4.1 req/wk`) at med won `P/L = 1.66`.
     - `1_D01 × Wed × same_day × 100-300m`: **56.9% request win** (`7.2 req/wk`) at med won `P/L = 1.69`.
     - `1_D01 × Fri × same_day × 100-300m`: **56.1% request win** (`2.6 req/wk`) at med won `P/L = 2.09`.
     - `1_D01 × Thu × next_day × >300m`: **54.4% request win** (`52.3%` option win, `4.2 req/wk`) at med won `P/L = 1.73`.
     - `1_D01 × Thu × same_day × 100-300m`: **53.7% request win** (`5.9 req/wk`) at med won `P/L = 1.75`.
     - `1_D01 × Tue × next_day × 100-300m`: **52.5% request win** (`50.9%` option win, `8.7 req/wk`) at med won `P/L = 1.48`.

2. **Slices winning <25% of normal quotes (pricing too high or self-cannibalizing):**
   - **Short drives (`<100m`) and dense-delivery lanes (`d_s30 >= 100`, easy return work):**
     - Across all dealers, **delivery to dense towns (`d_s30 >= 100`, `204.6 quotes/wk`) wins only 24.7% overall (`27.1%` normal)**, whereas **delivery to thin towns (`d_s30 < 30`, `337.4 quotes/wk`) wins 40.1% overall (`43.6%` normal)**!
     - Why? The competitor's price includes a **lane factor** (`docs/GAME.md`: *"harder lanes: little return work, few drivers near the delivery"*). On short `<100m` or dense-delivery (`d_s30 >= 100`) lanes, `typ_fee / list` is low (`0.80–0.86`) and the competitor quotes ~8–12% lower relative to `listPriceCents`. Because our multiplier `self.mult` is lane-blind, our `<100m` normal request win rate is `<25%` across almost every weekday:
       - `2_Top2-3 × Mon × next_day × <100m`: **20.0% normal request win** (`11.6%` option win).
       - `1_D01 × Mon × next_day × <100m`: **20.9% normal request win** (`11.9%` option win).
       - `2_Top2-3 × Tue × next_day × <100m`: **20.9% normal request win** (`14.4%` option win).
       - `3_Others × Wed × next_day × <100m`: **22.2% normal request win** (`13.8%` option win).
       - `3_Others × Tue × same_day × <100m`: **23.0% normal request win** (`19.2%` option win).
       - Across `2_mid_30-99` (`<100m` `next_day`, `50.3 req/wk`) and `3_ring_s55>=30` (`<100m` `next_day`, `96.6 req/wk`), total win rates are just **19% and 23%**, leaving over 110 safe short-haul requests/wk on the table!
   - **Slower options (`next_day` and `within_3_days`) when a faster option is also quoted (`OptWin < 18%`):**
     - For `within_3_days × <100m`, option win rate on normal quotes is **2.5% at `D01`**, **4.6% at `Top2-3`**, and **7.4% at `Others`** — NOT because the competitor beats us (`ReqWin` is `27.5%–35.0%`), but because `same_day` or `next_day` wins the request instead (`WOth% = 22.2%–33.3%`).

### Table 2D: Multi-Option Requests — Which Option Wins and at What `price / list`?

| Quoted Options Combination | Quoted/wk | Total Won/wk (Win%) | Wins by Option (/wk & Share of Won) | Median `P/L` Quoted (`Flr%`) & Won by Option |
|---|---:|---:|---|---|
| `('next_day',)` only | 351.2 | 111.3 (**31.7%**) | `next_day`: 111.3/wk (**100.0%**) | `next_day`: med_q `1.52` (`flr=32%`), med_won `1.51` |
| `('same_day', 'next_day')` | **160.1** | **61.1 (38.2%)** | `same_day`: **45.5/wk (74.4%)**<br>`next_day`: **15.6/wk (25.6%)** | `same_day`: med_q `1.53` (`flr=8%`), med_won `1.44`<br>`next_day`: med_q `1.48` (`flr=21%`), med_won `1.57` |
| `('next_day', 'within_3_days')` | 86.4 | 28.4 (**32.9%**) | `next_day`: **19.1/wk (67.3%)**<br>`within_3_days`: **9.3/wk (32.7%)** | `next_day`: med_q `1.48` (`flr=36%`), med_won `1.41`<br>`within_3_days`: med_q `1.52` (`flr=48%`), med_won `1.55` |
| `('same_day',)` only | 42.2 | 15.1 (**35.7%**) | `same_day`: 15.1/wk (**100.0%**) | `same_day`: med_q `1.58` (`flr=6%`), med_won `1.53` |
| `('same_day', 'next_day', 'within_3_days')` | **32.8** | **14.2 (43.2%)** | `same_day`: **11.1/wk (78.4%)**<br>`next_day`: 1.6/wk (11.0%)<br>`within_3_days`: 1.5/wk (10.6%) | `same_day`: med_q `1.47` (`flr=10%`), med_won `1.44`<br>`next_day`: med_q `1.45` (`flr=27%`), med_won `1.38`<br>`within_3_days`: med_q `1.51` (`flr=39%`), med_won `1.43` |

**Why `same_day` cannibalizes `74.4%–78.4%` of multi-option wins:**
- On `('same_day', 'next_day')` requests, `list(same_day) / list(next_day)` has median **`1.077`**. With `same_day_markup = 0.05`, our unfloored quote ratio `quote(same_day) / quote(next_day)` is **`1.128`** (+12.8%).
- Worse, because both options share the same request `referenceFeeCents`, the euro fee floor `floor = 1.359 × typ_fee` is identical for `same_day` and `next_day`. On **31.5% of our `same_day` wins**, `next_day` is floored while `same_day` is not, compressing `quote(same_day) / quote(next_day)` toward `1.00`!
- Because the dealer values `same_day` speed at ~15–18% over `next_day`, a +5% `same_day_markup` (and a shared euro floor) either leaves **+6–10% pure price on the table on 56.6 `same_day` wins/wk** OR unnecessarily steers medium-drive `100–300m` orders into `same_day` (where late rate is `4.7%` and margin is `€46.7/ord`) instead of `next_day` (where late rate is `1.9%` and margin is `€51.9/ord`).

---

## 3. Top 4 Ranked Euro-Per-Week Leaks & Concrete Recommendations

### Leak #1: Underpriced Won Quotes & Mispriced Competitor Factors (Clocks, `D01` Trust, Floor, Lane & Option Markup) — **€1,800 to €2,500 / wk**
This is the single largest gap against the €14.4k–€16k leaders. It consists of five additive pricing distortions measured above:
1. **Two Clocks — Morning-after-war underpricing & price-war freeze (`+€600–€900/wk`):**
   - On the 6 war-day worlds, the morning after (08:00–11:00) wins **69.2% (`137/198`)** at `1.37× list` (~15% below the restored competitor level, losing ~€18/order on ~23 wins/world). Across all 16 worlds, 13 of 80 mornings have `>50%` win rate (`66.2%` on `394` quotes).
   - Meanwhile, on price-war days (`loss_streak_freeze = 12`), freezing `self.mult` throws away ~15–20 profitable `D01`/`Top2-3` orders/world where high dealer trust (+15% to +25%) still beats the −20% war competitor above our true `0.90× typ_fee` cost.
2. **Exact Dealer Trust Decoupling & Higher Cap (`+€450–€650/wk`):**
   - `D01` accounts for **209.9 quotes/wk (31.2%)** and **84.5 wins/wk (36.7%)**. Because `dealer_lr = 0.02` lags behind exact trust (`+1%` per on-time order up to 25), we win **45.6% on Tue and 45.1% on Wed at `D01`**, while `self.mult` is dragged up and depresses `3_Others` win rate to **26.5%**.
   - **Fix:** Track exact `trust_count[dealer]` from on-time deliveries, apply `1 + trust_gain * (trust_count / 100.0)` explicitly, keep `self.mult` for the market level, and raise `dealer_adj_max` from `1.30` to `1.50` / `price_mult_max` from `1.80` to `2.20`.
3. **Lowering the Inflated Quote Floor `expected_fee_mult: 1.25 → 1.02` (`+€350–€500/wk`):**
   - `expected_fee_mult = 1.25` with `min_margin_frac = 0.08` sets `floor = 1.359 × typ_fee`, which floors **202.8 quotes/wk (30.2%)** even though our actual median driver fee is **`0.904× typ_fee`** (mean `1.028×`). On `3_Others`, floored quotes win only **13.4–18.3%** vs **30.0–38.3%** for normal quotes. Setting `expected_fee_mult = 1.02` (floor `= 1.11× typ_fee`) restores normal pricing on ~140 safe quotes/wk.
4. **Lane / Delivery-Supply & Drive-Length Factor (`+€250–€400/wk`):**
   - We win only **24.7%** when delivering to dense towns (`d_s30 >= 100`) and **19–23%** on `<100m` `next_day` in mid/ring towns, vs **40.1%** when delivering to thin towns (`d_s30 < 30`) and **45–58%** on `>300m` drives. Adding a small lane multiplier based on `typ_fee / list_price` (or `delivery_s30 < 30` markup `+0.05`, `<100m` discount `−0.05`) captures higher margin on hard lanes and wins +15–20 safe short/return orders/wk.
5. **Multi-Option Markup `same_day_markup: 0.05 → 0.12` (`+€200–€350/wk`):**
   - Raises revenue on the `56.6/wk` multi-option `same_day` wins and steers marginal `100–300m` requests into safer, higher-margin `next_day`.

---

### Leak #2: Driver Fees Paid Above `0.85×` Typical (`rising` Ramp & Overnight Climb) — **€1,100 to €1,600 / wk**
Out of **€17,286.92/wk** in total driver fees across `230.1` won orders/wk (`mean = 1.028× typ_fee`, `median = 0.904× typ_fee`), exactly **€3,216/wk** is paid above the `0.85×` opening floor:

| Booking Regime | Orders / wk (% of Won) | Med `Fee/Typ` | Mean `Fee/Typ` | Total Fee €/wk | Excess > `0.85×` €/wk |
|---|---:|---:|---:|---:|---:|
| **1. Unwarned, booked ≤ 5 min** (at `fee_open = 0.85`) | 60.2 / wk (26.2%) | 0.85 | 0.85 | €3,395 / wk | **€8 / wk** |
| **2. Unwarned, booked > 5 min on post day** (`rising` ramp) | 104.2 / wk (45.3%) | 0.90 | 0.96 | €7,040 / wk | **€751 / wk** |
| **3. Unwarned, booked on later day than post** (overnight climb) | 57.4 / wk (24.9%) | **1.17** | **1.18** | €5,270 / wk | **€1,477 / wk** |
| **4. Warned orders** (`deadline_close` steep ramp `1.80–3.00×`) | 7.9 / wk (3.4%) | **1.80** | **2.07** | €1,581 / wk | **€980 / wk** |

**Where the recoverable €1,100–€1,600/wk sits:**
- **Overnight / Next-Day Ramp (`€1,477/wk` excess on `57.4` orders/wk):** Because `Desk.rising()` interpolates linearly across all daytime half-hours from `self.now` to `lastPickupAt - 3h` (`fee_warn = 1.60`), a `next_day` order won at 11:00 on Monday has already climbed from `0.85×` to `~1.17×` by Tuesday morning at 08:00 when next-day drivers look at the app! Holding the fee flat at `fee_open` (`0.85×–0.90×`) until the morning of the deadline day (e.g., `10:00` on deadline day, or a two-stage ramp that stays flat for the first 60% of daytime slack) saves **~€700–€1,000/wk**.
- **Dense-Pool Opening Floor (`fee_open: 0.85 → 0.78–0.80` in `s30 >= 100`):** `94.8` orders/wk (`41.2%` of all orders) book within 30 minutes at `0.85–0.88×`. Lowering `fee_open` by `0.05×` in dense pools (`s30 >= 100`) saves **€319/wk** on fast bookings alone (`-0.05x` column in Section 5 of `margin_xray.py`).

---

### Leak #3: Safe Declined Requests We Could Serve (`361.9` Declined Requests / wk) — **€900 to €1,300 / wk**
Champion v2 declines **361.9 requests/wk (35.0% of the market)**. Decomposing those declines shows three safe, high-margin sub-buckets that do not require taking risky deep-thin `same_day` orders:

| Declined Sub-Bucket | Declined Req/wk | Why It Is Currently Declined | Safe Serve Strategy & Expected Yield |
|---|---:|---|---|
| **A1. Extended Ring (`s55` 20–29 or `s70 >= 30`, slow option offered, `<300m` drive)** — *Lahti (`27.3/wk`, `s70=44.9`), Kouvola (`8.4/wk`, `s70=28.3`), Oulu/Jyväskylä/Kuopio (`s30=14–29`)* | **53.2 / wk** (`37.8/wk` at `s55 20–29`, `15.4/wk` at `s70 >= 30`) | `gate_radius_km = 55` and `min_supply = 30` miss Lahti (62 km from Vantaa, `s70 = 44.9`) and worlds where Oulu/Jyväskylä/Kuopio dip to `14–29` drivers. | Allow `next_day` / `within_3_days` (`<=300m` drive) when `s70 >= 30` or `s55 >= 15`. At 35% win rate = **+18.6 wins/wk × €38/ord = +€700/wk**. |
| **A2. Thin-to-Capital Return Lanes (`s70 < 30` pickup → `d_s30 >= 100` Capital delivery, slow option, `<300m` drive)** | **37.7 / wk** (`7.2/wk` `<100m`, `30.5/wk` `100–300m`) | Pickup town has `<30` drivers, even though delivery ends in the Capital pool (`327–444` drivers) where our outbound drivers need return work. | Gate in slow options (`next_day`/`within_3_days`) when `delivery_s30 >= 100` (especially when an outbound driver of ours is delivering nearby). At 30% win rate = **+11.3 wins/wk × €35/ord = +€395/wk**. |
| **A3. Mid/Ring `same_day`-only short drives (`<100m` with ample slack)** | **25.0 / wk** (`18.4/wk` in `3_ring`, `6.6/wk` in `2_mid`) | Request only offered `same_day`; blocked by `far_options="slow"` or `same_day_min_supply=100`. | Keep blocked when on-time share is tight, or allow only when `s30 >= 50`, `drive < 90m`, and `slack >= 300m` (+3–4 wins/wk = **+€100/wk**). |

---

### Leak #4: Late Refunds (`€387/wk`), Failed Visits (`€165/wk`), and the Safety Tax — **€500 to €800 / wk**
Across the 16 worlds, we average **7.38 late/undelivered orders/wk (3.20% of won)** costing **€386.92/wk** in direct refunds/penalties plus **€165.44/wk** in failed visits (`3.75/wk`) and **€92.86/wk** in release/waiting fees (**€645.22/wk** direct ledger deductions, plus the D01 trust halving penalty and the safety tax of keeping `price_target_win = 0.35`).

Decomposing all **118 late orders (`7.38/wk`)** by root cause reveals a **major code bug in `stops_for` and `Desk.price`**:

| Root Cause of Late Order | Late Orders / wk (% of All Late) | Direct Refund €/wk | Mechanism & Fix |
|---|---:|---:|---|
| **1. Unbooked at `deadline_close` (`>300m` `next_day` in `1_dense`, `2_mid`, `3_ring` = `1.07/wk`; `same_day` = `0.69/wk`; others = `0.80/wk`)** | **2.56 / wk (34.7%)** | **€191.9 / wk** | Long drives (`>300m` `next_day` is **9.4% late** in `1_dense`, **7.7% late** in `2_mid` and `3_ring`, costing **€262/wk** in refunds!). **Fix:** Raise `slack_per_drive` or add a `>300m` price markup / early staffing alarm at 10:00 on deadline day (`alarm_after_min`). |
| **2. Trade-ins (`len(legs)==2`) & Narrow Private-Address Windows (`pickup.window.to < deadline` or `delivery.window.to < deadline`)** | **1.94 / wk (26.3%)** (`0.75/wk` 2-leg trade-ins = **50.0% late!**; `1.19/wk` 1-leg private windows = **6.5% late**) | **€86.0 / wk** | **Bug uncovered:** (a) On 2-leg trade-ins (`1.50 won/wk`), `leg[0]` delivers to a private customer with a 1-hour window `[W, W+60]`, and `leg[1]` picks up the trade-in in `[W, W+60]`. `stops_for()` overwrites `delivery.window.to` with `order.deadline` (20:00), stripping `leg[0]`'s 1-hour appointment window! **50.0% (12/24) of won trade-ins end up late!** (b) On 1-leg `pickup.privateAddress=true`, the seller's pickup window is only 3 hours wide (`pickup.window.to << option.deadline`), but `Desk.price()` computes slack from `option.deadline` instead of `pickup.window.to - ready`. **Fix:** Check `pickup.window.to - ready >= min_pickup_slack` in `Desk.price()`, preserve `min(delivery.window.to, order.deadline)` in `stops_for()`, or decline 2-leg trade-ins. Eliminates **~1.5 late orders/wk (+0.65% on-time share!)**. |
| **3. Driver Late Without Warning (Normal 1-leg dealer-to-dealer)** | **1.44 / wk (19.5%)** | **€53.0 / wk** | Booked driver arrives 1–60 minutes after deadline (`mins_late`: `1, 5, 10, 12, 22, 24, 28, 34, 58 min...`). **Fix:** Tighten delivery stop window by `delivery_buffer_min = 30–45` min (`Idea 9`) and release `driver_late` when projected arrival exceeds deadline (`Idea 13`). |
| **4. Unparsed Dealer Notes (Tighter deadline or delivery closing hours)** | **1.31 / wk (17.8%)** | **€44.5 / wk** (+ **€165.4/wk** in `not_ready` / `no_plates` failed visits) | Notes with English/Swedish/Finnish closing hours or pickup readiness that `window_from_note` misses. **Fix:** Expand `notes.py` regexes (`Idea 11`) and apply `window_from_note` to `delivery` window during `Desk.price()` slack check. |
| **5. Driver Dropped Gig (`gig_dropped`)** | **0.19 / wk (2.5%)** | **€9.3 / wk** | Low impact once re-posted promptly. |

---

## Summary Table of Ranked Leaks & Action Plan

| Rank | Leak Category | Estimated Value (€/wk) | Concrete `Params` / Code Changes |
|---|---|---:|---|
| **1** | **Competitor Pricing, `D01` Trust, Two Clocks, Floor & Lane/Option Factors** | **+€1,800 – €2,500 / wk** | 1. Decouple exact `trust_count` (`+1%/order` up to 25) from `self.mult`; raise `dealer_adj_max=1.50`, `price_mult_max=2.20` (`Idea 4`).<br>2. Two-clock tracker: reset daily shift each morning so price-war days don't underprice the next morning (currently `69.2%` win rate at `1.37×`) (`Idea 3`).<br>3. Lower `expected_fee_mult: 1.25 → 1.02` so the floor (`1.359× typ_fee`) stops pricing out 30% of quotes.<br>4. Add lane/drive adjustment (`<100m` / `d_s30>=100` `−5%`, `>300m` / `d_s30<30` `+6%`) and raise `same_day_markup: 0.05 → 0.12`. |
| **2** | **Driver Fee Schedule (`rising` Overnight Climb & Dense Opening Floor)** | **+€1,100 – €1,600 / wk** | 1. Hold `next_day` / `within_3_days` fee flat at `fee_open` overnight and through the first half of slack instead of ramping linearly to `1.17×` by the next morning (`€1,477/wk` excess) (`Idea 6`).<br>2. Lower `fee_open: 0.85 → 0.78–0.80` for dense pickups (`s30 >= 100`). |
| **3** | **Safe Declined Requests (70 km Slow Ring & Return-to-Capital Lanes)** | **+€900 – €1,300 / wk** | 1. Expand slow-option ring gate (`next_day`/`within_3_days`, `drive <= 300m`) to `s70 >= 30` (captures Lahti `27.3/wk` and Kouvola `8.4/wk`) or `s55 >= 18` (`+53 req/wk`).<br>2. Allow slow options on thin pickups (`s55 < 30`) when `delivery_s30 >= 100` (`+37.7 req/wk` returning to Capital). |
| **4** | **Late Refunds (`€387/wk`), Trade-In/Private Window Bug & Failed Visits (`€165/wk`)** | **+€500 – €800 / wk** *(+0.8% on-time)* | 1. Fix `stops_for()` so `delivery_base["to"] = min(delivery["window"]["to"], order["deadline"])` (fixes the **50.0% late rate on 2-leg trade-ins**), or decline 2-leg trade-ins (`0.75 late/wk`).<br>2. Check `pickup["window"]["to"] - ready` slack in `Desk.price()` for `privateAddress` pickups (`1.19 late/wk`).<br>3. Add `delivery_buffer_min = 35` (`Idea 9`) and check `delivery` note windows in `Desk.price()` (`Idea 11`). |

## Verdict
**research complete** — Together, the four leaks account for **+€4,300 to +€6,200/wk**, fully explaining the gap between champion v2 (`€8,990/wk` dev, `~€10.8k` round 4) and the `€14.4k–€16.0k` leaderboard leaders.
