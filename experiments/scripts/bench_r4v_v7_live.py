"""Benchmark realistic live per-call latency of spread_lab.policies.cycles:Desk + r4-volume-v7-dev2 flags."""
from __future__ import annotations

import json
import time

from spread_lab.env import lab_home
from spread_lab.geo import Geo
from spread_lab.policies.cycles import Desk, Params


class RealisticDummyWorld:
    def __init__(self) -> None:
        self._n = 0
        self.new_gigs: list[str] = []

    def act(self, actions: list[dict]) -> list[dict]:
        out = []
        for a in actions:
            if a["type"] == "post":
                self._n += 1
                gid = f"g{self._n}"
                self.new_gigs.append(gid)
                out.append({"ok": True, "id": gid})
            else:
                out.append({"ok": True})
        return out


def run_bench(overrides: dict, label: str) -> None:
    lh = lab_home()
    geo = Geo(json.loads((lh / "map.json").read_text()))
    tape = json.loads((lh / "tas" / "dev-12" / "tape.json").read_text())
    w = RealisticDummyWorld()
    p = Params.from_dict(overrides)
    desk = Desk(w, p, 8, geo, tape["roster"], 480)
    q_ms, w_ms, t_ms = [], [], []
    open_queue: list[tuple[int, str]] = []
    for idx, req in enumerate(tape["requests"]):
        desk.now = req["arrivedAt"]
        while open_queue and open_queue[0][0] <= desk.now:
            _, gid = open_queue.pop(0)
            if gid in desk.posts and gid not in desk.booked:
                desk.handle({"kind": "gig_booked", "at": desk.now, "gigId": gid, "driverId": tape["roster"][0]["id"], "feeCents": 5000})
        t0 = time.perf_counter()
        desk.handle({"kind": "price_request", "at": desk.now, "request": req})
        q_ms.append((time.perf_counter() - t0) * 1000.0)
        desk.send()
        if idx % 4 == 0:
            opt = req["options"][-1]
            order = {
                "id": req["id"],
                "dealerId": req["dealerId"],
                "option": opt["kind"],
                "priceCents": opt["listPriceCents"],
                "deadline": opt["deadline"],
                "lastPickupAt": opt["deadline"] - 180,
                "status": "waiting",
                "legs": req["legs"],
                "deliveredAt": [None] * len(req["legs"]),
            }
            t0 = time.perf_counter()
            desk.handle({"kind": "order_won", "at": desk.now, "order": order})
            w_ms.append((time.perf_counter() - t0) * 1000.0)
            desk.send()
        t0 = time.perf_counter()
        desk.tick()
        t_ms.append((time.perf_counter() - t0) * 1000.0)
        desk.send()
        while w.new_gigs:
            open_queue.append((desk.now + 45, w.new_gigs.pop(0)))

    print(f"[{label}] quote: mean={sum(q_ms)/len(q_ms):.2f}ms p99={sorted(q_ms)[int(0.99*len(q_ms))]:.2f}ms max={max(q_ms):.2f}ms | win: mean={sum(w_ms)/len(w_ms):.2f}ms max={max(w_ms):.2f}ms | tick: mean={sum(t_ms)/len(t_ms):.2f}ms p99={sorted(t_ms)[int(0.99*len(t_ms))]:.2f}ms max={max(t_ms):.2f}ms")


def main() -> None:
    run_bench({}, "Champion v7 baseline")
    run_bench({
        "r4v_cyc_unblock": True,
        "r4v_tradein_seq": True,
        "r4v_tradein_max_drive": 450,
        "return_hub_min_supply": 45,
        "return_hub_max_drive_min": 270,
        "ext_ring_max_drive_min": 260,
        "r4v_guard_return_hub": True,
        "lead_car_max_gap_km": 20.0,
        "r4v_lead_benign_notes": True,
        "r4v_lead_cross_slow": True,
    }, "Champion v7 + r4-volume-v7-dev2")


if __name__ == "__main__":
    main()
