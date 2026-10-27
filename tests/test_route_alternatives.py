"""GET /api/route/ plans every Route OSRM offers and returns the one with the cheapest fuel.

The recorded OSRM response (Chicago -> Los Angeles, one call with alternatives) has two Routes:
  0. I-80 / I-70 / I-15 via Denver and Las Vegas: 2,018.03 miles, 35.36 hours (the fastest);
  1. I-55 / I-44 / I-40 via St. Louis, Tulsa and Albuquerque: 2,124.37 miles, 37.26 hours.
Mile markers of the Stations below on their Route (scaled to OSRM's distance):
  I-80: Iowa City 220.3, Omaha 471.6, Ogallala 793.1, Denver 995.3, Grand Junction 1243.7,
        Richfield 1467.0, Las Vegas 1748.4.
  I-40: Saint Louis 299.3, Tulsa 684.8, Amarillo 1052.2, Albuquerque 1337.5, Flagstaff 1656.9,
        Kingman 1801.0.
Chicago is Mile marker 0 on both.
"""

import json
from decimal import Decimal
from pathlib import Path

import pytest
import responses

from routing.models import Station
from tests.polyline_encoding import encode

OSRM_FIXTURE = Path(__file__).parent / "fixtures" / "osrm_chicago_los_angeles_alternatives.json"
OSRM_URL = "https://osrm.test/route/v1/driving/-87.6298,41.8781;-118.2437,34.0522"
CHICAGO, LOS_ANGELES = "41.8781,-87.6298", "34.0522,-118.2437"

CHICAGO_STATION = (1, "Chicago", "IL", 41.837045, -87.684939)
I80_STATIONS = [
    (11, "Iowa City", "IA", 41.655661, -91.530859),
    (12, "Omaha", "NE", 41.262705, -96.053475),
    (13, "Ogallala", "NE", 41.129595, -101.720677),
    (14, "Denver", "CO", 39.76185, -104.881105),
    (15, "Grand Junction", "CO", 39.089062, -108.567452),
    (16, "Richfield", "UT", 38.761311, -112.092861),
    (17, "Las Vegas", "NV", 36.233499, -115.264037),
]
I40_STATIONS = [
    (21, "Saint Louis", "MO", 38.635699, -90.244582),
    (22, "Tulsa", "OK", 36.127949, -95.902316),
    (23, "Amarillo", "TX", 35.198064, -101.833107),
    (24, "Albuquerque", "NM", 35.10478, -106.646809),
    (25, "Flagstaff", "AZ", 35.185212, -111.620698),
    (26, "Kingman", "AZ", 35.216992, -114.010529),
]


def add_stations(stations, price: str) -> None:
    Station.objects.bulk_create(
        Station(
            opis_id=opis_id,
            name=f"{city.upper()} STOP",
            address="EXIT 1",
            city=city,
            state=state,
            lat=lat,
            lon=lon,
            price_per_gallon=Decimal(price),
            geocode_source="census",
        )
        for opis_id, city, state, lat, lon in stations
    )


@pytest.fixture
def osrm(settings):
    settings.OSRM_BASE_URL = "https://osrm.test"
    with responses.RequestsMock() as mock:
        mock.get(OSRM_URL, json=json.loads(OSRM_FIXTURE.read_text()))
        yield mock


def plan(client):
    return client.get("/api/route/", {"start": CHICAGO, "finish": LOS_ANGELES})


def test_the_slower_route_wins_when_its_fuel_is_cheaper(client, db, osrm):
    add_stations([CHICAGO_STATION], "4.00")
    add_stations(I80_STATIONS, "3.50")
    add_stations(I40_STATIONS, "3.00")

    body = plan(client).json()

    assert body["route"] == {"distance_miles": 2124.37, "duration_hours": 37.26}
    # 29.93 gal at $4.00 to reach St. Louis, then 182.507 gal at $3.00 (Flagstaff reaches LA)
    assert body["total_fuel_cost"] == 667.24
    assert [stop["station_id"] for stop in body["fuel_stops"]] == [1, 21, 22, 23, 24, 25]
    assert len(osrm.calls) == 1


def test_the_route_not_chosen_is_summarised_with_its_fuel_cost(client, db, osrm):
    add_stations([CHICAGO_STATION], "4.00")
    add_stations(I80_STATIONS, "3.50")
    add_stations(I40_STATIONS, "3.00")

    body = plan(client).json()

    assert body["alternatives"] == [
        {
            "distance_miles": 2018.03,
            "duration_hours": 35.36,
            # 22.03 gal at $4.00 to reach Iowa City, then 179.773 gal at $3.50 = $717.3255;
            # each of its 8 stops is rounded to the cent, which adds up to $717.34
            "total_fuel_cost": 717.34,
            "failure_code": None,
        }
    ]


