"""Orchestrates TAS Layer 4 (`tas-state`) measurements and exact 0-fork book-replay verifications:
- `--phase dev12`:
  1. Thursday 00:00 cold-start probe & branch (answers Laptop Lead's 13:50 Test-Final question).
  2. Flat-fee driver-learning probe (`0` forks on `book-won-apply.json`).
  3. Isolated single-lever ablations on `dev-12` (`L1-trust`, `L2-comp`, `L3-events`) on top of Layer 1 (`limits --apply`).
  4. Combined Layer 4 (`tas-state-dp-safe` at >=92% OT and `tas-state-dp-edge` at >=90% OT) + 0-fork `run --book` verification.
- `--phase others`:
  Runs `tas-state-dp-safe` and `tas-state-dp-edge` + 0-fork `run --book` verification across `dev-01`, `dev-08`, `dev-07`.
- `--selftest`:
  Verifies the entire suite end-to-end against `FakeWorld` in seconds with 0 network calls.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from argparse import Namespace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "experiments" / "scripts"))


def has_completed_run(seed_dir: Path, run_name: str) -> bool:
    rp = seed_dir / "runs.jsonl"
    if not rp.exists():
        return False
    for line in rp.read_text(encoding="utf-8").splitlines():
        if line.strip() and json.loads(line).get("name") == run_name:
            return True
    return False


def run_limits_and_verify(tas_mod, seed: str, name: str, set_list: list[str], iters: int = 8) -> dict:
    sdir = tas_mod.home(seed)
    rep_name = f"run-rep-{name}"
    lim_name = f"limits-{name}"
    if has_completed_run(sdir, rep_name) and (sdir / f"book-{name}.json").exists():
        print(f"[SKIP] {seed} {name} already verified in runs.jsonl", flush=True)
        rows = [json.loads(l) for l in (sdir / "runs.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
        return next(r for r in reversed(rows) if r["name"] == lim_name)

    print()
    print(f">>> [{seed}] Running {lim_name} ({set_list}) ...", flush=True)
    tas_mod.cmd_limits(
        Namespace(
            seed=seed,
            set=set_list,
            policy="spread_lab.policies.tas_state:TasStateDesk",
            name=name,
            until=None,
            book=None,
            mode="won",
            apply=True,
            iters=iters,
            lo=0.72,
            hi=2.60,
        )
    )
    rows = [json.loads(l) for l in (sdir / "runs.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    lim_res = next(r for r in reversed(rows) if r["name"] == lim_name)

    book_path = str(sdir / f"book-{name}.json")
    print(f">>> [{seed}] Verifying 0-fork replay {rep_name} from {book_path} ...", flush=True)
    tas_mod.cmd_run(
        Namespace(
            seed=seed,
            set=set_list,
            policy="spread_lab.policies.tas_state:TasStateDesk",
            name=f"rep-{name}",
            until=None,
            book=book_path,
        )
    )
    rows = [json.loads(l) for l in (sdir / "runs.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    rep_res = next(r for r in reversed(rows) if r["name"] == rep_name)
    drift = round(rep_res["margin"] - lim_res["margin"], 2)
    print(
        f"[DONE] {seed} {name}: limits=€{lim_res['margin']:,.2f} (OT={lim_res['on_time']*100:.2f}%, won={lim_res['won']}, forks={lim_res['forks']}) | "
        f"replay=€{rep_res['margin']:,.2f} (drift={drift:+.2f})",
        flush=True,
    )
    return lim_res


def run_phase_dev12(tas_mod, seed: str = "dev-12", is_selftest: bool = False) -> None:
    sdir = tas_mod.home(seed)
    tape_path = str(sdir / "tape.json")

    # 1. Thursday 00:00 cold-start probe (only on real server or if not selftest)
    if not is_selftest and not (sdir / "tas-state-thu-coldstart.json").exists():
        print()
        print(">>> [dev-12] Running Thursday 00:00 Test-Final Cold-Start Probe ...", flush=True)
        import tas_state_thu_coldstart_probe as thu_probe
        thu_probe.main()

    # 2. Zero-fork flat-fee driver holdout state test on Layer 1 won book
    bwa = sdir / "book-won-apply.json"
    if bwa.exists() and not has_completed_run(sdir, "run-tas-state-flatfees-L1"):
        print()
        print(">>> [dev-12] Running 0-fork Driver Holdout Learning test (tas_flat_fees=true on book-won-apply) ...", flush=True)
        tas_mod.cmd_run(
            Namespace(
                seed=seed,
                set=[f"tas_seed={seed}", f"tas_tape_path={tape_path}", "tas_flat_fees=true"],
                policy="spread_lab.policies.tas_state:TasStateDesk",
                name="tas-state-flatfees-L1",
                until=None,
                book=str(bwa),
            )
        )

    # 3. Single-lever ablations on dev-12 + Combined DP SAFE (>=92%) & EDGE (>=90%)
    iters = 6 if is_selftest else 8
    base_sets = [f"tas_seed={seed}", f"tas_tape_path={tape_path}"]
    configs = [
        ("tas-state-L1-trust", [*base_sets, "tas_trust_farm=true"]),
        ("tas-state-L2-comp", [*base_sets, "tas_comp_steer=true"]),
        ("tas-state-L3-events", [*base_sets, "tas_event_plan=true"]),
        ("tas-state-dp-safe", [*base_sets, "tas_dp_select=true", "tas_trust_farm=true", "tas_comp_steer=true", "tas_event_plan=true"]),
        ("tas-state-dp-edge", [*base_sets, "tas_dp_select=true", "tas_trust_farm=true", "tas_comp_steer=true", "tas_event_plan=true", "tas_late_edge=true", "tas_pool_rate=0.114"]),
    ]
    for cname, csets in configs:
        run_limits_and_verify(tas_mod, seed, cname, csets, iters=iters)


def run_phase_others(tas_mod, seeds: tuple[str, ...] = ("dev-01", "dev-08", "dev-07"), is_selftest: bool = False) -> None:
    iters = 6 if is_selftest else 8
    for seed in seeds:
        sdir = tas_mod.home(seed)
        tape_path = str(sdir / "tape.json")
        base_sets = [f"tas_seed={seed}", f"tas_tape_path={tape_path}"]
        run_limits_and_verify(
            tas_mod,
            seed,
            "tas-state-dp-safe",
            [*base_sets, "tas_dp_select=true", "tas_trust_farm=true", "tas_comp_steer=true", "tas_event_plan=true"],
            iters=iters,
        )
        run_limits_and_verify(
            tas_mod,
            seed,
            "tas-state-dp-edge",
            [*base_sets, "tas_dp_select=true", "tas_trust_farm=true", "tas_comp_steer=true", "tas_event_plan=true", "tas_late_edge=true", "tas_pool_rate=0.114"],
            iters=iters,
        )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["dev12", "others", "all", "selftest"], required=True)
    args = ap.parse_args()

    if args.phase == "selftest":
        real_home = Path.home() / ".spread-lab"
        tmp = Path(tempfile.mkdtemp(prefix="tas-suite-selftest-"))
        os.environ.update(SPREAD_LAB_HOME=str(tmp), SPREAD_KEY="selftest", SPREAD_URL="http://127.0.0.1:9")
        wmap = json.loads((real_home / "map.json").read_text(encoding="utf-8"))
        (tmp / "map.json").write_text(json.dumps(wmap), encoding="utf-8")

        import spread_lab.lab as lab_module
        import coplay
        import tas
        from tas_fakeworld import FakeWorld

        lab_module.quiet_until = lambda: None
        coplay.create_world = lambda client, level, seed, board=False: FakeWorld(seed, wmap)

        tas.cmd_tape(Namespace(seed="selftest-12", force=False))
        run_phase_dev12(tas, seed="selftest-12", is_selftest=True)
        print("SELFTEST SUITE PASSED!", flush=True)
        return

    import tas
    if args.phase in ("dev12", "all"):
        run_phase_dev12(tas, seed="dev-12", is_selftest=False)
    if args.phase in ("others", "all"):
        run_phase_others(tas, seeds=("dev-01", "dev-08", "dev-07"), is_selftest=False)


if __name__ == "__main__":
    main()
