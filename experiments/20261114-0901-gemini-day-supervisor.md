# day-supervisor: Evening LLM and formula supervisors that set tomorrow's intake and fee dials

- **Agent / branch / commit:** gemini · `exp/gemini-d14-04-day-supervisor` · `308d8af`
- **Date:** 2026-11-14 09:01 UTC
- **Idea from:** `experiments/prompts/carbon/c5-day-supervisor.md` / `experiments/prompts/day/04-day-supervisor.md` (c5, the user's evening supervisor idea for the jury's "creative" criterion)

## Why we tried it
In the live final, each price request has only 4.5 real seconds to answer (`15` world minutes), making per-request LLM calls too slow and brittle. However, a human head dispatcher does not re-invent pricing on every car: they review the desk's books each evening — pool and option win rates, driver drops, deadline warnings, overnight unbooked backlog, dealer trust, and projected on-time share — and adjust tomorrow's intake and opening-fee dials within safe guardrails so the desk adapts to worlds unlike our practice set (severe driver shortage, flu/snow drop spikes, regional competitor outages, or competitor price wars).

Running a deterministic `"rule"` formula arm beside an `"llm"` arm (`gemini-4-argon` at `temperature=0`) on the exact same Level-8 weeks directly answers the jury's core question — *"with and without, on the same weeks"* — and isolates whether multi-signal LLM reasoning improves tail safety or margin relative to both fixed dials (the champion) and a 2-variable threshold rule.

## What changed
Implemented `src/spread_lab/supervisor.py` and wired it into `src/spread_lab/policy.py` behind neutral defaults (`supervisor: str = ""`, `sup_low_backlog: int = 8`, `sup_high_backlog: int = 18`) that leave the champion untouched (`Δmargin €+0.00 ± 0.00` on all 4 smoke seeds):

- **Evening day-summary JSON (20:00 world time on Mon–Thu, `day` in `0..3`):** records `requests`, `quotes`, `wins`, `win_rate`, and `normal_win_rate`, broken down `by_pool` (`capital`: Helsinki/Espoo/Vantaa; `ring`: `< min_supply` within 30 km; `other`: regional hubs) and `by_option` (`same_day`, `next_day`, `within_3_days`), plus `late_orders_today`, `late_or_lost_week`, `warnings_today`/`warnings_week`, `drops_today`/`drops_week`, `unbooked_orders_now` (active unstaffed orders before `lastPickupAt`), `unbooked_urgent_now`, `unbooked_due_tomorrow`, `week_won_orders`, `projected_on_time`, `top_5_dealers_trust`, and today's `dials` (`price_target_win`, `min_supply`, `fee_open`, `price_mult`).
- **`supervisor="llm"`:** sends the day JSON with a 10-line system prompt (rules, dial meanings/limits, Level-8 shocks, `"Answer ONLY JSON"`) to `gemini-4-argon` via standard-library `urllib.request` (`x-goog-api-key` header so the key never enters URLs or exception strings, `temperature=0`, `timeout=20s`). Clamps answers to `price_target_win` `0.35–0.45`, `min_supply` `18–30`, `fee_open` `0.75–1.00`. On any HTTP error, timeout, or invalid JSON, keeps today's dials and increments `sup_fallbacks`.
- **`supervisor="rule"`:** formula arm over the same summary: loosens one step (`price_target_win + 0.02`, `min_supply - 2`) when `projected_on_time >= 0.96` and `unbooked_orders_now <= sup_low_backlog` (`8`); tightens one step (`price_target_win - 0.02`, `min_supply + 2`) when `projected_on_time <= 0.93` or `unbooked_orders_now >= sup_high_backlog` (`18`); else keeps today's dials. (An initial uncalibrated pass `rule-v1` with `low=5, high=12` plus `+0.05` `fee_open` on tighten was also measured; evening traces showed `7–14` active unbooked orders is normal at 20:00 before 23:00 notifications close.)
- **Deterministic replay & live-mode non-blocking thread:** caches valid LLM answers atomically in `runs/supervisor/<world seed>-<day>.json` and reuses them on reruns. In live mode (`lab final`), spawns a daemon thread so quoting never blocks and applies the clamped dials on the next `tick()` once answered; `rejoin()` rebuilds daily counters from history and restores completed evenings' dials (`--restart-at 3600` verified on `dev-01`: `€7,967.60`, `96.4%` on-time, `ranked=True`). *(Note for lead: if ever promoted via `scripts/promote.sh`, add `supervisor\.py` to the `allow=` regex on line 39 of `scripts/promote.sh`.)*
- **Counters in `desk.stats`:** `sup_calls`, `sup_api_calls`, `sup_cache_hits`, `sup_answers_used`, `sup_fallbacks`, `sup_loosened`, `sup_tightened`, `sup_kept`, and per-evening `sup_win_d0..3`, `sup_supply_d0..3`, `sup_fee_d0..3`, `sup_proj_ot_d0..3`, `sup_unbooked_d0..3`.

