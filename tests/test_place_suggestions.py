"""Autocomplete for "City, ST": suggestions come from the local Census places, never the network."""

import pytest

from routing.services.locations import resolve_location
from routing.services.places import PlaceIndex, get_place_index


def labels(suggestions) -> list[str]:
    return [s.label for s in suggestions]


@pytest.fixture
def index() -> PlaceIndex:
    places = PlaceIndex()
    for name, state in [
        ("Chicago Heights city", "IL"),
        ("Chicago city", "IL"),
        ("Chicago Ridge village", "IL"),
        ("Chico city", "CA"),
        ("Chicora CDP", "PA"),
        ("Springfield city", "IL"),
        ("Springfield city", "MO"),
        ("Nashville-Davidson metropolitan government (balance)", "TN"),
        ("Urban Honolulu CDP", "HI"),
        ("San Juan city", "TX"),
        ("Lynchburg, Moore County metropolitan government", "TN"),
    ]:
        places.add(name, state, 40.0, -90.0)
    # real positions, both outside the USA outline that resolve_location checks
    places.add("San Juan zona urbana", "PR", 18.41, -66.06)
    places.add("Attu Station CDP", "AK", 52.85, 173.18)  # western Aleutians, past 180°
    return places


def test_suggestions_match_the_start_of_the_name_and_drop_the_place_type(index):
    assert labels(index.suggest("chic")) == [
        "Chicago, IL",
        "Chicago Heights, IL",
        "Chico, CA",
        "Chicago Ridge, IL",
        "Chicora, PA",
    ]


def test_an_exact_name_comes_first(index):
    assert labels(index.suggest("chicago"))[0] == "Chicago, IL"


def test_cities_rank_above_villages_and_census_designated_places(index):
    position = labels(index.suggest("chic")).index
    assert position("Chico, CA") < position("Chicago Ridge, IL") < position("Chicora, PA")


def test_typing_a_state_after_a_comma_narrows_the_list(index):
    assert labels(index.suggest("springfield, mo")) == ["Springfield, MO"]
    assert labels(index.suggest("Springfield,")) == ["Springfield, IL", "Springfield, MO"]


def test_places_are_offered_under_the_name_people_use(index):
    assert labels(index.suggest("nash")) == ["Nashville, TN"]
    assert labels(index.suggest("honol")) == ["Honolulu, HI"]


def test_places_outside_the_usa_outline_are_not_offered(index):
    assert labels(index.suggest("san juan")) == ["San Juan, TX"]
    assert index.suggest("attu") == []


def test_a_name_with_a_comma_is_offered_and_found_by_its_first_part(index):
    # Census: "Lynchburg, Moore County metropolitan government"; people say "Lynchburg, TN"
    assert labels(index.suggest("lynch")) == ["Lynchburg, TN"]
    assert index.find("Lynchburg", "TN") == (40.0, -90.0)


def test_the_list_is_short(index):
    assert len(index.suggest("c", limit=3)) == 3
    assert index.suggest("   ") == []


def test_the_real_places_file_suggests_big_cities():
    assert labels(get_place_index().suggest("los ang"))[0] == "Los Angeles, CA"
    assert "Chicago, IL" in labels(get_place_index().suggest("chicago"))[:1]


def test_every_place_offered_resolves_locally_when_picked():
    # Picking any suggestion must plan from the Census file: no Nominatim call (the network
    # is blocked here, so a fallback would raise) and no LOCATION_OUTSIDE_USA.
    index = get_place_index()
    offered = {
        suggestion.label
        for prefix in two_letter_prefixes()
        for suggestion in index.suggest(prefix, limit=10**6)
    }

    assert len(offered) > 30_000
    for label in offered:
        assert resolve_location(label).resolved_by == "census", label


def two_letter_prefixes() -> list[str]:
    letters = "abcdefghijklmnopqrstuvwxyz"
    return [a + b for a in letters for b in letters]


# --- GET /api/places/


def test_the_api_returns_suggestions_without_any_external_call(client):
    response = client.get("/api/places/", {"q": "chicago"})

    assert response.status_code == 200
    first = response.json()["results"][0]
    assert first == {"label": "Chicago, IL", "name": "Chicago", "state": "IL"}
    assert response["X-External-Calls"] == "0"
    assert "max-age" in response["Cache-Control"]


def test_the_api_needs_at_least_two_characters(client):
    response = client.get("/api/places/", {"q": "c"})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_INPUT"
