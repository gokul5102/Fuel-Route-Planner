from routing.services.places import PlaceIndex


def test_finds_a_city_despite_case_whitespace_and_saint_spelling():
    index = PlaceIndex()
    index.add("St. Louis city", "MO", 38.635, -90.244)

    assert index.find("SAINT LOUIS ", "MO") == (38.635, -90.244)
    assert index.find("st louis", " mo") == (38.635, -90.244)


def test_place_type_suffix_is_optional_but_a_name_ending_in_city_still_matches():
    index = PlaceIndex()
    index.add("Kansas City city", "MO", 39.125, -94.551)
    index.add("Carson City", "NV", 39.151, -119.746)
    index.add("Smithtown town", "NY", 40.86, -73.21)

    assert index.find("Kansas City", "MO") == (39.125, -94.551)
    assert index.find("CARSON CITY", "NV") == (39.151, -119.746)
    assert index.find("Smithtown", "NY") == (40.86, -73.21)


def test_ignores_parentheticals_hyphens_and_apostrophes():
    index = PlaceIndex()
    index.add("Winston-Salem city", "NC", 36.1, -80.26)
    index.add("Coeur d'Alene city", "ID", 47.69, -116.78)
    index.add("Lexington-Fayette urban county (balance)", "KY", 38.04, -84.46)

    assert index.find("WINSTON SALEM", "NC") == (36.1, -80.26)
    assert index.find("Coeur dAlene", "ID") == (47.69, -116.78)
    assert index.find("Lexington-Fayette", "KY") == (38.04, -84.46)


def test_state_must_match_and_unknown_cities_return_none():
    index = PlaceIndex()
    index.add("Springfield city", "IL", 39.78, -89.65)

    assert index.find("Springfield", "MO") is None
    assert index.find("Nowhere", "IL") is None


def test_first_place_added_wins_when_two_share_a_name():
    index = PlaceIndex()
    index.add("Franklin city", "TN", 35.92, -86.85)
    index.add("Franklin town", "TN", 36.0, -86.0)

    assert index.find("Franklin", "TN") == (35.92, -86.85)


def test_loads_the_us_places_file(tmp_path):
    places_file = tmp_path / "us_places.csv"
    places_file.write_text("name,state,lat,lon\nDallas city,TX,32.794,-96.765\n")

    index = PlaceIndex.from_csv(places_file)

    assert index.find("Dallas", "TX") == (32.794, -96.765)