Run commands:
```sh
uv run lab eval --seeds-from smoke --name day-supervisor-noop
uv run lab eval -s supervisor=rule --seeds dev-01,dev-02,dev-03,dev-04,dev-05,dev-06,dev-07,dev-08 --name day-supervisor-rule-v2-8dev
uv run lab eval -s supervisor=llm  --seeds dev-01,dev-02,dev-03,dev-04,dev-05,dev-06,dev-07,dev-08 --name day-supervisor-llm-8dev
uv run lab eval -s supervisor=llm  --name day-supervisor-llm-dev
```

## Results: Worst world first, then margin against the champion

### 1. Worst-world safety & tail comparison
| Set & arm | Run folder | Worst on-time | Worlds < 92% | Ranked | Worst margin | SAFE |
|---|---|---:|---:|---:|---:|---|
| `dev-01..08` · Champion (fixed dials) | `champion/results/dev-L8.jsonl` | **94.38%** (`dev-01`) | 0 / 8 | 8 / 8 | €7,487.67 (`dev-01`) | yes |
| `dev-01..08` · `rule` v1 (`low=5, high=12, +fee`) | `runs/20261114-084806-day-supervisor-rule-8dev` | **94.76%** (`dev-01`) | 0 / 8 | 8 / 8 | €7,185.47 (`dev-05`) | yes |
| `dev-01..08` · `rule` v2 (`low=8, high=18`) | `runs/20261114-085119-day-supervisor-rule-v2-8dev` | **94.03%** (`dev-07`) | 0 / 8 | 8 / 8 | €7,697.63 (`dev-01`) | yes |
| **`dev-01..08` · `llm` (`gemini-4-argon`)** | `runs/20261114-085341-day-supervisor-llm-8dev` | **95.09%** (`dev-05`) | **0 / 8** | **8 / 8** | **€7,862.58** (`dev-01`) | **yes** |
| `dev` (all 16) · Champion (fixed dials) | `champion/results/dev-L8.jsonl` | **94.33%** (`dev-13`) | 0 / 16 | 16 / 16 | €7,487.67 (`dev-01`) | yes |
| **`dev` (all 16) · `llm` (`gemini-4-argon`)** | `runs/20261114-085603-day-supervisor-llm-dev` | **94.24%** (`dev-13`) | **0 / 16** | **16 / 16** | **€7,862.58** (`dev-01`) | **yes** |

On the 8-seed screen (`dev-01..08`), `"llm"` lifted both worst-world on-time (`94.38% -> 95.09%`, with `dev-01` rising from `94.38%` to `95.29%`) and worst-world margin (`€7,487.67 -> €7,862.58`, **`+€374.91`** on `dev-01`), with **0 worlds under 92%** (and 0 under 95%). Across all 16 dev worlds, `"llm"` remained **16/16 SAFE** (`0` worlds under 92%, worst on-time `94.24%` vs `94.33%` on `dev-13`, worst margin **`€7,862.58` vs `€7,487.67`**, `+€374.91`).

