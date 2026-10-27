"""OSRM sends each Route's geometry as a polyline6 string; decode() turns it back into points."""

import pytest

from routing.services.polyline import decode
from tests.polyline_encoding import encode

GOOGLE_EXAMPLE = [(38.5, -120.2), (40.7, -120.95), (43.252, -126.453)]


def test_decodes_googles_documented_example():
    # From Google's "Encoded Polyline Algorithm Format" page (precision 5).
    assert decode("_p~iF~ps|U_ulLnnqC_mqNvxq`@", precision=5) == pytest.approx(GOOGLE_EXAMPLE)


def test_decodes_a_precision_6_polyline_as_osrm_sends_it():
    # The same points at OSRM's polyline6 precision (checked with the `polyline` package).
    assert decode("_izlhA~rlgdF_{geC~ywl@_kwzCn`{nI") == pytest.approx(GOOGLE_EXAMPLE)


def test_an_empty_polyline_has_no_points():
    assert decode("") == []


def test_round_trips_points_with_six_decimals():
    points = [(41.8781, -87.629771), (41.878076, -87.629771), (34.052235, -118.243683)]

    assert decode(encode(points)) == pytest.approx(points, abs=1e-9)
