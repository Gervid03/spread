"""Slot-free live latency benchmark & 2-leg trade-in diagnostic on dev-12 tape."""
from __future__ import annotations

import json
import time

from spread_lab.env import lab_home
from spread_lab.geo import Geo
from spread_lab.policy import Desk, Params


class DummyWorld:
    def __init__(self) -> None:
        self._n = 0

    def act(self, actions: list[dict]) -> list[dict]:
        out = []
        for a in actions:
            if a["type"] == "post":
                self._n += 1
                out.append({"ok": True, "id": f"g{self._n}"})
            else:
                out.append({"ok": True})
        return out


def main() -> None:
    lh = lab_home()
    geo = Geo(json.loads((lh / "map.json").read_text()))
    tape = json.loads((lh / "tas" / "dev-12" / "tape.json").read_text())
    champ_p = json.loads(open("champion/champion.json").read())["params"]
    p = Params.from_dict({
        **champ_p,
        "r4v_tours": True,
        "r4v_stage_min": 75,
        "r4v_allow_shuttle": True,
        "r4v_sponsor_quote": True,
        "r4v_return_floor_mult": 0.75,
        "r4v_return_disc": 0.05,
        "r4v_tradein_seq": True,
        "r4v_slow_fee_mult": 1.05,
        "r4v_fri_endgame": True,
        "r4v_fri_slow_disc": 0.04,
    })
    desk = Desk(DummyWorld(), p, 8, geo, tape["roster"], 480)
    for req in tape["requests"]:
        if len(req["legs"]) == 2:
            desk.now = req["arrivedAt"]
            prices, dec = desk.price(req)
            l0, l1 = req["legs"][0], req["legs"][1]
            p0, d0 = l0["pickup"]["placeId"], l0["delivery"]["placeId"]
            p1, d1 = l1["pickup"]["placeId"], l1["delivery"]["placeId"]
            drv = geo.minutes(p0, d0) + geo.minutes(d0, p1) + geo.minutes(p1, d1)
            print(
                f"{req['id']} at={req['arrivedAt']} {p0}[s30={desk.supply[p0]},g55={desk.gate_supply[p0]}]->{d0}->{d1} "
                f"drv={drv} w0={l0['pickup']['window']} d0w={l0['delivery']['window']} w1={l1['pickup']['window']} "
                f"opts={[(o['kind'], o['deadline']) for o in req['options']]} note={bool(req['note'])} -> {dec} {prices}"
            )


if __name__ == "__main__":
    main()
