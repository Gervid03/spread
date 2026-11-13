"""Runners: the practice loop (we move the clock) and the live loop (the clock moves by itself:
test finals and the final). Both drive the same desk, so what is measured in practice is what
plays in the final."""
from __future__ import annotations

import sys
import time
from collections import Counter
from typing import Callable, Optional

from spread.client import Client, SpreadError, Unreachable, World
from spread.types import DeskEventKind

HOUR, DAY = 60, 24 * 60
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# Outside business hours the runner jumps up to an hour, but stops early at any of these.
URGENT: list[DeskEventKind] = [
    "price_request", "order_won", "order_changed", "order_cancelled", "visit_failed", "gig_expired",
    "deadline_close", "no_show", "gig_dropped", "driver_late", "release",
]


def busy(now: int) -> bool:
    """Weekdays 07:00-22:00 of the first week: requests can arrive, so steps stay under 15 minutes."""
    day = now // DAY
    return day < 5 and 7 * HOUR <= now % DAY < 22 * HOUR


def play_practice(world: World, desk, ends_at: int, on_day: Optional[Callable[[int], None]] = None) -> Counter:
    """Steps the world to its end. In business hours it advances `step_min` minutes at a time and
    answers every request of the step at its end (respondBy is 15 minutes after arrival, so a step
    of at most 14 minutes keeps every quote in time). Otherwise it jumps to the next urgent event or
    an hour on. The actions of each step go with the next advance: one request per step.

    Returns the account by ledger kind, in cents."""
    ledger: Counter = Counter()
    step_min = min(14, max(1, int(desk.p.step_min)))
    while desk.now < ends_at:
        actions = desk.take_outbox()
        day = desk.now // DAY
        if busy(desk.now):
            step = world.advance(to=min(ends_at, desk.now + step_min), actions=actions)
        else:
            step = world.advance(until=URGENT, max=min(ends_at, desk.now + HOUR), actions=actions)
        desk.read_results(actions, step["results"])
        desk.now = step["now"]
        for event in step["events"]:
            if event["kind"] == "ledger":
                ledger[event["line"]["kind"]] += event["line"]["cents"]
            desk.handle(event)
        desk.tick()
        if on_day and desk.now // DAY > day:
            on_day(day)
    return ledger


def play_live(world: World, make_desk: Callable[[World, dict, int], object], log: Callable[[str], None] = print) -> None:
    """Rebuilds the books from the world, then answers events as they stream in; after a second without
    an event it reads the clock. Safe to stop and start again: the desk rejoins from the server."""
    history = world.events()
    snapshot = world.snapshot()
    if snapshot["now"] >= snapshot["endsAt"]:
        log("This world has ended.")
        return
    desk = make_desk(world, snapshot, snapshot["now"])
    desk.rejoin(snapshot, history)
    desk.send()
    log(f"Rejoined at {clock(snapshot['now'])}: {len(desk.orders)} orders, {len(desk.requests)} requests seen.")
    last_day = desk.now // DAY
    for event in world.stream(after=history[-1]["seq"] if history else -1, idle=1.0):
        if event is None:
            desk.now = max(desk.now, world.client.final()["now"])
        else:
            desk.now = max(desk.now, event["at"])
            desk.handle(event)
        desk.tick()
        desk.send()
        if desk.now // DAY > last_day:
            last_day = desk.now // DAY
            score = world.score()
            log(f"{clock(desk.now)}  margin €{score['marginCents'] / 100:,.2f}  {score['wonOrders']} orders  "
                f"{score['onTimeShare']:.1%} on time  stats {dict(desk.stats)}")
        if desk.now >= snapshot["endsAt"]:
            return


def clock(minute: int) -> str:
    day = minute // DAY
    name = WEEKDAYS[day % 7] + ("+" if day >= 7 else "")
    return f"{name} {minute % DAY // 60:02d}:{minute % 60:02d}"


def wait_for_final(client: Client, log: Callable[[str], None] = print) -> World:
    """The team's copy of the final (or a test final) that is set or running. Waits while none is."""
    said = False
    while True:
        try:
            world: Optional[World] = client.world(client.final()["worldId"])
        except SpreadError as error:
            if error.status != 404:
                raise
            world = None
        if world is not None:
            snapshot = world.snapshot()
            if snapshot["now"] < snapshot["endsAt"]:
                return world
        if not said:
            log("No final is set yet. Waiting: test finals are set 15 minutes before their start, the final at 07:30.")
            said = True
        time.sleep(10)


def run_live_forever(client: Client, make_desk, log: Callable[[str], None] = print) -> None:
    """The final loop: survives server restarts and dropped connections by rejoining."""
    world = None
    while True:
        try:
            if world is None:
                world = wait_for_final(client, log)
                log(f"Final world {world.id}.")
            play_live(world, make_desk, log)
            score = world.score()
            log(f"End: margin €{score['marginCents'] / 100:,.2f}, {score['wonOrders']} orders, "
                f"{score['onTimeShare']:.1%} on time, ranked={score['ranked']}")
            return
        except Unreachable as error:
            print(f"spread: {error}. Rejoining in 5 seconds.", file=sys.stderr, flush=True)
            time.sleep(5)
