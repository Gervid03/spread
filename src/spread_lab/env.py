"""Environment: the team key from .env, the shared lab home, the slot budget."""
from __future__ import annotations

import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def load_dotenv() -> None:
    """Reads KEY=VALUE lines from the repo's .env (or the main checkout's, from a git worktree)
    into the environment, without overriding variables that are already set."""
    # uv might have injected env vars with \r from .env files, fix them:
    for k, v in os.environ.items():
        if v.endswith("\r"):
            os.environ[k] = v[:-1]
    
    candidates = [REPO / ".env"]
    common = REPO / ".git"
    if common.is_file():  # a worktree: .git is a file that points into the main checkout's .git/worktrees/
        text = common.read_text(encoding="utf-8").strip()
        if text.startswith("gitdir:"):
            gitdir = Path(text.split(":", 1)[1].strip())
            candidates.append(gitdir.parents[1].parent / ".env")
    for path in candidates:
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ.setdefault(key.strip(), value.strip().replace("\r", "").strip('"').strip("'"))
            break
    os.environ.setdefault("SPREAD_URL", "https://spread.bahnexpress.com")


def lab_home() -> Path:
    """State shared by every checkout and worktree on this machine: slot locks, the world registry,
    the map cache and the index of all evaluations."""
    home = Path(os.environ.get("SPREAD_LAB_HOME") or Path.home() / ".spread-lab").expanduser()
    home.mkdir(parents=True, exist_ok=True)
    return home


def slot_budget() -> int:
    """How many of the team's 8 practice worlds the harness may hold at once. The rest stay free
    for people: ranking runs, a live check, a fork by hand."""
    return max(1, min(8, int(os.environ.get("SPREAD_SLOTS", "6"))))
