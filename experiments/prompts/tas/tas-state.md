## Where you start: `tas-state`, the hidden state steered, and the full stack
Branch `exp/gemini-tas-state`. World: **dev-12** first. Read `~/.spread-lab/tas/STATUS.md` (from `tas-price`) before
your first fork-heavy run; the tape and the planning below need no forks. The four levers are a first path, and you
have a free hand (see above): yours is the widest brief, so expect your best finding to be one we did not list.

**The idea.** A desk answers each request as it comes. A TAS knows the week, so it can pay early to change what the
dealers and the competitor do later. Four levers. Measure each as a Δ on top of layer 1 (the champion's week at
perfect prices: `tas.py limits --apply`, there from the first hour), each on the same world.

**1. Trust, farmed.** Each dealer accepts +1% for every order we delivered to it on time, up to 25. The tape says
which dealers send the most and the dearest requests late in the week. One more trust point for dealer D at minute t
is worth 1% of the limits of D's later cars that we will win. So win D's early, easy cars (short, from a hub, with
slack) even at a thin margin, and deliver them early: the count moves at delivery, so `same_day` and Monday's cars
count first. The champion does this blind (`trust_invest` 0.05 for its three busiest dealers until Wednesday). With
foresight: which dealers, which cars, how many? The limits file shows each dealer's trust count beside limit ÷ list,
so the +1% can be checked.

**2. The competitor, steered.** Each morning it lowers its prices for a dealer where we won most of its recent
requests and raises them where we won few, a few steps at most. Its price is the dealer's alternative, so our limit
follows it. Measure the size first: two weeks that differ only in one busy dealer's Monday (win everything, decline
everything), then that dealer's Tuesday limits. If it is worth it, plan each dealer's share by day, so that the cars
that matter are quoted the morning after the competitor raised.

**3. The event days, known in advance.** The first `limits` week shows them: the price war (every limit about 20%
lower, 08:00–18:00, one day), the outage (limits about 30% higher in one town and 80 km around it, one day), and the
drivers show the flu day. Then plan around them. On the war day win little, and give its drivers the cars won on
other days with slower options (`next_day` and `within_3_days` cars can be delivered then). In the outage region win
everything that can be staffed, at the higher limit. Before the flu day win less for that day. The bulk order (30–40
cars from one yard, one `batchId`): which of its cars are worth having?

**4. The lateness allowance.** Ranked needs 90% on time. A car up to 2 hours late costs 10% of its price, and halves
its dealer's trust. Where is a late car worth it: a dear `same_day` whose only driver arrives at 20:30, a dealer who
sends nothing more this week? Report every number at ≥ 92% and at the edge.

**How.** These are choices of what to win, when, and at what price: a price book built offline from the tape and the
limits (`{"<request id>": {"option": "same_day"} | "decline", "*": "desk"}`), or a Desk subclass that loads the tape
(`src/spread_lab/policies/tas_state.py`, with `--policy`). A book entry without a price is priced by the oracle:
`tas.py limits --book <file> --apply` plays the book at each dealer's limit in one pass. Limits move when the state
moves, so a price found on another line may lose: take final numbers from `limits --apply` on your own line, and
replay its book with `tas.py run --book` to check.

**You also own the full stack.** When `tas-fees` and `tas-routes` have their layers (`STATUS.md`, `git fetch`,
`tas.py show`), assemble the table the user asked for on the four TAS worlds: the champion's week, + perfect prices,
+ perfect fees, + tours, + state, with won orders, on-time share and margin at each step, and one paragraph on what
the ceiling says about where our desk stands. Write it at the top of your note.

**The rule for Sunday.** For each lever: what does the live desk see that tells it the same thing? The dealer's
request count so far predicts its later volume (trust); a morning win share per dealer is a number the desk already
has (the share band, idea 29); a run of losses at 08:00 marks the war day, and a run of wins in one region the outage.

**And your own ideas.** Everything the world remembers about us is a state someone could steer. Some to start you
off; yours will be better. Lookahead as a method: `tas.py whatif --pick` chooses the best of several settings each
morning from forks (the lead's game made +€416 that way with one dial; what do ten dials and a pick every hour
make?). What drivers have learned about our fees by Wednesday, as a state to manage. Satisfaction: what one late car
costs in that dealer's later limits, measured. Quoting a request we do not want at a price that loses, against
declining it at four times the list: does the competitor see a difference? Which hidden state is worth the most
per euro spent on it? Test what you think of, on forks, and write down what you find.
