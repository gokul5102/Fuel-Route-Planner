import csv
import io
import zipfile

import pytest
import responses
from django.core.management import call_command
from responses import matchers

PLACES_ZIP = "2024_Gaz_place_national.zip"
COUSUBS_ZIP = "2024_Gaz_cousubs_national.zip"

# The real files are tab-separated with padded header names.
PLACES_TXT = (
    "USPS\tGEOID\tNAME\tALAND\tINTPTLAT\tINTPTLONG                    \n"
    "OK\t4006050\tBig Cabin town\t1\t36.540\t-95.220\n"
    "MO\t2965000\tSt. Louis city\t1\t38.635\t-90.244\n"
    "MO\t2938000\tKansas City city\t1\t39.125\t-94.551\n"
)
COUSUBS_TXT = (
    "USPS\tGEOID\tNAME\tALAND\tINTPTLAT\tINTPTLONG                    \n"
    "NY\t3610367000\tSmithtown town\t1\t40.860\t-73.210\n"
)
PRICE_HEADER = "OPIS Truckstop ID,Truckstop Name,Address,City,State,Rack ID,Retail Price\n"


def zipped(member: str, text: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(member, text.encode("latin-1"))
    return buffer.getvalue()


def read_csv(path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


@pytest.fixture
def data_dir(tmp_path, settings):
    """Point every data file at a temp dir with the Gazetteer already cached."""
    settings.PRICE_FILE = tmp_path / "prices.csv"
    settings.US_PLACES_FILE = tmp_path / "us_places.csv"
    settings.CITY_COORDS_FILE = tmp_path / "city_coords.csv"
    settings.GAZETTEER_CACHE_DIR = tmp_path / ".cache"
    settings.GAZETTEER_CACHE_DIR.mkdir()
    (settings.GAZETTEER_CACHE_DIR / PLACES_ZIP).write_bytes(
        zipped("2024_Gaz_place_national.txt", PLACES_TXT)
    )
    (settings.GAZETTEER_CACHE_DIR / COUSUBS_ZIP).write_bytes(
        zipped("2024_Gaz_cousubs_national.txt", COUSUBS_TXT)
    )
    return tmp_path


def write_prices(settings, *city_states: tuple[str, str]) -> None:
    lines = [
        f"{i},STOP {i},I-1 EXIT {i},{city},{state},1,3.0\n"
        for i, (city, state) in enumerate(city_states)
    ]
    settings.PRICE_FILE.write_text(PRICE_HEADER + "".join(lines))


def test_matches_price_file_cities_against_census_places_and_county_subdivisions(
    data_dir, settings
):
    write_prices(
        settings,
        ("Big Cabin", "OK"),
        ("SAINT LOUIS ", "MO"),
        ("Kansas City", "MO"),
        ("Kansas City", "MO"),
        ("Smithtown", "NY"),
    )
    out = io.StringIO()

    call_command("build_city_coords", stdout=out)

    rows = read_csv(settings.CITY_COORDS_FILE)
    assert rows == [
        {"city": "Big Cabin", "state": "OK", "lat": "36.54", "lon": "-95.22", "source": "census"},
        {
            "city": "Kansas City",
            "state": "MO",
            "lat": "39.125",
            "lon": "-94.551",
            "source": "census",
        },
        {
            "city": "SAINT LOUIS",
            "state": "MO",
            "lat": "38.635",
            "lon": "-90.244",
            "source": "census",
        },
        {"city": "Smithtown", "state": "NY", "lat": "40.86", "lon": "-73.21", "source": "census"},
    ]
    assert "census: 4" in out.getvalue()
    assert "100.0% of US cities" in out.getvalue()


def test_writes_the_us_places_file_from_the_census_places_only(data_dir, settings):
    write_prices(settings, ("Big Cabin", "OK"))

    call_command("build_city_coords", stdout=io.StringIO())

    assert read_csv(settings.US_PLACES_FILE) == [
        {"name": "Big Cabin town", "state": "OK", "lat": "36.54", "lon": "-95.22"},
        {"name": "St. Louis city", "state": "MO", "lat": "38.635", "lon": "-90.244"},
        {"name": "Kansas City city", "state": "MO", "lat": "39.125", "lon": "-94.551"},
    ]


GAZETTEER_URL = "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2024_Gazetteer/"


@responses.activate
def test_downloads_the_gazetteer_into_the_cache_when_missing(data_dir, settings):
    for name in (PLACES_ZIP, COUSUBS_ZIP):
        (settings.GAZETTEER_CACHE_DIR / name).unlink()
    settings.GAZETTEER_CACHE_DIR.rmdir()
    responses.get(
        GAZETTEER_URL + PLACES_ZIP, body=zipped("2024_Gaz_place_national.txt", PLACES_TXT)
    )
    responses.get(
        GAZETTEER_URL + COUSUBS_ZIP, body=zipped("2024_Gaz_cousubs_national.txt", COUSUBS_TXT)
    )
    write_prices(settings, ("Smithtown", "NY"))

    call_command("build_city_coords", stdout=io.StringIO())

    assert (settings.GAZETTEER_CACHE_DIR / PLACES_ZIP).exists()
    assert read_csv(settings.CITY_COORDS_FILE)[0]["source"] == "census"


@responses.activate
def test_uses_the_cached_gazetteer_without_downloading(data_dir, settings):
    write_prices(settings, ("Smithtown", "NY"))

    call_command("build_city_coords", stdout=io.StringIO())

    assert len(responses.calls) == 0


NOMINATIM_SEARCH = "https://nominatim.openstreetmap.org/search"


@pytest.fixture(autouse=True)
def sleeps(monkeypatch):
    """Record the throttle's sleeps instead of waiting."""
    calls = []
    monkeypatch.setattr("time.sleep", calls.append)
    return calls


def nominatim_answers(query: str, country: str, body: list) -> None:
    responses.get(
        NOMINATIM_SEARCH,
        json=body,
        match=[
            matchers.query_param_matcher(
                {"q": query, "format": "json", "limit": "1", "countrycodes": country}
            ),
            matchers.header_matcher({"User-Agent": "test-agent/1.0"}),
        ],
    )


@responses.activate
def test_cities_census_cannot_match_fall_back_to_nominatim_one_per_second(
    data_dir, settings, sleeps
):
    settings.NOMINATIM_USER_AGENT = "test-agent/1.0"
    write_prices(settings, ("Smithtown", "NY"), ("Tiny Spot", "TX"), ("Toronto", "ON"))
    nominatim_answers("Tiny Spot, TX", "us", [{"lat": "31.5", "lon": "-97.1"}])
    nominatim_answers("Toronto, ON", "ca", [{"lat": "43.65", "lon": "-79.38"}])
    out = io.StringIO()

    call_command("build_city_coords", stdout=out)

    rows = read_csv(settings.CITY_COORDS_FILE)
    assert [(r["city"], r["lat"], r["lon"], r["source"]) for r in rows] == [
        ("Smithtown", "40.86", "-73.21", "census"),
        ("Tiny Spot", "31.5", "-97.1", "nominatim"),
        ("Toronto", "43.65", "-79.38", "nominatim"),
    ]
    assert len(responses.calls) == 2
    assert sleeps == [1.0]  # a pause before every Nominatim call after the first
    assert "nominatim: 2" in out.getvalue()
    assert "50.0% of US cities" in out.getvalue()


@responses.activate
def test_cities_nominatim_cannot_find_are_recorded_as_unresolved(data_dir, settings):
    settings.NOMINATIM_USER_AGENT = "test-agent/1.0"
    write_prices(settings, ("Smithtown", "NY"), ("Atlantis", "TX"))
    nominatim_answers("Atlantis, TX", "us", [])
    out = io.StringIO()

    call_command("build_city_coords", stdout=out)

    assert read_csv(settings.CITY_COORDS_FILE)[0] == {
        "city": "Atlantis",
        "state": "TX",
        "lat": "",
        "lon": "",
        "source": "unresolved",
    }
    assert "unresolved: 1" in out.getvalue()


@responses.activate
def test_a_failed_nominatim_request_is_left_out_so_the_next_run_retries_it(data_dir, settings):
    write_prices(settings, ("Smithtown", "NY"), ("Tiny Spot", "TX"))
    responses.get(NOMINATIM_SEARCH, status=503)
    out = io.StringIO()

    call_command("build_city_coords", stdout=out)

    assert [r["city"] for r in read_csv(settings.CITY_COORDS_FILE)] == ["Smithtown"]
    assert "1 Nominatim request(s) failed" in out.getvalue()
