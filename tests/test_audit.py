"""End-to-end pipeline test against a mocked FortyGuard API (no network)."""

import datetime as dt
import json

import httpx
import pytest

from heatshift.audit import AuditInputs, InputError, plan, run_audit, validate
from heatshift.cache import DiskCache, request_key
from heatshift.client import FortyGuardClient
from heatshift.heat import heat_index_c
from heatshift.report import to_json, to_markdown

KEY = "test-key-123"
HOURS = ["06:00", "09:00", "12:00", "15:00", "18:00"]
SITE_T = {"06:00": 30.0, "09:00": 35.0, "12:00": 39.0, "15:00": 41.0, "18:00": 38.0}
RH = {"06:00": 30.0, "09:00": 25.0, "12:00": 20.0, "15:00": 15.0, "18:00": 18.0}


def tiles(lat, lon, centre_t):
    feats = []
    for i, (dy, dx) in enumerate([(0, 0), (0.001, 0), (0, 0.001)]):
        la, lo, d = lat + dy, lon + dx, 0.0004
        ring = [[lo - d, la - d], [lo + d, la - d], [lo + d, la + d], [lo - d, la + d], [lo - d, la - d]]
        feats.append({"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [ring]},
                      "properties": {"average_temperature": centre_t + 0.01 * i}})
    return {"type": "FeatureCollection", "features": feats}


class FakeAPI:
    def __init__(self):
        self.jobs, self.posts, self.status_calls = {}, [], {}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        assert request.headers.get("api-key") == KEY or request.url.path.endswith("fetch-api-key-usage")
        path = request.url.path
        if path == "/v1/system/fetch-api-key-usage":
            used = 4220 * sum(1 for p in self.posts if p[0] == "/v1/heatmap") + \
                   2900 * sum(1 for p in self.posts if p[0] == "/v1/env_params")
            return httpx.Response(200, json={"data": {"credit_summary": {
                "total_remaining_credits": 900000 - used, "cycle_remaining_credits": 910000 - used}}})
        if request.method == "POST":
            body = json.loads(request.content)
            self.posts.append((path, body))
            aid = f"act-{len(self.posts)}"
            self.jobs[aid] = (path, body)
            return httpx.Response(200, json={"error": False, "status_code": 200, "data": {"activity_id": aid}})
        if path.startswith("/v1/status/"):
            aid = path.rsplit("/", 1)[-1]
            n = self.status_calls[aid] = self.status_calls.get(aid, 0) + 1
            if n == 1:
                return httpx.Response(404, json={"message": "not found yet"})
            ep, body = self.jobs[aid]
            return httpx.Response(200, json={"data": {"status": "Completed", "result": self.result(ep, body)}})
        return httpx.Response(400, json={"message": "unexpected"})

    def result(self, ep, body):
        if ep == "/v1/heatmap":
            h = body["date_time"]["start_time"]
            ring = body["polygon_aoi"]["coordinates"][0]
            lat = sum(p[1] for p in ring[:-1]) / 4
            lon = sum(p[0] for p in ring[:-1]) / 4
            return {"map_data": tiles(lat, lon, SITE_T[h]), "stats_data": {"minimum": 0, "maximum": 0}}
        d = body["date_time"]
        h0 = int(d["start_time"][:2])
        h1 = int(d.get("end_time", d["start_time"])[:2])
        hrs = [f"{h:02d}:00" for h in range(h0, h1 + 1)]
        rh = [RH.get(h, 22.0) for h in hrs]
        t_in = body["temperature"]
        return {"metadata": {"timezone": "America/Phoenix",
                             "timestamps": [f"{body['date_time']['start_date']}T{h}:00-07:00" for h in hrs]},
                "locations": [{"temperature": t_in, "parameters": {
                    "heat_index_celsius": [round(heat_index_c(t_in, r), 1) for r in rh],
                    "apparent_temperature_celsius": [35.0] * len(hrs),
                    "wet_bulb_temperature_celsius": [20.0] * len(hrs),
                    "relative_humidity_percent": rh,
                    "air_quality:idx": [45.0] * (len(hrs) - 1) + [-999],
                    "cloud_cover_octas": [2] * len(hrs),
                    "precipitation_mm": [0.0] * len(hrs)},
                    "solar_irradiance": {"clear_sky": {"ghi": 600.0}, "description": "averaged"}}]}


