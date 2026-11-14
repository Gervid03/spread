## How you work (the Carbon protocol, Sat 14 Nov 09:30 Helsinki)
You are one of two Gemini 4 Carbon agents that replace the Argon swarm. Fewer agents, more thought per test.
**Practice worlds are the lab's bottleneck** (8 per team, shared with the other Carbon), so every world you play
must answer a question. Think, read code and reveals first; test second.

- **Build on main (champion v3)** and compare with the champion as usual (paired, same seeds, no `--vs`).
- **Flags with neutral defaults.** Every mechanism gets Params fields whose defaults reproduce v3. Check that once on
  `--seeds smoke` (Δ must be €0.00) before any real test.
- **Screen before you spend.** For each setting: `--seeds-from smoke` (2 worlds) to catch crashes and
  nonsense, then **8 dev worlds** (`--seeds dev-01,...,dev-08`). Go to the full 16 only if those 8 show Δ > 0. Go
  to fresh worlds (`--seeds night-01,...,night-32`) only for a candidate that is SAFE on all 16 with t >= 2.
  Write your own seed lists with `--seeds`. Never sweep blindly: at most 4 settings per question, chosen by
  reasoning from the stats you added.
- **Measure the mechanism, not just the margin.** Add counters to `desk.stats` (how often it fired, wins, late
  ones, euros) and read them on smoke before running dev. A mechanism that never fires can't be tested on dev.
- **Slot-free work first.** Reveals of finished practice worlds (`uv run lab reveal <world>`) and the results files
  cost no slots. Use them to size an idea before building it.
- **Tail matters as much as mean.** The final is one secret world: report the worst on-time share and the worlds
  under 92%, every time.
- **When you have a winner** (SAFE on dev with t >= 2 and no worse a tail on 32 fresh worlds), push your branch, write
  the note, and say so in your last message. Don't promote: the lead does that with `scripts/promote.sh`.
- Commit and push your branch after every finished measurement (`git push -u origin HEAD`), so nothing is lost if
  your session ends. Your note goes in `experiments/` as usual.
- Practice pauses by itself during the test finals (13:40–14:50 and 19:40–20:50 Helsinki). If an eval prints
  "Practice paused", keep working on code or reveals; don't kill it.

## Your task, in two parts
Part 1 is slot-free and feeds the other Carbon, who builds idea 31 (the route network) right now: finish it first, push the note, then start part 2.

### Part 1: R15, the network census
Research R15, the network census (for idea 31, the user's route network): no policy change, no practice worlds beyond
reveals (one request each). Use the reveals already on this machine (`/tmp/reveals-v3`, `/tmp/reveals-n14-01`; v2 and
v3 share seeds, rosters and requests) and reveal the rest of v3's dev worlds from `champion/results/dev-L8.jsonl` if
they are missing. Read docs/GAME.md, idea 31 in experiments/IDEAS.md and the R11 section of
`experiments/20261114-0635-gemini-snow.md` on `origin/exp/gemini-n14-06263-snow-and-hitch-research` first; extend R11,
don't repeat it. Write one standard-library script, `experiments/scripts/scout_network.py`.

Questions, each as a table per week (mean over the worlds, and the range):
1. Finishes. Every car of ours that was delivered: the driver (`gigs.csv`), their home (`drivers.csv`), the delivery
   place and minute. How many of our drivers finish in each town per day, in 2-hour blocks. How many of them finish
   more than 30 km from home.
2. Continuations. For each finish, the requests of any outcome (won, lost, declined) whose pickup is within 15 km and
   within 30 km of it, whose car is ready between 1 hour before and 3 hours after the finish, and which that driver
   could still deliver on time by road minutes. Split them: delivery within 30 km of that driver's home (home-bound),
   delivery in the capital, other. Count requests, not pairs, and also the disjoint pairs (each finish and each request
   used once, home-bound first).
3. Redundancy. For each continuation request in 2: how many of our finishing drivers were candidates for it (0, 1, 2,
   3, 4+). This tells us whether offering to three at once is possible, or whether a pickup usually has one candidate.
4. Organic chaining. Driver-days with two or more of our gigs; for each consecutive pair: the distance from the first
   delivery to the second pickup, whether the second pickup is within 30 km of the driver's home (a notification could
   reach them) or not (they found it some other way), the minutes between, and the second booked fee ÷ its typical fee
   against the first. And how many views (`views.csv`) came from drivers who were working one of our gigs at the time.
