"""Turn the raw fuel price file into clean Stations (used by `load_stations`).

Cleaning, in order:
1. trim whitespace from every field (1,256 cities in the file end with spaces);
2. drop rows that are exact copies of an earlier row;
3. keep one Station per OPIS ID, at its cheapest price;
4. attach the city's coordinates from the city coordinates file, skipping
   Stations whose city has none.

Prices stay `Decimal`s parsed from the file's text, so no digit is lost.
"""

import csv
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

PriceRow = tuple[str, ...]  # one trimmed row of the price file, in file column order
CityCoords = dict[tuple[str, str], tuple[float, float, str]]  # (city, state) -> lat, lon, source


@dataclass(frozen=True)
class CleanStation:
    opis_id: int
    name: str
    address: str
    city: str
    state: str
    price_per_gallon: Decimal
    lat: float
    lon: float
    geocode_source: str


@dataclass
class CleanedStations:
    stations: list[CleanStation] = field(default_factory=list)
    rows_read: int = 0
    duplicate_rows: int = 0
    skipped_unresolved: int = 0  # Stations dropped because their city has no coordinates


def read_price_file(path: Path) -> list[PriceRow]:
    """Every data row of the price file with each field trimmed (the file is only read)."""
    with open(path, newline="", encoding="utf-8") as f:
        rows = csv.reader(f)
        next(rows)  # header
        return [tuple(value.strip() for value in row) for row in rows]


def read_city_coords(path: Path) -> CityCoords:
    """The resolved cities of the city coordinates file; unresolved ones are left out."""
    with open(path, newline="", encoding="utf-8") as f:
        return {
            (row["city"], row["state"]): (float(row["lat"]), float(row["lon"]), row["source"])
            for row in csv.DictReader(f)
            if row["source"] != "unresolved"
        }


def clean_stations(rows: list[PriceRow], city_coords: CityCoords) -> CleanedStations:
    """Collapse trimmed price rows to one Station per OPIS ID and attach coordinates."""
    result = CleanedStations(rows_read=len(rows))

    unique_rows = list(dict.fromkeys(rows))  # keeps the first copy, in file order
    result.duplicate_rows = len(rows) - len(unique_rows)

    cheapest: dict[int, PriceRow] = {}
    for row in unique_rows:
        opis_id, price = int(row[0]), Decimal(row[6])
        if opis_id not in cheapest or price < Decimal(cheapest[opis_id][6]):
            cheapest[opis_id] = row

    for opis_id, row in cheapest.items():
        _, name, address, city, state, _rack_id, price = row
        coords = city_coords.get((city, state))
        if coords is None:
            result.skipped_unresolved += 1
            continue
        lat, lon, source = coords
        result.stations.append(
            CleanStation(opis_id, name, address, city, state, Decimal(price), lat, lon, source)
        )
    return result
