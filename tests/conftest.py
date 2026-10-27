import socket

import pytest


class NetworkAccessBlocked(RuntimeError):
    """Raised when a test tries to reach the real network.

    Mock external services at the HTTP layer with `responses` instead.
    Subclasses RuntimeError (not OSError) so HTTP libraries cannot swallow it.
    """


def _blocked(*args, **kwargs):
    raise NetworkAccessBlocked(f"Real network access is blocked in tests: {args!r}")


@pytest.fixture(autouse=True)
def _block_network(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _blocked)
    monkeypatch.setattr(socket.socket, "connect", _blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", _blocked)


@pytest.fixture(autouse=True)
def _fresh_station_index():
    """Each test sees an index built from its own Stations, never a previous test's."""
    from routing.services.station_index import reset_station_index

    reset_station_index()
    yield
    reset_station_index()


class FakeClock:
    """A monotonic clock that only moves when told to (or when something sleeps)."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


@pytest.fixture(autouse=True)
def nominatim_clock(monkeypatch):
    """Nominatim's 1-request-per-second pacing runs on a fake clock, so tests never wait.

    Each test starts as if Nominatim had never been called; `nominatim_clock.sleeps`
    records every pause.
    """
    clock = FakeClock()
    monkeypatch.setattr("routing.services.nominatim.monotonic", clock.monotonic)
    monkeypatch.setattr("routing.services.nominatim.sleep", clock.sleep)
    monkeypatch.setattr("routing.services.nominatim._next_turn", 0.0)
    return clock


@pytest.fixture(autouse=True)
def _empty_cache():
    """Each test starts with an empty cache, so cached geocodes never leak between tests."""
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()
