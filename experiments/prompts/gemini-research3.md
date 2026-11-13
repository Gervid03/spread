Research items R6 and R8 of experiments/IDEAS.md. No policy change; one evaluation at most.
Skip protocol steps 1-4. Use reveals of finished worlds: `uv run lab reveal <world id>` writes a folder of
CSV files (run it outside the repo); the champion's world ids are in champion/results/dev-L8.jsonl. Reveal
the 16 dev worlds once into one folder and say where it is in your note. Do not reveal holdout worlds.
- R6, the class table at v2. Start from experiments/scripts/scout_classes.py. For every won order: late or
  not (a late_refund or undelivered_penalty line), its account (the sum of its ledger lines), the booked fee
  over the typical fee, minutes from the first post to the last booking, the number of drops. Tabulate
  orders, late share, margin an order and fee ratio by: option; pickup pool (capital = Helsinki, Espoo,
  Vantaa; ring = under 30 drivers within 30 km and at least 30 within 55 km; 100 or more; 30-99) x delivery
  pool (same classes, plus under 30); drive band (under 60, 60-179, 180-299, 300+ minutes); premium car;
  private pickup; private delivery; trade-in; a digit or a weekday in the note; the delivery site's stated
  closing hour; weekday of the win; booked on the day of the post or later. For each class also "margin per
  late order": the class's summed margin over its late orders.
- Then one loose run, never to be promoted: `uv run lab eval -s min_supply=10 -s same_day_min_supply=0 -s
  far_options=all -s min_slack_min=120 -s long_drive_min=0 --name loose-dev`, reveal its 16 worlds, and make
  the same table for the classes the champion never wins (thin pickups by delivery pool, same_day in pools of
  30-99, ring same_day by hour of arrival, drives over 300 minutes). The answer we need: which closed class
  has the highest margin per late order, and which is poison.
- R8, what predicts a win. Over every quote of the 16 champion reveals that was not a decline (a quote above
  3x list is a decline): a logistic regression of won on log(quote / list) for the option the dealer took
  or, when lost, the cheapest quoted option; log(typical fee / highest list price); log(road km); option
  quoted; hour; weekday; batch size; and a level per world and day (subtract the day's mean, or add
  dummies). Standard library only: write the Newton steps yourself or bin and tabulate if that is quicker.
  Report: the slope on price (how many points of win rate does 5% of price cost near our price?), the
  coefficient on the typical-fee ratio (idea 18's weight), and the 10 pickup places and 10 delivery places
  whose quotes win most and least at a given price (the start of idea 28's lane table).
Write experiments/<YYYYMMDD-HHMM>-gemini-research-classes.md with the tables, and the scripts under
experiments/scripts/. End with what each table suggests for ideas 18, 20, 21(c), 24 and 25, in numbers.
