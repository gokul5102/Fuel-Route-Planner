"""Free-text geocoding through the public Nominatim (OpenStreetMap) API.

Policy: at most 1 request per second and an identifying User-Agent. Callers are
responsible for pacing and caching; this module makes exactly one request per call.
"""

import requests
from django.conf import settings

LatLon = tuple[float, float]


class NominatimError(Exception):
    """Nominatim could not be reached, or answered with an error."""


def search(query: str, country_code: str = "us") -> LatLon | None:
    """Return the best match for `query` within one country, or None if nothing matches."""
    try:
        response = requests.get(
            f"{settings.NOMINATIM_BASE_URL}/search",
            params={"q": query, "format": "json", "limit": 1, "countrycodes": country_code},
            headers={"User-Agent": settings.NOMINATIM_USER_AGENT},
            timeout=settings.HTTP_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        results = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise NominatimError(str(exc)) from exc
    if not results:
        return None
    return float(results[0]["lat"]), float(results[0]["lon"])
