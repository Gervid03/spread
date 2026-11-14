"""Co-play: the champion desk plays one practice world, and a person (or Claude) steers it between turns.

    uv run python scripts/coplay.py serve --seed dev-12      # in the background: holds the world and the desk
    uv run python scripts/coplay.py do '{"advance": 30}'     # one turn: apply a command, step, print the state

The desk steps exactly as `play_practice` does (so a game with no interventions reproduces the champion's
result on that seed); the server only pauses between steps. A command is a JSON object; its keys combine:

    "advance": minutes (default 30)    or  "until": "Tue 07:00"   how far to play before the next turn
    "set": {"param": value, ...}       change the desk's Params from now on (fields cached at start, such as
                                       radii, don't follow)
    "quote": {"<request id prefix>": 1.15 | "decline" | "keep"}
                                       override a quote waiting to be sent this turn: the multiple of the list
                                       price of the option the desk quoted (of the first option, for a decline).
                                       The tracker doesn't learn from overridden quotes.
    "raise": ["<order id prefix>", ...]  the desk's deadline-warning response now (steep fees and offers)
    "whatif": {"name": {"param": value}, ...}
                                       fork the world now and play the unchanged desk and each variant to the
                                       week's end on the same future draws; reports each margin and on-time share
    "note": "text"                     logged with the turn, for the write-up
    "stop": true                       end the game (the world is deleted after its score is logged)

Files: runs/coplay/{state.md, log.jsonl, cmd.json}. Forks wait and retry while the team's 8 worlds are taken.
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

from spread.client import SpreadError

from spread_lab.env import REPO, load_dotenv
from spread_lab.geo import Geo, load_map
from spread_lab.lab import CountingClient, Slot, champion, create_world, load_policy, register
from spread_lab.runner import DAY, HOUR, URGENT, busy, clock

HOME = REPO / "runs" / "coplay"
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def step(world, desk, ends_at, ledger, seen):
    """One iteration of play_practice's loop."""
    actions = desk.take_outbox()
    sent = getattr(desk, "_sent", None)
    if sent is not None:
        for a in actions:
            if a["type"] == "quote":
                sent[a["requestId"]] = a["prices"]
    step_min = min(14, max(1, int(desk.p.step_min)))
    if busy(desk.now):
        result = world.advance(to=min(ends_at, desk.now + step_min), actions=actions)
    else:
        result = world.advance(until=URGENT, max=min(ends_at, desk.now + HOUR), actions=actions)
    desk.read_results(actions, result["results"])
    desk.now = result["now"]
    for event in result["events"]:
        seen[event["kind"]] += 1
        if event["kind"] == "ledger":
            ledger[event["line"]["kind"]] += event["line"]["cents"]
            seen["€" + event["line"]["kind"]] += event["line"]["cents"]
        desk.handle(event)
        if event["kind"] == "ledger" and hasattr(desk, "_pnl"):
            oid = event["line"].get("orderId")
            if oid and oid in desk.requests:
                desk._pnl[order_class(desk, oid)][event["line"]["kind"]] += event["line"]["cents"]
        if event["kind"] == "gig_booked" and hasattr(desk, "_turn_booked"):
            post = desk.posts.get(event["gigId"])
            if post:
                oids = list(dict.fromkeys(s_["orderId"] for s_ in post["stops"]))
                ref = sum(desk.requests[o]["referenceFeeCents"] for o in oids if o in desk.requests)
                desk._turn_booked.append((oids[0], event["feeCents"], ref, event["at"] - post.get("_posted_at", event["at"]),
                                          oids[0] in desk.urgent))
        if event["kind"] == "price_request" and hasattr(desk, "_turn_reqs"):
            desk._turn_reqs.append(event["request"]["id"])
    desk.tick()


def order_class(desk, rid):
    r = desk.requests[rid]
    pick, dest = r["legs"][0]["pickup"]["placeId"], r["legs"][-1]["delivery"]["placeId"]
    a = "hub" if desk.supply.get(pick, 0) >= 200 else ("mid" if desk.supply.get(pick, 0) >= 30 else "thin")
    b = "hub" if desk.supply.get(dest, 0) >= 200 else ("mid" if desk.supply.get(dest, 0) >= 30 else "thin")
    drive = sum(desk.geo.minutes(l["pickup"]["placeId"], l["delivery"]["placeId"]) for l in r["legs"]) if desk.geo else 0
    d = "short" if drive < 60 else ("mid" if drive <= 180 else "long")
    return f"{a}->{b} {d}"


