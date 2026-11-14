"""Test TasStateDesk against FakeWorld (no network, 0 slots):
1. Neutral defaults reproduce spread_lab.policy:Desk to the cent (Δ = €0.00).
2. Individual levers (tas_trust_farm, tas_comp_steer, tas_event_plan, tas_late_edge) and full tas_dp_select run cleanly with limits --apply and replay to the cent via run --book.
3. Also prints trust drops in limits-won-apply.jsonl across dev-12, dev-01, dev-08, dev-07.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from argparse import Namespace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REAL_HOME = Path.home() / ".spread-lab"

# 1. Inspect trust drops on real cached limits-won-apply.jsonl first
for s in ("dev-12", "dev-01", "dev-08", "dev-07"):
    lwa = REAL_HOME / "tas" / s / "limits-won-apply.jsonl"
    if lwa.exists():
        rows = [json.loads(l) for l in lwa.read_text(encoding="utf-8").splitlines() if l.strip()]
        prev: dict[str, int] = {}
        drops = []
        for r in rows:
            d, t = r["dealer"], r["trust"]
            if d in prev and t < prev[d]:
                drops.append((r["day"], r["at"], d, prev[d], t, r["rid"]))
            prev[d] = t
        print(f"Real cached {s}: {len(rows)} rows, trust halvings = {drops}")

# 2. Run FakeWorld plumbing & neutrality tests
lab = Path(tempfile.mkdtemp(prefix="tas-state-selftest-"))
os.environ.update(SPREAD_LAB_HOME=str(lab), SPREAD_KEY="selftest", SPREAD_URL="http://127.0.0.1:9")
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "experiments" / "scripts")]

world_map = json.loads((REAL_HOME / "map.json").read_text(encoding="utf-8"))
(lab / "map.json").write_text(json.dumps(world_map), encoding="utf-8")

import spread_lab.lab as lab_module  # noqa: E402
import coplay  # noqa: E402
import tas  # noqa: E402
from tas_fakeworld import FakeWorld  # noqa: E402

lab_module.quiet_until = lambda: None


def fake_world(client, level, seed, board=False):
    return FakeWorld(seed, world_map)


coplay.create_world = fake_world

SEED = "selftest-state"
tas.cmd_tape(Namespace(seed=SEED, force=False))
tape_path = str(tas.home(SEED) / "tape.json")


def last_run() -> dict:
    return json.loads((tas.home(SEED) / "runs.jsonl").read_text(encoding="utf-8").splitlines()[-1])


# Check 1: Neutral defaults
tas.cmd_run(Namespace(seed=SEED, set=None, policy="spread_lab.policy:Desk", name="base", until=None, book=None))
base = last_run()
tas.cmd_run(Namespace(seed=SEED, set=None, policy="spread_lab.policies.tas_state:TasStateDesk", name="noop", until=None, book=None))
noop = last_run()
assert base["margin"] == noop["margin"] and base["won"] == noop["won"] and base["on_time"] == noop["on_time"], (base, noop)
print(f"OK 1: TasStateDesk neutral defaults match BaseDesk to the cent (€{noop['margin']:,.2f}, {noop['won']} won, {noop['on_time']:.2%})")

# Check 2: Each lever + DP with limits --apply & book replay
for label, sets in [
    ("trust", [f"tas_tape_path={tape_path}", "tas_trust_farm=true"]),
    ("comp", [f"tas_tape_path={tape_path}", "tas_comp_steer=true"]),
    ("event", [f"tas_tape_path={tape_path}", "tas_event_plan=true"]),
    ("dp-safe", [f"tas_tape_path={tape_path}", "tas_dp_select=true"]),
    ("dp-edge", [f"tas_tape_path={tape_path}", "tas_dp_select=true", "tas_late_edge=true"]),
]:
    tas.cmd_limits(
        Namespace(
            seed=SEED,
            set=sets,
            policy="spread_lab.policies.tas_state:TasStateDesk",
            name=label,
            until=None,
            book=None,
            mode="won",
            apply=True,
            iters=9,
            lo=0.7,
            hi=2.6,
        )
    )
    lim_r = last_run()
    book_file = str(tas.home(SEED) / f"book-{label}.json")
    tas.cmd_run(
        Namespace(
            seed=SEED,
            set=sets,
            policy="spread_lab.policies.tas_state:TasStateDesk",
            name=f"rep-{label}",
            until=None,
            book=book_file,
        )
    )
    rep_r = last_run()
    assert abs(lim_r["margin"] - rep_r["margin"]) < 1e-6, f"Drift on {label}: {lim_r['margin']} vs {rep_r['margin']}"
    print(f"OK 2 ({label:<8}): €{lim_r['margin']:>9,.2f}  won={lim_r['won']:>3}  OT={lim_r['on_time']*100:5.1f}%  (replay exact to the cent)")

print("ALL TasStateDesk fakeworld checks PASSED!")
