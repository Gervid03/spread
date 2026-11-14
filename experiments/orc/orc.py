"""orc: a bare oracle harness. Raw practice worlds, forks and actions, no Desk in between.

    with world("dev-12") as w:            # holds one practice slot
        w.to(630, on_request=quote_fn)     # steps by price_request; quote_fn(request, now) -> prices dict or None
        with w.fork() as f:                # a copy (a second slot), deleted at the end of the block
            ev = f.advance(by=11, actions=[...])

Files go to ~/.spread-lab/orc/<seed>/. The tape of a seed (every request, the roster) is tas.py's
(~/.spread-lab/tas/<seed>/tape.json).
"""
from __future__ import annotations

import json
import sys
import time
from contextlib import contextmanager
from pathlib import Path

from spread.client import SpreadError

from spread_lab.env import lab_home, load_dotenv
from spread_lab.lab import CountingClient, Slot, create_world, register, wait_while_quiet

DAY = 1440
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun", "Mon+", "Tue+", "Wed+"]


def clock(m: int) -> str:
    return f"{DAYS[m // DAY]} {m % DAY // 60:02d}:{m % 60:02d}"


def home(seed: str) -> Path:
    p = lab_home() / "orc" / seed
    p.mkdir(parents=True, exist_ok=True)
    return p


def tape(seed: str) -> dict:
    return json.loads((lab_home() / "tas" / seed / "tape.json").read_text(encoding="utf-8"))


def chunks(xs, n=50):
    for i in range(0, len(xs), n):
        yield xs[i:i + n]


class W:
    """One practice world: the clock, every event seen, the orders won."""

    def __init__(self, client, raw, slot, entry=None, parent=None):
        self.client, self.raw, self.slot, self.entry = client, raw, slot, entry
        self.now = parent.now if parent else 0
        self.ends_at = parent.ends_at if parent else raw.snapshot()["endsAt"]
        self.orders = dict(parent.orders) if parent else {}
        self.events = []          # the events of this world since it was made (a copy: since the fork)
        self.first = parent is not None   # a copy's first advance answers with its whole history
        self.seen = parent.seen if parent else -1

    def _take(self, events):
        fresh = [e for e in events if e["seq"] > self.seen]
        if fresh:
            self.seen = max(e["seq"] for e in fresh)
        for e in fresh:
            if e["kind"] == "order_won":
                self.orders[e["order"]["id"]] = e["order"]
            elif e["kind"] == "order_changed" and "order" in e:
                self.orders[e["order"]["id"]] = e["order"]
            elif e["kind"] == "order_cancelled":
                self.orders.pop(e.get("orderId"), None)
        self.events += fresh
        return fresh

    def act(self, actions):
        out = []
        for part in chunks(list(actions)):
            out += self.raw.act(part)
        return out

    def advance(self, to=None, by=None, until=None, max=None, actions=()):
        """Applies the actions now, then moves the clock. Returns (results, new events)."""
        actions = list(actions)
        results = []
        while len(actions) > 50:
            results += self.raw.act(actions[:50])
            actions = actions[50:]
        step = self.raw.advance(to=to, by=by, until=until, max=max, actions=actions)
        results += step.get("results") or []
        self.now = step["now"]
        return results, self._take(step["events"])

    def to(self, minute, on_request=None, on_events=None):
        """Plays to `minute`, stopping at each price request; `on_request(request, now)` gives the prices to
        quote (or None); `on_events(events)` may return more actions for the next step."""
        pending = []
        minute = min(minute, self.ends_at)
        while self.now < minute:
            _, events = self.advance(until=["price_request"], max=minute, actions=pending)
            pending = []
            for e in events:
                if e["kind"] == "price_request" and on_request:
                    prices = on_request(e["request"], self.now)
                    if prices:
                        pending.append({"type": "quote", "requestId": e["request"]["id"], "prices": prices})
            if on_events:
                pending += on_events(events) or []
        if pending:
            self.act(pending)

    def score(self):
        return self.raw.score()

    @contextmanager
    def fork(self):
        wait_while_quiet()
        slot = Slot().__enter__()
        raw = None
        try:
            for attempt in range(5):
                try:
                    raw = self.raw.fork()
                    break
                except SpreadError as error:
                    if error.status == 409:
                        time.sleep(3)
                        continue
                    if error.status < 500 or attempt == 4:
                        raise
                    time.sleep(3 * (attempt + 1))
            if raw is None:
                raise RuntimeError("no fork")
            yield W(self.client, raw, slot, parent=self)
        finally:
            if raw is not None:
                try:
                    raw.delete()
                except Exception:
                    pass
            slot.__exit__(None, None, None)


@contextmanager
def world(seed: str, level: int = 8, what: str = "orc"):
    load_dotenv()
    client = CountingClient()
    slot = Slot().__enter__()
    raw = None
    entry = None
    try:
        raw = create_world(client, level, seed)
        entry = register(raw.id, {"seed": seed, "level": level, "orc": what})
        yield W(client, raw, slot, entry)
    finally:
        if raw is not None:
            try:
                raw.delete()
            except Exception:
                pass
        if entry is not None:
            entry.unlink(missing_ok=True)
        slot.__exit__(None, None, None)


def solo_post(order, fee_cents, at):
    """A one-order gig (both legs of a trade-in in one gig, old car's pickup right after the new car's delivery)."""
    stops = []
    for i, _ in enumerate(order["legs"]):
        stops += [{"orderId": order["id"], "leg": i, "kind": "pickup"}, {"orderId": order["id"], "leg": i, "kind": "delivery"}]
    premium = any(leg["car"]["premium"] for leg in order["legs"])
    return {"type": "post", "stops": stops, "audience": {"experienced": premium, "manualLicence": False},
            "schedule": [{"at": at, "feeCents": fee_cents}]}


def say(*a):
    print(*a, flush=True)
