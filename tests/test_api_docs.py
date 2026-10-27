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


NAMED_EXAMPLES = {
    "Cross-country",
    "Short trip",
    "Coordinates",
    "Free-text address",
    "Outside the USA",
    "Missing field",
}


def _operation(client, path: str) -> dict:
    schema = client.get("/api/schema/", HTTP_ACCEPT="application/json").json()
    return schema["paths"][path]["get"]


def _parameter_examples(operation: dict, name: str) -> dict[str, str]:
    """{example summary: value} for one query parameter."""
    (parameter,) = (p for p in operation["parameters"] if p["name"] == name)
    return {example["summary"]: example["value"] for example in parameter["examples"].values()}


def test_route_query_parameters_have_the_named_examples(client):
    operation = _operation(client, "/api/route/")

    start = _parameter_examples(operation, "start")
    finish = _parameter_examples(operation, "finish")

    assert set(start) == NAMED_EXAMPLES
    assert set(finish) == NAMED_EXAMPLES
    assert (start["Cross-country"], finish["Cross-country"]) == ("Chicago, IL", "Los Angeles, CA")
    assert (start["Short trip"], finish["Short trip"]) == ("Dallas, TX", "Houston, TX")
    assert start["Outside the USA"] == "Toronto, ON"
