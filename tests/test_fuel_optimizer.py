"""The fuel optimizer picks the cheapest Fuel stops for one Route.

Hand-built cases with a 500-mile Range at 10 MPG and an empty tank at the start.
"""

from decimal import Decimal

import pytest

from routing.services.optimizer import (
    CandidateStation,
    NoStationAtStart,
    Unreachable,
    plan_fuel_stops,
)


def station(station_id: int, mile_marker: float, price: str) -> CandidateStation:
    return CandidateStation(station_id=station_id, mile_marker=mile_marker, price=Decimal(price))


def plan(distance: float, *stations: CandidateStation):
    return plan_fuel_stops(distance, list(stations), range_miles=500, mpg=10)


def summary(result) -> list[tuple[int, float, Decimal]]:
    return [(s.station_id, round(s.gallons, 6), s.cost) for s in result.stops]


def test_buys_just_enough_to_reach_a_cheaper_station_ahead():
    result = plan(300, station(1, 0, "4.00"), station(2, 100, "3.00"))

    # 100 mi to the cheaper Station (10 gal at $4), then 200 mi to the end (20 gal at $3).
    assert summary(result) == [(1, 10.0, Decimal("40.00")), (2, 20.0, Decimal("60.00"))]
    assert result.total_gallons == 30
    assert result.total_cost == Decimal("100.00")


def test_fills_up_and_jumps_to_the_cheapest_station_in_range():
    result = plan(
        900,
        station(1, 0, "3.00"),
        station(2, 300, "3.80"),
        station(3, 450, "3.50"),
        station(4, 800, "3.10"),
    )

    # Nothing cheaper than $3.00 in Range: fill 50 gal, go to the cheapest in Range ($3.50 at 450),
    # arrive with 50 mi left, buy 300 mi more to reach the cheaper Station at 800, then 100 mi.
    assert summary(result) == [
        (1, 50.0, Decimal("150.00")),
        (3, 30.0, Decimal("105.00")),
        (4, 10.0, Decimal("31.00")),
    ]
    assert result.total_gallons == 90
    assert result.total_cost == Decimal("286.00")


def test_a_gap_of_exactly_the_range_is_reachable():
    result = plan(1000, station(1, 0, "3.00"), station(2, 500, "3.00"))

    assert summary(result) == [(1, 50.0, Decimal("150.00")), (2, 50.0, Decimal("150.00"))]


def test_a_gap_longer_than_the_range_is_unreachable_at_the_mile_marker_where_fuel_runs_out():
    with pytest.raises(Unreachable) as failure:
        plan(1200, station(1, 0, "3.00"), station(2, 100, "3.00"), station(3, 601, "3.00"))

    assert failure.value.code == "UNREACHABLE"
    assert failure.value.mile_marker == 600


def test_no_station_at_the_start_means_an_empty_tank_cannot_leave():
    with pytest.raises(NoStationAtStart) as failure:
        plan(300, station(1, 5, "3.00"))

    assert failure.value.code == "NO_STATION_AT_START"


def test_a_trip_shorter_than_the_start_zone_buys_only_what_it_needs():
    result = plan(5, station(1, 0, "3.333"))

    assert summary(result) == [(1, 0.5, Decimal("1.67"))]
    assert result.total_cost == Decimal("1.67")


def test_the_cheapest_of_several_stations_at_mile_marker_zero_is_used():
    result = plan(100, station(1, 0, "3.50"), station(2, 0, "3.20"), station(3, 0, "3.90"))

    assert summary(result) == [(2, 10.0, Decimal("32.00"))]


def test_price_ties_at_one_mile_marker_go_to_the_lower_opis_id():
    result = plan(100, station(9, 0, "3.20"), station(4, 0, "3.20"))

    assert summary(result) == [(4, 10.0, Decimal("32.00"))]


def test_a_destination_within_range_is_reached_without_overbuying():
    result = plan(450, station(1, 0, "3.00"), station(2, 200, "3.50"))

    assert summary(result) == [(1, 45.0, Decimal("135.00"))]
    assert result.total_gallons == 45


def test_costs_are_rounded_per_stop_and_the_total_is_their_sum():
    # 1/3 of the trip at each price: 3.3333... gal per stop.
    result = plan(
        100, station(1, 0, "3.005"), station(2, 33.3333, "3.004"), station(3, 66.6667, "2.5")
    )

    costs = [s.cost for s in result.stops]
    assert all(c == c.quantize(Decimal("0.01")) for c in costs)
    assert result.total_cost == sum(costs)
    assert result.total_gallons == pytest.approx(10)


def test_price_ties_between_stations_ahead_still_give_the_cheapest_total():
    result = plan(900, station(1, 0, "3.00"), station(3, 450, "3.00"), station(2, 400, "3.00"))

    # Nothing strictly cheaper ahead: fill up, then drive to the cheapest in Range; the tie
    # goes to the lower OPIS ID (Station 2 at 400), from where the destination is in Range.
    assert summary(result) == [(1, 50.0, Decimal("150.00")), (2, 40.0, Decimal("120.00"))]
    assert result.total_cost == Decimal("270.00")
