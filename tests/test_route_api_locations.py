"""GET /api/route/ accepts place names, and explains locations it cannot use.

OSRM and Nominatim are mocked; any other HTTP request fails the test.
"""

import json

import pytest
import responses

from tests.test_route_api import OSRM_FIXTURE, stations  # noqa: F401  (pytest fixture)

# Every plan reads the Station index (its fingerprint is part of the cache key).
pytestmark = pytest.mark.django_db

# Census coordinates of "Chicago city", IL and "Los Angeles city", CA
OSRM_CENSUS_URL = "https://osrm.test/route/v1/driving/-87.684939,41.837045;-118.410825,34.019394"


@pytest.fixture
def http(settings):
    settings.OSRM_BASE_URL = "https://osrm.test"
    settings.NOMINATIM_BASE_URL = "https://nominatim.test"
    with responses.RequestsMock(assert_all_requests_are_fired=False) as mock:
        yield mock


@pytest.mark.usefixtures("stations")
def test_city_names_are_resolved_locally_so_the_only_external_call_is_osrm(client, http):
    http.get(OSRM_CENSUS_URL, json=json.loads(OSRM_FIXTURE.read_text()))

    response = client.get("/api/route/", {"start": "Chicago, IL", "finish": "Los Angeles, CA"})

    assert response.status_code == 200
    body = response.json()
    assert body["start"] == {
        "query": "Chicago, IL",
        "lat": 41.837045,
        "lon": -87.684939,
        "resolved_by": "census",
    }
    assert body["finish"]["resolved_by"] == "census"
    assert [call.request.url.split("?")[0] for call in http.calls] == [OSRM_CENSUS_URL]


def test_a_place_outside_the_usa_is_a_422_with_the_error_envelope(client, http):
    response = client.get("/api/route/", {"start": "Toronto, ON", "finish": "Chicago, IL"})

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "LOCATION_OUTSIDE_USA",
            "message": "'Toronto, ON' is outside the USA; only US trips can be planned.",
            "details": {"query": "Toronto, ON"},
        }
    }
    assert len(http.calls) == 0


def test_a_place_nominatim_cannot_find_is_a_422(client, http):
    http.get("https://nominatim.test/search", json=[])

    response = client.get("/api/route/", {"start": "Qwxyz Plaza", "finish": "Chicago, IL"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "LOCATION_NOT_FOUND"


def test_a_start_and_finish_at_the_same_point_is_a_400(client, http):
    response = client.get("/api/route/", {"start": "Chicago, IL", "finish": "chicago,il"})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_INPUT"
    assert len(http.calls) == 0
