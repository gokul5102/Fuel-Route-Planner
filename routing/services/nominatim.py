"""Free-text geocoding through the public Nominatim (OpenStreetMap) API.

Policy: at most 1 request per second and an identifying User-Agent. Callers are
responsible for pacing and caching; this module makes exactly one request per call.
"""

from dataclasses import dataclass

import requests
from django.conf import settings


@dataclass(frozen=True)
class NominatimPlace:
    lat: float
    lon: float
    region: str  # ISO 3166-2 code of the state or province, e.g. "US-TX"; "" if unknown


class NominatimError(Exception):
    """Nominatim could not be reached, or answered with an error."""


def search(query: str, country_code: str = "us") -> NominatimPlace | None:
    """Return the best match for `query` within one country, or None if nothing matches."""
    try:
        response = requests.get(
            f"{settings.NOMINATIM_BASE_URL}/search",
            params={
                "q": query,
                "format": "json",
                "limit": 1,
                "countrycodes": country_code,
                "addressdetails": 1,
            },
            headers={"User-Agent": settings.NOMINATIM_USER_AGENT},
            timeout=settings.HTTP_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        results = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise NominatimError(str(exc)) from exc
    if not results:
        return None
    best = results[0]
    region = best.get("address", {}).get("ISO3166-2-lvl4", "")
    return NominatimPlace(lat=float(best["lat"]), lon=float(best["lon"]), region=region)
