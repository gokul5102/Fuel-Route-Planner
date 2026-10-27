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
