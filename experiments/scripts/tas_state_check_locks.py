"""Read-only inspection of lock holders and progress of active TAS jsonl files."""
from __future__ import annotations

from pathlib import Path
from spread_lab.env import lab_home


def main() -> None:
    home = lab_home()
    for p in sorted((home / "slots").glob("*")) if (home / "slots").exists() else []:
        print("slot:", p.name, p.read_text(encoding="utf-8", errors="ignore").strip())
    for s in ("dev-12", "dev-01", "dev-08", "dev-07"):
        for f in sorted((home / "tas" / s).glob("*.jsonl")):
            lines = f.read_text(encoding="utf-8", errors="ignore").splitlines()
            print(f"{s}/{f.name}: {len(lines)} lines, mtime={int(f.stat().st_mtime)}")


if __name__ == "__main__":
    main()
