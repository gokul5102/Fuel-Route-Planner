"""Every way GET /api/route/ can fail gives one envelope: {"error": {code, message, details}}."""

import pytest

CHICAGO, LOS_ANGELES = "41.8781,-87.6298", "34.0522,-118.2437"


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
