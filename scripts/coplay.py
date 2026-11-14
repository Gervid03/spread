"""Co-play: an agent steers the champion desk through one practice week, turn by turn, and tests ideas with
exact what-ifs. Stateless: a game is a seed plus the log of its moves. Worlds are deterministic, so every turn
replays the log in a fresh world, applies the move, plays on to the next pause and deletes the world. A game
holds a practice world only for the seconds of a replay, so many agents can play at once under the team's cap.

    uv run python scripts/coplay.py new <game> --seed dev-05      # start a game (the champion's policy and params)
    uv run python scripts/coplay.py turn <game> '<json>'           # one turn; prints the state
    uv run python scripts/coplay.py show <game>                    # the last state again, no world
    uv run python scripts/coplay.py board                          # every game on this machine, best first

A turn is a JSON object; its keys combine:
    "advance": minutes (default 30)  or  "until": "Tue 07:00"      how far to play before your next turn
    "set": {"param": value}          change the desk's Params from now on (kept in the game's log)
    "quote": {"<request id prefix>": 1.15 | "decline"}            override a quote waiting to be sent now:
                                     multiple of the list price of the option the desk quoted
    "raise": ["<order id prefix>"]   the desk's deadline-warning response for that order now
    "whatif": {"name": {"set": {...}, "quote": {...}, "raise": [...]}, ...}
                                     each variant applies its moves now and plays the rest of the week; so does
                                     the main line unchanged. Exact (separate replays, same draws). No move made.
    "probe": {"<request id prefix>": [lo, hi]}                    binary-search, on forks, the highest multiple
                                     of list price that still wins each waiting quote (the dealer's real limit)
    "note": "text"                   logged with the turn (say what you are testing and why)
    "tour": [["<order prefix>", ...], 0.55]  (or a list of them)   post those won cars, in that order, as one flat
                                     multi-car gig at 0.55x their summed typical fee (needs a tour desk, see `new`)
    "tourprobe": [["<order prefix>", ...], lo, hi, minutes]       the lowest flat multiple of the summed typical
                                     fee at which a driver books that tour within the minutes, bisected on forks;
                                     logged to ~/.spread-lab/coplay/tour-fees.jsonl. No move made.

    new <game> --seed dev-05 --policy spread_lab.policies.sunday_tours:Desk -s sunday_tours=true -s tour_dynamic=true
                                     a game on another policy, with Params overrides on top of the champion's
The state shows a "Cycles" section: closed tours of 2-4 won cars without a driver (scripts/coplay_cycles.py).

Policy code comes from the checkout you run in, so a mechanism you add (as a Params flag with a neutral default)
can be switched on with "set". Games live in ~/.spread-lab/coplay/<game>/ (log.json, state.md, history.jsonl).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from spread.client import SpreadError

from spread_lab.env import lab_home, load_dotenv
from spread_lab.geo import Geo, load_map
from spread_lab.lab import CountingClient, Slot, champion, champion_results, create_world, load_policy, register
from spread_lab.runner import DAY, HOUR, URGENT, busy, clock

from coplay_cycles import apply_tour, cycles_text, tour_probe

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
_geo_lock = threading.Lock()
_geo: dict = {}


def home(game: str) -> Path:
    return lab_home() / "coplay" / game


def geo_and_names(client):
    with _geo_lock:
        if not _geo:
            m = load_map(client)
            _geo["geo"] = Geo(m)
            _geo["names"] = {p["id"]: p.get("name", p["id"])[:10] for p in m["places"]}
    return _geo["geo"], _geo["names"]


def order_class(desk, rid):
    r = desk.requests[rid]
    pick, dest = r["legs"][0]["pickup"]["placeId"], r["legs"][-1]["delivery"]["placeId"]
    cls = lambda n: "hub" if n >= 200 else ("mid" if n >= 30 else "thin")
    drive = sum(desk.geo.minutes(l["pickup"]["placeId"], l["delivery"]["placeId"]) for l in r["legs"])
    return f"{cls(desk.supply.get(pick, 0))}->{cls(desk.supply.get(dest, 0))} {'short' if drive < 60 else 'mid' if drive <= 180 else 'long'}"


class Game:
    """A world and the desk, replayed from the log; `record` collects what the state shows."""

    def __init__(self, log: dict):
        self.log = log
        self.client = CountingClient()
        self.geo, self.names = geo_and_names(self.client)
        self.cls = load_policy(log["policy"])
        self.world = None
        self.slot = None
        self.ledger = Counter()
        self.pnl = defaultdict(Counter)
        self.record = False
        self.seen, self.turn_reqs, self.booked, self.sent = Counter(), [], [], {}
        self.msgs: list[str] = []

    def __enter__(self):
        self.slot = Slot().__enter__()
        self.world = create_world(self.client, 8, self.log["seed"])
        self.entry = register(self.world.id, {"seed": self.log["seed"], "level": 8, "coplay": self.log["game"]})
        snap = self.world.snapshot()
        self.ends_at = snap["endsAt"]
        self.desk = self.cls(self.world, self.cls.Params.from_dict(self.log["params"]), 8, self.geo, self.world.roster(), snap["now"])
        return self

    def __exit__(self, *exc):
        try:
            self.world.delete()
        except Exception:
            pass
        self.entry.unlink(missing_ok=True)
        self.slot.__exit__(*exc)

    # one iteration of play_practice's loop
    def step(self):
        desk = self.desk
        actions = desk.take_outbox()
        for a in actions:
            if a["type"] == "quote":
                self.sent[a["requestId"]] = a["prices"]
        step_min = min(14, max(1, int(desk.p.step_min)))
        if busy(desk.now):
            result = self.world.advance(to=min(self.ends_at, desk.now + step_min), actions=actions)
        else:
            result = self.world.advance(until=URGENT, max=min(self.ends_at, desk.now + HOUR), actions=actions)
        desk.read_results(actions, result["results"])
        desk.now = result["now"]
        for event in result["events"]:
            kind = event["kind"]
            if kind == "ledger":
                line = event["line"]
                self.ledger[line["kind"]] += line["cents"]
                oid = line.get("orderId")
                if oid and oid in desk.requests:
                    self.pnl[order_class(desk, oid)][line["kind"]] += line["cents"]
            desk.handle(event)
            if self.record:
                self.seen[kind] += 1
                if kind == "ledger":
                    self.seen["€" + event["line"]["kind"]] += event["line"]["cents"]
                if kind == "price_request":
                    self.turn_reqs.append(event["request"]["id"])
                if kind == "gig_booked":
                    post = desk.posts.get(event["gigId"])
                    if post:
                        oids = list(dict.fromkeys(s["orderId"] for s in post["stops"]))
                        ref = sum(desk.requests[o]["referenceFeeCents"] for o in oids if o in desk.requests)
                        self.booked.append((oids[0], event["feeCents"], ref, oids[0] in desk.urgent))
        desk.tick()

    def play_to(self, minute):
        while self.desk.now < min(minute, self.ends_at):
            self.step()

    def apply(self, moves: dict):
        desk = self.desk
        for k, v in moves.get("set", {}).items():
            if not hasattr(desk.p, k):
                raise SystemExit(f"No Params field {k!r}")
            setattr(desk.p, k, v)
        for prefix, how in moves.get("quote", {}).items():
            hit = False
            for a in desk.outbox:
                if a["type"] == "quote" and a["requestId"].startswith(prefix):
                    r = desk.requests[a["requestId"]]
                    if how == "decline":
                        first = r["options"][0]
                        a["prices"] = {first["kind"]: int(first["listPriceCents"] * desk.p.decline_mult)}
                    else:
                        kind = next(iter(a["prices"]))
                        lst = next(o["listPriceCents"] for o in r["options"] if o["kind"] == kind)
                        a["prices"] = {kind: int(lst * float(how))}
                    desk.decided[a["requestId"]] = "manual"
                    hit = True
            if not hit:
                print(f"(quote {prefix}: no waiting quote matches; ignored)")
        for prefix in moves.get("raise", []):
            for oid in list(desk.orders):
                if oid.startswith(prefix):
                    desk.raise_fees(oid)
        tours = moves.get("tour") or []
        if tours and isinstance(tours[0], list) and tours[0] and isinstance(tours[0][0], str):
            tours = [tours]
        for prefixes, mult in tours:
            self.msgs.append(apply_tour(desk, prefixes, float(mult)))

    def replay(self, upto=None):
        """Plays the log's pauses and moves, up to the game's current minute (or `upto`)."""
        for pause in self.log["pauses"]:
            self.play_to(pause["at"])
            self.apply(pause)
        self.play_to(self.log["now"] if upto is None else upto)

    def result(self):
        s = self.world.score()
        return {"margin": round(s["marginCents"] / 100, 2), "won": s["wonOrders"], "on_time": round(s["onTimeShare"], 4),
                "ranked": s["ranked"]}


def play_variant(log, moves):
    with Game(log) as g:
        g.replay()
        if moves:
            g.apply(moves)
        g.play_to(g.ends_at)
        return g.result()


def probe(g: Game, rid: str, lo: float, hi: float, iters: int = 6):
    """Highest multiple of the quoted option's list price that still wins `rid`, searched on forks."""
    desk = g.desk
    base = [dict(a) for a in desk.outbox]
    idx = next(i for i, a in enumerate(base) if a["type"] == "quote" and a["requestId"] == rid)
    r = desk.requests[rid]
    kind = next(iter(base[idx]["prices"]))
    if desk.decided.get(rid) == "decline":
        kind = r["options"][0]["kind"]
    lst = next(o["listPriceCents"] for o in r["options"] if o["kind"] == kind)

    def wins(m):
        with Slot():
            fw = None
            for _ in range(120):
                try:
                    fw = g.world.fork()
                    break
                except SpreadError as error:
                    if error.status != 409:
                        raise
                    time.sleep(5)
            try:
                acts = [dict(a) for a in base]
                acts[idx] = {"type": "quote", "requestId": rid, "prices": {kind: int(lst * m)}}
                res = fw.advance(to=min(g.ends_at, max(r["respondBy"], desk.now) + 2), actions=acts)
                for e in res["events"]:
                    if e["kind"] == "order_won" and e["order"]["id"] == rid:
                        return True
                    if e["kind"] == "order_lost" and e["requestId"] == rid:
                        return False
                return None
            finally:
                try:
                    fw.delete()
                except Exception:
                    pass

    if wins(hi):
        return {"kind": kind, "limit": f">= {hi}"}
    if not wins(lo):
        return {"kind": kind, "limit": f"< {lo}"}
    for _ in range(iters):
        mid = (lo + hi) / 2
        w = wins(mid)
        if w is None:
            return {"kind": kind, "limit": "no outcome in time"}
        lo, hi = (mid, hi) if w else (lo, mid)
    return {"kind": kind, "limit": round(lo, 3), "list_eur": lst / 100}


