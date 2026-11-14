The lead's re-baseline: no new mechanism, a faster instrument. `n14-06041-capacity-steps`
(`experiments/20261114-0623-gemini-capacity-steps.md` on `origin/exp/gemini-n14-06041-capacity-steps`) showed that
14-minute steps, with mornings and evenings driven by events, leave the margin where it is (+€26 ± 149) and the worst
world a little better (94.4% → 95.3%). They cut a world from 645 to 480 requests and from 16.5 to 10.2 seconds:
**1,747 → 2,820 worlds an hour** under the team's 8-world cap. To adopt it, the champion's stored results must be
re-measured with those practice settings, or every later comparison would mix instruments. `scripts/promote.sh` with
`REBASE=1` does exactly that, with gates for a neutral change. The settings only affect practice (`play_practice`):
the final's live loop never reads them.

You may run `scripts/promote.sh` once, as below. Never push main yourself, and never run `lab board`, `lab final`,
`lab promote` or `lab reap --force` by hand.

1. `git fetch -q origin`. If `experiments/PROMOTIONS.md` on `origin/main` shows a promotion after 06:12 UTC (the
   final-champion study may have promoted v4), the capacity branch still applies: its change is two `Params` lines and
   `runner.py`.
2. Run: `REBASE=1 bash scripts/promote.sh exp/gemini-n14-06041-capacity-steps -s step_min=14 -s busy_start_min=480 -s busy_end_min=1080`.
   If it refuses because the branch does not merge cleanly, make your own branch from `origin/main` with the same
   change (in `Params`, `busy_start_min: int = 420` and `busy_end_min: int = 1320` under `step_min`; in `runner.py`,
   `busy()` taking them and `play_practice` passing `desk.p`'s values, as on that branch). Check that
   `uv run lab eval --seeds-from smoke --name rb-noop` shows +0.00 against the champion, push it, and run the same
   command with your branch.
3. After PROMOTED, and only then: `git -C $HOME/spread fetch -q origin && git -C $HOME/spread reset -q --hard origin/main && git -C $HOME/spread log --oneline -1`.
4. Note: `experiments/<YYYYMMDD-HHMM>-gemini-rebase-capacity.md` with promote.sh's last ten lines, and the new
   champion's dev and holdout mean seconds per world and requests per world (`results.jsonl`). Your last three lines:
   PROMOTED or the refusal; seconds per world before and after; the main commit.
