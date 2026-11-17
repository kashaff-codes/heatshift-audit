import pytest

from heatshift.geo import (haversine_m, in_contiguous_us, iter_features, nearest_feature,
                           polygon_area_m2, square_aoi)


def test_us_bbox():
    assert in_contiguous_us(33.4484, -112.0740)      # Phoenix
    assert in_contiguous_us(25.7617, -80.1918)       # Miami
    assert not in_contiguous_us(24.8607, 67.0011)    # Karachi
    assert not in_contiguous_us(61.2181, -149.9003)  # Anchorage (outside contiguous US)


def test_square_aoi_is_closed_and_sized():
    poly = square_aoi(33.4484, -112.0740, side_m=300)
    ring = poly["coordinates"][0]
    assert poly["type"] == "Polygon" and len(ring) == 5 and ring[0] == ring[-1]
    assert polygon_area_m2(poly) == pytest.approx(300 * 300, rel=0.01)
    # lon, lat order: longitudes are negative in the US
    assert all(p[0] < 0 < p[1] for p in ring)
    # centred on the site
    lons = [p[0] for p in ring[:-1]]
    lats = [p[1] for p in ring[:-1]]
    assert sum(lons) / 4 == pytest.approx(-112.0740, abs=1e-6)
    assert sum(lats) / 4 == pytest.approx(33.4484, abs=1e-6)


def test_square_side_lengths():
    poly = square_aoi(29.76, -95.37, side_m=300)
    (x0, y0), (x1, _), (_, y2) = poly["coordinates"][0][:3]
    assert haversine_m(y0, x0, y0, x1) == pytest.approx(300, rel=0.01)
    assert haversine_m(y0, x1, y2, x1) == pytest.approx(300, rel=0.01)


def _tile(lat, lon, temp, d=0.0005):
    ring = [[lon - d, lat - d], [lon + d, lat - d], [lon + d, lat + d], [lon - d, lat + d], [lon - d, lat - d]]
    return {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [ring]},
            "properties": {"average_temperature": temp}}


def test_nearest_feature():
    fc = {"type": "FeatureCollection", "features": [_tile(33.449, -112.075, 40.1), _tile(33.4484, -112.0740, 40.9)]}
    f, d = nearest_feature(iter_features(fc), 33.4484, -112.0740)
    assert f["properties"]["average_temperature"] == 40.9 and d < 1
    assert list(iter_features([fc, fc])) and len(list(iter_features([fc, fc]))) == 4
    assert nearest_feature([], 0, 0) == (None, None)
