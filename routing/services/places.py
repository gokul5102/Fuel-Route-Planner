"""Local "City, ST" -> (lat, lon) lookup built from the US Census Gazetteer.

Names are compared by a normalised *key* so that spelling differences between
the fuel price file and the Census files still match, e.g. "SAINT LOUIS" and
"St. Louis city" both become "st louis".
"""

import csv
import re
import unicodedata
from pathlib import Path

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


def place_key(name: str) -> str:
    """Normalise a city name for matching: case, accents, whitespace, punctuation, "Saint"."""
    key = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()  # ñ -> n
    key = key.lower().strip()
    key = key.replace("saint ", "st ").replace("st. ", "st ")
    key = key.replace(".", "").replace("'", "").replace("-", " ")
    return re.sub(r"\s+", " ", key).strip()


class PlaceIndex:
    """In-memory lookup of place coordinates by (normalised name, state)."""

    def __init__(self) -> None:
        self._coords: dict[tuple[str, str], LatLon] = {}

    def __len__(self) -> int:
        return len(self._coords)

    def add(self, name: str, state: str, lat: float, lon: float) -> None:
        """Index a Census place name, with and without its place-type suffix.

        The first place added under a key wins, so add higher-priority files first.
        """
        name = PARENTHETICAL.sub("", name)
        state = state.strip().upper()
        for variant in {name, PLACE_TYPE_SUFFIX.sub("", name)}:
            self._coords.setdefault((place_key(variant), state), (lat, lon))

    def find(self, city: str, state: str) -> LatLon | None:
        return self._coords.get((place_key(city), state.strip().upper()))

    @classmethod
    def from_csv(cls, path: Path) -> "PlaceIndex":
        """Load the committed US places file (columns: name, state, lat, lon)."""
        index = cls()
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                index.add(row["name"], row["state"], float(row["lat"]), float(row["lon"]))
        return index