def eur(c):
    return f"€{c / 100:,.0f}"


def state_text(g: Game, turn: int, extra: list[str]):
    desk, names, geo = g.desk, g.names, g.geo
    s = g.world.score()
    champ = g.log.get("champion")
    lines = [f"# {g.log['game']} · {g.log['seed']} · turn {turn} · {clock(desk.now)} · margin {eur(s['marginCents'])} · "
             f"won {s['wonOrders']} · on time {s['onTimeShare']:.1%} · late {len(desk.late)} · mult {desk.mult:.3f}"
             + (f" · champion's week here: €{champ['margin']:,.0f}, {champ['won']} won, {champ['on_time']:.1%}" if champ else "")]
    ev = ", ".join(f"{k} {v}" for k, v in sorted(g.seen.items()) if not k.startswith("€") and k not in ("ledger", "gig_viewed"))
    money = ", ".join(f"{k[1:]} {eur(v)}" for k, v in sorted(g.seen.items()) if k.startswith("€"))
    lines.append(f"Since last turn: {ev or 'nothing'}. Money: {money or 'none'}.")
    done = [rid for rid in g.turn_reqs if rid in g.sent]
    if done:
        lines.append(f"\n## This turn's requests ({len(done)}, won {sum(r in desk.orders for r in done)}): id · route[supply] · drive · options list € → decision quote → outcome")
    for rid in done[-16:]:
        r = desk.requests[rid]
        pick, dest = r["legs"][0]["pickup"]["placeId"], r["legs"][-1]["delivery"]["placeId"]
        drive = sum(geo.minutes(l["pickup"]["placeId"], l["delivery"]["placeId"]) for l in r["legs"])
        opts = " ".join(f"{o['kind'][:2]}:{o['listPriceCents'] / 100:.0f}" for o in r["options"])
        q = " ".join(f"{k[:2]}×{v / next(o['listPriceCents'] for o in r['options'] if o['kind'] == k):.2f}" for k, v in g.sent[rid].items())
        out = "WON" if rid in desk.orders else ("lost" if rid in desk.lost_requests else "open")
        lines.append(f"- {rid[:6]} {names.get(pick, pick)}[{desk.supply.get(pick, 0)}]→{names.get(dest, dest)}[{desk.supply.get(dest, 0)}] "
                     f"{len(r['legs'])}car {drive}m · {opts} · ref fee {r['referenceFeeCents'] / 100:.0f} · {desk.decided.get(rid, '?')} {q} → {out}")
    quotes = [a for a in desk.outbox if a["type"] == "quote"]
    if quotes:
        lines.append(f"\n## Quotes waiting ({len(quotes)}): id · dealer(trust) · route[supply] · drive · options (list €/deadline h) · ref fee → the desk's quote")
    for a in quotes[:14]:
        r = desk.requests.get(a["requestId"])
        pick, dest = r["legs"][0]["pickup"]["placeId"], r["legs"][-1]["delivery"]["placeId"]
        drive = sum(geo.minutes(l["pickup"]["placeId"], l["delivery"]["placeId"]) for l in r["legs"])
        opts = " ".join(f"{o['kind'][:2]}:{o['listPriceCents'] / 100:.0f}/{(o['deadline'] - desk.now) / 60:.0f}h" for o in r["options"])
        q = " ".join(f"{k[:2]}:{v / 100:.0f}(×{v / next(o['listPriceCents'] for o in r['options'] if o['kind'] == k):.2f})" for k, v in a["prices"].items())
        lines.append(f"- {r['id'][:6]} {r['dealerId'][:5]}({desk.dealer_trust.get(r['dealerId'], 0)}) {names.get(pick, pick)}[{desk.supply.get(pick, 0)}]"
                     f"→{names.get(dest, dest)}[{desk.supply.get(dest, 0)}] {len(r['legs'])}car {drive}m · {opts} · ref {r['referenceFeeCents'] / 100:.0f} → "
                     f"{desk.decided.get(r['id'], '?')} {q}")
    open_orders = sorted((o for o in desk.orders.values() if o["status"] == "waiting" and not desk.staffed(o)), key=lambda o: o["lastPickupAt"])
    if open_orders:
        lines.append(f"\n## Unstaffed won orders ({len(open_orders)}), soonest first: id · route · option · price · last pickup in h · flags")
    for o in open_orders[:10]:
        pick, dest = o["legs"][0]["pickup"]["placeId"], o["legs"][-1]["delivery"]["placeId"]
        flags = " ".join(f for f, on in (("URGENT", o["id"] in desk.urgent), ("LOST", o["id"] in desk.lost)) if on)
        lines.append(f"- {o['id'][:6]} {names.get(pick, pick)}[{desk.supply.get(pick, 0)}]→{names.get(dest, dest)} {o['option'][:2]} "
                     f"{o['priceCents'] / 100:.0f} · {(o['lastPickupAt'] - desk.now) / 60:.1f}h {flags}")
    if g.booked:
        lines.append(f"\n## Booked this turn ({len(g.booked)}): order · class · fee/ref fee · U = after the deadline warning")
        lines.append("  " + " | ".join(f"{o[:6]} {order_class(desk, o)} {fee / max(ref, 1):.2f}{' U' if u else ''}" for o, fee, ref, u in g.booked[:14]))
    if g.pnl:
        lines.append("\n## P&L so far by class: class · revenue · driver fees · other · margin")
        for k, v in sorted(g.pnl.items(), key=lambda kv: -sum(kv[1].values()))[:12]:
            rev, fee = v.get("revenue", 0), v.get("driver_fee", 0)
            lines.append(f"- {k:<16} {eur(rev):>8} {eur(fee):>8} {eur(sum(v.values()) - rev - fee):>7} {eur(sum(v.values())):>8}")
    lines += cycles_text(desk, names)
    changed = {k: v for p in g.log["pauses"] for k, v in p.get("set", {}).items()}
    lines.append(f"\nParams you changed: {changed or 'none'}")
    return "\n".join(lines + extra) + "\n"


