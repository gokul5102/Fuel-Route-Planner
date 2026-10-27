"""The price-file cleaning step behind `load_stations`, on a 10-row sample file.

The sample has an exact duplicate row, trailing whitespace, three prices for
OPIS ID 9, two prices for OPIS ID 7, a city missing from the coordinates file
(Nowhereville, ZZ) and a city recorded as unresolved (Lost Town, TX).
"""

from decimal import Decimal
from pathlib import Path

import pytest

from routing.services.stations import clean_stations, read_city_coords, read_price_file

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def cleaned():
    return clean_stations(
        read_price_file(FIXTURES / "prices_sample.csv"),
        read_city_coords(FIXTURES / "city_coords_sample.csv"),
    )


def by_id(cleaned, opis_id):
    return next(s for s in cleaned.stations if s.opis_id == opis_id)


def test_keeps_one_station_per_opis_id_with_a_resolved_city(cleaned):
    assert sorted(s.opis_id for s in cleaned.stations) == [7, 9, 12, 20]


def test_each_station_gets_its_cheapest_price_exactly_as_written(cleaned):
    prices = {s.opis_id: s.price_per_gallon for s in cleaned.stations}
    assert prices == {
        7: Decimal("3.00733333"),
        9: Decimal("3.19900000"),
        12: Decimal("3.10000000"),
        20: Decimal("4.10000000"),
    }


def test_trims_whitespace_from_every_field(cleaned):
    pilot = by_id(cleaned, 12)
    assert pilot.name == "PILOT TRAVEL CENTER #1"
    assert pilot.address == "I-70, EXIT 2"
    assert by_id(cleaned, 7).city == "Big Cabin"


def test_takes_coordinates_and_source_from_the_city_coordinates_file(cleaned):
    calgary = by_id(cleaned, 20)
    assert (calgary.lat, calgary.lon, calgary.geocode_source) == (51.045, -114.057, "nominatim")


def test_counts_what_was_read_dropped_and_skipped(cleaned):
    assert cleaned.rows_read == 10
    assert cleaned.duplicate_rows == 1
    assert cleaned.skipped_unresolved == 2  # Nowhereville, ZZ and Lost Town, TX
