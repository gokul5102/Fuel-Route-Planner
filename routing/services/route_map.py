"""The plan as a GeoJSON FeatureCollection (RFC 7946: coordinates are [lon, lat]).

Features, each with a `kind` property:
- "route": one LineString per Route; `chosen` is true for the cheapest, false for the alternatives;
- "start" and "finish": a Point each;
- "fuel_stop": a Point per Fuel stop, `number`ed from 1 in driving order.
"""

import numpy as np

from routing.services.locations import ResolvedLocation
from routing.services.osrm import RoutedPath
from routing.services.planner import TripPlan

COORDINATE_DECIMALS = 5  # about 1 metre: plenty for drawing a line
# A drawn Route line may stray this far from OSRM's road geometry. Fuel planning always uses
# the full geometry; only the map is simplified, so the response stays small.
DISPLAY_TOLERANCE_MILES = 0.05  # about 80 metres, under a pixel at zoom 10
MILES_PER_DEGREE_LATITUDE = 69.09


def trip_geojson(trip: TripPlan, route_summaries: list[dict], fuel_stops: list[dict]) -> dict:
    """The map of a plan, built around the dicts the JSON body already shows.

    `route_summaries` are the chosen Route's summary then the alternatives' (in
    `trip.alternatives` order); `fuel_stops` are the body's Fuel stops. Reusing them keeps
    the map's properties identical to the body.
    """
    routes = [trip.plan.route] + [other.route for other in trip.alternatives]
    lines = [
        _route_line(route, summary, chosen=number == 0)
        for number, (route, summary) in enumerate(zip(routes, route_summaries, strict=True))
    ]
    stops = [_fuel_stop_point(number, stop) for number, stop in enumerate(fuel_stops, 1)]
    return {
        "type": "FeatureCollection",
        "features": [
            *lines,
            _location_point("start", trip.start),
            _location_point("finish", trip.finish),
            *stops,
        ],
    }


def _feature(geometry: dict, properties: dict) -> dict:
    return {"type": "Feature", "geometry": geometry, "properties": properties}


def _route_line(route: RoutedPath, summary: dict, chosen: bool) -> dict:
    coordinates = [
        [round(lon, COORDINATE_DECIMALS), round(lat, COORDINATE_DECIMALS)]
        for lat, lon in simplify(route.points, DISPLAY_TOLERANCE_MILES)
    ]
    return _feature(
        {"type": "LineString", "coordinates": coordinates},
        {"kind": "route", "chosen": chosen, **summary},
    )


def _location_point(kind: str, location: ResolvedLocation) -> dict:
    return _feature(
        {"type": "Point", "coordinates": [location.lon, location.lat]},
        {"kind": kind, "query": location.query},
    )


def _fuel_stop_point(number: int, stop: dict) -> dict:
    """A body Fuel stop as a Point; its lat and lon go in the geometry, not the properties."""
    details = {field: value for field, value in stop.items() if field not in ("lat", "lon")}
    return _feature(
        {"type": "Point", "coordinates": [stop["lon"], stop["lat"]]},
        {"kind": "fuel_stop", "number": number, **details},
    )


def simplify(
    points: list[tuple[float, float]], tolerance_miles: float
) -> list[tuple[float, float]]:
    """Douglas-Peucker: drop the points that lie within `tolerance_miles` of the line kept.

    Start with the two ends; while some point between two kept points is farther than the
    tolerance from the straight line joining them, keep the farthest one and split there.
    Distances use a flat projection (miles east and north), which is fine at this scale.
    """
    if len(points) < 3:
        return list(points)
    lat_lon = np.asarray(points, dtype=float)
    mean_lat = np.radians(lat_lon[:, 0].mean())
    xy = (
        np.column_stack((lat_lon[:, 1] * np.cos(mean_lat), lat_lon[:, 0]))
        * MILES_PER_DEGREE_LATITUDE
    )
    keep = np.zeros(len(points), dtype=bool)
    keep[[0, -1]] = True
    pending = [(0, len(points) - 1)]
    while pending:
        first, last = pending.pop()
        if last - first < 2:
            continue
        distances = _distances_to_segment(xy[first + 1 : last], xy[first], xy[last])
        farthest = int(distances.argmax())
        if distances[farthest] > tolerance_miles:
            middle = first + 1 + farthest
            keep[middle] = True
            pending += [(first, middle), (middle, last)]
    return [points[i] for i in np.flatnonzero(keep)]


def _distances_to_segment(xy: np.ndarray, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Distance from each point to the segment a-b."""
    ab = b - a
    length_squared = float(ab @ ab)
    if length_squared == 0:
        return np.linalg.norm(xy - a, axis=1)
    t = np.clip((xy - a) @ ab / length_squared, 0, 1)
    return np.linalg.norm(xy - (a + t[:, None] * ab), axis=1)
