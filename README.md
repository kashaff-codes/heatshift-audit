# Heat Shift Audit

A small Python CLI that takes a **US work site and a past date** and returns an **hour-by-hour heat-stress table plus the safest window for outdoor work**. It is built on the FortyGuard Temperature API®, and it includes built-in data-quality checks that flag problems in the data it gets back.

It is meant for a site safety lead (construction, delivery, landscaping) reviewing a past hot day, such as last week's heat event, to set shift policy for similar days.

> Built as part of a product evaluation of FortyGuard's Temperature Dashboard®, Temperature API® and Temperature MCP.
> The full test log is in [`test_log.md`](test_log.md).

## Example output

```
$ python -m heatshift audit --lat 33.4484 --lon -112.0740 --date 2026-07-15 --name "Phoenix downtown site"

                       Heat Shift Audit — Phoenix downtown site — 2026-07-15
┌───────┬───────────────────┬─────────────────────────────┬─────────────┬─────────────┬──────┬─────┬─────────────────┐
│ Hour  │ Site temp °C / °F │ Heat index °C (local / API) │ Apparent °C │ Wet-bulb °C │ RH % │ AQI │ Category        │
├───────┼───────────────────┼─────────────────────────────┼─────────────┼─────────────┼──────┼─────┼─────────────────┤
│ 06:00 │       35.7 / 96.2 │                 40.4 / 54.0 │        33.5 │        22.6 │ 45.5 │  51 │ Danger          │
│ 09:00 │      38.3 / 100.9 │                 51.5 / 60.1 │        33.3 │        23.2 │ 53.4 │  50 │ Danger          │
│ 12:00 │      40.4 / 104.7 │                 47.2 / 48.1 │        38.6 │        24.3 │ 36.4 │  50 │ Danger          │
│ 15:00 │      40.8 / 105.4 │                 41.7 / 41.6 │        41.5 │        23.7 │ 23.2 │  49 │ Danger          │
│ 18:00 │      38.0 / 100.5 │                 36.5 / 40.1 │        41.2 │        23.2 │ 19.0 │  54 │ Extreme Caution │
└───────┴───────────────────┴─────────────────────────────┴─────────────┴─────────────┴──────┴─────┴─────────────────┘
No sampled hour was at OK/Caution with AQI < 101 — no safe window found in the sampled hours.
Avoid 06:00–15:00 (Danger). Extreme Caution at 18:00.

Data-quality notes
 • Heatmap AOI temperature range < 0.1 °C at every sampled hour (max 0.000 °C across 9 tiles of 100 m) ...
 • env_params range call applies one input temperature (40.8 °C) to every hour's heat_index_celsius. Using the API
   value as-is would be off by up to 13.6 °C (at 06:00: API 54.0 °C vs 40.4 °C from that hour's heatmap temperature).
 • Provider apparent temperature and heat index differ by > 3 °C ...: 09:00 apparent 33.3 vs HI 51.5 °C ...

Calls: 6 (0 from cache). Expected credits: 24,000. Credits used (usage endpoint, before→after): 24,000 total.
Saved runs/phoenix-downtown-site_2026-07-15.json and runs/phoenix-downtown-site_2026-07-15.md
```

### Demo runs (15 Jul 2026, 06:00–18:00, every 3 h)

| Site | Heat | Result | Full report |
|---|---|---|---|
| Phoenix, AZ (33.4484, −112.0740) | dry heat + monsoon morning | **No safe window.** Danger 06:00–15:00, Extreme Caution 18:00 | [examples/phoenix…](examples/phoenix-downtown-site_2026-07-15.md) |
| Houston, TX (29.7604, −95.3698) | humid | **Safest window 06:00** (Caution); Extreme Caution 09:00–18:00 | [examples/houston…](examples/houston-downtown-site_2026-07-15.md) |
| Miami, FL (25.7617, −80.1918) | humid | **Safest window 06:00** (Caution); Extreme Caution 09:00–18:00 | [examples/miami…](examples/miami-downtown-site_2026-07-15.md) |

Houston uses `--aoi-side 1000`: every 300 m Houston heatmap `Failed` with no reason given (see the issues below). Each run costs 24,000 credits, and an identical second run cost 0.

## How it works

```
for each sampled hour ──► POST /v1/heatmap   (300 m × 300 m square around the site, 100 m tiles)
                              └─► site temperature = tile nearest the site centre (+ AOI min/mean/max)
once for the window ───► POST /v1/env_params (filter_type 2, hourly RH, apparent temp, wet-bulb, AQI …)
                              └─► heat index recomputed locally per hour (NWS Rothfusz regression)
                                  from that hour's heatmap temperature + FortyGuard humidity
                         ──► NWS category per hour, EPA AQI flag, wet-bulb flag
                         ──► safest window = longest run of sampled hours at OK/Caution with AQI < 101
                         ──► data-quality notes, terminal table, runs/<site>_<date>.json + .md
```

