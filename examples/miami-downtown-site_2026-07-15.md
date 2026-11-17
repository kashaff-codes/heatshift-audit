# Heat Shift Audit — Miami downtown site

- **Site:** 25.7617, -80.1918  
- **Date:** 2026-07-15, 06:00–18:00 local (America/New_York), sampled every 3 h  
- **Data:** FortyGuard Temperature API — `/v1/heatmap` (100 m, 300 m × 300 m AOI) → `/v1/env_params` (range mode)  

**Safest window: 06:00. Extreme Caution at 09:00, 12:00, 15:00, 18:00.**

| Hour | Site temp °C / °F | Heat index °C (local / API) | Apparent °C | Wet-bulb °C | RH % | AQI | Category |
|---|---|---|---|---|---|---|---|
| 06:00 | 26.9 / 80.4 | 29.3 / 46.9 | 29.7 | 23.2 | 77.0 | 56 | Caution |
| 09:00 | 31.1 / 87.9 | 34.2 / 38.5 | 33.7 | 23.8 | 56.7 | 55 | Extreme Caution |
| 12:00 | 32.7 / 90.8 | 35.6 / 36.4 | 37.4 | 24.9 | 50.1 | 55 | Extreme Caution |
| 15:00 | 33.1 / 91.5 | 38.7 / 38.7 | 38.1 | 25.6 | 57.2 | 55 | Extreme Caution |
| 18:00 | 32.1 / 89.8 | 34.9 / 36.8 | 35.9 | 24.7 | 51.4 | 54 | Extreme Caution |

Category = NWS heat index category (°F bands: <80 OK, 80–90 Caution, 90–103 Extreme Caution, 103–124 Danger, ≥125 Extreme Danger) from the locally computed heat index (NWS Rothfusz regression) using the FortyGuard heatmap temperature and FortyGuard relative humidity. ⚠ on AQI = EPA AQI ≥ 101. ⚠ on wet-bulb = ≥ 28 °C, an **illustrative** threshold, not official guidance. The safe window is based on the sampled hours only.

## Site temperature detail

| Hour | Site tile °C | AOI min | AOI mean | AOI max | AOI range | Tiles | Cloud (octas) | Precip mm |
|---|---|---|---|---|---|---|---|---|
| 06:00 | 26.9 | 26.7 | 26.9 | 27.1 | 0.459 | 9 | 4.0 | 0.0 |
| 09:00 | 31.1 | 30.9 | 31.1 | 31.2 | 0.254 | 9 | 7.0 | 0.0 |
| 12:00 | 32.7 | 32.6 | 32.7 | 32.8 | 0.190 | 9 | 0.0 | 0.0 |
| 15:00 | 33.1 | 33.0 | 33.1 | 33.2 | 0.209 | 9 | 3.0 | 0.1 |
| 18:00 | 32.1 | 32.0 | 32.1 | 32.2 | 0.121 | 9 | 4.0 | 0.1 |

## Data-quality notes

- env_params range call applies one input temperature (33.1 °C) to every hour's heat_index_celsius. Using the API value as-is would be off by up to 17.6 °C (at 06:00: API 46.9 °C vs 29.3 °C from that hour's heatmap temperature 26.9 °C). The table uses the local value.
- Solar irradiance from the range call is a single average, not hourly (clear-sky GHI 534.36 W/m²).

## API calls

| Call | Status | Latency (s) | Cached | activity_id |
|---|---|---|---|---|
| heatmap 06:00 | Completed | 41.9 | yes | `9ccf61f8-5617-4972-a18f-95228c00587c` |
| heatmap 09:00 | Completed | 38.08 | no | `07b030d0-79ca-4041-890c-f767f5ec7ecc` |
| heatmap 12:00 | Completed | 43.85 | no | `d63a1201-2e23-4ba8-905b-dc815fa905e8` |
| heatmap 15:00 | Completed | 41.18 | no | `6a2cf549-67b2-41bd-9b56-ce0a2dbc320d` |
| heatmap 18:00 | Completed | 44.7 | no | `a7ec0087-0883-41cd-8255-e52c901d8f42` |
| env_params 06:00–18:00 | Completed | 13.91 | no | `a54a53b6-46b0-432d-85f4-e4e21efe6c57` |

Expected credits for this run: 19,780.
Credits used according to `/v1/system/fetch-api-key-usage` (before → after): 19,780 (total), 19,780 (cycle).

_Not medical or legal advice. For shift-planning review of a past day only._
