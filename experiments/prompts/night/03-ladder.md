Idea #5 of experiments/IDEAS.md, "The twin ladder: let batches bracket the competitor". Implement `ladder_spread`
(default 0 = off): the requests of one batch (same batchId, or same dealer and yard within a few minutes) are quoted at the
estimate x exp(±spread), spread evenly across the batch; when a batch both wins and loses, move the price multiplier
toward the middle of the bracket with a larger step (`ladder_lr`, default 0). Try spread 0.05 and 0.08 on smoke, the
better on dev. Add stats: batches quoted, batches bracketed.
