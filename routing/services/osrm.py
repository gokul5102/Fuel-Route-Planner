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
    """OSRM failed: it was unreachable, broke, or gave an answer we can't use.

    `code` is the API error code; `osrm_code` is OSRM's own code, if it answered with one.
    """

    code = "ROUTING_PROVIDER_ERROR"

    def __init__(self, message: str, osrm_code: str | None = None) -> None:
        self.osrm_code = osrm_code
        super().__init__(message)

    @property
    def details(self) -> dict:
        return {"provider_code": self.osrm_code} if self.osrm_code else {}


class RoutingTimeout(RoutingError):
    code = "ROUTING_PROVIDER_TIMEOUT"


class NoRoute(RoutingError):
    """OSRM answered, but there is no road between the points (or none near one of them)."""

    code = "NO_ROUTE"


NO_ROUTE_CODES = {"NoRoute", "NoSegment"}


def fetch_routes(start: tuple[float, float], finish: tuple[float, float]) -> list[RoutedPath]:
    """Ask OSRM for the driving Route(s) between two (lat, lon) points. One HTTP call."""
    (start_lat, start_lon), (finish_lat, finish_lon) = start, finish
    url = (
        f"{settings.OSRM_BASE_URL}/route/v1/driving/"
        f"{start_lon},{start_lat};{finish_lon},{finish_lat}"
    )
    try:
        response = requests.get(
            url,
            params={"overview": "full", "geometries": "geojson"},
            timeout=settings.HTTP_TIMEOUT_SECONDS,
        )
        body = response.json()
    except requests.Timeout as error:
        raise RoutingTimeout(
            f"The routing provider did not answer within {settings.HTTP_TIMEOUT_SECONDS:g} s."
        ) from error
    except (requests.RequestException, ValueError) as error:  # unreachable, or not JSON
        raise RoutingError("The routing provider could not be reached or broke.") from error

    osrm_code = body.get("code")
    if osrm_code in NO_ROUTE_CODES:
        raise NoRoute(f"No driving Route between the points: {body.get('message')}", osrm_code)
    if osrm_code != "Ok":
        raise RoutingError(
            f"The routing provider failed (HTTP {response.status_code}, {osrm_code}).", osrm_code
        )
    return [
        RoutedPath(
            points=[(lat, lon) for lon, lat in route["geometry"]["coordinates"]],
            distance_miles=route["distance"] / METERS_PER_MILE,
            duration_hours=route["duration"] / 3600,
        )
        for route in body["routes"]
    ]
