import json
import math
import sys
from pathlib import Path


def read_jsonl(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


if sys.argv[1] == "--all":
    champ_map = {r["seed"]: r for r in read_jsonl(Path("champion/results/dev-L8.jsonl"))}
    for d in sorted(Path("runs").iterdir()):
        sf = d / "summary.json"
        if not sf.exists():
            continue
        s = json.loads(sf.read_text())
        rows = read_jsonl(d / "results.jsonl")
        u92 = sum(1 for r in rows if r["on_time"] < 0.92)
        paired = [(r["margin"] - champ_map[r["seed"]]["margin"], r["on_time"] - champ_map[r["seed"]]["on_time"]) for r in rows if r["seed"] in champ_map]
        cmp_str = ""
        if paired:
            dm = [x[0] for x in paired]
            dot = [x[1] for x in paired]
            mean_dm = sum(dm) / len(dm)
            se = math.sqrt(sum((x - mean_dm) ** 2 for x in dm) / (len(dm) * max(1, len(dm) - 1))) if len(dm) > 1 else 0.0
            t = mean_dm / se if se > 0 else 0.0
            w = sum(1 for x in dm if x > 1e-6)
            l = sum(1 for x in dm if x < -1e-6)
            cmp_str = f"dM={mean_dm:+.2f}+/-{se:.2f} (t={t:.2f}) W/L={w}/{l} dOT={100*sum(dot)/len(dot):+.2f}%"
        print(
            d.name,
            f"n={s['n']}",
            f"mean={s['margin_mean']}",
            f"min={s['margin_min']}",
            f"ot_mean={s['on_time_mean']}",
            f"ot_min={s['on_time_min']}",
            f"u92={u92}",
            f"ranked={s['ranked']}/{s['n']}",
            f"won={s['won_mean']}",
            f"safe={s['safe']}",
            cmp_str,
        )
    sys.exit(0)

run_dir = Path(sys.argv[1])
vs_file = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("champion/results/dev-L8.jsonl")

champ = {json.loads(l)["seed"]: json.loads(l) for l in vs_file.read_text().splitlines() if l.strip()} if vs_file.exists() else {}
rows = [json.loads(l) for l in (run_dir / "results.jsonl").read_text().splitlines() if l.strip()]

tot: dict[str, float] = {}
acct_c: dict[str, float] = {}
acct_r: dict[str, float] = {}

for r in sorted(rows, key=lambda x: x["on_time"]):
    s = r["seed"]
    st = r["stats"]
    c = champ.get(s)
    if c:
        print(
            f"{s:9s} | champ {c['margin']:8.1f} ({c['on_time']*100:5.2f}%, w={c['won']:3d}) "
            f"-> {r['margin']:8.1f} ({r['on_time']*100:5.2f}%, w={r['won']:3d}) "
            f"| dM={r['margin']-c['margin']:+7.1f} dOT={(r['on_time']-c['on_time'])*100:+5.2f}% "
            f"| ret={st.get('ret_won',0)}/{st.get('ret_late',0)} hq={st.get('hitch_quote_won',0)}/{st.get('hitch_quote_late',0)} hb={st.get('hitch_booked',0)}/{st.get('hitch_late_booked',0)} hs={st.get('hitch_split',0)}/{st.get('hitch_late',0)} brk={st.get('chain_guard_blocked',0)}"
        )
        for k, v in c.get("account", {}).items():
            acct_c[k] = acct_c.get(k, 0.0) + v
    else:
        print(
            f"{s:9s} | margin {r['margin']:8.1f} ({r['on_time']*100:5.2f}%, w={r['won']:3d}) "
            f"| ret={st.get('ret_won',0)}/{st.get('ret_late',0)} hq={st.get('hitch_quote_won',0)}/{st.get('hitch_quote_late',0)} hb={st.get('hitch_booked',0)}/{st.get('hitch_late_booked',0)} hs={st.get('hitch_split',0)}/{st.get('hitch_late',0)} warn={st.get('deadline_close',0)} brk={st.get('chain_guard_blocked',0)}"
        )
    for k, v in r.get("account", {}).items():
        acct_r[k] = acct_r.get(k, 0.0) + v
    for k, v in st.items():
        if k.startswith("hitch") or k.startswith("ret_") or k in ("deadline_close", "gig_dropped", "gig_expired", "late_reposts", "chain_guard_blocked"):
            tot[k] = tot.get(k, 0.0) + v

n = len(rows)
print()
print(f"=== {n}-WORLD CHAIN STATS ===")
for k in sorted(tot):
    print(f"  {k:34s}: {tot[k]:10.0f}  ({tot[k]/n:8.2f}/wk)")
