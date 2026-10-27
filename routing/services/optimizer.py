"""The fuel optimizer: the cheapest Fuel stops along one Route (a pure function).

The vehicle starts with an empty tank at Mile marker 0 and may arrive anywhere
with an empty tank (the Reserve is 0 by default). Greedy, at each Station:

- if a cheaper Station is within Range, buy just enough fuel to reach it;
- otherwise, if the destination is within Range, buy just enough to get there;
- otherwise fill the tank and drive to the cheapest Station within Range.

This is the classic optimal strategy for linear prices with partial fills:
fuel is always bought at the cheapest price that can still carry it.
Fuel is tracked in miles of driving; gallons = miles / MPG.
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")


@dataclass(frozen=True)
class CandidateStation:
    """A Station in the Corridor, as the optimizer sees it."""

    station_id: int
    mile_marker: float
    price: Decimal


@dataclass(frozen=True)
class FuelStop:
    station_id: int
    mile_marker: float
    price: Decimal
    gallons: float
    cost: Decimal  # rounded to cents


@dataclass(frozen=True)
class FuelPlan:
    stops: list[FuelStop]
    total_gallons: float  # = Route distance / MPG
    total_cost: Decimal  # = sum of the rounded stop costs


class FuelPlanError(Exception):
    """The trip cannot be fuelled. `code` is the API error code; `details` explains it."""

    code = "FUEL_PLAN_ERROR"

    @property
    def details(self) -> dict:
        return {}


class NoStationAtStart(FuelPlanError):
    code = "NO_STATION_AT_START"

    def __init__(self) -> None:
        super().__init__("No Station to start from, so an empty tank cannot leave.")


class Unreachable(FuelPlanError):
    code = "UNREACHABLE"

    def __init__(self, mile_marker: float) -> None:
        self.mile_marker = mile_marker
        super().__init__(f"The vehicle would run out of fuel at Mile marker {mile_marker:.1f}.")

    @property
    def details(self) -> dict:
        return {"mile_marker": round(self.mile_marker, 1)}


def plan_fuel_stops(
    distance_miles: float,
    stations: list[CandidateStation],
    *,
    range_miles: float,
    mpg: float,
    reserve_miles: float = 0,
) -> FuelPlan:
    """Return the cheapest Fuel stops, or raise NoStationAtStart / Unreachable."""
    if distance_miles <= 0:  # start and finish snapped to the same spot: nothing to drive
        return FuelPlan(stops=[], total_gallons=0.0, total_cost=Decimal("0.00"))
    usable_range = range_miles - reserve_miles
    stops_by_marker = _cheapest_per_mile_marker(stations, distance_miles)
    if not stops_by_marker or stops_by_marker[0].mile_marker != 0:
        raise NoStationAtStart()

    purchases: list[tuple[CandidateStation, float]] = []  # (Station, miles of fuel bought)
    here, fuel = 0, 0.0  # index into stops_by_marker, miles of fuel in the tank
    while True:
        current = stops_by_marker[here]
        in_range = [
            i
            for i in range(here + 1, len(stops_by_marker))
            if stops_by_marker[i].mile_marker - current.mile_marker <= usable_range
        ]
        cheaper = next((i for i in in_range if stops_by_marker[i].price < current.price), None)
        to_destination = distance_miles - current.mile_marker

        if cheaper is not None:
            target, need = cheaper, stops_by_marker[cheaper].mile_marker - current.mile_marker
        elif to_destination <= usable_range:
            target, need = None, to_destination
        elif in_range:
            target = min(
                in_range, key=lambda i: (stops_by_marker[i].price, stops_by_marker[i].station_id)
            )
            need = usable_range  # fill the tank
        else:
            raise Unreachable(current.mile_marker + usable_range)

        if need > fuel:
            purchases.append((current, need - fuel))
            fuel = need
        if target is None:
            break
        fuel -= stops_by_marker[target].mile_marker - current.mile_marker
        here = target

    stops = [_fuel_stop(station, miles / mpg) for station, miles in purchases]
    return FuelPlan(
        stops=stops,
        total_gallons=distance_miles / mpg,
        total_cost=sum((stop.cost for stop in stops), Decimal("0.00")),
    )


def _cheapest_per_mile_marker(
    stations: list[CandidateStation], distance_miles: float
) -> list[CandidateStation]:
    """One Station per Mile marker before the destination: the cheapest, then the lowest ID."""
    cheapest: dict[float, CandidateStation] = {}
    for station in sorted(stations, key=lambda s: (s.price, s.station_id)):
        if station.mile_marker < distance_miles:
            cheapest.setdefault(station.mile_marker, station)
    return sorted(cheapest.values(), key=lambda s: s.mile_marker)


def _fuel_stop(station: CandidateStation, gallons: float) -> FuelStop:
    cost = (Decimal(repr(gallons)) * station.price).quantize(CENT, rounding=ROUND_HALF_UP)
    return FuelStop(station.station_id, station.mile_marker, station.price, gallons, cost)
