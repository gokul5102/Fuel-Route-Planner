"""Decode Google's Encoded Polyline format, which OSRM uses for `geometries=polyline6`.

Each point is stored as the difference from the previous one, in units of 10**-precision
degrees. Each number is zig-zag encoded (the sign goes in the lowest bit) and written as
5-bit groups, lowest first, one printable character per group (value + 63, with 0x20 set
while more groups follow). A polyline is about a fifth the size of the same GeoJSON.
"""


def decode(encoded: str, precision: int = 6) -> list[tuple[float, float]]:
    """The (lat, lon) points of a polyline. OSRM's polyline6 has precision 6.

    Raises ValueError if the text is cut short (mid-number, or a lat without its lon).
    """
    factor = 10**precision
    numbers = []
    value = shift = 0
    for char in encoded:
        group = ord(char) - 63
        value |= (group & 0x1F) << shift
        shift += 5
        if group < 0x20:  # the last group of this number
            numbers.append(~(value >> 1) if value & 1 else value >> 1)
            value = shift = 0
    if shift:
        raise ValueError("The polyline ends in the middle of a number.")

    points = []
    lat = lon = 0
    for lat_delta, lon_delta in zip(numbers[::2], numbers[1::2], strict=True):
        lat, lon = lat + lat_delta, lon + lon_delta
        points.append((lat / factor, lon / factor))
    return points
