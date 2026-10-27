"""The API docs plumbing works.

drf-spectacular 0.30.0 officially supports Django only up to 6.0, so these
tests also guard its compatibility with Django 6.1.
"""


def test_schema_endpoint_returns_an_openapi_document(client):
    response = client.get("/api/schema/", HTTP_ACCEPT="application/json")

    assert response.status_code == 200
    document = response.json()
    assert document["openapi"].startswith("3.")
    assert document["info"]["title"] == "Fuel Route Planner API"


def test_docs_endpoint_renders_swagger_ui(client):
    response = client.get("/api/docs/")

    assert response.status_code == 200
    assert b"swagger-ui" in response.content
