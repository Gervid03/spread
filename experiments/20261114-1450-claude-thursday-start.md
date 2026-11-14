# thursday-start: rehearse the test final (desk joins Thu 00:00) and find the volume setting for it

- **Agent / branch / commit:** claude · exp/claude-thursday-start · (see git log)
- **Date:** 2026-11-14 14:50
- **Idea from:** own, after the 14:00 test final

## Why we tried it
In the 14:00 test final the world joined us on Thu 00:00 with Mon-Wed pre-played as lost (LEDGER, 13:40).
We finished **19th: 106 orders, €2,448, 100.0% on time**. The winner had 158 orders, €4,023, 98.7%; 10th
(the cut) 153 orders, €3,292. Our margin per order (€23.1) was in line with the top (€21-25); the whole gap
is ~50 orders we did not win. The top teams paid only 1-2 points of on-time share for 50% more volume.
The champion's gates (min_supply, note_unsure=decline, min_slack_min, price_target_win=0.40) were tuned on
full Monday-start weeks, where keeping drivers free for later days pays. In a Thu-Fri sprint there are no
later days, and the competitor has had three mornings of 0% win share to raise its prices.

## What changed
`sim_start_day: int = 0` (off = champion, byte-identical path). With `-s sim_start_day=3` the desk leaves
every request that arrives before Thu 00:00 unanswered (no quote, no learning), as in the test final.
Counter: `sim_unanswered`. Practice only; never set it for the final.

## How to run (needs the server; pause during the 20:00 test final)
Margins under the rehearsal are not comparable with the champion's full weeks, so compare against the
rehearsal baseline, not the champion:
```sh
uv run lab eval --seeds-from smoke -s sim_start_day=3 --vs none --name thu-base
uv run lab sweep -s sim_start_day=3 -g price_target_win=0.40,0.50,0.60 -g min_supply=22,12
uv run lab compare runs/<sweep-run> runs/<thu-base-run>
```
Then the next volume knobs, one at a time: `note_unsure=quote`, `min_slack_min=150,120`.
Aim for on-time ~95-96% on every seed (still ≥ 92%). If a setting wins clearly, confirm on dev with
`sim_start_day=3`, then check it on full weeks (no sim flag) before it can become a Thursday-only rule.

## Results (level 8, sim_start_day=3, vs thu-base, paired)
| set | run folder | mean margin | Δmargin ± SE | t | better/worse | on-time min | SAFE |
|---|---|---|---|---|---|---|---|
| smoke | | | | | | | |
| dev | | | | | | | |

## Verdict
pending: written without server access (cloud session); not yet run.
