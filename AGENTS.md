# AGENTS.md: how to work on Swarm Dispatch

You are one of several coding agents (Codex, Gemini, Claude) improving our entry for **Bahn Express
Spread** at Junction 2026: a dispatcher that runs a simulated car-transport company for one week. Read
this file fully before you change anything. It is short on purpose; the facts of the game are in
[`docs/GAME.md`](docs/GAME.md), the organisers' full documents in `docs/kit/` (`uv run lab docs`).

## The objective
- The **final** (Sun 15 Nov 08:00 Helsinki) is one secret **level-8** world. The **10 ranked teams with the
  highest margin** go to the jury. Ranked means **≥ 90% of won orders on time**. Missing it once = out.
- So our objective is: **maximise mean margin on level-8 worlds, subject to never dropping below 90% on
  time** — we hold ourselves to **≥ 92% on every seed** as a safety margin.
- After the top 10, the jury judges elegance, clarity, creativity and robustness, and asks, for each big
  idea, *why we tried it and its measured effect on margin and on-time share*. Every experiment you record
  is material for that presentation, including the ones that failed.

## Setup (once per checkout or worktree)
```sh
uv sync                     # Python 3.10+, installs the organisers' kit and filelock
uv run lab docs             # downloads HANDBOOK/RULES/API to docs/kit/ (gitignored)
```
The team key is in `.env` at the main checkout (never committed). A git worktree reads it from the main
checkout automatically. **The harness needs network access to spread.bahnexpress.com**: run your agent
with network enabled (Codex: a sandbox with network access).

