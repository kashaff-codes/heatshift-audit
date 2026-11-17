"""Phase A: remaining FortyGuard API/MCP tests (T1-T10).

Runs the approved paid tests in parallel threads, caches Completed results
(re-running this script costs 0 credits), and writes raw responses to
phase_a/results/<test>.json with base64 images extracted to phase_a/images/.

  python scripts/phase_a.py            # run everything not yet done
  python scripts/phase_a.py T1 T7      # run selected tests
"""

from __future__ import annotations

import base64
import os
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from heatshift.client import FortyGuardClient, FortyGuardError  # noqa: E402
from heatshift.geo import square_aoi, polygon_area_m2  # noqa: E402
from mcp_client import MCPClient  # noqa: E402

OUT = Path("phase_a/results")
IMG = Path("phase_a/images")
PHX = (33.4484, -112.0740)
DATE = "2026-07-15"


def dt(ft: int, start: str | None = None, end: str | None = None, date: str = DATE, end_date: str | None = None) -> dict:
    d = {"start_date": date, "filter_type": ft}
    if start:
        d["start_time"] = start
    if end:
        d["end_time"] = end
    d["end_date"] = end_date or date
    return d


def strip_images(obj, prefix: str, counter=[0]):
    """Replace long base64 strings with a file reference so JSON stays readable."""
    if isinstance(obj, dict):
        return {k: strip_images(v, f"{prefix}_{k}") for k, v in obj.items()}
    if isinstance(obj, list):
        return [strip_images(v, f"{prefix}_{i}") for i, v in enumerate(obj)]
    if isinstance(obj, str) and len(obj) > 2000:
        try:
            raw = base64.b64decode(obj.split(",", 1)[-1], validate=False)
        except Exception:
            return obj[:200] + "...<truncated>"
        ext = "jpg" if raw[:3] == b"\xff\xd8\xff" else "png" if raw[:4] == b"\x89PNG" else "bin"
        IMG.mkdir(parents=True, exist_ok=True)
        path = IMG / f"{prefix}.{ext}"
        path.write_bytes(raw)
        return f"<{ext} {len(raw)} bytes -> {path.as_posix()}>"
    return obj


def save(name: str, record: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{name}.json").write_text(json.dumps(strip_images(record, name), indent=1, ensure_ascii=False),
                                      encoding="utf-8")
    print(f"[{name}] saved: status={record.get('status')} latency={record.get('latency_s')}", flush=True)


def rest(client: FortyGuardClient, name: str, endpoint: str, body: dict, note: str = "") -> dict:
    t0 = time.perf_counter()
    try:
        res = client.run(endpoint, body)
        rec = res.to_dict() | {"raw_status": res.raw_status, "note": note}
    except FortyGuardError as exc:
        rec = {"endpoint": endpoint, "request": body, "status": "Rejected", "http_status": exc.status_code,
               "activity_id": exc.activity_id, "error": str(exc), "error_body": exc.body, "latency_s": round(time.perf_counter() - t0, 2), "note": note}
    save(name, rec)
    return rec


