from heatshift.classify import (aqi_category, aqi_flag, avoid_windows, heat_index_category,
                                safest_window, wet_bulb_flag, worst_category)


def rows(*spec):
    return [{"hour": h, "category": c, "aqi": a} for h, c, a in spec]


def test_heat_index_category_boundaries():
    assert heat_index_category(79.9) == "OK"
    assert heat_index_category(80) == "Caution"
    assert heat_index_category(90) == "Extreme Caution"
    assert heat_index_category(102.9) == "Extreme Caution"
    assert heat_index_category(103) == "Danger"
    assert heat_index_category(124.9) == "Danger"
    assert heat_index_category(125) == "Extreme Danger"
    assert heat_index_category(None) == "Unknown"


def test_aqi_bands():
    assert aqi_category(0) == "Good"
    assert aqi_category(50) == "Good"
    assert aqi_category(51) == "Moderate"
    assert aqi_category(101) == "Unhealthy for Sensitive Groups"
    assert aqi_category(151) == "Unhealthy"
    assert aqi_category(201) == "Very Unhealthy"
    assert aqi_category(301) == "Hazardous"
    assert not aqi_flag(100.9) and aqi_flag(101) and not aqi_flag(None)


def test_wet_bulb_flag():
    assert wet_bulb_flag(28.0) and not wet_bulb_flag(27.9) and not wet_bulb_flag(None)
    assert wet_bulb_flag(26, warn_c=25)


def test_safest_window_longest_run():
    r = rows(("06:00", "OK", 30), ("09:00", "Caution", 40), ("12:00", "Danger", 40),
             ("15:00", "Danger", 40), ("18:00", "Caution", 40))
    w = safest_window(r)
    assert w.label() == "06:00–09:00" and w.hours == ["06:00", "09:00"]


def test_safest_window_aqi_blocks_hour():
    r = rows(("06:00", "OK", 120), ("09:00", "OK", 40), ("12:00", "OK", 40), ("15:00", "Danger", 40))
    assert safest_window(r).label() == "09:00–12:00"


def test_safest_window_tie_prefers_earliest_and_single():
    r = rows(("06:00", "OK", 10), ("09:00", "Danger", 10), ("12:00", "OK", 10))
    assert safest_window(r).label() == "06:00"


def test_safest_window_none():
    assert safest_window(rows(("12:00", "Danger", 10), ("15:00", "Extreme Caution", 10))) is None


def test_unknown_aqi_does_not_block():
    assert safest_window(rows(("06:00", "OK", None))).label() == "06:00"


def test_avoid_windows_and_worst():
    r = rows(("06:00", "OK", 1), ("09:00", "Danger", 1), ("12:00", "Extreme Danger", 1),
             ("15:00", "Extreme Caution", 1), ("18:00", "Danger", 1))
    assert [w.label() for w in avoid_windows(r)] == ["09:00–12:00", "18:00"]
    assert worst_category(r) == "Extreme Danger"
