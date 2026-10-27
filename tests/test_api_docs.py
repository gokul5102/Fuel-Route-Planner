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


def _response_examples(operation: dict, status: str) -> list[dict]:
    content = operation["responses"][status]["content"]["application/json"]
    return [example["value"] for example in content["examples"].values()]


def test_route_docs_show_a_sample_plan(client):
    (plan,) = _response_examples(_operation(client, "/api/route/"), "200")

    assert plan["fuel_stops"]
    assert plan["total_fuel_cost"] == round(sum(stop["cost"] for stop in plan["fuel_stops"]), 2)
    assert plan["meta"]["external_calls"] == 1


def test_route_docs_show_every_error_response(client):
    operation = _operation(client, "/api/route/")

    codes_by_status = {
        status: {example["error"]["code"] for example in _response_examples(operation, status)}
        for status in ("400", "422", "502", "504")
    }

    assert codes_by_status == {
        "400": {"INVALID_INPUT"},
        "422": {
            "LOCATION_NOT_FOUND",
            "LOCATION_OUTSIDE_USA",
            "NO_ROUTE",
            "NO_STATION_AT_START",
            "UNREACHABLE",
        },
        "502": {"ROUTING_PROVIDER_ERROR"},
        "504": {"ROUTING_PROVIDER_TIMEOUT"},
    }
