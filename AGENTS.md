# AGENTS.md: how this repo works (since the de-bloat, Sat 14 Nov ~22:00)

Our entry for **Bahn Express Spread** at Junction 2026: a desk that runs a simulated car-transport dispatcher for one
level-8 week. Score = gross margin; at least 90% of won orders on time or unranked. The game in short:
[`docs/GAME.md`](docs/GAME.md); the organisers' documents: `docs/kit/` (`uv run lab docs`).

The repo is deliberately small. What stays is what played the test runs and worked: the desk (the champion), the
measuring instrument, the final runner, and the gated road to a new champion. The swarm era (Gemini agents, TAS,
co-play, the night run, every experiment note and prompt) is in the git tag `swarm-era`; its verdicts are in
[`experiments/LEDGER.md`](experiments/LEDGER.md).

## What's here
| Path | What it is |
|---|---|
| `src/spread_lab/policy.py`, `notes.py`, `geo.py`, `policies/` | **The desk.** The champion is `policies/cycles.py:Desk` (on `sunday_tours` → `tas_routes` → `policy.Desk`) with the params in `champion/champion.json` |
| `src/spread_lab/runner.py`, `lab.py`, `env.py`, `cli.py` | **The instrument**: practice and live loops, slots, evaluation, paired comparison. Don't change it casually: every stored comparison depends on it |
| `champion/` | The current champion: policy, params, its per-seed results on dev and holdout |
| `seeds/` | `smoke` (4), `dev` (16), `holdout` (16, never tune on it) |
| `scripts/promote.sh`, `promote_gate.py` | The only road to a new champion on `main` (gated on dev, holdout and a restart) |
| `scripts/vm-push.sh`, `vm-setup.sh` | Set up a machine (the final runner on Verda, the practice host) |
| `experiments/orc/` | The bare oracle harness: raw worlds, forks, actions, no desk |
| `experiments/` | `LEDGER.md` (what worked), `PROMOTIONS.md` (champion history), the current notes |

## The instrument
| Command | What it does |
|---|---|
| `uv run lab eval --seeds-from smoke` | 4 worlds, compared with the champion (~1 min) |
| `uv run lab eval` | the 16 dev worlds |
| `uv run lab eval -s key=value` | the same with parameter overrides on top of the champion's |
| `uv run lab play --seed dev-03` | one world, a line per day |
| `uv run lab compare runs/A runs/B` | paired comparison of two run folders |
| `uv run lab reveal <world id>` | a finished world's reveal as CSV |

Worlds are deterministic: the same seed and actions give the same week to the cent, so comparisons are paired.
SAFE = every world ranked and ≥ 92% on time.

## Rules
1. Worlds only through `uv run lab` or `experiments/orc/orc.py`: both hold the slot budget (8 unended worlds per
   team) and delete worlds on errors. `uv run lab reap` frees leaked ones.
2. Never run `lab final` (Verda plays it), `lab board` or `lab promote` by hand. A new champion goes through
   `scripts/promote.sh`.
3. A new mechanism is a `Params` field whose default keeps the champion's behaviour exactly.
4. The desk is deterministic and live-safe: no wall clock, no unseeded randomness; `rejoin()` rebuilds its state.
5. Secrets stay in `.env` (gitignored).
6. Experiments stay small and readable: one script, one question, its answer written down next to it.
