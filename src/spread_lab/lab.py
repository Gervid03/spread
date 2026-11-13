"""The evaluation lab: run a policy on fixed seeds, in parallel, inside the team's practice limits,
and compare it with the champion on the same seeds.

Shared, machine-wide state lives in the lab home (`SPREAD_LAB_HOME`, default ~/.spread-lab), so every
checkout and git worktree on the machine shares one slot budget and one index of evaluations:

    slots/N.lock      one OS file lock per practice slot the harness may hold (SPREAD_SLOTS, default 6)
    worlds/<id>.json  the worlds the harness holds now, with their pid, for `lab reap`
    map.json          the map (the same in every world)
    index.jsonl       one summary line per evaluation, from every checkout
"""
from __future__ import annotations

import ctypes
import datetime as dt
import hashlib
import importlib
import json
import math
import os
import socket
import statistics
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path
from typing import Any, Optional

from filelock import FileLock, Timeout
from spread.client import Client, SpreadError, World

from .env import REPO, lab_home, slot_budget
from .geo import Geo, load_map
from .runner import play_practice

DEFAULT_POLICY = "spread_lab.policy:Desk"
CHAMPION = REPO / "champion"


# --- the team key's client, counting requests -----------------------------------------------------------
class CountingClient(Client):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.requests = 0

    def call(self, method, path, body=None, actions=0):
        self.requests += 1
        return super().call(method, path, body, actions)


# --- policies and params ----------------------------------------------------------------------------------
def load_policy(spec: str):
    module, _, name = spec.partition(":")
    return getattr(importlib.import_module(module), name or "Desk")


def parse_overrides(cls, pairs: list[str]) -> dict[str, Any]:
    """`key=value` strings, typed by the Params field they name."""
    types = {f: type(v) for f, v in asdict(cls.Params()).items()}
    out: dict[str, Any] = {}
    for pair in pairs:
        key, _, raw = pair.partition("=")
        key = key.strip()
        if key not in types:
            raise SystemExit(f"Unknown parameter {key!r} for {cls.__name__}.Params")
        kind = types[key]
        out[key] = (raw.lower() in ("1", "true", "yes")) if kind is bool else kind(raw)
    return out


def params_hash(policy: str, params: dict[str, Any]) -> str:
    return hashlib.sha1(json.dumps([policy, params], sort_keys=True).encode()).hexdigest()[:10]


def git_state() -> dict[str, Any]:
    def git(*args: str) -> str:
        try:
            return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, timeout=10).stdout.strip()
        except Exception:
            return ""
    return {"commit": git("rev-parse", "--short", "HEAD"), "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
            "dirty": bool(git("status", "--porcelain", "--untracked-files=no"))}


def seed_set(name: str) -> list[str]:
    path = REPO / "seeds" / f"{name}.txt"
    if not path.exists():
        raise SystemExit(f"No seed set {name!r}: sets are the files in seeds/")
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip() and not line.startswith("#")]


# --- practice slots, shared by every process on the machine -----------------------------------------------
class Slot:
    """Holds one of the harness's practice slots for the life of a `with` block (an OS file lock, so a
    crashed process frees its slot by itself)."""

    def __init__(self, budget: Optional[int] = None):
        self.budget = budget or slot_budget()
        self.lock: Optional[FileLock] = None

    def __enter__(self) -> "Slot":
        folder = lab_home() / "slots"
        folder.mkdir(exist_ok=True)
        while True:
            for i in range(self.budget):
                lock = FileLock(str(folder / f"{i}.lock"))
                try:
                    lock.acquire(timeout=0)
                    self.lock = lock
                    return self
                except Timeout:
                    continue
            time.sleep(0.5)

    def __exit__(self, *exc) -> None:
        if self.lock:
            self.lock.release()


def pid_alive(pid: int) -> bool:
    if pid == os.getpid():
        return True
    if os.name == "nt":  # os.kill(pid, 0) would terminate the process on Windows
        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        code = ctypes.c_ulong()
        ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
        ctypes.windll.kernel32.CloseHandle(handle)
        return code.value == 259  # STILL_ACTIVE
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def register(world_id: str, what: dict[str, Any]) -> Path:
    folder = lab_home() / "worlds"
    folder.mkdir(exist_ok=True)
    path = folder / f"{world_id}.json"
    path.write_text(json.dumps({"worldId": world_id, "pid": os.getpid(), "host": socket.gethostname(),
                                "started": time.time(), **what}), encoding="utf-8")
    return path