5. Seeding. Requests we lost or declined that leave a pickup with ≥ 100 drivers within 30 km and deliver within 30 km of
   a town that sent ≥ 6 requests that week: per week, our quote ÷ list on them, and how many continuations (as in 2)
   each would have opened had we won it.
6. The size of the prize, as arithmetic from 2 and 3: extra orders a week if a continuation offer is accepted with
   chance 0.2, 0.4 or 0.6 and each request has the candidates measured in 3, split home-bound and not.

Write experiments/<YYYYMMDD-HHMM>-gemini-research-network.md with the tables and a short verdict for idea 31: is the
network big enough to matter, is redundancy (several candidates per pickup) common or rare, and do home-bound
continuations exist in useful numbers. Commit the note and the script and push. The paired-delta line of your three
closing lines is "+0.00 (research only)".

### Part 2: chains by a return offer to our own driver
Idea 26, the return-offer form: build on the champion on main (v3), no merge needed, and compare with the champion
as usual. This is the day's biggest volume bet, so take care with the details. Read docs/GAME.md, then idea 26 and
12(a) in experiments/IDEAS.md, and the R11 table in `experiments/20261114-0635-gemini-snow.md` on
`origin/exp/gemini-n14-06263-snow-and-hitch-research`.

Why: the leaders win ~430 orders a week, we ~280, and drivers are our constraint, not demand (thin-town quoting
alone took drivers from the other orders, `n14-05162`). R11: 165.7 of our declined slow requests a week pick up
within 15 km of where one of our won orders delivers on the same or previous business day, inside 12 hours of driving.
That's 94 disjoint chains a week, ~30–38 extra wins at our win rate. Our gigs book within minutes, so a return car
rarely finds an unbooked partner gig. The handbook names the channel that works after booking: a direct offer
"reaches a driver whom a notification does not, for example a driver who finishes one of your gigs far from home",
and a driver who is working one of our gigs today does read offers.

Implement in src/spread_lab/policy.py, flags off by default (A noop must show +0.00 on every smoke seed):
- Track every booked gig's driver and the planned delivery minute and place of each of its cars (from `gig_booked`
  and the gig's stops and road minutes; rebuild in `rejoin()` from the snapshot's gigs).
- `return_offer_km: float = 0.0` (0 = off): a request that fails the supply gate is quoted for its slow options when a
  driver of ours delivers within this many km (straight line) of its pickup, before the pickup window closes, with
  time to reach it and still be on time with `min_slack_min` to spare. Try 15. Price: the tracker's price ×
  (1 + `return_markup` (0.0)). At most `return_cap_day` (8) such wins a day. These quotes don't move the tracker.
- On winning one: post its gig as usual, but at `return_fee_open` (0.75) × the typical fee (the driver is already
  there), and send that driver a direct offer of it at `return_offer_mult` (0.9) × the typical fee, timed for when
  they deliver (an offer lasts 10 minutes, a driver gets at most 3 a day, a gig at most 3 open: respect the limits
  that `offers_per_warning` code already knows). If the offer is declined or expires, the gig stays on the board and
  climbs as usual.
- Counters: `ret_quoted`, `ret_won`, `ret_offered`, `ret_accepted`, `ret_late`, `ret_margin_cents`, and how often the
  outbound driver had already finished and gone home.
Smoke: `return_offer_km` 15 with the cap 4, then 8; once with `return_fee_open` 1.0. Dev: the best two. The hard rule
is that every dev world stays ≥ 92% on time. Report the worst world first, then won orders a week and margin against
the champion. If offers are rarely accepted, say why: timing, fee, or the limits.
