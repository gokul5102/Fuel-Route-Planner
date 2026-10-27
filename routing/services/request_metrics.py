"""What the current request has cost: its external HTTP calls and how long it has taken.

The middleware starts a fresh RequestMetrics for each request and keeps it in a ContextVar,
so the HTTP clients (OSRM, Nominatim) can count their calls without it being passed around.
Outside a request (e.g. in a management command) counting does nothing.
"""

from contextvars import ContextVar
from dataclasses import dataclass, field
from time import perf_counter


@dataclass
class RequestMetrics:
    started: float = field(default_factory=perf_counter)
    external_calls: int = 0

    def elapsed_ms(self) -> float:
        return round((perf_counter() - self.started) * 1000, 1)


_current: ContextVar[RequestMetrics | None] = ContextVar("request_metrics", default=None)


def start_request() -> RequestMetrics:
    metrics = RequestMetrics()
    _current.set(metrics)
    return metrics


def current() -> RequestMetrics | None:
    return _current.get()


def count_external_call() -> None:
    """Called by the HTTP clients just before each real request leaves."""
    metrics = current()
    if metrics is not None:
        metrics.external_calls += 1
