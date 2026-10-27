"""What the current request has cost: its external HTTP calls and where its time went.

The middleware starts a fresh RequestMetrics for each request and keeps it in a ContextVar,
so the HTTP clients (OSRM, Nominatim) can count their calls and the planner can time its
stages without the metrics being passed around. Outside a request (e.g. in a management
command) counting and timing do nothing.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from time import perf_counter

STAGES = ("geocode", "routing", "corridor", "optimize")


@dataclass
class RequestMetrics:
    started: float = field(default_factory=perf_counter)
    external_calls: int = 0
    stage_ms: dict[str, float] = field(default_factory=lambda: dict.fromkeys(STAGES, 0.0))

    def elapsed_ms(self) -> float:
        return round((perf_counter() - self.started) * 1000, 1)

    def meta(self, cache: str) -> dict:
        """The `meta` of a plan response. `cache` is "hit" or "miss"."""
        timings = {name: round(ms, 1) for name, ms in self.stage_ms.items()}
        return {
            "external_calls": self.external_calls,
            "cache": cache,
            "timings_ms": {**timings, "total": self.elapsed_ms()},
        }


_current: ContextVar[RequestMetrics | None] = ContextVar("request_metrics", default=None)


def start_request() -> RequestMetrics:
    metrics = RequestMetrics()
    _current.set(metrics)
    return metrics


def current() -> RequestMetrics:
    """The current request's metrics (a throwaway one outside a request)."""
    return _current.get() or RequestMetrics()


def count_external_call() -> None:
    """Called by the HTTP clients just before each real request leaves."""
    current().external_calls += 1


@contextmanager
def stage(name: str) -> Iterator[None]:
    """Add the time spent inside the `with` block to stage `name` (stages can repeat)."""
    started = perf_counter()
    try:
        yield
    finally:
        current().stage_ms[name] += (perf_counter() - started) * 1000
