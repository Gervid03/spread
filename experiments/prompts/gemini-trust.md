Idea #4 of experiments/IDEAS.md, "Trust is capital: count it exactly, buy it on Monday, never gamble it".
Implement the three parts as separate flags, defaults off: (a) `trust_gain` (0): count each dealer's on-time
orders exactly from the ledger (a revenue line without a late refund raises the count by 1 up to 25; a
late_refund or undelivered_penalty halves it, rounded down) and multiply that dealer's quote by
1 + trust_gain x count/100; (b) `trust_invest` (0): a discount on safe requests (pickup supply >= 100, slack
>= 6 h, no note) for the three dealers with the most requests so far, until their count reaches 25, Monday to
Wednesday only; (c) `trust_guard` (off): for a dealer with a count of 13 or more, decline requests with
same_day in a thin town or a drive over 300 minutes instead of pricing them. Keep the count correct in
`rejoin()` too (rebuild it from the ledger events in the history).
Add `stats`: the top dealer's count at each day's end, mean price/list by weekday. Measure (a) alone first.
