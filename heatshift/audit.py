"""Heat Shift Audit pipeline.

FortyGuard heatmap (site temperature per sampled hour)
    -> FortyGuard env_params (humidity, apparent temp, wet-bulb, AQI ...)
    -> local NWS heat index + checks -> hourly categories + safest work window.

env_params modes
----------------
range (default): one env_params call with filter_type 2 covering the window.
    Phase A test T1 showed the provider fields (RH, apparent temperature,
    wet-bulb, AQI, cloud) are genuinely hourly, but the API's
    heat_index_celsius applies the single `temperature` input to every hour.
    So we pass the hottest sampled hour's heatmap temperature, and recompute
    heat index locally for each hour from that hour's heatmap temperature.
    Cost: N heatmaps + 1 env_params.
per-hour: one env_params call per sampled hour with that hour's heatmap
    temperature. API heat index is then directly comparable for every hour.
    Cost: N heatmaps + N env_params.
"""

from __future__ import annotations

import datetime as dt
import re
import statistics
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from . import config
from .classify import (aqi_category, aqi_flag, avoid_windows, heat_index_category, safest_window,
                       wet_bulb_flag, worst_category)
from .client import ActivityResult, FortyGuardClient, FortyGuardError
from .geo import in_contiguous_us, iter_features, nearest_feature, square_aoi
from .heat import c_to_f, heat_index_c, heat_index_f


# ---------------------------------------------------------------- inputs
@dataclass
class AuditInputs:
    lat: float
    lon: float
    date: str
    start: str = "06:00"
    end: str = "18:00"
    every: int = 3
    name: str | None = None
    env_mode: str = "range"
    granularity: int = config.HEATMAP_GRANULARITY_M
    aoi_side_m: float = config.AOI_SIDE_M
    wet_bulb_warn_c: float = config.WET_BULB_WARN_C
    concurrency: int = 2

    @property
    def site_name(self) -> str:
        return self.name or f"site {self.lat:.4f},{self.lon:.4f}"

    @property
    def slug(self) -> str:
        return re.sub(r"[^a-z0-9]+", "-", self.site_name.lower()).strip("-")[:60] or "site"


class InputError(ValueError):
    pass


def _parse_hhmm(value: str) -> int:
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", value.strip())
    if not m:
        raise InputError(f"time must be HH:MM, got {value!r}")
    h, mnt = int(m.group(1)), int(m.group(2))
    if not (0 <= h <= 23) or mnt != 0:
        raise InputError(f"time must be a whole hour between 00:00 and 23:00, got {value!r}")
    return h


def validate(inp: AuditInputs, today: dt.date | None = None) -> list[str]:
    """Raise InputError on bad input; return the sampled hours as HH:MM strings."""
    if not in_contiguous_us(inp.lat, inp.lon):
        raise InputError("location is outside the contiguous US (FortyGuard coverage is US-only)")
    try:
        day = dt.date.fromisoformat(inp.date)
    except ValueError:
        raise InputError(f"date must be YYYY-MM-DD, got {inp.date!r}")
    today = today or dt.date.today()
    if day >= today:
        raise InputError("date must be in the past: FortyGuard env_params does not support future "
                         "dates (and today's later hours are not available yet)")
    if day < dt.date.fromisoformat(config.EARLIEST_DATE):
        raise InputError(f"date must be on or after {config.EARLIEST_DATE}")
    h0, h1 = _parse_hhmm(inp.start), _parse_hhmm(inp.end)
    if h0 >= h1:
        raise InputError("--start must be before --end")
    if inp.every < 1:
        raise InputError("--every must be >= 1")
    if inp.env_mode not in ("range", "per-hour"):
        raise InputError("--env-mode must be 'range' or 'per-hour'")
    if inp.granularity not in (60, 80, 100):
        raise InputError("--granularity must be 60, 80 or 100")
    return [f"{h:02d}:00" for h in range(h0, h1 + 1, inp.every)]


# ---------------------------------------------------------------- request bodies
def heatmap_body(inp: AuditInputs, hour: str) -> dict:
    return {
        "polygon_aoi": square_aoi(inp.lat, inp.lon, inp.aoi_side_m),
        "date_time": {"start_date": inp.date, "end_date": inp.date, "start_time": hour, "filter_type": 1},
        "granularity": inp.granularity,
        "analytic_type": "tcm",
    }


