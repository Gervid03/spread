## Where you start: `tas-price`, the price oracle (every order at its dealer's limit)
Branch `exp/gemini-tas-price`. World: **dev-12** first. You go first: the other three wait for your `STATUS.md`, so
do step 0 before anything else. After that the steps are a first path, and you have a free hand (see above).

**Why.** The desk prices with one multiplier that tracks a win rate, and floors 341 of 837 quotes on dev-12. It never
learns what a dealer would have paid, only won or lost. A fork tells: quote, advance to `respondBy`, read the answer,
delete the copy. Bisected, that is each dealer's limit to within 0.4% of the list price.

**0. Validate the instrument on the real server.** The laptop lead did part of it on Sat 12:45–13:00 (read
`~/.spread-lab/tas/STATUS.md` first): `run` gave v4's dev-12 week to the cent; `limits` and `limits --apply` to
Mon 14:00 measured 32 of 32 won orders exactly, with no `CHECK`, at ~190 forks a minute. The champion is now **v5**
(cp-fees). What is left, in this order:
- `uv run python experiments/scripts/tas_selftest.py` passes.
- `uv run python scripts/tas.py run --seed dev-12` must give v5's week **to the cent** (`tas.py show --seed dev-12`
  prints it: €10,910.49, 246 won, 98.0%). If it does not, the wrapper around `world.act`/`world.advance` is the
  suspect.
- `tas.py tape --seed dev-12`: about 1,036 requests. Check the foresight claim: the tape's requests are the ones the
  desk saw in its own week (same ids, list prices, `respondBy`).
- `tas.py limits --seed dev-12 --until "Tue 07:00"` against `tas.py run --seed dev-12 --until "Tue 07:00"`: the main
  line must be the same to the cent (forks must not move the parent), and the output must not say `CHECK` (one fork
  tests many requests at once, on the claim that dealers decide each request by itself). Note the seconds per fork on
  Monday morning and Monday evening.
- Write `~/.spread-lab/tas/STATUS.md`: what holds, what you fixed (and the commit), the cost of a fork, and when the
  shared files below are ready. Keep it current: the others read it.

**1. Layer 1: the champion's week at perfect prices.** `tas.py limits --seed dev-12 --apply`. Check the claim that
only prices change: the same number of orders, the same on-time share, the same `driver_fee` to the cent. Replay
`book-won-apply.json` with `tas.py run --book`: the same margin with no fork. Then dev-01, dev-08, dev-07. This is
the first step of the waterfall, and `limits-won-apply.jsonl` is the first shared file.

**2. The demand curve.** `tas.py limits --seed dev-12 --mode all --iters 6 --name all` measures every option of every
request, declined ones too (about three times the forks of step 1: start with `--until "Wed 07:00"`, look, then
decide on the rest). From it:
- the week's revenue if every request were won at its limit (a bound, before any driver is paid);
- limit ÷ list by day and hour (the price war day: about 20% lower everywhere 08:00–18:00; the outage: about 30%
  higher in one town and 80 km around it), by lane, by option (is `next_day`'s limit the same multiple of its list
  price as `same_day`'s?), by the dealer's trust count (is the +1% a count there?), by our share of the dealer's
  requests the day before (the competitor's morning reaction);
- the requests the desk lost whose limit was above its own floor, and the declined ones whose limit was above
  1.25 × the typical fee ÷ 0.92.

Say in `STATUS.md` when `limits-all.jsonl` is there: `tas-routes` and `tas-state` plan with it.

**3. Layer 2: choose with the oracle.** A desk that knows every limit before it quotes sells at the limit what is
worth having and declines the rest. Keep the champion's staffing. Start from its own gates (supply, slack, backlog)
and replace the price floor by the true test (the limit covers the expected fee and the margin). Mind the driver
ceiling: past about 280 orders a week the on-time share falls. A selection is a price book
(`{"<request id>": {"option": "next_day"}, "*": "decline"}` with `tas.py limits --book <file> --apply` prices each
chosen request at its limit in one pass), or a Desk subclass with `--policy`. Each variant is one week.

**4. The rule for Sunday.** Where is the desk's price furthest below the limit: which class, day, trust count,
dealer? Is the limit ÷ list of a lane stable across the four worlds (a lane table for Monday morning, idea 28)? Would
a price that follows trust (+1% a count) have taken part of it (`trust_gain` exists as a flag)?

**And your own ideas.** The oracle answers any question about dealers that you can put as a fork. Some we have not
looked at, to start you off; yours will be better. Does a dealer take a dearer `same_day` over a cheaper `next_day`
when both are quoted, and can a second option be used as a decoy? Do requests of one `batchId` decide together? Does a
quote sent in the last minute before `respondBy` meet a different limit than one sent at once? What does a lost quote
or a declined request do to that dealer's next limit? Is there a price the competitor's morning reaction cannot see?
Test what you think of, on forks, and write down what you find.