def save_log(game, log):
    path = home(game) / "log.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(log, indent=1), encoding="utf-8")
    tmp.replace(path)


def cmd_new(a):
    h = home(a.game)
    if (h / "log.json").exists():
        raise SystemExit(f"Game {a.game} exists ({h}); pick another name.")
    h.mkdir(parents=True)
    champ = champion()
    row = next((r for r in champion_results() if r.get("seed") == a.seed and r.get("level") == 8), None)
    params = dict(champ["params"])
    for kv in a.s or []:
        k, v = kv.split("=", 1)
        params[k] = json.loads(v.lower()) if v.lower() in ("true", "false") else (json.loads(v) if re.fullmatch(r"-?[0-9.]+", v) else v)
    log = {"game": a.game, "seed": a.seed, "policy": a.policy or champ["policy"], "params": params, "pauses": [], "now": 7 * 60,
           "turn": 0, "champion": {k: row[k] for k in ("margin", "won", "on_time")} if row else None, "best": None, "projected": None}
    save_log(a.game, log)
    print(f"New game {a.game} on {a.seed}; it starts on Monday 07:00 at your first turn. "
          + (f"The champion's week on this world: €{row['margin']:,.2f}, {row['won']} won, {row['on_time']:.1%} on time." if row else ""))


def cmd_turn(a):
    h = home(a.game)
    log = json.loads((h / "log.json").read_text(encoding="utf-8"))
    cmd = json.loads(a.cmd)
    moves = {k: cmd[k] for k in ("set", "quote", "raise", "tour") if k in cmd}
    extra = []
    whatif = None
    if cmd.get("whatif"):
        key = hashlib.sha1(json.dumps(log["pauses"], sort_keys=True).encode()).hexdigest()  # the main line depends only on its moves
        variants = {"main line, unchanged": None, **cmd["whatif"]}
        with ThreadPoolExecutor(max_workers=min(4, len(variants))) as pool:
            futs = {name: (None if name == "main line, unchanged" and log.get("cache", {}).get("key") == key
                           else pool.submit(play_variant, log, mv)) for name, mv in variants.items()}
            whatif = {name: (log["cache"]["result"] if f is None else f.result()) for name, f in futs.items()}
        log["cache"] = {"key": key, "result": whatif["main line, unchanged"]}
        base = whatif["main line, unchanged"]
        log["projected"] = base
        best = max(whatif.items(), key=lambda kv: kv[1]["margin"] if kv[1]["ranked"] else -1e9)
        extra.append("\n## What-if (each plays the rest of the week from now; exact, same draws):")
        for name, r in whatif.items():
            extra.append(f"- {name}: €{r['margin']:,.0f} ({r['margin'] - base['margin']:+,.0f}) · won {r['won']} · on time {r['on_time']:.1%}"
                         + ("" if r["ranked"] else " · NOT RANKED"))
        if not log.get("best") or best[1]["margin"] > log["best"]["margin"]:
            log["best"] = {**best[1], "variant": best[0], "at": clock(log["now"]), "moves": cmd["whatif"].get(best[0])}
    with Game(log) as g:
        g.replay()
        g.msgs = []
        if moves:
            g.apply(moves)
            log["pauses"].append({"at": g.desk.now, **moves})
            extra += ["\n## Moves"] + [f"- {m}" for m in g.msgs]
        if cmd.get("tourprobe"):
            tp = cmd["tourprobe"]
            tps = [tp] if isinstance(tp[0], list) and tp[0] and isinstance(tp[0][0], str) else tp
            extra.append("\n## Tour probes (the lowest flat multiple of the summed typical fee that a driver books within the minutes):")
            for prefixes, lo, hi, within in tps:
                r = tour_probe(g, prefixes, float(lo), float(hi), int(within))
                extra.append(f"- {r.get('cars', '?')} cars {'→'.join(r.get('towns', []))} (Σ ref €{r.get('ref_eur', 0):.0f}, "
                             f"road {(r.get('road_min') or 0) / 60:.1f} h, start drivers {r.get('start_supply')}): "
                             f"min {r.get('min_mult')} = €{r.get('fee_eur', '-')} ({r.get('eur_per_road_h', '-')} €/road h)"
                             + (f" ERROR {r['error']}" if r.get("error") else ""))
        if cmd.get("probe"):
            extra.append("\n## Probes (the highest multiple of list that still wins; searched on forks):")
            for prefix, (lo, hi) in cmd["probe"].items():
                rid = next((x["requestId"] for x in g.desk.outbox if x["type"] == "quote" and x["requestId"].startswith(prefix)), None)
                if not rid:
                    extra.append(f"- {prefix}: no waiting quote")
                    continue
                extra.append(f"- {rid[:6]}: {probe(g, rid, float(lo), float(hi))}")
        if "until" in cmd:
            m = re.match(r"(\w{3})\s+(\d{1,2}):(\d{2})", cmd["until"])
            target = WEEKDAYS.index(m.group(1).title()) * DAY + int(m.group(2)) * 60 + int(m.group(3))
            while target <= g.desk.now:
                target += 7 * DAY
        elif "advance" in cmd:
            target = g.desk.now + int(cmd["advance"])
        else:
            target = g.desk.now if (whatif or cmd.get("probe") or cmd.get("tourprobe")) and not moves else g.desk.now + 30
        g.record = True
        g.play_to(target)
        log["now"] = g.desk.now
        log["turn"] += 1
        text = state_text(g, log["turn"], extra)
        s = g.world.score()
        log["current"] = {"clock": clock(g.desk.now), "margin": s["marginCents"] / 100, "won": s["wonOrders"], "on_time": s["onTimeShare"]}
        if g.desk.now >= g.ends_at:
            log["projected"] = {"margin": s["marginCents"] / 100, "won": s["wonOrders"], "on_time": s["onTimeShare"], "ranked": s["ranked"]}
            text += f"\nTHE WEEK IS OVER: €{s['marginCents'] / 100:,.2f}, {s['wonOrders']} won, {s['onTimeShare']:.1%} on time.\n"
    save_log(a.game, log)
    (h / "state.md").write_text(text, encoding="utf-8")
    with open(h / "history.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"turn": log["turn"], "clock": log["current"]["clock"], "cmd": cmd, "current": log["current"],
                            "whatif": whatif}) + "\n")
    sys.stdout.write(text)


