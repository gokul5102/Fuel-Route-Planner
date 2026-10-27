import hashlib
import json
from dataclasses import asdict
from urllib.parse import urlencode

from django.conf import settings
from django.core.cache import cache
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_GET
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from routing.api_docs import (
    ROUTE_DESCRIPTION,
    ROUTE_QUERY_PARAMETERS,
    ROUTE_RESPONSES,
    ROUTE_SUMMARY,
)
from routing.errors import describe_error
from routing.serializers import RouteQuerySerializer, serialize_trip_plan, with_queries
from routing.services import request_metrics
from routing.services.locations import normalise_query
from routing.services.planner import Vehicle, plan_trip


def plan_trip_body(start: str, finish: str) -> tuple[dict, str]:
    """The JSON body of a plan (without `map.url` and `meta`), and "hit" or "miss".

    The API and the map page both use this, so opening the map after calling the API is
    a cache hit with no external calls. Only successful plans are cached; the cached dict
    is never changed (callers build new dicts around it).
    """
    key = plan_cache_key(start, finish)
    body = cache.get(key)
    if body is not None:  # maybe cached for another spelling, so echo this request's text
        return with_queries(body, start, finish), "hit"
    body = serialize_trip_plan(plan_trip(start, finish))
    cache.set(key, body, settings.PLAN_CACHE_SECONDS)
    return body, "miss"


def plan_cache_key(start: str, finish: str) -> str:
    """One key per trip and planning setup.

    Case and runs of spaces don't matter: "Chicago,  IL" and "chicago, il" share a plan.
    The vehicle settings and the OSRM server are part of the key, so changing them never
    serves a plan made with the old ones. The parts go in as a JSON list (so "A|B" to "C"
    and "A" to "B|C" stay apart), hashed so the key is safe for any cache backend.
    """
    parts = [
        normalise_query(start),
        normalise_query(finish),
        asdict(Vehicle.from_settings()),
        settings.OSRM_BASE_URL,
    ]
    return "plan:" + hashlib.sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()


def map_url(request, start: str, finish: str) -> str:
    query = urlencode({"start": start, "finish": finish})
    return request.build_absolute_uri(f"{reverse('route-map')}?{query}")


class RouteView(APIView):
    """Plan the cheapest Fuel stops between two places.

    Failures are raised, not caught here: routing.errors turns each into the error envelope.
    """

    authentication_classes = []
    permission_classes = []

    @extend_schema(
        summary=ROUTE_SUMMARY,
        description=ROUTE_DESCRIPTION,
        parameters=ROUTE_QUERY_PARAMETERS,
        responses=ROUTE_RESPONSES,
    )
    def get(self, request):
        query = RouteQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        start, finish = query.validated_data["start"], query.validated_data["finish"]
        body, cache_status = plan_trip_body(start, finish)
        url = map_url(request, start, finish)
        meta = request_metrics.current().meta(cache=cache_status)
        return Response({**body, "map": {**body["map"], "url": url}, "meta": meta})


@require_GET
def route_map(request):
    """The same plan as GET /api/route/, drawn on a Leaflet map with OpenStreetMap tiles.

    A failure renders a short HTML page with the same error code and status as the API.
    """
    try:
        query = RouteQuerySerializer(data=request.GET)
        query.is_valid(raise_exception=True)
        start, finish = query.validated_data["start"], query.validated_data["finish"]
        body, _ = plan_trip_body(start, finish)
    except Exception as exc:  # describe_error logs the unexpected ones
        status_code, body = describe_error(exc, request)
        error = {**body["error"], "details": _as_text(body["error"]["details"])}
        return render(request, "routing/map_error.html", {"error": error}, status=status_code)
    return render(request, "routing/map.html", {"plan": body, "start": start, "finish": finish})


def _as_text(details: dict) -> dict[str, str]:
    """Error details as one line of text each, e.g. {"start": "This field may not be blank."}."""
    return {
        field: " ".join(map(str, value)) if isinstance(value, list) else str(value)
        for field, value in details.items()
    }
