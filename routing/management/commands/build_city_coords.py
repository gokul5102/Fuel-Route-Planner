"""Turn the price file's city/state names into coordinates (maintainers only, needs internet).

1. Read the Census Gazetteer (places + county subdivisions) from the download cache.
2. Write the trimmed US places file used for "City, ST" lookups.
3. Match every unique city/state in the price file locally.
4. Append one row per city to the city coordinates file.
"""

import csv
import io
import zipfile
from collections.abc import Iterator
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from routing.services.places import PlaceIndex

PLACES_ZIP = "2024_Gaz_place_national.zip"
COUSUBS_ZIP = "2024_Gaz_cousubs_national.zip"

CITY_COORDS_COLUMNS = ["city", "state", "lat", "lon", "source"]


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