## The measuring instrument
| Command | What it does | Cost |
|---|---|---|
| `uv run lab eval --seeds-from smoke` | 4 level-8 worlds, compared with the champion | ~1 min |
| `uv run lab eval` | the **dev** set: 16 level-8 worlds | ~3–4 min |
| `uv run lab eval -s key=value -s ...` | the same with parameter overrides (on top of the champion's) | |
| `uv run lab sweep -g key=a,b -g key2=c,d` | every combination, on smoke by default | 1 min × combos |
| `uv run lab play --seed dev-03` | one world, a line per day | ~1 min |
| `uv run lab runs` | the latest evaluations from every checkout on this machine | free |
| `uv run lab compare runs/A runs/B` | paired comparison of two run folders | free |
| `uv run lab reveal <world id>` | a finished world's reveal as CSV files: quotes and outcomes, each won car's truth (what its note meant), every view of our gigs with its fee | 1 request |

- Every eval writes `runs/<time>-<name>/` (`meta.json`, `results.jsonl` with one line per world incl.
  the account by ledger kind and the desk's counters, `summary.json`) and a line in the machine-wide index.
- **SAFE** = every world ranked and ≥ 92% on time. **Δmargin ± SE** is a *paired* comparison with the
  champion on the same seeds: worlds are deterministic, so seed noise cancels, but a changed decision
  changes what drivers do afterwards, so single-seed differences are still noisy. Trust 16 seeds, not 4.
- **Seed sets** (`seeds/`): `smoke` (4) while iterating; `dev` (16) to claim a result; `holdout` (16) is
  the lead's check before promoting — never tune on it.

## Rules (hard)
1. **Worlds only through `uv run lab`.** It holds the cross-process slot budget (`SPREAD_SLOTS`, default 6
   of the team's 8) and deletes worlds on errors. Never create worlds with raw API calls or the kit's
   `spread-starter`. If a world leaked (killed process), `uv run lab reap` frees it.
2. **Never run `lab board`, `lab final`, `lab promote` or `lab reap --force`.** Ranking runs are public and
   limited (5 per round), the final is live, promotion is the lead's decision.
   A new champion reaches `main` only through `scripts/promote.sh <branch> <flags>` (gated against the champion
   on dev, holdout and a restart), and only when your task tells you to run it.
3. **Don't touch the instrument** without the lead: `src/spread_lab/lab.py`, `runner.py`, `env.py`,
   `seeds/`. A change there can make every comparison meaningless. Propose it in your experiment note.
4. **One idea per branch**, named `exp/<agent>-<slug>`, in your own git worktree
   (`git worktree add ../spread-<slug> -b exp/<agent>-<slug>`). Don't commit to `main`.
5. **A new mechanism is a new `Params` field whose default keeps the champion's behaviour exactly.**
   Enable it with `-s field=value`. Then the champion's stored results stay valid, and the ablation is the
   flag. If an idea cannot be a flag, subclass `Desk` in `src/spread_lab/policies/<slug>.py` and evaluate
   it with `--policy spread_lab.policies.<slug>:Desk`.
6. **Determinism.** The desk must be a pure function of what the world told it: no wall clock, no
   unseeded randomness, no iteration over sets where order matters. Otherwise paired comparisons break.
7. **Live-mode compatible.** In the final, events arrive one by one and the desk sends after each; it may
   also be restarted mid-week and rebuild itself in `rejoin()`. Don't depend on the practice step size,
   and keep `rejoin()` working when you add state (rebuild it from the snapshot and the event history).
8. **Budget.** Iterate on `smoke`, claim on `dev`. Sweeps of more than ~8 combinations, or anything that
   would hold slots for over 20 minutes, need the lead. During the test finals (Sat 14:00, 20:00) and the
   final (Sun 08:00) the practice limit drops to 20 requests/s for the whole team: pause heavy work.
9. **Secrets.** Never print, log or commit the key. `.env` is gitignored; keep it that way.
10. **Record every experiment**, success or not, in `experiments/` (below). An unrecorded result didn't happen.

## Claiming an improvement
1. Implement behind a flag; check the default reproduces the champion (`lab eval --seeds-from smoke`
   with no overrides must show Δ = 0.00 on every seed).
2. Iterate on smoke. When it looks good, run dev: `uv run lab eval -s your_flag=... --name <slug>`.
3. A result counts when, on dev: **SAFE**, and **Δmargin > 0 with t ≥ 2** (or better on ≥ 12 of 16 seeds).
4. Write the experiment note, commit it with the code on your branch, push the branch, and tell the lead
   the run folder. The lead runs holdout and promotes.

## Experiment notes
One file per experiment: `experiments/<YYYYMMDD-HHMM>-<agent>-<slug>.md`, from
[`experiments/TEMPLATE.md`](experiments/TEMPLATE.md): the idea, why we tried it, what changed (flags),
the dev numbers (Δmargin ± SE, Δon-time, SAFE?), and a one-line verdict. Copy the run's `summary.json`
numbers, not your impressions. The ideas to work on are in [`experiments/IDEAS.md`](experiments/IDEAS.md).

## The code
| File | What it holds |
|---|---|
| `src/spread_lab/policy.py` | **The desk** (`Desk`, `Params`): quoting, selection, fees, offers, the rule-handling mechanics |
| `src/spread_lab/notes.py` | Reading dealer notes: windows (the kit starter's reader) and flags (manual, plates, summer tyres) |
| `src/spread_lab/geo.py` | The map, road minutes, straight-line km, drivers near each place |
| `src/spread_lab/runner.py` | Practice loop (batched 10-minute steps in business hours) and live loop (stream, rejoin) — *instrument* |
| `src/spread_lab/lab.py` | Slots, world registry, parallel evaluation, summaries, paired comparison, champion — *instrument* |
| `src/spread_lab/cli.py` | `uv run lab ...` |
| `champion/` | The current best: `champion.json` (policy + params) and its per-seed results |
| `experiments/` | `IDEAS.md` (the backlog), `TEMPLATE.md`, one note per experiment |

The desk's event handlers are in `Desk.handle`. Prices come from `Desk.price`, fee schedules from
`Desk.fees_for`/`rising`/`steep`, escalation from `Desk.raise_fees`/`offer`. `desk.stats` counters end up
in every result line: add counters for anything your idea changes, so its effect is visible.
