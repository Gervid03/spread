Research, no policy change: protocol steps 1–4 don't apply. Write the note, commit it with your scripts, push.
**You create no worlds**: reveals of finished worlds cost one request each and hold no practice slot, so you run beside
the workers for free.

The question: **where are the ~160 orders a week that the leaders win and we don't, and what would it take to staff
them?** The leaders on the public level-8 board win 410–460 orders a run at 96–98% on time, at about the same €40
margin an order as ours. We win ~270. Read the directive at the top of experiments/IDEAS.md, idea 26 and research
items R6, R11 and R14 there, and the margin x-ray on `origin/exp/gemini-n14-01392-margin-xray-v2`
(`experiments/20261114-0200-gemini-research-margin-xray.md` and its script `experiments/scripts/margin_xray.py`):
reuse that script where you can.

Data: the 16 dev worlds of A, the night's base. Their world ids are in A's dev run,
`/home/lab/spread-wt/n14-03324-supply-adaptive-fee-open-and-drop-rescue/runs/20261114-034812-fee-drop-all180-dev/results.jsonl`
(the `world` field; check the path with `uv run lab runs | grep fee-drop-all180-dev`). Reveal each world once into a
folder outside the repo: `uv run lab reveal <world id>`. Also `GET /drivers` (the roster) is in the reveal or the snapshot.

Measure, for A's declined requests by class (pickup pool: capital, ring, 100+, 30–99, under 30 drivers within 30 km
and 55 km × option × drive band):
1. Volume: requests a week, list price, typical fee ÷ list, slack to the deadline, drive minutes.
2. Who could drive them: drivers living within 30, 55 and 80 km of the pickup, and within 30 km of the delivery (the
   inbound case, idea 24).
3. Pairs (R11, for idea 26): how many of them have one of our won orders that delivers within 15 km of their pickup
   the same or the previous business day, with time to chain both inside 12 hours of driving? And how many pair with
   another declined request (a round trip)?
4. From A's won orders: the late share and margin an order of the classes that sit closest to the declined ones (the
   ring and 30–99 pools), as a bound on what opening them could cost.

Output: `experiments/<YYYYMMDD-HHMM>-gemini-research-volume.md`, with one table per question. Under the tables, a
ranked list: each volume pool (orders a week a safe policy could add), the mechanism that would staff it (inbound,
chain, price-to-pay-far, quota), and the flags it would need. Commit the scripts under `experiments/scripts/`. Your
last three lines: the biggest pool and its size; the mechanism you would build first; the one number the lead should
watch when it is opened.
