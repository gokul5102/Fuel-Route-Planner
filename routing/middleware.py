"""Adds X-External-Calls and X-Response-Time-Ms to every response, success or error,
and logs one line per request with the call count and where the time went."""

import logging

from routing.services import request_metrics

logger = logging.getLogger("routing.requests")


class RequestMetricsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        metrics = request_metrics.start_request()
        response = self.get_response(request)
        total_ms = metrics.elapsed_ms()
        response["X-External-Calls"] = str(metrics.external_calls)
        response["X-Response-Time-Ms"] = f"{total_ms:.1f}"
        stages = " ".join(f"{name}_ms={ms:.1f}" for name, ms in metrics.stage_ms.items())
        logger.info(
            "%s %s %s external_calls=%d total_ms=%.1f %s",
            request.method,
            request.path,
            response.status_code,
            metrics.external_calls,
            total_ms,
            stages,
        )
        return response
