Research, no policy change (use the research protocol: steps 1-4 of the protocol don't apply; write the note, commit it with your scripts, push).
Question: **where does champion v2 lose margin against the best teams?** In ranking round 4 we made ~€10.8k a world on the
same worlds where House best made ~€14.4k and the leader ~€16k. Take the dev worlds the champion played
(world ids in champion/results/dev-L8.jsonl; reveal them with `uv run lab reveal <world id>`, one request each, at most 16)
and decompose our week: requests by class (pickup supply band x option x drive length) with our share quoted, declined,
won and lost; price/list of won and lost quotes; booked fee / typical fee; late and failed visits. Then estimate, per class,
the margin we leave on the table: (a) declined requests that were safe to serve (estimate from the classes we do serve),
(b) lost quotes we priced far above what won, (c) fees paid above what booked quickly, (d) refunds.
Write experiments/<date>-gemini-research-margin-xray.md with the table and a ranked list of the 3 biggest leaks in
euros per week, each with the Params change (or new mechanism) that would close it. Scripts go to experiments/scripts/.
