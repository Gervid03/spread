# Night status, 2026-11-14 01:15 UTC (ends 2026-11-14T10:13:17Z)

## Workers

| worker | started (UTC) | state | tool calls | pushed | last Δ line |
|---|---|---|---|---|---|
| n14-01-margin-xray | 00:13 | done 00:27 (14 min) | 47 | no |  |
| n14-02-trust-v2 | 00:13 | done 00:27 (14 min) | 38 | yes | Δmargin €+303.46 ± 134.52 (t=2.26, 11/5 better/worse), worst on-time share 94.7% (SAFE) |
| n14-03-ladder | 00:13 | done 00:48 (34 min) | 70 | yes | Δmargin €+45.41 ± 169.07 (SE) t=0.27, worst on-time share 94.2% (SAFE) |
| n14-04-alarm | 00:14 | done 00:33 (19 min) | 54 | yes | Δmargin €-313.97 ± 180.23 (SE) t=-1.74, worst on-time share 92.5% (SAFE; 5.3% late among 415 alarmed orders vs 71% after deadline_close, €1,505.65/world alarm f |
| n14-05-buffer | 00:14 | done 00:35 (20 min) | 64 | yes | Δmargin €-91.41 ± 156.85 (SE) t=-0.58, Δon-time +0.19%, worst on-time 93.8% (SAFE) |
| n14-06-budget | 00:27 | done 01:02 (34 min) | 71 | no | dev paired Δmargin €+93.76 ± 64.88 (t=1.45), worst on-time share 94.38% on dev-07 (combined loose: Δmargin €-51.26 ± 305.17, worst on-time share 94.94% on dev-0 |
| n14-07-notes | 00:28 | running | 116 | no |  |
| n14-08-return | 00:33 | done 01:09 (35 min) | 80 | yes | dev Δmargin €-3.61 ± 60.66 (SE) (t=-0.06, better 5 / worse 5), worst on-time share 94.4% (SAFE) |
| n14-09-release | 00:35 | running | 102 | no | I will run `uv run lab reveal` on four finished champion dev worlds (`dev-01`, `dev-07`, `dev-10`, `dev-14`) into the temporary directory `/home/lab/.gemini/tmp |
| n14-10-flu | 00:48 | running | 57 | no |  |
| n14-11-class-table | 01:02 | running | 52 | no |  |
| n14-12-twoclocks-v2 | 01:09 | running | 25 | no | I will merge `origin/exp/gemini-clocks` into the current branch (`exp/gemini-n14-12-twoclocks-v2`) to bring in the two-clocks pricing tracker changes and its ex |

Queued prompts: none

## Sweeps started (in order; logs/sweep-NN.txt has each table)

01. `sweep --seeds-from dev --name n-ptw-minsup -g price_target_win=0.30,0.40,0.45 -g min_supply=20,30`
02. `sweep --seeds-from dev --name n-feeopen -g fee_open=0.70,0.75,0.80`
03. `sweep --seeds-from dev --name n-feewarn -g fee_warn=1.40,1.80 -g fee_step_min=20,45`
04. `eval --seeds night-01,night-02,night-03,night-04,night-05,night-06,night-07,night-08,night-09,night-10,night-11,night-12,night-13,night-14,night-15,night-16,night-17,night-18,night-19,night-20,night-21,night-22,night-23,night-24,night-25,night-26,night-27,night-28,night-29,night-30,night-31,night-32 --vs none --name n-champ-fresh32`
05. `sweep --seeds-from dev --name n-slack -g min_slack_min=150,210,240 -g slack_per_drive=0.25,0.75`
06. `sweep --seeds-from dev --name n-ring -g gate_radius_km=45,70 -g far_options=slow,all`
07. `sweep --seeds-from dev --name n-sdsupply -g same_day_min_supply=50,150,200`
08. `sweep --seeds-from dev --name n-caps -g price_mult_max=2.0,2.4 -g dealer_adj_max=1.3,1.6`
09. `sweep --seeds-from dev --name n-lr -g price_lr=0.03,0.08 -g dealer_lr=0.01,0.04`
10. `sweep --seeds-from dev --name n-margin -g expected_fee_mult=1.10,1.40 -g min_margin_frac=0.04,0.12`
11. `sweep --seeds-from dev --name n-backlog -g backlog_ratio=0.04,0.09,0.12`
12. `sweep --seeds-from dev --name n-longdrive -g long_drive_min=0,240,360`
13. `sweep --seeds-from dev --name n-streak -g loss_streak_freeze=8,20,9999`
14. `sweep --seeds-from dev --name n-sdmarkup -g same_day_markup=0.0,0.10,0.15`
15. `sweep --seeds-from dev --name n-steep -g steep_open=1.5,2.2 -g steep_step=0.15,0.35`

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
| 20261114-003349-n-slack-min_slack_min210-slack_per_drive0.75 | 16 | 8,841 | 5,957 | 94.4% | SAFE | -150 ± 114 (t -1.3, 7/16 better) |
| 20261114-003431-n-slack-min_slack_min240-slack_per_drive0.25 | 16 | 9,061 | 6,481 | 93.4% | SAFE | +71 ± 122 (t +0.6, 9/16 better) |
| 20261114-003523-n-slack-min_slack_min240-slack_per_drive0.75 | 16 | 8,706 | 6,012 | 93.1% | SAFE | -284 ± 183 (t -1.6, 7/16 better) |
| 20261114-003622-n-ring-gate_radius_km45-far_optionsslow | 16 | 8,500 | 5,600 | 95.2% | SAFE | -490 ± 252 (t -1.9, 4/16 better) |
| 20261114-003707-n-ring-gate_radius_km45-far_optionsall | 16 | 8,500 | 5,600 | 95.2% | SAFE | -490 ± 252 (t -1.9, 4/16 better) |
| 20261114-003758-n-ring-gate_radius_km70-far_optionsslow | 16 | 8,662 | 5,610 | 93.5% | SAFE | -328 ± 132 (t -2.5, 6/16 better) |
| 20261114-003859-n-ring-gate_radius_km70-far_optionsall | 16 | 8,662 | 5,610 | 93.5% | SAFE | -328 ± 132 (t -2.5, 6/16 better) |
| 20261114-004022-n-sdsupply-same_day_min_supply50 | 16 | 9,090 | 6,017 | 94.4% | SAFE | +100 ± 128 (t +0.8, 5/16 better) |
| 20261114-004106-n-sdsupply-same_day_min_supply150 | 16 | 8,974 | 5,886 | 94.4% | SAFE | -16 ± 75 (t -0.2, 2/16 better) |
| 20261114-004204-n-sdsupply-same_day_min_supply200 | 16 | 8,828 | 5,886 | 92.3% | SAFE | -162 ± 161 (t -1.0, 2/16 better) |
| 20261114-004322-n-caps-price_mult_max2.0-dealer_adj_max1.3 | 16 | 8,691 | 6,446 | 93.3% | SAFE | -300 ± 125 (t -2.4, 4/16 better) |
| 20261114-004514-n-caps-price_mult_max2.0-dealer_adj_max1.6 | 16 | 8,647 | 6,325 | 93.3% | SAFE | -343 ± 128 (t -2.7, 4/16 better) |
| 20261114-004627-n-caps-price_mult_max2.4-dealer_adj_max1.3 | 16 | 8,620 | 6,446 | 93.6% | SAFE | -371 ± 153 (t -2.4, 4/16 better) |
| 20261114-004710-n-caps-price_mult_max2.4-dealer_adj_max1.6 | 16 | 8,596 | 6,325 | 93.6% | SAFE | -394 ± 145 (t -2.7, 4/16 better) |
| 20261114-004842-n-lr-price_lr0.03-dealer_lr0.01 | 16 | 9,094 | 6,298 | 94.0% | SAFE | +104 ± 161 (t +0.6, 9/16 better) |
| 20261114-004934-n-lr-price_lr0.03-dealer_lr0.04 | 16 | 8,681 | 5,643 | 91.7% | no | -309 ± 196 (t -1.6, 3/16 better) |
| 20261114-005022-n-lr-price_lr0.08-dealer_lr0.01 | 16 | 8,946 | 5,064 | 93.7% | SAFE | -45 ± 209 (t -0.2, 9/16 better) |
| 20261114-005105-n-lr-price_lr0.08-dealer_lr0.04 | 16 | 8,590 | 5,657 | 93.4% | SAFE | -400 ± 164 (t -2.4, 3/16 better) |
| 20261114-005242-n-margin-expected_fee_mult1.10-min_margin_frac0.04 | 16 | 8,127 | 5,008 | 93.3% | SAFE | -864 ± 259 (t -3.3, 2/16 better) |
| 20261114-005337-n-margin-expected_fee_mult1.10-min_margin_frac0.12 | 16 | 8,724 | 6,075 | 94.0% | SAFE | -267 ± 164 (t -1.6, 7/16 better) |
| 20261114-005436-n-margin-expected_fee_mult1.40-min_margin_frac0.04 | 16 | 8,884 | 6,251 | 92.7% | SAFE | -106 ± 282 (t -0.4, 9/16 better) |
| 20261114-005540-n-margin-expected_fee_mult1.40-min_margin_frac0.12 | 16 | 8,563 | 5,230 | 92.4% | SAFE | -427 ± 248 (t -1.7, 4/16 better) |
| 20261114-005746-n-backlog-backlog_ratio0.04 | 16 | 8,887 | 5,852 | 94.3% | SAFE | -103 ± 107 (t -1.0, 4/16 better) |
| 20261114-005900-n-backlog-backlog_ratio0.09 | 16 | 8,821 | 6,017 | 93.9% | SAFE | -169 ± 143 (t -1.2, 4/16 better) |
| 20261114-010000-n-backlog-backlog_ratio0.12 | 16 | 8,771 | 6,017 | 92.5% | SAFE | -219 ± 169 (t -1.3, 3/16 better) |
| 20261114-010146-n-longdrive-long_drive_min0 | 16 | 8,954 | 6,017 | 94.4% | SAFE | -37 ± 90 (t -0.4, 3/16 better) |
| 20261114-010239-n-longdrive-long_drive_min240 | 16 | 8,870 | 6,393 | 93.4% | SAFE | -120 ± 139 (t -0.9, 8/16 better) |
| 20261114-010343-n-longdrive-long_drive_min360 | 16 | 8,975 | 6,017 | 94.4% | SAFE | -15 ± 89 (t -0.2, 3/16 better) |
| 20261114-010606-n-streak-loss_streak_freeze8 | 16 | 8,910 | 5,581 | 93.0% | SAFE | -80 ± 190 (t -0.4, 6/16 better) |
| 20261114-010707-n-streak-loss_streak_freeze20 | 16 | 8,980 | 5,698 | 93.9% | SAFE | -10 ± 126 (t -0.1, 5/16 better) |
| 20261114-010833-n-streak-loss_streak_freeze9999 | 16 | 8,979 | 5,698 | 93.9% | SAFE | -11 ± 126 (t -0.1, 5/16 better) |
| 20261114-011028-n-sdmarkup-same_day_markup0.0 | 16 | 8,901 | 6,360 | 91.8% | no | -89 ± 229 (t -0.4, 8/16 better) |
| 20261114-011150-n-sdmarkup-same_day_markup0.10 | 16 | 8,798 | 6,100 | 92.8% | SAFE | -192 ± 234 (t -0.8, 5/16 better) |
| 20261114-011257-n-sdmarkup-same_day_markup0.15 | 16 | 8,467 | 5,774 | 94.0% | SAFE | -523 ± 265 (t -2.0, 3/16 better) |
| 20261114-011428-n-steep-steep_open1.5-steep_step0.15 (running) | 9 | 9,006 | 7,039 | 94.4% | no | -82 ± 178 (t -0.5, 4/9 better) |
