## You are engineering the TAS: the theoretically best week (Sat 14 Nov, from 13:00 Helsinki)
**This task replaces the protocol above** (its steps 1–7, the turn budget, the smoke and dev evals, the three-line
ending). The conduct rules stay: never print a key, never touch `lab.py`, `runner.py`, `env.py`, `seeds/` or
`champion/`, never run `lab board`, `lab final`, `lab promote` or `lab reap --force`. You have about 300 model turns.

**The user's ask.** "I want a theoretically perfect TAS run. I want to see the bare potential: what we get if we
always get the best achievable margins, and on top of that apply the ideas of the travelling salesman." A TAS is a
tool-assisted speedrun: a perfect play built with savestates, re-recording and knowledge of what comes. Four of you
build it, each starting from one layer. It will never play the final (the final has no forks and no foresight), so
nothing here is promoted. It gives the team two things:
1. **The ceiling, as a waterfall on the same worlds**: the champion's week → + perfect prices → + perfect fees →
   + tours planned with foresight → + the hidden state steered. One measured number per step, with the on-time share.
2. **Where our desk leaves the money**, and for each layer **the rule a desk without forks could use** to take part
   of it on Sunday. That second part matters as much as the number: the final is at 08:00 tomorrow.

### You have a free hand
The user's words: "I want the agents to have a wide range of freedom to test their own ideas and compare them on
forks. I trust them."
- **Your layer is where you start, not a fence.** The steps in your brief are a first path that we could see from the
  rules. Follow them while they pay. Drop a step that looks poor, reorder them, go deeper where the money is, and
  leave your layer when you find something bigger elsewhere.
- **Your own ideas come first where they look better.** Anything a dispatcher with savestates and foresight could
  do is in scope: a different way to price, to choose, to staff, to route, to time, to bluff the competitor, to use
  the rules' edges. If you can state it, you can test it: play it on forks against a control (`tas.py whatif`,
  `branch`), or re-record the week with it. Let the forks decide, not our guesses and not yours.
- **The tools are yours.** Extend `scripts/tas.py`, write your own oracles and planners, subclass the desk, add a
  package for offline work. Nobody approves your experiments. Forks are there to be spent.
- **What stays fixed** is short: the conduct rules above; the truth of your numbers (a number is from the real
  server or it says "toy world"; one world is one world; a ranked week needs 90% on time); a fair share of the
  slots (the lanes below see to it); and telling the others what you do (`STATUS.md`), so two of you don't spend a
  day on the same thing by accident. On purpose is fine: two approaches to one question is a result.
- If your worktree already holds your commits or a note, you were restarted: read them and carry on.

### The three tools a practice world gives you
- **Savestate.** `fork` copies a world at a minute with the same future draws. Try something on the copy, read what
  happens, delete the copy; the main world never moved.
- **Re-recording.** The same seed and the same actions at the same minutes give the same week to the cent. A week is
  its inputs: keep them (a price book, the code, the flags) and you can replay, change one decision and replay.
- **Foresight.** Every team gets the same requests whatever it does (HANDBOOK: "Satisfaction does not change the
  requests"). A silent week (`tas.py tape`) therefore lists every request of the week, with its lane, options, list
  prices, typical fee, note and minute, before you quote the first one. The driver list and the forecasts too.

### The hidden numbers a fork can read out
- **A dealer's limit**: the highest price at which it still buys this request, now. Bisect it on forks (quote,
  advance to `respondBy`, won or lost). `tas.py` does this for a whole batch of requests with one fork per round.
- **A driver's price**: a direct offer is taken "when the fee pays for the gig and what else their day is worth"
  (no waiting game), and a flat fee in the app is booked or not. Fork, offer or post at a fee, advance, read.
- **Who works today, the price war day, the outage region and day, the flu day**: all show up in forks and in a
  first play of the week.

### What the world's rules say will and will not move (use these, and test them: they are claims until measured)
- The competitor "learns only whether it won each request" and reacts each morning per dealer; a dealer's trust and
  satisfaction move only with on-time and late deliveries; drivers never see a price. **So the same orders won at
  higher prices give the same week**: same gigs, same drivers, same lateness. Perfect pricing is an exact re-recording.
