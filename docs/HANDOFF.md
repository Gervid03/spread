# Handoff: where the lab stands

## Sat 14 Nov, 07:15 Helsinki (the cloud lead, night shift)
Read this, then the directive at the top of `experiments/IDEAS.md`, then `docs/OPERATIONS.md`.

**The night (scripts/night.sh on the swarm VM, 02:13–12:13 Helsinki; results force-pushed every 20 minutes to
`night/20261114`):** about 50 Gemini 4 Argon workers and 47 dev sweeps on v2. The best stacks are 16-seed dev numbers,
not yet validated on fresh worlds:

| | branch | dev mean | Δ vs v2 (t) | worst world |
|---|---|---:|---:|---:|
| v2 (champion) | `main` | €8,990 | — | 94.4% |
| A, fee-drop | `exp/gemini-n14-03324-supply-adaptive-fee-open-and-drop-rescue` | €10,578 | +1,588 (6.8) | 95.6% |
| B, buffer-alarm | `exp/gemini-n14-03111-adaptive-delivery-buffer-and-alarm` | €10,508 | +1,518 (7.5) | 95.8% |
| D, ext-ring + lead car | `exp/gemini-n14-03501-extring-full-neutral-and-leadcar` | €10,529 | +1,539 (5.8) | 94.4% |
| C, v7 = A + B + `dealer_lr` 0.01 | `exp/gemini-n14-04154-stack-v7-feedrop-buf-alarm` | €10,648 | +1,658 (7.1) | 94.0% |

All four are within one SE of each other, so re-stacking has stopped paying. v2 on 32 fresh worlds (`night-01..32`)
made €9,193 with 3 worlds under 92% (night-11 90.5%). The fresh-world tail is the real risk for the final.

**The public board** (`GET https://spread.bahnexpress.com/v1/leaderboards/practice?level=8`, round "Saturday
00:00"): **35th of 63 ranked teams** (151 in all) with €54.2k for 5 worlds. The top 10 need ~€75.5k, and House best
has €71.8k. **The leaders win 410–460 orders a week at 96–98% on time, at the same ~€40 margin an order as ours;
we win ~270.** The gap is volume. The margin x-ray (`exp/gemini-n14-01392-margin-xray-v2`) puts it in the thin
class (under 30 drivers within 55 km: 287 requests a week, all declined) and in same_day from mid towns and the
ring (all declined).

**Done tonight from the cloud** (everything is on `main`, nothing in `src/`, so the final runner did not restart):
- Fable's round 3 (ideas 15–30, S7–S17, R6–R14, 14 briefs) merged. It had never reached the night run.
- The lead's directive at the top of IDEAS.md: build on A, volume first, round 3 gets the slots, no v2 sweeps.
- Four prompts that the night lead's tick copies from `night-queue/` on main: `01-validate-top` (A, B, D, C on holdout
  plus `night-01..32`, a restart, `step_min=3` live parity, then **`scripts/promote.sh`** for the winner and a reset of
  the swarm host's root checkout so ranking rounds play it), `02-thin-volume` (ideas 25 + 24), `03-triage` (15),
  `04-thermostat` (19). **Remove them from `night-queue/` once they are queued** (main brings them back at every
  tick).
- `scripts/promote.sh` + `scripts/promote_gate.py`: the gated road to main (tested with stubs; see OPERATIONS.md).
- `experiments/prompts/fable-ideas.md`: the brief to give Fable now and then.

**Server capacity, measured tonight.** A level-8 week takes **~16 s on the swarm VM** (~630 requests at ~25 ms), not
the 50–60 s measured from the laptop. With 8 worlds per team that's a ceiling of **~1,800 worlds an hour**, and the night
ran close to it. Machines don't raise it: the cap is per team. The v2 sweep track alone used 2.4–3.6 of the 8
slot-hours each hour (30–45%), on code that is no longer the frontier, so it is now off until the root checkout is
on the new champion. **Gemini** (Argon for the lead and workers, 5 at a time) runs at ~15–20 requests a minute,
about 1% of the Tier 3 limit. More Gemini buys more thinking, not more tests. Its best use is slot-free work:
research on reveals (one request each), code review, and two workers on one structural idea (best of two).

**After the night ends (12:13 Helsinki): the day run, one paste on the laptop.** If it says "already running", the
night's last workers are finishing: wait ten minutes and paste again.
```sh
ssh -i ~/.ssh/verda_spread ops@34.51.182.19 'sudo -u lab -H bash -lc "cd ~/spread && git fetch -q origin && git reset -q --hard origin/main && mkdir -p runs && (HOURS=17 MAX_WORKERS=6 setsid nohup bash scripts/night.sh > runs/night-day.out 2>&1 < /dev/null &); sleep 60; tail -n 6 runs/night/night.txt"'
```
It runs until Sun 05:00 Helsinki and pauses itself in the quiet hours. promote.sh refuses after Sun 06:00. The
freeze (`touch /home/lab/spread-final/.freeze` on Verda) is still by hand.

---

## Sat 14 Nov, 01:00 Helsinki (the laptop lead)

For the next lead session (Claude in a cloud session, or a person). Read this, then `docs/OPERATIONS.md`,
`AGENTS.md` and `experiments/IDEAS.md`.

## Where we are
- **Champion v2** (`champion/champion.json`): €8,990 a week on dev, €9,414 on holdout, all 32 worlds
  ranked. One holdout world was at 91.8% on time; v2 was promoted as a recorded exception to the 92% rule
  (veto: revert 0e9b882).
- **Public standing: 10th of 15 in ranking round 4** (Sat 00:00, level 8, the same 5 worlds for everyone):
  we made **€54,213** (10,126 · 10,851 · 11,177 · 11,466 · 10,594), at 95.6–98.6% on time. The leader, Juhus,
  made €80,030 and House best €71,790. **We are ~25% below House best on the same worlds.** Tuning steps of
  ±€200 won't close that: the next gains have to come from structure (where is the margin lost: prices too
  low, fees too high, requests we skip, late orders?). Diagnostics on revealed practice worlds
  (`lab reveal`, ideas R1–R5) are the obvious first step.
