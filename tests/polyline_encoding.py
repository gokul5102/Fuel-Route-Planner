"""A polyline encoder, for tests and for converting recorded OSRM fixtures.

The app only ever decodes (OSRM encodes); this is the inverse of routing.services.polyline.
"""


def encode(points: list[tuple[float, float]], precision: int = 6) -> str:
    """Encode (lat, lon) points with Google's polyline algorithm at 10**-precision degrees."""
    factor = 10**precision
    chunks = []
    previous_lat = previous_lon = 0
    for lat, lon in points:
        lat_units, lon_units = round(lat * factor), round(lon * factor)
        for delta in (lat_units - previous_lat, lon_units - previous_lon):
            value = ~(delta << 1) if delta < 0 else delta << 1
            while value >= 0x20:
                chunks.append(chr((0x20 | (value & 0x1F)) + 63))
                value >>= 5
            chunks.append(chr(value + 63))
        previous_lat, previous_lon = lat_units, lon_units
    return "".join(chunks)
