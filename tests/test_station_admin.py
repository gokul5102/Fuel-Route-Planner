"""Reviewers can browse, search and filter Stations in the Django admin."""

from decimal import Decimal

import pytest

from routing.models import Station

CHANGELIST = "/admin/routing/station/"


@pytest.fixture
def stations(db):
    for opis_id, name, city, state, source in [
        (7, "WOODSHED OF BIG CABIN", "Big Cabin", "OK", "census"),
        (9, "KWIK TRIP #796", "Tomah", "WI", "census"),
        (20, "FLYING J CALGARY", "Calgary", "AB", "nominatim"),
    ]:
        Station.objects.create(
            opis_id=opis_id,
            name=name,
            address="I-1, EXIT 1",
            city=city,
            state=state,
            price_per_gallon=Decimal("3.5"),
            lat=40.0,
            lon=-90.0,
            geocode_source=source,
        )


def listed(response) -> set[str]:
    return {s.name for s in response.context["cl"].result_list}


def test_lists_every_station(admin_client, stations):
    response = admin_client.get(CHANGELIST)
    assert response.status_code == 200
    assert listed(response) == {"WOODSHED OF BIG CABIN", "KWIK TRIP #796", "FLYING J CALGARY"}


@pytest.mark.parametrize("query", ["kwik", "tomah", "WI"])
def test_searches_by_name_city_or_state(admin_client, stations, query):
    assert listed(admin_client.get(CHANGELIST, {"q": query})) == {"KWIK TRIP #796"}


def test_filters_by_state(admin_client, stations):
    assert listed(admin_client.get(CHANGELIST, {"state__exact": "AB"})) == {"FLYING J CALGARY"}


def test_filters_by_geocode_source(admin_client, stations):
    response = admin_client.get(CHANGELIST, {"geocode_source__exact": "nominatim"})
    assert listed(response) == {"FLYING J CALGARY"}