# ---------------------------------------------------------------- REST tests
def build_rest_tests() -> dict:
    downtown_1mi = square_aoi(*PHX, side_m=1600)
    houston = square_aoi(29.7604, -95.3698, side_m=2300)
    vegas = square_aoi(36.1147, -115.1728, side_m=2300)
    return {
        "T1_env_range_hours": ("/v1/env_params", {
            "latitude": PHX[0], "longitude": PHX[1], "temperature": 40.8,
            "date_time": dt(2, "06:00", "18:00")}, "filter_type 2, 06:00-18:00, temperature 40.8"),
        "T2_env_single_day": ("/v1/env_params", {
            "latitude": PHX[0], "longitude": PHX[1], "temperature": 40.8,
            "date_time": dt(3)}, "filter_type 3, full day"),
        "T3_env_future_date": ("/v1/env_params", {
            "latitude": PHX[0], "longitude": PHX[1], "temperature": 20.0,
            "date_time": dt(1, "15:00", date="2026-11-18")}, "tomorrow"),
        "T3b_env_missing_temperature": ("/v1/env_params", {
            "latitude": PHX[0], "longitude": PHX[1],
            "date_time": dt(1, "15:00")}, "temperature omitted (should be 400)"),
        "T4a_heatmap_persistence": ("/v1/heatmap", {
            "polygon_aoi": downtown_1mi, "date_time": dt(3), "granularity": 100,
            "analytic_type": "persistence", "threshold": 40, "direction": "above"},
            f"~{polygon_area_m2(downtown_1mi) / 2.59e6:.2f} mi2 downtown Phoenix"),
        "T4b_heatmap_time_of_measure": ("/v1/heatmap", {
            "polygon_aoi": downtown_1mi, "date_time": dt(3), "granularity": 100,
            "analytic_type": "time_of_measure"}, "same AOI, full day"),
        "T5a_heatmap_houston": ("/v1/heatmap", {
            "polygon_aoi": houston, "date_time": dt(1, "15:00"), "granularity": 60, "analytic_type": "tcm"},
            f"downtown Houston + Buffalo Bayou, ~{polygon_area_m2(houston) / 2.59e6:.2f} mi2"),
        "T5b_heatmap_las_vegas": ("/v1/heatmap", {
            "polygon_aoi": vegas, "date_time": dt(1, "15:00"), "granularity": 60, "analytic_type": "tcm"},
            f"Las Vegas Strip, ~{polygon_area_m2(vegas) / 2.59e6:.2f} mi2"),
        "T6_satellite": ("/v1/satellite", {
            "sat": {"latitude": 33.4300, "longitude": -112.0600},
            "date_time": dt(3), "granularity": 100}, "south Phoenix industrial point"),
        "T7_streetview_road": ("/v1/streetview", {
            "latitude": 33.4560, "longitude": -112.07399, "vertical_angle": 0.0,
            "horizontal_angle": 0.0, "back_view": True}, "Central Ave centreline, looking north + back"),
        # Retries after T6/T7 Failed twice with no reason: use the docs' own example shapes.
        "T6b_satellite_single_hour": ("/v1/satellite", {
            "sat": {"latitude": PHX[0], "longitude": PHX[1]},
            "date_time": {"start_date": DATE, "start_time": "15:00", "filter_type": 1}},
            "downtown Phoenix, filter_type 1, default granularity"),
        "T7b_streetview_docs_example": ("/v1/streetview", {
            "latitude": 40.7128, "longitude": -74.0060, "vertical_angle": 10.0,
            "horizontal_angle": 90.0, "back_view": False}, "exact Python example from the docs (NYC)"),
    }


def run_t10(client: FortyGuardClient) -> None:
    src = OUT / "T5a_heatmap_houston.json"
    if not src.exists():
        print("[T10] skipped: T5a has no result yet")
        return
    activity_id = json.loads(src.read_text(encoding="utf-8")).get("activity_id")
    out = {}
    for mode in (None, "links"):
        t0 = time.perf_counter()
        code, payload = client.status(activity_id, mode)
        dt_s = round(time.perf_counter() - t0, 2)
        size = len(json.dumps(payload))
        data = payload.get("data", {}) if isinstance(payload, dict) else {}
        result = data.get("result") if isinstance(data, dict) else None
        out[mode or "default"] = {
            "http": code, "latency_s": dt_s, "response_bytes": size,
            "result_keys": list(result.keys()) if isinstance(result, dict) else type(result).__name__,
            "result_preview": json.dumps(result)[:1500] if mode == "links" else None,
        }
    save("T10_status_links", {"status": "Done", "activity_id": activity_id, "comparison": out})


# ----------------------------------------------------------------- MCP tests
def mcp_text(res: dict) -> dict:
    sc = res.get("structuredContent")
    if sc:
        return sc
    for c in res.get("content", []):
        if c.get("type") == "text":
            try:
                return json.loads(c["text"])
            except ValueError:
                return {"text": c["text"]}
    return res


