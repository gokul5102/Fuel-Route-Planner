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
