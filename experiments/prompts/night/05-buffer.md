Idea #9 of experiments/IDEAS.md, "Give drivers an earlier deadline than the dealer's". First measure (R3): with
`uv run lab reveal` on 4 of the champion's dev worlds (world ids in champion/results/dev-L8.jsonl), how many minutes late
the late orders were. Then implement `delivery_buffer_min` (default 0) and `buffer_per_drive` (default 0): the delivery
stop's window ends that much before the deadline when we post; a repost after expiry uses the order's own window. Try
(30, 0), (45, 0.1), (60, 0.1) on smoke; best on dev. Stats: gigs posted with a buffer, expired, late.