- Trust: +1% on the accepted price per on-time order of that dealer, up to 25; a late order halves the count.
- The competitor cuts its prices for a dealer where we win most of its requests and raises them where we win few.
- A driver's cost is the time at the wheel, the trip to the first pickup and the trip home (a ticket bought on the day
  is dear; small towns have a last connection). "For a driver who already has one of your gigs, a second gig costs
  only the extra time and tickets." A gig that ends where the driver lives, or where their next car waits, is cheap.
- Drivers learn the booked fee ÷ the first fee they viewed, and the minutes to the booking. A flat fee that books
  teaches nobody to wait. A driver hears of an order once, when its first pickup is within 30 km of home.
- A gig with several cars may plan at most 12 hours of driving, the drives between cars included.
- Ranked means ≥ 90% of won orders on time. Report every TAS number twice when they differ: at **≥ 92%** (the team's
  rule) and at the edge (**≥ 90%**; a car up to 2 h late costs 10% of its price and half that dealer's trust).

### The instrument: `scripts/tas.py` (read its docstring first; it is short)
It is this track's sanctioned way to play worlds: it takes the harness's slots, registers its worlds and forks, and
steps the desk exactly as `play_practice` does (through co-play's engine, `scripts/coplay.py`).
- `uv run python scripts/tas.py tape --seed dev-12`: every request of the week (`~/.spread-lab/tas/dev-12/tape.json`).
- `... tas.py limits --seed dev-12 [--mode won|quoted|all] [--apply] [--until "Tue 07:00"]`: the desk's own week,
  and the limit of every order it wins (or of every quote, or of every option of every request), bisected on forks.
  `--apply` also sends each won quote at its limit: the same week at perfect prices. Writes `limits-<name>.jsonl`
  (one line per request and option: `lo` is the highest price seen to win, `hi` the lowest seen to lose) and
  `book-<name>.json` (every quote it sent).
- `... tas.py run --seed dev-12 --book <file>`: the week again with a price book, no forks (re-recording).
- `... tas.py whatif --seed dev-12 --at "Tue 07:00" --variants '{"my idea": {"set": {"fee_open": 0.7}}}'`: **ideas
  compared on forks.** The desk plays to that minute; then each variant, and an unchanged control, plays a copy of
  the world to the week's end on the same future. Variants are co-play moves (`set` any Params field, also one you
  added; `quote` overrides; `raise`). With several times and `--pick` it applies the best variant at each time and
  plays on: a week steered by lookahead.
- `... tas.py show --seed dev-12`: everything measured on the seed so far, by all four of you.
- `-s key=value`, `--policy module:Class` (a Desk subclass) and `--name <label>` work on `limits` and `run`.
- In your own code: `from tas import Tas, on_fork, branch, forked, probe_prices` (add `scripts/` to `sys.path`).
  `Tas` is the game with a hook on every batch of actions before it reaches the world. `on_fork(game, actions, to)`
  tries raw actions on a copy and returns what happened. **`branch(game, variants, until)` plays whole ideas on
  copies, desk and all, against a control**: a variant can be a function that gets the copy's game and rewires its
  desk in any way (Params, books, methods, a hook), so any idea you can code is one call away from a Δ. Branch at
  any minute, as often as you like; apply the winner to the main line with `game.apply(moves)` and play on.
  Compare with the control, not with the main line (a copied desk can drift a little by itself).
- Quotes are easiest to change in a hook or a book. Staffing (which cars share a gig, the fee, offers) is easiest
  in a **Desk subclass** (`src/spread_lab/policies/tas_<your part>.py`, `--policy`), because the desk matches the
  world's answers to its own actions.
- **It was written in a session without the team key and tested only on a toy world**
  (`uv run python experiments/scripts/tas_selftest.py`, a few seconds, no network; the toy world is
  `experiments/scripts/tas_fakeworld.py`). Run the self-test first. `tas-price` validates the instrument on the real
  server before anything else and writes what it finds to `~/.spread-lab/tas/STATUS.md`; the rest of you read that
  file before your first fork-heavy run. If you fix `tas.py`, keep the self-test passing, push, and add a line to
  `STATUS.md` so the others pull your fix (`git fetch origin && git merge origin/exp/gemini-<slug>`).
- Use the toy world to test your own plumbing while practice is paused. Never read a margin off it.

### Worlds, files and budget
- **The TAS worlds: dev-12 first** (the champion's median world: €10,418, 254 won, 96.5% on time, driver fees 64% of
  revenue), then **dev-01** (its weakest, €7,488), **dev-08** (its richest, €14,637) and **dev-07** (the northern
  world: €42k revenue, the most late refunds). Get your layer right on dev-12, then measure it on the other three.
- `~/.spread-lab/tas/<seed>/` is shared by the four of you. Name your own files with `--name <your slug>-<what>`.
  `tas-price` owns the canonical `limits-won-apply` and `limits-all`.
- **Forks are yours to spend; the lanes keep it fair.** Ten co-players share the team's 8 practice slots with you.
  A game that forks holds two slots, and only two such games run at once on the machine, so this track never holds
  more than 4 of the 8. You don't have to ration beyond that. A third fork-heavy run prints "Waiting for a fork
  lane" once a minute until one ends: don't kill it. What it means in practice: a lane is the scarce thing, so a
  short look (`--until "Tue 07:00"`, a `whatif` with `--until`) that answers the question frees the lane for the
  next idea, yours or another agent's.
- For scale: a full `limits` week is about 3,000 forks (each a second or so, more late in the week: a copy's first
  answer carries its whole history); a `whatif` variant costs what the rest of the week costs. Start a long run in
  the background with its output in a file (`nohup uv run python scripts/tas.py limits ... > runs/<name>.out 2>&1 &`),
  work on something else, and read the file when you need it. Don't poll in a loop. If a run dies,
  `uv run lab reap` (never `--force`) frees its worlds.
- Practice pauses during the test finals (13:40–14:50 and 19:40–20:50 Helsinki). Runs wait by themselves. Plan,
  code and use the toy world meanwhile. Don't kill a waiting run.

### How you work, and what you hand in
1. Read `AGENTS.md`, `docs/GAME.md`, and in `docs/kit/` (`uv run lab docs`) the HANDBOOK's "How the world works"
   and RULES "Gigs", "Drivers", "Direct offers". The mechanisms above are quoted from there.
2. Keep a **journal** in your note, `experiments/<YYYYMMDD-HHMM>-gemini-<your slug>.md`: each idea, yours or ours,
   where it came from, how you tested it (forks, a re-recorded week, how many worlds), what it showed, and what you
   concluded. The failures too: an idea that lost on forks is material for the jury. Commit and
   `git push -u origin HEAD` after every finished measurement.
3. Your note ends with three things:
   - **The table**: for each TAS world, the champion's week, your layer, Δ margin, won, on-time share, forks used;
     and each stack you measured on top of another agent's layer.
   - **Achieved or bound.** A TAS margin is a week that was really played, so it is a floor on the ceiling, not a
     proof of the optimum. Where a cheap arithmetic bound exists (every request at its limit, every car at the
     cheapest fee ever booked for its kind), give it too, and call it a bound.
   - **The rule for Sunday.** For each euro you found: what would a desk without forks need to know to take part of
     it, and how would it know? If a rule looks worth testing today, test it yourself if you have the turns (a
     Params flag with a neutral default, then `uv run lab eval` on dev as AGENTS.md describes), or write a brief
     (the shape of `experiments/prompts/day/*.md`) to `$HOME/spread/runs/night/queue/9<HHMM>-<slug>.md`.
4. **Stack when your layer stands.** Read the others' notes (`git fetch`, `tas.py show`) and play your layer on top
   of theirs. The last table the user wants is the full stack on the four worlds.
5. Your last message: what you found (your layer's Δ on dev-12 and on the four worlds with the on-time share, and
   the best of your own ideas with its Δ), and the one rule for Sunday you would bet on.