def reap(client: Client, force: bool = False, log=print) -> int:
    """Deletes practice worlds that hold a slot but belong to no running process on this machine: a
    harness that was killed hard leaves its world behind. Ranking runs and finals are never touched.
    With `force`, deletes every unended practice world of the team, also ones this machine does not know."""
    folder = lab_home() / "worlds"
    folder.mkdir(exist_ok=True)
    known = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in folder.glob("*.json")}
    host, deleted = socket.gethostname(), 0
    for w in client.worlds():
        if w["ended"] or w["kind"] != "practice" or w["boardRun"] is not None:
            continue
        entry = known.get(w["worldId"])
        orphan = (entry is not None and entry.get("host") == host and not pid_alive(int(entry["pid"]))) or (entry is None and force)
        if orphan:
            try:
                client.world(w["worldId"]).delete()
                deleted += 1
                log(f"deleted {w['worldId']} (level {w['level']})")
            except SpreadError as error:
                log(f"could not delete {w['worldId']}: {error}")
    for world_id, entry in known.items():  # forget registry entries of dead processes
        if entry.get("host") == host and not pid_alive(int(entry["pid"])):
            (folder / f"{world_id}.json").unlink(missing_ok=True)
    return deleted


def create_world(client: Client, level: int, seed: Optional[str], board: bool = False) -> World:
    """A new practice world. 409 means the team holds 8 unended worlds (another machine, a person, a
    leak): reap this machine's orphans and wait for a slot."""
    waited = 0.0
    while True:
        try:
            return client.create(level=level, seed=seed, board=board)
        except SpreadError as error:
            if error.status != 409 or board:
                raise
            if waited == 0:
                reap(client, log=lambda s: print(f"[reap] {s}", file=sys.stderr))
            if waited > 1800:
                raise
            time.sleep(5)
            waited += 5


# --- one world ----------------------------------------------------------------------------------------------
def run_world(policy: str, params: dict[str, Any], seed: str, level: int, slots: Optional[int] = None) -> dict[str, Any]:
    """Plays one practice world to its end with the policy and returns its result line."""
    cls = load_policy(policy)
    p = cls.Params.from_dict(params)
    client = CountingClient()
    geo = Geo(load_map(client))
    with Slot(slots):
        t0 = time.time()
        world = create_world(client, level, seed)
        entry = register(world.id, {"seed": seed, "level": level})
        try:
            snapshot = world.snapshot()
            desk = cls(world, p, level, geo, world.roster(), snapshot["now"])
            ledger = play_practice(world, desk, snapshot["endsAt"])
            score = world.score()
        except BaseException:
            try:
                world.delete()
            except Exception:
                pass
            raise
        finally:
            entry.unlink(missing_ok=True)
    return {
        "seed": seed, "level": level, "world": world.id,
        "margin": score["marginCents"] / 100, "revenue": score["revenueCents"] / 100,
        "won": score["wonOrders"], "on_time": score["onTimeShare"], "undelivered": score["undeliveredShare"],
        "ranked": score["ranked"],
        "ledger": {k: v / 100 for k, v in sorted(ledger.items())},
        "stats": dict(sorted(desk.stats.items())),
        "requests": client.requests, "seconds": round(time.time() - t0, 1),
    }


