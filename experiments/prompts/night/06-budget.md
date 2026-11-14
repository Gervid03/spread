Idea #10 of experiments/IDEAS.md, "The on-time share as a budget, and Friday as the repair day". Implement
`budget_target` (default 0 = off) and `ballast_discount` (0.1): project the week's on-time share (known late +
0.7 x warned-without-driver + the class late rates of open orders; take rates from the champion's dev results or a small
table you measure with reveals), and under the target discount the safest classes (capital and ring, next_day or slower)
by up to ballast_discount and decline the worst ones. The aim is to let the desk run *looser* elsewhere: once it works,
combine it with `-s price_target_win=0.42 -s min_supply=20`. Report the worst world, not just the mean.
