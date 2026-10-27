"""Corridor matching: which Stations are on the Route, and at which Mile marker.

1. Resample the Route to about one point per mile, with each point's cumulative miles.
2. A Station is on the Route if it is within `corridor_miles` of any sample point.
3. Its Mile marker is the cumulative miles of its nearest sample point (the detour is
   ignored), scaled so the finish sits at the Route distance OSRM reported: the line
   measured from the geometry is slightly shorter than the road, and the totals use
   OSRM's figure. Stations in the Start zone (the first `start_zone_miles`) are at
   Mile marker 0.
4. The tank starts empty, so with no Station in the Start zone the Station nearest the
   start, if within `start_station_miles`, is put at Mile marker 0: the trip fills up
   there first (its detour is ignored, like every other).
"""

from dataclasses import dataclass

import numpy as np
from scipy.spatial import cKDTree

from routing.services.geo import chord_to_miles, unit_vectors
from routing.services.station_index import IndexedStation, StationIndex

LatLon = tuple[float, float]


@dataclass(frozen=True)
class CorridorStation:
    station: IndexedStation
    mile_marker: float


def resample(route: list[LatLon], step_miles: float = 1.0) -> tuple[np.ndarray, np.ndarray]:
    """Points every `step_miles` along the Route (plus the finish), and their cumulative miles."""
    vertices = np.asarray(route, dtype=float)
    segment_miles = chord_to_miles(np.linalg.norm(np.diff(unit_vectors(vertices), axis=0), axis=1))
    cumulative = np.concatenate([[0.0], np.cumsum(segment_miles)])
    miles = np.append(np.arange(0, cumulative[-1], step_miles), cumulative[-1])
    lat = np.interp(miles, cumulative, vertices[:, 0])
    lon = np.interp(miles, cumulative, vertices[:, 1])
    return np.column_stack([lat, lon]), miles


def stations_in_corridor(
    route: list[LatLon],
    index: StationIndex,
    *,
    corridor_miles: float,
    start_zone_miles: float | None = None,
    route_miles: float | None = None,
    start_station_miles: float = 0,
) -> list[CorridorStation]:
    """The Stations within the Corridor, ordered by Mile marker.

    `route_miles` is the Route distance to scale Mile markers to (default: the measured line).
    `start_station_miles` is how far from the start a Station may be to stand in for an
    empty Start zone (0: never).
    """
    start_zone = corridor_miles if start_zone_miles is None else start_zone_miles
    samples, sample_miles = resample(route)
    if route_miles is not None and sample_miles[-1] > 0:
        sample_miles = sample_miles * (route_miles / sample_miles[-1])
    sample_points = unit_vectors(samples)
    matches = []
    if rows := index.near(sample_points, corridor_miles):
        stations = [index.stations[row] for row in rows]
        station_points = unit_vectors(np.array([(s.lat, s.lon) for s in stations]))
        _, nearest_sample = cKDTree(sample_points).query(station_points)
        for station, sample in zip(stations, nearest_sample, strict=True):
            mile_marker = float(sample_miles[sample])
            at = 0.0 if mile_marker <= start_zone else mile_marker
            matches.append(CorridorStation(station, at))

    empty_start_zone = not any(match.mile_marker == 0 for match in matches)
    if empty_start_zone and (first := index.nearest(sample_points[0], start_station_miles)):
        matches = [m for m in matches if m.station.opis_id != first.opis_id]
        matches.append(CorridorStation(first, 0.0))
    return sorted(matches, key=lambda m: (m.mile_marker, m.station.opis_id))
