#!/usr/bin/env python3
"""The overnight lab's status (scripts/night.sh): workers, sweeps and every evaluation since the night began,
with the paired delta against the champion. Standard library only, so it runs with the system python3.
    python3 scripts/night_status.py              Markdown status (published as STATUS.md)
    python3 scripts/night_status.py --lead       the same plus the workers' reports and notes: the lead's input
    python3 scripts/night_status.py --reports D  writes each worker's final report to D/<slug>.md
"""
import json
import math
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNS, NIGHT, SWARM = ROOT / "runs", ROOT / "runs" / "night", ROOT / "runs" / "swarm"


def rows(path: Path) -> list:
    try:
        return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    except (OSError, ValueError):
        return []


CHAMP = {(r["seed"], r["level"]): r for p in sorted((ROOT / "champion" / "results").glob("*.jsonl")) for r in rows(p) if "error" not in r}


def paired(res: list) -> str:
    pairs = [(r, CHAMP[(r["seed"], r["level"])]) for r in res if "error" not in r and (r.get("seed"), r.get("level")) in CHAMP]
    if len(pairs) < 2:
        return "—"
    d = [a["margin"] - b["margin"] for a, b in pairs]
    se = statistics.stdev(d) / math.sqrt(len(d))
    t = statistics.mean(d) / se if se > 0 else 0
    return f"{statistics.mean(d):+,.0f} ± {se:,.0f} (t {t:+.1f}, {sum(x > 0 for x in d)}/{len(d)} better)"


def night_start() -> float:
    try:
        return float((NIGHT / "start").read_text())
    except (OSError, ValueError):
        return 0.0


def run_table(since: float) -> list:
    out = ["| run | worlds | margin mean | min margin | on-time min | SAFE | Δ vs champion (paired) |", "|---|---|---|---|---|---|---|"]
    dirs = sorted(d for d in RUNS.iterdir() if d.is_dir() and d.name not in ("night", "swarm") and d.stat().st_mtime >= since) if RUNS.exists() else []
    for d in dirs:
        res = rows(d / "results.jsonl")
        ok = [r for r in res if "error" not in r]
        if not ok:
            out.append(f"| {d.name} | {len(res)} failed | | | | | |")
            continue
        done = (d / "summary.json").exists()
        m = [r["margin"] for r in ok]
        safe = done and all(r["ranked"] for r in ok) and min(r["on_time"] for r in ok) >= 0.92 and len(ok) == len(res)
        out.append(f"| {d.name}{'' if done else ' (running)'} | {len(ok)}{f' +{len(res) - len(ok)} failed' if len(res) > len(ok) else ''} | "
                   f"{statistics.mean(m):,.0f} | {min(m):,.0f} | {min(r['on_time'] for r in ok):.1%} | {'SAFE' if safe else 'no'} | {paired(ok)} |")
    return out


def events(slug: str):
    for line in (SWARM / f"{slug}.jsonl").read_text(encoding="utf-8", errors="replace").splitlines() if (SWARM / f"{slug}.jsonl").exists() else []:
        try:
            yield json.loads(line)
        except ValueError:
            continue


def worker(slug: str) -> dict:
    tools, text, result = 0, [], None
    for e in events(slug):
        kind = e.get("type")
        if kind == "tool_use":
            tools += 1
        elif kind == "message" and e.get("role") == "assistant" and isinstance(e.get("content"), str):
            text.append(e["content"])
        elif kind == "result":
            result = e
    body = "".join(text)
    deltas = [x.strip() for x in body.splitlines() if "Δ" in x or "delta" in x.lower()]
    return {"tools": tools, "text": body, "result": result, "delta": deltas[-1][:160] if deltas else ""}


def workers() -> list:
    seen, order = {}, []
    for line in (NIGHT / "workers.tsv").read_text().splitlines() if (NIGHT / "workers.tsv").exists() else []:
        f = line.split("\t")
        if f[0] not in seen:
            order.append(f[0])
            seen[f[0]] = {"started": f[1], "prompt": f[2] if len(f) > 2 else "", "state": "running"}
        if len(f) > 2 and f[2] == "done":
            seen[f[0]].update(state=f"done {f[1]} ({f[3]})")
    return [(s, seen[s]) for s in order]


