from urllib.parse import urlencode

from django.urls import reverse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

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


def route_map(request):
    """The plan drawn on a Leaflet map."""
    raise NotImplementedError
