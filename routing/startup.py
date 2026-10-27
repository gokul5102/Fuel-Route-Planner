"""Work done once when the server starts, so the first request is as fast as the rest."""

from django.conf import settings

from routing.services import http
from routing.services.places import get_place_index
from routing.services.station_index import warm_station_index


def warm_up() -> None:
    warm_station_index()  # one query, then every request uses the in-memory index
    get_place_index()  # the "City, ST" lookup (~0.1 s from data/us_places.csv)
    http.preconnect(f"{settings.OSRM_BASE_URL}/")  # TLS handshake now, not on the first request
