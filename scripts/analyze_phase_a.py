"""Summarise phase_a/results/*.json into compact metrics for test_log.md."""

import json
import statistics as st
import sys
from pathlib import Path

R = Path("phase_a/results")


def heatmap_summary(res: dict) -> dict:
    fs = res.get("map_data", {}).get("features", [])
    props = fs[0]["properties"] if fs else {}
    key = "average_temperature" if "average_temperature" in props else "value"
    vals = [f["properties"][key] for f in fs if isinstance(f["properties"].get(key), (int, float))]
    out = {"tiles": len(fs), "value_key": key}
    if vals:
        out.update(min=min(vals), max=max(vals), range=round(max(vals) - min(vals), 4),
                   mean=round(st.fmean(vals), 4), std=round(st.pstdev(vals), 4), distinct=len(set(vals)))
        counts = {}
        for v in vals:
            counts[v] = counts.get(v, 0) + 1
        if len(counts) <= 12:
            out["value_counts"] = dict(sorted(counts.items()))
    sd = res.get("stats_data") or {}
    out["stats_keys"] = list(sd.keys())
    for k in ("temperature_stats", "units", "analytic_type", "threshold", "direction", "hour_counts_utc", "window_utc"):
        if k in sd:
            out[f"stats.{k}"] = sd[k]
    other = {k: v for k, v in sd.items() if isinstance(v, (int, float, str)) and k not in out}
    out["stats_scalars"] = other
    return out


def seg_summary(res: dict) -> dict:
    def walk(o, path=""):
        if isinstance(o, dict):
            for k, v in o.items():
                if k in ("segments", "image_date", "image_year", "imagery_retrieved_at", "coordinates", "mode",
                         "image_dimensions", "processing_time_seconds"):
                    yield f"{path}{k}", v
                else:
                    yield from walk(v, f"{path}{k}.")
        elif isinstance(o, list):
            for i, v in enumerate(o):
                yield from walk(v, f"{path}{i}.")
    return dict(walk(res))


def main(names):
    for f in sorted(R.glob("T*.json")):
        if names and not any(f.stem.startswith(n) for n in names):
            continue
        j = json.loads(f.read_text(encoding="utf-8"))
        print(f"===== {f.stem}: status={j.get('status')} latency={j.get('latency_s')} "
              f"activity={j.get('activity_id')} http={j.get('http_status')}")
        if j.get("error"):
            print("  error:", j["error"])
        res = j.get("result")
        ep = j.get("endpoint", "")
        if isinstance(res, dict) and ep == "/v1/heatmap":
            print(" ", json.dumps(heatmap_summary(res), default=str)[:1500])
        elif isinstance(res, dict) and ep in ("/v1/satellite", "/v1/streetview"):
            print(" ", json.dumps(seg_summary(res), default=str)[:2500])
        elif "comparison" in j:
            print(" ", json.dumps(j["comparison"])[:2500])
        elif "reads" in j:
            print("  submit:", json.dumps(j.get("submit_response"))[:800])
            last = j["reads"][-1] if j["reads"] else {}
            print(f"  reads={len(j['reads'])} last={json.dumps(last)[:2500]}")


if __name__ == "__main__":
    main(sys.argv[1:])
