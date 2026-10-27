from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from routing.serializers import RouteQuerySerializer, serialize_trip_plan
from routing.services.planner import plan_trip


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
        trip = plan_trip(query.validated_data["start"], query.validated_data["finish"])
        return Response(serialize_trip_plan(trip))
