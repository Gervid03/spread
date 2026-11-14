The cloud lead's validation worker. No new mechanism, so protocol steps 1–4 don't apply. You measure the night's
best candidates on worlds they were never tuned on, run two checks for the final, and leave a promotion branch.
Two exceptions to the common rules, for you alone and given by the lead: you may evaluate holdout seeds
(`--seeds-from holdout`), and you may run `uv run lab promote` inside YOUR OWN worktree. Never push `main`, and
never run `lab board`, `lab final` or `lab reap --force`.

## Candidates (each one: a branch, plus the flags to pass on every eval)
BASE = `-s trust_invest=0.05 -s notes_v2=True -s note_unsure=decline -s max_next_day_drive_min=480 -s fri_same_day_max_drive=100 -s thin_long_next_day_supply=50 -s ring_to_hub_same_day_min=60 -s same_day_min_supply=50 -s min_slack_min=150 -s slack_per_drive=0.75`
- **A** `origin/exp/gemini-n14-03324-supply-adaptive-fee-open-and-drop-rescue`: BASE `-s backlog_multiday_weight=0.25 -s backlog_in_flight_weight=0.35 -s price_target_win=0.40 -s min_supply=22 -s drop_urgent_margin_min=180 -s hub_multiday_fee_open=0.80 -s thin_sameday_fee_open=0.90` (dev €10,577.92)
- **B** `origin/exp/gemini-n14-03111-adaptive-delivery-buffer-and-alarm`: BASE `-s price_target_win=0.40 -s min_supply=22 -s delivery_buffer_min=30 -s buffer_min_slack_min=210 -s pre_warn_lead_min=60 -s pre_warn_fee=1.35` (dev €10,508.07)
- **D** `origin/exp/gemini-n14-03501-extring-full-neutral-and-leadcar`: BASE `-s backlog_multiday_weight=0.25 -s backlog_in_flight_weight=0.35 -s price_target_win=0.40 -s min_supply=22 -s dealer_lr=0.01 -s ext_ring_min_supply=30 -s ext_ring_max_drive_min=220 -s return_hub_min_supply=200 -s return_hub_max_drive_min=180 -s ext_ring_neutral_learn=True -s lead_car=True -s lead_car_max_gap_km=0.0 -s lead_car_max_deliv_gap_km=25.0 -s lead_car_fee_mult=1.00` (dev €10,529.42)
- **C**: `git fetch origin` and look for `origin/exp/gemini-n14-04154-stack-v7-feedrop-buf-alarm` and any later `*stack*` or `*v7*`/`*v8*` branch with an experiment note. Take the one whose best dev run is SAFE with the highest mean margin, provided that mean beats A's €10,577.92, and use exactly the flags its note gives. If there is none, skip C.

## 1. Fresh worlds (the main job)
For each candidate X: `git worktree add --detach /home/lab/spread-wt/val-X origin/<its branch>`, `cd` there,
`uv sync -q`, then:
- `uv run lab eval --seeds-from holdout <flags> --name holdout` (paired with champion v2's stored holdout results)
- `uv run lab eval --seeds night-01,night-02,night-03,night-04,night-05,night-06,night-07,night-08,night-09,night-10,night-11,night-12,night-13,night-14,night-15,night-16,night-17,night-18,night-19,night-20,night-21,night-22,night-23,night-24,night-25,night-26,night-27,night-28,night-29,night-30,night-31,night-32 <flags> --vs <V2_FRESH> --name night32`

V2_FRESH is champion v2's run on those 32 worlds: `/home/lab/spread/runs/20261114-002838-n-champ-fresh32`. Find it with
`ls ~/spread/runs | grep champ-fresh32`. v2 made €9,193 there, with 3 worlds under 92% (night-11 90.5%,
night-30 91.0%, night-15 91.9%). On holdout it made €9,414 with hold-10 at 91.8%. Run the candidates one after
another, and never tune anything on these seeds.

The winner W is the candidate with the highest mean margin over the 48 worlds, among those with every world
ranked and no more worlds under 92% than v2 has on the same 48 (4). On a tie within €150, take the one with the
higher worst on-time share.

## 2. Two checks on W (for the final)
- **Restart:** `uv run lab play --seed dev-03 <W flags> --restart-at 3600` (Wednesday 12:00). It must finish
  ranked. Report its margin and on-time share next to W's dev-03 line from W's dev run (`uv run lab runs`
  shows where that is; the margins needn't match, but a drop of more than ~€1,500 or 2 points is a rejoin bug).
- **Live parity (S16):** `uv run lab eval --seeds-from smoke <W flags> -s step_min=3 --vs <W's dev run folder> --name step3`.
  The final answers every event; practice steps 10 minutes. Report Δmargin and Δon-time per seed. A fall in
  on-time share of more than 1 point on any seed matters more than the margin: say so in the first line of
  your report.

## 3. The promotion branch
In your own worktree: `git fetch -q origin && git merge --no-edit origin/<W's branch>`, `uv sync -q`, then
`uv run lab eval <W flags> --name dev` (it must reproduce W's dev mean to the cent; say whether it does) and
`uv run lab eval --seeds-from holdout <W flags> --name holdout`. Then
`uv run lab promote runs/<the dev folder> --note "<one line: W, the 48-world numbers>"` and
`uv run lab promote runs/<the holdout folder> --note "<the same line>"`. Commit `champion/` together with your
note, and push your branch. Don't merge into main.

## 4. The note
`experiments/<YYYYMMDD-HHMM>-gemini-validate-top.md` with one table: one row per candidate and v2, with columns
holdout mean, Δ vs v2 ± SE (t), night32 mean, Δ vs v2 ± SE (t), the 48-world mean, worst on-time, worlds under
92% and under 91%. Add the restart and step3 results, which candidate won and why, and the commit of your branch.
Your last three lines: W and its branch; its 48-world mean and Δ vs v2, worst on-time, worlds under 92%; the
step3 and restart verdicts.