@pytest.fixture
def api(tmp_path):
    fake = FakeAPI()
    http = httpx.Client(base_url="https://api.test", transport=httpx.MockTransport(fake))
    client = FortyGuardClient(api_key=KEY, base_url="https://api.test", cache=DiskCache(tmp_path / "cache"),
                              poll_interval=0, sleep=lambda s: None, http=http)
    return fake, client


def inputs(**kw):
    return AuditInputs(lat=33.4484, lon=-112.0740, date="2026-07-15", name="Test site", **kw)


def test_validate_rules():
    today = dt.date(2026, 11, 17)
    assert validate(inputs(), today) == HOURS
    with pytest.raises(InputError, match="future"):
        validate(AuditInputs(lat=33.4, lon=-112.0, date="2026-11-17"), today)
    with pytest.raises(InputError, match="2021"):
        validate(AuditInputs(lat=33.4, lon=-112.0, date="2020-07-01"), today)
    with pytest.raises(InputError, match="contiguous US"):
        validate(AuditInputs(lat=24.86, lon=67.0, date="2026-07-15"), today)
    with pytest.raises(InputError, match="before"):
        validate(AuditInputs(lat=33.4, lon=-112.0, date="2026-07-15", start="18:00", end="06:00"), today)
    with pytest.raises(InputError, match="whole hour"):
        validate(AuditInputs(lat=33.4, lon=-112.0, date="2026-07-15", start="06:30"), today)


def test_dry_run_plan_costs(api):
    _, client = api
    calls = plan(inputs(), HOURS, client)
    assert sum(c.credits for c in calls) == 5 * 4220 + 2900
    calls = plan(inputs(env_mode="per-hour"), HOURS, client)
    assert sum(c.credits for c in calls) == 5 * 4220 + 5 * 2900


def test_full_run_range_mode_and_cache(api):
    fake, client = api
    res = run_audit(inputs(), client, HOURS)
    assert len(fake.posts) == 6  # 5 heatmaps + 1 env_params range call
    env_post = [b for p, b in fake.posts if p == "/v1/env_params"][0]
    assert env_post["date_time"]["filter_type"] == 2
    assert env_post["temperature"] == 41.0  # hottest sampled hour

    by_hour = {r["hour"]: r for r in res.rows}
    for h in HOURS:
        assert by_hour[h]["site_temp_c"] == SITE_T[h]                      # nearest tile = centre tile
        assert by_hour[h]["heat_index_local_c"] == pytest.approx(heat_index_c(SITE_T[h], RH[h]))
    assert by_hour["06:00"]["category"] == "Caution"  # 86 F / 30 % RH -> HI ~84 F
    assert by_hour["15:00"]["category"] in ("Extreme Caution", "Danger")
    assert res.window is not None and res.window.start == "06:00"
    assert by_hour["18:00"]["aqi"] is None                                  # -999 sentinel -> None
    notes = " ".join(res.notes)
    assert "spatial variation negligible" in notes
    assert "applies one input temperature" in notes                        # range-mode heat index caveat
    assert "sentinel" in notes
    assert "Could not" not in notes
    assert to_json(res)["credits"]["used"]["total"] == 5 * 4220 + 2900
    md = to_markdown(res)
    assert "| 06:00 |" in md and "Safest window" in md

    # second identical run: everything from cache, no new POSTs
    res2 = run_audit(inputs(), client, HOURS)
    assert len(fake.posts) == 6
    assert all(c["cached"] for c in res2.calls)
    assert sum(c.credits for c in plan(inputs(), HOURS, client)) == 0
    assert [r["category"] for r in res2.rows] == [r["category"] for r in res.rows]


