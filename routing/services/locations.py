"""Turn a `start` / `finish` query into a point on the map.

Tried in order:
1. "lat,lng" coordinates: parsed (no external call).
2. "City, ST": looked up in the local Census places index (no external call).
3. Anything else: Nominatim, restricted to the USA (one external call, then cached
   for GEOCODE_CACHE_SECONDS, keyed on the query ignoring case and spacing).
"""

import hashlib
import re
from dataclasses import dataclass

from django.conf import settings
from django.core.cache import cache
from requests import Timeout

from routing.services import nominatim
from routing.services.places import get_place_index
from routing.services.usa import is_in_usa

COORDINATES = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")
CITY_STATE = re.compile(r"^\s*([^,]+?)\s*,\s*([A-Za-z]{2})\s*$")


@dataclass(frozen=True)
class ResolvedLocation:
    query: str
    lat: float
    lon: float
    resolved_by: str  # "coordinates" | "census" | "nominatim"


# Canadian provinces and territories: "Toronto, ON" is rejected without any lookup.
CANADIAN_PROVINCES = frozenset(
    {"AB", "BC", "MB", "NB", "NL", "NS", "NT", "NU", "ON", "PE", "QC", "SK", "YT"}
)


class LocationError(Exception):
    """A query that cannot become a start or finish point.

    `code` is the API error code (routing.errors maps it to an HTTP status); `details`
    goes into the error body as is.
    """

    code = "LOCATION_ERROR"

    def __init__(self, message: str, query: str) -> None:
        self.query = query
        self.details = {"query": query}
        super().__init__(message)


class LocationNotFound(LocationError):
    code = "LOCATION_NOT_FOUND"

    def __init__(self, query: str) -> None:
        super().__init__(f"Could not find a location for {query!r}.", query)


class LocationOutsideUSA(LocationError):
    code = "LOCATION_OUTSIDE_USA"

    def __init__(self, query: str) -> None:
        super().__init__(f"{query!r} is outside the USA; only US trips can be planned.", query)


class GeocodingFailed(LocationError):
    """Nominatim could not be reached or answered with an error (an upstream failure)."""

    def __init__(self, query: str, timed_out: bool) -> None:
        self.code = "ROUTING_PROVIDER_TIMEOUT" if timed_out else "ROUTING_PROVIDER_ERROR"
        super().__init__(f"The geocoding service failed for {query!r}; try again later.", query)


class SameStartAndFinish(LocationError):
    code = "INVALID_INPUT"

    def __init__(self, start: "ResolvedLocation", finish: "ResolvedLocation") -> None:
        super().__init__(
            f"{start.query!r} and {finish.query!r} are the same place; there is no trip to plan.",
            start.query,
        )
        self.details = {"start": start.query, "finish": finish.query}


def check_distinct(start: "ResolvedLocation", finish: "ResolvedLocation") -> None:
    """Start and finish must differ by more than ~10 m (4 decimal places)."""
    if (round(start.lat, 4), round(start.lon, 4)) == (round(finish.lat, 4), round(finish.lon, 4)):
        raise SameStartAndFinish(start, finish)


def resolve_location(query: str) -> ResolvedLocation:
    match = COORDINATES.match(query)
    if match:
        lat, lon = float(match[1]), float(match[2])
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            if not is_in_usa(lat, lon):
                raise LocationOutsideUSA(query)
            return ResolvedLocation(query, lat, lon, "coordinates")
    state = None
    match = CITY_STATE.match(query)
    if match:
        city, state = match[1], match[2].upper()
        if state in CANADIAN_PROVINCES:
            raise LocationOutsideUSA(query)
        found = get_place_index().find(city, state)
        if found:
            return ResolvedLocation(query, *found, "census")
    lat, lon = _geocode(query, state)
    return ResolvedLocation(query, lat, lon, "nominatim")


def _geocode(query: str, state: str | None) -> tuple[float, float]:
    """Nominatim, through the cache. Only places that were found are cached.

    For a "City, ST" query, a match in another state does not count.
    """
    normalised = " ".join(query.lower().split())
    key = "geocode:" + hashlib.sha256(normalised.encode()).hexdigest()
    cached = cache.get(key)
    if cached is not None:
        return cached
    try:
        place = nominatim.search(query, country_code="us")
    except nominatim.NominatimError as error:
        raise GeocodingFailed(query, timed_out=isinstance(error.__cause__, Timeout)) from error
    if place is None or (state and place.region != f"US-{state}"):
        raise LocationNotFound(query)
    cache.set(key, (place.lat, place.lon), settings.GEOCODE_CACHE_SECONDS)
    return place.lat, place.lon