### 2. Paired margin & volume comparison (`summary.json` numbers)
| Set & arm | Run folder | Mean margin | Median margin | Mean won | Δmargin ± SE (vs champion) | t | Better / worse | Δon-time | SAFE |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| smoke (4) · `noop` (`supervisor=""`) | `runs/20261114-084634-day-supervisor-noop` | €10,816.98 | €11,134.03 | 283.2 | €+0.00 ± 0.00 | 0.00 | 0 / 0 | +0.00% | yes |
| 8 dev · `rule` v1 (`low=5, high=12`) | `runs/20261114-084806-day-supervisor-rule-8dev` | €11,000.57 | €11,237.08 | 284.9 | €-119.48 ± 172.63 | -0.69 | 3 / 4 | +0.27% | yes |
| 8 dev · `rule` v2 (`low=8, high=18`) | `runs/20261114-085119-day-supervisor-rule-v2-8dev` | €11,084.53 | €11,125.92 | 295.2 | €-35.51 ± 67.96 | -0.52 | 3 / 4 | -0.36% | yes |
| **8 dev · `llm` (`gemini-4-argon`)** | `runs/20261114-085341-day-supervisor-llm-8dev` | **€11,154.90** | €11,097.34 | 289.6 | **€+34.85 ± 100.42** | **+0.35** | **4 / 4** | **+0.06%** | **yes** |
| **16 dev · `llm` (`gemini-4-argon`)** | `runs/20261114-085603-day-supervisor-llm-dev` | **€10,791.83** | €10,469.25 | 281.2 | **€-93.05 ± 116.71** | **-0.80** | **7 / 9** | **-0.06%** | **yes** |

Direct paired comparison of **`llm` vs `rule` v2** on the same 8 dev worlds (`uv run lab compare`):
- **`llm` beat `rule` v2 by `€+70.37 ± 109.65` (`t = +0.64`, 4 better / 4 worse)** with **`+0.41pp` higher mean on-time (`96.70%` vs `96.29%`)** and **`+1.06pp` higher worst-world on-time (`95.09%` vs `94.03%`)**.

