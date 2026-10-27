"""The plan as a GeoJSON FeatureCollection (RFC 7946: coordinates are [lon, lat]).

Features, each with a `kind` property:
- "route": one LineString per Route; `chosen` is true for the cheapest, false for the alternatives;
- "start" and "finish": a Point each;
- "fuel_stop": a Point per Fuel stop, `number`ed from 1 in driving order.
"""

from routing.services.locations import ResolvedLocation
from routing.services.osrm import RoutedPath
from routing.services.planner import PlannedStop, RoutePlan, TripPlan

COORDINATE_DECIMALS = 5  # about 1 metre: plenty for drawing a line


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
        for lat, lon in route.points
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
