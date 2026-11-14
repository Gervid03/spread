"""Can one car be in two open gigs at once? (Sat 14 Nov: the user's idea of posting every rotation of a cycle.)
Replays a co-play game to its current minute, then on a fork posts two available cars as [A, B] and as [B, A]
(and A alone twice), and prints what the world answers.   uv run python scripts/test_dual_post.py cyc-2
"""
import json
import sys

sys.path.insert(0, "scripts")
from coplay import Game, home  # noqa: E402
from coplay_cycles import available_orders, tour_actions  # noqa: E402
from spread_lab.env import load_dotenv  # noqa: E402

load_dotenv()
log = json.loads((home(sys.argv[1]) / "log.json").read_text(encoding="utf-8"))
with Game(log) as g:
    g.replay()
    desk = g.desk
    av = [o for o in available_orders(desk) if not any(o in {s["orderId"] for s in p["stops"]} for gid, p in desk.posts.items() if gid in desk.booked)]
    print("available:", av)
    a, b = av[0], av[1]
    fw = g.world.fork()
    try:
        w1, p_ab = tour_actions(desk, [a, b], 0.6)
        _, p_ba = tour_actions(desk, [b, a], 0.6)
        _, p_a = tour_actions(desk, [a], 0.9)
        res = fw.act(w1 + [p_ab, p_ba, p_a])
        for name, r in zip([f"withdraw {x['gigId'][:6]}" for x in w1] + ["post [A,B]", "post [B,A]", "post [A] alone"], res):
            print(name, "->", json.dumps(r)[:300])
    finally:
        fw.delete()
