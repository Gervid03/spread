"""TAS: the tool-assisted week. What would a dispatcher make who could save, reload and see the future?

A practice world gives a team the three tools of a tool-assisted run:
  * a savestate    `fork` copies a world at a minute, with the same future draws;
  * re-recording   the same seed and the same actions at the same minutes give the same week to the cent;
  * foresight      every team gets the same requests whatever it does, so a week played once is known.
This script holds the shared primitives. It builds on co-play's replay engine (scripts/coplay.py), so the
desk steps the world exactly as `play_practice` does, and its files live in ~/.spread-lab/tas/<seed>/.

    uv run python scripts/tas.py tape   --seed dev-12     every request of the week, the roster, the forecasts
                                                          (a silent week: no quotes, a dozen requests)
    uv run python scripts/tas.py limits --seed dev-12     the desk's own week, unchanged, and for every order it
                                                          wins the highest price the dealer would still have
                                                          paid, bisected on forks (the price oracle)
        --mode won|quoted|all   whose limit to measure: the orders won (default) · every request the desk
                                really quoted, every option · every request, every option (the demand curve)
        --apply                 also send each won quote at its limit: the same week at perfect prices
        --iters 9 --lo 0.7 --hi 2.6   the bisection: rounds, and the bracket as multiples of the list price
                                (9 rounds leave under 0.4% of the list price between a win and a loss)
        --until "Tue 07:00"     stop there (a cheap first look)
    uv run python scripts/tas.py run    --seed dev-12 --book <file>   the week again with a price book
                                                          (re-recording: no forks, one normal world)
    uv run python scripts/tas.py whatif --seed dev-12 --at "Tue 07:00" --variants '{"low fees": {"set": {"fee_open": 0.7}}}'
                                                          your ideas compared on forks: the desk plays to that
                                                          minute, then each variant and an unchanged control play
                                                          a copy of the world to the week's end (--until for less)
        --at "Mon 08:00,Tue 07:00,Wed 07:00" --pick       at each time, apply the best variant to the main line
                                                          and play on: a week steered by lookahead
    uv run python scripts/tas.py show   --seed dev-12     what is measured for the seed so far

Every command takes `-s key=value` (Params overrides on top of the champion's), `--policy module:Class` (a Desk
subclass with your staffing or selection) and `--name` (the label of its output files).

A price book is JSON: {"<request id>": {"option": "next_day", "cents": 41250} | "decline" | "desk", ...,
"*": "desk" | "decline"}. "*" is what happens to a request the book does not name (default "desk": the desk's
own quote). `limits` writes the book of everything it sent (book-<name>.json), so a week found with forks
replays without them. `limits --book <file> --apply` plays a book at the dealers' limits: an entry may then name
only the option ({"option": "next_day"}), and the oracle finds its price. That is how a plan is played: the
cars to win by option, "*": "decline", and one pass.

For your own oracles and experiments, import this module: `Tas` is the game with a hook on every batch of actions
before it reaches the world (`Tas(seed, forks=True)` for a game that forks); `on_fork(game, actions, to)` tries
raw actions on a copy; `branch(game, variants, until)` plays whole ideas on copies, desk and all, against a
control (a variant can be a function that rewires the copy's desk); `forked(game)` is the bare copy;
`probe_prices` is the batch bisection. A sketch:

    with Tas("dev-12", forks=True) as g:
        g.play_to(minute_of("Tue 07:00"))
        table = branch(g, {"my idea": lambda sub: setattr(sub.desk.p, "fee_open", 0.7)})
        print(branch_text(g.desk.now, table))

Slots: a game that forks holds two of the team's eight practice slots while it runs (its world, and one copy at
a time). Only TAS_LANES (default 2) such games run at once on a machine; the next one waits before it takes a
world. A plain `run` or `tape` is one ordinary world and does not wait.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import re
import statistics
import sys
import time
from collections import Counter, defaultdict
from contextlib import contextmanager, nullcontext
from pathlib import Path
from typing import Callable, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import coplay  # noqa: E402  (the replay engine: Game steps the world exactly as play_practice)

from filelock import FileLock, Timeout  # noqa: E402
from spread.client import SpreadError  # noqa: E402

from spread_lab.env import lab_home, load_dotenv  # noqa: E402
from spread_lab.lab import (  # noqa: E402
    CountingClient, Slot, champion, champion_results, load_policy, parse_overrides, register, wait_while_quiet,
)
from spread_lab.runner import DAY, clock  # noqa: E402

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
LANES = max(1, int(os.environ.get("TAS_LANES", "2")))   # fork-heavy games at a time on this machine


class Lane:
    """One of the machine's fork lanes. A game that forks holds its world and, one at a time, a copy: two practice
    slots of the team's eight, for as long as it runs. The other agents need slots too, so only `TAS_LANES` (2)
    such games run at once and the rest wait here, before they take a world."""

    def __init__(self):
        self.lock: Optional[FileLock] = None

    def take(self) -> "Lane":
        folder = lab_home() / "tas"
        folder.mkdir(parents=True, exist_ok=True)
        said = 0.0
        while self.lock is None:
            for i in range(LANES):
                lock = FileLock(str(folder / f"lane-{i}.lock"))
                try:
                    lock.acquire(timeout=0)
                    self.lock = lock
                    break
                except Timeout:
                    continue
            else:
                if time.time() - said > 60:   # a line a minute keeps an agent's shell alive
                    print(f"Waiting for a fork lane ({LANES} fork-heavy TAS runs at a time on this machine).", flush=True)
                    said = time.time()
                time.sleep(5)
        return self

    def release(self) -> None:
        if self.lock is not None:
            self.lock.release()
            self.lock = None


def home(seed: str) -> Path:
    path = lab_home() / "tas" / seed
    path.mkdir(parents=True, exist_ok=True)
    return path


def minute_of(text: str) -> int:
    m = re.match(r"(\w{3})\s+(\d{1,2}):(\d{2})", text)
    if not m:
        raise SystemExit(f"Cannot read the time {text!r}: write it like 'Tue 07:00'")
    return WEEKDAYS.index(m.group(1).title()) * DAY + int(m.group(2)) * 60 + int(m.group(3))


# --- the game: the desk on one seed, with a hook between the desk and the world ---------------------------------
class Tas(coplay.Game):
    """The desk on one seed. Every batch of actions passes `hook(game, actions, fresh)` on its way to the world:
    `fresh` are the indexes of the quotes that go out for the first time. The hook returns the actions to send,
    the same number in the same order (the desk matches results to actions by position). `outcome` collects
    what the dealers did on the main line: request id -> ("won", option, cents) or ("lost", None, None)."""

    def __init__(self, seed: str, params: Optional[dict] = None, policy: Optional[str] = None, name: str = "tas",
                 forks: bool = False):
        """`forks=True` for a game that will use `on_fork`: it waits for a fork lane before it takes a world."""
        champ = champion()
        super().__init__({"game": name, "seed": seed, "policy": policy or champ["policy"],
                          "params": {**champ["params"], **(params or {})}, "pauses": [], "now": 0})
        self.hook: Optional[Callable[["Tas", list, list], list]] = None
        self.quoted: dict[str, dict] = {}     # request id -> the prices that really went out
        self.outcome: dict[str, tuple] = {}
        self.expect: dict[str, str] = {}      # request id -> the option a repriced quote must win with
        self.forks = 0
        self.lane = Lane()
        self.heavy = forks
        self.held = {"slot": None, "busy": False}   # the fork slot (see `forked`); copy.copy shares this dict

    def __exit__(self, *exc):
        try:
            super().__exit__(*exc)
        finally:
            if self.held["slot"] is not None:
                self.held["slot"].__exit__(None, None, None)
                self.held["slot"] = None
            self.lane.release()

    def __enter__(self) -> "Tas":
        if self.heavy:
            self.lane.take()
        try:
            super().__enter__()
        except BaseException:
            self.lane.release()
            raise
        self._wire()
        return self

    def _wire(self) -> None:
        """Puts the hook between the desk and `self.world`: the desk's own `send()` goes through `act`, the runner
        through `advance`."""
        world = self.world
        act0, advance0 = world.act, world.advance

        def act(actions):
            return act0(self._through(list(actions)))

        def advance(to=None, by=None, until=None, max=None, actions=()):
            step = advance0(to=to, by=by, until=until, max=max, actions=self._through(list(actions)))
            self.outcome.update(outcomes(step["events"]))
            return step

        world.act, world.advance = act, advance

    def _through(self, actions: list) -> list:
        fresh = [i for i, a in enumerate(actions) if a["type"] == "quote" and a["requestId"] not in self.quoted]
        if fresh and self.hook is not None:
            sent = self.hook(self, actions, fresh)
            if len(sent) != len(actions):
                raise RuntimeError("A hook must return as many actions as it got, in the same order")
            actions = sent
        for i in fresh:
            self.quoted[actions[i]["requestId"]] = dict(actions[i]["prices"])
        return actions

    def finish(self, until: Optional[int] = None, say: Callable[[str], None] = print) -> dict:
        """Plays to `until` (or the end), with a line a world day, and returns the result."""
        end = self.ends_at if until is None else min(until, self.ends_at)
        while self.desk.now < end:
            day = self.desk.now // DAY
            wait_while_quiet()   # a long run stands still while a final or a test final is on
            self.play_to(min(end, (day + 1) * DAY))
            s = self.world.score()
            say(f"  {clock(self.desk.now)}  margin €{s['marginCents'] / 100:>10,.2f}  won {s['wonOrders']:>4}  "
                f"on time {s['onTimeShare']:6.1%}  forks {self.forks}")
        s = self.world.score()
        return {"seed": self.log["seed"], "until": clock(self.desk.now), "margin": s["marginCents"] / 100,
                "revenue": s["revenueCents"] / 100, "won": s["wonOrders"], "on_time": s["onTimeShare"], "ranked": s["ranked"],
                "ledger": {k: v / 100 for k, v in sorted(self.ledger.items())}, "forks": self.forks,
                "requests": self.client.requests, "policy": self.log["policy"]}


def outcomes(events: list) -> dict[str, tuple]:
    out: dict[str, tuple] = {}
    for e in events:
        if e["kind"] == "order_won":
            out[e["order"]["id"]] = ("won", e["order"]["option"], e["order"]["priceCents"])
        elif e["kind"] == "order_lost":
            out[e["requestId"]] = ("lost", None, None)
    return out


# --- the savestate ------------------------------------------------------------------------------------------------
def on_fork(g: Tas, actions: list, to: int) -> dict:
    """Copies the world at this minute, applies `actions` on the copy, plays the copy to minute `to` and deletes
    it. Returns the copy's answer: `results` of the actions and the `events` that are new on the copy. The main
    world does not move. A copy holds a practice slot for its lifetime (a second or so)."""
    with forked(g) as copy:
        return copy.advance(to=min(g.ends_at, to), actions=actions)


@contextmanager
def forked(g: Tas):
    """A copy of the game's world at this minute, deleted when the block ends. It uses the game's fork slot, which
    the game takes at its first fork and keeps to its end (shared with its branch copies); a fork inside a fork (a
    branch copy's own oracle) takes a slot of its own for its lifetime. Taking a slot per fork queued every fork
    behind the other agents' evals: one order measured in 13 minutes on the swarm host (14 Nov, 11:00)."""
    g.lane.take()   # at once when the game said `forks=True`; else it waits here, holding its world
    wait_while_quiet()   # a held slot does not check the quiet hours by itself: forks stop while a final is on
    held = g.held
    if held["slot"] is None:
        held["slot"] = Slot().__enter__()
    if held["busy"]:
        held, slot = None, Slot()
    else:
        held["busy"], slot = True, nullcontext()
    with slot:
        copy = None
        for _ in range(240):
            try:
                copy = g.world.fork()
                break
            except SpreadError as error:
                if error.status != 409:
                    raise
                time.sleep(5)   # the team holds 8 worlds: wait for another agent's world to end
        if copy is None:
            raise SystemExit("No practice slot came free for a fork in 20 minutes.")
        entry = register(copy.id, {"seed": g.log["seed"], "level": 8, "tas": "fork of " + g.world.id})
        try:
            copy._last_seq = g.world._last_seq   # the first advance of a copy answers with its whole history: skip it
            g.forks += 1
            if g.forks % 200 == 0:   # a sign of life: a world day can take many minutes of forks
                print(f"  … {clock(g.desk.now)}, {g.forks} forks", flush=True)
            yield copy
        finally:
            try:
                copy.delete()
            except Exception:
                pass
            entry.unlink(missing_ok=True)
            if held is not None:
                held["busy"] = False


# --- ideas compared on forks --------------------------------------------------------------------------------------
def branch(g: Tas, variants: dict, until: Optional[int] = None) -> dict[str, dict]:
    """Compares ideas on forks, from this minute, on the same future.

    Each variant plays a copy of the world with a copy of the desk (its books, its waiting actions, its Params) to
    `until` (default: the end of the week). So does "control", the desk unchanged. The main world and the main
    desk do not move, so you can branch again later, or apply the winner with `g.apply(moves)` and play on.
    A variant is one of:
      * co-play moves: {"set": {"fee_open": 0.7}, "quote": {"<request id prefix>": 1.2 | "decline"}, "raise": [...]}
      * a function `f(sub)`: `sub` is the copy's game. Change anything: `sub.desk.p`, `sub.desk.outbox`, the desk's
        books, `sub.hook` (a price book, an oracle), or replace methods of `sub.desk`.
      * None or {}: nothing (a second control).
    Returns name -> {margin, revenue, won, on_time, ranked, ledger, stats, delta}: `delta` is the margin against
    control. Compare with control, not with the main line: a copied desk may walk its sets in another order, so a
    copy can drift from the main line by itself. Each variant costs what the rest of the week costs (one fork)."""
    end = g.ends_at if until is None else min(until, g.ends_at)
    out: dict[str, dict] = {}
    for name, variant in {"control": None, **variants}.items():
        with forked(g) as world:
            sub = copy.copy(g)
            sub.world = world
            sub.desk = copy.deepcopy(g.desk, {id(g.world): world, id(g.geo): g.geo, id(g): sub, id(g.client): g.client})
            sub.ledger, sub.pnl = Counter(g.ledger), defaultdict(Counter, {k: Counter(v) for k, v in g.pnl.items()})
            sub.quoted, sub.outcome, sub.expect, sub.sent = dict(g.quoted), dict(g.outcome), {}, dict(g.sent)
            sub.seen, sub.turn_reqs, sub.booked, sub.record, sub.forks = Counter(), [], [], False, 0
            sub._wire()
            if callable(variant):
                variant(sub)
            elif variant:
                sub.apply(variant)
            sub.play_to(end)
            score = world.score()
            g.forks += sub.forks
            out[name] = {"margin": score["marginCents"] / 100, "revenue": score["revenueCents"] / 100, "won": score["wonOrders"],
                         "on_time": score["onTimeShare"], "ranked": score["ranked"], "until": clock(sub.desk.now),
                         "ledger": {k: v / 100 for k, v in sorted(sub.ledger.items())}, "stats": dict(sorted(sub.desk.stats.items()))}
    for row in out.values():
        row["delta"] = round(row["margin"] - out["control"]["margin"], 2)
    return out


def branch_text(at: int, table: dict[str, dict]) -> str:
    lines = [f"From {clock(at)}, each played to {next(iter(table.values()))['until']} on the same future:"]
    for name, r in table.items():
        lines.append(f"  {name:<28} €{r['margin']:>10,.2f} ({r['delta']:+,.2f})  won {r['won']:>4}  on time {r['on_time']:6.1%}"
                     + ("" if r["ranked"] else "  NOT RANKED"))
    return "\n".join(lines)


# --- the price oracle ---------------------------------------------------------------------------------------------
def probe_prices(g: Tas, quotes: list, targets: dict[str, str], lo_x: float, hi_x: float, iters: int,
                 known_win: Optional[dict[str, int]] = None, tol: int = 100) -> dict[str, dict]:
    """The highest price at which each dealer still buys, for many requests at once.

    `quotes` are the quote actions about to go out, `targets` maps request id -> the one option to measure for it.
    Each round is one fork: it quotes every target its trial price for that option alone (the other quotes go as
    they are), plays to the last response deadline and reads who won. Dealers decide each request by itself at its
    deadline, so one fork tests one price for every target. Rounds: the top of the bracket, the bottom, then
    `iters` halvings. `known_win` gives a price already seen to win (in cents), tried as the bottom.

    Returns request id -> {option, list, lo, hi, bound}: `lo` is the highest price seen to win and `hi` the lowest
    seen to lose (cents; None when never seen); bound is "exact" (lo < limit <= hi), ">=hi" (the top still won),
    "<lo" (the bottom lost) or "none" (the dealer gave no answer in time)."""
    desk, known_win = g.desk, known_win or {}
    state: dict[str, dict] = {}
    for rid, kind in targets.items():
        lst = next(o["listPriceCents"] for o in desk.requests[rid]["options"] if o["kind"] == kind)
        bottom = min(int(lst * lo_x), known_win.get(rid, 10 ** 12))
        top = max(int(lst * hi_x), int(known_win.get(rid, 0) * 1.5))
        state[rid] = {"option": kind, "list": lst, "lo": None, "hi": None, "bound": None, "bottom": bottom, "top": top}
    if not state:
        return {}
    to = max(desk.requests[rid]["respondBy"] for rid in state) + 1

    def fork_round(trial: dict[str, int]) -> dict[str, tuple]:
        acts = [{"type": "quote", "requestId": a["requestId"], "prices": {state[a["requestId"]]["option"]: trial[a["requestId"]]}}
                if a["requestId"] in trial else a for a in quotes]
        return outcomes(on_fork(g, acts, to)["events"])

    def read(seen: dict, trial: dict[str, int]) -> None:
        for rid, cents in trial.items():
            st, result = state[rid], seen.get(rid)
            if result is None:
                st["bound"] = "none"
            elif result[0] == "won":
                st["lo"] = cents if st["lo"] is None else max(st["lo"], cents)
            else:
                st["hi"] = cents if st["hi"] is None else min(st["hi"], cents)

    trial = {rid: st["top"] for rid, st in state.items()}
    read(fork_round(trial), trial)
    for st in state.values():
        if st["bound"] is None and st["lo"] is not None:
            st["bound"] = ">=hi"
    trial = {rid: st["bottom"] for rid, st in state.items() if st["bound"] is None}
    if trial:
        read(fork_round(trial), trial)
        for rid in trial:
            if state[rid]["bound"] is None and state[rid]["lo"] is None:
                state[rid]["bound"] = "<lo"
    for _ in range(iters):
        trial = {rid: (st["lo"] + st["hi"]) // 2 for rid, st in state.items() if st["bound"] is None and st["hi"] - st["lo"] > tol}
        if not trial:
            break
        read(fork_round(trial), trial)
    for st in state.values():
        st["bound"] = st["bound"] or "exact"
        del st["bottom"], st["top"]
    return state


def price_oracle(mode: str, apply: bool, lo_x: float, hi_x: float, iters: int, sink) -> Callable:
    """The hook of `limits`. One preview fork shows which of the batch's quotes win, and with which option. Then
    the targets are bisected: in "won" mode the option each winner took; in "quoted" mode every option the desk
    priced; in "all" mode every option of every request, declined ones too. With `apply`, each winner goes out at
    its limit for the option the dealer took, alone: the dealer, the competitor and the drivers only learn that we
    won, so the week stays the same and only the prices change."""
    def hook(g: Tas, actions: list, fresh: list) -> list:
        desk = g.desk
        quotes = [actions[i] for i in fresh]
        to = max(desk.requests[a["requestId"]]["respondBy"] for a in quotes) + 1
        preview = outcomes(on_fork(g, quotes, to)["events"])
        series: list[dict[str, str]] = []
        for a in quotes:
            rid = a["requestId"]
            request = desk.requests[rid]
            won = preview.get(rid, ("?",))[0] == "won"
            kinds = [preview[rid][1]] if won else []
            declined = is_decline(g, a)
            if mode == "quoted" and not declined:
                kinds += [k for k in a["prices"] if k not in kinds]
            elif mode == "all":
                kinds += [o["kind"] for o in request["options"] if o["kind"] not in kinds]
            for j, kind in enumerate(kinds):
                while len(series) <= j:
                    series.append({})
                series[j][rid] = kind
        out = list(actions)
        for j, targets in enumerate(series):
            known = {}   # the desk's own price for the option the dealer took: a price that wins
            for rid, kind in targets.items():
                own = next(a["prices"] for a in quotes if a["requestId"] == rid)
                if preview.get(rid, ("?", None))[:2] == ("won", kind) and own.get(kind):
                    known[rid] = own[kind]
            for rid, st in probe_prices(g, quotes, targets, lo_x, hi_x, iters, known_win=known).items():
                request = desk.requests[rid]
                seen = preview.get(rid, ("?", None, None))
                own = next(a["prices"] for a in quotes if a["requestId"] == rid)
                line = {
                    "rid": rid, "at": desk.now, "day": desk.now // DAY, "dealer": request["dealerId"],
                    "trust": desk.dealer_trust.get(request["dealerId"], 0), "decided": desk.decided.get(rid),
                    "legs": len(request["legs"]), "pickup": request["legs"][0]["pickup"]["placeId"],
                    "delivery": request["legs"][-1]["delivery"]["placeId"], "ref": request["referenceFeeCents"],
                    "note": bool(request["note"]), "desk": seen[0], "desk_option": seen[1], "desk_cents": own.get(st["option"]),
                    **st, "x": round(st["lo"] / st["list"], 4) if st["lo"] else None,
                }
                sink(line)
                took = seen[0] == "won" and seen[1] == st["option"]
                if apply and took and st["lo"] and st["lo"] > own.get(st["option"], 0):
                    i = next(i for i in fresh if actions[i]["requestId"] == rid)
                    out[i] = {"type": "quote", "requestId": rid, "prices": {st["option"]: st["lo"]}}
                    g.expect[rid] = st["option"]
        return out
    return hook


def is_decline(g: Tas, action: dict) -> bool:
    """A decline is a quote far above the list price (the desk's `decline_mult`): it loses and costs no goodwill."""
    by_kind = {o["kind"]: o["listPriceCents"] for o in g.desk.requests[action["requestId"]]["options"]}
    return all(cents >= 0.99 * g.desk.p.decline_mult * by_kind[kind] for kind, cents in action["prices"].items())


def book_hook(book: dict, open_x: Optional[float] = None) -> Callable:
    """Quotes by the book: an option at a price, "decline", or "desk" (the desk's own quote). "*" is the default.
    An entry that names an option and no price is for the oracle: it goes out at `open_x` times the list price (low
    enough to win), and `limits --apply` then raises it to the dealer's limit. `run` has no oracle and refuses it."""
    default = book.get("*", "desk")

    def hook(g: Tas, actions: list, fresh: list) -> list:
        out = list(actions)
        for i in fresh:
            rid = actions[i]["requestId"]
            entry = book.get(rid, default)
            if entry == "desk":
                continue
            request = g.desk.requests[rid]
            if entry == "decline":
                first = request["options"][0]
                prices = {first["kind"]: int(first["listPriceCents"] * g.desk.p.decline_mult)}
            elif "prices" in entry:
                prices = {k: int(v) for k, v in entry["prices"].items()}
            elif entry.get("cents") is not None:
                prices = {entry["option"]: int(entry["cents"])}
            elif open_x is None:
                raise SystemExit(f"The book names no price for {rid}: `tas.py limits --book ... --apply` prices it at the dealer's limit")
            else:
                lst = next((o["listPriceCents"] for o in request["options"] if o["kind"] == entry["option"]), None)
                if lst is None:
                    raise SystemExit(f"The book wants {entry['option']} for {rid}, which the dealer does not accept")
                prices = {entry["option"]: int(lst * open_x)}
            unknown = set(prices) - {o["kind"] for o in request["options"]}
            if unknown:
                raise SystemExit(f"The book prices {sorted(unknown)} for {rid}, which the dealer does not accept")
            out[i] = {"type": "quote", "requestId": rid, "prices": prices}
        return out
    return hook


# --- commands -----------------------------------------------------------------------------------------------------
def params_of(a) -> dict:
    cls = load_policy(a.policy or champion()["policy"])
    return parse_overrides(cls, a.set or [])


def champion_line(seed: str) -> Optional[dict]:
    return next((r for r in champion_results() if r.get("seed") == seed and r.get("level") == 8), None)


def report(seed: str, name: str, result: dict, extra: Optional[dict] = None) -> None:
    row = {"name": name, **result, **(extra or {})}
    with open(home(seed) / "runs.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")
    champ = champion_line(seed)
    line = f"{name} on {seed}: €{result['margin']:,.2f}, {result['won']} won, {result['on_time']:.1%} on time" + \
           ("" if result["ranked"] else ", NOT RANKED") + f" (to {result['until']}; {result['forks']} forks, {result['requests']} requests)"
    if champ:
        line += f"\nThe champion's week on {seed}: €{champ['margin']:,.2f}, {champ['won']} won, {champ['on_time']:.1%} on time" \
                f" → Δ €{result['margin'] - champ['margin']:+,.2f}"
    print(line)


def cmd_tape(a) -> None:
    out = home(a.seed) / "tape.json"
    if out.exists() and not a.force:
        tape = json.loads(out.read_text(encoding="utf-8"))
        print(f"{out}: {len(tape['requests'])} requests (already there; --force plays it again)")
        return
    client = CountingClient()
    with Slot():
        world = coplay.create_world(client, 8, a.seed)
        entry = register(world.id, {"seed": a.seed, "level": 8, "tas": "tape"})
        try:
            snap = world.snapshot()
            roster, events, now = world.roster(), [], snap["now"]
            while now < snap["endsAt"]:      # nobody quotes, so the world only tells what every team is told
                step = world.advance(to=min(snap["endsAt"], now + DAY))
                now = step["now"]
                events += step["events"]
        finally:
            try:
                world.delete()
            except Exception:
                pass
            entry.unlink(missing_ok=True)
    requests = [e["request"] for e in events if e["kind"] == "price_request"]
    tape = {"seed": a.seed, "level": 8, "starts_at": snap["now"], "ends_at": snap["endsAt"], "requests": requests,
            "forecasts": [e for e in events if e["kind"] == "forecast"], "roster": roster,
            "other_events": dict(Counter(e["kind"] for e in events if e["kind"] not in ("price_request", "forecast")))}
    out.write_text(json.dumps(tape), encoding="utf-8")
    by_day = Counter(r["arrivedAt"] // DAY for r in requests)
    print(f"{out}: {len(requests)} requests ({', '.join(f'{WEEKDAYS[d]} {n}' for d, n in sorted(by_day.items()))}), "
          f"{len(roster)} drivers, {len(tape['forecasts'])} forecasts, {client.requests} server requests")


def cmd_limits(a) -> None:
    name = a.name or ((Path(a.book).stem + "-" if a.book else "") + a.mode + ("-apply" if a.apply else ""))
    path = home(a.seed) / f"limits-{name}.jsonl"
    lines: list[dict] = []
    with open(path, "w", encoding="utf-8") as f, Tas(a.seed, params_of(a), a.policy, name, forks=True) as g:
        def sink(line: dict) -> None:
            lines.append(line)
            f.write(json.dumps(line) + "\n")
            f.flush()

        oracle = price_oracle(a.mode, a.apply, a.lo, a.hi, a.iters, sink)
        if a.book:   # the book chooses what to quote, the oracle then measures (and with --apply, sets) the price
            by_book = book_hook(json.loads(Path(a.book).read_text(encoding="utf-8")), open_x=max(a.lo, 0.8))
            g.hook = lambda game, actions, fresh: oracle(game, by_book(game, actions, fresh), fresh)
        else:
            g.hook = oracle
        result = g.finish(minute_of(a.until) if a.until else None)
        (home(a.seed) / f"book-{name}.json").write_text(json.dumps({"*": "desk", **{rid: {"prices": p} for rid, p in g.quoted.items()}}), encoding="utf-8")
        broken = sorted(rid for rid, kind in g.expect.items() if rid in g.outcome and g.outcome[rid][:2] != ("won", kind))
        mismatch = sorted(l["rid"] for l in lines if l["rid"] in g.outcome and l["desk"] in ("won", "lost")
                          and l["desk"] != g.outcome[l["rid"]][0] and l["rid"] not in broken)
    summary = summarize_limits(lines)
    summary.update({"repriced": len(g.expect), "repriced_but_lost": broken, "preview_differs_from_main_line": mismatch})
    report(a.seed, f"limits-{name}", result, {"limits": summary, "params": a.set or []})
    print(limits_text(summary))
    if broken or mismatch:
        print(f"CHECK: {len(broken)} repriced quotes did not win as their fork said, and {len(mismatch)} previews differ from the "
              f"main line. One fork tests many requests at once on the claim that dealers decide each request by itself: "
              f"look at these requests before you trust the numbers.")
    print(f"Limits: {path}")


def summarize_limits(lines: list[dict]) -> dict:
    took = [l for l in lines if l["desk"] == "won" and l["desk_option"] == l["option"]]
    exact = [l for l in took if l["lo"] and l["desk_cents"]]
    left = sum(max(0, l["lo"] - l["desk_cents"]) for l in exact)
    best: dict[str, dict] = {}
    for l in lines:   # per request: the option with the highest price the dealer would pay
        if l["lo"] and (l["rid"] not in best or l["lo"] > best[l["rid"]]["lo"]):
            best[l["rid"]] = l
    lost = {l["rid"] for l in lines if l["desk"] != "won"}
    xs = [l["x"] for l in exact]
    return {
        "lines": len(lines), "won_measured": len(exact), "won_revenue": sum(l["desk_cents"] for l in exact) / 100,
        "won_at_limit": sum(l["lo"] for l in exact) / 100, "left_on_table": left / 100,
        "won_x_median": round(statistics.median(xs), 3) if xs else None,
        "won_desk_x_median": round(statistics.median(l["desk_cents"] / l["list"] for l in exact), 3) if exact else None,
        "not_won_measured": len(lost), "not_won_winnable": sum(1 for rid in lost if rid in best),
        "not_won_at_limit": sum(best[rid]["lo"] for rid in lost if rid in best) / 100,
        "bounds": dict(Counter(l["bound"] for l in lines)),
    }


def limits_text(s: dict) -> str:
    text = (f"Price oracle: {s['won_measured']} won orders measured. The desk took €{s['won_revenue']:,.0f} for them; at each "
            f"dealer's limit they pay €{s['won_at_limit']:,.0f}: €{s['left_on_table']:,.0f} left on the table "
            f"(median limit {s['won_x_median']} × list against the desk's {s['won_desk_x_median']} ×).")
    if s["not_won_measured"]:
        text += (f"\nNot won: {s['not_won_measured']} requests measured, {s['not_won_winnable']} winnable inside the bracket, "
                 f"worth €{s['not_won_at_limit']:,.0f} at their limits (before any driver is paid).")
    return text + f"\nBounds: {s['bounds']}"


def cmd_run(a) -> None:
    name = a.name or (Path(a.book).stem if a.book else "desk")
    with Tas(a.seed, params_of(a), a.policy, name) as g:
        if a.book:
            g.hook = book_hook(json.loads(Path(a.book).read_text(encoding="utf-8")))
        result = g.finish(minute_of(a.until) if a.until else None)
        won = sum(1 for o in g.outcome.values() if o[0] == "won")
        lost = sum(1 for o in g.outcome.values() if o[0] == "lost")
    report(a.seed, f"run-{name}", result, {"book": a.book, "params": a.set or [], "quotes_won": won, "quotes_lost": lost})


def cmd_whatif(a) -> None:
    text = a.variants
    variants = json.loads(Path(text[1:]).read_text(encoding="utf-8") if text.startswith("@") else text)
    name = a.name or "whatif"
    times = sorted(minute_of(t) for t in a.at.split(","))
    until = minute_of(a.until) if a.until else None
    picks = []
    with open(home(a.seed) / f"whatif-{name}.jsonl", "a", encoding="utf-8") as f, Tas(a.seed, params_of(a), a.policy, name, forks=True) as g:
        if a.book:
            g.hook = book_hook(json.loads(Path(a.book).read_text(encoding="utf-8")))
        for t in times:
            g.play_to(t)
            table = branch(g, variants, until)
            print(branch_text(g.desk.now, table), flush=True)
            ok = {n: r for n, r in table.items() if r["ranked"] and r["on_time"] >= a.min_on_time}
            best = max(ok, key=lambda n: ok[n]["margin"]) if ok else "control"
            f.write(json.dumps({"at": clock(g.desk.now), "variants": variants, "table": table, "picked": best if a.pick else None}) + "\n")
            f.flush()
            if a.pick:
                if best != "control":
                    g.apply(variants[best])   # the winner's moves, on the main line, from here on
                picks.append((clock(g.desk.now), best, table[best]["delta"]))
                print(f"  picked: {best}", flush=True)
        result = g.finish() if a.pick else None
    if result:
        report(a.seed, f"whatif-{name}", result, {"picks": picks, "params": a.set or [], "book": a.book})
        print("Picks: " + "; ".join(f"{at} {n} ({d:+,.0f})" for at, n, d in picks))


def cmd_show(a) -> None:
    h = home(a.seed)
    tape = h / "tape.json"
    if tape.exists():
        t = json.loads(tape.read_text(encoding="utf-8"))
        print(f"tape: {len(t['requests'])} requests, {len(t['roster'])} drivers")
    champ = champion_line(a.seed)
    if champ:
        print(f"champion: €{champ['margin']:,.2f}, {champ['won']} won, {champ['on_time']:.1%} on time")
    runs = h / "runs.jsonl"
    if runs.exists():
        for line in runs.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            print(f"{r['name']:<28} €{r['margin']:>10,.2f}  won {r['won']:>4}  on time {r['on_time']:6.1%}  to {r['until']}  forks {r['forks']}"
                  + ("" if r["ranked"] else "  NOT RANKED"))
            if r.get("limits"):
                print("    " + limits_text(r["limits"]).replace("\n", "\n    "))
    for p in sorted(h.glob("*")):
        print(f"  {p}")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    load_dotenv()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="c", required=True)

    def common(p, world: bool = True):
        p.add_argument("--seed", required=True)
        if world:
            p.add_argument("-s", "--set", action="append", metavar="key=value", help="a Params override on top of the champion's")
            p.add_argument("--policy", help="module:Class of a Desk subclass (default: the champion's)")
            p.add_argument("--name", help="the label of the output files")
            p.add_argument("--until", help="stop at this time, e.g. 'Tue 07:00'")

    p = sub.add_parser("tape"); common(p, world=False); p.add_argument("--force", action="store_true")
    p = sub.add_parser("limits"); common(p)
    p.add_argument("--mode", choices=["won", "quoted", "all"], default="won")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--iters", type=int, default=9)
    p.add_argument("--lo", type=float, default=0.7)
    p.add_argument("--hi", type=float, default=2.6)
    p.add_argument("--book", help="a price book that chooses what to quote; the oracle prices it")
    p = sub.add_parser("run"); common(p); p.add_argument("--book")
    p = sub.add_parser("whatif"); common(p); p.add_argument("--book")
    p.add_argument("--at", required=True, help="when to branch, e.g. 'Tue 07:00' or 'Mon 08:00,Tue 07:00,Wed 07:00'")
    p.add_argument("--variants", required=True, help="JSON {name: {\"set\": {...}, \"quote\": {...}, \"raise\": [...]}}, or @file")
    p.add_argument("--pick", action="store_true", help="apply the best variant at each time and play the week to its end")
    p.add_argument("--min-on-time", type=float, default=0.92, help="a variant below this on-time share is not picked")
    p = sub.add_parser("show"); common(p, world=False)
    a = ap.parse_args()
    {"tape": cmd_tape, "limits": cmd_limits, "run": cmd_run, "whatif": cmd_whatif, "show": cmd_show}[a.c](a)


if __name__ == "__main__":
    main()
