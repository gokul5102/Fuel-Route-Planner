"""resolve_location turns a `start` / `finish` query into a point in the USA.

Order: "lat,lng" (parsed) -> "City, ST" (local Census lookup) -> free text (Nominatim).
Nominatim is mocked at the HTTP layer; any unmocked request fails the test.
"""

import io
import time

import pytest
import requests
import responses

from routing.services.locations import (
    GeocodingFailed,
    LocationNotFound,
    LocationOutsideUSA,
    resolve_location,
)
from tests.test_route_errors import SlowBody

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


@pytest.mark.parametrize(
    ("query", "census_point"),
    [
        # Consolidated city-counties: "Nashville-Davidson metropolitan government (balance)"
        ("Nashville, TN", (36.1718, -86.785002)),
        ("Lexington, KY", (38.040678, -84.458272)),  # "Lexington-Fayette urban county"
        ("Augusta, GA", (33.365531, -82.073422)),
        ("Athens, GA", (33.949597, -83.370088)),
        ("Macon, GA", (32.80899, -83.69406)),  # "Macon-Bibb County"
        ("Butte, MT", (45.896232, -112.660071)),  # "Butte-Silver Bow (balance)"
        # Census names no rule turns into the everyday name
        ("Honolulu, HI", (21.324347, -157.84764)),  # "Urban Honolulu CDP"
        ("Boise, ID", (43.599335, -116.229817)),  # "Boise City city"
    ],
)
def test_big_cities_with_unusual_census_names_resolve_locally(http, query, census_point):
    location = resolve_location(query)

    assert (location.lat, location.lon) == census_point
    assert location.resolved_by == "census"
    assert len(http.calls) == 0


def test_a_canadian_province_is_outside_the_usa_without_any_http_call(http):
    with pytest.raises(LocationOutsideUSA) as error:
        resolve_location("Toronto, ON")

    assert error.value.code == "LOCATION_OUTSIDE_USA"
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

    assert error.value.code == "LOCATION_NOT_FOUND"


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


@pytest.mark.parametrize(
    "query",
    [
        "43.6532,-79.3832",  # Toronto, across Lake Ontario from New York
        "45.5017,-73.5673",  # Montreal
        "49.2827,-123.1207",  # Vancouver
        "60.7212,-135.0568",  # Whitehorse, Yukon (east of the Alaska panhandle)
        "19.4326,-99.1332",  # Mexico City
        "32.5149,-117.0382",  # Tijuana
        "26.0,-90.0",  # Gulf of Mexico
        "35.0,-60.0",  # Atlantic Ocean
        "51.5074,-0.1278",  # London
    ],
)
def test_coordinates_outside_the_usa_are_rejected(http, query):
    with pytest.raises(LocationOutsideUSA):
        resolve_location(query)


@pytest.mark.parametrize(
    "query",
    [
        "41.8781,-87.6298",  # Chicago
        "34.0522,-118.2437",  # Los Angeles
        "40.97,-117.0",  # I-80 in the Nevada desert, far from any town
        "25.7617,-80.1918",  # Miami
        "24.5551,-81.78",  # Key West
        "29.3013,-94.7977",  # Galveston
        "42.3314,-83.0458",  # Detroit, across the river from Windsor
        "47.6062,-122.3321",  # Seattle
        "46.8721,-68.0101",  # Presque Isle, northern Maine
        "48.9984,-97.0",  # the 49th parallel in North Dakota
        "61.2181,-149.9003",  # Anchorage
        "58.3019,-134.4197",  # Juneau, in the Alaska panhandle
        "21.3069,-157.8583",  # Honolulu
    ],
)
def test_coordinates_inside_the_usa_are_accepted(http, query):
    assert resolve_location(query).resolved_by == "coordinates"


def test_a_nominatim_outage_is_a_provider_error(http):
    http.get(NOMINATIM, status=503)

    with pytest.raises(GeocodingFailed) as error:
        resolve_location(WACKER)

    assert error.value.code == "ROUTING_PROVIDER_ERROR"


def test_a_nominatim_timeout_is_a_provider_timeout(http):
    http.get(NOMINATIM, body=requests.Timeout("read timed out"))

    with pytest.raises(GeocodingFailed) as error:
        resolve_location(WACKER)

    assert error.value.code == "ROUTING_PROVIDER_TIMEOUT"


def test_nominatim_is_given_up_on_once_the_total_limit_passes(http, settings):
    settings.HTTP_TIMEOUT_SECONDS = 0.2
    http.get(NOMINATIM, body=io.BufferedReader(SlowBody(seconds=2)))

    started = time.monotonic()
    with pytest.raises(GeocodingFailed) as error:
        resolve_location(WACKER)

    assert time.monotonic() - started < 1  # not the 2 s the read takes
    assert error.value.code == "ROUTING_PROVIDER_TIMEOUT"


@pytest.mark.parametrize("body", [{"lat": "41.9"}, [{"lat": "41.9"}], ["not a place"]])
def test_a_nominatim_answer_we_cannot_read_is_a_provider_error(http, body):
    http.get(NOMINATIM, json=body)

    with pytest.raises(GeocodingFailed) as error:
        resolve_location(WACKER)

    assert error.value.code == "ROUTING_PROVIDER_ERROR"


def test_nominatim_calls_are_spaced_at_least_one_second_apart(http, nominatim_clock):
    """Nominatim's policy is 1 request/s; a start and finish both in free text must wait."""
    http.get(NOMINATIM, json=WILLIS_TOWER)

    resolve_location(WACKER)
    nominatim_clock.now += 0.25
    resolve_location("Willis Tower")  # a different query, so not from the cache
    nominatim_clock.now += 5
    resolve_location("Sears Tower")

    assert nominatim_clock.sleeps == [0.75]  # only the second call waited
    assert len(http.calls) == 3


def test_a_census_place_outside_the_usa_outline_is_rejected_without_any_http_call(http):
    """The Census list includes Puerto Rico, but the outline (like "18.46,-66.10") excludes it."""
    with pytest.raises(LocationOutsideUSA):
        resolve_location("San Juan, PR")

    assert len(http.calls) == 0


def test_a_nominatim_answer_outside_the_usa_outline_is_rejected(http):
    http.get(
        NOMINATIM,
        json=[{"lat": "18.4655", "lon": "-66.1057", "address": {"ISO3166-2-lvl4": "US-PR"}}],
    )

    with pytest.raises(LocationOutsideUSA):
        resolve_location("Old San Juan")