def clone(desk, world):
    w, g = desk.world, desk.geo
    desk.world = desk.geo = None
    try:
        c = copy.deepcopy(desk)
    finally:
        desk.world, desk.geo = w, g
    c.world, c.geo = world, g
    return c


def fork(world):
    waited = 0
    while True:
        try:
            return world.fork()
        except SpreadError as error:
            if error.status != 409 or waited > 600:
                raise
            time.sleep(5)
            waited += 5


def play_out(world, desk, ends_at, changes):
    """Forks the world, plays a copy of the desk with `changes` to the end, returns its score."""
    fw = fork(world)
    try:
        d = clone(desk, fw)
        for k, v in changes.items():
            setattr(d.p, k, v)
        ledger, seen = Counter(), Counter()
        while d.now < ends_at:
            step(fw, d, ends_at, ledger, seen)
        s = fw.score()
        return {"margin": s["marginCents"] / 100, "on_time": s["onTimeShare"], "won": s["wonOrders"]}
    finally:
        try:
            fw.delete()
        except Exception:
            pass


def parse_until(text, now):
    m = re.match(r"(\w{3})\s+(\d{1,2}):(\d{2})", text)
    day = WEEKDAYS.index(m.group(1).title())
    target = day * DAY + int(m.group(2)) * 60 + int(m.group(3))
    while target <= now:
        target += 7 * DAY
    return target


def eur(cents):
    return f"€{cents / 100:,.0f}"


