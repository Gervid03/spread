Research, no policy change (steps 1-4 of the protocol don't apply; write the note, commit it with your scripts, push).
R2 + R5 of experiments/IDEAS.md: **the class table and the capital's daily ceiling** for champion v2. Reveal the 16
champion dev worlds (world ids in champion/results/dev-L8.jsonl; one request each) and tabulate late share, margin per
order and booked fee / typical fee by pickup class (capital, ring, 30-200 drivers, under 30) x option x drive length
(<100, 100-300, >300 min) x weekday. Then, per day, same_day orders in the capital against that day's late share. End
with concrete gate values: which classes could be opened (late share < 3%, positive margin) and which closed.
experiments/scripts/scout_classes.py is a start. Note to experiments/<date>-gemini-research-class-table.md.