It chains two FortyGuard products the way they're meant to be used. `env_params` needs the caller to supply a temperature, so the tool takes it from FortyGuard's own heatmap rather than inventing one.

### Why `env_params` is called once per window (range mode), and why heat index is computed locally

Phase A test T1 showed that a range-of-hours call (`filter_type: 2`) returns genuinely hourly humidity, apparent temperature, wet-bulb, AQI and cloud values. Its 15:00 values matched a single-hour call exactly. However, `heat_index_celsius` applies the **single `temperature` input to every hour**: with 40.8 °C supplied, it reports a 60.3 °C heat index at 08:00. So the tool:

- makes **one** range call (2,900 credits instead of 2,900 × N), passing the hottest sampled hour's heatmap temperature;
- recomputes heat index **locally for every hour** from that hour's heatmap temperature and the hourly RH;
- checks the API's heat-index formula against NWS for the temperature it was actually given, and reports how far off the raw API value would have been.

`--env-mode per-hour` makes one env_params call per hour instead, so the API heat index is directly comparable hour by hour. It costs more.

## Setup

Python 3.11+.

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows  (source .venv/bin/activate on macOS/Linux)
pip install -r requirements.txt
copy .env.example .env          # then put your key in .env:  FORTYGUARD_API_KEY=...
```

The key is read from `.env` only. It is never printed, logged or written to `runs/`, and `.env`, `.cache/` and `runs/` are git-ignored.

## Usage

```bash
python -m heatshift audit --lat 33.4484 --lon -112.0740 --date 2026-07-15 \
  --start 06:00 --end 18:00 --every 3 --name "Phoenix downtown site"
