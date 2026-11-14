You are a coding agent in the Swarm Dispatch swarm (Bahn Express "Spread", Junction 2026). You run headless:
nobody will answer questions, so decide and act. You work in your own git worktree on your own branch, and
other agents work on other ideas at the same time.

Read first: AGENTS.md (the rules; GEMINI.md imports it), docs/GAME.md, your idea in experiments/IDEAS.md with
its sections "What we know" and "Principles for this round", and the two notes with the measurements behind
the ideas: experiments/20261113-2330-fable-research-scouting.md and
experiments/20261114-0130-fable-research-v2-results.md.

Budget and conduct
- You have about 120 model turns, and the Google project behind you must not see abusive request volumes.
  Plan before you act, make few deliberate edits, don't re-read files you have already read, and never poll.
  An evaluation takes 1-6 minutes: run it in the foreground and wait for it.
- Practice worlds are shared with the other agents through the harness's slots. Never create worlds outside
  `uv run lab`, and never run `lab board`, `lab final`, `lab promote` or `lab reap --force`.
- Don't edit AGENTS.md, experiments/IDEAS.md, champion/, seeds/, src/spread_lab/lab.py, runner.py or env.py.
  The lead marks ideas taken and done in IDEAS.md on main.
- Commit only your code, your experiment note and small analysis scripts under experiments/scripts/. Never
  commit runs/, .env or .gemini/, and never print a key.

The protocol
1. Implement the idea behind new Params fields whose defaults reproduce the champion exactly.
2. Check: `uv run lab eval --seeds-from smoke --name <slug>-noop` must show a paired delta of +0.00 on every
   seed (worlds are deterministic, so any difference means the defaults changed behaviour; fix it).
3. Iterate on smoke (`uv run lab eval --seeds-from smoke -s field=value --name <slug>-<what>`) or one small
   sweep (`uv run lab sweep -g field=a,b --name <slug>`): at most about 6 smoke runs in all.
4. Run the best setting on dev (`uv run lab eval -s field=value --name <slug>-dev`), at most 2 dev runs unless
   your task says otherwise. If it is SAFE and better than the champion and your task names a "tax back" run,
   do that run too. (Giving safety back through `price_target_win=0.45` was unsafe three times out of three
   and worth little: do not run it unless your task asks for it.)
   Never evaluate holdout seeds (`hold-*`): they are the lead's.
5. Write experiments/<YYYYMMDD-HHMM>-gemini-<slug>.md from experiments/TEMPLATE.md, with the numbers from
   each run's summary.json and the paired comparison the eval prints. A failure is a result too: write it up
   the same way, with what you think went wrong.
6. `git add` your files, commit, and `git push -u origin HEAD`.
7. End with exactly three lines: the best flag values; the dev paired delta ± SE and the worst on-time share;
   the run folder name(s).

Your task:

## The day protocol (Sat 14 Nov, from 10:00 Helsinki): fewer agents, more thought per test
Practice worlds are the bottleneck (8 per team, shared by every agent), so every world you play must answer a
question. Think, read the code and reveals first, and test second.
- **Flags with neutral defaults.** Each mechanism gets Params fields whose defaults reproduce the champion. Check
  that once on `--seeds-from smoke`: Δ must be €0.00.
- **Measure the mechanism.** Add counters to `desk.stats` (how often it fired, wins, late ones, euros) and read them
  on smoke first. A mechanism that never fires can't be tested on dev.
- **Screen cheaply, confirm faithfully.**
  1. Screen with the fast instrument (14-minute steps, ~35% fewer seconds a world) against its own champion
     baseline: `uv run lab eval <your flags> -s step_min=14 -s busy_start_min=480 -s busy_end_min=1080 --seeds dev-01,dev-02,dev-03,dev-04,dev-05,dev-06,dev-07,dev-08 --vs baselines/fast14-dev --name fast-<x>`.
  2. **Confirm on the normal instrument** (no step flags, vs the champion) on all 16 dev worlds, only for settings
     that screened Δ > 0. The fast instrument is fine for paired screening but **not neutral** (the champion lost
     €414 ± 131 on holdout with it), so every number you report as a result comes from the normal instrument.
  3. Use 32 fresh worlds (`--seeds night-01,...,night-32`) only for a candidate that is SAFE on dev with t >= 2.

  At most 4 settings per question, chosen by reasoning from your counters. No blind grids.
- **Slot-free work first.** Reveals of finished practice worlds (`uv run lab reveal <world>`) and results files cost no
  slots. Size an idea with them before you build it.
- **Tail matters as much as mean.** The final is one secret world: report the worst on-time share and the number of
  worlds under 92%, every time.
- **Push after every finished measurement** (`git push -u origin HEAD`), so nothing is lost if your session ends.
- **Ideas are welcome.** If you see a promising idea that you won't test yourself, write a brief (the shape of
  `experiments/prompts/day/*.md`: the idea, why, the flags, what to measure) to
  `$HOME/spread/runs/night/queue/9<HHMM>-<slug>.md`, at most two per session. The next free agent takes it.
- Practice pauses by itself during the test finals (13:40–14:50 and 19:40–20:50 Helsinki). If an eval prints
  "Practice paused", work on code or reveals meanwhile, and don't kill it.
