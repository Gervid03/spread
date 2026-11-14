## Your direction: `r4-volume`, closing the gap to the leaders
Branch `exp/gemini-r4-volume`. Leaders win 410–460 orders a week at about our margin per order; we win 250–345.
Drivers are the ceiling: past ~280 orders a week our on-time share and margin fall. So volume means **more cars per
driver-hour**, not just cheaper quotes.
- Start by measuring where the capacity goes on one world (co-play `new` + `turn` on a dev world): driver idle time,
  empty kilometres between a delivery and the next pickup, orders declined for supply, `next_day` and `within_3_days`
  options we never quote, multi-car batches.
- Ideas to test (the LEDGER says what was already tried): chains (a driver's next car starts where the last one ends;
  cp-chains and cp-routes did part of this), quoting the slower options where drivers are thin, batches, taking more on
  the days with spare drivers and less on the tight ones, Friday's endgame (no requests after Friday).
- Keep the on-time share above 92% on every world: a run under the delivery minimum is not ranked, and that costs the
  whole run.
