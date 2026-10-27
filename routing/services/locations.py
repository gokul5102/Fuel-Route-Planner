"""Turn a `start` / `finish` query into a point on the map.

Only "lat,lng" coordinates for now (no external call).
"""

import re
from dataclasses import dataclass

COORDINATES = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")


@dataclass(frozen=True)
class ResolvedLocation:
    query: str
    lat: float
    lon: float
    resolved_by: str  # "coordinates"


class LocationNotFound(Exception):
    code = "LOCATION_NOT_FOUND"

    def __init__(self, query: str) -> None:
        self.query = query
        super().__init__(f"Could not find a location for {query!r}.")


def resolve_location(query: str) -> ResolvedLocation:
    match = COORDINATES.match(query)
    if match:
        lat, lon = float(match[1]), float(match[2])
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            return ResolvedLocation(query, lat, lon, "coordinates")
    raise LocationNotFound(query)
