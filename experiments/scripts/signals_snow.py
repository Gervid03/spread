"""Part of the unused-signals sizing (exp/claude-batch-bracket): reads the folder that signals_fetch.py writes."""
import json, collections, sys
from pathlib import Path
T = collections.Counter()
for f in sorted(Path(sys.argv[1]).glob("*.json")):
    d = json.loads(f.read_text()); ev = d["events"]
    fc = [(e["from"], e["to"], set(e["placeIds"])) for e in ev if e["kind"] == "forecast"]
    snowy = set().union(*[P for _, _, P in fc]) if fc else set()
    late = {e["line"]["orderId"] for e in ev if e["kind"] == "ledger" and e["line"]["kind"] in ("late_refund", "undelivered_penalty")}
    for e in ev:
        if e["kind"] != "order_won": continue
        o = e["order"]; places = {o["legs"][0]["pickup"]["placeId"], o["legs"][-1]["delivery"]["placeId"]}
        if not (places & snowy): continue
        t0 = max(o["legs"][0]["pickup"]["window"]["from"], e["at"]); t1 = o["deadline"]
        hit = any(a < t1 and b > t0 and (places & P) for a, b, P in fc)
        k = "in_snow" if hit else "same_places_no_snow"
        T[k] += 1; T[k + "_late"] += o["id"] in late
        if hit: T["in_snow_" + o["option"]] += 1; T["in_snow_late_" + o["option"]] += o["id"] in late
print(dict(T))
for k in ("in_snow", "same_places_no_snow"): print(k, T[k], "late", round(T[k + "_late"] / max(1, T[k]), 4))
