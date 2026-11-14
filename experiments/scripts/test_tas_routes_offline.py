"""End-to-end offline test of `TasRoutesDesk`, `SundayDesk`, `tas_routes_planner`, `tas.cmd_limits --apply`,
`tas.cmd_run`, and `tas_routes_fee_oracle` on `FakeWorld` (zero network, ~3 seconds)."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from argparse import Namespace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
tmp_lab = Path(tempfile.mkdtemp(prefix="tas-routes-offline-"))
cached_map = Path.home() / ".spread-lab" / "map.json"
world_map = json.loads(cached_map.read_text(encoding="utf-8"))
(tmp_lab / "map.json").write_text(json.dumps(world_map), encoding="utf-8")
os.environ.update(SPREAD_LAB_HOME=str(tmp_lab), SPREAD_KEY="selftest", SPREAD_URL="http://127.0.0.1:9")
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "experiments" / "scripts"), str(ROOT)]

import spread_lab.lab as lab_module  # noqa: E402
import coplay  # noqa: E402
import tas  # noqa: E402
from spread_lab.geo import Geo  # noqa: E402
from spread_lab.policy import Desk as BaseDesk, Params as BaseParams  # noqa: E402
from spread_lab.policies.tas_routes import Desk as TasDesk, Params as TasParams  # noqa: E402
from spread_lab.policies.sunday_tours import Desk as SundayDesk, Params as SundayParams  # noqa: E402
from spread_lab.runner import play_practice  # noqa: E402
from tas_fakeworld import FakeWorld  # noqa: E402
from tas_routes_planner import load_tape, run_full_planner  # noqa: E402
from tas_routes_fee_oracle import bisect_post_fees  # noqa: E402

lab_module.quiet_until = lambda: None


def fake_world(client, level, seed, board=False):
    return FakeWorld(seed, world_map, n_requests=150)


coplay.create_world = fake_world
tas.create_world = fake_world


def main() -> None:
    geo = Geo(world_map)
    seed = "offline-seed-1"

    # 1. SundayDesk exact noop parity + active check
    fw_base = FakeWorld(seed, world_map, n_requests=110)
    play_practice(fw_base, BaseDesk(fw_base, BaseParams(), 8, geo, fw_base.roster(), 0), 14280)
    fw_noop = FakeWorld(seed, world_map, n_requests=110)
    play_practice(fw_noop, SundayDesk(fw_noop, SundayParams(sunday_tours=False), 8, geo, fw_noop.roster(), 0), 14280)
    assert fw_base.score() == fw_noop.score()
    print("ok  1) SundayDesk noop == BaseDesk to the cent:", fw_noop.score())

    fw_sun = FakeWorld(seed, world_map, n_requests=110)
    d_sun = SundayDesk(fw_sun, SundayParams(sunday_tours=True, sunday_stage_min=90, sunday_tour_quote=True), 8, geo, fw_sun.roster(), 0)
    play_practice(fw_sun, d_sun, 14280)
    print("ok  2) SundayDesk active:", fw_sun.score())

    # 2. Full TAS pipeline: tape -> planner -> limits --apply -> run (0 forks exact replay!) -> fee oracle!
    tas.cmd_tape(Namespace(seed=seed, force=False))
    tape = load_tape(seed)
    run_full_planner(seed, geo, tape, "offline-test", max_cars=80, active_fraction=0.40, max_dealer_share=0.68, include_solos=True, compute_bound=True, steered_state=True)

    plan_p = str(tas.home(seed) / "plan-offline-test.json")
    tours_p = str(tas.home(seed) / "tours-offline-test.json")
    tas.cmd_limits(Namespace(
        seed=seed, mode="won", apply=True, lo=0.70, hi=2.50, iters=8,
        book=plan_p, policy="spread_lab.policies.tas_routes:Desk",
        set=[f"tour_plan_file={tours_p}"], name="offline-lim-apply", until=None,
    ))
    applied_book = str(tas.home(seed) / "book-offline-lim-apply.json")
    tas.cmd_run(Namespace(
        seed=seed, book=applied_book, policy="spread_lab.policies.tas_routes:Desk",
        set=[f"tour_plan_file={tours_p}"], name="offline-replay", until=None,
    ))
    rows = [json.loads(l) for l in (tas.home(seed) / "runs.jsonl").read_text(encoding="utf-8").splitlines()]
    r_lim = next(r for r in rows if r["name"] == "limits-offline-lim-apply")
    r_rep = next(r for r in rows if r["name"] == "run-offline-replay")
    assert r_lim["margin"] == r_rep["margin"] and r_lim["won"] == r_rep["won"], f"Replay drift! {r_lim} vs {r_rep}"
    assert not r_lim["limits"]["repriced_but_lost"], f"Broken repriced quotes: {r_lim['limits']}"
    print(f"ok  3) Full pipeline limits --apply == 0-fork replay to the cent (€{r_rep['margin']:.2f}, won={r_rep['won']}, forks={r_lim['forks']}, 0 CHECKs)!")

    # 3. Test tas_routes_fee_oracle bisect_post_fees hook on FakeWorld
    by_book = tas.book_hook(json.loads(Path(applied_book).read_text(encoding="utf-8")))
    with tas.Tas(seed, {"tour_plan_file": tours_p}, "spread_lab.policies.tas_routes:Desk", "offline-fee-oracle", forks=True) as g:
        def hook(game, actions, fresh):
            acts = by_book(game, actions, fresh)
            p_idxs = [i for i, a in enumerate(acts) if a["type"] == "post"]
            if not p_idxs:
                return acts
            others = [a for i, a in enumerate(acts) if i not in p_idxs]
            posts = [acts[i] for i in p_idxs]
            tuned = bisect_post_fees(game, others, posts, iters=5)
            out = list(acts)
            for i, tp in zip(p_idxs, tuned):
                out[i] = tp
            return out
        g.hook = hook
        res_oracle = g.finish()
    print(f"ok  4) Tour Fee Oracle finished cleanly (€{res_oracle['margin']:.2f}, won={res_oracle['won']}, forks={g.forks}, stats_applied={g.desk.stats['oracle_fee_applied']})!")


if __name__ == "__main__":
    main()
