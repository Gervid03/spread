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
from spread_lab.policies.sunday_tours import Desk as SundayDesk, Params as SundayParams
from spread_lab.policy import Desk as BaseDesk, Params as BaseParams


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
        play_practice(fw, desk, 14280)
        print("FakeWorld TasRoutesDesk ok:", fw.score(), "tour stats:", {k: v for k, v in desk.stats.items() if "tour" in k or "relay" in k})
        assert fw.score()["wonOrders"] > 0

    # Verify SundayDesk noop exact parity with BaseDesk
    fw_base = FakeWorld("test-sunday-parity", world_map, n_requests=110)
    d_base = BaseDesk(fw_base, BaseParams(), 8, geo, fw_base.roster(), 0)
    play_practice(fw_base, d_base, 14280)

    fw_noop = FakeWorld("test-sunday-parity", world_map, n_requests=110)
    d_noop = SundayDesk(fw_noop, SundayParams(sunday_tours=False), 8, geo, fw_noop.roster(), 0)
    play_practice(fw_noop, d_noop, 14280)
    assert fw_base.score() == fw_noop.score(), f"Noop mismatch: {fw_base.score()} vs {fw_noop.score()}"
    print("SundayDesk noop exact parity ok:", fw_noop.score())

    # Verify SundayDesk active mode
    fw_act = FakeWorld("test-sunday-parity", world_map, n_requests=110)
    d_act = SundayDesk(fw_act, SundayParams(sunday_tours=True, sunday_stage_min=90, sunday_tour_quote=True), 8, geo, fw_act.roster(), 0)
    play_practice(fw_act, d_act, 14280)
    print("SundayDesk active ok:", fw_act.score(), "sunday stats:", {k: v for k, v in d_act.stats.items() if "sunday" in k or "tour" in k})


if __name__ == "__main__":
    main()
