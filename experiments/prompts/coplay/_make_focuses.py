"""Writes the ten co-player focus files (run once from the repo root)."""
from pathlib import Path

F = {
    "cp-routes": ("dev-12", "**the route network (idea 31, the user's own design)**. Read its brief, `experiments/prompts/night2/network-routes-on-v3.md`, and the census brief `research-network-census.md` next to it. Watch where our drivers finish their gigs and which requests start there, then build the offers to our finishing drivers and test them in co-play."),
    "cp-chains": ("dev-10", "**chains**, a driver's next car. Read `experiments/prompts/night2/hitch-pairs-on-v3.md` and `hitch-return-offer-on-v3.md`. R11 found 94 disjoint chains a week among the requests we decline. Find them live in your week (a declined request whose pickup is near where one of our gigs ends, at about that time), and test winning them with a return offer or a paired gig."),
    "cp-demand": ("dev-02", "**the demand curve**. Probe many waiting quotes (different classes, dealers, trust, times of day, floors and declines), and tabulate the dealer's real limit against our quote. Where do we leave money on the table, and where does the floor lose winnable cars? Turn what you learn into a pricing rule (also the user's c3 brief, `experiments/prompts/carbon/c3-acceptance-model.md`), and test it with what-ifs and then on 16 worlds."),
    "cp-fees": ("dev-09", "**staffing cost**: driver fees are 64% of revenue. Watch the bookings (fee ÷ reference fee, urgent or not), the drops and the late cars. Test the fee schedule, the timing of steps, direct offers and which gigs to post first. What would cut fees by 10% without late cars?"),
    "cp-supervisor": ("dev-15", "**the day supervisor** (the user's c5 brief, `experiments/prompts/carbon/c5-day-supervisor.md`). Each game morning, use what-ifs to find the best settings for the rest of the week, and record what you pick and why. Then find a rule that reads the state (backlog, drivers free, wins so far, weekday) and makes the same choices without forks, and test it from Monday."),
    "cp-buffer": ("dev-14", "**the buffer spender** (the user's c4 brief, `experiments/prompts/carbon/c4-buffer-spender.md`): spend the on-time margin above 92% on volume, and steer the slack and the selection by how much buffer is left. Test it live."),
    "cp-classes": ("dev-06", "**one price tracker per class**. The global multiplier couples every class: a cheap win in one class raises the price everywhere. Give each class (pickup supply hub/mid/thin × drive short/mid/long) its own tracker and win target. Find the targets in co-play (high where the margin rate is high), then test from Monday."),
    "cp-volume": ("dev-04", "**your own ideas for volume**. The leaders win 410–460 orders a week; we win ~270. Where do they come from without breaking the driver ceiling? (Thin towns, same-day, batches, multi-car orders, Friday?) Watch your week, then test your best idea."),
    "cp-margin": ("dev-13", "**your own ideas for margin per order**: price (each dealer's real limit, trust), fees, and which orders to decline. Watch your week, then test your best idea."),
    "cp-wild": ("dev-11", "**anything you think the others will miss**. This is the champion's weakest kind of world: €7.6k where its median is €10.4k. Find out why it does badly here and what would fix it without hurting the good worlds."),
}

for slug, (seed, focus) in F.items():
    Path(f"experiments/prompts/coplay/{slug}.md").write_text(
        f"## Your world and focus\nSeed: **{seed}**. Name your games `{slug}-1`, `{slug}-2`, ...\n\nFocus: {focus}\n",
        encoding="utf-8")
print(" ".join(F))
