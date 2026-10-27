"""The greedy fuel optimizer is truly cheapest: it matches an exhaustive search.

The oracle below knows nothing about the greedy rules. It tries every amount of fuel
(in 0.1-gallon steps, i.e. 1 mile at 10 MPG) at every Station and keeps, for each
possible tank level, the cheapest way to get there. Mile markers are whole miles, so
every tank level the trip can reach lies on that grid and the search is exact.
"""

import json
import math
import random
from decimal import Decimal
from pathlib import Path

import numpy as np
import pytest
from django.conf import settings

from routing.services.corridor import stations_in_corridor
from routing.services.optimizer import CandidateStation, FuelPlanError, plan_fuel_stops
from routing.services.osrm import METERS_PER_MILE
from routing.services.station_index import IndexedStation, StationIndex
from routing.services.stations import clean_stations, read_city_coords, read_price_file

OSRM_FIXTURE = Path(__file__).parent / "fixtures" / "osrm_chicago_los_angeles.json"

RANGE_MILES, MPG = 500, 10
STEP_MILES = 1  # 0.1 gallon at 10 MPG


def cheapest_by_exhaustive_search(distance: int, stations: list[CandidateStation]) -> float:
    """The lowest possible fuel cost, or infinity if the trip can't be fuelled.

    `cost[f]` is the cheapest way to be at the current Mile marker with `f` miles of fuel.
    At a Station, the tank can be raised from any level f to any higher level g; buying
    costs (g - f) * price per mile. Driving d miles shifts every level down by d.
    """
    levels = RANGE_MILES // STEP_MILES + 1
    cost = np.full(levels, math.inf)
    cost[0] = 0.0  # empty tank at Mile marker 0
    position = 0
    for station in sorted(stations, key=lambda s: s.mile_marker):
        if station.mile_marker >= distance:
            break
        cost = _drive(cost, int(station.mile_marker) - position)
        position = int(station.mile_marker)
        price_per_step = float(station.price) * STEP_MILES / MPG
        for level in range(1, levels):  # every purchase: one more step from the level below
            cost[level] = min(cost[level], cost[level - 1] + price_per_step)
    return float(_drive(cost, distance - position).min())


def _drive(cost: np.ndarray, miles: int) -> np.ndarray:
    """Tank levels after driving `miles`; levels that would run dry become impossible."""
    steps = miles // STEP_MILES
    after = np.full_like(cost, math.inf)
    if steps < len(cost):
        after[: len(cost) - steps] = cost[steps:]
    return after


def greedy(distance: float, stations: list[CandidateStation]) -> tuple[float, int]:
    """The greedy total cost and its number of Fuel stops (infinity, 0 if it can't be fuelled)."""
    try:
        plan = plan_fuel_stops(distance, stations, range_miles=RANGE_MILES, mpg=MPG)
    except FuelPlanError:
        return math.inf, 0
    return float(plan.total_cost), len(plan.stops)


def random_scenario(rng: random.Random) -> tuple[int, list[CandidateStation]]:
    distance = rng.randint(5, 2500)
    count = rng.randint(1, 40)
    markers = [0] * rng.randint(0, 3) + [rng.randrange(0, distance) for _ in range(count)]
    stations = [
        CandidateStation(
            station_id=station_id,
            mile_marker=marker,
            price=Decimal(rng.randint(2800, 5200)) / 1000,
        )
        for station_id, marker in enumerate(markers, start=1)
    ]
    return distance, stations


def rounding_allowance(stops: int) -> float:
    """The greedy rounds each Fuel stop to the cent: at most half a cent per stop."""
    return 0.005 * stops + 1e-6


def test_the_oracle_agrees_with_a_worked_example():
    # 100 mi at $4.00 then 200 mi at $3.00: 10 gal * 4 + 20 gal * 3.
    stations = [
        CandidateStation(1, 0, Decimal("4.00")),
        CandidateStation(2, 100, Decimal("3.00")),
    ]
    assert cheapest_by_exhaustive_search(300, stations) == pytest.approx(100.0)


def test_greedy_matches_exhaustive_search_on_200_random_scenarios():
    rng = random.Random(2026_10_27)
    worst, feasible = 0.0, 0
    for _ in range(200):
        distance, stations = random_scenario(rng)
        best = cheapest_by_exhaustive_search(distance, stations)
        cost, stops = greedy(distance, stations)

        if math.isinf(best):
            assert math.isinf(cost), (distance, stations)
            continue
        feasible += 1
        assert abs(cost - best) <= rounding_allowance(stops), (distance, stations)
        worst = max(worst, abs(cost - best))

    assert feasible >= 100  # most scenarios can be fuelled, so the check has teeth
    print(f"\n{feasible} feasible scenarios, max |greedy - exhaustive| = ${worst:.4f}")


@pytest.fixture(scope="module")
def chicago_to_los_angeles() -> tuple[float, list[CandidateStation]]:
    """The real recorded Route and every real Station in its Corridor (no database needed)."""
    cleaned = clean_stations(
        read_price_file(settings.PRICE_FILE), read_city_coords(settings.CITY_COORDS_FILE)
    )
    index = StationIndex.build(
        [
            IndexedStation(
                s.opis_id, s.name, s.address, s.city, s.state, s.price_per_gallon, s.lat, s.lon
            )
            for s in cleaned.stations
        ]
    )
    route = json.loads(OSRM_FIXTURE.read_text())["routes"][0]
    distance = route["distance"] / METERS_PER_MILE
    points = [(lat, lon) for lon, lat in route["geometry"]["coordinates"]]
    on_route = stations_in_corridor(points, index, corridor_miles=8, route_miles=distance)
    return distance, [
        CandidateStation(m.station.opis_id, m.mile_marker, m.station.price) for m in on_route
    ]


def test_greedy_plans_the_real_chicago_to_los_angeles_trip_at_the_known_cost(
    chicago_to_los_angeles,
):
    distance, stations = chicago_to_los_angeles

    plan = plan_fuel_stops(distance, stations, range_miles=RANGE_MILES, mpg=MPG)

    assert plan.total_cost == Decimal("612.22")  # $612.24 before Mile marker scaling
    assert len(plan.stops) == 18


def test_greedy_matches_exhaustive_search_on_the_real_chicago_to_los_angeles_trip(
    chicago_to_los_angeles,
):
    distance, stations = chicago_to_los_angeles
    # The oracle needs whole-mile Mile markers; both solvers get the same rounded trip.
    whole_miles = [CandidateStation(s.station_id, round(s.mile_marker), s.price) for s in stations]
    trip = round(distance)

    best = cheapest_by_exhaustive_search(trip, whole_miles)
    cost, stops = greedy(trip, whole_miles)

    assert not math.isinf(best)
    assert abs(cost - best) <= rounding_allowance(stops)
