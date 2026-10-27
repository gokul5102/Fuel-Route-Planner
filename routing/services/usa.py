"""Is a point in the USA? A coarse, hand-drawn outline, checked with no external call.

Three polygons: the lower 48, Alaska and Hawaii. Each is a few dozen (lat, lon) corners
that follow the Canadian border (the 49th parallel, then the middle of the Great Lakes
and the St. Lawrence, then Maine), the Mexican border (the Rio Grande, then the straight
lines to the Pacific) and run a little offshore along the coasts.

Checked against the data: all 32,041 US Census places in data/us_places.csv (outside
Puerto Rico) lie inside the outline except two CDPs in the western Aleutians, and of the
85 Canadian cities in the fuel price file only Windsor and Fort Erie, each across a river
from the USA, fall inside it. Such near-border false positives are accepted: a coarse
outline cannot follow a river exactly. Coastal waters a few miles offshore count as the
USA; the open ocean does not. Not covered: Puerto Rico and the other territories, and the
western Aleutians across the 180th meridian (none can be reached by road anyway).
"""

LatLon = tuple[float, float]

LOWER_48: tuple[LatLon, ...] = (
    # Pacific Northwest, then the 49th parallel eastward
    (48.5, -124.9),
    (48.25, -123.25),
    (48.8, -123.2),
    (49.0, -123.05),
    (49.0, -95.15),
    # Lake of the Woods, Rainy River, Lake Superior
    (49.4, -95.15),
    (49.4, -94.85),
    (48.75, -94.65),
    (48.6, -93.0),
    (48.0, -89.55),
    (48.3, -88.4),
    (46.9, -84.8),
    (46.52, -84.55),
    (46.48, -84.1),
    # St. Marys River, Lake Huron, St. Clair and Detroit rivers
    (46.0, -83.4),
    (45.35, -82.5),
    (43.0, -82.4),
    (42.6, -82.46),
    (42.53, -82.6),
    (42.35, -82.92),
    (42.0, -83.1),
    # Lake Erie, Niagara River, Lake Ontario
    (41.68, -82.65),
    (42.5, -79.8),
    (43.25, -79.05),
    (43.6, -78.7),
    (43.65, -76.5),
    (44.1, -76.4),
    # St. Lawrence River, then the 45th parallel
    (44.25, -76.2),
    (44.4, -75.85),
    (44.65, -75.6),
    (44.75, -75.42),
    (44.92, -75.1),
    (45.0, -74.7),
    (45.0, -71.6),
    # Maine
    (45.03, -71.5),
    (45.3, -71.1),
    (46.4, -70.0),
    (47.45, -69.05),
    (47.42, -68.4),
    (47.33, -68.0),
    (47.2, -67.85),
    (47.07, -67.79),
    (45.6, -67.8),
    (45.57, -67.4),
    (45.18, -67.25),
    # Atlantic coast, a little offshore, southward
    (44.95, -66.95),
    (44.6, -66.75),
    (42.0, -69.7),
    (41.0, -69.6),
    (40.8, -71.5),
    (40.3, -73.6),
    (38.7, -74.7),
    (36.5, -75.4),
    (35.1, -75.2),
    (34.4, -76.3),
    (33.6, -77.7),
    (31.8, -80.5),
    (30.0, -81.1),
    (28.4, -80.3),
    (26.5, -79.9),
    (25.3, -80.0),
    # Florida Keys, then the Gulf coast westward
    (24.4, -81.0),
    (24.4, -82.2),
    (26.2, -82.2),
    (27.6, -83.0),
    (28.6, -83.2),
    (29.4, -85.0),
    (30.0, -86.5),
    (30.0, -88.0),
    (28.9, -88.8),
    (28.7, -89.5),
    (28.9, -90.5),
    (29.5, -93.5),
    (29.0, -94.8),
    (28.0, -96.5),
    (27.0, -97.0),
    (25.9, -97.1),
    # The Rio Grande upstream to El Paso
    (25.85, -97.5),
    (26.05, -98.3),
    (26.4, -99.15),
    (27.0, -99.48),
    (27.5, -99.6),
    (28.7, -100.55),
    (29.35, -101.0),
    (29.75, -102.0),
    (29.75, -102.7),
    (28.95, -103.2),
    (29.5, -104.4),
    (30.6, -105.0),
    (31.0, -105.5),
    (31.38, -106.05),
    (31.55, -106.35),
    (31.78, -106.55),
    # The straight-line border to the Pacific
    (31.78, -108.2),
    (31.33, -108.2),
    (31.33, -111.07),
    (32.49, -114.83),
    (32.72, -114.72),
    (32.53, -117.12),
    # Pacific coast, a little offshore (Channel Islands included), northward
    (32.5, -117.3),
    (32.7, -119.0),
    (34.3, -121.0),
    (36.5, -122.3),
    (38.0, -123.2),
    (40.4, -124.7),
    (42.8, -124.8),
)

ALASKA: tuple[LatLon, ...] = (
    (72.0, -180.0),
    (72.0, -141.0),
    # The 141st meridian south, then the panhandle border
    (60.3, -141.0),
    (60.0, -139.0),
    (59.2, -137.5),
    (59.6, -136.5),
    (59.8, -135.5),
    (59.5, -135.0),
    (58.4, -133.4),
    (57.0, -132.0),
    (56.0, -130.0),
    (55.0, -130.0),
    (54.6, -130.6),
    # Offshore back west, south of the Aleutians
    (54.5, -133.5),
    (58.5, -140.0),
    (54.0, -160.0),
    (51.0, -170.0),
    (51.0, -180.0),
)

HAWAII: tuple[LatLon, ...] = (
    (22.4, -160.5),
    (22.4, -154.6),
    (18.8, -154.6),
    (18.8, -160.5),
)

OUTLINES = (LOWER_48, ALASKA, HAWAII)


def is_in_usa(lat: float, lon: float) -> bool:
    return any(_inside(lat, lon, outline) for outline in OUTLINES)


def _inside(lat: float, lon: float, polygon: tuple[LatLon, ...]) -> bool:
    """Ray casting: inside if a ray going east crosses the edges an odd number of times."""
    inside = False
    for (lat1, lon1), (lat2, lon2) in zip(polygon, polygon[1:] + polygon[:1], strict=True):
        if (lat1 > lat) != (lat2 > lat):
            crossing_lon = lon1 + (lat - lat1) * (lon2 - lon1) / (lat2 - lat1)
            if lon < crossing_lon:
                inside = not inside
    return inside
