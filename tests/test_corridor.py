"""Corridor matching finds the Stations within 8 miles of a Route and gives each a Mile marker.

The synthetic Route runs 100 miles east along the equator, so "m miles along, d miles
off" is exact: longitude m/R radians and latitude d/R radians.
"""

import math
from decimal import Decimal

import pytest

from routing.models import Station
from routing.services.corridor import stations_in_corridor
from routing.services.station_index import (
    IndexedStation,
    StationIndex,
    get_station_index,
    reset_station_index,
)

EARTH_RADIUS_MILES = 3958.8


def degrees(miles: float) -> float:
    return math.degrees(miles / EARTH_RADIUS_MILES)


def along_and_off(opis_id: int, along: float, off: float) -> IndexedStation:
    return IndexedStation(
        opis_id=opis_id,
        name=f"Station {opis_id}",
        address="",
        city="",
        state="",
        price=Decimal("3.00"),
        lat=degrees(off),
        lon=degrees(along),
    )


STRAIGHT_ROUTE = [(0.0, 0.0), (0.0, degrees(100))]


def mile_markers(index: StationIndex) -> dict[int, float]:
    return {
        match.station.opis_id: match.mile_marker
        for match in stations_in_corridor(STRAIGHT_ROUTE, index, corridor_miles=8)
    }


def test_stations_up_to_8_miles_off_the_route_are_in_the_corridor():
    index = StationIndex.build(
        [along_and_off(1, 30, 1), along_and_off(2, 50, 7.9), along_and_off(3, 80, 8.1)]
    )

    assert mile_markers(index) == {1: pytest.approx(30, abs=0.01), 2: pytest.approx(50, abs=0.01)}


def test_stations_in_the_start_zone_are_at_mile_marker_zero():
    index = StationIndex.build(
        [along_and_off(1, 5, 1), along_and_off(2, 7.9, 3), along_and_off(3, 9, 1)]
    )

    assert mile_markers(index) == {1: 0, 2: 0, 3: pytest.approx(9, abs=0.01)}


def test_a_station_near_the_finish_gets_the_last_mile_marker():
    index = StationIndex.build([along_and_off(1, 100, 2), along_and_off(2, 104, 0)])

    assert mile_markers(index) == {1: pytest.approx(100, abs=0.01), 2: pytest.approx(100, abs=0.01)}


def test_an_empty_index_matches_nothing():
    assert mile_markers(StationIndex.build([])) == {}


@pytest.mark.django_db
def test_the_shared_index_is_built_from_the_station_table():
    Station.objects.create(
        opis_id=42,
        name="ON THE WAY",
        address="I-1, EXIT 30",
        city="Nowhere",
        state="ZZ",
        price_per_gallon=Decimal("3.12300000"),
        lat=degrees(1),
        lon=degrees(30),
        geocode_source="census",
    )
    reset_station_index()

    matches = stations_in_corridor(STRAIGHT_ROUTE, get_station_index(), corridor_miles=8)

    assert [(m.station.opis_id, m.station.price, m.station.name) for m in matches] == [
        (42, Decimal("3.12300000"), "ON THE WAY")
    ]


@pytest.mark.django_db
def test_an_empty_station_table_gives_an_empty_index():
    assert stations_in_corridor(STRAIGHT_ROUTE, get_station_index(), corridor_miles=8) == []
