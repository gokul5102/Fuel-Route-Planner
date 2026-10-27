"""Every way GET /api/route/ can fail gives one envelope: {"error": {code, message, details}}.

OSRM is mocked: with the recorded Chicago -> Los Angeles Route (2,018.03 miles), or to fail.
"""

import io
import itertools
import json
import time
from decimal import Decimal
from pathlib import Path

import pytest
import requests
import responses
from django.core.exceptions import PermissionDenied
from django.http import Http404

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
def test_no_station_within_50_miles_of_the_start_is_no_station_at_start(client, osrm):
    osrm.get(OSRM_URL, json=json.loads(OSRM_FIXTURE.read_text()))
    add_station(1, "Iowa City", 41.655661, -91.530859)  # Mile marker 220, ~200 miles away

    error_of(plan(client), 422, "NO_STATION_AT_START")


@pytest.mark.django_db
def test_a_gap_beyond_the_range_is_unreachable_with_the_mile_marker_where_fuel_runs_out(
    client, osrm
):
    osrm.get(OSRM_URL, json=json.loads(OSRM_FIXTURE.read_text()))
    add_station(1, "Chicago", 41.837045, -87.684939)  # Mile marker 0, and nothing after it

    error = error_of(plan(client), 422, "UNREACHABLE")

    assert error["details"] == {"mile_marker": 500.0}


@pytest.mark.parametrize(
    ("osrm_code", "message"),
    [
        ("NoRoute", "Impossible route between points"),
        ("NoSegment", "Could not find a matching segment for coordinate"),
    ],
)
def test_osrm_finding_no_road_between_the_points_is_no_route(client, osrm, osrm_code, message):
    osrm.get(OSRM_URL, status=400, json={"code": osrm_code, "message": message})

    error = error_of(plan(client), 422, "NO_ROUTE")

    assert error["details"] == {"provider_code": osrm_code}


def ok_with(**route) -> dict:
    """An OSRM "Ok" answer with one Route made of `route`'s fields."""
    return {"code": "Ok", "routes": [route]}


@pytest.mark.parametrize(
    "body",
    [
        ["not", "an", "object"],
        {"code": "Ok"},  # no routes
        ok_with(distance=1000.0, duration=60.0),  # no geometry
        ok_with(geometry="_p~iF~ps|U", duration=60.0),  # no distance
        ok_with(geometry="_p~iF~ps|U", distance=None, duration=60.0),
        ok_with(geometry="_p~iF", distance=1000.0, duration=60.0),  # a lat without its lon
        ok_with(geometry="_p~iF~ps|U_", distance=1000.0, duration=60.0),  # cut mid-number
    ],
)
def test_osrm_answering_ok_with_a_body_we_cannot_read_is_a_routing_provider_error(
    client, osrm, body
):
    osrm.get(OSRM_URL, json=body)

    error_of(plan(client), 502, "ROUTING_PROVIDER_ERROR")


def test_osrm_answering_ok_with_no_routes_is_no_route(client, osrm):
    osrm.get(OSRM_URL, json={"code": "Ok", "routes": [], "waypoints": []})

    error_of(plan(client), 422, "NO_ROUTE")


@pytest.mark.parametrize(
    "failure",
    [
        {"status": 503, "body": "<html>Service Unavailable</html>"},
        {"status": 500, "json": {"code": "InternalError"}},
        {"status": 400, "json": {"code": "TooBig", "message": "Too many coordinates"}},
        {"status": 200, "body": "not json"},
        {"body": requests.exceptions.ConnectionError("connection refused")},
    ],
)
def test_osrm_failing_is_a_routing_provider_error(client, osrm, failure):
    osrm.get(OSRM_URL, **failure)

    error_of(plan(client), 502, "ROUTING_PROVIDER_ERROR")


