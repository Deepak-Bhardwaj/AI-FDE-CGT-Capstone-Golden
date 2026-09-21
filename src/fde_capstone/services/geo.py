"""Local geography reference.

City-level coordinates for every synthetic treatment centre and manufacturing site, held
locally so the application makes no external geocoding or map-tile request. Coordinates are
approximate and exist only to position markers on the route schematic.
"""
from __future__ import annotations

import math

# site_id -> (latitude, longitude, display city)
COORDS: dict[str, tuple[float, float, str]] = {
    # Treatment centres
    "TC-US-ATL-01": (33.749, -84.388, "Atlanta"),
    "TC-US-BOS-02": (42.360, -71.059, "Boston"),
    "TC-US-SF-03": (37.775, -122.419, "San Francisco"),
    "TC-US-CHI-04": (41.878, -87.630, "Chicago"),
    "TC-GB-LON-01": (51.507, -0.128, "London"),
    "TC-GB-MAN-02": (53.481, -2.242, "Manchester"),
    "TC-DE-BER-01": (52.520, 13.405, "Berlin"),
    "TC-DE-MUC-02": (48.135, 11.582, "Munich"),
    "TC-FR-PAR-01": (48.857, 2.352, "Paris"),
    "TC-NL-AMS-01": (52.370, 4.895, "Amsterdam"),
    "TC-ES-MAD-01": (40.417, -3.704, "Madrid"),
    "TC-IT-MIL-01": (45.464, 9.190, "Milan"),
    "TC-JP-TYO-01": (35.676, 139.650, "Tokyo"),
    "TC-JP-OSA-02": (34.694, 135.502, "Osaka"),
    "TC-SG-SIN-01": (1.352, 103.820, "Singapore"),
    "TC-AU-SYD-01": (-33.869, 151.209, "Sydney"),
    "TC-AU-MEL-02": (-37.814, 144.963, "Melbourne"),
    "TC-AE-DXB-01": (25.205, 55.271, "Dubai"),
    "TC-CA-TOR-01": (43.653, -79.383, "Toronto"),
    "TC-CA-VAN-02": (49.283, -123.121, "Vancouver"),
    "TC-CH-ZRH-01": (47.377, 8.542, "Zurich"),
    "TC-SE-STO-01": (59.329, 18.069, "Stockholm"),
    "TC-BE-BRU-01": (50.851, 4.352, "Brussels"),
    "TC-IN-BLR-01": (12.972, 77.594, "Bengaluru"),
    # Manufacturing sites
    "MFG-US-NJ-01": (40.736, -74.172, "Newark, New Jersey"),
    "MFG-US-CA-02": (37.339, -121.895, "San Jose, California"),
    "MFG-DE-01": (50.110, 8.682, "Frankfurt"),
    "MFG-GB-01": (51.507, -0.128, "London"),
    "MFG-SG-01": (1.352, 103.820, "Singapore"),
    "MFG-JP-01": (35.676, 139.650, "Tokyo"),
}

EARTH_RADIUS_KM = 6371.0


def locate(site_id: str, name: str | None = None, country: str | None = None) -> dict:
    lat, lon, city = COORDS.get(site_id, (0.0, 0.0, "Unknown"))
    return {
        "site_id": site_id,
        "name": name or site_id,
        "city": city,
        "country": country,
        "lat": lat,
        "lon": lon,
        "known": site_id in COORDS,
    }


def distance_km(a: dict, b: dict) -> float:
    """Great-circle distance between two located points."""
    lat1, lon1 = math.radians(a["lat"]), math.radians(a["lon"])
    lat2, lon2 = math.radians(b["lat"]), math.radians(b["lon"])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return round(2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(h))), 1)


def interpolate(a: dict, b: dict, fraction: float) -> dict:
    """Point along the great-circle path. Used to estimate an in-transit position."""
    fraction = max(0.0, min(1.0, fraction))
    lat1, lon1 = math.radians(a["lat"]), math.radians(a["lon"])
    lat2, lon2 = math.radians(b["lat"]), math.radians(b["lon"])

    d = distance_km(a, b) / EARTH_RADIUS_KM
    if d == 0:
        return {"lat": a["lat"], "lon": a["lon"], "fraction": fraction}

    sin_d = math.sin(d)
    p = math.sin((1 - fraction) * d) / sin_d
    q = math.sin(fraction * d) / sin_d
    x = p * math.cos(lat1) * math.cos(lon1) + q * math.cos(lat2) * math.cos(lon2)
    y = p * math.cos(lat1) * math.sin(lon1) + q * math.cos(lat2) * math.sin(lon2)
    z = p * math.sin(lat1) + q * math.sin(lat2)

    return {
        "lat": round(math.degrees(math.atan2(z, math.hypot(x, y))), 4),
        "lon": round(math.degrees(math.atan2(y, x)), 4),
        "fraction": round(fraction, 4),
    }
