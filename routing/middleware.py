"""Adds X-External-Calls and X-Response-Time-Ms to every response, success or error."""

from routing.services import request_metrics


class RequestMetricsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        metrics = request_metrics.start_request()
        response = self.get_response(request)
        response["X-External-Calls"] = str(metrics.external_calls)
        response["X-Response-Time-Ms"] = f"{metrics.elapsed_ms():.1f}"
        return response
