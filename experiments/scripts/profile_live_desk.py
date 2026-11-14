#!/usr/bin/env python3
"""Live-mode event-by-event latency profiler for Desk.handle() and Desk.tick() (0 slots)."""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from spread.client import Client
from spread_lab.env import load_dotenv
from spread_lab.geo import Geo, load_map
from spread_lab.policy import Desk, Params
from analyze_board_vs_dev import fetch_all_events


def parse_kv(item: str) -> tuple[str, Any]:
    k, raw = item.split("=", 1)
    if raw in ("True", "true"):
        return k, True
    if raw in ("False", "false"):
        return k, False
    try:
        return k, int(raw)
    except ValueError:
        try:
            return k, float(raw)
        except ValueError:
            return k, raw


class ReplayWorld:
    def __init__(self, wid: str) -> None:
        self.id = wid
        self._g = 0

    def act(self, actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        res = []
        for a in actions:
            if a["type"] == "post":
                self._g += 1
                res.append({"ok": True, "id": f"G{self._g:05d}"})
            else:
                res.append({"ok": True})
        return res


def profile_world(wid: str, params: Params, client: Client, geo: Geo) -> None:
    w = client.world(wid)
    roster = w.roster()
    events = fetch_all_events(w)

    rw = ReplayWorld(wid)
    desk = Desk(rw, params, 8, geo, roster, 420)

    # Map real order gigIds on booked/started/delivered events to current leg_gigs if needed
    quote_ms: list[float] = []
    handle_other_ms: list[float] = []
    tick_ms: list[float] = []

    t_wall0 = time.perf_counter()
    # Group events by timestamp <=1s burst or replay strictly 1-by-1 as worst-case live stream!
    for ev in events:
        desk.now = max(desk.now, ev["at"])
        # Remap gigId for order events when possible so pos_ledger / booked stay populated
        if ev.get("gigId") and ev["gigId"] not in desk.posts:
            oid = ev.get("orderId")
            leg = ev.get("leg", 0)
            if oid and oid in desk.leg_gigs and leg in desk.leg_gigs[oid]:
                ev = {**ev, "gigId": desk.leg_gigs[oid][leg]}
            else:
                open_gids = [g for g in desk.posts if g not in desk.booked]
                if open_gids and ev["kind"] == "gig_booked":
                    ev = {**ev, "gigId": open_gids[0]}

        t0 = time.perf_counter()
        desk.handle(ev)
        dt_h = (time.perf_counter() - t0) * 1000.0
        if ev["kind"] == "price_request":
            quote_ms.append(dt_h)
        else:
            handle_other_ms.append(dt_h)

        t1 = time.perf_counter()
        desk.tick()
        desk.send()
        dt_t = (time.perf_counter() - t1) * 1000.0
        tick_ms.append(dt_t)

    total_s = time.perf_counter() - t_wall0
    quote_ms.sort()
    tick_ms.sort()
    handle_other_ms.sort()

    def pct(arr: list[float], p: float) -> float:
        if not arr:
            return 0.0
        return arr[min(len(arr) - 1, int(len(arr) * p))]

    print(
        f"World {wid} ({len(events)} events, strict 1-by-1 live replay): total={total_s:.2f}s | "
        f"quote() p50={pct(quote_ms,0.5):.3f}ms p99={pct(quote_ms,0.99):.3f}ms max={max(quote_ms,default=0):.3f}ms | "
        f"tick() p50={pct(tick_ms,0.5):.3f}ms p99={pct(tick_ms,0.99):.3f}ms max={max(tick_ms,default=0):.3f}ms"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("-s", "--set", action="append", default=[])
    parser.add_argument("--world", default="wc8550ccd7438d978fbe3")
    args = parser.parse_args()

    champ = json.loads(Path("champion/champion.json").read_text())
    p_dict = dict(champ["params"])
    for item in args.set:
        k, v = parse_kv(item)
        p_dict[k] = v
    params = Params(**p_dict)

    load_dotenv()
    client = Client()
    geo = Geo(load_map(client))
    profile_world(args.world, params, client, geo)


if __name__ == "__main__":
    main()
