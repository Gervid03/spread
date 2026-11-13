Idea #18 of experiments/IDEAS.md, "A price that knows the cost: undo the adverse selection". Read points 5 and
13 there. Implement in src/spread_lab/policy.py:
- `fee_weight: float = 0.0` (0 = the champion), `fee_ratio_mid: float = 0.9`, `fee_tilt_max: float = 0.25`.
  In `Desk.price`, ratio = `referenceFeeCents` / (`fee_ratio_mid` x the highest `listPriceCents` among the
  request's options); tilt = clamp(ratio ** `fee_weight`, 1 / (1 + `fee_tilt_max`), 1 + `fee_tilt_max`); every
  option's price is multiplied by the tilt before the floor is applied. The tracker and the dealer factor
  work as today (a tilted quote is a normal quote for `learn`).
- `learn_from_floor: bool = False`: with it, a quote decided as "floor" that wins moves the tracker and the
  dealer factor up as a normal win does; a floor quote that loses teaches nothing.
- Counters, by third of the ratio (cut at 0.8 and 1.0 of typical fee / highest list price): quotes that were
  not declines and wins (`q_easy`, `q_mid`, `q_hard`, `w_easy`, ...), and late orders (`late_easy`, ...) from
  the late_refund and undelivered_penalty lines.
First run the champion once on smoke with the counters only: does it win a larger share of the hard third
than of the easy third? That is the adverse selection this idea is about; put the three win rates in the
note. Then smoke: `fee_weight` 0.25, 0.5, 0.75; `learn_from_floor` alone. Dev: the best weight, then with
`learn_from_floor`. Report driver fees / revenue next to the margin (it is in results.jsonl's ledger).
