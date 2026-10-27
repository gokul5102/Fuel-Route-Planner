"""Every response says how many external calls it made and how long it took; repeat
requests (and the map page after the API) are served from the plan cache with 0 calls.

OSRM is mocked with the recorded Chicago -> Los Angeles Route; Nominatim is mocked too.
"""

import json
import logging

import pytest
import responses

from tests.test_route_api import (  # noqa: F401  (stations is a pytest fixture)
    CHICAGO,
    LOS_ANGELES,
    OSRM_FIXTURE,
    OSRM_URL,
    stations,
)

NOMINATIM_URL = "https://nominatim.test/search"
OSRM_CENSUS_URL = "https://osrm.test/route/v1/driving/-87.684939,41.837045;-118.410825,34.019394"
# The reversed trip gets the same recorded Route: only the cache key matters here.
OSRM_REVERSED_URL = "https://osrm.test/route/v1/driving/-118.2437,34.0522;-87.6298,41.8781"


@pytest.fixture
def http(settings):
    """OSRM and Nominatim, mocked; `http.calls` lists every request that reached them."""
    settings.OSRM_BASE_URL = "https://osrm.test"
    settings.NOMINATIM_BASE_URL = "https://nominatim.test"
    with responses.RequestsMock(assert_all_requests_are_fired=False) as mock:
        mock.get(OSRM_URL, json=json.loads(OSRM_FIXTURE.read_text()))
        yield mock


def plan(client, start=CHICAGO, finish=LOS_ANGELES):
    return client.get("/api/route/", {"start": start, "finish": finish})


def response_time_ms(response) -> float:
    return float(response.headers["X-Response-Time-Ms"])


@pytest.mark.usefixtures("stations")
def test_a_plan_reports_its_one_osrm_call_and_its_time_in_headers(client, http):
    response = plan(client)

    assert response.status_code == 200
    assert response.headers["X-External-Calls"] == "1"
    assert response_time_ms(response) >= 0


@pytest.mark.usefixtures("db")
def test_an_invalid_request_reports_no_external_calls(client, http):
    response = plan(client, start="")

    assert response.status_code == 400
    assert response.headers["X-External-Calls"] == "0"
    assert response_time_ms(response) >= 0


@pytest.mark.usefixtures("stations")
def test_a_failed_geocode_still_counts_its_nominatim_call(client, http):
    http.get(NOMINATIM_URL, json=[])

    response = plan(client, start="Nowhere Special, Atlantis")

    assert response.status_code == 422
    assert response.headers["X-External-Calls"] == "1"
    assert len(http.calls) == 1


@pytest.mark.usefixtures("stations")
def test_the_map_page_carries_the_same_headers(client, http):
    response = client.get("/api/route/map/", {"start": CHICAGO, "finish": LOS_ANGELES})

    assert response.status_code == 200
    assert response.headers["X-External-Calls"] == "1"
    assert response_time_ms(response) >= 0


@pytest.mark.usefixtures("stations")
def test_a_fresh_plan_reports_a_cache_miss_its_calls_and_each_stage_time(client, http):
    meta = plan(client).json()["meta"]

    assert meta["cache"] == "miss"
    assert meta["external_calls"] == 1
    timings = meta["timings_ms"]
    assert set(timings) == {"geocode", "routing", "corridor", "optimize", "total"}
    assert all(ms >= 0 for ms in timings.values())
    assert timings["total"] >= timings["routing"] + timings["corridor"] + timings["optimize"]


@pytest.mark.usefixtures("stations")
def test_a_repeat_request_is_served_from_the_cache_with_no_external_calls(client, http):
    first = plan(client)
    second = plan(client)

    assert len(http.calls) == 1  # OSRM was asked once, for the first request only
    assert second.status_code == 200
    assert second.json()["meta"]["cache"] == "hit"
    assert second.json()["meta"]["external_calls"] == 0
    assert second.headers["X-External-Calls"] == "0"
    without_meta = [{k: v for k, v in r.json().items() if k != "meta"} for r in (first, second)]
    assert without_meta[0] == without_meta[1]


