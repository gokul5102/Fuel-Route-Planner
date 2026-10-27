"""Points on the Earth as 3D unit vectors, so straight-line (chord) distance tracks miles."""

import numpy as np

EARTH_RADIUS_MILES = 3958.8


def unit_vectors(lat_lon: np.ndarray) -> np.ndarray:
    """(n, 2) degrees lat/lon -> (n, 3) points on the unit sphere."""
    lat_lon = np.asarray(lat_lon, dtype=float).reshape(-1, 2)
    lat, lon = np.radians(lat_lon[:, 0]), np.radians(lat_lon[:, 1])
    return np.column_stack([np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)])


def miles_to_chord(miles: float) -> float:
    """The unit-sphere chord length for a great-circle distance in miles."""
    return 2 * np.sin(miles / (2 * EARTH_RADIUS_MILES))


def chord_to_miles(chord: np.ndarray) -> np.ndarray:
    """The great-circle distance in miles for unit-sphere chord lengths."""
    return 2 * EARTH_RADIUS_MILES * np.arcsin(np.clip(chord / 2, 0, 1))
