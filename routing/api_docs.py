"""What Swagger (/api/docs/) shows for the two endpoints: named examples and sample bodies.

Kept apart from the views so the views stay short. The Postman collection in `postman/`
uses the same named examples.
"""

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiExample, OpenApiParameter, OpenApiResponse

# Named example: (start, finish). "Missing field" leaves `finish` empty to show the 400.
TRIP_EXAMPLES = {
    "Cross-country": ("Chicago, IL", "Los Angeles, CA"),
    "Short trip": ("Dallas, TX", "Houston, TX"),
    "Coordinates": ("41.8781,-87.6298", "34.0522,-118.2437"),
    "Free-text address": ("233 S Wacker Dr, Chicago, IL", "Denver, CO"),
    "Outside the USA": ("Toronto, ON", "Chicago, IL"),
    "Missing field": ("Chicago, IL", ""),
}

LOCATION_HELP = '"lat,lng", "City, ST" or a US address'


def _location_parameter(name: str, position: int) -> OpenApiParameter:
    return OpenApiParameter(
        name,
        str,
        required=True,
        description=LOCATION_HELP,
        examples=[
            OpenApiExample(title, summary=title, value=trip[position])
            for title, trip in TRIP_EXAMPLES.items()
        ],
    )


ROUTE_QUERY_PARAMETERS = [_location_parameter("start", 0), _location_parameter("finish", 1)]


# A real response for the "Short trip" example (OSRM demo, 2026-10-27, uncached). Only the
# Route line is cut, to 4 of its 112 points, to keep the docs short.
SAMPLE_PLAN = {
    "start": {"query": "Dallas, TX", "lat": 32.793333, "lon": -96.766513, "resolved_by": "census"},
    "finish": {
        "query": "Houston, TX",
        "lat": 29.785743,
        "lon": -95.388806,
        "resolved_by": "census",
    },
    "route": {"distance_miles": 238.25, "duration_hours": 4.25},
    "fuel_stops": [
        {
            "station_id": 72773,
            "name": "RaceTrac #2626",
            "address": "I-20 Exit 472",
            "city": "Dallas",
            "state": "TX",
            "lat": 32.793333,
            "lon": -96.766513,
            "price_per_gallon": 2.864,
            "mile_marker": 0.0,
            "gallons": 1.597,
            "cost": 4.57,
        },
        {
            "station_id": 63669,
            "name": "One9 #1248",
            "address": "I-45, EXIT 271",
            "city": "Wilmer",
            "state": "TX",
            "lat": 32.599015,
            "lon": -96.681585,
            "price_per_gallon": 2.75566666,
            "mile_marker": 16.0,
            "gallons": 22.228,
            "cost": 61.25,
        },
    ],
    "total_gallons": 23.825,
    "total_fuel_cost": 65.82,
    "alternatives": [],
    "assumptions": {
        "range_miles": 500.0,
        "mpg": 10.0,
        "tank_gallons": 50.0,
        "starting_fuel": "empty",
        "reserve_miles": 0.0,
        "corridor_miles": 8.0,
        "start_zone_miles": 8.0,
        "station_locations": "city-level; the detour to reach a Station is ignored",
    },
    "map": {
        "geojson": {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [
                            [-96.76642, 32.79325],
                            [-96.42049, 31.96159],
                            [-95.71702, 30.8354],
                            [-95.38881, 29.78576],
                        ],
                    },
                    "properties": {
                        "kind": "route",
                        "chosen": True,
                        "distance_miles": 238.25,
                        "duration_hours": 4.25,
                        "total_fuel_cost": 65.82,
                        "failure_code": None,
                    },
                },
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [-96.766513, 32.793333]},
                    "properties": {"kind": "start", "query": "Dallas, TX"},
                },
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [-95.388806, 29.785743]},
                    "properties": {"kind": "finish", "query": "Houston, TX"},
                },
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [-96.766513, 32.793333]},
                    "properties": {
                        "kind": "fuel_stop",
                        "number": 1,
                        "station_id": 72773,
                        "name": "RaceTrac #2626",
                        "address": "I-20 Exit 472",
                        "city": "Dallas",
                        "state": "TX",
                        "price_per_gallon": 2.864,
                        "mile_marker": 0.0,
                        "gallons": 1.597,
                        "cost": 4.57,
                    },
                },
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [-96.681585, 32.599015]},
                    "properties": {
                        "kind": "fuel_stop",
                        "number": 2,
                        "station_id": 63669,
                        "name": "One9 #1248",
                        "address": "I-45, EXIT 271",
                        "city": "Wilmer",
                        "state": "TX",
                        "price_per_gallon": 2.75566666,
                        "mile_marker": 16.0,
                        "gallons": 22.228,
                        "cost": 61.25,
                    },
                },
            ],
        },
        "url": "http://localhost:8000/api/route/map/?start=Dallas%2C+TX&finish=Houston%2C+TX",
    },
    "meta": {
        "external_calls": 1,
        "cache": "miss",
        "timings_ms": {
            "geocode": 0.0,
            "routing": 4661.2,
            "corridor": 3.1,
            "optimize": 0.2,
            "total": 4673.5,
        },
    },
}


