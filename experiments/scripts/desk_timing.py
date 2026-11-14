#!/usr/bin/env python3
"""Desk wall-time profiler, live-order practice simulator, and low-request runner benchmark.

Records wall time (p50, p95, p99, max, count, calls > 50 ms, calls > 10 ms) of every:
  - desk.handle(event), overall and broken down by event['kind'] (both total and CPU-only excl. nested send)
  - desk.tick() (both total and CPU-only excl. nested send)
  - desk.send() / world.act()
  - desk.rejoin(snapshot, history)

Also supports multiple practice execution modes on the exact same seed:
  - practice      : current instrument (10-min steps Mon-Fri 07:00-22:00, 1h URGENT jumps outside)
  - fast-exact    : jumps directly to next busy/tick trigger outside business hours (bit-exact €0.00 vs practice)
  - until-urgent  : event-driven untilEvent + next_tick_at across the whole week, piggybacking actions on advance
  - live          : live event-by-event order (desk.now = event['at'], handle + tick + send per event) + wall-budget check
  - live-batched  : live event order, draining same-timestamp event bursts before tick() + send()

Examples:
  uv run python experiments/scripts/desk_timing.py --fake
  uv run python experiments/scripts/desk_timing.py --seed dev-12 --mode practice
  uv run python experiments/scripts/desk_timing.py --seed dev-12 --git-ref origin/exp/stack-v7 -s net_relay=True ...
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Any, Optional

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "src") not in sys.path:
    sys.path.insert(0, str(REPO / "src"))

from spread.types import DeskEventKind  # noqa: E402
from spread_lab.geo import Geo, load_map  # noqa: E402
from spread_lab.lab import (  # noqa: E402
    CHAMPION,
    CountingClient,
    Slot,
    create_world,
    load_policy,
    parse_overrides,
    register,
)
from spread_lab.runner import DAY, HOUR, URGENT, busy, play_practice  # noqa: E402


LIVE_ACTION_EVENTS: list[DeskEventKind] = list(
    dict.fromkeys(
        list(URGENT)
        + [
            "gig_booked",
            "gig_viewed",
            "delivered",
            "offer_answered",
        ]
    )
)


def live_sec_per_game_min(minute: int) -> float:
    """Exact real-time seconds per game minute in the final (from API.md):
    - Mon-Fri 06:00-22:00: 18 s/h = 0.30 s/min (15m respondBy = 4.50s)
    - Sat     06:00-22:00:  6 s/h = 0.10 s/min (15m respondBy = 1.50s)
    - Mon+    06:00-22:00:  9 s/h = 0.15 s/min (15m respondBy = 2.25s)
    - Nights (22:00-06:00), Sun, and after Mon+ 22:00: 3 s/h = 0.05 s/min (15m = 0.75s)
    """
    day = minute // DAY
    tod = minute % DAY
    if 6 * HOUR <= tod < 22 * HOUR:
        if day < 5:
            return 18.0 / 60.0
        if day == 5:
            return 6.0 / 60.0
        if day == 7:
            return 9.0 / 60.0
    return 3.0 / 60.0


def build_wall_clock_table(ends_at: int = 14500) -> list[float]:
    """Cumulative wall seconds W[m] from Monday 00:00 to game minute m in a live final."""
    w = [0.0] * (ends_at + 1)
    acc = 0.0
    for m in range(ends_at):
        acc += live_sec_per_game_min(m)
        w[m + 1] = acc
    return w


class FinalActionBucket:
    """Models the live server's `final-actions` token bucket (API.md: refills 20/s, holds at most 50,
    costs 1 token per action in POST /actions)."""

    def __init__(self, rate: float = 20.0, capacity: float = 50.0):
        self.rate = rate
        self.capacity = capacity
        self.tokens = capacity
        self.last_t = 0.0

    def take(self, now_w: float, n_actions: int) -> float:
        if now_w > self.last_t:
            self.tokens = min(self.capacity, self.tokens + (now_w - self.last_t) * self.rate)
            self.last_t = now_w
        cost = float(max(1, n_actions))
        if self.tokens >= cost:
            self.tokens -= cost
            return 0.0
        deficit = cost - self.tokens
        wait_s = deficit / self.rate
        self.tokens = 0.0
        self.last_t = now_w + wait_s
        return wait_s


def percentile(sorted_vals: list[float], q: float) -> float:
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    pos = q * (len(sorted_vals) - 1)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return sorted_vals[lo]
    return sorted_vals[lo] + (pos - lo) * (sorted_vals[hi] - sorted_vals[lo])


def summarize_samples_ms(samples_ns: list[int]) -> dict[str, Any]:
    if not samples_ns:
        return {
            "count": 0,
            "total_ms": 0.0,
            "mean_ms": 0.0,
            "p50_ms": 0.0,
            "p95_ms": 0.0,
            "p99_ms": 0.0,
            "max_ms": 0.0,
            "over_10ms": 0,
            "over_50ms": 0,
        }
    ms = sorted(x / 1e6 for x in samples_ns)
    total = sum(ms)
    return {
        "count": len(ms),
        "total_ms": round(total, 3),
        "mean_ms": round(total / len(ms), 4),
        "p50_ms": round(percentile(ms, 0.50), 4),
        "p95_ms": round(percentile(ms, 0.95), 4),
        "p99_ms": round(percentile(ms, 0.99), 4),
        "max_ms": round(ms[-1], 4),
        "over_10ms": sum(1 for x in ms if x > 10.0),
        "over_50ms": sum(1 for x in ms if x > 50.0),
    }


class DeskProfiler:
    """Wraps a Desk instance to time every handle, tick, send, and rejoin call in nanoseconds."""

    def __init__(self, desk: Any):
        self.desk = desk
        self._send_depth = 0
        self._nested_send_ns = 0
        self.handle_total_ns: list[int] = []
        self.handle_cpu_ns: list[int] = []
        self.handle_by_kind_total_ns: dict[str, list[int]] = defaultdict(list)
        self.handle_by_kind_cpu_ns: dict[str, list[int]] = defaultdict(list)
        self.tick_total_ns: list[int] = []
        self.tick_cpu_ns: list[int] = []
        self.send_all_ns: list[int] = []
        self.send_nonempty_ns: list[int] = []
        self.act_http_ns: list[int] = []
        self.advance_http_ns: list[int] = []
        self.rejoin_ns: list[int] = []
        self.slow_events: list[dict[str, Any]] = []
        self._install()

    def _install(self) -> None:
        desk = self.desk
        orig_handle = desk.handle
        orig_tick = desk.tick
        orig_send = desk.send
        orig_rejoin = desk.rejoin
        orig_act = desk.world.act
        orig_advance = desk.world.advance

        def timed_act(actions):
            t0 = time.perf_counter_ns()
            try:
                return orig_act(actions)
            finally:
                dt = time.perf_counter_ns() - t0
                self._nested_send_ns += dt
                if actions:
                    self.act_http_ns.append(dt)
                    if self._send_depth == 0:
                        # Direct world.act call bypassing desk.send() (e.g. _flush_non_quotes)
                        self.send_all_ns.append(dt)
                        self.send_nonempty_ns.append(dt)

        def timed_advance(*args, **kwargs):
            t0 = time.perf_counter_ns()
            try:
                return orig_advance(*args, **kwargs)
            finally:
                self.advance_http_ns.append(time.perf_counter_ns() - t0)

        def timed_send():
            had_actions = len(desk.outbox)
            self._send_depth += 1
            t0 = time.perf_counter_ns()
            try:
                return orig_send()
            finally:
                dt = time.perf_counter_ns() - t0
                self._send_depth -= 1
                self.send_all_ns.append(dt)
                if had_actions:
                    self.send_nonempty_ns.append(dt)
                if dt > 50_000_000:
                    self.slow_events.append(
                        {"call": "send", "at": desk.now, "actions": had_actions, "ms": round(dt / 1e6, 3)}
                    )

        def timed_handle(event):
            kind = event.get("kind", "?")
            before_send = self._nested_send_ns
            t0 = time.perf_counter_ns()
            try:
                return orig_handle(event)
            finally:
                dt = time.perf_counter_ns() - t0
                nested = self._nested_send_ns - before_send
                cpu_dt = max(0, dt - nested)
                self.handle_total_ns.append(dt)
                self.handle_cpu_ns.append(cpu_dt)
                self.handle_by_kind_total_ns[kind].append(dt)
                self.handle_by_kind_cpu_ns[kind].append(cpu_dt)
                if dt > 50_000_000 or cpu_dt > 10_000_000:
                    self.slow_events.append(
                        {
                            "call": f"handle:{kind}",
                            "at": desk.now,
                            "seq": event.get("seq"),
                            "total_ms": round(dt / 1e6, 3),
                            "cpu_ms": round(cpu_dt / 1e6, 3),
                        }
                    )

        def timed_tick():
            before_send = self._nested_send_ns
            t0 = time.perf_counter_ns()
            try:
                return orig_tick()
            finally:
                dt = time.perf_counter_ns() - t0
                nested = self._nested_send_ns - before_send
                cpu_dt = max(0, dt - nested)
                self.tick_total_ns.append(dt)
                self.tick_cpu_ns.append(cpu_dt)
                if dt > 50_000_000 or cpu_dt > 10_000_000:
                    self.slow_events.append(
                        {
                            "call": "tick",
                            "at": desk.now,
                            "total_ms": round(dt / 1e6, 3),
                            "cpu_ms": round(cpu_dt / 1e6, 3),
                        }
                    )

        def timed_rejoin(snapshot, history):
            t0 = time.perf_counter_ns()
            try:
                return orig_rejoin(snapshot, history)
            finally:
                self.rejoin_ns.append(time.perf_counter_ns() - t0)

        desk.world.act = timed_act
        desk.world.advance = timed_advance
        desk.send = timed_send
        desk.handle = timed_handle
        desk.tick = timed_tick
        desk.rejoin = timed_rejoin

    def report(self) -> dict[str, Any]:
        by_kind_cpu = {
            k: summarize_samples_ms(v)
            for k, v in sorted(self.handle_by_kind_cpu_ns.items(), key=lambda kv: -sum(kv[1]))
        }
        by_kind_total = {
            k: summarize_samples_ms(v)
            for k, v in sorted(self.handle_by_kind_total_ns.items(), key=lambda kv: -sum(kv[1]))
        }
        return {
            "handle_cpu": summarize_samples_ms(self.handle_cpu_ns),
            "handle_total": summarize_samples_ms(self.handle_total_ns),
            "tick_cpu": summarize_samples_ms(self.tick_cpu_ns),
            "tick_total": summarize_samples_ms(self.tick_total_ns),
            "send_all": summarize_samples_ms(self.send_all_ns),
            "send_nonempty": summarize_samples_ms(self.send_nonempty_ns),
            "act_http": summarize_samples_ms(self.act_http_ns),
            "advance_http": summarize_samples_ms(self.advance_http_ns),
            "rejoin": summarize_samples_ms(self.rejoin_ns),
            "handle_by_kind_cpu": by_kind_cpu,
            "handle_by_kind_total": by_kind_total,
            "slow_events": self.slow_events[:50],
        }


def load_policy_from_git_ref(git_ref: str) -> tuple[Any, Path]:
    """Extracts spread_lab/{__init__,env,geo,notes,policy}.py from a git ref into a temporary package
    and loads its Desk class so we can benchmark any branch (e.g. origin/exp/stack-v7) cleanly."""
    tmpdir = Path(tempfile.mkdtemp(prefix="spread_ref_"))
    pkg_dir = tmpdir / "spread_ref_pkg"
    pkg_dir.mkdir(parents=True, exist_ok=True)
    env = {k: v for k, v in dict(**__import__("os").environ).items() if not k.startswith("GIT_CONFIG_")}
    env.pop("GIT_ASKPASS", None)
    env.pop("SSH_ASKPASS", None)
    for fname in ("__init__.py", "env.py", "geo.py", "notes.py", "policy.py"):
        res = subprocess.run(
            ["git", "show", f"{git_ref}:src/spread_lab/{fname}"],
            cwd=REPO,
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        (pkg_dir / fname).write_text(res.stdout, encoding="utf-8")
    sys.path.insert(0, str(tmpdir))
    spec = importlib.util.spec_from_file_location("spread_ref_pkg", pkg_dir / "__init__.py", submodule_search_locations=[str(pkg_dir)])
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["spread_ref_pkg"] = mod
    spec.loader.exec_module(mod)
    pol = importlib.import_module("spread_ref_pkg.policy")
    return pol.Desk, tmpdir


def has_open_unbooked_gig(desk: Any) -> bool:
    for order_id, legs_map in desk.leg_gigs.items():
        if order_id not in desk.orders:
            continue
        for gid in legs_map.values():
            if gid not in desk.booked:
                return True
    return False


def next_nonbusy_wake(desk: Any, ends_at: int) -> tuple[int, list[DeskEventKind]]:
    """Earliest minute > desk.now outside busy hours when either busy() begins or desk.tick()
    could change state or emit an action, plus the event list to wake on."""
    now = desk.now
    p = desk.p
    day = now // DAY
    candidates = [ends_at]

    # 1. Next weekday busy start (07:00 Mon-Fri)
    busy_start = getattr(p, "busy_start_min", 7 * HOUR)
    for d in range(day, 5):
        bs = d * DAY + busy_start
        if bs > now:
            candidates.append(bs)
            break

    # 2. Weekday post-22:00 in-flight quote resolution (respondBy <= 22:15 must stay on same day for learn())
    tod = now % DAY
    if day < 5 and 22 * HOUR <= tod < 22 * HOUR + 20:
        if any(
            req_id not in desk.orders and req_id not in desk.lost_requests and now <= req["respondBy"]
            for req_id, req in desk.requests.items()
        ):
            candidates.append(min(ends_at, now + HOUR))

    # 3. Before Friday 22:00, preserve self.now <= order['deadline'] on night deliveries for dealer_trust parity
    if now < 4 * DAY + 22 * HOUR:
        if desk.dealer_trust:
            candidates.append((day + 1) * DAY)
        for oid, order in desk.orders.items():
            if any(d is None for d in order["deliveredAt"]):
                dl = order["deadline"]
                if dl > now:
                    # Wake at or before deadline (aligned to 1h step like play_practice) so self.now <= deadline holds
                    step_before_dl = now + ((dl - now) // HOUR) * HOUR
                    if step_before_dl > now:
                        candidates.append(step_before_dl)
                    else:
                        candidates.append(min(ends_at, now + HOUR))

    # 4. Any undelivered unstaffed order crossing lastPickupAt (+1) or late_reprice_grace_min (+1)
    for oid, order in desk.orders.items():
        if any(d is None for d in order["deliveredAt"]) and not desk.staffed(order):
            lp1 = order["lastPickupAt"] + 1
            if lp1 > now:
                candidates.append(lp1)
            if getattr(p, "urgent_hygiene", False) and getattr(p, "late_fee_open", 0) > 0 and not getattr(p, "late_repost", False):
                if oid not in desk.late_repriced:
                    lpg = order["lastPickupAt"] + getattr(p, "late_reprice_grace_min", 0) + 1
                    if lpg > now:
                        candidates.append(lpg)

    # 5. Deferred orders
    if getattr(desk, "deferred_orders", None):
        for oid, def_at in desk.deferred_orders.items():
            t_def = def_at + p.defer_multiday_min
            if t_def > now:
                candidates.append(t_def)

    # 6. Chain pairs / relays / hitch / proactive offers when any open unbooked gig exists
    wake_events: list[DeskEventKind] = list(URGENT)
    open_gig = has_open_unbooked_gig(desk)
    if open_gig:
        if 6 * HOUR <= tod < 21 * HOUR:
            candidates.append(now + HOUR)
        elif tod < 6 * HOUR:
            candidates.append(day * DAY + 7 * HOUR)
        else:
            candidates.append((day + 1) * DAY + 7 * HOUR)

    return min(candidates), wake_events


def play_fast_exact(world: Any, desk: Any, ends_at: int) -> Counter:
    """Provably 100% bit-exact to play_practice to the cent on every seed:
    1. Jumps Monday 00:00 -> busy_start (07:00) in 1 request instead of 7 empty 1h steps.
    2. After Friday 22:00 (when no more price_requests can arrive), whenever all undelivered orders
       are staffed (no open unbooked gig in leg_gigs and no post in actions), advances with
       `until=URGENT, max=ends_at` in 1 request instead of ~110 empty 1h steps (if an URGENT event
       like gig_dropped occurs at minute t, `until=URGENT` still stops at exact minute t)."""
    ledger: Counter = Counter()
    step_min = min(14, max(1, int(desk.p.step_min)))
    busy_start = getattr(desk.p, "busy_start_min", 7 * HOUR)
    while desk.now < ends_at:
        actions = desk.take_outbox()
        if busy(desk.now):
            step = world.advance(to=min(ends_at, desk.now + step_min), actions=actions)
        elif desk.now == 0 and busy_start > 0 and not actions:
            step = world.advance(until=URGENT, max=min(ends_at, busy_start), actions=actions)
        elif (
            desk.now >= 4 * DAY + 22 * HOUR
            and not any(a["type"] == "post" for a in actions)
            and not any(
                any(d is None for d in o["deliveredAt"]) and not desk.staffed(o)
                for o in desk.orders.values()
            )
            and not getattr(desk, "deferred_orders", None)
        ):
            step = world.advance(until=URGENT, max=ends_at, actions=actions)
        else:
            step = world.advance(until=URGENT, max=min(ends_at, desk.now + HOUR), actions=actions)
        desk.read_results(actions, step["results"])
        desk.now = step["now"]
        for event in step["events"]:
            if event["kind"] == "ledger":
                ledger[event["line"]["kind"]] += event["line"]["cents"]
            desk.handle(event)
        desk.tick()
    return ledger


def next_live_tick_wake(desk: Any, ends_at: int) -> int:
    """Earliest minute > desk.now at which desk.tick() could emit an action without a new event."""
    now = desk.now
    p = desk.p
    day = now // DAY
    cands = [ends_at]

    # 1. Morning supervisor at 08:00 Mon-Fri
    if getattr(p, "supervisor", False):
        for d in range(day, 5):
            if d not in desk.sup_days_done:
                t8 = d * DAY + 8 * HOUR
                if t8 > now:
                    cands.append(t8)
                    break

    # 2. Midnight trust stat
    if desk.dealer_trust:
        cands.append((day + 1) * DAY)

    # 3. Order crossing lastPickupAt / late_reprice_grace_min
    for oid, order in desk.orders.items():
        if any(d is None for d in order["deliveredAt"]) and not desk.staffed(order):
            for trig in (order["lastPickupAt"] + 1, order["lastPickupAt"] + getattr(p, "late_reprice_grace_min", 0) + 1):
                if trig > now:
                    cands.append(trig)

    # 4. Pending recent_views for view_offer_mult (fires when now - at >= 2 and now - posted_at >= view_offer_after_min)
    if getattr(p, "view_offer_mult", 0) > 0 and getattr(desk, "recent_views", None):
        for at, gid, _ in desk.recent_views:
            if gid not in desk.booked and gid in desk.posts:
                posted_at = desk.gig_posted_at.get(gid, now)
                fire_at = max(at + 2, posted_at + p.view_offer_after_min)
                if fire_at < day * DAY + 7 * HOUR:
                    fire_at = day * DAY + 7 * HOUR
                if fire_at > now and now - at <= max(15, p.view_offer_window_min) + 5:
                    cands.append(fire_at)

    # 5. dest_offer_mult
    if getattr(p, "dest_offer_mult", 0) > 0:
        for gid in desk.posts:
            if gid not in desk.booked and gid not in desk.dest_offered_gigs:
                fire_at = desk.gig_posted_at.get(gid, now) + p.dest_offer_delay_min
                if fire_at > now:
                    cands.append(fire_at)

    # 6. Deferred orders / chain pairs / cp-routes / cp-chains periodic wakes when open gigs exist
    if getattr(desk, "deferred_orders", None):
        for def_at in desk.deferred_orders.values():
            if def_at + p.defer_multiday_min > now:
                cands.append(def_at + p.defer_multiday_min)
    if has_open_unbooked_gig(desk) and (
        getattr(p, "net_relay", False)
        or getattr(p, "net_offer", False)
        or getattr(p, "hitch", False)
        or getattr(p, "return_offer_km", 0) > 0
        or (getattr(p, "chain_pair_km", 0) > 0 and getattr(desk, "chain_pairs", None))
    ):
        cands.append(now + 5)

    return min(cands)


def play_lean_urgent(world: Any, desk: Any, ends_at: int) -> Counter:
    """Organisers' lean event-driven runner (~350-450 requests/week):
    advances with `until=URGENT` (no blind 10-min polling and no per-view wakeups),
    waking periodically (every 15m in daytime) only while an unbooked gig is open so
    `view_offer_mult` and `net_offer` still fire inside their windows, and piggybacks actions on `advance`."""
    ledger: Counter = Counter()
    while desk.now < ends_at:
        actions = desk.take_outbox()
        open_gig = has_open_unbooked_gig(desk)
        wake_events: list[DeskEventKind] = list(URGENT)
        if getattr(desk.p, "net_offer", False) and open_gig:
            wake_events.append("gig_booked")
        target = next_live_tick_wake(desk, ends_at)
        if open_gig and (7 * HOUR <= desk.now % DAY < 21 * HOUR):
            target = min(target, desk.now + 15)
        step = world.advance(until=wake_events, max=min(ends_at, max(desk.now + 1, target)), actions=actions)
        desk.read_results(actions, step["results"])
        desk.now = step["now"]
        for event in step["events"]:
            if event["kind"] == "ledger":
                ledger[event["line"]["kind"]] += event["line"]["cents"]
            desk.handle(event)
        desk.tick()
    return ledger


def play_adaptive_14(world: Any, desk: Any, ends_at: int) -> Counter:
    """Organisers' ~350-request/week Level-8 client:
    - Whenever the previous step saw at least one `price_request` (active traffic), steps forward by up to 14m
      (bounded by `earliest_respond_by` of quotes in `actions`, though `actions` execute at the START of `advance`,
      so `to = min(ends_at, desk.now + 14)` guarantees every new request arriving in `(now, now+14]` still has
      `respondBy >= now + 1 + 15 = now + 16 > now + 14` on the NEXT step!).
    - Whenever no `price_request` arrived in the previous step (quiet morning/evening, outage, night, weekend,
      Mon+-Wed+), switches to `advance(until=URGENT, max=...)` to jump over all quiet time in 1 request!"""
    ledger: Counter = Counter()
    active_burst = False
    while desk.now < ends_at:
        actions = desk.take_outbox()
        if active_burst and desk.now < 5 * DAY:
            step = world.advance(to=min(ends_at, desk.now + 14), actions=actions)
        elif (
            desk.now >= 4 * DAY + 22 * HOUR
            and not any(a["type"] == "post" for a in actions)
            and not any(
                any(d is None for d in o["deliveredAt"]) and not desk.staffed(o)
                for o in desk.orders.values()
            )
            and not getattr(desk, "deferred_orders", None)
        ):
            step = world.advance(until=URGENT, max=ends_at, actions=actions)
        else:
            open_gig = has_open_unbooked_gig(desk)
            target = ends_at
            if desk.now < 5 * DAY:
                # Wake for morning supervisor at 08:00 if not yet run today
                d = desk.now // DAY
                if getattr(desk.p, "supervisor", False) and d not in desk.sup_days_done and desk.now < d * DAY + 8 * HOUR:
                    target = min(target, d * DAY + 8 * HOUR)
            if open_gig and (7 * HOUR <= desk.now % DAY < 21 * HOUR):
                target = min(target, desk.now + 30)
            elif desk.now < 4 * DAY + 22 * HOUR:
                target = min(target, ((desk.now // DAY) + 1) * DAY)
            step = world.advance(until=URGENT, max=min(ends_at, max(desk.now + 1, target)), actions=actions)
        desk.read_results(actions, step["results"])
        desk.now = step["now"]
        saw_req = False
        for event in step["events"]:
            if event["kind"] == "price_request":
                saw_req = True
            elif event["kind"] == "ledger":
                ledger[event["line"]["kind"]] += event["line"]["cents"]
            desk.handle(event)
        desk.tick()
        active_burst = saw_req
    return ledger


def play_live_sim(
    world: Any,
    desk: Any,
    ends_at: int,
    batched: bool = False,
    enforce_wall_budget: bool = True,
    assumed_http_rtt_ms: Optional[float] = None,
) -> tuple[Counter, dict[str, Any]]:
    """Simulates `play_live` on a practice world:
    - Feeds every event in exact `seq` order with `desk.now = max(desk.now, event['at'])`.
    - In `batched=False` (current `play_live`), calls `desk.handle(e) -> desk.tick() -> desk.send()` on EVERY event.
    - In `batched=True` (stream-draining `play_live`), processes all events arriving at the same timestamp `at`
      before calling `desk.tick() -> desk.send()`.
    - Tracks exact live wall-clock progression W[t] + measured CPU time + HTTP action RTT + final-actions bucket
      (20 actions/s, burst 50) and checks whether any quote misses `W[respondBy]`.
    """
    ledger: Counter = Counter()
    w_table = build_wall_clock_table(max(ends_at + 100, 14500))
    bucket = FinalActionBucket()
    worker_w = w_table[desk.now]
    live_stats: dict[str, Any] = {
        "events_total": 0,
        "ticks_run": 0,
        "http_act_batches": 0,
        "quotes_total": 0,
        "quotes_missed_respond_by": 0,
        "min_quote_slack_s": 9999.0,
        "max_stream_lag_s": 0.0,
        "rate_limit_wait_s": 0.0,
        "max_burst_events_same_min": 0,
    }

    # Measure baseline HTTP RTT once if not specified and not fakeworld
    rtt_s = (assumed_http_rtt_ms / 1000.0) if assumed_http_rtt_ms is not None else 0.0

    def flush_with_wall_budget(at_min: int, cpu_s: float) -> None:
        nonlocal worker_w
        event_w = w_table[min(at_min, len(w_table) - 1)]
        start_w = max(event_w, worker_w)
        finish_cpu_w = start_w + cpu_s
        actions = desk.outbox
        if not actions:
            desk.send()  # still record empty send() call for parity with play_live
            worker_w = finish_cpu_w
            live_stats["max_stream_lag_s"] = max(live_stats["max_stream_lag_s"], worker_w - event_w)
            return

        # Count how many HTTP batches of <=50 actions this send() requires
        n_batches = (len(actions) + 49) // 50
        wait_s = 0.0
        cur_w = finish_cpu_w
        for i in range(0, len(actions), 50):
            chunk_len = min(50, len(actions) - i)
            bw = bucket.take(cur_w, chunk_len)
            wait_s += bw
            cur_w += bw

        live_stats["rate_limit_wait_s"] += wait_s
        live_stats["http_act_batches"] += n_batches

        # Check quote deadlines against W[respondBy]
        kept_actions = []
        for a in actions:
            if a["type"] == "quote":
                live_stats["quotes_total"] += 1
                req = desk.requests.get(a["requestId"])
                if req is not None:
                    deadline_w = w_table[min(req["respondBy"], len(w_table) - 1)]
                    # Arrival at server is cur_w + (rtt_s if rtt_s > 0 else measured HTTP time)
                    est_arrive_w = cur_w + (rtt_s if rtt_s > 0 else 0.030) * n_batches
                    slack_w = deadline_w - est_arrive_w
                    live_stats["min_quote_slack_s"] = min(live_stats["min_quote_slack_s"], slack_w)
                    if slack_w < 0:
                        live_stats["quotes_missed_respond_by"] += 1
                        if enforce_wall_budget:
                            continue
            kept_actions.append(a)

        desk.outbox = kept_actions
        t_http0 = time.perf_counter_ns()
        desk.send()
        measured_http_s = (time.perf_counter_ns() - t_http0) / 1e9
        eff_http_s = (rtt_s * n_batches) if rtt_s > 0 else measured_http_s
        worker_w = cur_w + eff_http_s
        live_stats["max_stream_lag_s"] = max(live_stats["max_stream_lag_s"], worker_w - event_w)

    while desk.now < ends_at:
        wake_events: list[DeskEventKind] = list(URGENT)
        if has_open_unbooked_gig(desk) and getattr(desk.p, "view_offer_mult", 0) > 0:
            wake_events.append("gig_viewed")
        if getattr(desk.p, "net_offer", False) or getattr(desk, "deferred_orders", None):
            wake_events.append("gig_booked")
        if getattr(desk, "recent_views", None):
            wake_events.extend(["delivered", "offer_answered"])
        wake_events = list(dict.fromkeys(wake_events))

        target = next_live_tick_wake(desk, ends_at)
        step = world.advance(until=wake_events, max=min(ends_at, max(desk.now + 1, target)), actions=[])
        ev_list = step["events"]

        if not ev_list:
            desk.now = max(desk.now, step["now"])
            t0 = time.perf_counter_ns()
            desk.tick()
            cpu_s = (time.perf_counter_ns() - t0) / 1e9
            live_stats["ticks_run"] += 1
            flush_with_wall_budget(desk.now, cpu_s)
            continue

        # Count burst size at same minute
        by_min = Counter(e["at"] for e in ev_list)
        if by_min:
            live_stats["max_burst_events_same_min"] = max(
                live_stats["max_burst_events_same_min"], max(by_min.values())
            )

        if not batched:
            for event in ev_list:
                live_stats["events_total"] += 1
                desk.now = max(desk.now, event["at"])
                if event["kind"] == "ledger":
                    ledger[event["line"]["kind"]] += event["line"]["cents"]
                t0 = time.perf_counter_ns()
                desk.handle(event)
                desk.tick()
                cpu_s = (time.perf_counter_ns() - t0) / 1e9
                live_stats["ticks_run"] += 1
                flush_with_wall_budget(desk.now, cpu_s)
        else:
            # Drain all events sharing the same `at` timestamp before running tick() + send()
            idx = 0
            while idx < len(ev_list):
                cur_at = ev_list[idx]["at"]
                desk.now = max(desk.now, cur_at)
                t0 = time.perf_counter_ns()
                while idx < len(ev_list) and ev_list[idx]["at"] == cur_at:
                    event = ev_list[idx]
                    live_stats["events_total"] += 1
                    if event["kind"] == "ledger":
                        ledger[event["line"]["kind"]] += event["line"]["cents"]
                    desk.handle(event)
                    idx += 1
                desk.tick()
                cpu_s = (time.perf_counter_ns() - t0) / 1e9
                live_stats["ticks_run"] += 1
                flush_with_wall_budget(desk.now, cpu_s)

        if step["now"] > desk.now:
            desk.now = step["now"]
            t0 = time.perf_counter_ns()
            desk.tick()
            cpu_s = (time.perf_counter_ns() - t0) / 1e9
            live_stats["ticks_run"] += 1
            flush_with_wall_budget(desk.now, cpu_s)

    live_stats["min_quote_slack_s"] = round(live_stats["min_quote_slack_s"], 3)
    live_stats["max_stream_lag_s"] = round(live_stats["max_stream_lag_s"], 3)
    live_stats["rate_limit_wait_s"] = round(live_stats["rate_limit_wait_s"], 3)
    return ledger, live_stats


def print_markdown_report(title: str, row: dict[str, Any]) -> None:
    prof = row["profile"]
    print()
    print(f"### {title} (`{row['seed']}`, mode=`{row['mode']}`)")
    print(
        f"- **Score:** margin **€{row['margin']:,.2f}** · won **{row['won']}** · "
        f"on-time **{row['on_time']:.2%}** · ranked=`{row['ranked']}`"
    )
    print(
        f"- **Harness:** **{row['requests']}** HTTP requests · **{row['wall_s']:.2f}s** total wall · "
        f"rejoin **{prof['rejoin']['max_ms']:.2f} ms**"
    )
    if "live_stats" in row:
        ls = row["live_stats"]
        print(
            f"- **Live budget:** events={ls['events_total']} · ticks={ls['ticks_run']} · "
            f"POST /actions batches={ls['http_act_batches']} · max burst={ls['max_burst_events_same_min']} events/min · "
            f"max stream lag=**{ls['max_stream_lag_s']:.3f}s** · min quote slack=**{ls['min_quote_slack_s']:.3f}s** · "
            f"missed respondBy=**{ls['quotes_missed_respond_by']}/{ls['quotes_total']}**"
        )
    print()
    print("| Call | Count | Total ms | p50 ms | p95 ms | p99 ms | Max ms | >10 ms | >50 ms |")
    print("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for label, key in [
        ("`handle` (CPU excl send)", "handle_cpu"),
        ("`handle` (wall incl send)", "handle_total"),
        ("`tick` (CPU excl send)", "tick_cpu"),
        ("`tick` (wall incl send)", "tick_total"),
        ("`send` (non-empty HTTP)", "send_nonempty"),
        ("`send` (all calls)", "send_all"),
        ("`world.advance` (HTTP)", "advance_http"),
        ("`rejoin` (end-of-week)", "rejoin"),
    ]:
        s = prof[key]
        print(
            f"| {label} | {s['count']} | {s['total_ms']:.1f} | {s['p50_ms']:.3f} | "
            f"{s['p95_ms']:.3f} | {s['p99_ms']:.3f} | {s['max_ms']:.3f} | {s['over_10ms']} | {s['over_50ms']} |"
        )

    print()
    print("| `handle` by event kind (CPU / wall) | Count | CPU total ms | CPU p50 ms | CPU p99 ms | CPU max ms | Wall max ms | Wall >50 ms |")
    print("|---|---:|---:|---:|---:|---:|---:|---:|")
    for kind, sc in prof["handle_by_kind_cpu"].items():
        st = prof["handle_by_kind_total"][kind]
        print(
            f"| `{kind}` | {sc['count']} | {sc['total_ms']:.1f} | {sc['p50_ms']:.3f} | "
            f"{sc['p99_ms']:.3f} | {sc['max_ms']:.3f} | {st['max_ms']:.3f} | {st['over_50ms']} |"
        )


def run_one(
    cls: Any,
    params: dict[str, Any],
    seed: str,
    level: int,
    mode: str,
    fake: bool = False,
    assumed_http_rtt_ms: Optional[float] = None,
    test_rejoin: bool = True,
) -> dict[str, Any]:
    p = cls.Params.from_dict(params)
    if fake:
        from spread_lab.env import lab_home
        from tas_fakeworld import FakeWorld  # type: ignore

        world_map = json.loads((lab_home() / "map.json").read_text(encoding="utf-8"))
        geo = Geo(world_map)
        t0 = time.perf_counter()
        world = FakeWorld(seed, world_map)
        snapshot = world.snapshot()
        roster = world.roster()
        desk = cls(world, p, level, geo, roster, snapshot["now"])
        profiler = DeskProfiler(desk)
        live_stats = None
        if mode == "practice":
            ledger = play_practice(world, desk, snapshot["endsAt"])
        elif mode == "fast-exact":
            ledger = play_fast_exact(world, desk, snapshot["endsAt"])
        elif mode == "adaptive-14":
            ledger = play_adaptive_14(world, desk, snapshot["endsAt"])
        elif mode in ("until-urgent", "lean-urgent"):
            ledger = play_lean_urgent(world, desk, snapshot["endsAt"])
        elif mode in ("live", "live-batched"):
            ledger, live_stats = play_live_sim(
                world, desk, snapshot["endsAt"], batched=(mode == "live-batched"), assumed_http_rtt_ms=assumed_http_rtt_ms
            )
        else:
            raise ValueError(f"Unknown mode {mode!r}")
        score = world.score()
        wall_s = time.perf_counter() - t0
        if test_rejoin:
            snap_end = world.snapshot()
            hist_end = world.events()
            desk2 = cls(world, p, level, geo, roster, snap_end["now"])
            t_rej0 = time.perf_counter_ns()
            desk2.rejoin(snap_end, hist_end)
            profiler.rejoin_ns.append(time.perf_counter_ns() - t_rej0)
        reqs = len(profiler.advance_http_ns) + len(profiler.act_http_ns) + 4
    else:
        client = CountingClient()
        geo = Geo(load_map(client))
        print(f"[timing] acquiring slot for {seed} ({mode})...", flush=True)
        slot_obj = Slot()
        # Heartbeat thread while acquiring slot or running
        import threading

        done_ev = threading.Event()
        state_box = ["waiting for slot"]

        def _hb() -> None:
            while not done_ev.wait(20.0):
                print(f"[timing] {seed} ({mode}): {state_box[0]} (reqs={client.requests})", flush=True)

        hb_thread = threading.Thread(target=_hb, daemon=True)
        hb_thread.start()
        try:
            with slot_obj:
                state_box[0] = "creating world"
                t0 = time.perf_counter()
                world = create_world(client, level, seed)
                entry = register(world.id, {"seed": seed, "level": level, "tool": "desk_timing", "mode": mode})
                try:
                    state_box[0] = f"playing {world.id}"
                    snapshot = world.snapshot()
                    roster = world.roster()
                    desk = cls(world, p, level, geo, roster, snapshot["now"])
                    profiler = DeskProfiler(desk)
                    live_stats = None
                    if mode == "practice":
                        ledger = play_practice(world, desk, snapshot["endsAt"])
                    elif mode == "fast-exact":
                        ledger = play_fast_exact(world, desk, snapshot["endsAt"])
                    elif mode == "adaptive-14":
                        ledger = play_adaptive_14(world, desk, snapshot["endsAt"])
                    elif mode in ("until-urgent", "lean-urgent"):
                        ledger = play_lean_urgent(world, desk, snapshot["endsAt"])
                    elif mode in ("live", "live-batched"):
                        ledger, live_stats = play_live_sim(
                            world,
                            desk,
                            snapshot["endsAt"],
                            batched=(mode == "live-batched"),
                            assumed_http_rtt_ms=assumed_http_rtt_ms,
                        )
                    else:
                        raise ValueError(f"Unknown mode {mode!r}")
                    score = world.score()
                    reqs = client.requests
                    wall_s = time.perf_counter() - t0
                    if test_rejoin:
                        snap_end = world.snapshot()
                        hist_end = world.events()
                        desk2 = cls(world, p, level, geo, roster, snap_end["now"])
                        t_rej0 = time.perf_counter_ns()
                        desk2.rejoin(snap_end, hist_end)
                        profiler.rejoin_ns.append(time.perf_counter_ns() - t_rej0)
                except BaseException:
                    try:
                        world.delete()
                    except Exception:
                        pass
                    raise
                finally:
                    entry.unlink(missing_ok=True)
        finally:
            done_ev.set()

    out: dict[str, Any] = {
        "seed": seed,
        "level": level,
        "mode": mode,
        "margin": score["marginCents"] / 100.0,
        "margin_cents": score["marginCents"],
        "revenue": score["revenueCents"] / 100.0,
        "won": score["wonOrders"],
        "on_time": score["onTimeShare"],
        "ranked": score["ranked"],
        "requests": reqs,
        "wall_s": round(wall_s, 3),
        "ledger": {k: v / 100.0 for k, v in sorted(ledger.items())},
        "stats": dict(sorted(desk.stats.items())),
        "profile": profiler.report(),
    }
    if live_stats is not None:
        out["live_stats"] = live_stats
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Profile Desk latency and test live/low-request practice modes.")
    ap.add_argument("--policy", default=None, help="Policy spec module:Class (default: champion policy)")
    ap.add_argument("--git-ref", default=None, help="Load policy.py/notes.py from a git ref (e.g. origin/exp/stack-v7)")
    ap.add_argument("--no-champion", action="store_true", help="Start from raw Params() defaults instead of champion.json")
    ap.add_argument("-s", "--set", action="append", default=[], help="Override Params field key=value")
    ap.add_argument("--seed", default="dev-12", help="Comma-separated seeds (default: dev-12)")
    ap.add_argument("--level", type=int, default=8)
    ap.add_argument(
        "--mode",
        default="practice",
        help="Comma-separated modes: practice,fast-exact,until-urgent,live,live-batched",
    )
    ap.add_argument("--fake", action="store_true", help="Run offline against tas_fakeworld (0 slots, 0 network)")
    ap.add_argument("--http-rtt-ms", type=float, default=None, help="Override HTTP RTT (ms) in live wall-budget model")
    ap.add_argument("--title", default=None, help="Report heading")
    ap.add_argument("--json-out", default=None, help="Optional path to write full JSON results")
    args = ap.parse_args()

    if args.fake and str(REPO / "experiments" / "scripts") not in sys.path:
        sys.path.insert(0, str(REPO / "experiments" / "scripts"))

    champ_data = json.loads((CHAMPION / "champion.json").read_text(encoding="utf-8"))
    tmpdir: Optional[Path] = None
    try:
        if args.git_ref:
            cls, tmpdir = load_policy_from_git_ref(args.git_ref)
        else:
            cls = load_policy(args.policy or champ_data["policy"])

        base_params: dict[str, Any] = {} if args.no_champion else dict(champ_data["params"])
        # Filter base_params to known fields if testing an older ref
        known = set(asdict(cls.Params()).keys())
        base_params = {k: v for k, v in base_params.items() if k in known}
        overrides = parse_overrides(cls, args.set)
        params = {**base_params, **overrides}

        seeds = [s.strip() for s in args.seed.split(",") if s.strip()]
        modes = [m.strip() for m in args.mode.split(",") if m.strip()]
        all_rows = []
        for mode in modes:
            for seed in seeds:
                title = args.title or (args.git_ref or args.policy or "champion-v6")
                row = run_one(
                    cls,
                    params,
                    seed=seed,
                    level=args.level,
                    mode=mode,
                    fake=args.fake,
                    assumed_http_rtt_ms=args.http_rtt_ms,
                )
                all_rows.append(row)
                print_markdown_report(title, row)

        if args.json_out:
            Path(args.json_out).write_text(json.dumps(all_rows, indent=2), encoding="utf-8")
    finally:
        if tmpdir is not None:
            shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    main()
