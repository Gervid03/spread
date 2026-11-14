Idea #11 of experiments/IDEAS.md, "Notes: harvest the truth, then price out what we cannot read". Do (b) and (c) with the
data we already have: reveal 6 of the champion's dev worlds (world ids in champion/results/dev-L8.jsonl, one request each);
the reveal gives each won car's note truth. Score src/spread_lab/notes.py field by field on them, fix the reader (delivery
hours, "by tomorrow 17:00", weekday names, Finnish/Swedish hours), keeping old behaviour behind a flag `notes_v2`
(default False). Then (c): with `notes_v2`, delivery hours and note deadlines shorten each option's slack, and
`note_unsure` ("quote" default, or "decline"). Measure on smoke then dev. Stats: notes read, unsure, failed visits.