def state_text(turn, world, desk, geo, seen, score, whatif, names):
    p = desk.p
    lines = [f"# Turn {turn} · {clock(desk.now)} · margin {eur(score['marginCents'])} · won {score['wonOrders']} · "
             f"on time {score['onTimeShare']:.1%} · late {len(desk.late)} · lost {len(desk.lost)} · mult {desk.mult:.3f} · "
             f"loss streak {desk.loss_streak}"]
    ev = ", ".join(f"{k} {v}" for k, v in sorted(seen.items()) if not k.startswith("€") and k not in ("ledger", "gig_viewed"))
    money = ", ".join(f"{k[1:]} {eur(v)}" for k, v in sorted(seen.items()) if k.startswith("€"))
    lines.append(f"Since last turn: {ev or 'nothing'}. Money: {money or 'none'}.")
    done = [rid for rid in getattr(desk, "_turn_reqs", []) if rid in desk._sent]
    if done:
        wins = sum(rid in desk.orders for rid in done)
        lines.append(f"\n## This turn's requests ({len(done)}, won {wins}): id · route · drive · options → decision quote → outcome")
    for rid in done[-16:]:
        r = desk.requests[rid]
        pick, dest = r["legs"][0]["pickup"]["placeId"], r["legs"][-1]["delivery"]["placeId"]
        drive = sum(geo.minutes(l["pickup"]["placeId"], l["delivery"]["placeId"]) for l in r["legs"])
        opts = " ".join(f"{o['kind'][:2]}:{o['listPriceCents'] / 100:.0f}" for o in r["options"])
        q = " ".join(f"{k[:2]}×{v / next(o['listPriceCents'] for o in r['options'] if o['kind'] == k):.2f}" for k, v in desk._sent[rid].items())
        out = "WON" if rid in desk.orders else ("lost" if rid in desk.lost_requests else "open")
        lines.append(f"- {rid[:6]} {names.get(pick, pick)}[{desk.supply.get(pick, 0)}]→{names.get(dest, dest)}[{desk.supply.get(dest, 0)}] "
                     f"{len(r['legs'])}car {drive}m · {opts} · {desk.decided.get(rid, '?')} {q} → {out}")
    quotes = [a for a in desk.outbox if a["type"] == "quote"]
    if quotes:
        lines.append(f"\n## Quotes waiting ({len(quotes)}): id · dealer(trust) · route · drive · options (list €, deadline h) → quote")
    for a in quotes[:14]:
        r = desk.requests.get(a["requestId"])
        if not r:
            continue
        pick, dest = r["legs"][0]["pickup"]["placeId"], r["legs"][-1]["delivery"]["placeId"]
        drive = sum(geo.minutes(l["pickup"]["placeId"], l["delivery"]["placeId"]) for l in r["legs"])
        opts = " ".join(f"{o['kind'][:2]}:{o['listPriceCents'] / 100:.0f}/{(o['deadline'] - desk.now) / 60:.0f}h" for o in r["options"])
        q = " ".join(f"{k[:2]}:{v / 100:.0f}(×{v / next(o['listPriceCents'] for o in r['options'] if o['kind'] == k):.2f})" for k, v in a["prices"].items())
        lines.append(f"- {r['id'][:6]} {r['dealerId'][:5]}({desk.dealer_trust.get(r['dealerId'], 0)}) "
                     f"{names.get(pick, pick)}[{desk.supply.get(pick, 0)}]→{names.get(dest, dest)}[{desk.supply.get(dest, 0)}] "
                     f"{len(r['legs'])}car {drive}m · {opts} · ref fee {r['referenceFeeCents'] / 100:.0f} → "
                     f"{desk.decided.get(r['id'], '?')} {q}")
    open_orders = [o for o in desk.orders.values() if o["status"] in ("waiting",) and not desk.staffed(o)]
    open_orders.sort(key=lambda o: o["lastPickupAt"])
    if open_orders:
        lines.append(f"\n## Unstaffed won orders ({len(open_orders)}), soonest first: id · route · option · price · last pickup in h · flags")
    for o in open_orders[:12]:
        pick, dest = o["legs"][0]["pickup"]["placeId"], o["legs"][-1]["delivery"]["placeId"]
        flags = " ".join(f for f, on in (("URGENT", o["id"] in desk.urgent), ("LOST", o["id"] in desk.lost)) if on)
        lines.append(f"- {o['id'][:6]} {names.get(pick, pick)}[{desk.supply.get(pick, 0)}]→{names.get(dest, dest)} "
                     f"{o['option'][:2]} {o['priceCents'] / 100:.0f} · {(o['lastPickupAt'] - desk.now) / 60:.1f}h {flags}")
    booked = getattr(desk, "_turn_booked", [])
    if booked:
        lines.append(f"\n## Booked this turn ({len(booked)}): order · class · fee/ref · urgent")
        lines.append("  " + " | ".join(f"{o[:6]} {order_class(desk, o)} {fee / max(ref, 1):.2f}{' U' if u else ''}" for o, fee, ref, _, u in booked[:14]))
    pnl = getattr(desk, "_pnl", {})
    if pnl:
        lines.append("\n## P&L so far by class (delivered money): class · revenue · fees · other · margin")
        for k, v in sorted(pnl.items(), key=lambda kv: -sum(kv[1].values())):
            rev, fee = v.get("revenue", 0), v.get("driver_fee", 0)
            other = sum(v.values()) - rev - fee
            lines.append(f"- {k:<16} {eur(rev):>8} {eur(fee):>8} {eur(other):>7} {eur(sum(v.values())):>8}")
    active = [o for o in desk.orders.values() if o["status"] != "delivered"]
    lines.append(f"\nOrders in play {len(active)} (booked {sum(o['status'] == 'booked' for o in active)}, "
                 f"moving {sum(o['status'] == 'moving' for o in active)}). Params changed so far: "
                 f"{ {k: getattr(p, k) for k in getattr(desk, '_coplay_set', {})} or 'none'}")
    if whatif:
        lines.append("\n## What-if (forked now, played to the end on the same future):")
        for name, r in whatif.items():
            lines.append(f"- {name}: margin €{r['margin']:,.0f} · won {r['won']} · on time {r['on_time']:.1%}")
    return "\n".join(lines) + "\n"