# --- many worlds ----------------------------------------------------------------------------------------------
def evaluate(policy: str, params: dict[str, Any], seeds: list[str], level: int, name: str, workers: Optional[int] = None,
             out_root: Optional[Path] = None, quiet: bool = False) -> Path:
    """Runs every seed (in parallel, within the slot budget), writes the run folder, appends the summary to
    the shared index, and returns the folder."""
    workers = workers or slot_budget()
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    out = (out_root or REPO / "runs") / f"{stamp}-{name}"
    out.mkdir(parents=True, exist_ok=True)
    meta = {"name": name, "policy": policy, "params": params, "params_hash": params_hash(policy, params), "level": level,
            "seeds": seeds, "started": stamp, "host": socket.gethostname(), "git": git_state(), "argv": sys.argv[1:]}
    (out / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    results: list[dict[str, Any]] = []
    lock = threading.Lock()
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as pool, open(out / "results.jsonl", "w", encoding="utf-8") as sink:
        futures = {pool.submit(run_world, policy, params, seed, level, workers): seed for seed in seeds}
        for future in as_completed(futures):
            seed = futures[future]
            try:
                row = future.result()
            except Exception as error:  # one broken world must not sink the others; it shows as failed
                row = {"seed": seed, "level": level, "error": f"{type(error).__name__}: {error}"}
            with lock:
                results.append(row)
                sink.write(json.dumps(row) + "\n")
                sink.flush()
            if not quiet:
                print(line_of(row), flush=True)
    summary = summarize(results)
    summary["seconds"] = round(time.time() - t0, 1)
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    with FileLock(str(lab_home() / "index.lock")):
        with open(lab_home() / "index.jsonl", "a", encoding="utf-8") as index:
            index.write(json.dumps({"dir": str(out), **{k: meta[k] for k in ("name", "policy", "params_hash", "level", "started", "git")},
                                    "params": params, "summary": summary}) + "\n")
    return out


def line_of(row: dict[str, Any]) -> str:
    if "error" in row:
        return f"  {row['seed']:<10} FAILED  {row['error']}"
    flag = "" if row["ranked"] else "  NOT RANKED"
    return (f"  {row['seed']:<10} margin €{row['margin']:>10,.2f}  won {row['won']:>4}  on time {row['on_time']:6.1%}  "
            f"req {row['requests']:>5}  {row['seconds']:>5.0f}s{flag}")


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    ok = [r for r in results if "error" not in r]
    if not ok:
        return {"n": 0, "failed": len(results)}
    margins = [r["margin"] for r in ok]
    on_time = [r["on_time"] for r in ok]
    return {
        "n": len(ok), "failed": len(results) - len(ok),
        "margin_mean": round(statistics.mean(margins), 2), "margin_median": round(statistics.median(margins), 2),
        "margin_min": round(min(margins), 2), "margin_sum": round(sum(margins), 2),
        "ranked": sum(1 for r in ok if r["ranked"]), "on_time_min": round(min(on_time), 4),
        "on_time_mean": round(statistics.mean(on_time), 4),
        "won_mean": round(statistics.mean(r["won"] for r in ok), 1),
        "requests_mean": round(statistics.mean(r["requests"] for r in ok)),
        "safe": all(r["ranked"] for r in ok) and min(on_time) >= 0.92 and len(ok) == len(results),
    }


def load_results(folder: Path) -> list[dict[str, Any]]:
    path = folder / "results.jsonl" if folder.is_dir() else folder
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def compare(candidate: list[dict[str, Any]], base: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """Paired comparison on the seeds both evaluated (worlds are deterministic, so a seed is a pair)."""
    by_seed = {(r["seed"], r["level"]): r for r in base if "error" not in r}
    pairs = [(r, by_seed[(r["seed"], r["level"])]) for r in candidate if "error" not in r and (r["seed"], r["level"]) in by_seed]
    if not pairs:
        return None
    deltas = [a["margin"] - b["margin"] for a, b in pairs]
    on_time = [a["on_time"] - b["on_time"] for a, b in pairs]
    mean = statistics.mean(deltas)
    se = statistics.stdev(deltas) / math.sqrt(len(deltas)) if len(deltas) > 1 else float("nan")
    return {"n": len(pairs), "delta_mean": round(mean, 2), "delta_se": round(se, 2),
            "t": round(mean / se, 2) if se and se == se and se > 0 else None,
            "better": sum(d > 0 for d in deltas), "worse": sum(d < 0 for d in deltas),
            "on_time_delta_mean": round(statistics.mean(on_time), 4)}


# --- the champion ---------------------------------------------------------------------------------------------
def champion() -> dict[str, Any]:
    path = CHAMPION / "champion.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"policy": DEFAULT_POLICY, "params": {}}


def champion_results() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted((CHAMPION / "results").glob("*.jsonl")):
        rows += load_results(path)
    return rows


def promote(folder: Path, note: str) -> None:
    """Makes an evaluated run the champion: its policy and params, and its per-seed results as the
    baseline that later runs are compared with. Results of other seed sets are kept only when the
    policy and params are the same."""
    meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    rows = load_results(folder)
    old = champion()
    same = old.get("policy") == meta["policy"] and old.get("params") == meta["params"]
    (CHAMPION / "results").mkdir(parents=True, exist_ok=True)
    if not same:
        for path in (CHAMPION / "results").glob("*.jsonl"):
            path.unlink()
    name = f"{Path(folder).name.split('-', 2)[-1]}-L{meta['level']}.jsonl"
    (CHAMPION / "results" / name).write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    summaries = dict(old.get("summary", {})) if same else {}
    summaries[name] = summarize(rows)
    record = {"policy": meta["policy"], "params": meta["params"], "params_hash": meta["params_hash"],
              "git": meta["git"], "promoted": dt.datetime.now().isoformat(timespec="minutes"), "note": note,
              "summary": summaries}
    (CHAMPION / "champion.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
