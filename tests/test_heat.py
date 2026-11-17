import pytest

from heatshift.heat import c_to_f, f_to_c, heat_index_c, heat_index_f

# Values read from the NWS heat index chart (https://www.weather.gov/safety/heat-index).
# The chart is rounded to whole degrees, so allow +/- 1 F.
NWS_CHART = [
    (80, 40, 80),
    (90, 50, 95),
    (90, 70, 106),
    (94, 55, 106),
    (100, 40, 109),
    (96, 65, 121),
    (104, 40, 119),
    (86, 90, 105),
    (110, 40, 136),
]


@pytest.mark.parametrize("t,rh,expected", NWS_CHART)
def test_heat_index_matches_nws_chart(t, rh, expected):
    assert heat_index_f(t, rh) == pytest.approx(expected, abs=1.0)


def test_low_humidity_adjustment_applied():
    # Dry heat (Phoenix-like): RH < 13 % and 80-112 F subtracts the adjustment.
    raw_t, rh = 105.0, 8.0
    hi = heat_index_f(raw_t, rh)
    assert hi < raw_t  # very dry air: heat index below air temperature
    # Hand-computed from the published equation: Rothfusz 98.93 - adjustment 0.80 = 98.12
    assert hi == pytest.approx(98.12, abs=0.05)


def test_high_humidity_adjustment_applied():
    # RH > 85 % and 80-87 F adds the adjustment (chart: 84 F / 95 % -> 101 F... approx)
    assert heat_index_f(84, 95) == pytest.approx(101, abs=2.0)


def test_simple_formula_used_when_cool():
    # Below ~80 F the NWS uses Steadman's simple formula; heat index ~= temperature.
    # 0.5 * (70 + 61 + (70 - 68) * 1.2 + 50 * 0.094) = 69.05
    assert heat_index_f(70, 50) == pytest.approx(69.05, abs=0.01)


def test_unit_round_trip():
    for c in (-10, 0, 20.5, 40.8):
        assert f_to_c(c_to_f(c)) == pytest.approx(c)
    assert c_to_f(40.0) == pytest.approx(104.0)


def test_heat_index_c_consistent_with_f():
    assert heat_index_c(40.0, 23.2) == pytest.approx(f_to_c(heat_index_f(104.0, 23.2)))