def cmd_show(a):
    sys.stdout.write((home(a.game) / "state.md").read_text(encoding="utf-8"))


def cmd_board(a):
    rows = []
    for p in sorted((lab_home() / "coplay").glob("*/log.json")):
        log = json.loads(p.read_text(encoding="utf-8"))
        c, pr, b = log.get("champion") or {}, log.get("projected") or {}, log.get("best") or {}
        cm = c.get("margin")
        rows.append((b.get("margin", 0) - (cm or 0), log, c, pr, b))
    print("game · seed · now · champion's week · main line projected (Δ) · best what-if (Δ, variant, at)")
    for d, log, c, pr, b in sorted(rows, key=lambda r: -r[0]):
        cm = c.get("margin")
        f = lambda r: f"€{r['margin']:,.0f} ({r['margin'] - cm:+,.0f})" if r and cm else "-"
        print(f"{log['game']:<18} {log['seed']:<8} {log.get('current', {}).get('clock', 'Mon 07:00'):<10} "
              f"€{cm or 0:,.0f}  {f(pr):<18} {f(b):<18} {b.get('variant', '')[:30]} {b.get('at', '')}")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    load_dotenv()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="c", required=True)
    s = sub.add_parser("new"); s.add_argument("game"); s.add_argument("--seed", required=True)
    s.add_argument("--policy", help="module:Class, default the champion's"); s.add_argument("-s", action="append", help="key=value on top of the champion's params")
    s = sub.add_parser("turn"); s.add_argument("game"); s.add_argument("cmd", nargs="?", default='{"advance": 30}')
    s = sub.add_parser("show"); s.add_argument("game")
    sub.add_parser("board")
    a = ap.parse_args()
    {"new": cmd_new, "turn": cmd_turn, "show": cmd_show, "board": cmd_board}[a.c](a)


if __name__ == "__main__":
    main()
