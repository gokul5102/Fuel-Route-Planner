"""GET /api/route/ plans the cheapest Fuel stops for a trip given as coordinates.

OSRM is mocked with a real recorded Chicago -> Los Angeles response (2,018.03 miles,
35.36 hours). That Route runs I-80 -> Denver -> I-70 -> I-15 -> Las Vegas, and the Stations
below sit in cities on it. Their Mile markers on this Route (scaled to OSRM's 2,018.03 miles):
Chicago 0, Iowa City 220.3, Des Moines 329.4, Omaha 471.6, Ogallala 793.1, Denver 995.3,
Grand Junction 1243.7, Richfield 1467.0, Cedar City 1579.1, Las Vegas 1748.4.
Milwaukee and Fillmore are cheap but off the Route.
"""

import json
import logging
from decimal import Decimal
from pathlib import Path

import pytest
import responses

from routing.models import Station
from routing.services.station_index import get_station_index, warm_station_index

OSRM_FIXTURE = Path(__file__).parent / "fixtures" / "osrm_chicago_los_angeles.json"
OSRM_URL = "https://osrm.test/route/v1/driving/-87.6298,41.8781;-118.2437,34.0522"
CHICAGO, LOS_ANGELES = "41.8781,-87.6298", "34.0522,-118.2437"

STATIONS = [
    # opis_id, name, city, state, lat, lon, price
    (101, "PRICEY CHICAGO", "Chicago", "IL", 41.837045, -87.684939, "3.999"),
    (102, "CHEAP CHICAGO", "Chicago", "IL", 41.837045, -87.684939, "3.899"),
    (103, "OFF ROUTE MILWAUKEE", "Milwaukee", "WI", 43.063348, -87.966695, "2.500"),
    (104, "IOWA CITY STOP", "Iowa City", "IA", 41.655661, -91.530859, "3.300"),
    (105, "DES MOINES STOP", "Des Moines", "IA", 41.57259, -93.610243, "3.600"),
    (106, "OMAHA STOP", "Omaha", "NE", 41.262705, -96.053475, "3.450"),
    (107, "OGALLALA STOP", "Ogallala", "NE", 41.129595, -101.720677, "3.200"),
    (108, "DENVER STOP", "Denver", "CO", 39.76185, -104.881105, "3.700"),
    (109, "GRAND JUNCTION STOP", "Grand Junction", "CO", 39.089062, -108.567452, "3.650"),
    (110, "RICHFIELD STOP", "Richfield", "UT", 38.761311, -112.092861, "3.400"),
    (111, "OFF ROUTE FILLMORE", "Fillmore", "UT", 38.964264, -112.338679, "2.000"),
    (112, "CEDAR CITY STOP", "Cedar City", "UT", 37.683818, -113.09554, "3.550"),
    (113, "LAS VEGAS STOP", "Las Vegas", "NV", 36.233499, -115.264037, "4.100"),
]


@pytest.fixture
def stations(db):
    add_stations()


def add_stations() -> None:
    Station.objects.bulk_create(
        Station(
            opis_id=opis_id,
            name=name,
            address=f"I-80, EXIT {opis_id}",
            city=city,
            state=state,
            lat=lat,
            lon=lon,
            price_per_gallon=Decimal(price),
            geocode_source="census",
        )
        for opis_id, name, city, state, lat, lon, price in STATIONS
    )


@pytest.fixture
def osrm(settings):
    settings.OSRM_BASE_URL = "https://osrm.test"
    with responses.RequestsMock() as mock:
        mock.get(
            OSRM_URL,
            match=[
                responses.matchers.query_param_matcher(
                    {"overview": "full", "geometries": "polyline6", "alternatives": "true"}
                )
            ],
            json=json.loads(OSRM_FIXTURE.read_text()),
        )
        yield mock


def plan(client):
    return client.get("/api/route/", {"start": CHICAGO, "finish": LOS_ANGELES})


