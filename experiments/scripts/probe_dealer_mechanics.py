"""Live 9-fork probe of dealer choice mechanics on dev-12:
1. Decoy option effect (can a 2nd option raise an option's limit above hi?)
2. Additive utility indifference law: V(sd) - V(nd) == L_sd - L_nd
3. Quote timing invariance: immediate quote at arrivedAt vs last-minute quote at respondBy - 1
4. BatchId independence: does winning vs declining half of a multi-request batchId change the limits of the other half?
5. Unquoted timeout vs 4.0x explicit decline goodwill impact on same-day next requests.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import tas  # noqa: E402
from spread_lab.env import lab_home, load_dotenv  # noqa: E402


def load_jsonl(p: Path) -> list[dict]:
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    load_dotenv()
    d12_dir = lab_home() / "tas" / "dev-12"
    tape = json.loads((d12_dir / "tape.json").read_text(encoding="utf-8"))
    reqs = {r["id"]: r for r in tape["requests"]}
    lines = load_jsonl(d12_dir / "limits-all.jsonl")
    by_rid = defaultdict(list)
    for r in lines:
        by_rid[r["rid"]].append(r)

    # Find first Monday batch with >=2 multi-option exact requests, and first Monday batchId with >=3 requests
    mon_batches = defaultdict(list)
    for r in tape["requests"]:
        if r["arrivedAt"] < 1440 and r.get("batchId"):
            mon_batches[(r["arrivedAt"], r["batchId"])].append(r["id"])
    target_batch = next(((at, bid, rids) for (at, bid), rids in sorted(mon_batches.items()) if len(rids) >= 3), None)
    print("Target Monday multi-car batchId:", target_batch)

    done = {"multi": False, "batch": False}

    with tas.Tas("dev-12", name="mechanics-probe2", forks=True) as g:
        def hook(game: tas.Tas, actions: list, fresh: list) -> list:
            quotes = [actions[i] for i in fresh]
            rids = [q["requestId"] for q in quotes]
            to = max(game.desk.requests[r]["respondBy"] for r in rids) + 1

            multi = []
            for r in rids:
                sd = next((o for o in by_rid[r] if o["option"] == "same_day" and o["bound"] == "exact"), None)
                nd = next((o for o in by_rid[r] if o["option"] == "next_day" and o["bound"] == "exact"), None)
                if sd and nd:
                    multi.append((r, sd, nd))

            if not done["multi"] and len(multi) >= 2:
                print(f"=== 1-3. Multi-option & Timing Probes at {tas.clock(game.desk.now)} on {len(multi)} multi-opt / {len(quotes)} total reqs ===")
                for decoy_mult in [1.01, 1.20, 2.50]:
                    acts = []
                    for a in quotes:
                        m = next((x for x in multi if x[0] == a["requestId"]), None)
                        if m:
                            _, sd, nd = m
                            acts.append({"type": "quote", "requestId": m[0], "prices": {"same_day": sd["hi"], "next_day": int(nd["hi"] * decoy_mult)}})
                        else:
                            acts.append(a)
                    out = tas.outcomes(tas.on_fork(game, acts, to)["events"])
                    wins = sum(1 for r, _, _ in multi if out.get(r, ("?",))[0] == "won")
                    print(f"  Decoy mult={decoy_mult:.2f} at sd=hi: wins={wins}/{len(multi)}")

                acts_sd, acts_nd = [], []
                for a in quotes:
                    m = next((x for x in multi if x[0] == a["requestId"]), None)
                    if m:
                        _, sd, nd = m
                        acts_sd.append({"type": "quote", "requestId": m[0], "prices": {"same_day": sd["lo"] - 150, "next_day": nd["lo"]}})
                        acts_nd.append({"type": "quote", "requestId": m[0], "prices": {"same_day": sd["lo"], "next_day": nd["lo"] - 150}})
                    else:
                        acts_sd.append(a)
                        acts_nd.append(a)
                out_sd = tas.outcomes(tas.on_fork(game, acts_sd, to)["events"])
                out_nd = tas.outcomes(tas.on_fork(game, acts_nd, to)["events"])
                print(f"  Utility indifference: (sd_lo-€1.50, nd_lo) -> {sum(1 for r,_,_ in multi if out_sd.get(r,('?',None))[:2]==('won','same_day'))}/{len(multi)} same_day; "
                      f"(sd_lo, nd_lo-€1.50) -> {sum(1 for r,_,_ in multi if out_nd.get(r,('?',None))[:2]==('won','next_day'))}/{len(multi)} next_day")

                min_rb = min(game.desk.requests[r]["respondBy"] for r in rids)
                if min_rb > game.desk.now + 2:
                    with tas.forked(game) as cw:
                        cw.advance(to=min_rb - 1, actions=[])
                        acts_lo = [{"type": "quote", "requestId": a["requestId"], "prices": {by_rid[a["requestId"]][0]["option"]: by_rid[a["requestId"]][0]["lo"]}} for a in quotes]
                        out_lo = tas.outcomes(cw.advance(to=to, actions=acts_lo)["events"])
                    with tas.forked(game) as cw:
                        cw.advance(to=min_rb - 1, actions=[])
                        acts_hi = [{"type": "quote", "requestId": a["requestId"], "prices": {by_rid[a["requestId"]][0]["option"]: by_rid[a["requestId"]][0]["hi"]}} for a in quotes if by_rid[a["requestId"]][0]["hi"]]
                        out_hi = tas.outcomes(cw.advance(to=to, actions=acts_hi)["events"])
                    print(f"  Last-minute quote (t={min_rb-1} vs arrived={game.desk.now}): lo_wins={sum(1 for a in quotes if out_lo.get(a['requestId'],('?',))[0]=='won')}/{len(quotes)}, "
                          f"hi_wins={sum(1 for a in quotes if by_rid[a['requestId']][0]['hi'] and out_hi.get(a['requestId'],('?',))[0]=='won')}/{len(quotes)}")
                done["multi"] = True

            if target_batch and not done["batch"] and target_batch[2][0] in rids:
                b_rids = [r for r in target_batch[2] if r in rids]
                half = set(b_rids[: len(b_rids) // 2])
                rest = [r for r in b_rids if r not in half]
                print(f"=== 4. BatchId {target_batch[1]} Independence Probe on {len(b_rids)} simultaneous cars ===")
                # Fork A: win `half` at 0.7x, test `rest` at their known `lo` and `hi`!
                # Fork B: decline `half` at 4.0x, test `rest` at their known `lo` and `hi`!
                for mode_half in ["win_half_0.7x", "decline_half_4.0x"]:
                    acts_lo, acts_hi = [], []
                    for a in quotes:
                        r = a["requestId"]
                        o0 = by_rid[r][0]
                        if r in half:
                            mult = 0.7 if mode_half.startswith("win") else 4.0
                            p = int(o0["list"] * mult)
                            acts_lo.append({"type": "quote", "requestId": r, "prices": {o0["option"]: p}})
                            acts_hi.append({"type": "quote", "requestId": r, "prices": {o0["option"]: p}})
                        elif r in rest:
                            acts_lo.append({"type": "quote", "requestId": r, "prices": {o0["option"]: o0["lo"]}})
                            acts_hi.append({"type": "quote", "requestId": r, "prices": {o0["option"]: o0["hi"]}})
                        else:
                            acts_lo.append(a)
                            acts_hi.append(a)
                    out_lo = tas.outcomes(tas.on_fork(game, acts_lo, to)["events"])
                    out_hi = tas.outcomes(tas.on_fork(game, acts_hi, to)["events"])
                    w_lo = sum(1 for r in rest if out_lo.get(r, ("?",))[0] == "won")
                    w_hi = sum(1 for r in rest if out_hi.get(r, ("?",))[0] == "won")
                    print(f"  [{mode_half}]: rest ({len(rest)} cars) wins at lo={w_lo}/{len(rest)}, wins at hi={w_hi}/{len(rest)}")
                done["batch"] = True

            return actions

        g.hook = hook
        while g.desk.now < tas.minute_of("Mon 18:00") and not (done["multi"] and (done["batch"] or not target_batch)):
            g.step()
        print(f"Total forks used: {g.forks}")


if __name__ == "__main__":
    main()
