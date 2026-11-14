"""Collect and reveal all finished level-8 worlds of v2 and v3/v3T into temp directory."""
from __future__ import annotations

import glob
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from spread_lab.env import REPO, lab_home

CACHE_ROOT = Path("/home/lab/.gemini/tmp/d14-02-acceptance-model/reveals")


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def git_jsonl(rev: str, rel: str) -> list[dict]:
    try:
        out = subprocess.check_output(["git", "show", f"{rev}:{rel}"], cwd=REPO, text=True)
        return [json.loads(l) for l in out.splitlines() if l.strip()]
    except Exception:
        return []


def find_existing_reveals() -> dict[str, Path]:
    existing: dict[str, Path] = {}
    patterns = [
        "/tmp/reveal*",
        "/tmp/reveals*/*",
        "/home/lab/.gemini/tmp/*/reveal*",
        "/home/lab/.gemini/tmp/*/*/reveal*",
        str(CACHE_ROOT / "reveal-*"),
    ]
    for pat in patterns:
        for p_str in sorted(glob.glob(pat)):
            p = Path(p_str)
            if p.is_dir() and (p / "requests.csv").exists() and (p / "events.csv").exists() and (p / "legs.csv").exists():
                existing[p.name.removeprefix("reveal-")] = p
    return existing


def collect_target_worlds() -> list[dict]:
    targets: dict[str, dict] = {}

    def add_rows(rows: list[dict], version: str, source: str) -> None:
        for r in rows:
            if "world" in r and "error" not in r and r.get("level", 8) == 8:
                wid = r["world"]
                if wid not in targets:
                    targets[wid] = {
                        "world": wid,
                        "seed": r["seed"],
                        "version": version,
                        "source": source,
                        "margin": r.get("margin"),
                        "on_time": r.get("on_time"),
                        "won": r.get("won"),
                    }

    # 1. Champion v2 (git 34e7063~1)
    add_rows(git_jsonl("34e7063~1", "champion/results/dev-L8.jsonl"), "v2", "git-v2-dev")
    add_rows(git_jsonl("34e7063~1", "champion/results/holdout-L8.jsonl"), "v2", "git-v2-holdout")
    # v2 fresh32 (night-01..32)
    add_rows(load_jsonl(Path("/home/lab/spread/runs/20261114-002838-n-champ-fresh32/results.jsonl")), "v2", "v2-night32")

    # 2. Champion v3 (git a523d64) + validate-top / final-champion runs of pure v3
    add_rows(git_jsonl("a523d64", "champion/results/dev-L8.jsonl"), "v3", "git-v3-dev")
    add_rows(git_jsonl("a523d64", "champion/results/holdout-L8.jsonl"), "v3", "git-v3-holdout")
    add_rows(
        load_jsonl(Path("/home/lab/spread-wt/n14-06591-final-champion/runs/20261114-070833-fc-v3-final32/results.jsonl")),
        "v3",
        "fc-v3-final32",
    )

    # Check index.jsonl for any night-* run of v2 or v3 (e.g. 05161-validate-top)
    idx_path = lab_home() / "index.jsonl"
    if idx_path.exists():
        for line in idx_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            e = json.loads(line)
            if e.get("level") != 8:
                continue
            dpath = Path(e["dir"])
            branch = e.get("git", {}).get("branch", "")
            name = e.get("name", "")
            if "05161" in branch or "validate" in branch:
                if "v2" in name:
                    add_rows(load_jsonl(dpath / "results.jsonl"), "v2", name)
                elif "d-" in name.lower() or "v3" in name.lower() or "extring" in name.lower():
                    add_rows(load_jsonl(dpath / "results.jsonl"), "v3", name)

    # 3. Current Champion v3T (HEAD = v3 + late_fee_open=1.0)
    add_rows(load_jsonl(REPO / "champion/results/dev-L8.jsonl"), "v3T", "champ-v3T-dev")
    add_rows(load_jsonl(REPO / "champion/results/holdout-L8.jsonl"), "v3T", "champ-v3T-holdout")
    add_rows(
        load_jsonl(Path("/home/lab/spread-wt/n14-06591-final-champion/runs/20261114-073207-fc-v3T-night32/results.jsonl")),
        "v3T",
        "fc-v3T-night32",
    )
    add_rows(
        load_jsonl(Path("/home/lab/spread-wt/n14-06591-final-champion/runs/20261114-073349-fc-v3T-final32/results.jsonl")),
        "v3T",
        "fc-v3T-final32",
    )

    return list(targets.values())


def reveal_one(wid: str) -> tuple[str, bool, str]:
    out_dir = CACHE_ROOT / f"reveal-{wid}"
    if (out_dir / "requests.csv").exists() and (out_dir / "events.csv").exists():
        return wid, True, str(out_dir)
    proc = subprocess.run(
        ["uv", "run", "--project", str(REPO), "lab", "reveal", wid],
        cwd=CACHE_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if proc.returncode == 0 and (out_dir / "requests.csv").exists():
        return wid, True, str(out_dir)
    return wid, False, (proc.stderr or proc.stdout).strip()[:200]


def main() -> None:
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    existing = find_existing_reveals()
    targets = collect_target_worlds()
    by_ver: dict[str, int] = {}
    for t in targets:
        by_ver[t["version"]] = by_ver.get(t["version"], 0) + 1
    print(f"Target worlds collected: {len(targets)} {by_ver}")

    to_reveal = []
    manifest = []
    for t in targets:
        wid = t["world"]
        if wid in existing:
            manifest.append({**t, "dir": str(existing[wid])})
        else:
            to_reveal.append(t)

    print(f"Already revealed on disk: {len(manifest)}; need to reveal: {len(to_reveal)}")
    ok_new, fail_new = 0, 0
    errors = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futs = {pool.submit(reveal_one, t["world"]): t for t in to_reveal}
        for fut in as_completed(futs):
            t = futs[fut]
            wid, ok, info = fut.result()
            if ok:
                ok_new += 1
                manifest.append({**t, "dir": info})
            else:
                fail_new += 1
                if len(errors) < 5:
                    errors.append((t["version"], t["seed"], wid, info))

    manifest.sort(key=lambda x: (x["version"], x["seed"], x["world"]))
    (CACHE_ROOT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Newly revealed: {ok_new}, failed: {fail_new}, total in manifest: {len(manifest)}")
    for err in errors:
        print("  sample error:", err)
    by_ver_ok: dict[str, list[str]] = {}
    for m in manifest:
        by_ver_ok.setdefault(m["version"], []).append(m["seed"])
    for v, seeds in sorted(by_ver_ok.items()):
        prefixes = {}
        for s in seeds:
            p = s.split("-")[0]
            prefixes[p] = prefixes.get(p, 0) + 1
        print(f"  {v}: {len(seeds)} worlds, unique seeds={len(set(seeds))}, splits={prefixes}")
    all_seeds = sorted(set(m["seed"] for m in manifest))
    print(f"Total distinct seeds across manifest: {len(all_seeds)}")


if __name__ == "__main__":
    main()