### 3. Telemetry counters & operational reliability
- **`llm-8dev` (`dev-01..08`):** `sup_calls = 32`, `sup_api_calls = 32`, `sup_cache_hits = 0`, `sup_answers_used = 32`, `sup_fallbacks = 0` (`11` loosened, `12` tightened, `9` kept).
- **`llm-16dev` (`dev-01..16`):** `sup_calls = 64`, `sup_api_calls = 32` (`dev-09..16`), `sup_cache_hits = 32` (`dev-01..08` replayed from `runs/supervisor/<seed>-<day>.json`, reproducing all 8 worlds **to the exact cent** in `9–14s`), `sup_answers_used = 62`, `sup_fallbacks = 2` (`dev-10 Thu` and `dev-12 Mon` hit the 20s timeout, cleanly kept today's dials, and finished at `+€496.55` and `+€293.69` vs champion).

## How `"llm"` differed from `"rule"` (and when)
Across the 32 paired evenings on `dev-01..08`, `"llm"` and `"rule"` v2 moved in the **same direction on 16 evenings** and **diverged on 16 evenings** across four clear structural patterns:

1. **Competitor price-war recognition (`dev-03 Mon`, `dev-05 Tue`, `dev-06 Wed`, plus `dev-10 Wed`, `dev-13 Mon`, `dev-14 Mon`, `dev-16 Mon`):**
   - On `dev-05 Tue`, the competitor launched a price war (`win_rate = 0.153`) alongside `12` driver drops. Because we won very few orders, `unbooked_orders_now` dropped to `7` (`<= 8`). `"rule"` mistook that low backlog for spare capacity and loosened to `(0.42, 20)` and then `(0.44, 18)` on Wednesday, losing `€-288.88` vs champion on `dev-05`.
   - `"llm"` read `win_rate = 0.153` and `drops_today = 12` together, held `(0.40, 22, 0.85)`, and finished `+€40.27` ahead of the champion (`+€329.15` ahead of `"rule"`).
2. **Mean-reversion after transient shocks vs `"rule"`'s hysteresis ratchet (`dev-01 Thu`, `dev-06 Wed`, `dev-07 Tue & Thu`):**
   - `"rule"` only acts at the outer thresholds (`>= 0.96 & <= 8` or `<= 0.93 | >= 18`); whenever the next evening returns to the normal middle band (`unbooked` `9–17`), `"rule"` stays permanently displaced from `(0.40, 22, 0.85)` (e.g. staying at `(0.44, 18)` on `dev-06` and losing `€-295.46`).
   - `"llm"` actively mean-reverted to `(0.40, 22, 0.85)` once shocks cleared — e.g. on `dev-01`: tightened sharply on Wednesday (`0.37, 25, 0.90`) when flu/snow hit (`pot = 0.932, drops = 15, warnings = 18`), then returned to `(0.40, 22, 0.85)` on Thursday evening after `0` drops and `0` warnings (`+€374.91` and `+0.92pp` on-time on `dev-01`).
3. **Multi-signal early tightening on drop/warning spikes (`dev-02 Tue/Wed`, `dev-07 Mon`):**
   - On `dev-07 Mon`, `projected_on_time` was still `0.994` and `unbooked` was `16` (`< 18`), so `"rule"` did nothing despite `19` gig drops. `"llm"` tightened to `(0.38, 24, 0.89)` for Tuesday, then restored `(0.40, 22, 0.85)` Tuesday evening (`95.72%` on-time vs `94.03%` for `"rule"` v2).
4. **Why 16-dev mean margin was `€-93.05 ± 116.71` (`dev-14` Thursday-evening lesson):**
   - Excluding `dev-14` (`-€1,447.12`), `"llm"` averaged **`-€2.78/world`** across the other 15 dev worlds (`7` better, `8` worse). On `dev-14 Thu`, a Thursday storm (`unbooked = 23, warnings = 19, drops = 14, pot = 0.967`) caused `"llm"` to tighten **Friday's** dials to `(0.37, 25, 0.89)`, shedding `10` Friday orders (`won 264 -> 254`). Because Friday's slow options are due on the second Monday (with the entire weekend plus a request-free Monday to clear), tightening on Thursday evening cuts high-margin Friday intake without helping Thursday's already-won cars. Restricting supervisor tightening to Mon–Wed evenings (or exempting Friday slow options) directly addresses that single failure mode.

### Representative `"why"` lines from `gemini-4-argon` (`runs/supervisor/*.json`)
- **`dev-01 Wed` → `(0.37, 25, 0.90)`:** *"Tighten intake and raise fee_open: projected_on_time (0.932) fell below 0.935 safety target following a flu/snow shock (drops_today=15, warnings_today=18, late_orders_today=7)."*
- **`dev-01 Thu` → `(0.40, 22, 0.85)`:** *"Thursday recovery achieved zero drops, zero warnings, and zero unbooked backlog with projected_on_time at 94.53%. Returning to baseline dials (0.40, 22, 0.85) for Friday to maximize gross margin safely."*
- **`dev-05 Tue` → `(0.40, 22, 0.85)`:** *"Competitor price war today (win_rate 0.153 < 0.25) and elevated drops (12); sitting out price war and holding base dials as instructed."*
- **`dev-08 Tue` → `(0.42, 20, 0.85)`:** *"Projected on-time is 1.0, unbooked orders are low at 6, and drops are at the threshold of 6. Loosening modestly to capture more volume while keeping fee_open at base 0.85."*
- **`dev-10 Tue` → `(0.41, 20, 0.85)`:** *"Projected on-time is strong (96.9%), unbooked orders are low (5), and drops are low (4); loosening modestly to capture more volume, especially in ring towns where quotes were heavily restricted today."*

## Verdict
**reject for default promotion (null on mean margin), keep behind `-s supervisor=llm` as measured jury artifact** — both arms are **100% SAFE** (`0` worlds `< 92%`), `"llm"` (`gemini-4-argon`) lifts worst-world margin by **`+€374.91`** (`€7,487.67 -> €7,862.58` on `dev-01`) and outperforms `"rule"` on the 8-world paired test (`€+70.37 ± 109.65`, worst on-time `95.09%` vs `94.03%`) by recognizing price wars and mean-reverting after shocks, while finishing statistically indistinguishable from the already well-tuned champion across all 16 dev worlds (`Δmargin €-93.05 ± 116.71`, `t = -0.80`, worst on-time `94.24%`).
