## Your direction: `r4-live`, the desk made for real time (and faster practice for everyone)
Branch `exp/gemini-r4-live`. You own the question "does what wins in practice also win live?".
1. **Time the desk.** Write a small harness (e.g. `experiments/scripts/desk_timing.py`) that plays a practice world with
   any policy and params and records the wall time of every `handle`, `tick` and `send` call: p50, p99, max, and the
   calls over 50 ms, by event kind. Run it on v6 and, as soon as `exp/stack-v7` exists, on the stack with all its
   flags on. Report in `~/.spread-lab/tas/STATUS.md`-style notes in your experiment file, and tell the lead's ledger.
2. **Fix what is slow without changing a decision**: the same margin to the cent on the same world, only faster
   (caching, indexes, doing work once per minute instead of per event). That kind of change may be promoted as a neutral
   change (`REBASE=1 bash scripts/promote.sh ...`, see the header of `scripts/promote.sh`).
3. **Live-like practice.** The live runner (`play_live`) and practice (`play_practice`) differ: live answers every event
   as it streams, practice steps the clock. Find where the same desk can decide differently, e.g. a quote that would be
   sent after `respondBy` in wall time, or a tick that runs less often. If you can, build a practice mode that imposes the
   live order of events and the wall-time budget, and measure the champion in it.
4. **Fewer requests per practice week** (the organisers' advice; the team shares ~1,000 requests a minute): actions in
   the `advance` call (up to 50), `untilEvent` instead of stepping, the events from `advance` instead of `/events` and
   `/score` after each step. Count the requests a week takes now (`lab play` prints `requests`), and if the instrument
   can do it in far fewer with the same result to the cent, that speeds up every agent's evals: propose it in your note
   and push it on your branch; the lead decides about the instrument.
