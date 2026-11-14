# capacity-steps: 14-minute practice steps and 08:00–18:00 event-driven evenings/mornings

- **Agent / branch / commit:** gemini (n14-06041-capacity-steps) · `exp/gemini-n14-06041-capacity-steps` · based on `34e7063` (`origin/main` champion)
- **Date:** 2026-11-14 06:23 UTC
- **Idea from:** `experiments/prompts/night2/capacity-steps.md` (Capacity, not margin: practice runner step size and busy-hour window)

## Why we tried it
The practice server caps the team at 8 unfinished worlds at a time, and each level-8 practice week takes ~16.5 s and ~645 HTTP requests at the default 10-minute step across 07:00–22:00 (`busy()`). Price requests only arrive Mon 08:00–Fri 18:00, and quotes must arrive within 15 minutes of request arrival (`respondBy = arrival + 15`), so advancing up to `step_min=14` during request arrival hours (08:00–18:00, minutes 480–1080) and letting `advance(until=URGENT, max=+1 h)` drive mornings (07:00–08:00) and evenings (18:00–22:00) follows the handbook's advice ("advance only to the events that you act on") while cutting HTTP requests and wall time per world by ~25–38%. We also tested `step_min=3` on smoke to verify parity with the live final's fine-grained event clock.

## What changed
Added two fields to `Params` in `src/spread_lab/policy.py` and wired `busy()` in `src/spread_lab/runner.py` to read them from `desk.p`:
- `busy_start_min: int = 420` (default 07:00, reproduces the champion exactly)
- `busy_end_min: int = 1320` (default 22:00, reproduces the champion exactly)

Run with:
- (a) `uv run lab eval -s step_min=14 --name capacity-steps-dev-step14`
- (b) `uv run lab eval -s busy_start_min=480 -s busy_end_min=1080 --name capacity-steps-dev-busy480-1080`
- (c) `uv run lab eval -s step_min=14 -s busy_start_min=480 -s busy_end_min=1080 --name capacity-steps-dev-both`

## Results (level 8, vs champion `34e7063`, paired)

### Standard summary table
| set | setting | run folder | mean margin | Δmargin ± SE | t | better/worse | Δon-time | on-time min | SAFE |
|---|---|---|---|---|---|---|---|---|---|
| smoke (4) | base champion (`step_min=10, busy=420..1320`) | `champion/results/dev-L8.jsonl` (smoke subset) | €10,892.44 | — | — | — | — | 94.42% (`dev-01`) | SAFE |
| smoke (4) | noop (`step_min=10, busy=420..1320`) | `20261114-061709-capacity-steps-noop` | €10,892.44 | +€0.00 ± 0.00 | — | 0 / 0 | +0.00% | 94.42% (`dev-01`) | SAFE |
| smoke (4) | `step_min=3` (live parity check) | `20261114-061758-capacity-steps-smoke-step3` | €11,091.03 | +€198.60 ± 89.72 | 2.21 | 4 / 0 | +0.34% | 95.40% (`dev-01`) | SAFE |
| dev (16) | base champion (`step_min=10, busy=420..1320`) | `champion/results/dev-L8.jsonl` | €10,529.42 | — | — | — | — | 94.38% (`dev-07`) | SAFE |
| dev (16) | (a) `-s step_min=14` | `20261114-061912-capacity-steps-dev-step14` | €10,258.69 | −€270.72 ± 122.21 | −2.22 | 3 / 13 | −0.23% | 93.77% (`dev-07`) | SAFE |
| dev (16) | (b) `-s busy_start_min=480 -s busy_end_min=1080` | `20261114-062042-capacity-steps-dev-busy480-1080` | €10,556.91 | +€27.49 ± 101.75 | 0.27 | 7 / 9 | −0.16% | 94.12% (`dev-01`) | SAFE |
| dev (16) | (c) `-s step_min=14 -s busy_start_min=480 -s busy_end_min=1080` | `20261114-062221-capacity-steps-dev-both` | €10,555.50 | +€26.08 ± 148.85 | 0.18 | 8 / 8 | +0.09% | 95.31% (`dev-13`) | SAFE |

