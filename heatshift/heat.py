"""Unit conversions and the NWS heat index (Rothfusz regression + NWS adjustments).

Reference: https://www.wpc.ncep.noaa.gov/html/heatindex_equation.shtml
"""

from __future__ import annotations

import math


def c_to_f(c: float) -> float:
    return c * 9.0 / 5.0 + 32.0


def f_to_c(f: float) -> float:
    return (f - 32.0) * 5.0 / 9.0


def heat_index_f(temp_f: float, rh: float) -> float:
    """NWS heat index in degrees F from air temperature (F) and relative humidity (%)."""
    t, r = float(temp_f), float(rh)
    # Steadman's simple formula first; NWS uses it when the average with T is < 80 F.
    simple = 0.5 * (t + 61.0 + (t - 68.0) * 1.2 + r * 0.094)
    if (simple + t) / 2.0 < 80.0:
        return simple

    hi = (-42.379 + 2.04901523 * t + 10.14333127 * r
          - 0.22475541 * t * r - 0.00683783 * t * t - 0.05481717 * r * r
          + 0.00122874 * t * t * r + 0.00085282 * t * r * r
          - 0.00000199 * t * t * r * r)

    if r < 13.0 and 80.0 <= t <= 112.0:
        hi -= ((13.0 - r) / 4.0) * math.sqrt((17.0 - abs(t - 95.0)) / 17.0)
    elif r > 85.0 and 80.0 <= t <= 87.0:
        hi += ((r - 85.0) / 10.0) * ((87.0 - t) / 5.0)
    return hi


def heat_index_c(temp_c: float, rh: float) -> float:
    return f_to_c(heat_index_f(c_to_f(temp_c), rh))
