"""Every response says how many external calls it made and how long it took; repeat
requests (and the map page after the API) are served from the plan cache with 0 calls.

OSRM is mocked with the recorded Chicago -> Los Angeles Route; Nominatim is mocked too.
"""

import json

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
