"""What Swagger (/api/docs/) shows for the two endpoints: named examples and sample bodies.

Kept apart from the views so the views stay short. The Postman collection in `postman/`
uses the same named examples.
"""

from drf_spectacular.utils import OpenApiExample, OpenApiParameter

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