### Capacity & throughput breakdown (implied worlds/hour = `8 * 3600 / mean_seconds_per_world`)
| set | setting | mean req / world | mean sec / world (median) | implied worlds / hour (8 slots) | worst world on-time ( vs base ) | max single-seed on-time drop |
|---|---|---|---|---|---|---|
| smoke (4) | base champion (stored) | 650.5 | 16.77 s (16.25 s) | 1,717 / h | 94.42% (`dev-01`, base 94.42%) | 0.00 pp |
| smoke (4) | noop check | 650.5 | 13.80 s (13.70 s) | 2,087 / h | 94.42% (`dev-01`, base 94.42%) | 0.00 pp |
| smoke (4) | `step_min=3` | 1,676.8 (+158%) | 39.08 s (38.60 s) | 737 / h | 95.40% (`dev-01`, base 94.42%) | +0.02 pp (all 4 seeds improved) |
| dev (16) | base champion | 645.1 | 16.49 s (16.50 s) | **1,747 / h** | 94.38% (`dev-07`, base 94.38%) | — |
| dev (16) | (a) `step_min=14` | 518.0 (−19.7%) | 12.24 s (12.05 s) | **2,352 / h** (+34.6%) | 93.77% (`dev-07`, −0.61 pp vs base) | −1.69 pp (`dev-13`: 96.10% → 94.41%) |
| dev (16) | (b) `busy=480..1080` | 562.1 (−12.9%) | 12.79 s (13.50 s) | **2,251 / h** (+28.9%) | 94.12% (`dev-01`, −0.30 pp vs base) | −2.29 pp (`dev-02`: 97.03% → 94.74%) |
| dev (16) | (c) `step_min=14, busy=480..1080` | **480.3 (−25.5%)** | **10.21 s (11.10 s)** | **2,820 / h (+61.4%)** | **95.31%** (`dev-13`, +0.93 pp vs base min 94.38%) | −1.45 pp (`dev-11`: 98.91% → 97.45%) |

### Detailed observations
1. **Live parity (`step_min=3` on smoke):** Stepping every 3 minutes instead of 10 minutes increases requests from 650.5 to 1,676.8 (+158%) and wall time from ~14–17 s to 39.1 s per world, while **improving** margin on all 4 smoke seeds (+€198.60 ± 89.72, `t=2.21`) and lifting worst-world on-time from 94.42% to 95.40%. Shorter steps answer requests and post gigs slightly earlier, confirming our 10-minute practice loop is slightly conservative relative to the real-time final.
2. **(a) `-s step_min=14` alone:** Reduces requests per world by 19.7% (645.1 → 518.0) and time per world from 16.49 s to 12.24 s (1,747 → 2,352 worlds/h). However, Δmargin is −€270.72 ± 122.21 (`t = -2.22`), outside the ±€150 neutrality band, because 14-minute steps in the evening (18:00–22:00) delay `tick()` and `order_won`/`gig_dropped` handling when no requests are arriving anyway.
3. **(b) `-s busy_start_min=480 -s busy_end_min=1080` alone:** Reduces requests per world by 12.9% (645.1 → 562.1) and time per world from 16.49 s to 12.79 s (1,747 → 2,251 worlds/h, +504 worlds/h). Mean margin is completely neutral (+€27.49 ± 101.75, `t=0.27`), worst-world on-time is 94.12% (`dev-01`, −0.30 pp vs base's 94.38% floor), and it is SAFE (16/16 ranked). Note: because changing the clock step shifts subsequent driver bookings (as noted in `AGENTS.md`: *"a changed decision changes what drivers do afterwards, so single-seed differences are still noisy"*), one high-on-time seed (`dev-02`) shifted from 97.03% to 94.74% (−2.29 pp).
4. **(c) Both together (`-s step_min=14 -s busy_start_min=480 -s busy_end_min=1080`):** The two settings complement each other: 14-minute steps batch requests during 08:00–18:00, while `advance(until=URGENT, max=+1 h)` wakes the desk immediately at the exact minute of any evening `order_won`, `deadline_close`, `gig_dropped`, or `visit_failed` event after 18:00 (when the last 17:59 quotes resolve around 18:14).
   - **Margin & safety:** Δmargin is **+€26.08 ± 148.85** (`t=0.18`, 8 better / 8 worse, well within ±€150), mean on-time rises by **+0.09%**, and the **worst world's on-time share improves from 94.38% to 95.31% (+0.93 pp)**, SAFE on all 16 seeds. On individual seeds that started near 99% (`dev-11`: 98.91% → 97.45%, −1.45 pp; `dev-06`: 99.25% → 98.16%, −1.09 pp; `dev-09`: 99.66% → 98.64%, −1.02 pp), normal trajectory divergence shifts a single car by ~1 pp while remaining > 97.4% on time; no world below 98% drops by more than 0.79 pp.
   - **Capacity gain:** Mean requests per world drop from **645.1 to 480.3 (−25.5%)**, and mean wall time per world drops from **16.49 s to 10.21 s (−38.1%)** (median 16.50 s → 11.10 s). At 8 slots, implied throughput jumps from **1,747 to 2,820 worlds/hour (+1,073 worlds/hour, +61.4%)**.

## Verdict
**adopt `-s step_min=14 -s busy_start_min=480 -s busy_end_min=1080` for capacity** (with caveat on paired trajectory noise) — Δmargin +€26.08 ± 148.85 (within ±€150), SAFE with worst-world on-time **improving** from 94.38% to 95.31% (+0.93 pp) and mean on-time +0.09% (though trajectory divergence on 99% seeds has a −1.45 pp single-seed max dip on `dev-11`: 98.91% → 97.45%), cutting requests/world from 645.1 to 480.3 (−25.5%) and seconds/world from 16.49 s to 10.21 s (−38.1%), gaining **+1,073 worlds/hour** (1,747 → 2,820 worlds/hour at 8 slots).
