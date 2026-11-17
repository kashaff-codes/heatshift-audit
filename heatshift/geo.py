"""Geometry helpers: square AOI around a site, contiguous-US check, nearest tile."""

from __future__ import annotations

import math
from typing import Iterable

# Contiguous US bounding box (approx.). FortyGuard coverage is US-only; the API
# itself returns 400 OUT_OF_COVERAGE outside it, this check just fails fast.
US_BBOX = {"min_lat": 24.396308, "max_lat": 49.384358, "min_lon": -124.848974, "max_lon": -66.885444}

EARTH_RADIUS_M = 6_371_008.8


def in_contiguous_us(lat: float, lon: float) -> bool:
    b = US_BBOX
    return b["min_lat"] <= lat <= b["max_lat"] and b["min_lon"] <= lon <= b["max_lon"]


def square_aoi(lat: float, lon: float, side_m: float = 300.0) -> dict:
    """Closed GeoJSON Polygon, side_m x side_m, centred on (lat, lon). [lon, lat] order."""
    half = side_m / 2.0
    dlat = math.degrees(half / EARTH_RADIUS_M)
    dlon = math.degrees(half / (EARTH_RADIUS_M * math.cos(math.radians(lat))))
    r = lambda v: round(v, 7)
    ring = [
        [r(lon - dlon), r(lat - dlat)],
        [r(lon + dlon), r(lat - dlat)],
        [r(lon + dlon), r(lat + dlat)],
        [r(lon - dlon), r(lat + dlat)],
        [r(lon - dlon), r(lat - dlat)],
    ]
    return {"type": "Polygon", "coordinates": [ring]}


def polygon_area_m2(polygon: dict) -> float:
    """Approximate planar area of a small lon/lat polygon (equirectangular)."""
    ring = polygon["coordinates"][0]
    lat0 = math.radians(sum(p[1] for p in ring) / len(ring))
    pts = [(math.radians(x) * EARTH_RADIUS_M * math.cos(lat0), math.radians(y) * EARTH_RADIUS_M) for x, y in ring]
    s = sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(pts, pts[1:]))
    return abs(s) / 2.0


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def _ring_centroid(geometry: dict) -> tuple[float, float] | None:
    gtype = geometry.get("type")
    coords = geometry.get("coordinates")
    if not coords:
        return None
    if gtype == "Point":
        return coords[1], coords[0]
    if gtype == "Polygon":
        ring = coords[0]
    elif gtype == "MultiPolygon":
        ring = coords[0][0]
    else:
        return None
    pts = ring[:-1] if len(ring) > 1 and ring[0] == ring[-1] else ring
    return sum(p[1] for p in pts) / len(pts), sum(p[0] for p in pts) / len(pts)


def iter_features(map_data) -> Iterable[dict]:
    """Yield GeoJSON features from a heatmap `map_data` (FeatureCollection or list)."""
    if isinstance(map_data, dict):
        if map_data.get("type") == "FeatureCollection":
            yield from map_data.get("features", [])
        elif map_data.get("type") == "Feature":
            yield map_data
        elif "features" in map_data:
            yield from map_data["features"]
    elif isinstance(map_data, list):
        for item in map_data:
            yield from iter_features(item)


def nearest_feature(features: Iterable[dict], lat: float, lon: float) -> tuple[dict | None, float | None]:
    best, best_d = None, None
    for f in features:
        c = _ring_centroid(f.get("geometry") or {})
        if c is None:
            continue
        d = haversine_m(lat, lon, c[0], c[1])
        if best_d is None or d < best_d:
            best, best_d = f, d
    return best, best_d