def serve(args):
    HOME.mkdir(parents=True, exist_ok=True)
    champ = champion()
    cls = load_policy(champ["policy"])
    client = CountingClient()
    world_map = load_map(client)
    geo = Geo(world_map)
    names = {p["id"]: p.get("name", p["id"])[:10] for p in world_map["places"]}
    with Slot():
        world = create_world(client, 8, args.seed)
        entry = register(world.id, {"seed": args.seed, "level": 8, "coplay": True})
        try:
            snap = world.snapshot()
            desk = cls(world, cls.Params.from_dict(champ["params"]), 8, geo, world.roster(), snap["now"])
            desk._coplay_set, desk._sent, desk._turn_reqs = {}, {}, []
            desk._pnl, desk._turn_booked = __import__("collections").defaultdict(Counter), []
            ends_at = snap["endsAt"]
            ledger, seen, whatif, turn = Counter(), Counter(), {}, 0
            log = open(HOME / "log.jsonl", "a", encoding="utf-8")
            log.write(json.dumps({"start": world.id, "seed": args.seed, "params": champ["params"]}) + "\n")
            while True:
                score = world.score()
                (HOME / "state.md").write_text(state_text(turn, world, desk, geo, seen, score, whatif, names), encoding="utf-8")
                (HOME / "turn").write_text(str(turn), encoding="utf-8")
                log.write(json.dumps({"turn": turn, "at": desk.now, "clock": clock(desk.now), "margin": score["marginCents"] / 100,
                                      "won": score["wonOrders"], "on_time": score["onTimeShare"], "seen": seen}) + "\n")
                log.flush()
                if desk.now >= ends_at:
                    print(f"END {args.seed}: margin €{score['marginCents'] / 100:,.2f} on time {score['onTimeShare']:.1%}", flush=True)
                    break
                cmd_path = HOME / "cmd.json"
                while not cmd_path.exists():
                    time.sleep(0.3)
                time.sleep(0.1)
                cmd = json.loads(cmd_path.read_text(encoding="utf-8"))
                cmd_path.unlink()
                log.write(json.dumps({"turn": turn, "clock": clock(desk.now), "cmd": cmd}) + "\n")
                if cmd.get("stop"):
                    break
                for k, v in cmd.get("set", {}).items():
                    if not hasattr(desk.p, k):
                        continue
                    setattr(desk.p, k, v)
                    desk._coplay_set[k] = v
                for prefix, how in cmd.get("quote", {}).items():
                    for a in desk.outbox:
                        if a["type"] == "quote" and a["requestId"].startswith(prefix) and how != "keep":
                            r = desk.requests[a["requestId"]]
                            if how == "decline":
                                first = r["options"][0]
                                a["prices"] = {first["kind"]: int(first["listPriceCents"] * desk.p.decline_mult)}
                            else:
                                kind = next(iter(a["prices"]))
                                lst = next(o["listPriceCents"] for o in r["options"] if o["kind"] == kind)
                                a["prices"] = {kind: int(lst * float(how))}
                            desk.decided[a["requestId"]] = "manual"
                for prefix in cmd.get("raise", []):
                    for oid in list(desk.orders):
                        if oid.startswith(prefix):
                            desk.raise_fees(oid)
                whatif = {}
                if cmd.get("whatif"):
                    whatif["unchanged"] = play_out(world, desk, ends_at, {})
                    for name, changes in cmd["whatif"].items():
                        whatif[name] = play_out(world, desk, ends_at, changes)
                    log.write(json.dumps({"turn": turn, "clock": clock(desk.now), "whatif": whatif}) + "\n")
                if "until" in cmd:
                    target = parse_until(cmd["until"], desk.now)
                elif "advance" in cmd:
                    target = desk.now + int(cmd["advance"])
                else:
                    target = desk.now if cmd.get("whatif") else desk.now + 30
                seen, desk._turn_reqs, desk._turn_booked = Counter(), [], []
                while desk.now < min(target, ends_at):
                    step(world, desk, ends_at, ledger, seen)
                turn += 1
        finally:
            entry.unlink(missing_ok=True)
            try:
                world.delete()
            except Exception:
                pass


def do(args):
    turn_path = HOME / "turn"
    before = turn_path.read_text() if turn_path.exists() else ""
    (HOME / "cmd.json.tmp").write_text(args.cmd, encoding="utf-8")
    (HOME / "cmd.json.tmp").replace(HOME / "cmd.json")
    t0 = time.time()
    while time.time() - t0 < 1500:   # every command ends a turn, so the turn number changes
        time.sleep(0.5)
        if (turn_path.read_text() if turn_path.exists() else "") != before:
            break
    time.sleep(0.2)
    sys.stdout.write((HOME / "state.md").read_text(encoding="utf-8"))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    load_dotenv()
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd_name", required=True)
    s = sub.add_parser("serve"); s.add_argument("--seed", default="dev-12")
    d = sub.add_parser("do"); d.add_argument("cmd", nargs="?", default='{"advance": 30}')
    a = ap.parse_args()
    serve(a) if a.cmd_name == "serve" else do(a)


if __name__ == "__main__":
    main()
