"""`load_stations` fills the Station table from the price file, offline and re-runnably."""

import hashlib
import shutil
from decimal import Decimal
from io import StringIO
from pathlib import Path

import pytest
from django.core.management import call_command

from routing.models import Station

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_files(tmp_path, settings):
    settings.PRICE_FILE = shutil.copy(FIXTURES / "prices_sample.csv", tmp_path / "prices.csv")
    settings.CITY_COORDS_FILE = FIXTURES / "city_coords_sample.csv"
    return settings


def load() -> str:
    out = StringIO()
    call_command("load_stations", stdout=out)
    return out.getvalue()


@pytest.mark.django_db
def test_loads_one_station_per_opis_id_at_its_cheapest_price(sample_files):
    load()

    assert Station.objects.count() == 4
    tomah = Station.objects.get(opis_id=9)
    assert tomah.price_per_gallon == Decimal("3.19900000")
    assert (tomah.city, tomah.state, tomah.lat, tomah.lon) == ("Tomah", "WI", 43.981, -90.504)
    assert tomah.geocode_source == "census"


@pytest.mark.django_db
def test_summary_reports_rows_read_duplicates_and_skipped_cities(sample_files):
    summary = load()

    assert "10 rows read" in summary
    assert "1 exact duplicate" in summary
    assert "4 Stations loaded" in summary
    assert "2 skipped (city unresolved)" in summary


@pytest.mark.django_db
def test_running_twice_leaves_the_same_stations(sample_files):
    load()
    load()

    assert Station.objects.count() == 4
    assert sorted(Station.objects.values_list("opis_id", flat=True)) == [7, 9, 12, 20]


@pytest.mark.django_db
def test_never_modifies_the_price_file(sample_files):
    before = hashlib.sha256(sample_files.PRICE_FILE.read_bytes()).hexdigest()
    load()
    assert hashlib.sha256(sample_files.PRICE_FILE.read_bytes()).hexdigest() == before
