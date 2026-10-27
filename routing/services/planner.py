"""Plan a trip: resolve -> route -> corridor -> optimize -> choose the cheapest Route.

`plan_trip` is the whole request flow; each step is a small service of its own.
"""

from dataclasses import dataclass
from decimal import Decimal

from django.conf import settings

from routing.services.corridor import stations_in_corridor
from routing.services.locations import ResolvedLocation, check_distinct, resolve_location
from routing.services.optimizer import CandidateStation, FuelPlanError, plan_fuel_stops
from routing.services.osrm import RoutedPath, fetch_routes
from routing.services.request_metrics import stage
from routing.services.station_index import IndexedStation, StationIndex, get_station_index

TIE_CENTS = Decimal("0.01")  # Routes whose fuel costs differ by at most this are a tie


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
    on_route: bool  # False when the truck is assumed to start at this off-Route Station


@dataclass(frozen=True)
class RoutePlan:
    """The cheapest Fuel stops along one Route."""

    route: RoutedPath
    stops: list[PlannedStop]
    total_gallons: float
    total_cost: Decimal


@dataclass(frozen=True)
class RouteOption:
    """One Route OSRM offered: its fuel plan, or the reason it cannot be fuelled."""

    route: RoutedPath
    plan: RoutePlan | None
    failure: FuelPlanError | None = None


@dataclass(frozen=True)
class TripPlan:
    start: ResolvedLocation
    finish: ResolvedLocation
    plan: RoutePlan  # the chosen Route's plan
    vehicle: Vehicle
    alternatives: list[RoutePlan]  # the other Routes that can be fuelled, in OSRM's order


def plan_trip(start_query: str, finish_query: str) -> TripPlan:
    vehicle = Vehicle.from_settings()
    with stage("geocode"):
        start = resolve_location(start_query)
        finish = resolve_location(finish_query)
    check_distinct(start, finish)
    with stage("routing"):
        routes = fetch_routes((start.lat, start.lon), (finish.lat, finish.lon))
    plan, alternatives = choose_cheapest_route(routes, get_station_index(), vehicle)
    return TripPlan(start, finish, plan, vehicle, alternatives)


def choose_cheapest_route(
    routes: list[RoutedPath], index: StationIndex, vehicle: Vehicle
) -> tuple[RoutePlan, list[RoutePlan]]:
    """Plan every Route OSRM offered; the one with the cheapest fuel wins.

    Fuel costs within TIE_CENTS of the cheapest count as a tie, and the faster Route wins it.
    Routes that cannot be fuelled are dropped; if none can, raises the fastest Route's failure.
    Returns the winner's plan and the other fuelled Routes' plans (the alternatives).
    """
    options = [_plan_option(route, index, vehicle) for route in routes]
    fuelled = [option for option in options if option.plan is not None]
    if not fuelled:
        raise _fastest(options).failure
    cheapest = min(option.plan.total_cost for option in fuelled)
    winner = _fastest([o for o in fuelled if o.plan.total_cost - cheapest <= TIE_CENTS])
    return winner.plan, [option.plan for option in fuelled if option is not winner]


def _fastest(options: list[RouteOption]) -> RouteOption:
    return min(options, key=lambda option: option.route.duration_hours)


def _plan_option(route: RoutedPath, index: StationIndex, vehicle: Vehicle) -> RouteOption:
    try:
        return RouteOption(route, plan_route(route, index, vehicle))
    except FuelPlanError as failure:
        return RouteOption(route, plan=None, failure=failure)


def plan_route(route: RoutedPath, index: StationIndex, vehicle: Vehicle) -> RoutePlan:
    """Corridor matching then the fuel optimizer, for one Route.

    Raises the optimizer's FuelPlanError when the Route cannot be fuelled.
    """
    with stage("corridor"):
        matches = stations_in_corridor(
            route.points,
            index,
            corridor_miles=vehicle.corridor_miles,
            route_miles=route.distance_miles,
            start_at_nearest_station=True,  # the tank starts empty
        )
    by_id = {match.station.opis_id: match for match in matches}
    with stage("optimize"):
        fuel_plan = plan_fuel_stops(
            route.distance_miles,
            [CandidateStation(m.station.opis_id, m.mile_marker, m.station.price) for m in matches],
            range_miles=vehicle.range_miles,
            mpg=vehicle.mpg,
            reserve_miles=vehicle.reserve_miles,
        )
    stops = [
        PlannedStop(
            station=by_id[stop.station_id].station,
            mile_marker=stop.mile_marker,
            gallons=stop.gallons,
            cost=stop.cost,
            on_route=by_id[stop.station_id].on_route,
        )
        for stop in fuel_plan.stops
    ]
    return RoutePlan(route, stops, fuel_plan.total_gallons, fuel_plan.total_cost)
