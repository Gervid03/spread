"""Orchestrates TAS Layer 4 (`tas-state`) measurements in optimal priority order:
1. Core 4-world `tas-state-dp-safe` (`dev-12, dev-01, dev-08, dev-07`) + 0-fork `run --book` verification.
2. `dev-12` `tas-state-dp-edge` (`>=90%` OT edge) + 0-fork `run --book` verification.
3. 4-world `State + Exact Drop-Proof Fees` stack (`tas-state-plus-fees` on `book-tas-state-dp-safe.json`, ~50s/world).
4. `dev-12` isolated single-lever ablations (`L1-trust`, `L2-comp`, `L3-events`) + remaining `dp-edge` runs.
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


def run_limits_and_verify(tas_mod, seed: str, name: str, set_list: list[str], iters: int = 7) -> dict:
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


def run_priority_all(tas_mod, seeds: tuple[str, ...] = ("dev-12", "dev-01", "dev-08", "dev-07"), is_selftest: bool = False) -> None:
    import tas_state_fee_stack as fee_stack

    iters = 5 if is_selftest else 7

    # Stage 1: Core 4-world tas-state-dp-safe + dev-12 tas-state-dp-edge
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
        if seed == seeds[0]:
            run_limits_and_verify(
                tas_mod,
                seed,
                "tas-state-dp-edge",
                [*base_sets, "tas_dp_select=true", "tas_trust_farm=true", "tas_comp_steer=true", "tas_event_plan=true", "tas_late_edge=true", "tas_pool_rate=0.114"],
                iters=iters,
            )

    # Stage 2: 4-world State + Exact Drop-Proof Fees stack (~45s/world!)
    for seed in seeds:
        sdir = tas_mod.home(seed)
        bpath = sdir / "book-tas-state-dp-safe.json"
        if bpath.exists() and not has_completed_run(sdir, "stack-tas-state-plus-fees"):
            print()
            print(f">>> [{seed}] Running stack-tas-state-plus-fees (Prices + State + Exact Fees) ...", flush=True)
            fee_stack.run_state_plus_fees(tas_mod, seed, bpath, "tas-state-plus-fees", iters=4 if is_selftest else 6)

    # Stage 3: Single-lever ablations on dev-12 (first seed)
    s0 = seeds[0]
    s0_tape = str(tas_mod.home(s0) / "tape.json")
    b0 = [f"tas_seed={s0}", f"tas_tape_path={s0_tape}"]
    for cname, csets in [
        ("tas-state-L1-trust", [*b0, "tas_trust_farm=true"]),
        ("tas-state-L2-comp", [*b0, "tas_comp_steer=true"]),
        ("tas-state-L3-events", [*b0, "tas_event_plan=true"]),
    ]:
        run_limits_and_verify(tas_mod, s0, cname, csets, iters=iters)

    # Stage 4: Remaining dp-edge runs on dev-01, dev-08, dev-07
    for seed in seeds[1:]:
        sdir = tas_mod.home(seed)
        tape_path = str(sdir / "tape.json")
        base_sets = [f"tas_seed={seed}", f"tas_tape_path={tape_path}"]
        run_limits_and_verify(
            tas_mod,
            seed,
            "tas-state-dp-edge",
            [*base_sets, "tas_dp_select=true", "tas_trust_farm=true", "tas_comp_steer=true", "tas_event_plan=true", "tas_late_edge=true", "tas_pool_rate=0.114"],
            iters=iters,
        )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["all", "selftest"], required=True)
    args = ap.parse_args()

    if args.phase == "selftest":
        real_home = Path.home() / ".spread-lab"
        tmp = Path(tempfile.mkdtemp(prefix="tas-suite-prio-"))
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
        run_priority_all(tas, seeds=("selftest-12",), is_selftest=True)
        print("PRIORITY SELFTEST PASSED!", flush=True)
        return

    import tas
    run_priority_all(tas, seeds=("dev-12", "dev-01", "dev-08", "dev-07"), is_selftest=False)


if __name__ == "__main__":
    main()
