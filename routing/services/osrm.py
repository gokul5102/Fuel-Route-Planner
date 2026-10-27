"""The OSRM routing client: one call returns the Route's full geometry, distance and duration.

The public demo server allows at most 1 request per second and has no uptime
guarantee, so there are no retries and a short timeout. Note OSRM wants lon,lat.
"""

from dataclasses import dataclass

import requests
from django.conf import settings

METERS_PER_MILE = 1609.344


@dataclass(frozen=True)
class RoutedPath:
    """One Route as OSRM returned it."""

    points: list[tuple[float, float]]  # (lat, lon) along the road, start to finish
    distance_miles: float
    duration_hours: float


class RoutingError(Exception):
    """OSRM failed or found no Route. `osrm_code` is OSRM's own code, if it answered."""

    def __init__(self, message: str, osrm_code: str | None = None) -> None:
        self.osrm_code = osrm_code
        super().__init__(message)


def fetch_routes(start: tuple[float, float], finish: tuple[float, float]) -> list[RoutedPath]:
    """Ask OSRM for the driving Route(s) between two (lat, lon) points. One HTTP call."""
    (start_lat, start_lon), (finish_lat, finish_lon) = start, finish
    url = (
        f"{settings.OSRM_BASE_URL}/route/v1/driving/"
        f"{start_lon},{start_lat};{finish_lon},{finish_lat}"
    )
    response = requests.get(
        url,
        params={"overview": "full", "geometries": "geojson"},
        timeout=settings.HTTP_TIMEOUT_SECONDS,
    )
    body = response.json()
    if body.get("code") != "Ok":
        raise RoutingError(body.get("message", "OSRM found no Route."), body.get("code"))
    return [
        RoutedPath(
            points=[(lat, lon) for lon, lat in route["geometry"]["coordinates"]],
            distance_miles=route["distance"] / METERS_PER_MILE,
            duration_hours=route["duration"] / 3600,
        )
        for route in body["routes"]
    ]
