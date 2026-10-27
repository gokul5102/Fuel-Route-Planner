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
