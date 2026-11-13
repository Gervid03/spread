"""The map (places and road times) and driver supply around each place.

The map is the same for every world and costs no token, so it is cached in the lab home."""
from __future__ import annotations

import json
import math
from collections import Counter
from typing import Iterable

from spread.types import DriverProfile, WorldMap

from .env import lab_home


def load_map(client) -> WorldMap:
    path = lab_home() / "map.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    world_map = client.map()
    path.write_text(json.dumps(world_map), encoding="utf-8")
    return world_map


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (lat1, lon1, lat2, lon2))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(h))


class Geo:
    """Places, road km/minutes for every ordered pair, and straight-line km (the app's 30 km
    notification radius is a straight line)."""

    def __init__(self, world_map: WorldMap):
        self.places = {p["id"]: p for p in world_map["places"]}
        self._road = {(r["from"], r["to"]): (float(r["km"]), int(r["minutes"])) for r in world_map["roads"]}
        ids = list(self.places)
        self._line = {
            (a, b): haversine_km(self.places[a]["lat"], self.places[a]["lon"], self.places[b]["lat"], self.places[b]["lon"])
            for a in ids for b in ids
        }

    def minutes(self, a: str, b: str) -> int:
        return self._road[(a, b)][1]

    def road_km(self, a: str, b: str) -> float:
        return self._road[(a, b)][0]

    def line_km(self, a: str, b: str) -> float:
        return self._line[(a, b)]

    def within(self, a: str, radius_km: float) -> list[str]:
        return [b for b in self.places if self._line[(a, b)] <= radius_km]

    def supply(self, roster: Iterable[DriverProfile], radius_km: float) -> dict[str, int]:
        """Drivers whose home is within `radius_km` (straight line) of each place: the drivers whom a
        new gig there notifies. At level 8 towns keep very different shares of their drivers."""
        homes = Counter(d["homePlaceId"] for d in roster)
        return {p: sum(n for home, n in homes.items() if self._line[(p, home)] <= radius_km) for p in self.places}
