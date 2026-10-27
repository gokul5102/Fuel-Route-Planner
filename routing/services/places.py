"""Local "City, ST" -> (lat, lon) lookup built from the US Census Gazetteer.

Names are compared by a normalised *key* so that spelling differences between
the fuel price file and the Census files still match, e.g. "SAINT LOUIS" and
"St. Louis city" both become "stlouis".
"""

import csv
import re
import threading
import unicodedata
from bisect import bisect_left
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings

LatLon = tuple[float, float]

# Census names end with the kind of place ("Chicago city", "Smithtown town").
# The price file never has these, so each name is also indexed without one.
PLACE_TYPE_SUFFIX = re.compile(
    r"\s+(city|town|village|cdp|borough|municipality|charter township|township"
    r"|plantation|urban county|metropolitan government|consolidated government"
    r"|unified government|city and borough|comunidad|zona urbana)$",
    re.IGNORECASE,
)
PARENTHETICAL = re.compile(r"\s*\(.*\)")
# A consolidated city-county is named after both, e.g. "Nashville-Davidson metropolitan
# government (balance)", "Macon-Bibb County", "Butte-Silver Bow (balance)"; people say
# "Nashville", "Macon", "Butte". So the part before the "-" or "/" is indexed too.
CONSOLIDATED_CITY = re.compile(r"^([^-/]+)[-/].*(county|government|\(balance\))$", re.IGNORECASE)
# Census names that no rule turns into the name people use.
EVERYDAY_NAMES = {
    ("Urban Honolulu CDP", "HI"): "Honolulu",
    ("Boise City city", "ID"): "Boise",
}


# Autocomplete ranks incorporated cities first, then towns and villages, then the rest
# (census-designated places and so on). Puerto Rico is outside the USA check, so it's not offered.
CITY_RANK, TOWN_RANK, OTHER_RANK = 0, 1, 2
TOWN_SUFFIX = re.compile(r"\s(town|village|borough|municipality)$", re.IGNORECASE)
NOT_SUGGESTED = {"PR"}


@dataclass(frozen=True)
class Suggestion:
    """A place offered while typing, e.g. Chicago, IL."""

    name: str
    state: str

    @property
    def label(self) -> str:
        return f"{self.name}, {self.state}"


def place_key(name: str) -> str:
    """Normalise a city name for matching: case, accents, spaces, punctuation, "Saint"."""
    key = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()  # ñ -> n
    key = key.lower().strip()
    key = key.replace("saint ", "st ").replace("st. ", "st ")
    key = key.replace(".", "").replace("'", "").replace("-", " ")
    return re.sub(r"\s+", "", key)  # "Mc Calla" = "McCalla", "La Place" = "LaPlace"


class PlaceIndex:
    """In-memory lookup of place coordinates by (normalised name, state)."""

    def __init__(self) -> None:
        self._coords: dict[tuple[str, str], LatLon] = {}
        # (key, rank, name, state), sorted by key on first use so a prefix is a bisect away
        self._suggestions: list[tuple[str, int, str, str]] = []
        self._sorted = True

    def __len__(self) -> int:
        return len(self._coords)

    def add(self, name: str, state: str, lat: float, lon: float) -> None:
        """Index a Census place name, with and without its place-type suffix.

        A consolidated city-county is also indexed under its city's name, and a few
        places under their EVERYDAY_NAMES. The first place added under a key wins, so add
        higher-priority files first.
        """
        state = state.strip().upper()
        short_name = PARENTHETICAL.sub("", name)
        variants = {short_name, PLACE_TYPE_SUFFIX.sub("", short_name)}
        if consolidated := CONSOLIDATED_CITY.match(name):
            variants.add(consolidated[1])
        if everyday_name := EVERYDAY_NAMES.get((name, state)):
            variants.add(everyday_name)
        for variant in variants:
            self._coords.setdefault((place_key(variant), state), (lat, lon))

        if state not in NOT_SUGGESTED:
            shown = (
                everyday_name
                or (consolidated and consolidated[1])
                or PLACE_TYPE_SUFFIX.sub("", short_name)
            )
            if everyday_name or consolidated or short_name.lower().endswith(" city"):
                rank = CITY_RANK
            else:
                rank = TOWN_RANK if TOWN_SUFFIX.search(short_name) else OTHER_RANK
            self._suggestions.append((place_key(shown), rank, shown.strip(), state))
            self._sorted = False

    def find(self, city: str, state: str) -> LatLon | None:
        return self._coords.get((place_key(city), state.strip().upper()))

    def suggest(self, query: str, limit: int = 8) -> list[Suggestion]:
        """Places whose name starts with `query`; "springfield, mo" also narrows by state.

        An exact name comes first, then cities, towns and other places, alphabetically.
        """
        name, _, state = query.partition(",")
        key, state = place_key(name), state.strip().upper()
        if not key:
            return []
        if not self._sorted:
            self._suggestions.sort()
            self._sorted = True
        matches = []
        for entry in self._suggestions[bisect_left(self._suggestions, (key,)) :]:
            if not entry[0].startswith(key):
                break
            if entry[3].startswith(state):
                matches.append(entry)
        matches.sort(key=lambda e: (e[0] != key, e[1], e[2], e[3]))
        suggestions = list(dict.fromkeys(Suggestion(name=e[2], state=e[3]) for e in matches))
        return suggestions[:limit]

    @classmethod
    def from_csv(cls, path: Path) -> "PlaceIndex":
        """Load the committed US places file (columns: name, state, lat, lon)."""
        index = cls()
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                index.add(row["name"], row["state"], float(row["lat"]), float(row["lon"]))
        return index


_index: PlaceIndex | None = None
_lock = threading.Lock()


def get_place_index() -> PlaceIndex:
    """The shared US places index, loaded from `US_PLACES_FILE` on first use (~0.1 s)."""
    global _index
    if _index is None:
        with _lock:
            if _index is None:
                _index = PlaceIndex.from_csv(settings.US_PLACES_FILE)
    return _index