@pytest.mark.usefixtures("stations")
def test_the_cache_ignores_case_and_extra_spaces_in_place_names(client, http):
    http.get(OSRM_CENSUS_URL, json=json.loads(OSRM_FIXTURE.read_text()))

    plan(client, "Chicago, IL", "Los Angeles, CA")
    again = plan(client, "  chicago,   IL ", "LOS ANGELES,  ca")

    assert again.json()["meta"]["cache"] == "hit"
    assert len(http.calls) == 1


@pytest.mark.usefixtures("stations")
def test_a_different_trip_is_not_a_cache_hit(client, http):
    http.get(OSRM_REVERSED_URL, json=json.loads(OSRM_FIXTURE.read_text()))

    plan(client)
    reversed_trip = plan(client, start=LOS_ANGELES, finish=CHICAGO)

    assert reversed_trip.json()["meta"]["cache"] == "miss"
    assert len(http.calls) == 2


def nominatim_finds(http, query: str, lat: float, lon: float) -> None:
    http.get(
        NOMINATIM_URL,
        match=[responses.matchers.query_param_matcher({"q": query}, strict_match=False)],
        json=[{"lat": str(lat), "lon": str(lon), "address": {"ISO3166-2-lvl4": "US-IL"}}],
    )


@pytest.mark.usefixtures("stations")
def test_text_that_only_looks_alike_once_joined_is_not_a_cache_hit(client, http):
    """ "Chicago|x" to "Los Angeles" and "Chicago" to "x|Los Angeles" are different trips."""
    nominatim_finds(http, "Chicago|x", 41.8781, -87.6298)
    nominatim_finds(http, "Los Angeles", 34.0522, -118.2437)
    nominatim_finds(http, "Chicago", 41.8781, -87.6298)
    nominatim_finds(http, "x|Los Angeles", 34.0522, -118.2437)

    plan(client, "Chicago|x", "Los Angeles")
    other = plan(client, "Chicago", "x|Los Angeles")

    assert other.json()["meta"]["cache"] == "miss"


@pytest.mark.usefixtures("stations")
@pytest.mark.parametrize(
    ("setting", "value"),
    [
        ("RANGE_MILES", 400.0),
        ("MPG", 8.0),
        ("MIN_RESERVE_MILES", 20.0),
        ("CORRIDOR_MILES", 5.0),
        ("OSRM_BASE_URL", "https://other-osrm.test"),
    ],
)
def test_changing_a_planning_setting_is_not_served_a_stale_plan(
    client, http, settings, setting, value
):
    other_osrm_url = OSRM_URL.replace("osrm.test", "other-osrm.test")
    http.get(other_osrm_url, json=json.loads(OSRM_FIXTURE.read_text()))
    plan(client)
    setattr(settings, setting, value)

    again = plan(client)

    assert again.json()["meta"]["cache"] == "miss"


@pytest.mark.usefixtures("stations")
def test_the_map_page_after_the_api_makes_no_external_calls(client, http):
    plan(client)

    page = client.get("/api/route/map/", {"start": CHICAGO, "finish": LOS_ANGELES})

    assert page.status_code == 200
    assert page.headers["X-External-Calls"] == "0"
    assert len(http.calls) == 1


@pytest.mark.usefixtures("stations")
def test_each_request_logs_its_status_calls_and_stage_timings(client, http, caplog):
    with caplog.at_level(logging.INFO, logger="routing.requests"):
        plan(client)

    [record] = caplog.records
    line = record.getMessage()
    assert line.startswith("GET /api/route/ 200 external_calls=1 total_ms=")
    for stage in ("geocode", "routing", "corridor", "optimize"):
        assert f"{stage}_ms=" in line


@pytest.mark.usefixtures("stations")
def test_errors_are_not_cached(client, http, settings):
    http.get(NOMINATIM_URL, json=[])

    plan(client, start="Nowhere Special, Atlantis")
    again = plan(client, start="Nowhere Special, Atlantis")

    assert again.status_code == 422
    assert again.headers["X-External-Calls"] == "1"
