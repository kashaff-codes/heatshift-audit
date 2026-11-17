"""Resume polling Phase A activities that were submitted but lost to the 504 outage.

Polling is free; this never re-submits. Each activity is matched back to its
test by comparing the result geometry/endpoint with the Phase A request bodies.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from heatshift.client import FortyGuardClient  # noqa: E402
from phase_a import build_rest_tests, save  # noqa: E402

ORPHANS = {
    "24d77df4-f350-415d-866e-aeb6e1cbc145": "/v1/heatmap",
    "46e8f82d-eeda-46dd-991d-a0b85b8511c9": "/v1/heatmap",
    "75e9a184-a768-4d59-adaf-c28e29295cb7": "/v1/streetview",
    "4788bd9b-4cec-4886-9683-e8ba97871ae6": "/v1/satellite",
}


def which_heatmap(result) -> str:
    feats = (result or {}).get("map_data", {}).get("features", [])
    lon = feats[0]["geometry"]["coordinates"][0][0][0] if feats else 0
    return "T5a_heatmap_houston" if lon > -100 else "T4b_heatmap_time_of_measure"


def main():
    client = FortyGuardClient.from_env(log=lambda m: print("  ", m, flush=True))
    tests = build_rest_tests()
    print("credits:", json.dumps(client.credits()), flush=True)
    for aid, ep in ORPHANS.items():
        res = client.resume(ep, {}, aid)
        if ep == "/v1/heatmap":
            name = which_heatmap(res.result)
        else:
            name = {"/v1/streetview": "T7_streetview_road", "/v1/satellite": "T6_satellite"}[ep]
        body = tests[name][1]
        if res.ok:  # cache under the real request body so a re-run is free
            client.cache.put(ep, body, res.to_dict() | {"request": body, "raw_status": res.raw_status})
        rec = res.to_dict() | {"request": body, "raw_status": res.raw_status, "note": tests[name][2],
                               "resumed_after_outage": True}
        save(name, rec)


if __name__ == "__main__":
    main()
