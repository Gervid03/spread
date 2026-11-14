## Your task: c4, spend the unused on-time budget on easy orders (the user's buffer idea)

The user's argument (14 Nov): short orders from pools with many drivers are almost never late, so they are the buffer
that lets riskier orders fail without breaking the 90%; and a win is worth more than its margin (trust, routes). The
team's earlier finding points the other way: lowering the price everywhere ("tax back" through
`price_target_win` 0.45) was unsafe and worth €100–160, because it cut the price of cars we would win anyway. This
task tests the narrow form the user means: cheaper only on easy classes, and only while the week has budget to spare.
v3 runs ~96–97% on time against the 92% we aim for, so about ten late orders a world go unspent.

Implement in policy.py, flags off by default:
- `buffer_discount: float = 0.0` (0 = off) and `buffer_hi: float = 0.955`. "Easy" = pickup with ≥ 100 drivers within
  30 km, drive ≤ 120 minutes, not same_day after 13:00, no note (or a note the reader is sure of). While the projected
  on-time share (`projected_on_time()`, with `guard_min_orders` as its floor) is ≥ `buffer_hi`, easy requests are
  quoted at the tracker's price × (1 − `buffer_discount`); below it, as usual. These quotes don't move the tracker.
- Counters: `buf_quoted`, `buf_won`, `buf_late`, `buf_margin_cents`, the minutes the budget gate was open, and the
  on-time share at the end.
If c3 has written its late classes (`experiments/*research-acceptance*` or its branch), use its "under 2% late"
classes as "easy" instead of the rule above, and say which you used.

Settings (screen on smoke, then 8 dev): `buffer_discount` 0.05 and 0.10 at `buffer_hi` 0.955; then the better one at
0.945. The question to answer: does extra easy volume add margin, and does it let the champion's own risky classes
fail more safely (look at the worst world)? Report the worst world first, won orders a week, and margin against the
champion.