def mcp_flow(name: str, submit_tool: str, submit_args: dict, read_tool: str, read_key: str,
             interval: float = 10, max_wait: float = 600) -> None:
    if (OUT / f"{name}.json").exists():
        print(f"[{name}] already done, skipping (would cost credits again)")
        return
    c = MCPClient(client_key())
    c.initialize()
    res, sub_dt = c.call(submit_tool, submit_args)
    sub = mcp_text(res)
    rec = {"tool": submit_tool, "args": submit_args, "submit_latency_s": sub_dt, "submit_response": sub, "reads": []}
    activity_id = None
    blob = json.dumps(sub)
    for key in ("activity_id", "analytics_id"):
        if key in blob:
            # find the first value for the key anywhere in the structure
            def find(o):
                if isinstance(o, dict):
                    if isinstance(o.get(key), str):
                        return o[key]
                    for v in o.values():
                        r = find(v)
                        if r:
                            return r
                if isinstance(o, list):
                    for v in o:
                        r = find(v)
                        if r:
                            return r
            activity_id = find(sub)
            if activity_id:
                break
    rec["activity_id"] = activity_id
    if not activity_id:
        rec["status"] = "NoActivityId"
        save(name, rec)
        return
    t0 = time.perf_counter()
    state = "processing"
    while time.perf_counter() - t0 < max_wait:
        time.sleep(interval)
        r, r_dt = c.call(read_tool, {read_key: activity_id})
        body = mcp_text(r)
        b = json.dumps(body).lower()
        state = ("completed" if '"completed"' in b else "failed" if '"failed"' in b else "processing")
        rec["reads"].append({"t": round(time.perf_counter() - t0, 1), "latency_s": r_dt, "state": state,
                             "is_error": r.get("isError"),
                             "body": body if state != "processing" else json.dumps(body)[:600]})
        if state in ("completed", "failed") or r.get("isError"):
            break
    rec["status"] = state
    rec["latency_s"] = round(time.perf_counter() - t0 + sub_dt, 1)
    save(name, rec)


_KEY = None


def client_key() -> str:
    return _KEY


def main(selected: list[str]) -> None:
    global _KEY
    client = FortyGuardClient.from_env(log=lambda m: print("  ", m, flush=True))
    _KEY = client.api_key
    before = client.credits()["credit_summary"]
    print("credits before:", json.dumps(before), flush=True)

    tests = build_rest_tests()
    pick = lambda n: not selected or any(n.startswith(s) for s in selected)
    jobs = []
    with ThreadPoolExecutor(max_workers=int(os.environ.get("PHASE_A_WORKERS", "8"))) as pool:
        for name, (ep, body, note) in tests.items():
            if pick(name):
                jobs.append(pool.submit(rest, client, name, ep, body, note))
        if pick("T9a"):
            jobs.append(pool.submit(mcp_flow, "T9a_mcp_heatmap", "heatmap", {
                "polygon_aoi": square_aoi(*PHX, side_m=300),
                "date_time": {"start_date": DATE, "start_time": "15:00", "filter_type": 1},
                "granularity": 100, "analytic_type": "tcm"}, "heatmap_read", "activity_id", 10, 400))
        if pick("T9b"):
            jobs.append(pool.submit(mcp_flow, "T9b_mcp_report", "report", {
                "latitude": PHX[0], "longitude": PHX[1], "temperature": 105, "date": DATE,
                "analysis": ["environmental", "urban"]}, "report_read", "analytics_id", 20, 720))
        for j in jobs:
            try:
                j.result()
            except Exception as exc:  # keep going; record failure
                print("job error:", type(exc).__name__, str(exc).replace(_KEY, "***")[:500], flush=True)
    if pick("T10"):
        run_t10(client)

    after = client.credits()
    print("credits after:", json.dumps(after["credit_summary"]), flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"_credits_{int(time.time())}.json").write_text(
        json.dumps({"before": before, "after": after}, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1:])
