"""Autocomplete for "City, ST": suggestions come from the local Census places, never the network."""

import pytest

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
        ("San Juan zona urbana", "PR"),
        ("San Juan city", "TX"),
    ]:
        places.add(name, state, 40.0, -90.0)
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


def test_places_outside_the_usa_are_not_offered(index):
    assert labels(index.suggest("san juan")) == ["San Juan, TX"]


def test_the_list_is_short(index):
    assert len(index.suggest("c", limit=3)) == 3
    assert index.suggest("   ") == []


def test_the_real_places_file_suggests_big_cities():
    assert labels(get_place_index().suggest("los ang"))[0] == "Los Angeles, CA"
    assert "Chicago, IL" in labels(get_place_index().suggest("chicago"))[:1]


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
