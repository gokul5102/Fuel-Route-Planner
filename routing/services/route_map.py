"""The plan as a GeoJSON FeatureCollection (RFC 7946: coordinates are [lon, lat]).

Features, each with a `kind` property:
- "route": one LineString per Route; `chosen` is true for the cheapest, false for the alternatives;
- "start" and "finish": a Point each;
- "fuel_stop": a Point per Fuel stop, `number`ed from 1 in driving order.
"""

import numpy as np

from routing.services.locations import ResolvedLocation
from routing.services.osrm import RoutedPath
from routing.services.planner import PlannedStop, RoutePlan, TripPlan

COORDINATE_DECIMALS = 5  # about 1 metre: plenty for drawing a line
# A drawn Route line may stray this far from OSRM's road geometry. Fuel planning always uses
# the full geometry; only the map is simplified, so the response stays small.
DISPLAY_TOLERANCE_MILES = 0.05  # about 80 metres, under a pixel at zoom 10
MILES_PER_DEGREE_LATITUDE = 69.09


def trip_geojson(trip: TripPlan) -> dict:
    routes = [_route_line(trip.plan.route, trip.plan, chosen=True, failure_code=None)] + [
        _route_line(
            option.route,
            option.plan,
            chosen=False,
            failure_code=option.failure.code if option.failure else None,
        )
        for option in trip.alternatives
    ]
    stops = [_fuel_stop_point(number, stop) for number, stop in enumerate(trip.plan.stops, 1)]
    return {
        "type": "FeatureCollection",
        "features": [
            *routes,
            _location_point("start", trip.start),
            _location_point("finish", trip.finish),
            *stops,
        ],
    }


def _feature(geometry: dict, properties: dict) -> dict:
    return {"type": "Feature", "geometry": geometry, "properties": properties}


def _route_line(
    route: RoutedPath, plan: RoutePlan | None, chosen: bool, failure_code: str | None
) -> dict:
    coordinates = [
        [round(lon, COORDINATE_DECIMALS), round(lat, COORDINATE_DECIMALS)]
        for lat, lon in simplify(route.points, DISPLAY_TOLERANCE_MILES)
    ]
    return _feature(
        {"type": "LineString", "coordinates": coordinates},
        {
            "kind": "route",
            "chosen": chosen,
            "distance_miles": round(route.distance_miles, 2),
            "duration_hours": round(route.duration_hours, 2),
            "total_fuel_cost": float(plan.total_cost) if plan else None,
            "failure_code": failure_code,
        },
    )


def _location_point(kind: str, location: ResolvedLocation) -> dict:
    return _feature(
        {"type": "Point", "coordinates": [location.lon, location.lat]},
        {"kind": kind, "query": location.query},
    )


def _fuel_stop_point(number: int, stop: PlannedStop) -> dict:
    station = stop.station
    return _feature(
        {"type": "Point", "coordinates": [station.lon, station.lat]},
        {
            "kind": "fuel_stop",
            "number": number,
            "station_id": station.opis_id,
            "name": station.name,
            "address": station.address,
            "city": station.city,
            "state": station.state,
            "price_per_gallon": float(station.price),
            "mile_marker": round(stop.mile_marker, 1),
            "gallons": round(stop.gallons, 3),
            "cost": float(stop.cost),
        },
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
