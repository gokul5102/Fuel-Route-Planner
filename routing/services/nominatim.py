"""Free-text geocoding through the public Nominatim (OpenStreetMap) API.

Policy: at most 1 request per second and an identifying User-Agent. This module paces
its own calls (process-wide, across threads); callers cache the results. Each call makes
exactly one request.
"""

import threading
from dataclasses import dataclass
from time import monotonic, sleep

import requests
from django.conf import settings

from routing.services import http
from routing.services.request_metrics import count_external_call


@dataclass(frozen=True)
class NominatimPlace:
    lat: float
    lon: float
    region: str  # ISO 3166-2 code of the state or province, e.g. "US-TX"; "" if unknown


class NominatimError(Exception):
    """Nominatim could not be reached, or answered with an error."""


MIN_INTERVAL_SECONDS = 1.0  # Nominatim usage policy: at most 1 request per second
_last_call: float | None = None  # monotonic time of this process's latest request
_pacing_lock = threading.Lock()


def _wait_for_turn() -> None:
    """Sleep until at least MIN_INTERVAL_SECONDS have passed since the previous request.

    The lock is held while sleeping, so concurrent callers queue up one second apart.
    """
    global _last_call
    with _pacing_lock:
        if _last_call is not None:
            remaining = _last_call + MIN_INTERVAL_SECONDS - monotonic()
            if remaining > 0:
                sleep(remaining)
        _last_call = monotonic()


def search(query: str, country_code: str = "us") -> NominatimPlace | None:
    """Return the best match for `query` within one country, or None if nothing matches."""
    _wait_for_turn()
    count_external_call()
    try:
        status, results = http.get_json(  # within HTTP_TIMEOUT_SECONDS in total
            f"{settings.NOMINATIM_BASE_URL}/search",
            params={
                "q": query,
                "format": "json",
                "limit": 1,
                "countrycodes": country_code,
                "addressdetails": 1,
            },
            headers={"User-Agent": settings.NOMINATIM_USER_AGENT},
        )
    except (requests.RequestException, ValueError) as exc:  # unreachable, too slow, not JSON
        raise NominatimError(str(exc)) from exc
    if status >= 400:
        raise NominatimError(f"Nominatim answered HTTP {status}.")
    try:
        return _best_place(results)
    except (AttributeError, KeyError, TypeError, ValueError) as exc:  # not the shape we expect
        raise NominatimError(f"Nominatim sent an answer we could not read: {exc!r}") from exc


def _best_place(results: list) -> NominatimPlace | None:
    if not results:
        return None
    best = results[0]
    region = best.get("address", {}).get("ISO3166-2-lvl4", "")
    return NominatimPlace(lat=float(best["lat"]), lon=float(best["lon"]), region=region)
