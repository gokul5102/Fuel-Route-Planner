from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from routing.serializers import serialize_trip_plan
from routing.services.locations import LocationError
from routing.services.planner import plan_trip


def location_error_response(error: LocationError) -> Response:
    """The error envelope for a start or finish that cannot be used."""
    body = {"code": error.code, "message": str(error), "details": error.details}
    return Response({"error": body}, status=error.status_code)


class RouteView(APIView):
    """Plan the cheapest Fuel stops between two places."""

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
        try:
            trip = plan_trip(request.query_params["start"], request.query_params["finish"])
        except LocationError as error:
            return location_error_response(error)
        return Response(serialize_trip_plan(trip))