def _error(code: str, message: str, details: dict | None = None) -> dict:
    return {"error": {"code": code, "message": message, "details": details or {}}}


# HTTP status -> {example name: error body}. The statuses match routing.errors.STATUS_BY_CODE.
ERROR_EXAMPLES = {
    400: {
        "Missing field": _error(
            "INVALID_INPUT",
            "Check the query parameters.",
            {"finish": ["This field is required."]},
        ),
        "Same start and finish": _error(
            "INVALID_INPUT",
            "'Chicago, IL' and 'chicago, il' are the same place; there is no trip to plan.",
            {"start": "Chicago, IL", "finish": "chicago, il"},
        ),
    },
    422: {
        "Location not found": _error(
            "LOCATION_NOT_FOUND",
            "Could not find a location for 'Qwzxv Plorkville'.",
            {"query": "Qwzxv Plorkville"},
        ),
        "Outside the USA": _error(
            "LOCATION_OUTSIDE_USA",
            "'Toronto, ON' is outside the USA; only US trips can be planned.",
            {"query": "Toronto, ON"},
        ),
        "No drivable Route": _error(
            "NO_ROUTE",
            "No driving Route between the points: Impossible route between points",
            {"provider_code": "NoRoute"},
        ),
        "No Station in the Start zone": _error(
            "NO_STATION_AT_START",
            "No Station in the Start zone, so an empty tank cannot leave.",
        ),
        "Gap longer than the Range": _error(
            "UNREACHABLE",
            "The vehicle would run out of fuel at Mile marker 612.4.",
            {"mile_marker": 612.4},
        ),
    },
    502: {
        "Routing provider failed": _error(
            "ROUTING_PROVIDER_ERROR", "The routing provider could not be reached or broke."
        ),
    },
    504: {
        "Routing provider too slow": _error(
            "ROUTING_PROVIDER_TIMEOUT", "The routing provider did not answer within 10 s."
        ),
    },
}

ERROR_DESCRIPTIONS = {
    400: "Invalid query: a field is missing or blank, or start and finish are the same place.",
    422: "The query is valid, but no plan is possible.",
    502: "OSRM or Nominatim failed.",
    504: "OSRM or Nominatim did not answer within the timeout (10 s).",
}


def _response_examples(named_bodies: dict[str, dict]) -> list[OpenApiExample]:
    return [
        OpenApiExample(name, summary=name, value=body, response_only=True)
        for name, body in named_bodies.items()
    ]


ROUTE_SUMMARY = "Plan the cheapest Fuel stops between two places in the USA"
ROUTE_DESCRIPTION = (
    "One routing call (OSRM, up to 3 Routes) per uncached trip; repeats come from the cache "
    "with no external calls. Pick a named example in both `start` and `finish`."
)

ROUTE_RESPONSES = {
    200: OpenApiResponse(
        OpenApiTypes.OBJECT,
        description="The cheapest plan. Every response, errors included, also carries the "
        "X-External-Calls and X-Response-Time-Ms headers.",
        examples=_response_examples({"Short trip": SAMPLE_PLAN}),
    ),
    **{
        status: OpenApiResponse(
            OpenApiTypes.OBJECT,
            description=ERROR_DESCRIPTIONS[status],
            examples=_response_examples(bodies),
        )
        for status, bodies in ERROR_EXAMPLES.items()
    },
}


def add_map_page(result: dict, generator, request, public) -> dict:
    """drf-spectacular postprocessing hook: document GET /api/route/map/ too.

    drf-spectacular only sees DRF views, and the map page is a plain Django view. It takes
    the same query as GET /api/route/, so its parameters are copied from there.
    """
    route = result["paths"]["/api/route/"]["get"]
    html = {"text/html": {"schema": {"type": "string"}}}
    error_page = "An HTML page with the same error code and status as the API."
    result["paths"]["/api/route/map/"] = {
        "get": {
            "operationId": "route_map",
            "summary": "The same plan drawn on an interactive Leaflet map",
            "description": "Open it in a browser. It reuses the cached plan, so opening it "
            "after calling GET /api/route/ makes no external calls.",
            "tags": route.get("tags", []),
            "parameters": route["parameters"],
            "responses": {
                "200": {"description": "The map page.", "content": html},
                **{
                    str(status): {"description": error_page, "content": html}
                    for status in ERROR_EXAMPLES
                },
            },
        }
    }
    return result
