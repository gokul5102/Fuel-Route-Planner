"""Turn the price file's city/state names into coordinates (maintainers only, needs internet).

1. Download the Census Gazetteer (places + county subdivisions) unless already cached.
2. Write the trimmed US places file used for "City, ST" lookups.
3. Match every unique city/state in the price file locally.
4. Append one row per city to the city coordinates file.
"""

import csv
import io
import zipfile
from collections.abc import Iterator
from pathlib import Path

import requests
from django.conf import settings
from django.core.management.base import BaseCommand

from routing.services.places import PlaceIndex

GAZETTEER_URL = "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2024_Gazetteer/"
PLACES_ZIP = "2024_Gaz_place_national.zip"
COUSUBS_ZIP = "2024_Gaz_cousubs_national.zip"

CITY_COORDS_COLUMNS = ["city", "state", "lat", "lon", "source"]


def download_once(url: str, path: Path) -> None:
    """Download `url` to `path` unless it is already there (written atomically)."""
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    response = requests.get(
        url,
        headers={"User-Agent": settings.NOMINATIM_USER_AGENT},
        timeout=settings.HTTP_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    partial = path.with_suffix(".part")
    partial.write_bytes(response.content)
    partial.rename(path)


def read_gazetteer(zip_path: Path) -> Iterator[tuple[str, str, float, float]]:
    """Yield (name, state, lat, lon) from a Gazetteer zip (tab-separated, latin-1)."""
    with zipfile.ZipFile(zip_path) as archive:
        member = next(n for n in archive.namelist() if n.endswith(".txt"))
        text = archive.read(member).decode("latin-1")
    for row in csv.DictReader(io.StringIO(text), delimiter="\t"):
        row = {key.strip(): value for key, value in row.items()}
        yield row["NAME"], row["USPS"], float(row["INTPTLAT"]), float(row["INTPTLONG"])


def read_price_file_cities(path: Path) -> list[tuple[str, str]]:
    """Unique (city, state) pairs from the price file, whitespace trimmed, sorted."""
    with open(path, newline="", encoding="utf-8") as f:
        return sorted({(row["City"].strip(), row["State"].strip()) for row in csv.DictReader(f)})


class Command(BaseCommand):
    help = "Build data/us_places.csv and data/city_coords.csv (needs internet)."

    def handle(self, *args, **options):
        for name in (PLACES_ZIP, COUSUBS_ZIP):
            download_once(GAZETTEER_URL + name, settings.GAZETTEER_CACHE_DIR / name)

        places = list(read_gazetteer(settings.GAZETTEER_CACHE_DIR / PLACES_ZIP))
        self.write_us_places(places)

        index = PlaceIndex()
        for place in places:  # places first, so they win over county subdivisions
            index.add(*place)
        for subdivision in read_gazetteer(settings.GAZETTEER_CACHE_DIR / COUSUBS_ZIP):
            index.add(*subdivision)

        counts = {"census": 0}
        with open(settings.CITY_COORDS_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(CITY_COORDS_COLUMNS)
            for city, state in read_price_file_cities(settings.PRICE_FILE):
                coords = index.find(city, state)
                if coords:
                    writer.writerow([city, state, *coords, "census"])
                    counts["census"] += 1

        us_total = counts["census"]
        self.stdout.write(f"census: {counts['census']}")
        self.stdout.write(
            f"{100 * counts['census'] / us_total:.1f}% of US cities matched by census"
        )

    def write_us_places(self, places: list[tuple[str, str, float, float]]) -> None:
        with open(settings.US_PLACES_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["name", "state", "lat", "lon"])
            writer.writerows(places)
