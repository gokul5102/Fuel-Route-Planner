"""The plan as a map: `map.geojson` and `map.url` in GET /api/route/, and the page at that URL.

OSRM is mocked with the recorded Chicago -> Los Angeles response that offers two Routes
(see tests/test_route_alternatives.py). With the prices below the I-80 Route is cheapest:
its plan is 22.03 gal at Chicago for $88.12, then Iowa City, Omaha, Ogallala, Denver,
Grand Junction, Richfield and Las Vegas at $3.50; the I-40 Route is the alternative.
"""

import json
from pathlib import Path

import pytest
import responses

from tests.test_route_alternatives import CHICAGO_STATION, I40_STATIONS, I80_STATIONS, add_stations

OSRM_FIXTURE = Path(__file__).parent / "fixtures" / "osrm_chicago_los_angeles_alternatives.json"
OSRM_URL = "https://osrm.test/route/v1/driving/-87.6298,41.8781;-118.2437,34.0522"
CHICAGO, LOS_ANGELES = "41.8781,-87.6298", "34.0522,-118.2437"


@pytest.fixture
def osrm(settings):
    settings.OSRM_BASE_URL = "https://osrm.test"
    with responses.RequestsMock() as mock:
        mock.get(OSRM_URL, json=json.loads(OSRM_FIXTURE.read_text()))
        yield mock


@pytest.fixture
def stations(db):
    add_stations([CHICAGO_STATION], "4.00")
    add_stations(I80_STATIONS, "3.50")
    add_stations(I40_STATIONS, "3.60")


def plan(client):
    return client.get("/api/route/", {"start": CHICAGO, "finish": LOS_ANGELES})


def features_of(geojson: dict, kind: str) -> list[dict]:
    return [f for f in geojson["features"] if f["properties"]["kind"] == kind]


def test_the_geojson_has_the_chosen_route_and_its_alternative_as_lines(client, stations, osrm):
    geojson = plan(client).json()["map"]["geojson"]

    assert geojson["type"] == "FeatureCollection"
    chosen, alternative = features_of(geojson, "route")
    assert chosen["geometry"]["type"] == "LineString"
    assert chosen["properties"] == {
        "kind": "route",
        "chosen": True,
        "distance_miles": 2018.03,
        "duration_hours": 35.36,
        "total_fuel_cost": 717.34,
        "failure_code": None,
    }
    assert alternative["properties"]["chosen"] is False
    assert alternative["properties"]["distance_miles"] == 2124.37
    # RFC 7946 order is [lon, lat]; both Routes leave Chicago and arrive in Los Angeles
    for line in (chosen, alternative):
        assert line["geometry"]["coordinates"][0] == [-87.62977, 41.8781]
        assert line["geometry"]["coordinates"][-1] == [-118.24356, 34.05233]


def test_the_geojson_has_start_finish_and_numbered_fuel_stops_as_points(client, stations, osrm):
    body = plan(client).json()
    geojson = body["map"]["geojson"]

    [start] = features_of(geojson, "start")
    [finish] = features_of(geojson, "finish")
    assert start["geometry"] == {"type": "Point", "coordinates": [-87.6298, 41.8781]}
    assert finish["geometry"] == {"type": "Point", "coordinates": [-118.2437, 34.0522]}
    assert start["properties"]["query"] == CHICAGO

    stops = features_of(geojson, "fuel_stop")
    assert [stop["properties"]["number"] for stop in stops] == [1, 2, 3, 4, 5, 6, 7, 8]
    first = stops[0]
    assert first["geometry"] == {"type": "Point", "coordinates": [-87.684939, 41.837045]}
    assert first["properties"] == {
        "kind": "fuel_stop",
        "number": 1,
        "station_id": 1,
        "name": "CHICAGO STOP",
        "address": "EXIT 1",
        "city": "Chicago",
        "state": "IL",
        "price_per_gallon": 4.0,
        "mile_marker": 0.0,
        "gallons": 22.03,
        "cost": 88.12,
    }
    assert [s["properties"]["station_id"] for s in stops] == [
        stop["station_id"] for stop in body["fuel_stops"]
    ]
