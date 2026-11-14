"""Verify SundayStateDesk neutrality and active execution on FakeWorld (0 network calls)."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from argparse import Namespace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REAL_HOME = Path.home() / ".spread-lab"

tmp = Path(tempfile.mkdtemp(prefix="tas-sun-test-"))
os.environ.update(SPREAD_LAB_HOME=str(tmp), SPREAD_KEY="selftest", SPREAD_URL="http://127.0.0.1:9")
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "experiments" / "scripts")]

wmap = json.loads((REAL_HOME / "map.json").read_text(encoding="utf-8"))
(tmp / "map.json").write_text(json.dumps(wmap), encoding="utf-8")

import spread_lab.lab as lab_module  # noqa: E402
import coplay  # noqa: E402
import tas  # noqa: E402
from tas_fakeworld import FakeWorld  # noqa: E402

lab_module.quiet_until = lambda: None
coplay.create_world = lambda client, level, seed, board=False: FakeWorld(seed, wmap)


def last_run(seed: str) -> dict:
    return json.loads((tas.home(seed) / "runs.jsonl").read_text(encoding="utf-8").splitlines()[-1])


SEED = "selftest-sunday"
tas.cmd_run(Namespace(seed=SEED, set=None, policy="spread_lab.policy:Desk", name="base", until=None, book=None))
base = last_run(SEED)
tas.cmd_run(Namespace(seed=SEED, set=None, policy="spread_lab.policies.sunday_state:Desk", name="noop", until=None, book=None))
noop = last_run(SEED)
assert base["margin"] == noop["margin"] and base["won"] == noop["won"] and base["on_time"] == noop["on_time"], (base, noop)
print(f"OK 1: SundayStateDesk neutral defaults match BaseDesk to the cent (€{noop['margin']:,.2f}, {noop['won']} won)")

tas.cmd_run(
    Namespace(
        seed=SEED,
        set=["sun_early_trust_rescue_h=4.5", "sun_trust_decouple=0.45", "sun_war_defer=true", "sun_comp_band=true"],
        policy="spread_lab.policies.sunday_state:Desk",
        name="active",
        until=None,
        book=None,
    )
)
act = last_run(SEED)
print(f"OK 2: SundayStateDesk active ran cleanly (€{act['margin']:,.2f}, {act['won']} won, {act['on_time']:.2%})")
