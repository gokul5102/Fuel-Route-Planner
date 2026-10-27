"""One error envelope for every API failure: {"error": {"code", "message", "details"}}.

Services raise plain exceptions that carry a `code` (and optionally `details`) and know
nothing about HTTP. `STATUS_BY_CODE` is the single place that decides each code's HTTP
status, and DRF calls `api_exception_handler` for anything a view raises.
"""

import logging

from rest_framework import status
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger(__name__)

STATUS_BY_CODE = {
    "INVALID_INPUT": status.HTTP_400_BAD_REQUEST,
    "LOCATION_NOT_FOUND": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "LOCATION_OUTSIDE_USA": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "NO_ROUTE": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "NO_STATION_AT_START": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "UNREACHABLE": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "ROUTING_PROVIDER_ERROR": status.HTTP_502_BAD_GATEWAY,
    "ROUTING_PROVIDER_TIMEOUT": status.HTTP_504_GATEWAY_TIMEOUT,
}


def error_body(code: str, message: str, details: dict | None = None) -> dict:
    return {"error": {"code": code, "message": message, "details": details or {}}}


def api_exception_handler(exc: Exception, context: dict) -> Response:
    """DRF's EXCEPTION_HANDLER: turn any exception from a view into the error envelope."""
    code = getattr(exc, "code", None)
    if isinstance(code, str) and code in STATUS_BY_CODE:  # a domain error from the services
        details = getattr(exc, "details", None)
        return Response(error_body(code, str(exc), details), status=STATUS_BY_CODE[code])

    if isinstance(exc, ValidationError):  # the query parameters failed validation
        return Response(
            error_body("INVALID_INPUT", "Check the query parameters.", exc.detail),
            status=status.HTTP_400_BAD_REQUEST,
        )

    response = drf_exception_handler(exc, context)
    if response is not None and isinstance(exc, APIException):  # e.g. 405 for a POST
        response.data = error_body(exc.default_code.upper(), str(exc.detail))
        return response

    logger.exception("Unexpected error while handling %s", context.get("request"))
    return Response(
        error_body("INTERNAL_ERROR", "Something went wrong on our side."),
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
