"""resolve_location turns a `start` / `finish` query into a point in the USA.

Order: "lat,lng" (parsed) -> "City, ST" (local Census lookup) -> free text (Nominatim).
Nominatim is mocked at the HTTP layer; any unmocked request fails the test.
"""

import pytest
import responses

from routing.services.locations import LocationNotFound, LocationOutsideUSA, resolve_location

NOMINATIM = "https://nominatim.test/search"
WACKER = "233 S Wacker Dr, Chicago, IL"
WILLIS_TOWER = [
    {
        "lat": "41.8788761",
        "lon": "-87.6359155",
        "display_name": "Willis Tower, 233, South Wacker Drive, Chicago, Illinois, USA",
        "address": {"city": "Chicago", "ISO3166-2-lvl4": "US-IL", "country_code": "us"},
    }
]


@pytest.fixture
def http(settings):
    """Every HTTP request must be mocked here; `http.calls` counts them."""
    settings.NOMINATIM_BASE_URL = "https://nominatim.test"
    with responses.RequestsMock(assert_all_requests_are_fired=False) as mock:
        yield mock


def test_city_and_state_resolve_locally_without_any_http_call(http):
    location = resolve_location("Chicago, IL")

    assert (location.lat, location.lon) == (41.837045, -87.684939)  # Census "Chicago city"
    assert location.resolved_by == "census"
    assert location.query == "Chicago, IL"
    assert len(http.calls) == 0


def test_city_lookup_uses_the_station_data_normalisation(http):
    """Case, spacing and "Saint"/"St." are ignored, as when matching the price file."""
    assert resolve_location("  SAINT LOUIS ,mo ").lat == resolve_location("St. Louis, MO").lat


def test_a_canadian_province_is_outside_the_usa_without_any_http_call(http):
    with pytest.raises(LocationOutsideUSA) as error:
        resolve_location("Toronto, ON")

    assert error.value.code == "LOCATION_OUTSIDE_USA"
    assert error.value.status_code == 422
    assert len(http.calls) == 0


def test_free_text_falls_back_to_nominatim_restricted_to_the_usa(http, settings):
    settings.NOMINATIM_USER_AGENT = "fuel-route-planner/test"
    http.get(
        NOMINATIM,
        match=[
            responses.matchers.query_param_matcher(
                {"q": WACKER, "countrycodes": "us"}, strict_match=False
            ),
            responses.matchers.header_matcher({"User-Agent": "fuel-route-planner/test"}),
        ],
        json=WILLIS_TOWER,
    )

    location = resolve_location(WACKER)

    assert (location.lat, location.lon) == (41.8788761, -87.6359155)
    assert location.resolved_by == "nominatim"
    assert len(http.calls) == 1


def test_a_repeated_free_text_query_is_answered_from_the_cache(http):
    http.get(NOMINATIM, json=WILLIS_TOWER)

    first = resolve_location(WACKER)
    again = resolve_location("  233 s wacker dr,  chicago, il ")

    assert (again.lat, again.lon, again.resolved_by) == (first.lat, first.lon, "nominatim")
    assert len(http.calls) == 1


def test_nothing_found_is_location_not_found(http):
    http.get(NOMINATIM, json=[])

    with pytest.raises(LocationNotFound) as error:
        resolve_location("Nowhereville Lane 99")

    assert (error.value.code, error.value.status_code) == ("LOCATION_NOT_FOUND", 422)


def test_a_city_missing_from_the_census_falls_back_to_nominatim_in_that_state(http):
    http.get(
        NOMINATIM,
        json=[{"lat": "38.7", "lon": "-98.1", "address": {"ISO3166-2-lvl4": "US-KS"}}],
    )

    location = resolve_location("Not A Census Town, KS")

    assert (location.lat, location.lon, location.resolved_by) == (38.7, -98.1, "nominatim")


def test_a_nominatim_answer_in_another_state_is_not_a_match(http):
    """Nominatim can answer with a same-named place elsewhere; "…, KS" must be in Kansas."""
    http.get(
        NOMINATIM,
        json=[{"lat": "39.8", "lon": "-89.6", "address": {"ISO3166-2-lvl4": "US-IL"}}],
    )

    with pytest.raises(LocationNotFound):
        resolve_location("Not A Census Town, KS")
