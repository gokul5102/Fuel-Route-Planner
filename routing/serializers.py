"""The query parameters and the JSON body of GET /api/route/."""

from rest_framework import serializers

from routing.services.locations import COORDINATES, ResolvedLocation
from routing.services.planner import PlannedStop, TripPlan, Vehicle


class RouteQuerySerializer(serializers.Serializer):
    """`start` and `finish` are required and non-blank (surrounding spaces are trimmed).

    A value written as "lat,lng" must be a real coordinate pair.
    """

    start = serializers.CharField(max_length=200)
    finish = serializers.CharField(max_length=200)

    def validate_start(self, value: str) -> str:
        return _valid_coordinates_if_given(value)

    def validate_finish(self, value: str) -> str:
        return _valid_coordinates_if_given(value)


def _valid_coordinates_if_given(value: str) -> str:
    match = COORDINATES.match(value)
    if match and not (-90 <= float(match[1]) <= 90 and -180 <= float(match[2]) <= 180):
        raise serializers.ValidationError(
            "Coordinates must be latitude -90..90 and longitude -180..180."
        )
    return value


def serialize_trip_plan(trip: TripPlan) -> dict:
    plan = trip.plan
    return {
        "start": _location(trip.start),
        "finish": _location(trip.finish),
        "route": {
            "distance_miles": round(plan.route.distance_miles, 2),
            "duration_hours": round(plan.route.duration_hours, 2),
        },
        "fuel_stops": [_fuel_stop(stop) for stop in plan.stops],
        "total_gallons": round(plan.total_gallons, 3),
        "total_fuel_cost": float(plan.total_cost),
        "assumptions": _assumptions(trip.vehicle),
    }


def _location(location: ResolvedLocation) -> dict:
    return {
        "query": location.query,
        "lat": location.lat,
        "lon": location.lon,
        "resolved_by": location.resolved_by,
    }


def _fuel_stop(stop: PlannedStop) -> dict:
    station = stop.station
    return {
        "station_id": station.opis_id,
        "name": station.name,
        "address": station.address,
        "city": station.city,
        "state": station.state,
        "lat": station.lat,
        "lon": station.lon,
        "price_per_gallon": float(station.price),
        "mile_marker": round(stop.mile_marker, 1),
        "gallons": round(stop.gallons, 3),
        "cost": float(stop.cost),
    }


def _assumptions(vehicle: Vehicle) -> dict:
    return {
        "range_miles": vehicle.range_miles,
        "mpg": vehicle.mpg,
        "tank_gallons": vehicle.tank_gallons,
        "starting_fuel": "empty",
        "reserve_miles": vehicle.reserve_miles,
        "corridor_miles": vehicle.corridor_miles,
        "start_zone_miles": vehicle.corridor_miles,
        "station_locations": "city-level; the detour to reach a Station is ignored",
    }
