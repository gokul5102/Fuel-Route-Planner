"""The in-memory Station index: a KD-tree over every Station, built once per process.

One database query loads all Stations; their coordinates become 3D unit vectors in a
scipy cKDTree, and the Station details sit in a parallel tuple (row i of the tree is
`stations[i]`). Requests then find nearby Stations in milliseconds without touching
the database.
"""

import logging
import threading
from dataclasses import dataclass
from decimal import Decimal

import numpy as np
from scipy.spatial import cKDTree

from routing.services.geo import miles_to_chord, unit_vectors


@dataclass(frozen=True)
class IndexedStation:
    opis_id: int
    name: str
    address: str
    city: str
    state: str
    price: Decimal
    lat: float
    lon: float


class StationIndex:
    def __init__(self, stations: tuple[IndexedStation, ...], tree: cKDTree | None) -> None:
        self.stations = stations
        self._tree = tree

    @classmethod
    def build(cls, stations: list[IndexedStation]) -> "StationIndex":
        if not stations:
            return cls((), None)
        points = unit_vectors(np.array([(s.lat, s.lon) for s in stations]))
        return cls(tuple(stations), cKDTree(points))

    @classmethod
    def from_database(cls) -> "StationIndex":
        from routing.models import Station

        rows = Station.objects.values_list(
            "opis_id", "name", "address", "city", "state", "price_per_gallon", "lat", "lon"
        )
        return cls.build([IndexedStation(*row) for row in rows])

    def near(self, points: np.ndarray, radius_miles: float) -> list[int]:
        """Rows of the Stations within `radius_miles` of any of the unit-vector `points`."""
        if self._tree is None or len(points) == 0:
            return []
        hits = self._tree.query_ball_point(points, miles_to_chord(radius_miles))
        return sorted({row for rows in hits for row in rows})


logger = logging.getLogger(__name__)

_index: StationIndex | None = None
_lock = threading.Lock()


def get_station_index() -> StationIndex:
    """The shared index, built from the Station table on first use."""
    global _index
    if _index is None:
        with _lock:
            if _index is None:
                _index = StationIndex.from_database()
    return _index


def reset_station_index() -> None:
    """Forget the shared index so the next use rebuilds it (after reloading Stations, in tests)."""
    global _index
    with _lock:
        _index = None


def warm_station_index() -> None:
    """Build the shared index at server startup, so the first request doesn't pay for it.

    If the database isn't ready yet (not migrated), log it and build on first use instead.
    """
    from django.db import DatabaseError

    try:
        stations = len(get_station_index().stations)
    except DatabaseError as error:
        logger.warning("Station index not built at startup (%s); run `make load`.", error)
    else:
        logger.info("Station index built: %d Stations.", stations)
