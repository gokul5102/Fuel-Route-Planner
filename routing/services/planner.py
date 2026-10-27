"""Plan a trip: resolve -> route -> corridor -> optimize.

`plan_trip` is the whole request flow; each step is a small service of its own.
"""

from dataclasses import dataclass
from decimal import Decimal

from django.conf import settings

from routing.services.corridor import stations_in_corridor
from routing.services.locations import ResolvedLocation, check_distinct, resolve_location
from routing.services.optimizer import CandidateStation, plan_fuel_stops
from routing.services.osrm import RoutedPath, fetch_routes
from routing.services.station_index import IndexedStation, StationIndex, get_station_index


@dataclass(frozen=True)
class Vehicle:
    """The planning assumptions, read from settings."""

    range_miles: float
    mpg: float
    reserve_miles: float
    corridor_miles: float

    @classmethod
    def from_settings(cls) -> "Vehicle":
        return cls(
            range_miles=settings.RANGE_MILES,
            mpg=settings.MPG,
            reserve_miles=settings.MIN_RESERVE_MILES,
            corridor_miles=settings.CORRIDOR_MILES,
        )

    @property
    def tank_gallons(self) -> float:
        return self.range_miles / self.mpg


@dataclass(frozen=True)
class PlannedStop:
    """A Fuel stop with its Station's details."""

    station: IndexedStation
    mile_marker: float
    gallons: float
    cost: Decimal


@dataclass(frozen=True)
class RoutePlan:
    """The cheapest Fuel stops along one Route."""

    route: RoutedPath
    stops: list[PlannedStop]
    total_gallons: float
    total_cost: Decimal


@dataclass(frozen=True)
class TripPlan:
    start: ResolvedLocation
    finish: ResolvedLocation
    plan: RoutePlan
    vehicle: Vehicle


def plan_trip(start_query: str, finish_query: str) -> TripPlan:
    vehicle = Vehicle.from_settings()
    start = resolve_location(start_query)
    finish = resolve_location(finish_query)
    check_distinct(start, finish)
    routes = fetch_routes((start.lat, start.lon), (finish.lat, finish.lon))
    plan = plan_route(routes[0], get_station_index(), vehicle)
    return TripPlan(start, finish, plan, vehicle)


def plan_route(route: RoutedPath, index: StationIndex, vehicle: Vehicle) -> RoutePlan:
    """Corridor matching then the fuel optimizer, for one Route.

    Raises the optimizer's FuelPlanError when the Route cannot be fuelled.
    """
    on_route = stations_in_corridor(route.points, index, corridor_miles=vehicle.corridor_miles)
    by_id = {match.station.opis_id: match.station for match in on_route}
    fuel_plan = plan_fuel_stops(
        route.distance_miles,
        [CandidateStation(m.station.opis_id, m.mile_marker, m.station.price) for m in on_route],
        range_miles=vehicle.range_miles,
        mpg=vehicle.mpg,
        reserve_miles=vehicle.reserve_miles,
    )
    stops = [
        PlannedStop(by_id[stop.station_id], stop.mile_marker, stop.gallons, stop.cost)
        for stop in fuel_plan.stops
    ]
    return RoutePlan(route, stops, fuel_plan.total_gallons, fuel_plan.total_cost)