def env_body(inp: AuditInputs, temperature_c: float, start: str, end: str | None = None) -> dict:
    d = {"start_date": inp.date, "end_date": inp.date, "start_time": start, "filter_type": 1}
    if end and end != start:
        d.update(end_time=end, filter_type=2)
    return {"latitude": inp.lat, "longitude": inp.lon, "temperature": round(temperature_c, 2), "date_time": d}


@dataclass
class PlannedCall:
    endpoint: str
    label: str
    body: dict | None  # None when it depends on earlier results
    cached: bool = False

    @property
    def credits(self) -> int:
        return 0 if self.cached else config.CREDIT_COST[self.endpoint]


def plan(inp: AuditInputs, hours: list[str], client: FortyGuardClient | None = None) -> list[PlannedCall]:
    calls: list[PlannedCall] = []
    for h in hours:
        body = heatmap_body(inp, h)
        cached = bool(client and client.cache.get("/v1/heatmap", body))
        calls.append(PlannedCall("/v1/heatmap", f"heatmap {h}", body, cached))
    if inp.env_mode == "range":
        label = f"env_params {hours[0]}–{hours[-1]} (range)" if len(hours) > 1 else f"env_params {hours[0]}"
        calls.append(PlannedCall("/v1/env_params", label, None))
    else:
        calls.extend(PlannedCall("/v1/env_params", f"env_params {h}", None) for h in hours)

    # env bodies depend on heatmap temperatures; if every heatmap is cached we can resolve them now.
    if client and all(c.cached for c in calls if c.endpoint == "/v1/heatmap"):
        temps = {}
        for h in hours:
            rec = client.cache.get("/v1/heatmap", heatmap_body(inp, h))
            temps[h] = site_temperature(rec.get("result"), inp.lat, inp.lon).get("site_c")
        if all(v is not None for v in temps.values()):
            for c, body in zip([c for c in calls if c.endpoint == "/v1/env_params"], env_bodies(inp, hours, temps)):
                c.body = body
                c.cached = bool(client.cache.get("/v1/env_params", body))
    return calls


def env_bodies(inp: AuditInputs, hours: list[str], temps: dict[str, float | None]) -> list[dict]:
    if inp.env_mode == "range":
        known = {h: t for h, t in temps.items() if t is not None}
        ref = max(known.values()) if known else 35.0
        return [env_body(inp, ref, hours[0], hours[-1])]
    return [env_body(inp, temps[h], h) for h in hours if temps.get(h) is not None]


# ---------------------------------------------------------------- parsing
def _num(v: Any) -> float | None:
    if isinstance(v, bool) or v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f in config.SENTINELS else f


def _tile_temp(props: dict) -> float | None:
    for key in ("average_temperature", "avg_temperature", "temperature", "mean_temperature"):
        if key in props:
            return _num(props[key])
    return None


def site_temperature(result: Any, lat: float, lon: float) -> dict:
    """Site temperature = tile nearest the site centre; plus AOI min/mean/max from all tiles."""
    out: dict[str, Any] = {"site_c": None, "aoi_min_c": None, "aoi_mean_c": None, "aoi_max_c": None,
                           "tiles": 0, "nearest_tile_m": None, "stats_data": None, "sentinels": 0}
    if not isinstance(result, dict):
        return out
    feats = list(iter_features(result.get("map_data")))
    temps, valid = [], []
    for f in feats:
        raw = (f.get("properties") or {})
        t = _tile_temp(raw)
        if t is None and any(k in raw for k in ("average_temperature", "temperature")):
            out["sentinels"] += 1
        if t is not None:
            temps.append(t)
            valid.append(f)
    out["tiles"] = len(feats)
    out["stats_data"] = result.get("stats_data")
    if temps:
        out.update(aoi_min_c=min(temps), aoi_max_c=max(temps), aoi_mean_c=statistics.fmean(temps))
        f, d = nearest_feature(valid, lat, lon)
        out["site_c"] = _tile_temp(f["properties"]) if f else None
        out["nearest_tile_m"] = round(d, 1) if d is not None else None
    return out


AQI_KEYS = ("air_quality:idx", "aqi_us")
ENV_FIELDS = {
    "heat_index_api_c": ("heat_index_celsius",),
    "apparent_c": ("apparent_temperature_celsius",),
    "wet_bulb_c": ("wet_bulb_temperature_celsius",),
    "rh": ("relative_humidity_percent",),
    "aqi": AQI_KEYS,
    "cloud_octas": ("cloud_cover_octas",),
    "precip_mm": ("precipitation_mm",),
}