def test_plans_the_cheapest_fuel_stops_from_chicago_to_los_angeles(client, stations, osrm):
    response = plan(client)

    assert response.status_code == 200
    body = response.json()
    assert [
        (s["station_id"], s["mile_marker"], s["gallons"], s["cost"]) for s in body["fuel_stops"]
    ] == [
        (102, 0.0, 22.03, 85.89),  # cheapest at the start; just enough to reach $3.30 Iowa City
        (104, 220.3, 50.0, 165.0),  # nothing cheaper in Range: fill up, go to Omaha
        (106, 471.6, 7.277, 25.11),  # just enough to top up for $3.20 Ogallala
        (107, 793.1, 50.0, 160.0),  # fill up, go to the cheapest in Range (Grand Junction)
        (109, 1243.7, 17.391, 63.48),  # just enough to top up for $3.40 Richfield
        (110, 1467.0, 50.0, 170.0),  # fill up, go to Cedar City
        (112, 1579.1, 5.106, 18.12),  # Los Angeles is in Range: just enough to arrive
    ]
    assert body["total_gallons"] == 201.803  # 2,018.03 miles / 10 MPG
    assert body["total_fuel_cost"] == 687.6
    assert len(osrm.calls) == 1


def test_echoes_the_resolved_locations_and_the_route(client, stations, osrm):
    body = plan(client).json()

    assert body["start"] == {
        "query": CHICAGO,
        "lat": 41.8781,
        "lon": -87.6298,
        "resolved_by": "coordinates",
    }
    assert body["finish"]["resolved_by"] == "coordinates"
    assert body["route"] == {"distance_miles": 2018.03, "duration_hours": 35.36}


def test_each_fuel_stop_carries_the_station_details(client, stations, osrm):
    first_stop = plan(client).json()["fuel_stops"][0]

    assert first_stop == {
        "station_id": 102,
        "name": "CHEAP CHICAGO",
        "address": "I-80, EXIT 102",
        "city": "Chicago",
        "state": "IL",
        "lat": 41.837045,
        "lon": -87.684939,
        "price_per_gallon": 3.899,
        "mile_marker": 0.0,
        "gallons": 22.03,
        "cost": 85.89,
    }


def test_with_no_station_in_the_start_zone_the_trip_fills_up_at_the_nearest_one(
    client, stations, osrm
):
    # Take away the Chicago Stations; Waukegan is about 35 miles north, off the Route.
    Station.objects.filter(opis_id__in=[101, 102]).delete()
    Station.objects.create(
        opis_id=901,
        name="WAUKEGAN STOP",
        address="I-94, EXIT 1",
        city="Waukegan",
        state="IL",
        lat=42.363633,
        lon=-87.844794,
        price_per_gallon=Decimal("3.899"),
        geocode_source="census",
    )

    response = plan(client)

    assert response.status_code == 200
    first = response.json()["fuel_stops"][0]
    # the same price as Cheap Chicago, so the same purchase: just enough to reach Iowa City
    assert (first["station_id"], first["mile_marker"], first["gallons"]) == (901, 0.0, 22.03)


def test_states_the_assumptions_behind_the_plan(client, stations, osrm):
    assert plan(client).json()["assumptions"] == {
        "range_miles": 500.0,
        "mpg": 10.0,
        "tank_gallons": 50.0,
        "starting_fuel": "empty",
        "reserve_miles": 0.0,
        "corridor_miles": 8.0,
        "start_zone_miles": 8.0,
        "station_locations": "city-level; the detour to reach a Station is ignored",
    }


def test_a_request_never_queries_the_database(client, stations, osrm, django_assert_num_queries):
    get_station_index()  # built once, before any request

    with django_assert_num_queries(0):
        assert plan(client).status_code == 200


@pytest.mark.django_db
def test_stations_loaded_after_an_empty_start_are_used_without_a_restart(client, osrm, caplog):
    with caplog.at_level(logging.WARNING, logger="routing.services.station_index"):
        warm_station_index()  # the server started before `make load`

    assert "make load" in caplog.text
    assert plan(client).json()["error"]["code"] == "NO_STATION_AT_START"

    add_stations()

    assert plan(client).status_code == 200
