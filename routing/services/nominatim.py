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
_next_turn = 0.0  # monotonic time from which this process may send its next request
_pacing_lock = threading.Lock()


def _wait_for_turn() -> None:
    """Take the next free one-second slot and sleep until it comes.

    Concurrent callers get slots one second apart. A slot further away than
    HTTP_TIMEOUT_SECONDS is refused (a Timeout), so a queue never makes a request wait
    longer than the timeout promises.
    """
    global _next_turn
    with _pacing_lock:
        now = monotonic()
        turn = max(now, _next_turn)
        if turn - now > settings.HTTP_TIMEOUT_SECONDS:
            raise NominatimError("Too many geocoding requests queued") from requests.Timeout()
        _next_turn = turn + MIN_INTERVAL_SECONDS
    if turn > now:
        sleep(turn - now)


def search(query: str, country_code: str = "us") -> NominatimPlace | None:
    """Return the best match for `query` within one country, or None if nothing matches."""
    _wait_for_turn()  # may raise NominatimError (a Timeout) when the queue is too long
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