def env_by_hour(result: Any) -> tuple[dict[str, dict], dict]:
    """Map 'HH:MM' -> {field: value} from an env_params result. Also returns metadata."""
    if not isinstance(result, dict):
        return {}, {}
    meta = result.get("metadata", {}) or {}
    stamps = meta.get("timestamps") or []
    locs = result.get("locations") or []
    loc = locs[0] if locs else {}
    params = loc.get("parameters", {}) or {}
    hours = {}
    for i, ts in enumerate(stamps):
        hh = str(ts)[11:16]
        row = {}
        for out_key, keys in ENV_FIELDS.items():
            for k in keys:
                if k in params:
                    arr = params[k]
                    val = arr[i] if isinstance(arr, list) and i < len(arr) else arr
                    row[out_key] = _num(val)
                    row[f"_raw_{out_key}"] = val
                    break
        hours[hh] = row
    solar = (loc.get("solar_irradiance") or {}).get("clear_sky") or {}
    meta = dict(meta, input_temperature_c=loc.get("temperature"), clear_sky_ghi=solar.get("ghi"),
                solar_description=(loc.get("solar_irradiance") or {}).get("description"))
    return hours, meta


# ---------------------------------------------------------------- the run
@dataclass
class AuditResult:
    inputs: AuditInputs
    hours: list[str]
    rows: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    calls: list[dict] = field(default_factory=list)
    credits_before: dict | None = None
    credits_after: dict | None = None
    summary: str = ""
    window: Any = None
    avoid: list = field(default_factory=list)
    timezone: str | None = None


class CircuitBreaker:
    """Stop submitting paid jobs after a 5xx on submit.

    Observed 17 Nov 2026: during FortyGuard 504 incidents a submit can fail with
    504 yet still create and charge the job. Continuing to submit would burn
    credits for results we can never retrieve.
    """

    def __init__(self):
        self.tripped: str | None = None

    def guard(self, client: FortyGuardClient, endpoint: str, body: dict, label: str):
        if self.tripped and not client.cache.get(endpoint, body):
            return FortyGuardError(f"skipped — not submitted because an earlier submit failed ({self.tripped})")
        try:
            return client.run(endpoint, body)
        except FortyGuardError as exc:
            if exc.status_code and exc.status_code >= 500 and exc.activity_id is None:
                self.tripped = self.tripped or f"HTTP {exc.status_code} on {label}"
            return exc
        except Exception as exc:  # never let one call crash the whole audit
            self.tripped = self.tripped or f"{type(exc).__name__} on {label}"
            return FortyGuardError(client._redact(f"{type(exc).__name__}: {exc}"))


class ServiceUnavailable(FortyGuardError):
    pass


def preflight(client: FortyGuardClient) -> dict | None:
    """Free health check (credits endpoint). Raises ServiceUnavailable on 5xx/network errors."""
    try:
        return client.credits().get("credit_summary")
    except FortyGuardError as exc:
        if exc.status_code is None or exc.status_code >= 500:
            raise ServiceUnavailable(f"FortyGuard API looks unavailable ({exc}); no paid calls were made. "
                                     f"Try again later.", status_code=exc.status_code)
        raise


def _record(res, label: str, endpoint: str, body: dict) -> dict:
    if isinstance(res, FortyGuardError):
        return {"label": label, "endpoint": endpoint, "status": "Rejected", "http_status": res.status_code,
                "activity_id": res.activity_id, "error": str(res), "request": body}
    d = res.to_dict()
    d["label"] = label
    return d


