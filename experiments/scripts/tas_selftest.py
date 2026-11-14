"""Checks the TAS primitives (scripts/tas.py) against the toy world: no key, no network, a few seconds.

    uv run python experiments/scripts/tas_selftest.py

It proves the plumbing, not the game: that probing on forks leaves the main line untouched, that the batch
bisection finds each toy dealer's hidden limit, that a week repriced at the limits wins the same orders, and that
its book replays to the cent without forks. Run it after you change tas.py, and before you spend practice slots.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import urllib.request
from argparse import Namespace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
lab = Path(tempfile.mkdtemp(prefix="tas-selftest-"))
os.environ.update(SPREAD_LAB_HOME=str(lab), SPREAD_KEY="selftest", SPREAD_URL="http://127.0.0.1:9")
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "experiments" / "scripts")]

cached = Path.home() / ".spread-lab" / "map.json"
if cached.exists():
    world_map = json.loads(cached.read_text(encoding="utf-8"))
else:  # the map needs no key
    world_map = json.loads(urllib.request.urlopen("https://spread.bahnexpress.com/v1/map", timeout=30).read())
(lab / "map.json").write_text(json.dumps(world_map), encoding="utf-8")

import spread_lab.lab as lab_module  # noqa: E402
import coplay  # noqa: E402
import tas  # noqa: E402
from tas_fakeworld import FakeWorld  # noqa: E402

lab_module.quiet_until = lambda: None
worlds: list[FakeWorld] = []


def fake_world(client, level, seed, board=False):
    worlds.append(FakeWorld(seed, world_map))
    return worlds[-1]


coplay.create_world = fake_world
SEED = "selftest-1"
args = dict(seed=SEED, set=None, policy=None, name=None, until=None, book=None)


def check(ok: bool, what: str) -> None:
    print(("ok    " if ok else "FAIL  ") + what)
    if not ok:
        raise SystemExit(1)


def runs() -> list[dict]:
    return [json.loads(line) for line in (tas.home(SEED) / "runs.jsonl").read_text(encoding="utf-8").splitlines()]


tas.cmd_tape(Namespace(seed=SEED, force=False))
tape = json.loads((tas.home(SEED) / "tape.json").read_text(encoding="utf-8"))
check(len(tape["requests"]) == 150 and len(tape["roster"]) > 0, "tape: every request of the week from a silent world")

tas.cmd_run(Namespace(**args))
tas.cmd_run(Namespace(**args))
base, again = runs()[-2:]
check(base["margin"] == again["margin"] and base["won"] == again["won"] and base["won"] > 20, f"the desk's week repeats to the cent ({base['won']} won)")
base_world = worlds[-1]

tas.cmd_limits(Namespace(**args, mode="won", apply=False, iters=9, lo=0.7, hi=2.6))
probed = runs()[-1]
main_world = next(w for w in reversed(worlds) if w.s["now"] >= w.s["ends_at"])
check(probed["margin"] == base["margin"] and probed["won"] == base["won"] and probed["forks"] > 0,
      f"probing on forks leaves the main line untouched ({probed['forks']} forks)")
lines = [json.loads(line) for line in (tas.home(SEED) / "limits-won.jsonl").read_text(encoding="utf-8").splitlines()]
truth = lambda l: main_world.s["limit_cents"][l["rid"]][l["option"]]   # noqa: E731  (the toy dealer's limit when it decided)
exact = [l for l in lines if l["bound"] == "exact"]
check(len(exact) >= 20 and all(l["lo"] <= truth(l) < l["hi"] and l["hi"] - l["lo"] <= max(100, l["list"] * 0.005) for l in exact),
      f"the bisection brackets every hidden limit within 0.5% of the list price ({len(exact)} orders)")
check(not probed["limits"]["repriced_but_lost"] and not probed["limits"]["preview_differs_from_main_line"], "previews agree with the main line")

tas.cmd_limits(Namespace(**args, mode="won", apply=True, iters=9, lo=0.7, hi=2.6))
perfect = runs()[-1]
left = perfect["limits"]["left_on_table"]
refunds = perfect["ledger"].get("late_refund", 0) - base["ledger"].get("late_refund", 0)
penalty = perfect["ledger"].get("undelivered_penalty", 0) - base["ledger"].get("undelivered_penalty", 0)
check(perfect["won"] == base["won"] and perfect["on_time"] == base["on_time"], "at the limits the desk wins the same orders, as often on time")
check(abs(perfect["revenue"] - base["revenue"] - left) < 0.01 and left > 0,
      f"its revenue is the desk's plus what was left on the table (€{left:,.0f}; refunds and penalties moved by €{refunds + penalty:,.0f})")
check(abs(perfect["ledger"]["driver_fee"] - base["ledger"]["driver_fee"]) < 0.01, "and the driver fees are the same: only prices changed")

tas.cmd_run(Namespace(**{**args, "book": str(tas.home(SEED) / "book-won-apply.json")}))
replay = runs()[-1]
check(replay["margin"] == perfect["margin"] and replay["forks"] == 0, "the book replays the perfect-price week to the cent without a fork")

tas.cmd_limits(Namespace(**{**args, "until": "Mon 15:00", "name": "all-mon"}, mode="all", apply=False, iters=6, lo=0.7, hi=2.6))
lines = [json.loads(line) for line in (tas.home(SEED) / "limits-all-mon.jsonl").read_text(encoding="utf-8").splitlines()]
check(len({(l["rid"], l["option"]) for l in lines}) == len(lines) and len({l["option"] for l in lines}) > 1
      and any(l["desk"] != "won" and l["lo"] for l in lines), f"mode all measures every option, also of requests the desk did not win ({len(lines)} lines)")
won_base = [l["rid"] for l in exact][:12]
plan = tas.home(SEED) / "plan.json"
plan.write_text(json.dumps({"*": "decline", **{l["rid"]: {"option": l["option"]} for l in exact[:12]}}), encoding="utf-8")
tas.cmd_limits(Namespace(**{**args, "book": str(plan)}, mode="won", apply=True, iters=9, lo=0.7, hi=2.6))
planned = runs()[-1]
lines = [json.loads(line) for line in (tas.home(SEED) / "limits-plan-won-apply.jsonl").read_text(encoding="utf-8").splitlines()]
check(planned["won"] == 12 and sorted(l["rid"] for l in lines) == sorted(won_base) and all(l["x"] > 1 for l in lines),
      "a plan (the cars to win by option, the rest declined) is played at the dealers' limits in one pass")
check(all(w.deleted for w in worlds if w.s["now"] < w.s["ends_at"]), "every fork and every stopped world was deleted")
print("All TAS self-tests pass (plumbing only: the toy world is not the game).")
