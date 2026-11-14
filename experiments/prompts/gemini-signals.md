Idea #23 of experiments/IDEAS.md, "Free signals the desk throws away", parts (a), (b) and (c). Three small
flags in src/spread_lab/policy.py, defaults off, measured apart on smoke and together on dev.
- (a) `ready_from_deadline: bool = False`. When a note makes a car ready a day or more later, `order_won`
  already carries the moved deadline. `retry_from()` uses that after a failed visit; use it at the first
  post. In `post` (and so in `win`, `change`, `rejoin`): delay = the order's deadline minus the deadline of
  the won option in the request, rounded down to whole days; when it is a day or more, move the pickup
  window's start by it, and read the note's clock time on that moved day (today `window_from_note` puts the
  clock time on the stated day). Counter `ready_moved`.
- (b) `eligible_supply: bool = False`. Build two more supply tables from the roster at start: experienced
  drivers only (rating >= 4.8 and completedGigs >= 50) and manual licences only. With the flag, a request
  with a premium car uses the experienced table, and a request whose note has the manual flag the manual
  table, for the supply gate, the ring test, the backlog limit and the same_day rule. Counters: premium
  requests quoted, won and late (`prem_q`, `prem_won`, `prem_late`), with the flag off too.
- (c) Keep the minute of each `release` event per order and leg (and from the history in `rejoin()`); when a
  leg is posted again after a failed visit, its pickup never starts before that minute if the release is
  still to come, and starts at once if it has come. Flag `use_release: bool = False`.
Report `visit_failed_not_ready`, the failed-visit and waiting lines of the ledger, and late orders, next to
the margin. These are small effects: say plainly when a result is inside the noise. No tax-back run.
