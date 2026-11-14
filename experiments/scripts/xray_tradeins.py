"""Print exact reason every 2-leg trade-in on dev-12, dev-01, dev-08, dev-07 was declined,
plus its list, ref, and true dealer limit_x!"""
from __future__ import annotations

import json
from pathlib import Path

from spread_lab.geo import Geo, load_map
from spread_lab.policy import Desk, Params


class DummyW:
    def act(self, a):
        return [{"ok": True, "id": "g1"} for _ in a]


def main() -> None:
    geo = Geo(load_map(None))
    champ_p = Params.from_dict(json.loads(Path("champion/champion.json").read_text())["params"])
    lims = {}
    for l in (Path.home() / ".spread-lab/tas/dev-12/limits-all.jsonl").read_text().splitlines():
        if l.strip():
            r = json.loads(l)
            if r["legs"] == 2:
                lims[r["rid"]] = r

    for seed in ["dev-12", "dev-07", "dev-08", "dev-01"]:
        tape = json.loads((Path.home() / f".spread-lab/tas/{seed}/tape.json").read_text())
        rev = json.loads((Path.home() / f".spread-lab/tas/{seed}/reveal-v5.json").read_text())
        desk = Desk(DummyW(), champ_p, 8, geo, tape["roster"], 0)
        print(f"=== {seed} 2-LEG TRADE-INS ===")
        for it in rev["requests"]:
            r = it["request"]
            if len(r["legs"]) != 2:
                continue
            desk.now = r["arrivedAt"]
            prices, dec = desk.price(r)
            p0 = r["legs"][0]["pickup"]["placeId"]
            d0 = r["legs"][0]["delivery"]["placeId"]
            drv = geo.minutes(p0, d0) * 2
            sup = desk.supply.get(p0, 0)
            opt = r["options"][0]
            w0 = r["legs"][0]["pickup"]["window"]
            w1 = r["legs"][1]["pickup"]["window"]
            lim_info = lims.get(r["id"], {})
            lo = lim_info.get("lo")
            print(
                f"  {r['id']} d{r['arrivedAt']//1440} {(r['arrivedAt']%1440)//60:02d}h {p0}[{sup}]<->{d0} "
                f"opt={opt['kind']:8s} 2xdrv={drv:3d}m list={opt['listPriceCents']/100:6.1f} ref={r['referenceFeeCents']/100:6.1f} "
                f"lo={lo/100 if lo else 0:6.1f} w0={w0['from']%1440//60:02d}-{w0['to']%1440//60:02d}h "
                f"w1={w1['from']%1440//60:02d}-{w1['to']%1440//60:02d}h note={bool(r['note'])} -> dec={dec} out={it['outcome']}"
            )


if __name__ == "__main__":
    main()
