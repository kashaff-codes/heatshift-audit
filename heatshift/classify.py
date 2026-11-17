"""Hour classification and safest-work-window logic."""

from __future__ import annotations

from dataclasses import dataclass

from . import config


def heat_index_category(hi_f: float | None) -> str:
    if hi_f is None:
        return "Unknown"
    for lower, label in config.HEAT_INDEX_CATEGORIES_F:
        if hi_f >= lower:
            return label
    return "OK"


def aqi_category(aqi: float | None) -> str:
    if aqi is None:
        return "Unknown"
    for lower, label in config.AQI_BANDS:
        if aqi >= lower:
            return label
    return "Good"


def aqi_flag(aqi: float | None) -> bool:
    return aqi is not None and aqi >= config.AQI_FLAG_AT


def wet_bulb_flag(wb_c: float | None, warn_c: float = config.WET_BULB_WARN_C) -> bool:
    return wb_c is not None and wb_c >= warn_c


def is_workable(category: str, aqi: float | None) -> bool:
    """OK/Caution heat index and AQI below the flag level (unknown AQI does not block)."""
    return category in config.WORKABLE_CATEGORIES and not aqi_flag(aqi)


@dataclass
class Window:
    start: str
    end: str
    hours: list[str]

    def label(self) -> str:
        return self.start if self.start == self.end else f"{self.start}–{self.end}"


def _runs(hours: list[str], flags: list[bool]) -> list[list[str]]:
    runs, cur = [], []
    for h, ok in zip(hours, flags):
        if ok:
            cur.append(h)
        elif cur:
            runs.append(cur)
            cur = []
    if cur:
        runs.append(cur)
    return runs


def safest_window(rows: list[dict]) -> Window | None:
    """Longest continuous run of sampled hours that are workable. Ties -> earliest.

    rows: [{"hour": "06:00", "category": "OK", "aqi": 40.0}, ...] in time order.
    """
    hours = [r["hour"] for r in rows]
    flags = [is_workable(r["category"], r.get("aqi")) for r in rows]
    runs = _runs(hours, flags)
    if not runs:
        return None
    best = max(runs, key=len)  # max() keeps the first of equal-length runs
    return Window(best[0], best[-1], best)


def avoid_windows(rows: list[dict], at_or_above: str = "Danger") -> list[Window]:
    order = [label for _, label in reversed(config.HEAT_INDEX_CATEGORIES_F)]
    level = order.index(at_or_above)
    hours = [r["hour"] for r in rows]
    flags = [r["category"] in order and order.index(r["category"]) >= level for r in rows]
    return [Window(run[0], run[-1], run) for run in _runs(hours, flags)]


def worst_category(rows: list[dict]) -> str:
    order = [label for _, label in reversed(config.HEAT_INDEX_CATEGORIES_F)]
    known = [r["category"] for r in rows if r["category"] in order]
    return max(known, key=order.index) if known else "Unknown"
