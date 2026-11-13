Idea #7 of experiments/IDEAS.md, "Bulk orders: budget the yard, count the quotes in flight".
Implement `yard_cap_ratio` (default 0 = off): per pickup town and deadline day, won-and-unstaffed orders plus
quotes in flight x `price_target_win` may not exceed max(`backlog_min`, ratio x supply). Quotes in flight are
the quotes sent whose outcome has not come yet. Within a batch (same `batchId`) quote the safest cars first
(slow option, short drive, towards a town with drivers) and decline the rest once the cap is reached.
Add `stats`: declined by the cap, and late orders that came from batches of 5 or more (track batch sizes
from the requests). This idea is about the worst world, not the mean: report the worst on-time share and
the worst world's margin next to the mean, on dev.