```

| Flag | Meaning |
|---|---|
| `--lat --lon` | Site (contiguous US only) |
| `--date` | Past date, `YYYY-MM-DD`, ≥ 2021-01-01 |
| `--start --end` | Local wall-clock hours at the site, inclusive (default 06:00–18:00) |
| `--every N` | Sample every N hours (default 3) to control credits |
| `--env-mode` | `range` (default) or `per-hour` |
| `--dry-run` | Print the planned calls and estimated credits; make **no** paid calls |
| `--yes` | Skip the confirmation prompt (otherwise it always asks before spending credits) |
| `--granularity` | Heatmap tile size: 60, 80 or 100 m (default 100) |
| `--wet-bulb-warn` | Wet-bulb warning threshold in °C (default 28, **illustrative, not official guidance**) |
| `--concurrency` | Parallel API jobs (default 2) |

Cost per run (Premium): heatmap 4,220 × N + env_params 2,900. The default 06:00–18:00 every 3 h gives 5 × 4,220 + 2,900 = **24,000 credits**. A repeat of an identical run costs **0** because every completed response is cached on disk under `sha256(endpoint + canonical JSON body)`; FortyGuard charges again for identical re-runs.

## Classification

All thresholds live in [`heatshift/config.py`](heatshift/config.py), with sources.

- **Primary — heat index** (NWS categories, °F): < 80 OK · 80–90 Caution · 90–103 Extreme Caution · 103–124 Danger · ≥ 125 Extreme Danger. The tool uses the locally computed value and shows the API value next to it. Source: [NWS heat index](https://www.weather.gov/safety/heat-index), [Rothfusz regression](https://www.wpc.ncep.noaa.gov/html/heatindex_equation.shtml).
- **Secondary flag — AQI** (US EPA bands): flags AQI ≥ 101 (Unhealthy for Sensitive Groups or worse). Source: [AirNow](https://www.airnow.gov/aqi/aqi-basics/).
- **Info — wet-bulb temperature**: flagged at ≥ 28 °C by default. This is an illustrative threshold, not official guidance.
- **Safest window**: the longest continuous run of sampled hours at OK or Caution with AQI < 101. It is based on the sampled hours only.

## Data-quality checks (automatic notes)

- Heatmap AOI temperature range < 0.1 °C: spatial variation negligible at this site/hour.
- API heat index ≠ NWS heat index for the same inputs (> 1 °C).
- Range mode: how far the API's single-temperature heat index is from the per-hour value.
- Provider apparent temperature vs heat index gap > 3 °C (two "feels-like" metrics disagree).
- Any Failed/rejected activity (with its `activity_id`), and null or −999 values.
- Solar irradiance from a range call is one average, not hourly.

## Reliability safeguards (added after real incidents during testing)

- **Pre-flight check:** a free call to the credits endpoint runs before any paid call. If the API is returning 5xx, the run stops having spent nothing.
- **Circuit breaker:** after one 5xx on submit, no further paid jobs are submitted. On 17 Nov 2026 a `504` on submit still created and charged the job, with no `activity_id` returned to fetch it.
- Polling every 5 s for up to 6 min. A `404` right after submit counts as "not ready yet", and transient 5xx on status keeps polling. Submits are never blindly retried; only TLS/connect failures, where nothing reached the server, are retried.
- FortyGuard's error message is shown verbatim, with the `activity_id`.
- Latency of every call is recorded in the JSON output.

## FortyGuard products used

| Product | How |
|---|---|
| Temperature API® `POST /v1/heatmap` | Site temperature per sampled hour (`tcm`, 100 m) |
| Temperature API® `POST /v1/env_params` | Hourly humidity, apparent temperature, wet-bulb, AQI, cloud, precipitation |
| Temperature API® `GET /v1/status/{id}` | Async polling |
| Temperature API® `POST /v1/system/fetch-api-key-usage` | Pre-flight health check and credits used before/after |
| Temperature MCP | Phase A tests T8–T9 through [`scripts/mcp_client.py`](scripts/mcp_client.py) (same `heatmap` request as the audit's 15:00 call) |
| Temperature Dashboard® | Manual evaluation (see `test_log.md`, D1–D17) |

## Limitations

- **Past dates only.** `env_params` rejects future dates, so this can't forecast tomorrow's shift. That's a product limitation; a forecast-capable `env_params` would make it a planning tool rather than a review tool.
- **US only** (contiguous-US bounding box check; the API returns `OUT_OF_COVERAGE` elsewhere).
- Hours are sampled (default every 3 h), so the safe window is conservative and coarse.
- The heat index uses air temperature from FortyGuard's model. It doesn't account for direct sun, workload, clothing or acclimatisation. WBGT would be the occupational standard, but it isn't available from the API.
- Not medical or legal advice.

## Product issues found while building

Details, inputs and raw responses are in [`test_log.md`](test_log.md).

Ordered by impact on someone building on the API:

1. **`env_params` heat index in range mode uses one temperature for every hour** (T1, T2, B3, B8). A 06:00–18:00 call with 40.8 °C returns a 60.3 °C heat index at 08:00. Against each hour's own heatmap temperature, the raw value is off by 13.6 °C (Phoenix), 14.6 °C (Houston) and 17.6 °C (Miami) at 06:00. The per-hour provider fields are fine. *Suggested fix:* accept a per-hour temperature array, or fill temperature from FortyGuard's own model when it's omitted.
2. **A 504 on submit can still create and charge the job, with no `activity_id` returned** (incidents log). It happened 3 times today, 12,660 credits in total. *Suggested fix:* a REST idempotency key (the MCP already has one) and a "list my recent activities" endpoint.
3. **Reliability:** five `504 upstream request timeout` incidents in about 75 minutes, which also hit the free credits endpoint and the dashboard.
4. **Spatial resolution:** in Phoenix all 9 tiles of a 300 m AOI at 100 m are identical at every hour, and 2 mi² AOIs vary by only 0.18–0.68 °C (Las Vegas, Houston). `persistence` and `exceedance` gave the same value for every tile (T4a, A9). Miami showed real variation. The response doesn't say what the effective resolution is.
5. **Silent `Failed` jobs:** Houston 300 m heatmaps, satellite (×3) and street view (×2) all failed with no reason. Only `activity_id`, `status` and `task_id` come back.
6. **Docs/contract gaps:** the credits endpoint is labelled GET but is POST, and its path isn't shown. `time_of_measure` returns UTC hours although inputs are local. Range end is inclusive in env_params but end-exclusive in MCP heatmap. Two "feels-like" fields disagree by up to 18 °C with no guidance. A future date returns `code: NO_COVERAGE`. Routing charges are missing from `activity_breakdown`.

What worked well: clear 400/401/422 errors with `field` names, failed jobs not charged, `result_delivery=links` (526 KB → 1 KB), MCP submits that report `credits_reserved_this_request`, the MCP tool descriptions (cost disclosure, confirm-before-pay, "never invent a temperature"), a NWS-consistent heat index formula, and rich hourly provider data.

## Development

```bash
pip install -r requirements.txt
python -m pytest -q          # offline: the HTTP layer is mocked, no key or network needed
```

```
heatshift/
  __main__.py   CLI (argparse)            client.py   REST client: submit, poll, retries, redaction
  audit.py      pipeline + checks         cache.py    disk cache keyed by sha256(endpoint + body)
  geo.py        AOI square, US bbox       heat.py     NWS heat index, unit conversions
  classify.py   categories + windows      report.py   table, JSON, Markdown
  config.py     thresholds, costs, sources
scripts/        Phase A test runner, raw MCP client, analysis helpers
tests/          unit + mocked end-to-end tests
```
