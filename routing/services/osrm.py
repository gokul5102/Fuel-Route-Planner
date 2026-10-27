"""The OSRM routing client: one call returns each Route (the fastest plus OSRM's alternatives)
with its full geometry, distance and duration.

The geometry comes as polyline6 (about a fifth the size of GeoJSON) and is decoded here.
The public demo server allows at most 1 request per second and has no uptime
guarantee, so there are no retries and a short timeout. Note OSRM wants lon,lat.
"""

import json
from dataclasses import dataclass
from time import monotonic

import requests
from django.conf import settings
from urllib3.exceptions import ReadTimeoutError

from routing.services import polyline

METERS_PER_MILE = 1609.344
CHUNK_BYTES = 64 * 1024


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
    limit = settings.HTTP_TIMEOUT_SECONDS
    too_slow = f"The routing provider did not answer within {limit:g} s."
    deadline = monotonic() + limit
    try:
        with requests.get(
            url,
            params={"overview": "full", "geometries": "polyline6", "alternatives": "true"},
            timeout=limit,  # requests applies this to the connect and to EACH read...
            stream=True,
        ) as response:
            content = _download(response, deadline)  # ...so the whole download is capped here
        body = json.loads(content)
    except (requests.Timeout, DeadlinePassed) as error:
        raise RoutingTimeout(too_slow) from error
    except requests.ConnectionError as error:
        # requests reports a read that times out in the middle of the body as a ConnectionError
        if error.args and isinstance(error.args[0], ReadTimeoutError):
            raise RoutingTimeout(too_slow) from error
        raise RoutingError("The routing provider could not be reached or broke.") from error
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
            points=polyline.decode(route["geometry"]),
            distance_miles=route["distance"] / METERS_PER_MILE,
            duration_hours=route["duration"] / 3600,
        )
        for route in body["routes"]
    ]


class DeadlinePassed(Exception):
    """The response body was still arriving when the total time limit ran out."""


def _download(response: requests.Response, deadline: float) -> bytes:
    """Read the whole body, giving up once the monotonic clock passes `deadline`."""
    chunks = []
    for chunk in response.iter_content(CHUNK_BYTES):
        if monotonic() > deadline:
            raise DeadlinePassed
        chunks.append(chunk)
    return b"".join(chunks)
