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
