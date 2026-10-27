"""Opening the OSRM connection at server start, so the first request skips the TLS handshake."""

import logging

import responses

from routing.services import http


@responses.activate
def test_preconnect_opens_a_connection_to_the_service():
    responses.add(responses.HEAD, "https://osrm.test/", status=200)

    http.preconnect("https://osrm.test/").result(timeout=5)

    assert [(call.request.method, call.request.url) for call in responses.calls] == [
        ("HEAD", "https://osrm.test/")
    ]


def test_preconnect_never_fails_server_start(caplog):
    # The network is blocked in tests, so the HEAD request raises; startup must carry on.
    with caplog.at_level(logging.INFO, logger="routing.services.http"):
        http.preconnect("https://osrm.test/").result(timeout=5)

    assert "Could not pre-connect to https://osrm.test/" in caplog.text


@responses.activate
def test_every_call_goes_through_the_shared_keep_alive_session(monkeypatch):
    responses.add(responses.GET, "https://osrm.test/a", json={"code": "Ok"})
    responses.add(responses.GET, "https://osrm.test/b", json={"code": "Ok"})
    used = []
    real_get = http.session.get

    def spy(url, **kwargs):
        used.append(url)
        return real_get(url, **kwargs)

    monkeypatch.setattr(http.session, "get", spy)

    http.get_json("https://osrm.test/a", params={})
    http.get_json("https://osrm.test/b", params={})

    # The same session (and so its pooled TLS connections) served both calls.
    assert used == ["https://osrm.test/a", "https://osrm.test/b"]
