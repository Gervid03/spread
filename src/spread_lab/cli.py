"""`uv run lab <command>`: the one entry point. `uv run lab --help` lists the commands."""
from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path

from .env import REPO, lab_home, load_dotenv, slot_budget


def _policy_and_params(args) -> tuple[str, dict]:
    from .lab import champion, load_policy, parse_overrides
    champ = champion()
    policy = args.policy or champ["policy"]
    params: dict = {}
    if not args.fresh:
        params.update(champ.get("params", {}) if policy == champ["policy"] else {})
    if args.params:
        params.update(json.loads(Path(args.params).read_text(encoding="utf-8")))
    params.update(parse_overrides(load_policy(policy), args.set or []))
    load_policy(policy).Params.from_dict(params)  # fail early on a typo
    return policy, params


def _add_policy_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--policy", help="module:Class of the desk (default: the champion's)")
    p.add_argument("--params", help="JSON file of parameter overrides, applied over the champion's params")
    p.add_argument("-s", "--set", action="append", metavar="KEY=VALUE", help="one parameter override; repeatable")
    p.add_argument("--fresh", action="store_true", help="start from the Params defaults, not the champion's params")
    p.add_argument("--level", type=int, default=8, choices=range(1, 9))


def _seeds(args) -> list[str]:
    from .lab import seed_set
    if args.seeds:
        return [s.strip() for s in args.seeds.split(",") if s.strip()]
    return seed_set(args.set_name)


def cmd_eval(args) -> None:
    from .lab import champion_results, compare, evaluate, load_results, summarize
    policy, params = _policy_and_params(args)
    seeds = _seeds(args)
    name = args.name or "eval"
    print(f"Evaluating {policy} on {len(seeds)} seeds at level {args.level}, {args.workers or slot_budget()} at a time. Overrides: {params or 'none'}")
    out = evaluate(policy, params, seeds, args.level, name, workers=args.workers)
    rows = load_results(out)
    s = summarize(rows)
    print(f"\n{out}\n" + summary_text(s))
    base = champion_results() if args.vs == "champion" else (load_results(Path(args.vs)) if args.vs != "none" else [])
    c = compare(rows, base)
    if c:
        print(compare_text(c, "champion" if args.vs == "champion" else args.vs))


def summary_text(s: dict) -> str:
    if not s.get("n"):
        return "  no world finished"
    safe = "SAFE" if s["safe"] else "NOT SAFE (a seed unranked or under 92% on time, or a failure)"
    return (f"  mean margin €{s['margin_mean']:,.2f}  (median €{s['margin_median']:,.2f}, min €{s['margin_min']:,.2f})  "
            f"ranked {s['ranked']}/{s['n']}  on time min {s['on_time_min']:.1%} mean {s['on_time_mean']:.1%}  "
            f"won {s['won_mean']:.0f}  failed {s['failed']}  -> {safe}")


def compare_text(c: dict, label: str) -> str:
    t = f"t={c['t']}" if c["t"] is not None else ""
    return (f"  vs {label} on {c['n']} paired seeds: Δmargin €{c['delta_mean']:+,.2f} ± {c['delta_se']:,.2f} (SE) {t}  "
            f"better on {c['better']}, worse on {c['worse']}  Δon-time {c['on_time_delta_mean']:+.2%}")


def cmd_compare(args) -> None:
    from .lab import champion_results, compare, load_results, summarize
    a = load_results(Path(args.a))
    b = champion_results() if args.b == "champion" else load_results(Path(args.b))
    print(summary_text(summarize(a)))
    c = compare(a, b)
    print(compare_text(c, args.b) if c else "  no seeds in common")


def cmd_sweep(args) -> None:
    """Grid over parameters: every combination is one evaluation on the same seeds."""
    from .lab import champion_results, compare, evaluate, load_results, summarize
    policy, params = _policy_and_params(args)
    seeds = _seeds(args)
    axes = []
    for g in args.grid:
        key, _, values = g.partition("=")
        axes.append([(key, v) for v in values.split(",")])
    from .lab import load_policy, parse_overrides
    cls = load_policy(policy)
    table = []
    for combo in itertools.product(*axes):
        over = parse_overrides(cls, [f"{k}={v}" for k, v in combo])
        run_params = {**params, **over}
        label = ",".join(f"{k}={v}" for k, v in combo)
        print(f"\n=== {label}")
        out = evaluate(policy, run_params, seeds, args.level, f"{args.name or 'sweep'}-" + "-".join(f"{k}{v}" for k, v in combo)[:60],
                       workers=args.workers, quiet=True)
        rows = load_results(out)
        s, c = summarize(rows), compare(rows, champion_results())
        print(summary_text(s))
        if c:
            print(compare_text(c, "champion"))
        table.append((label, s, c, out))
    print("\n=== sweep, best mean margin first (SAFE = every seed ranked and >= 92% on time)")
    for label, s, c, out in sorted(table, key=lambda x: -(x[1].get("margin_mean") or -1e18)):
        d = f"Δ €{c['delta_mean']:+,.0f}±{c['delta_se']:,.0f}" if c else ""
        print(f"  {label:<50} €{s.get('margin_mean', 0):>10,.0f}  on-time min {s.get('on_time_min', 0):.1%}  "
              f"{'SAFE' if s.get('safe') else 'unsafe'}  {d}  {Path(out).name}")


def cmd_play(args) -> None:
    """One world, with a line per day: for reading what the desk does."""
    from .geo import Geo, load_map
    from .lab import CountingClient, Slot, create_world, load_policy, register
    from .runner import WEEKDAYS, play_practice
    policy, params = _policy_and_params(args)
    cls = load_policy(policy)
    client = CountingClient()
    geo = Geo(load_map(client))
    with Slot():
        world = create_world(client, args.level, args.seed)
        entry = register(world.id, {"seed": args.seed, "level": args.level})
        print(f"World {world.id}, level {args.level}, seed {args.seed}")
        try:
            snap = world.snapshot()
            desk = cls(world, cls.Params.from_dict(params), args.level, geo, world.roster(), snap["now"])

            def on_day(day: int) -> None:
                s = world.score()
                print(f"  {WEEKDAYS[day % 7]:<4} margin €{s['marginCents'] / 100:>10,.2f}  won {s['wonOrders']:>4}  "
                      f"on time {s['onTimeShare']:6.1%}  mult {desk.mult:.3f}", flush=True)
            if args.restart_at is not None:  # the final's failure mode: the desk dies and rebuilds from the server
                ledger = play_practice(world, desk, snap["endsAt"], on_day, stop_at=args.restart_at)
                desk.take_outbox()  # a crash loses whatever the desk had not sent yet
                old_stats = desk.stats
                desk = cls(world, cls.Params.from_dict(params), args.level, geo, world.roster(), desk.now)
                desk.rejoin(world.snapshot(), world.events())
                print(f"  -- restarted at minute {desk.now}: rejoined {len(desk.orders)} orders, {len(desk.posts)} live gigs, "
                      f"mult {desk.mult:.3f}, outbox {len(desk.outbox)}", flush=True)
                ledger.update(play_practice(world, desk, snap["endsAt"], on_day))
                desk.stats.update(old_stats)
            else:
                ledger = play_practice(world, desk, snap["endsAt"], on_day)
        except BaseException:
            world.delete()
            raise
        finally:
            entry.unlink(missing_ok=True)
    s = world.score()
    print(f"End: margin €{s['marginCents'] / 100:,.2f}  on time {s['onTimeShare']:.1%}  ranked {s['ranked']}  requests {client.requests}")
    print("Ledger:", {k: round(v / 100) for k, v in ledger.items()})
    print("Stats:", dict(sorted(desk.stats.items())))


def cmd_final(args) -> None:
    """Plays the live final or test final with the champion (or the given policy). Start it any time
    before the start; it waits, rejoins after crashes and restarts, and survives server restarts."""
    from spread.client import Client
    from .geo import Geo, load_map
    from .lab import load_policy
    from .runner import run_live_forever
    policy, params = _policy_and_params(args)
    cls = load_policy(policy)
    client = Client()
    geo = Geo(load_map(client))
    log_path = REPO / "runs" / "final.log"
    log_path.parent.mkdir(exist_ok=True)

    def log(text: str) -> None:
        print(text, flush=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(text + "\n")

    def make_desk(world, snapshot, now):
        level = next((w["level"] for w in client.worlds() if w["worldId"] == world.id), 8)
        return cls(world, cls.Params.from_dict(params), level, geo, world.roster(), now)
    log(f"Live desk: {policy} with {params or 'default params'}")
    run_live_forever(client, make_desk, log)


def cmd_board(args) -> None:
    """Plays the team's next ranking run at the level. It counts on the public practice rankings and
    each round allows 5 per level: for the lead, not for swarm agents."""
    if not args.yes:
        sys.exit("A ranking run counts publicly and each round has only 5 per level. Re-run with --yes if you mean it.")
    from .geo import Geo, load_map
    from .lab import CountingClient, load_policy
    from .runner import play_practice
    policy, params = _policy_and_params(args)
    cls = load_policy(policy)
    client = CountingClient()
    geo = Geo(load_map(client))
    world = client.create(level=args.level, board=True)
    print(f"Ranking run {world.id} at level {args.level} with {policy} {params or ''}")
    snap = world.snapshot()
    desk = cls(world, cls.Params.from_dict(params), args.level, geo, world.roster(), snap["now"])
    play_practice(world, desk, snap["endsAt"])
    s = world.score()
    print(f"End: margin €{s['marginCents'] / 100:,.2f}  won {s['wonOrders']}  on time {s['onTimeShare']:.1%}  ranked {s['ranked']}")


def cmd_leaderboard(args) -> None:
    from spread.client import Client
    board = Client().board(args.level)
    for key in ("current", "previous"):
        season = board.get(key)
        if not season:
            continue
        print(f"Level {args.level}, {key} round {season['season']} ({season['name']}):")
        teams = [t for t in season["teams"] if t["played"]]
        for t in teams[: args.top]:
            m = f"€{t['marginCents'] / 100:>10,.0f}" if t["marginCents"] is not None else "         -"
            runs = " ".join(f"{r['marginCents'] / 100:>7,.0f}{'' if r['ranked'] else '*'}" for r in t["runs"])
            print(f"  {str(t['rank'] or '-'):>3} {t['name'][:28]:<28} played {t['played']}  {m}  runs: {runs}")
        print("  (* = run under the delivery minimum)")


def cmd_runs(args) -> None:
    path = lab_home() / "index.jsonl"
    if not path.exists():
        print("No evaluations yet.")
        return
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    for r in rows[-args.last:]:
        s = r["summary"]
        if not s.get("n"):
            print(f"{r['started']}  {r['name']:<28} failed")
            continue
        print(f"{r['started']}  {r['name'][:28]:<28} L{r['level']} n={s['n']:<2} €{s['margin_mean']:>9,.0f}  on-time min {s['on_time_min']:.1%}  "
              f"{'SAFE' if s['safe'] else 'unsafe'}  {r['git'].get('branch', '')}@{r['git'].get('commit', '')}  {Path(r['dir']).name}")


def cmd_promote(args) -> None:
    from .lab import promote
    promote(Path(args.run), args.note)
    print(f"Champion is now {args.run}. Commit champion/ to make it official.")


def cmd_worlds(args) -> None:
    from spread.client import Client
    for w in Client().worlds():
        if args.all or not w["ended"]:
            print(w)


def cmd_reap(args) -> None:
    from spread.client import Client
    from .lab import reap
    n = reap(Client(), force=args.force)
    print(f"Deleted {n} world(s).")


def cmd_reveal(args) -> None:
    from spread import reveal_csv
    sys.argv = ["spread-reveal-csv", args.world]
    reveal_csv.main()


def cmd_docs(args) -> None:
    """Downloads the organisers' documents for offline reading (docs/kit/, gitignored)."""
    import os
    import urllib.request
    url = os.environ.get("SPREAD_URL", "https://spread.bahnexpress.com").rstrip("/")
    folder = REPO / "docs" / "kit"
    folder.mkdir(parents=True, exist_ok=True)
    for name, path in [("HANDBOOK.md", "/kit/HANDBOOK.md"), ("RULES.md", "/kit/RULES.md"), ("API.md", "/kit/API.md"),
                       ("openapi.json", "/openapi.json"), ("llms.txt", "/llms.txt")]:
        with urllib.request.urlopen(url + path, timeout=30) as answer:
            (folder / name).write_bytes(answer.read())
        print(f"docs/kit/{name}")


def main() -> None:
    for stream in (sys.stdout, sys.stderr):  # Windows consoles and redirects default to a legacy code page
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    load_dotenv()
    parser = argparse.ArgumentParser(prog="lab", description="Swarm Dispatch's lab for Spread. Reads SPREAD_KEY from .env.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("eval", help="evaluate a policy on a seed set and compare it with the champion")
    _add_policy_args(p)
    p.add_argument("--seeds-from", dest="set_name", default="dev", help="seed set: smoke, dev or holdout (files in seeds/)")
    p.add_argument("--seeds", help="comma-separated seeds instead of a set")
    p.add_argument("--name", help="a short label for the run folder")
    p.add_argument("--workers", type=int, help=f"worlds at once (default SPREAD_SLOTS={slot_budget()})")
    p.add_argument("--vs", default="champion", help="champion, none, or a run folder to compare with")
    p.set_defaults(func=cmd_eval)

    p = sub.add_parser("compare", help="paired comparison of two run folders (or a run and the champion)")
    p.add_argument("a")
    p.add_argument("b", nargs="?", default="champion")
    p.set_defaults(func=cmd_compare)

    p = sub.add_parser("sweep", help="grid over parameters, e.g. -g fee_open=0.9,1.0 -g min_supply=4,8")
    _add_policy_args(p)
    p.add_argument("-g", "--grid", action="append", required=True, metavar="KEY=V1,V2,...")
    p.add_argument("--seeds-from", dest="set_name", default="smoke")
    p.add_argument("--seeds")
    p.add_argument("--name")
    p.add_argument("--workers", type=int)
    p.set_defaults(func=cmd_sweep)

    p = sub.add_parser("play", help="play one seed with a line per day")
    _add_policy_args(p)
    p.add_argument("--seed", default="spread-1")
    p.add_argument("--restart-at", type=int, help="world minute at which to kill the desk and rebuild it from the server (tests rejoin)")
    p.set_defaults(func=cmd_play)

    p = sub.add_parser("final", help="play the live final / test final (the lead runs this)")
    _add_policy_args(p)
    p.set_defaults(func=cmd_final)

    p = sub.add_parser("board", help="play the next public ranking run (the lead only; needs --yes)")
    _add_policy_args(p)
    p.add_argument("--yes", action="store_true")
    p.set_defaults(func=cmd_board)

    p = sub.add_parser("leaderboard", help="the public practice rankings")
    p.add_argument("--level", type=int, default=8)
    p.add_argument("--top", type=int, default=15)
    p.set_defaults(func=cmd_leaderboard)

    p = sub.add_parser("runs", help="the latest evaluations from every checkout on this machine")
    p.add_argument("--last", type=int, default=25)
    p.set_defaults(func=cmd_runs)

    p = sub.add_parser("promote", help="make an evaluated run folder the champion (the lead only)")
    p.add_argument("run")
    p.add_argument("--note", default="")
    p.set_defaults(func=cmd_promote)

    p = sub.add_parser("worlds", help="the team's practice worlds that have not ended")
    p.add_argument("--all", action="store_true")
    p.set_defaults(func=cmd_worlds)

    p = sub.add_parser("reap", help="delete practice worlds left behind by killed processes")
    p.add_argument("--force", action="store_true", help="also unknown worlds (stops anyone else's practice runs!)")
    p.set_defaults(func=cmd_reap)

    p = sub.add_parser("docs", help="download the organisers' handbook, rules and API reference to docs/kit/")
    p.set_defaults(func=cmd_docs)

    p = sub.add_parser("reveal", help="write a finished world's reveal to CSV files (spread-reveal-csv)")
    p.add_argument("world")
    p.set_defaults(func=cmd_reveal)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
