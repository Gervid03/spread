"""How much is knowing the price worth? (his question, Sun 15 Nov ~00:15)

Each dealer request has a limit: the highest price that still wins (binary search on forks, dev-12). A desk never
sees it; it predicts ln(limit/list) from what it knows and quotes the price that maximises (price - cost) x P(win).
Same requests, same cost, different information:

  A  nothing             one mean for everything
  B  before the week     option, menu, pickup town, delivery town, hour (holds across worlds, roughly)
  C  + trust             our on-time count for that dealer: we keep it exactly
  D  + competitor steps  from our own daily win share per busy dealer: < 30% -> it raises next morning, 70%+ -> it cuts
  E  + day and dealer    today's day factor and the dealer's own taste (a live desk learns these only from wins and
                         losses during the week: an upper bound for live)
  F  + lane              the in-sample fit: what's left is the noise no one can predict (~0.17)
  P  perfect             the oracle: quote just under the limit

Cost = COST x the typical fee (a single car's driver costs ~0.8x). Residual sd by 10-fold CV, grouped by request.

    uv run --with numpy python experiments/orc/info.py ~/.spread-lab/tas/dev-12 [cost x typical, default 0.8]
"""
import json
import math
import sys
from collections import Counter, defaultdict

import numpy as np
from statistics import NormalDist

D = sys.argv[1]
COST = float(sys.argv[2]) if len(sys.argv) > 2 else 0.8
rows = [json.loads(line) for line in open(D + "/limits-all.jsonl")]
rows = [r for r in rows if r["bound"] == "exact" and r["legs"] == 1]
tape = json.load(open(D + "/tape.json", encoding="utf-8"))
reqs = {r["id"]: r for r in tape["requests"]}
y = np.array([math.log(r["lo"] / r["list"]) for r in rows])

# the competitor's steps per dealer, from the measuring desk's own wins (tas-state's law)
won_by = defaultdict(Counter)                 # (dealer, day) -> won / asked, one count per request
seen = set()
for r in rows:
    if r["rid"] not in seen:
        seen.add(r["rid"])
        won_by[(r["dealer"], r["day"])]["asked"] += 1
        won_by[(r["dealer"], r["day"])]["won"] += r["desk"] == "won"
steps = {}
for dealer in {r["dealer"] for r in rows}:
    s = 0
    for day in range(5):
        steps[(dealer, day)] = s
        c = won_by[(dealer, day)]
        if day < 4 and c["asked"] >= 10:
            share = c["won"] / c["asked"]
            s += 1 if share < 0.3 else -1 if share >= 0.7 else 0


def menu(r):
    return ",".join(sorted(o["kind"] for o in reqs[r["rid"]]["options"]))


feats = {
    "option": [r["option"] for r in rows], "menu": [menu(r) for r in rows],
    "pickup": [r["pickup"] for r in rows], "delivery": [r["delivery"] for r in rows],
    "hour": [(r["at"] % 1440) // 120 for r in rows],
    "trust": [min(r["trust"], 25) for r in rows],                      # numeric: +1% a count
    "steps": [steps[(r["dealer"], r["day"])] for r in rows],             # numeric
    "day": [r["day"] for r in rows], "dealer": [r["dealer"] for r in rows],
    "lane": [r["pickup"] + ">" + r["delivery"] for r in rows],
}
NUMERIC = {"trust", "steps"}


def design(names):
    cols = [np.ones((len(rows), 1))]
    for n in names:
        if n in NUMERIC:
            cols.append(np.array(feats[n], dtype=float)[:, None])
        else:
            u = sorted(set(feats[n]))
            idx = {v: i for i, v in enumerate(u)}
            M = np.zeros((len(rows), len(u)))
            for i, v in enumerate(feats[n]):
                M[i, idx[v]] = 1
            cols.append(M[:, 1:])
    return np.hstack(cols)


def predict(names, k=10, ridge=1.0):
    """Out-of-fold predictions of ln(limit/list), grouped by request."""
    X = design(names)
    rng = np.random.default_rng(0)
    rids = sorted({r["rid"] for r in rows})
    perm = {q: i for i, q in enumerate(rng.permutation(rids))}
    fold = np.array([perm[r["rid"]] % k for r in rows])
    mu = np.zeros(len(rows))
    for f in range(k):
        te, tr = np.where(fold == f)[0], np.where(fold != f)[0]
        A = X[tr]
        w = np.linalg.solve(A.T @ A + ridge * np.eye(A.shape[1]), A.T @ y[tr])
        mu[te] = X[te] @ w
    return mu, (y - mu).std()


N = NormalDist()
lst = np.array([r["list"] for r in rows], dtype=float)
cost = COST * np.array([r["ref"] for r in rows], dtype=float)
limit = np.array([r["lo"] for r in rows], dtype=float)
grid = np.exp(np.linspace(-0.6, 1.0, 321))           # quotes from 0.55x to 2.7x the list price


def play(mu, sd):
    """Quote the price that maximises (p - cost) P(limit >= p) under the prediction; count what really wins."""
    margin, wins = 0.0, 0
    for i in range(len(rows)):
        p = lst[i] * grid
        pw = np.array([1 - N.cdf((g - mu[i]) / sd) for g in np.log(grid)])
        q = p[int(np.argmax((p - cost[i]) * pw))]
        if limit[i] >= q:
            margin += q - cost[i]
            wins += 1
    return margin / 100, wins / len(rows)


SETS = [("A nothing", []),
        ("B before the week", ["option", "menu", "pickup", "delivery", "hour"]),
        ("C + trust", ["option", "menu", "pickup", "delivery", "hour", "trust"]),
        ("D + competitor steps", ["option", "menu", "pickup", "delivery", "hour", "trust", "steps"]),
        ("E + day, dealer", ["option", "menu", "pickup", "delivery", "hour", "trust", "steps", "day", "dealer"]),
        ("F + lane (in-sample floor)", ["option", "menu", "pickup", "delivery", "hour", "trust", "steps", "day", "dealer", "lane"])]
perfect = float(np.maximum(limit - 1 - cost, 0).sum() / 100)
print(f"dev-12: {len(rows)} (request, option) limits; cost {COST} x typical fee; every option priced on its own")
print(f"{'information':30s} {'resid sd':>8s} {'margin':>9s} {'win':>5s} {'of perfect':>10s}")
for name, names in SETS:
    mu, sd = predict(names)
    m, w = play(mu, sd)
    print(f"{name:30s} {sd:8.3f} €{m:8,.0f} {100 * w:4.0f}% {100 * m / perfect:9.0f}%")
print(f"{'P perfect (the oracle)':30s} {0:8.3f} €{perfect:8,.0f} {100 * float((limit - 1 > cost).mean()):4.0f}%      100%")
