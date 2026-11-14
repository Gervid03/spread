# Night status, 2026-11-14 00:34 UTC (ends 2026-11-14T10:13:17Z)

## Workers

| worker | started (UTC) | state | tool calls | pushed | last Δ line |
|---|---|---|---|---|---|
| n14-01-margin-xray | 00:13 | done 00:27 (14 min) | 47 | no |  |
| n14-02-trust-v2 | 00:13 | done 00:27 (14 min) | 38 | yes | Δmargin €+303.46 ± 134.52 (t=2.26, 11/5 better/worse), worst on-time share 94.7% (SAFE) |
| n14-03-ladder | 00:13 | running | 45 | no |  |
| n14-04-alarm | 00:14 | done 00:33 (19 min) | 54 | yes | Δmargin €-313.97 ± 180.23 (SE) t=-1.74, worst on-time share 92.5% (SAFE; 5.3% late among 415 alarmed orders vs 71% after deadline_close, €1,505.65/world alarm f |
| n14-05-buffer | 00:14 | running | 64 | yes | Δmargin €-91.41 ± 156.85 (SE) t=-0.58, Δon-time +0.19%, worst on-time 93.8% (SAFE) |
| n14-06-budget | 00:27 | running | 28 | no |  |
| n14-07-notes | 00:28 | running | 32 | no |  |
| n14-08-return | 00:33 | running | 8 | no |  |

Queued prompts: 09-release.md, 10-flu.md, 11-class-table.md, 12-twoclocks-v2.md

## Sweeps started (in order; logs/sweep-NN.txt has each table)

01. `sweep --seeds-from dev --name n-ptw-minsup -g price_target_win=0.30,0.40,0.45 -g min_supply=20,30`
02. `sweep --seeds-from dev --name n-feeopen -g fee_open=0.70,0.75,0.80`
03. `sweep --seeds-from dev --name n-feewarn -g fee_warn=1.40,1.80 -g fee_step_min=20,45`
04. `eval --seeds night-01,night-02,night-03,night-04,night-05,night-06,night-07,night-08,night-09,night-10,night-11,night-12,night-13,night-14,night-15,night-16,night-17,night-18,night-19,night-20,night-21,night-22,night-23,night-24,night-25,night-26,night-27,night-28,night-29,night-30,night-31,night-32 --vs none --name n-champ-fresh32`
05. `sweep --seeds-from dev --name n-slack -g min_slack_min=150,210,240 -g slack_per_drive=0.25,0.75`

## Every evaluation since the night began

Champion v2 on dev: margin mean 8,990, on-time min 94.4%. Δ is paired on seeds the champion has (dev, holdout).

| run | worlds | margin mean | min margin | on-time min | SAFE | Δ vs champion (paired) |
|---|---|---|---|---|---|---|
| 20261114-001458-n-ptw-minsup-price_target_win0.30-min_supply20 | 16 | 8,975 | 5,747 | 94.1% | SAFE | -15 ± 218 (t -0.1, 9/16 better) |
| 20261114-001539-n-ptw-minsup-price_target_win0.30-min_supply30 | 16 | 8,712 | 5,937 | 94.1% | SAFE | -279 ± 177 (t -1.6, 6/16 better) |
| 20261114-001620-n-ptw-minsup-price_target_win0.40-min_supply20 | 16 | 9,201 | 6,420 | 92.4% | SAFE | +210 ± 265 (t +0.8, 11/16 better) |
| 20261114-001702-n-ptw-minsup-price_target_win0.40-min_supply30 | 16 | 9,050 | 6,607 | 92.4% | SAFE | +59 ± 218 (t +0.3, 10/16 better) |
| 20261114-001749-n-ptw-minsup-price_target_win0.45-min_supply20 | 16 | 8,988 | 6,356 | 91.3% | no | -3 ± 316 (t -0.0, 9/16 better) |
| 20261114-001842-n-ptw-minsup-price_target_win0.45-min_supply30 | 16 | 9,061 | 6,105 | 91.3% | no | +71 ± 306 (t +0.2, 10/16 better) |
| 20261114-001958-n-feeopen-fee_open0.70 | 16 | 7,997 | 5,915 | 92.5% | SAFE | -994 ± 315 (t -3.2, 3/16 better) |
| 20261114-002120-n-feeopen-fee_open0.75 | 16 | 8,457 | 5,953 | 93.8% | SAFE | -534 ± 214 (t -2.5, 4/16 better) |
| 20261114-002210-n-feeopen-fee_open0.80 | 16 | 8,816 | 6,166 | 90.7% | no | -174 ± 222 (t -0.8, 7/16 better) |
| 20261114-002358-n-feewarn-fee_warn1.40-fee_step_min20 | 16 | 9,124 | 6,944 | 92.3% | SAFE | +133 ± 200 (t +0.7, 9/16 better) |
| 20261114-002447-n-feewarn-fee_warn1.40-fee_step_min45 | 16 | 9,076 | 6,667 | 90.1% | no | +85 ± 208 (t +0.4, 9/16 better) |
| 20261114-002537-n-feewarn-fee_warn1.80-fee_step_min20 | 16 | 8,580 | 5,776 | 94.1% | SAFE | -411 ± 157 (t -2.6, 7/16 better) |
| 20261114-002625-n-feewarn-fee_warn1.80-fee_step_min45 | 16 | 8,498 | 6,108 | 94.5% | SAFE | -493 ± 119 (t -4.1, 2/16 better) |
| 20261114-002838-n-champ-fresh32 | 32 | 9,193 | 3,434 | 90.5% | no | — |
| 20261114-003138-n-slack-min_slack_min150-slack_per_drive0.25 | 16 | 8,709 | 6,148 | 91.3% | no | -281 ± 310 (t -0.9, 7/16 better) |
| 20261114-003224-n-slack-min_slack_min150-slack_per_drive0.75 | 16 | 9,126 | 6,279 | 93.8% | SAFE | +135 ± 59 (t +2.3, 11/16 better) |
| 20261114-003307-n-slack-min_slack_min210-slack_per_drive0.25 | 16 | 9,153 | 6,488 | 93.3% | SAFE | +163 ± 161 (t +1.0, 8/16 better) |
| 20261114-003349-n-slack-min_slack_min210-slack_per_drive0.75 | 0 failed | | | | | |
