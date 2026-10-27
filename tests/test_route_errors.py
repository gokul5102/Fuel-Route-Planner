"""Every way GET /api/route/ can fail gives one envelope: {"error": {code, message, details}}.

OSRM is mocked: with the recorded Chicago -> Los Angeles Route (2,018.03 miles), or to fail.
"""

import json
from decimal import Decimal
from pathlib import Path

import pytest
import responses

from routing.models import Station

CHICAGO, LOS_ANGELES = "41.8781,-87.6298", "34.0522,-118.2437"
OSRM_URL = "https://osrm.test/route/v1/driving/-87.6298,41.8781;-118.2437,34.0522"
OSRM_FIXTURE = Path(__file__).parent / "fixtures" / "osrm_chicago_los_angeles.json"


@pytest.fixture
def osrm(settings):
    """OSRM, mocked; register the response each test needs with `osrm.get(OSRM_URL, ...)`."""
    settings.OSRM_BASE_URL = "https://osrm.test"
    with responses.RequestsMock() as mock:
        yield mock


def add_station(opis_id: int, city: str, lat: float, lon: float) -> None:
    Station.objects.create(
        opis_id=opis_id,
        name=f"{city.upper()} STOP",
        address="I-80",
        city=city,
        state="",
        lat=lat,
        lon=lon,
        price_per_gallon=Decimal("3.50"),
        geocode_source="census",
    )


def plan(client):
    return client.get("/api/route/", {"start": CHICAGO, "finish": LOS_ANGELES})


def error_of(response, status: int, code: str) -> dict:
    """Assert the status and the envelope, and return the error body."""
    assert response.status_code == status, response.content
    body = response.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "details"}
    assert body["error"]["code"] == code
    assert body["error"]["message"]
    return body["error"]


@pytest.mark.parametrize(
    ("query", "field"),
    [
        ({"finish": LOS_ANGELES}, "start"),
        ({"start": CHICAGO}, "finish"),
        ({"start": "  ", "finish": LOS_ANGELES}, "start"),
        ({"start": CHICAGO, "finish": ""}, "finish"),
    ],
)
def test_a_missing_or_blank_location_is_invalid_input(client, query, field):
    error = error_of(client.get("/api/route/", query), 400, "INVALID_INPUT")

    assert field in error["details"]


@pytest.mark.parametrize("value", ["91,0", "45,-181", "x" * 201])
def test_an_unparseable_location_is_invalid_input(client, value):
    error = error_of(
        client.get("/api/route/", {"start": value, "finish": LOS_ANGELES}), 400, "INVALID_INPUT"
    )

    assert "start" in error["details"]


def test_post_is_not_allowed(client):
    response = client.post("/api/route/", {"start": CHICAGO, "finish": LOS_ANGELES})

    error_of(response, 405, "METHOD_NOT_ALLOWED")
    assert response["Allow"] == "GET, HEAD, OPTIONS"


@pytest.mark.django_db
def test_no_station_in_the_start_zone_is_no_station_at_start(client, osrm):
    osrm.get(OSRM_URL, json=json.loads(OSRM_FIXTURE.read_text()))
    add_station(1, "Iowa City", 41.655661, -91.530859)  # Mile marker 220

    error_of(plan(client), 422, "NO_STATION_AT_START")


@pytest.mark.django_db
def test_a_gap_beyond_the_range_is_unreachable_with_the_mile_marker_where_fuel_runs_out(
    client, osrm
):
    osrm.get(OSRM_URL, json=json.loads(OSRM_FIXTURE.read_text()))
    add_station(1, "Chicago", 41.837045, -87.684939)  # Mile marker 0, and nothing after it

    error = error_of(plan(client), 422, "UNREACHABLE")

    assert error["details"] == {"mile_marker": 500.0}
