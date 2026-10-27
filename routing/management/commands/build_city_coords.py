"""Turn the price file's city/state names into coordinates (maintainers only, needs internet).

1. Download the Census Gazetteer (places + county subdivisions) unless already cached.
2. Write the trimmed US places file used for "City, ST" lookups.
3. Match every unique city/state in the price file locally; send the rest (hard US
   names and the Canadian provinces) to Nominatim, one request per second.
4. Write one row per city to the city coordinates file as each result arrives.
"""

import csv
import io
import time
import zipfile
from collections import Counter
from collections.abc import Iterator
from pathlib import Path

import requests
from django.conf import settings
from django.core.management.base import BaseCommand

from routing.services import nominatim
from routing.services.places import PlaceIndex

GAZETTEER_URL = "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2024_Gazetteer/"
PLACES_ZIP = "2024_Gaz_place_national.zip"
COUSUBS_ZIP = "2024_Gaz_cousubs_national.zip"

CITY_COORDS_COLUMNS = ["city", "state", "lat", "lon", "source"]
CANADIAN_PROVINCES = {"AB", "BC", "MB", "NB", "NL", "NS", "NT", "NU", "ON", "PE", "QC", "SK", "YT"}
NOMINATIM_INTERVAL_SECONDS = 1.0  # Nominatim usage policy: at most 1 request per second


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
    """Yield (name, state, lat, lon) from a Gazetteer zip (tab-separated, UTF-8)."""
    with zipfile.ZipFile(zip_path) as archive:
        member = next(n for n in archive.namelist() if n.endswith(".txt"))
        text = archive.read(member).decode("utf-8")
    for row in csv.DictReader(io.StringIO(text), delimiter="\t"):
        row = {key.strip(): value for key, value in row.items()}
        yield row["NAME"], row["USPS"], float(row["INTPTLAT"]), float(row["INTPTLONG"])


def read_price_file_cities(path: Path) -> Counter[tuple[str, str]]:
    """Price-file row count per (city, state), whitespace trimmed."""
    with open(path, newline="", encoding="utf-8") as f:
        return Counter((row["City"].strip(), row["State"].strip()) for row in csv.DictReader(f))


def read_done_cities(path: Path) -> set[tuple[str, str]]:
    """(city, state) pairs already in the city coordinates file (empty if it doesn't exist)."""
    if not path.exists():
        return set()
    with open(path, newline="", encoding="utf-8") as f:
        return {(row["city"], row["state"]) for row in csv.DictReader(f)}


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

        price_rows = read_price_file_cities(settings.PRICE_FILE)
        done = read_done_cities(settings.CITY_COORDS_FILE)
        new_cities = sorted(set(price_rows) - done)
        self.stdout.write(f"{len(done)} cities already in the file, {len(new_cities)} new cities")

        self.nominatim_calls = 0
        self.failed = 0
        with open(settings.CITY_COORDS_FILE, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if f.tell() == 0:  # new file: write the header first
                writer.writerow(CITY_COORDS_COLUMNS)
            for city, state in new_cities:
                try:
                    lat, lon, source = self.locate(index, city, state)
                except nominatim.NominatimError as exc:
                    # Not written, so the next run retries it (no retries within a run).
                    self.failed += 1
                    self.stderr.write(f"Nominatim failed for {city}, {state}: {exc}")
                    continue
                writer.writerow([city, state, lat, lon, source])
                f.flush()  # an interrupted run keeps every city written so far

        self.print_summary(price_rows)
        if self.failed:
            self.stdout.write(f"{self.failed} Nominatim request(s) failed; re-run to retry them")

    def locate(self, index: PlaceIndex, city: str, state: str) -> tuple:
        """Return (lat, lon, source); lat and lon are "" when the city is unresolved."""
        coords = index.find(city, state)
        if coords:
            return *coords, "census"
        if self.nominatim_calls:
            time.sleep(NOMINATIM_INTERVAL_SECONDS)
        self.nominatim_calls += 1
        country = "ca" if state in CANADIAN_PROVINCES else "us"
        place = nominatim.search(f"{city}, {state}", country_code=country)
        # Free-text search can land in another state (e.g. "La Place, LA" in Alabama).
        if place is None or place.region != f"{country.upper()}-{state}":
            return "", "", "unresolved"
        return place.lat, place.lon, "nominatim"

    def print_summary(self, price_rows: Counter[tuple[str, str]]) -> None:
        with open(settings.CITY_COORDS_FILE, newline="", encoding="utf-8") as f:
            sources = {(r["city"], r["state"]): r["source"] for r in csv.DictReader(f)}
        for source, count in sorted(Counter(sources.values()).items()):
            self.stdout.write(f"{source}: {count}")

        us = [key for key in sources if key[1] not in CANADIAN_PROVINCES]
        us_census = [key for key in us if sources[key] == "census"]
        city_share = 100 * len(us_census) / max(len(us), 1)
        row_share = (
            100 * sum(price_rows[k] for k in us_census) / max(sum(price_rows[k] for k in us), 1)
        )
        self.stdout.write(
            f"{city_share:.1f}% of US cities ({row_share:.1f}% of US price rows) matched by census"
        )

    def write_us_places(self, places: list[tuple[str, str, float, float]]) -> None:
        with open(settings.US_PLACES_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["name", "state", "lat", "lon"])
            writer.writerows(places)
