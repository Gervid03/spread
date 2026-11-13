Idea #11 of experiments/IDEAS.md, parts (b) and (c), with the data we already hold. No harvest worlds.
- Data: reveal 8 of the champion's dev worlds (ids in champion/results/dev-L8.jsonl; `uv run lab reveal
  <world id>`, outside the repo). legs.csv has, for every won order, the truth of its note: `readyAt`,
  `releasedAt`, the real `pickupHours` and `deliveryHours`, `manualGearbox`, `needsPlates`, `summerTyres`,
  `noteDeadline`. requests.csv has the note text. That is about 750 won orders with a note.
- Score src/spread_lab/notes.py on them with a script, experiments/scripts/score_notes.py: for each field,
  how often the reader agrees with the truth, and the 30 most common misses with their note text. Fields:
  ready time (to the minute, and to the day), release time, pickup closing time, delivery closing time, the
  note's deadline, manual, plates, summer tyres. The rules say how days and times read (RULES.md, "Notes
  and changes of plan"): days count from the arrival day; "huomenna / i morgon / tomorrow"; a weekday name
  is 2 to 6 days ahead; an hour in words is a working hour ("two" is 14:00, "half three" is 14:30); "am"
  and "pm"; a correction counts and a denied time does not.
- Fix the reader for the misses, field by field, behind `note_reader: str = "v1"` ("v2" = the new reader), so
  the champion is unchanged by default. Keep it a pure function of the text and the windows. Split the 8
  worlds: fix on 5, report the score on the other 3.
- (c) `note_at_quote: bool = False`: in `price`, the note's delivery hours and its tighter deadline shorten
  each option's slack (today only the pickup's ready time does). `note_unsure: str = "quote"`: with
  "decline", a request whose note has digits or a weekday that the reader could not place is declined.
Measure: smoke then dev with `note_reader=v2`, then with `note_at_quote`. Report the failed-visit, waiting
and late-refund lines and the three `visit_failed_*` counters next to the margin.
