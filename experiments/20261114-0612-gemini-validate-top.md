# validate-top: Out-of-Sample 48-World Validation (`holdout` + `night32`), Final Checks, and Promotion of Champion v3 (`n14-03501`)

- **Agent / branch / commit:** gemini · `exp/gemini-n14-05161-validate-top` · `7ab0a2c` (on `fd4aa2f`)
- **Promoted main commit:** `34e7063` (`Champion: exp/gemini-n14-03501-extring-full-neutral-and-leadcar`)
- **Date:** 2026-11-14 06:12 UTC
- **Idea from:** Cloud lead validation task (`night-queue/01-validate-top.md`)

## Summary & Verdict
- **Live parity (`step_min=3`) and Wednesday 12:00 restart (`--restart-at 3600`) are completely clean on Winner W (`D`: `origin/exp/gemini-n14-03501-extring-full-neutral-and-leadcar`):** under `step_min=3` on `smoke`, no seed loses any on-time share (`Δon-time` is positive on all 4 seeds: `+0.98 pp`, `+0.02 pp`, `+0.35 pp`, `+0.02 pp`; mean `+0.34%`, `Δmargin €+198.60 ± 89.72, t=2.21, 4/4`), and the `dev-03` restart at minute 3600 finishes ranked (`True`) at `€13,667.02` and `96.9%` on-time (`+€343.96`, `-0.88 pp` vs `dev-03` baseline).
- **Winner W (`D`, `origin/exp/gemini-n14-03501-extring-full-neutral-and-leadcar`)** achieved the highest 48-world mean margin (`€10,960.49`, `Δ vs v2 €+1,693.52 ± 180.06, t=9.41, 46/2`), beating second-place eligible Candidate `A` (`€10,777.68`) by `+€182.81/world` (above the `€150` tie-breaker band), with `48/48` worlds ranked and only `2` worlds under `92%` (`0` on `holdout`, `2` on `night32`, vs Champion v2's `4`).
- **Promoted via `scripts/promote.sh`:** all gates passed and `origin/main` was fast-forwarded to **`34e7063`**, followed by resetting `/home/lab/spread` to `origin/main` (`34e7063`).

---

## Candidates Evaluated
Common base flags (`BASE`):
```sh
-s trust_invest=0.05 -s notes_v2=True -s note_unsure=decline -s max_next_day_drive_min=480 -s fri_same_day_max_drive=100 -s thin_long_next_day_supply=50 -s ring_to_hub_same_day_min=60 -s same_day_min_supply=50 -s min_slack_min=150 -s slack_per_drive=0.75
```

1. **A (`origin/exp/gemini-n14-03324-supply-adaptive-fee-open-and-drop-rescue`, commit `52c06e1`, dev €10,577.92):**
   `BASE -s backlog_multiday_weight=0.25 -s backlog_in_flight_weight=0.35 -s price_target_win=0.40 -s min_supply=22 -s drop_urgent_margin_min=180 -s hub_multiday_fee_open=0.80 -s thin_sameday_fee_open=0.90`
2. **B (`origin/exp/gemini-n14-03111-adaptive-delivery-buffer-and-alarm`, commit `8af3ad7`, dev €10,508.07):**
   `BASE -s price_target_win=0.40 -s min_supply=22 -s delivery_buffer_min=30 -s buffer_min_slack_min=210 -s pre_warn_lead_min=60 -s pre_warn_fee=1.35`
3. **C (`origin/exp/gemini-n14-04154-stack-v7-feedrop-buf-alarm`, commit `d62858b`, dev €10,648.07 — highest SAFE dev mean among `04154` and later `*stack*`/`*v7*`/`*v8*` branches with an experiment note, beating `04394`'s €10,585.43 and A's €10,577.92):**
   `BASE -s backlog_multiday_weight=0.25 -s backlog_in_flight_weight=0.35 -s hub_multiday_fee_open=0.80 -s thin_sameday_fee_open=0.90 -s drop_urgent_margin_min=180 -s delivery_buffer_min=30 -s buffer_min_slack_min=210 -s pre_warn_lead_min=60 -s pre_warn_fee=1.35 -s price_target_win=0.40 -s min_supply=22 -s fee_warn=1.48 -s fee_step_min=25 -s steep_open=1.55 -s dealer_lr=0.01`
4. **D (`origin/exp/gemini-n14-03501-extring-full-neutral-and-leadcar`, commit `3e02692`, dev €10,529.42):**
   `BASE -s backlog_multiday_weight=0.25 -s backlog_in_flight_weight=0.35 -s price_target_win=0.40 -s min_supply=22 -s dealer_lr=0.01 -s ext_ring_min_supply=30 -s ext_ring_max_drive_min=220 -s return_hub_min_supply=200 -s return_hub_max_drive_min=180 -s ext_ring_neutral_learn=True -s lead_car=True -s lead_car_max_gap_km=0.0 -s lead_car_max_deliv_gap_km=25.0 -s lead_car_fee_mult=1.00`

---

## 1. Out-of-Sample Results on 48 Fresh Worlds (`holdout` 16 + `night32` 32)

| Candidate | Holdout Mean (16) | Holdout Δ vs v2 ± SE (t) | Night32 Mean (32) | Night32 Δ vs v2 ± SE (t) | 48-World Mean | 48-World Δ vs v2 ± SE (t) | Worst On-Time | Worlds <92% | Worlds <91% | Ranked |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **v2 (Champion)** | €9,414.43 | — | €9,193.25 | — | €9,266.97 | — | 90.45% | 4 | 1 | 48/48 |
| **A** (`n14-03324`) | €11,160.19 | €+1,745.76 ± 269.91 (6.47, 16/0) | €10,586.42 | €+1,393.17 ± 239.63 (5.81, 30/2) | €10,777.68 | €+1,510.70 ± 183.27 (8.24, 46/2) | **92.00%** | **0** | **0** | 48/48 |
| **B** (`n14-03111`) | €10,897.17 | €+1,482.75 ± 206.28 (7.19, 16/0) | €10,622.03 | €+1,428.78 ± 210.11 (6.80, 30/2) | €10,713.75 | €+1,446.77 ± 154.76 (9.35, 46/2) | 91.56% | 1 | **0** | 48/48 |
| **C** (`n14-04154`) | €11,057.17 | €+1,642.75 ± 267.71 (6.14, 15/1) | €10,869.77 | €+1,676.53 ± 249.36 (6.72, 30/2) | €10,932.24 | €+1,665.27 ± 187.01 (8.90, 45/3) | 89.29% | 2 | 1 | **47/48 (UNRANKED)** |
| **D** (`n14-03501`) — **W** | **€11,280.68** | **€+1,866.25 ± 248.38 (7.51, 16/0)** | €10,800.40 | €+1,607.15 ± 241.02 (6.67, 30/2) | **€10,960.49** | **€+1,693.52 ± 180.06 (9.41, 46/2)** | 90.73% | 2 | 1 | 48/48 |

### Run Folders & Worlds Under 92%
- **v2 (Champion):** `champion/results/holdout-L8.jsonl` + `/home/lab/spread/runs/20261114-002838-n-champ-fresh32` (`hold-10` 91.8%, `night-11` 90.45%, `night-30` 91.0%, `night-15` 91.9%)
- **A (`val-A`):** `20261114-052501-holdout` (min 95.4%) + `20261114-055101-night32` (min 92.00% on `night-15`) -> **0 worlds <92%**
- **B (`val-B`):** `20261114-053941-holdout` (min 95.7%) + `20261114-055342-night32` (`night-11` 91.56%) -> **1 world <92%**
- **C (`val-C`):** `20261114-054118-holdout` (min 94.5%) + `20261114-055754-night32` (`night-11` 91.90%, `night-15` **89.29% UNRANKED**) -> **2 worlds <92%, 1 unranked**
- **D (`val-D`):** `20261114-054352-holdout` (min 94.39%) + `20261114-060206-night32` (`night-11` 90.73%, `night-15` 91.12%) -> **2 worlds <92%**

### Why Candidate D Won
1. **Candidate C (`n14-04154`) is eliminated** because lowering `fee_warn=1.48` and `steep_open=1.55` caused `night-15` to drop to `89.29%` on-time (`300 / 336`, unranked).
2. Among the candidates with `48/48` worlds ranked and `<= 4` worlds under `92%` (`A`, `B`, `D`), **Candidate D (`origin/exp/gemini-n14-03501-extring-full-neutral-and-leadcar`)** has the highest 48-world mean margin (`€10,960.49`) and highest holdout mean margin (`€11,280.68`, `t = 7.51`, `16/16` better than v2, `0` holdout worlds under `92%`).
3. Candidate D's 48-world mean margin beats second-place eligible Candidate A (`€10,777.68`) by **`+€182.81/world`**, which exceeds the `€150` tie-breaker threshold (`€182.81 > €150.00`). (Note: Candidate A is the only candidate with `0` worlds under `92%` across all 48 worlds, making its `hub_multiday_fee_open=0.80, thin_sameday_fee_open=0.90, drop_urgent_margin_min=180` mechanism — with standard `fee_warn=1.60, steep_open=1.80` kept intact — the prime mechanism to stack onto the new Champion D in daytime runs.)

---

## 2. Two Final Checks on Winner W (Candidate D)

### Check 2a: Mid-Week Restart (`--seed dev-03 --restart-at 3600`, Wednesday 12:00)
| Run | Margin | Won Orders | On-Time Share | Ranked | Notes |
|---|---:|---:|---:|---|---|
| **D `dev-03` baseline** (`20261114-040101-backlog-extring-neutral-leadcar-dev`) | €13,323.06 | 315 | 97.78% | `True` | Practice 10-min steps, no restart |
| **D `dev-03` `--restart-at 3600`** | **€13,667.02** | **322** | **96.89%** (`96.9%`) | **`True`** | Rejoined at minute 3609: 125 orders, 67 live gigs, `mult=1.702`, outbox 5 |
| **Difference (`restart - dev`)** | **€+343.96** | **+7** | **-0.88 pp** | **Pass** | Clean rejoin (well within the €1,500 and 2.0 pp bounds) |

### Check 2b: Live Parity (`--seeds-from smoke -s step_min=3 --vs 20261114-040101-backlog-extring-neutral-leadcar-dev --name step3`)
- Run folder: `/home/lab/spread-wt/val-D/runs/20261114-060723-step3`
- Summary: `mean margin €11,091.03 (median €11,426.97, min €7,724.97) ranked 4/4 on time min 95.4% mean 96.9% won 292 failed 0 -> SAFE`
- Paired comparison vs D's dev run (`20261114-040101-backlog-extring-neutral-leadcar-dev`): `Δmargin €+198.60 ± 89.72 (SE) t=2.21, better on 4, worse on 0, Δon-time +0.34%`

| Seed | Dev Margin (`step_min=10`) | Step3 Margin (`step_min=3`) | Δmargin | Dev On-Time | Step3 On-Time | Δon-time (pp) | Ranked |
|---|---:|---:|---:|---:|---:|---:|---|
| `dev-01` | €7,614.48 | €7,724.97 | **€+110.49** | 94.42% | 95.40% | **+0.98 pp** | `True` |
| `dev-02` | €10,659.12 | €10,725.49 | **€+66.37** | 97.03% | 97.05% | **+0.02 pp** | `True` |
| `dev-03` | €13,323.06 | €13,785.23 | **€+462.17** | 97.78% | 98.12% | **+0.35 pp** | `True` |
| `dev-04` | €11,973.09 | €12,128.45 | **€+155.36** | 97.13% | 97.15% | **+0.02 pp** | `True` |

**Step3 Verdict:** Clean pass — every seed improves on both margin and on-time share (`0` seeds lose any on-time share).

---

## 3. Gated Promotion (`scripts/promote.sh`) Output (Last 10 Lines)
```text
  "candidate_holdout": 0,
  "champion_holdout": 1,
  "candidate_dev": 0,
  "champion_dev": 0
 }
}
ALL GATES PASSED: dev Δ +1,539 ± 265 (t 5.81), holdout Δ +1,866 ± 248, holdout on-time min 94.4%
Champion is now runs/20261114-060916-dev. Commit champion/ to make it official.
Champion is now runs/20261114-061036-holdout. Commit champion/ to make it official.
promote: PROMOTED: main is 34e7063. The final runner picks it up within ~5 minutes (unless .freeze).
```

Post-promotion root checkout sync (`/home/lab/spread`):
```text
34e7063 Champion: exp/gemini-n14-03501-extring-full-neutral-and-leadcar (dev Δ +1,539 ± 265 (t 5.81), holdout Δ +1,866 ± 248, holdout on-time min 94.4%)
```
