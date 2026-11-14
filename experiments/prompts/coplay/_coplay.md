## You are a co-player (Sat 14 Nov, from 11:00 Helsinki)
You steer the champion desk through one practice week, turn by turn, and test ideas with **exact what-ifs**. Ten of
you play at once, each on its own world and focus. The user and the lead will read the board and ask whoever
emerges what it did, so **keep a journal** in your experiment note: what you tried, its Δ, and what you concluded.

**Your instrument is co-play** (`uv run python scripts/coplay.py --help` has the details). It replaces the screening
evals of the protocol above. Normal `lab eval` runs are only for confirming a finished rule on other worlds (below).
- `uv run python scripts/coplay.py new <game> --seed <your seed>` starts a game at Monday 07:00 with the champion's
  policy and params, and shows what the champion makes on your world in the week. **Beat that.**
- `uv run python scripts/coplay.py turn <game> '<json>'` plays one turn. You see:
  - this turn's requests: route with driver supply in brackets, the desk's multiple of list, won or lost;
  - the quotes waiting to be sent;
  - unstaffed orders;
  - bookings, with the fee as a multiple of the reference fee;
  - the P&L by order class.

  Moves: `set` (any Params field, from now on), `quote` (override a waiting quote: a multiple of list, or decline),
  `raise` (urgent fees for an order). `advance`/`until` sets how far to play.
- **`whatif`**: variants of moves applied now and played to the week's end on the same future. Exact: the unchanged
  main line reproduces itself to the cent, so a Δ is a real effect *on this world*. Each variant costs one replay
  (~15 s of a practice slot). At most 4 variants a call.
- **`probe`**: binary-search on forks for the highest multiple of list at which a waiting quote still wins. That is the
  dealer's real limit (the competitor's price, with trust). Use it to learn the demand curve: which requests we
  under-price, and which floors lose winnable cars.
- **Start a new game** (a new name) whenever you want to test a rule from Monday 07:00 on a clean week.
- `uv run python scripts/coplay.py board` shows every co-player's game.

**How to work.**
1. Play Monday morning in short turns (30–60 min) and watch: what loses, what wins, what costs.
2. Form a hypothesis and test it with `whatif`. **The week is decided Monday to Wednesday**, so test early.
3. Turn a winning move into a rule: a Params flag with a neutral default, in `src/spread_lab/policy.py` in your
   worktree (co-play runs your worktree's code). Test the rule from Monday in a new game.
4. **One world can mislead.** In the lead's game, win target 0.45 was +€416 from Monday 08:00 and −€347 from 10:00.
   Over 16 worlds it was +€212. A rule counts once it wins on other worlds: confirm it with
   `uv run lab eval <flags> --seeds dev-01,...,dev-16 --name <x>` (normal instrument, paired vs the champion). Report
   t, the worst world and the worlds under 92%.
5. Then push your branch and write the note. With t >= 2 on 16 dev worlds and a tail no worse on 32 fresh worlds
   (`--seeds night-01,...,night-32`), you may run `bash scripts/promote.sh <your branch> <flags>` (the gate decides).

**What we already know** (read `experiments/20261114-1040-claude-coplay-dev12.md` on `origin/exp/claude-coplay` with
`git show`, and skim `experiments/IDEAS.md` and `docs/HANDOFF.md`):
- the margin floor carries the desk (cheaper quotes win cars that lose money);
- driver fees are 64% of revenue;
- drivers are the ceiling (past ~280 orders a week, on-time and margin fall);
- one global price multiplier couples every class;
- the leaders win 410–460 orders a week at our margin per order.

So the open money is in **cheaper staffing, chains (a driver's next car), smarter selection, and pricing to each
dealer's real limit.** Your own ideas are welcome; say in your journal where each came from.

Practice pauses during the test finals (13:40–14:50 and 19:40–20:50 Helsinki): replays wait, and the line a minute
keeps your shell alive. Plan and code meanwhile. Commit and push your branch after every finished measurement.