def test_per_hour_mode_matches_api_heat_index(api):
    fake, client = api
    res = run_audit(inputs(env_mode="per-hour"), client, HOURS)
    assert sum(1 for p, _ in fake.posts if p == "/v1/env_params") == 5
    for r in res.rows:
        assert r["heat_index_api_c"] == pytest.approx(r["heat_index_local_c"], abs=0.06)
    assert not any("≠ NWS" in n for n in res.notes)


def test_failed_heatmap_is_reported(api):
    fake, client = api
    orig = fake.__call__

    def failing(request):
        if request.url.path.startswith("/v1/status/") and fake.jobs.get(request.url.path.rsplit("/", 1)[-1],
                                                                       ("", {}))[0] == "/v1/heatmap":
            aid = request.url.path.rsplit("/", 1)[-1]
            if fake.jobs[aid][1]["date_time"]["start_time"] == "12:00":
                return httpx.Response(200, json={"data": {"status": "Failed"}})
        return orig(request)

    client.http = httpx.Client(base_url="https://api.test", transport=httpx.MockTransport(failing))
    res = run_audit(inputs(), client, HOURS)
    row12 = [r for r in res.rows if r["hour"] == "12:00"][0]
    assert row12["category"] == "Unknown"
    assert any("12:00: heatmap did not complete" in n and "activity_id=" in n for n in res.notes)
    assert "could not be classified" in res.summary


def test_preflight_blocks_paid_calls_when_api_down(api):
    from heatshift.audit import ServiceUnavailable
    fake, client = api
    client.http = httpx.Client(base_url="https://api.test", transport=httpx.MockTransport(
        lambda r: httpx.Response(504, text="upstream request timeout")))
    with pytest.raises(ServiceUnavailable, match="no paid calls"):
        run_audit(inputs(), client, HOURS)


def test_circuit_breaker_stops_after_submit_504(api):
    fake, client = api
    orig = fake.__call__
    submits = []

    def flaky(request):
        if request.method == "POST" and request.url.path == "/v1/heatmap":
            submits.append(1)
            if len(submits) == 2:  # second heatmap submit hits the gateway timeout
                return httpx.Response(504, text="upstream request timeout")
        return orig(request)

    client.http = httpx.Client(base_url="https://api.test", transport=httpx.MockTransport(flaky))
    inp = inputs(concurrency=1)
    res = run_audit(inp, client, HOURS)
    assert len(submits) == 2                      # hours 3-5 were never submitted
    assert not [p for p, _ in fake.posts if p == "/v1/heatmap"][1:]  # only the first reached the fake API
    assert any("Stopped submitting" in n for n in res.notes)
    assert any("skipped — not submitted" in n for n in res.notes)
    assert res.rows[0]["site_temp_c"] == SITE_T["06:00"]  # completed hour still reported


def test_pending_activity_is_resumed_not_resubmitted(api):
    fake, client = api
    from heatshift.audit import heatmap_body
    body = heatmap_body(inputs(), "06:00")
    fake.jobs["act-orphan"] = ("/v1/heatmap", body)      # submitted by an earlier, crashed run
    client.cache.put_pending("/v1/heatmap", body, "act-orphan")
    res = client.run("/v1/heatmap", body)
    assert res.ok and res.activity_id == "act-orphan"
    assert fake.posts == []                               # no new (paid) submit
    assert client.cache.get_pending("/v1/heatmap", body) is None
    assert client.cache.get("/v1/heatmap", body) is not None


def test_key_never_in_outputs(api):
    _, client = api
    res = run_audit(inputs(), client, HOURS)
    blob = json.dumps(to_json(res)) + to_markdown(res)
    assert KEY not in blob


def test_cache_key_is_order_independent():
    assert request_key("/v1/heatmap", {"a": 1, "b": 2}) == request_key("/v1/heatmap", {"b": 2, "a": 1})
    assert request_key("/v1/heatmap", {"a": 1}) != request_key("/v1/env_params", {"a": 1})