- **Wave 2** (Gemini 3.1 Pro, on v1; all branches pushed, notes in each branch's `experiments/`):

  | idea | branch | best Δ vs v1 (dev, 16 worlds) | verdict |
  |---|---|---|---|
  | 3 two price clocks | `exp/gemini-clocks` | +46 ± 204 | nothing |
  | 6 fee floor | `exp/gemini-feefloor` | +104 ± 196 (its `fee_open_dense=0.85` overlaps v2's `fee_open 0.85`) | nothing new |
  | 7 bulk orders | `exp/gemini-bulk` | −98 ± 220 | reject |
  | 4 trust | `exp/gemini-trust` | `trust_invest=0.1`: +215 ± 157 (t 1.4); `trust_gain` −285 (t −2.4) | the one worth a re-test on v2 |

## Changed in this commit (not yet live-tested)
- **Quiet hours** (`lab.py`, `QUIET_UTC`): no practice world starts during the test finals (Sat 13:40–14:50,
  19:40–20:50 Helsinki) or the final (Sun 07:20–09:00), or while `~/.spread-lab/pause` exists. Evals wait and
  print a line a minute.
- **The final runner updates itself**: while no final is set, `lab final` checks `origin/main` every 5 minutes
  and exits when `src/`, `champion/` or the lock file changed. systemd restarts it, and it pulls main on
  start. `.freeze` in `/home/lab/spread-final` pins it. So a promotion reaches Verda with no SSH.
- **`lab board --auto --yes`** plays what is left of the current ranking round (5 runs) with the champion,
  in slots, outside quiet hours, and logs to `runs/board.log`. Round 4 is played.

## Models (probed 00:50 Sat on the hackathon key)
`gemini-4-argon`, `gemini-4-carbon` and `gemini-4-hydrogen` are available. On an AIME counting problem all
were right; **Argon used 458 thinking tokens in 8 s**, Carbon 2.4k in 25 s, Hydrogen 2.3k in 9 s, and
3.1 Pro 12k in 81 s (and ignored the answer format). **Use `gemini-4-argon` for the lead and the workers.**

## The next step: a Gemini lead running the swarm (the user's ask: more agents, stronger ones, more tests in parallel, a Gemini orchestrator)
**Parallel tests:** the server allows **8 unended practice worlds per team**, and a week takes ~50–60 s of
server time. That caps us at ~8 worlds a minute, about 30 sixteen-world evals an hour, whatever machines we
add. So more than ~6 workers just queue. Run everything that plays worlds on the swarm VM with
`SPREAD_SLOTS=8`, and keep the laptop out of it.

To build (all on the swarm VM, as `lab`):
1. `scripts/spawn.sh <slug> <prompt file>`: pulls `~/spread`, refuses past `MAX_WORKERS` (6), starts
   `scripts/swarm.sh` with `$WORKER_MODEL` (gemini-4-argon) under `setsid nohup`, writes
   `runs/swarm/<slug>.pid`. `swarm.sh` must `git fetch` before `worktree add` (it branches from
   origin/main) and accept an absolute prompt path.
2. `scripts/swarm-status.sh`: one line per worker: running or done, minutes, tool calls, its last
   `Δmargin` line, and whether the branch is pushed. Parse `runs/swarm/<slug>.jsonl`: `type: tool_use` events,
   assistant `message` content, and `result.stats`.
3. `scripts/promote.sh [-s key=value ...]`, **the only road to main for code**, run in a worktree based on
   origin/main. It refuses diffs outside `src/spread_lab/policy.py`, `notes.py`, `experiments/` and
   `README.md`. It refuses after Sun 06:00 Helsinki. Then:
   - import check;
   - `lab eval --name dev` must be SAFE with t ≥ 2 vs the champion;
   - `lab eval --seeds-from holdout --name holdout` must be all ranked, with Δ ≥ 0, no more worlds under 92%
     than the champion, and a minimum no more than 0.5 points below the champion's;
   - `lab play --seed dev-01 --restart-at <minute>` must finish ranked.

   Then it runs `lab promote` on both runs, commits `champion/`, and pushes to main fast-forward only (if
   main moved, re-run).
4. `scripts/lead.sh` as a systemd service. Each loop:
   - honour `~/.spread-lab/pause`;
   - `uv run lab board --auto --yes`;
   - one lead tick, `gemini -m gemini-4-argon`, with `experiments/prompts/_lead.md` and the status output
     inlined, in its own worktree reset to origin/main;
   - then wait until a worker finishes or 20 minutes pass.
5. `experiments/prompts/_lead.md`. The lead:
   - reads `experiments/LEDGER.md`, `IDEAS.md` and finished workers' notes, and records verdicts in the
     ledger;
   - writes worker prompts (like `gemini-trust.md`), spawns up to `MAX_WORKERS`, and sends promising branches
     to a re-test worker that merges them onto main and runs `promote.sh`;
   - pushes only docs (ledger, ideas, prompts) to main itself;
   - prefers structural ideas over sweeps, and never runs `lab final` / `lab reap --force`, never touches
     `.env`, never runs SSH.

   Amend AGENTS.md rule 2: `lab promote` only through `scripts/promote.sh` when the prompt says so.
6. `experiments/prompts/fable-ideas.md`, for the user to give Fable now and then. It reads GAME.md, LEDGER,
   the notes and the leaderboard, and appends dated, testable ideas to IDEAS.md.

**Budget:** wave 2 was 4 agents, 249 tool calls and 12.6M tokens (mostly cached) in ~20 minutes. The Google
project warns against "thousands of requests" and also hosts the swarm VM. A suspension would cost the swarm,
not the final, which runs on Verda.

## What a cloud session can and can't reach
The repo is all a cloud session gets. It has no `.env` (`SPREAD_KEY`, `GEMINI_API_KEY`) and no SSH key for the
machines (`~/.ssh/verda_spread` is on the laptop only). With neither, it can write code and push, but it
can't play worlds or reach the VMs. To give it reach, add `SPREAD_KEY` and `GEMINI_API_KEY` as secrets in the
cloud environment, and either the SSH key (sensitive: it opens both machines) or leave the machines to the
laptop. Pushing to main still reaches the final runner by itself (see above).

## Clock
- Sat 14:00 and 20:00: test finals, played by the Verda service with whatever is on main (quiet hours pause
  practice).
- Ranking rounds: Sat 09, 12, 15, 18, 21; Sun 00, 03, 06. `board --auto` plays them once the lead loop
  runs; until then play them by hand: `uv run lab board --auto --yes`.
- Sun ~06:00: freeze (`touch /home/lab/spread-final/.freeze` on Verda); the final is set 07:30 and starts
  08:00.
- Sun 10:00: Junction submission. It needs the hash from spread.bahnexpress.com/team, the code link (make
  the repo public), and 5–10 slides (see GAME.md).
