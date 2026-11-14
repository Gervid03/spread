# stack-trust-notes-slack: Combine dealer trust investment, 100%-truth note reader, and fine drive-proportional slack

- **Agent / branch / commit:** gemini · exp/gemini-n14-01394-stack-trust-notes-slack · be93410
- **Date:** 2026-11-14 02:05
- **Idea from:** IDEAS.md items #2 (`07-notes`), #4 (`02-trust-v2`), and `17 n-slack-fine`

## Why we tried it
Three orthogonal mechanisms each improved both margin and on-time safety on champion v2 by fixing independent leaks:
1. **Dealer trust investment (`origin/exp/gemini-n14-02-trust-v2`, `trust_invest=0.05`):** Each on-time order for a dealer raises the price that dealer accepts by +1% (up to +25%), whereas a late order halves that count. Investing a 5% discount on safe, note-free requests (`supply >= 100, slack >= 360` min) for the top 3 dealers on Mon–Wed yielded `Δmargin €+303.46 ± 134.52` (`t = 2.26`, 11/16 better, min on-time `94.7%` SAFE).
2. **100%-truth note reader + note-deadline slack (`origin/exp/gemini-n14-07-notes`, `notes_v2=True, note_unsure="decline"`):** Achieved 100% precision/recall on all 177 ground-truth note fields across 6 revealed worlds, cutting `visit_failed` on dev by 91.8% (from 73 to 6) and lifting mean on-time by `+0.44%` to `97.19%` (`Δmargin €+83.07 ± 205.80`, 10/16 better, min on-time `94.06%` SAFE).
3. **Fine drive-proportional slack (`17 n-slack-fine`, `min_slack_min=140, slack_per_drive=0.75`):** Admits short-drive orders (`drive < 160` min) while requiring more slack on long drives (`drive > 160` min), yielding `Δmargin €+235 ± 131` (`t = 1.8`, 10/16 better, min on-time `93.8%` SAFE).

Because `notes_v2` makes `ready` and `deadline` exact when notes shift ready days or tighten delivery closing hours, combining `notes_v2` with `min_slack_min=140, slack_per_drive=0.75` and `trust_invest=0.05` should compound cleanly—and provide enough on-time buffer (`+1.08%` mean, `95.3%` min) to safely give back the safety tax (`price_target_win=0.40, min_supply=20, same_day_min_supply=50`).

## What changed
Merged `origin/exp/gemini-n14-02-trust-v2` and `origin/exp/gemini-n14-07-notes` into `exp/gemini-n14-01394-stack-trust-notes-slack`:
- `src/spread_lab/notes.py`: `parse_note_v2`, `shift_business_days`, `window_from_note(..., v2=...)`, `note_flags(..., v2=...)`.
- `src/spread_lab/policy.py`: Combined `Params` fields (`notes_v2: bool = False`, `note_unsure: str = "quote"`, `trust_gain: float = 0.0`, `trust_invest: float = 0.0`, `trust_guard: bool = False`) and `Desk` logic in `__init__`, `handle`, `tick`, `quote`, `price`, `post`, and `rejoin`. All defaults reproduce champion v2 (`Δmargin €+0.00 ± 0.00` on smoke).

Run with:
- Conservative stack (Run B):
  `uv run lab eval -s trust_invest=0.05 -s notes_v2=True -s note_unsure=decline -s min_slack_min=140 -s slack_per_drive=0.75 --name stack-trust-notes-slack140-dev`
- Taxback stack (Run C):
  `uv run lab eval -s trust_invest=0.05 -s notes_v2=True -s note_unsure=decline -s min_slack_min=140 -s slack_per_drive=0.75 -s same_day_min_supply=50 -s price_target_win=0.40 -s min_supply=20 --name stack-trust-notes-taxback-dev`

## Results (level 8, vs champion v2, paired)
| set | run folder | mean margin | Δmargin ± SE | t | better/worse | on-time min | mean on-time (Δ) | SAFE |
|---|---|---|---|---|---|---|---|---|
| smoke (no-op) | `runs/20261114-015442-trust-notes-noop` | €9,662.25 | €+0.00 ± 0.00 | — | 0/0 | 95.5% | 96.7% (+0.00%) | yes |
| smoke (140/0.75) | `runs/20261114-015732-stack-smoke-140` | €10,060.98 | €+398.73 ± 478.25 | 0.83 | 3/1 | 96.4% | 97.8% (+1.09%) | yes |
| smoke (150/0.75 + sd50) | `runs/20261114-015924-stack-smoke-150-sd50` | €10,549.04 | €+886.79 ± 586.01 | 1.51 | 3/1 | 96.4% | 97.7% (+1.03%) | yes |
| dev Run A (`trust+notes`) | `runs/20261114-020044-stack-trust-notes-dev` | €9,208.09 | €+217.79 ± 157.88 | 1.38 | 13/3 | 95.3% | 97.4% (+0.66%) | yes |
| **dev Run B (`+slack 140/0.75`)** | `runs/20261114-020214-stack-trust-notes-slack140-dev` | **€9,478.39** | **€+488.08 ± 182.33** | **2.68** | **14/2** | **95.3%** | **97.8% (+1.08%)** | **yes** |
| **dev Run C (`+taxback`)** | `runs/20261114-020419-stack-trust-notes-taxback-dev` | **€9,626.63** | **€+636.33 ± 269.13** | **2.36** | **12/4** | **93.1%** | **96.0% (-0.71%)** | **yes** |

