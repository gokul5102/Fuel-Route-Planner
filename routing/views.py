from urllib.parse import urlencode

from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_GET
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from routing.errors import describe_error
from routing.serializers import RouteQuerySerializer, serialize_trip_plan
from routing.services.planner import plan_trip


def plan_trip_body(start: str, finish: str) -> dict:
    """The JSON body of a plan (without `map.url`). The API and the map page both use this."""
    return serialize_trip_plan(plan_trip(start, finish))


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
        parameters=[
            OpenApiParameter(
                "start", str, required=True, description='"lat,lng", "City, ST" or a US address'
            ),
            OpenApiParameter(
                "finish", str, required=True, description='"lat,lng", "City, ST" or a US address'
            ),
        ],
        responses=OpenApiTypes.OBJECT,
    )
    def get(self, request):
        query = RouteQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        start, finish = query.validated_data["start"], query.validated_data["finish"]
        body = plan_trip_body(start, finish)
        url = map_url(request, start, finish)
        return Response({**body, "map": {**body["map"], "url": url}})


@require_GET
def route_map(request):
    """The same plan as GET /api/route/, drawn on a Leaflet map with OpenStreetMap tiles.

    A failure renders a short HTML page with the same error code and status as the API.
    """
    try:
        query = RouteQuerySerializer(data=request.GET)
        query.is_valid(raise_exception=True)
        start, finish = query.validated_data["start"], query.validated_data["finish"]
        body = plan_trip_body(start, finish)
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
