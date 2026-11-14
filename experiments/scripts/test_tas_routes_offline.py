"""Offline smoke test of `spread_lab.policies.tas_routes:Desk` on FakeWorld (zero network)."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from spread_lab.env import lab_home
from spread_lab.geo import Geo
from spread_lab.runner import play_practice
from experiments.scripts.tas_fakeworld import FakeWorld
from spread_lab.policies.tas_routes import Desk, Params


def main() -> None:
    world_map = json.loads((lab_home() / "map.json").read_text(encoding="utf-8"))
    geo = Geo(world_map)
    fw = FakeWorld("test-routes-1", world_map, n_requests=90)
    reqs = fw.s["requests"]

    # Create a tiny tour plan from two early requests + one broken tour
    tours = [
        {"id": "T0001", "rids": [reqs[0]["id"], reqs[1]["id"]]},
        {"id": "T0002", "rids": [reqs[2]["id"], "R99999"]},
    ]
    with tempfile.TemporaryDirectory() as tmp:
        plan_file = Path(tmp) / "tours.json"
        plan_file.write_text(json.dumps({"tours": tours}), encoding="utf-8")
        p = Params(tour_plan_file=str(plan_file), tour_dynamic=True, relay_offers=True)
        desk = Desk(fw, p, 8, geo, fw.roster(), 0)
        res = play_practice(fw, desk, 14280)
        print("FakeWorld run ok:", fw.score(), "tour stats:", {k: v for k, v in desk.stats.items() if "tour" in k or "relay" in k})
        assert fw.score()["wonOrders"] > 0


if __name__ == "__main__":
    main()