### Progressive paired comparisons on dev (16 seeds)
- **Run A vs Champion v2:** `Δmargin €+217.79 ± 157.88` (`t = 1.38`, **13/16 better**), `Δon-time +0.66%` (`95.3%` min vs `94.4%`).
- **Run B vs Run A (`uv run lab compare`):** Adding `min_slack_min=140, slack_per_drive=0.75` onto `trust+notes` adds **`€+270.29 ± 110.02` (`t = 2.46`)** and **`+0.42%` on-time**, bringing Run B to **`Δmargin €+488.08 ± 182.33` (`t = 2.68`, 14/16 seeds better)** and **`97.8%` mean on-time (`+1.08%`, `95.3%` min)**. Worse-case seed margin rises by **`+€732.74`** (`€6,750.04` vs `€6,017.30` on champion).
- **Run C vs Champion v2:** Spending part of Run B's `+1.08%` on-time buffer on `same_day_min_supply=50, price_target_win=0.40, min_supply=20` reaches **`€9,626.63` mean margin (`Δmargin €+636.33 ± 269.13`, `t = 2.36`, 12/16 seeds better)** and lifts the worst-seed margin by **`+€1,422.65` to `€7,439.95`**, while keeping worst-seed on-time at **`93.1%` (`dev-07`, SAFE)**—whereas `price_target_win=0.40` without `notes_v2 + slack 140/0.75` failed safety at `91.5%`.

### Stats counters and ledger breakdown (mean per world across 16 dev seeds, totals in parens)
| Metric / Counter | Champion v2 | Run A (`trust+notes`) | Run B (`+slack 140/0.75`) | Run C (`+taxback`) |
|---|---:|---:|---:|---:|
| `won` (mean / total) | 230.12 (3,682) | 231.31 (3,701) | 231.62 (3,706) | 276.06 (4,417) |
| `won_same_day` | 71.69 (1,147) | 72.19 (1,155) | 72.62 (1,162) | 100.56 (1,609) |
| `won_next_day` | 147.62 (2,362) | 148.12 (2,370) | 147.69 (2,363) | 163.75 (2,620) |
| `won_within_3_days` | 10.81 (173) | 11.00 (176) | 11.31 (181) | 11.75 (188) |
| `notes_read` (mean / total) | 0.00 (0) | 166.12 (2,658) | 166.12 (2,658) | 166.12 (2,658) |
| `notes_unsure` (mean / total) | 0.00 (0) | 0.88 (14) | 0.88 (14) | 0.88 (14) |
| `visit_failed` (mean / total) | 4.56 (73) | 0.50 (8) | **0.38 (6)** | **0.25 (4)** |
| `visit_failed_not_ready` | 3.50 (56) | **0.00 (0)** | **0.00 (0)** | **0.00 (0)** |
| `visit_failed_no_plates` | 0.94 (15) | **0.00 (0)** | **0.00 (0)** | **0.00 (0)** |
| `visit_failed_closed` | 0.12 (2) | 0.50 (8) | 0.38 (6) | 0.25 (4) |
| `dropped_slack` (mean / total) | 24.81 (397) | 29.06 (465) | 26.44 (423) | 32.69 (523) |
| `deadline_close` (mean / total) | 12.06 (193) | 11.44 (183) | **10.06 (161)** | 21.31 (341) |
| `gig_expired` (mean / total) | 7.56 (121) | 5.44 (87) | **4.69 (75)** | 10.81 (173) |
| `no_show` (mean / total) | 0.69 (11) | 0.62 (10) | **0.38 (6)** | 0.75 (12) |
| `top_dealer_trust_d0..d4` (mean) | — | 4.1 / 14.9 / 24.1 / 22.6 / 23.1 | 4.1 / 15.0 / 23.4 / 22.5 / 22.6 | 5.2 / 18.8 / 22.2 / 22.9 / 24.7 |
| Ledger `revenue` (€/world) | +26,922.43 | +27,083.22 | +27,172.62 | +31,230.20 |
| Ledger `driver_fee` (€/world) | -17,286.92 | -17,386.69 | -17,287.23 | -20,922.60 |
| Ledger `late_refund` (€/world) | -376.20 | -377.43 | **-298.42** | -592.73 |
| Ledger `failed_visit` (€/world) | -165.44 | -34.09 | **-30.02** | **-10.33** |
| Ledger `waiting` (€/world) | -39.38 | -23.17 | **-21.98** | -24.48 |

## Verdict
**adopt** — Both Run B (`trust_invest=0.05, notes_v2=True, note_unsure="decline", min_slack_min=140, slack_per_drive=0.75`: **Δmargin €+488.08 ± 182.33, t=2.68, 14/16 better, 95.3% min / 97.8% mean on-time SAFE**) and Run C (`+ same_day_min_supply=50, price_target_win=0.40, min_supply=20`: **Δmargin €+636.33 ± 269.13, t=2.36, 12/16 better, 93.1% min on-time SAFE**) significantly beat champion v2 on dev.