def remote_branches() -> set:
    try:
        out = subprocess.run(["git", "-C", str(ROOT), "branch", "-r", "--format=%(refname:short)"], capture_output=True, text=True, timeout=30).stdout
    except (OSError, subprocess.SubprocessError):
        return set()
    return {b.strip() for b in out.splitlines()}


def notes_on(branch: str) -> str:
    try:
        names = subprocess.run(["git", "-C", str(ROOT), "diff", "--name-only", "origin/main...", branch, "--", "experiments/"],
                               capture_output=True, text=True, timeout=30).stdout.split()
        names = [n for n in names if n.endswith(".md") and "/prompts/" not in n]
        return "\n\n".join(subprocess.run(["git", "-C", str(ROOT), "show", f"{branch}:{n}"], capture_output=True, text=True, timeout=30).stdout
                           for n in names)
    except (OSError, subprocess.SubprocessError):
        return ""


def main() -> None:
    args = sys.argv[1:]
    since = night_start()
    if args[:1] == ["--reports"]:
        dest = Path(args[1])
        dest.mkdir(parents=True, exist_ok=True)
        for slug, _ in workers():
            w = worker(slug)
            stats = json.dumps((w["result"] or {}).get("stats", {}))[:600]
            (dest / f"{slug}.md").write_text(f"# {slug}\ntool calls {w['tools']}; result {stats}\n\n## Its last words\n\n{w['text'][-4000:]}\n", encoding="utf-8")
        return
    deadline = (NIGHT / "deadline").read_text().strip() if (NIGHT / "deadline").exists() else "?"
    print(f"# Night status, {time.strftime('%Y-%m-%d %H:%M', time.gmtime())} UTC (ends {deadline})\n")
    branches = remote_branches()
    print("## Workers\n\n| worker | started (UTC) | state | tool calls | pushed | last Δ line |\n|---|---|---|---|---|---|")
    ws = workers()
    for slug, w in ws:
        info = worker(slug)
        pushed = "yes" if f"origin/exp/gemini-{slug}" in branches else "no"
        print(f"| {slug} | {w['started']} | {w['state']} | {info['tools']} | {pushed} | {info['delta'].replace('|', '/')} |")
    queued = sorted(p.name for p in (NIGHT / "queue").glob("*.md")) if (NIGHT / "queue").exists() else []
    print(f"\nQueued prompts: {', '.join(queued) or 'none'}\n")
    done = (NIGHT / "sweeps.done").read_text().splitlines() if (NIGHT / "sweeps.done").exists() else []
    print("## Sweeps started (in order; logs/sweep-NN.txt has each table)\n")
    print("\n".join(f"{i + 1:02d}. `{x}`" for i, x in enumerate(done)) or "none")
    try:
        cj = json.loads((ROOT / "champion" / "champion.json").read_text(encoding="utf-8"))
        dv = cj.get("summary", {}).get("dev-L8.jsonl", {})
        label = (f"Champion (promoted {cj.get('promoted', '?')}, git {cj.get('git', {}).get('commit', '?')}) on dev: margin mean "
                 f"{dv.get('margin_mean', 0):,.0f}, on-time min {dv.get('on_time_min', 0):.1%}")
    except Exception:
        label = "Champion: unreadable champion/champion.json"
    print(f"\n## Every evaluation since the night began\n\n{label}. Δ is paired on seeds the champion has (dev, holdout).\n")
    print("\n".join(run_table(since)))
    if args[:1] == ["--lead"]:
        print("\n## Each finished worker's last words\n")
        for slug, w in ws:
            if w["state"].startswith("done"):
                print(f"### {slug}\n\n{worker(slug)['text'][-2500:]}\n")
        print("\n## Experiment notes on the night's branches\n")
        for slug, _ in ws:
            b = f"origin/exp/gemini-{slug}"
            if b in branches:
                print(f"### {b}\n\n{notes_on(b)[:6000]}\n")
        ledger = NIGHT / "LEDGER.md"
        if ledger.exists():
            print("\n## The night's ledger so far\n\n" + ledger.read_text(encoding="utf-8")[-6000:])


if __name__ == "__main__":
    main()