def test_a_route_that_cannot_be_fuelled_is_skipped_and_summarised_with_its_failure(
    client, db, osrm
):
    add_stations([CHICAGO_STATION], "4.00")
    add_stations(I80_STATIONS, "3.50")  # nothing on I-40: it runs dry at Mile marker 500

    response = plan(client)

    assert response.status_code == 200
    body = response.json()
    assert body["route"] == {"distance_miles": 2018.03, "duration_hours": 35.36}
    assert body["total_fuel_cost"] == 717.34
    assert body["alternatives"] == [
        {
            "distance_miles": 2124.37,
            "duration_hours": 37.26,
            "total_fuel_cost": None,
            "failure_code": "UNREACHABLE",
        }
    ]


# Hand-made OSRM responses on the Kansas/Nebraska plains, from (40.0, -100.0) to (40.0, -97.0).
# DIRECT runs straight east. NORTH_LOOP goes 34.5 miles north first, east along latitude 40.5,
# then back south; the Northern Station on it is about 45 miles in and 34 miles off DIRECT.
# Each test declares the distance and duration OSRM reports for each Route.
START, FINISH = "40.0,-100.0", "40.0,-97.0"
DIRECT = [(40.0, -100.0), (40.0, -97.0)]
NORTH_LOOP = [(40.0, -100.0), (40.5, -100.0), (40.5, -97.0), (40.0, -97.0)]
START_STATION = (1, "Start", "KS", 40.0, -100.0)
NORTHERN_STATION = (2, "Northern", "NE", 40.5, -99.8)


def osrm_route(points, miles: float, hours: float) -> dict:
    return {
        "geometry": encode(points),
        "distance": miles * 1609.344,
        "duration": hours * 3600,
        "legs": [],
        "weight": hours * 3600,
        "weight_name": "routability",
    }


@pytest.fixture
def osrm_offers(settings):
    """Mock OSRM to offer the given Routes, in that order."""
    settings.OSRM_BASE_URL = "https://osrm.test"
    with responses.RequestsMock() as mock:

        def offer(*routes):
            mock.get(
                "https://osrm.test/route/v1/driving/-100.0,40.0;-97.0,40.0",
                json={"code": "Ok", "routes": list(routes), "waypoints": []},
            )

        yield offer


def plan_hand_made(client):
    return client.get("/api/route/", {"start": START, "finish": FINISH})


def test_hand_made_the_slower_loop_wins_when_a_cheap_station_is_on_it(client, db, osrm_offers):
    add_stations([START_STATION], "4.00")
    add_stations([NORTHERN_STATION], "2.00")
    osrm_offers(osrm_route(DIRECT, 160, 2.5), osrm_route(NORTH_LOOP, 230, 3.5))

    body = plan_hand_made(client).json()

    assert body["route"] == {"distance_miles": 230.0, "duration_hours": 3.5}
    assert [stop["station_id"] for stop in body["fuel_stops"]] == [1, 2]
    assert body["total_fuel_cost"] == 55.13  # ~4.6 gal at $4.00, then ~18.4 gal at $2.00
    assert body["alternatives"] == [
        # only the Start Station is on DIRECT: 16 gal at $4.00
        {
            "distance_miles": 160.0,
            "duration_hours": 2.5,
            "total_fuel_cost": 64.0,
            "failure_code": None,
        }
    ]


@pytest.mark.parametrize(
    ("slower_miles", "slower_cost"),
    [
        (160.0, 64.00),  # the same cost
        (159.975, 63.99),  # one cent cheaper is still a tie
    ],
)
def test_a_tie_within_a_cent_goes_to_the_faster_route(
    client, db, osrm_offers, slower_miles, slower_cost
):
    add_stations([START_STATION], "4.00")  # every gallon costs $4.00 on both Routes
    osrm_offers(osrm_route(NORTH_LOOP, slower_miles, 3.0), osrm_route(DIRECT, 160, 2.5))

    body = plan_hand_made(client).json()

    assert body["route"] == {"distance_miles": 160.0, "duration_hours": 2.5}
    assert body["total_fuel_cost"] == 64.0
    assert body["alternatives"][0]["total_fuel_cost"] == slower_cost


def test_two_cents_cheaper_is_not_a_tie(client, db, osrm_offers):
    add_stations([START_STATION], "4.00")
    osrm_offers(osrm_route(NORTH_LOOP, 159.95, 3.0), osrm_route(DIRECT, 160, 2.5))

    body = plan_hand_made(client).json()

    assert body["route"] == {"distance_miles": 159.95, "duration_hours": 3.0}
    assert body["total_fuel_cost"] == 63.98


def test_when_every_route_fails_the_fastest_routes_failure_is_returned(client, db, osrm_offers):
    add_stations([START_STATION, NORTHERN_STATION], "4.00")
    # DIRECT runs dry at Mile marker 500. NORTH_LOOP, the faster though OSRM lists it second,
    # refills at the Northern Station (Mile marker 138.9 once scaled to 700 miles) and runs dry
    # 500 miles after it.
    osrm_offers(osrm_route(DIRECT, 600, 9.0), osrm_route(NORTH_LOOP, 700, 8.0))

    response = plan_hand_made(client)

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "UNREACHABLE"
    assert error["details"] == {"mile_marker": 638.9}
