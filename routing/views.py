from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from routing.serializers import serialize_trip_plan
from routing.services.planner import plan_trip


class RouteView(APIView):
    """Plan the cheapest Fuel stops between two places."""

    authentication_classes = []
    permission_classes = []

    @extend_schema(
        parameters=[
            OpenApiParameter("start", str, required=True, description='"lat,lng"'),
            OpenApiParameter("finish", str, required=True, description='"lat,lng"'),
        ],
        responses=OpenApiTypes.OBJECT,
    )
    def get(self, request):
        trip = plan_trip(request.query_params["start"], request.query_params["finish"])
        return Response(serialize_trip_plan(trip))