def run_audit(inp: AuditInputs, client: FortyGuardClient, hours: list[str]) -> AuditResult:
    out = AuditResult(inputs=inp, hours=hours)
    out.credits_before = preflight(client)  # raises ServiceUnavailable before any paid call
    breaker = CircuitBreaker()
    _call = breaker.guard

    # 1) heatmaps, one per sampled hour
    with ThreadPoolExecutor(max_workers=max(1, inp.concurrency)) as pool:
        futures = {h: pool.submit(_call, client, "/v1/heatmap", heatmap_body(inp, h), f"heatmap {h}") for h in hours}
        hm = {h: f.result() for h, f in futures.items()}
    site: dict[str, dict] = {}
    for h in hours:
        res = hm[h]
        out.calls.append(_record(res, f"heatmap {h}", "/v1/heatmap", heatmap_body(inp, h)))
        if isinstance(res, ActivityResult) and res.ok:
            site[h] = site_temperature(res.result, inp.lat, inp.lon)
        else:
            site[h] = {"site_c": None}
            err = str(res) if isinstance(res, FortyGuardError) else f"{res.status} (no reason given)"
            aid = res.activity_id
            out.notes.append(f"{h}: heatmap did not complete — {err}" + (f" [activity_id={aid}]" if aid and aid not in err else ""))

    temps = {h: site[h].get("site_c") for h in hours}

    # 2) env_params
    env: dict[str, dict] = {}
    env_meta: dict = {}
    bodies = env_bodies(inp, hours, temps)
    if not any(t is not None for t in temps.values()):
        out.notes.append("No heatmap temperature available, so env_params was not called (nothing to classify).")
        bodies = []
    if breaker.tripped:
        out.notes.append(f"Stopped submitting new paid jobs after {breaker.tripped}: FortyGuard can create and "
                         f"charge for a job even when the submit returns 5xx. Compare credits before/after.")
    with ThreadPoolExecutor(max_workers=max(1, inp.concurrency)) as pool:
        env_results = list(pool.map(lambda b: (b, _call(client, "/v1/env_params", b, "env_params")), bodies))
    for body, res in env_results:
        d = body["date_time"]
        label = f"env_params {d['start_time']}" + (f"–{d['end_time']}" if d.get("end_time") else "")
        out.calls.append(_record(res, label, "/v1/env_params", body))
        if isinstance(res, ActivityResult) and res.ok:
            by_hour, meta = env_by_hour(res.result)
            env_meta = env_meta or meta
            for hh, row in by_hour.items():
                env[hh] = row | {"_input_temperature_c": meta.get("input_temperature_c")}
        else:
            err = str(res) if isinstance(res, FortyGuardError) else f"{res.status} (no reason given)"
            out.notes.append(f"{label}: did not complete — {err}"
                             + (f" [activity_id={res.activity_id}]"
                                if res.activity_id and res.activity_id not in err else ""))
    out.timezone = env_meta.get("timezone")

    # 3) rows + checks
    formula_gaps, range_gaps, flat, apparent_gaps = [], [], [], []
    for h in hours:
        s, e = site.get(h, {}), env.get(h, {})
        t = s.get("site_c")
        rh = e.get("rh")
        hi_local_c = heat_index_c(t, rh) if t is not None and rh is not None else None
        hi_local_f = heat_index_f(c_to_f(t), rh) if hi_local_c is not None else None
        hi_api = e.get("heat_index_api_c")
        t_in = e.get("_input_temperature_c")
        row = {
            "hour": h,
            "site_temp_c": t, "site_temp_f": c_to_f(t) if t is not None else None,
            "aoi_min_c": s.get("aoi_min_c"), "aoi_max_c": s.get("aoi_max_c"), "aoi_mean_c": s.get("aoi_mean_c"),
            "aoi_range_c": (s["aoi_max_c"] - s["aoi_min_c"]) if s.get("aoi_max_c") is not None else None,
            "tiles": s.get("tiles"), "nearest_tile_m": s.get("nearest_tile_m"),
            "heat_index_local_c": hi_local_c, "heat_index_local_f": hi_local_f,
            "heat_index_api_c": hi_api, "env_input_temperature_c": t_in,
            "apparent_c": e.get("apparent_c"), "wet_bulb_c": e.get("wet_bulb_c"), "rh": rh,
            "aqi": e.get("aqi"), "cloud_octas": e.get("cloud_octas"), "precip_mm": e.get("precip_mm"),
        }
        row["category"] = heat_index_category(hi_local_f)
        row["aqi_category"] = aqi_category(row["aqi"])
        row["aqi_flag"] = aqi_flag(row["aqi"])
        row["wet_bulb_flag"] = wet_bulb_flag(row["wet_bulb_c"], inp.wet_bulb_warn_c)
        out.rows.append(row)

        # --- data-quality notes (grouped across hours below)
        if row["aoi_range_c"] is not None and row["aoi_range_c"] < config.DQ_FLAT_RANGE_C:
            flat.append((h, row["aoi_range_c"], row["tiles"]))
        if hi_api is not None and t_in is not None and rh is not None:
            # Does the API's heat index match NWS for the temperature it was actually given?
            expected = heat_index_c(t_in, rh)
            if abs(expected - hi_api) > config.DQ_HEAT_INDEX_MISMATCH_C:
                formula_gaps.append((h, hi_api, expected))
            if hi_local_c is not None and abs(hi_api - hi_local_c) > config.DQ_HEAT_INDEX_MISMATCH_C:
                range_gaps.append((h, hi_api, hi_local_c, t_in, t))
        if hi_local_c is not None and row["apparent_c"] is not None and \
                abs(hi_local_c - row["apparent_c"]) > config.DQ_APPARENT_GAP_C:
            apparent_gaps.append((h, row["apparent_c"], hi_local_c))
        for k, v in e.items():
            if k.startswith("_raw_") and (v is None or _num(v) is None):
                out.notes.append(f"{h}: env_params field {k[5:]} is null or a sentinel ({v!r}).")
        if s.get("sentinels"):
            out.notes.append(f"{h}: {s['sentinels']} heatmap tiles had null/sentinel temperatures.")

    if flat:
        which = "every sampled hour" if len(flat) == len([r for r in out.rows if r["aoi_range_c"] is not None]) \
            else ", ".join(h for h, _, _ in flat)
        out.notes.append(
            f"Heatmap AOI temperature range < {config.DQ_FLAT_RANGE_C} °C at {which} "
            f"(max {max(r for _, r, _ in flat):.3f} °C across {max(n or 0 for _, _, n in flat)} tiles of "
            f"{inp.granularity} m): spatial variation negligible at this site, so the "
            f"{inp.granularity} m tiles carry no more detail than a single value.")
    if apparent_gaps:
        detail = "; ".join(f"{h} apparent {a:.1f} vs HI {hi:.1f} °C" for h, a, hi in apparent_gaps)
        out.notes.append(f"Provider apparent temperature and heat index differ by > {config.DQ_APPARENT_GAP_C:g} °C "
                         f"(two 'feels-like' metrics disagree): {detail}.")
    for h, api, exp in formula_gaps:
        out.notes.append(f"{h}: API heat index {api:.1f} °C ≠ NWS heat index {exp:.1f} °C for the same input "
                         f"temperature and humidity (> {config.DQ_HEAT_INDEX_MISMATCH_C} °C).")
    if range_gaps:
        worst = max(range_gaps, key=lambda g: abs(g[1] - g[2]))
        if inp.env_mode == "range":
            out.notes.append(
                f"env_params range call applies one input temperature ({worst[3]:.1f} °C) to every hour's "
                f"heat_index_celsius. Using the API value as-is would be off by up to "
                f"{abs(worst[1] - worst[2]):.1f} °C (at {worst[0]}: API {worst[1]:.1f} °C vs "
                f"{worst[2]:.1f} °C from that hour's heatmap temperature {worst[4]:.1f} °C). "
                f"The table uses the local value.")
        else:
            for h, api, loc, _, _ in range_gaps:
                out.notes.append(f"{h}: API heat index {api:.1f} °C vs local {loc:.1f} °C (> 1 °C).")
    if inp.env_mode == "range" and env_meta.get("solar_description"):
        out.notes.append(f"Solar irradiance from the range call is a single average, not hourly "
                         f"(clear-sky GHI {env_meta.get('clear_sky_ghi')} W/m²).")

    # 4) window + summary
    out.window = safest_window(out.rows)
    out.avoid = avoid_windows(out.rows, "Danger")
    parts = []
    parts.append(f"Safest window: {out.window.label()}." if out.window else
                 "No sampled hour was at OK/Caution with AQI < 101 — no safe window found in the sampled hours.")
    for w in out.avoid:
        worst = worst_category([r for r in out.rows if r["hour"] in w.hours])
        parts.append(f"Avoid {w.label()} ({worst}).")
    ext = [r["hour"] for r in out.rows if r["category"] == "Extreme Caution"]
    if ext:
        parts.append(f"Extreme Caution at {', '.join(ext)}.")
    if any(r["category"] == "Unknown" for r in out.rows):
        parts.append("Some hours could not be classified (see notes).")
    out.summary = " ".join(parts)

    try:
        out.credits_after = client.credits().get("credit_summary")
    except FortyGuardError as exc:
        out.notes.append(f"Could not read credits after the run: {exc}")
    return out
