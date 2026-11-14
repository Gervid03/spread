## Your layer: `tas-routes`, the travelling salesman (tours planned with the whole week known)
Branch `exp/gemini-tas-routes`. World: **dev-12** first. Steps 1 and 3 need no forks: start there. Read
`~/.spread-lab/tas/STATUS.md` (from `tas-price`) before your first fork-heavy run.

**The idea.** A car is an arc: a driver takes it from its pickup to its delivery, and is then on foot. The typical fee
pays a driver for the drive, the trip to the pickup and the trip home, and the trip home is the dear one (a ticket
bought on the day; small towns have a last connection). A tour in which every delivery is where the next car waits,
and which ends where the driver lives, has no trips to pay. That is the travelling salesman's problem on arcs (the
stacker crane problem) with time windows, at most 12 hours of driving a gig, a prize for each car and many drivers.
A desk sees one request at a time. With the tape you know every arc of the week on Monday 07:00, and the map has only
30 places.

**What we know.** Pairs found by the live desk, without foresight, booked at 0.75 × the sum of the two typical fees
and were 99.8% on time, for +€644 a week (`git show origin/exp/fable-roundtrip:experiments/20261114-0836-gemini-hitch-pairs.md`;
that branch also holds `rt_hold`, a round-trip book). R11 counted 94 disjoint return chains a week among the declined
requests alone. Pairs that drive away from home were split and late: tours must close.

**1. The census (no forks; a tape is a dozen requests).** `tas.py tape` for the four TAS worlds. One arc per request
and option: the option sets the deadline, and a slower option gives a day to line cars up (it also has a lower list
price: the planner chooses). "b right after a" is feasible when the ready times and the opening hours at both ends
allow it, the trip from a's delivery to b's pickup is short (zero at the same place; by road minutes otherwise), both
deadlines hold with slack, and the gig stays under 12 hours of driving. Count round trips (A→B, B→A), triangles and
longer closed tours, shuttles on one lane (A→B, B→A, A→B, …), and open chains that end where drivers live. How many
of the week's requests fit in a tour of two or more cars that starts and ends within 30 km of a town with drivers, by
day and by town? Read notes with the desk's reader (`notes.py`) and keep unsure notes out of tours. (A TAS can also
learn what a note meant: win the car in a throwaway world and read `LegTruth` in the reveal.)

**2. The prize and the cost of a tour.** Prize: the dealer's limit (`limits-all.jsonl` from `tas-price` when it is
there; until then the limits of the orders the champion won, or 1.35 × list). Cost: start from the minutes at the
wheel, then measure. For a planned tour whose cars are won, post it as one gig at a flat fee on forks and bisect the
fee (`on_fork` in `scripts/tas.py`): the fee per hour at the wheel for tours of 1, 2, 3 and 4 cars, closed and open,
by town. A dozen measured tours are worth more than a model.

**3. The plan.** Disjoint tours with the highest total prize minus cost, within what each town's drivers can carry
each day (the roster gives homes; who works is hidden, but the champion's week shows how many different drivers
booked from each town each day). Greedy by profit per driver hour, then local search (move a car between tours,
exchange tails, drop a car). An exact solver is welcome offline (`uv run --with ortools …`), but a good plan today
beats an optimal one tomorrow.

**4. Play the plan, with re-recording.**
- Quotes: a price book that names the option for each planned car and declines the rest
  (`{"<request id>": {"option": "next_day"}, "*": "decline"}`); `tas.py limits --book plan.json --apply` wins each at
  its dealer's limit in one pass and writes the book of what it sent, which `tas.py run --book` replays with no fork.
- Staffing: a Desk subclass, `src/spread_lab/policies/tas_routes.py`, that knows the plan: it holds a tour's cars
  until the tour is complete or its first car must go, posts the tour as one gig (stops in order, windows from the
  notes, the handling rules as the desk applies them), and falls back to single gigs when a tour breaks: a quote
  lost, a cancellation, a change of plan, a drop near the pickup.
- Replay, see what broke, repair the plan, replay. Hold the on-time share at 92% or more.

Report cars per driver day, the fee per car in tours against single gigs, and the margin against the champion on the
same world.

**5. The rule for Sunday.** Which of these tours could a desk have seen coming without the tape? Across the four
tapes: on which lanes does a return car arrive within a few hours on most days (part of a lane "is almost the same in
every world")? A table "after A→B is won, a B→A request comes within H hours with probability p" lets the live desk
price A→B knowing its return, and hold the gig for it.
