"""Controlled fork probe for the Laptop Lead's 13:50 Thursday-Start discovery on dev-12 (~22 forks, ~15s):
1. Measures exact Thursday 08:00 dealer limits when Mon-Wed (614 requests) are:
   (a) Completely unquoted (silent advance to Thu 00:00 = exact replica of the 14:00 Test Final!), vs
   (b) Explicitly declined at 4.0x list (0% win share, 0 unquoted penalty).
   -> Directly isolates the 3-day unquoted satisfaction penalty vs the +3-step competitor price hike!
2. Runs exact `branch()` from `Thu 00:00` (after silent Mon-Wed) comparing:
   - Control: standard Desk cold-start (`mult=1.35`, `price_target_win=0.35`),
   - ThuHike152: initialize `mult=1.52` + `price_target_win=0.45` to capture +3-step competitor ceiling immediately,
   - ThuHike152+FriUncork: `mult=1.52`, `price_target_win=0.46`, `backlog_ratio=0.14` (harvest Thu <70% + Fri 100% endgame!).
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from spread_lab.env import lab_home  # noqa: E402
from tas import DAY, HOUR, Tas, branch, forked, probe_prices  # noqa: E402


def probe_thu_morning(seed: str, silent_mon_wed: bool) -> dict:
    label = "thu-silent" if silent_mon_wed else "thu-declined4x"
    thu_start = 3 * DAY
    probe_end = 3 * DAY + 9 * HOUR + 30

    with Tas(seed, {}, "spread_lab.policy:Desk", label, forks=True) as g:
        if silent_mon_wed:
            # Advance world silently to Thu 00:00 (exact replica of test final pre-played Mon-Wed!)
            while g.desk.now < thu_start:
                nxt = min(thu_start, g.desk.now + 12 * HOUR)
                step = g.world.advance(to=nxt, actions=[])
                g.desk.now = step["now"]
                for ev in step["events"]:
                    if ev["kind"] == "price_request":
                        g.desk.requests[ev["request"]["id"]] = ev["request"]
        else:
            def decline_hook(game: Tas, actions: list, fresh: list) -> list:
                out = list(actions)
                for idx in fresh:
                    rid = out[idx]["requestId"]
                    req = game.desk.requests[rid]
                    out[idx] = {
                        "type": "quote",
                        "requestId": rid,
                        "prices": {o["kind"]: o["listPriceCents"] * 4 for o in req["options"]},
                    }
                return out

            g.hook = decline_hook
            g.play_to(thu_start)

        # Now capture quotes arriving Thu 07:00 .. 09:30 and probe their exact dealer limits!
        captured_quotes: list[dict] = []
        captured_targets: dict[str, str] = {}

        def capture_thu(game: Tas, actions: list, fresh: list) -> list:
            out = list(actions)
            for idx in fresh:
                rid = out[idx]["requestId"]
                req = game.desk.requests[rid]
                opt0 = req["options"][0]
                decl = {
                    "type": "quote",
                    "requestId": rid,
                    "prices": {o["kind"]: o["listPriceCents"] * 4 for o in req["options"]},
                }
                out[idx] = decl
                if not captured_quotes:
                    captured_quotes.extend([out[j] for j in fresh])
                    for j in fresh:
                        r2 = game.desk.requests[out[j]["requestId"]]
                        captured_targets[r2["id"]] = r2["options"][0]["kind"]
            return out

        # Advance to Thu 08:20 where first morning batch arrives, probe before sending!
        while g.desk.now < probe_end and not captured_targets:
            # Peek on next step by intercepting inside hook!
            def probe_first_batch(game: Tas, actions: list, fresh: list) -> list:
                if not fresh or captured_targets:
                    return actions
                quotes = [actions[i] for i in fresh]
                targets = {q["requestId"]: game.desk.requests[q["requestId"]]["options"][0]["kind"] for q in quotes}
                res = probe_prices(game, quotes, targets, lo_x=0.9, hi_x=2.6, iters=9)
                for rid, st in res.items():
                    captured_quotes.append({"rid": rid, "dealer": game.desk.requests[rid]["dealerId"], **st})
                captured_targets.update(targets)
                return actions

            g.hook = probe_first_batch
            g.play_to(min(probe_end, g.desk.now + 20))

        # If silent_mon_wed, also run exact branch() to end of week comparing cold-start strategies!
        branch_res = {}
        if silent_mon_wed:
            # Re-create clean silent Thu 00:00 game for exact branch() from Thu 00:00!
            pass
        return {"probed": captured_quotes}


def run_thu_coldstart_branch(seed: str) -> dict:
    thu_start = 3 * DAY
    with Tas(seed, {}, "spread_lab.policy:Desk", "thu-cold-branch", forks=True) as g:
        # Advance world silently to Thu 00:00, then initialize fresh Desk via rejoin/now=4320 semantics!
        while g.desk.now < thu_start:
            nxt = min(thu_start, g.desk.now + 12 * HOUR)
            step = g.world.advance(to=nxt, actions=[])
            g.desk.now = step["now"]
        # Reset desk to clean Thu 00:00 cold-join state (mult=1.35, 0 orders, 0 trust)
        g.desk.mult = g.desk.p.price_mult_l8
        g.desk.dealer_adj.clear()
        g.desk.dealer_trust.clear()

        def hike_152(sub: Tas) -> None:
            sub.desk.mult = 1.52
            sub.desk.p.price_target_win = 0.44

        def hike_154_uncork(sub: Tas) -> None:
            sub.desk.mult = 1.54
            sub.desk.p.price_target_win = 0.46
            sub.desk.p.backlog_ratio = 0.135
            sub.desk.p.trust_invest = 0.05

        res = branch(g, {"mult152_win44": hike_152, "mult154_win46_uncork": hike_154_uncork})
        return res


def main() -> None:
    seed = "dev-12"
    r_sil = probe_thu_morning(seed, silent_mon_wed=True)
    r_dec = probe_thu_morning(seed, silent_mon_wed=False)
    b_res = run_thu_coldstart_branch(seed)

    sil_map = {x["rid"]: x for x in r_sil["probed"]}
    dec_map = {x["rid"]: x for x in r_dec["probed"]}
    print("=== THURSDAY 08:00 LIMITS: SILENT MON-WED (614 UNQUOTED) vs DECLINED 4.0x ===")
    for rid, s in sil_map.items():
        d = dec_map.get(rid, {})
        if s.get("lo") and d.get("lo"):
            print(
                f"  {rid} {s['dealer']}: silent={s['lo']/s['list']:.4f}x  declined4x={d['lo']/d['list']:.4f}x  "
                f"ratio(silent/decl4x)={s['lo']/d['lo']:.4f}"
            )

    print("=== THU 00:00 COLD-START BRANCH TO WEEK END ===")
    for k, v in b_res.items():
        print(f"  {k:<24}: margin=€{v['margin']:>9,.2f} (Δ {v['delta']:+,.2f})  won={v['won']:>3}  OT={v['on_time']*100:5.2f}%")

    out_p = lab_home() / "tas" / seed / "tas-state-thu-coldstart.json"
    out_p.write_text(json.dumps({"silent_probe": r_sil, "declined_probe": r_dec, "branch": b_res}, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