@pytest.mark.parametrize(
    "timeout", [requests.exceptions.ReadTimeout(), requests.exceptions.ConnectTimeout()]
)
def test_osrm_timing_out_is_a_routing_provider_timeout(client, osrm, timeout):
    osrm.get(OSRM_URL, body=timeout)

    error_of(plan(client), 504, "ROUTING_PROVIDER_TIMEOUT")


def test_osrm_taking_longer_than_the_limit_in_total_is_a_routing_provider_timeout(
    client, osrm, settings, monkeypatch
):
    # Every single read is fast, but the clock says the whole download has taken 10.5 s.
    settings.HTTP_TIMEOUT_SECONDS = 10
    clock = itertools.chain([1000.0], itertools.repeat(1010.5))
    monkeypatch.setattr("routing.services.http.monotonic", lambda: next(clock))
    osrm.get(OSRM_URL, json=json.loads(OSRM_FIXTURE.read_text()))

    error = error_of(plan(client), 504, "ROUTING_PROVIDER_TIMEOUT")

    assert "10 s" in error["message"]


class StallingBody(io.RawIOBase):
    """A response body that sends a few bytes, then times out (as a socket read would)."""

    def __init__(self) -> None:
        self.sent = False

    def readable(self) -> bool:
        return True

    def readinto(self, buffer) -> int:
        if self.sent:
            raise TimeoutError("timed out")
        self.sent = True
        buffer[:9] = b'{"code":"'
        return 9


def test_osrm_stalling_in_the_middle_of_the_body_is_a_routing_provider_timeout(client, osrm):
    osrm.get(OSRM_URL, body=io.BufferedReader(StallingBody()))

    error_of(plan(client), 504, "ROUTING_PROVIDER_TIMEOUT")


class SlowBody(io.RawIOBase):
    """A response body that sends "[" at once, then takes `seconds` to send "]".

    No single read times out, so only a limit on the whole download stops it.
    """

    def __init__(self, seconds: float) -> None:
        self.seconds = seconds
        self.parts = [b"[", b"]"]

    def readable(self) -> bool:
        return True

    def readinto(self, buffer) -> int:
        if not self.parts:
            return 0
        if len(self.parts) == 1:
            time.sleep(self.seconds)
        part = self.parts.pop(0)
        buffer[: len(part)] = part
        return len(part)


def test_osrm_is_given_up_on_once_the_total_limit_passes_even_while_a_read_waits(
    client, osrm, settings
):
    settings.HTTP_TIMEOUT_SECONDS = 0.2
    osrm.get(OSRM_URL, body=io.BufferedReader(SlowBody(seconds=2)))

    started = time.monotonic()
    error = error_of(plan(client), 504, "ROUTING_PROVIDER_TIMEOUT")

    assert time.monotonic() - started < 1  # not the 2 s the read takes
    assert "0.2 s" in error["message"]


def test_an_unexpected_failure_still_uses_the_envelope(client, monkeypatch):
    def broken_planner(start, finish):
        raise RuntimeError("bug")

    monkeypatch.setattr("routing.views.plan_trip", broken_planner)

    error = error_of(plan(client), 500, "INTERNAL_ERROR")

    assert "bug" not in error["message"]  # internals are logged, not shown


@pytest.mark.parametrize(
    ("django_error", "status", "code"),
    [(Http404, 404, "NOT_FOUND"), (PermissionDenied, 403, "PERMISSION_DENIED")],
)
@pytest.mark.parametrize("path", ["/api/route/", "/api/route/map/"])
def test_django_not_found_and_permission_denied_keep_their_status(
    client, monkeypatch, django_error, status, code, path
):
    def refusing_planner(start, finish):
        raise django_error

    monkeypatch.setattr("routing.views.plan_trip", refusing_planner)

    response = client.get(path, {"start": CHICAGO, "finish": LOS_ANGELES})

    assert response.status_code == status
    if path == "/api/route/":
        error_of(response, status, code)
    else:
        assert code in response.content.decode()
