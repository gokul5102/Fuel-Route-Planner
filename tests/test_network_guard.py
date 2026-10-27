"""Any unmocked network call fails the test, so the suite stays offline."""

import urllib.request

import pytest
import requests
import responses

from tests.conftest import NetworkAccessBlocked


def test_unmocked_requests_call_is_blocked():
    with pytest.raises(NetworkAccessBlocked):
        requests.get("https://router.project-osrm.org/", timeout=1)


def test_unmocked_urllib_call_is_blocked():
    with pytest.raises(NetworkAccessBlocked):
        urllib.request.urlopen("https://nominatim.openstreetmap.org/", timeout=1)


@responses.activate
def test_calls_mocked_with_responses_still_work():
    responses.get("https://router.project-osrm.org/ping", json={"code": "Ok"})

    assert requests.get("https://router.project-osrm.org/ping", timeout=1).json() == {"code": "Ok"}
