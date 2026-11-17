# Heat Shift Audit — Phoenix downtown site

- **Site:** 33.4484, -112.074  
- **Date:** 2026-07-15, 06:00–18:00 local (America/Phoenix), sampled every 3 h  
- **Data:** FortyGuard Temperature API — `/v1/heatmap` (100 m, 300 m × 300 m AOI) → `/v1/env_params` (range mode)  

**No sampled hour was at OK/Caution with AQI < 101 — no safe window found in the sampled hours. Avoid 06:00–15:00 (Danger). Extreme Caution at 18:00.**

| Hour | Site temp °C / °F | Heat index °C (local / API) | Apparent °C | Wet-bulb °C | RH % | AQI | Category |
|---|---|---|---|---|---|---|---|
| 06:00 | 35.7 / 96.2 | 40.4 / 54.0 | 33.5 | 22.6 | 45.5 | 51 | Danger |
| 09:00 | 38.3 / 100.9 | 51.5 / 60.1 | 33.3 | 23.2 | 53.4 | 50 | Danger |
| 12:00 | 40.4 / 104.7 | 47.2 / 48.1 | 38.6 | 24.3 | 36.4 | 50 | Danger |
| 15:00 | 40.8 / 105.4 | 41.7 / 41.6 | 41.5 | 23.7 | 23.2 | 49 | Danger |
| 18:00 | 38.0 / 100.5 | 36.5 / 40.1 | 41.2 | 23.2 | 19.0 | 54 | Extreme Caution |

Category = NWS heat index category (°F bands: <80 OK, 80–90 Caution, 90–103 Extreme Caution, 103–124 Danger, ≥125 Extreme Danger) from the locally computed heat index (NWS Rothfusz regression) using the FortyGuard heatmap temperature and FortyGuard relative humidity. ⚠ on AQI = EPA AQI ≥ 101. ⚠ on wet-bulb = ≥ 28 °C, an **illustrative** threshold, not official guidance. The safe window is based on the sampled hours only.

## Site temperature detail

| Hour | Site tile °C | AOI min | AOI mean | AOI max | AOI range | Tiles | Cloud (octas) | Precip mm |
|---|---|---|---|---|---|---|---|---|
| 06:00 | 35.7 | 35.7 | 35.7 | 35.7 | 0.000 | 9 | 5.0 | 0.0 |
| 09:00 | 38.3 | 38.3 | 38.3 | 38.3 | 0.000 | 9 | 7.0 | 2.2 |
| 12:00 | 40.4 | 40.4 | 40.4 | 40.4 | 0.000 | 9 | 6.0 | 0.6 |
| 15:00 | 40.8 | 40.8 | 40.8 | 40.8 | 0.000 | 9 | 5.0 | 0.0 |
| 18:00 | 38.0 | 38.0 | 38.0 | 38.0 | 0.000 | 9 | 6.0 | 0.0 |

## Data-quality notes

- Heatmap AOI temperature range < 0.1 °C at every sampled hour (max 0.000 °C across 9 tiles of 100 m): spatial variation negligible at this site, so the 100 m tiles carry no more detail than a single value.
- Provider apparent temperature and heat index differ by > 3 °C (two 'feels-like' metrics disagree): 06:00 apparent 33.5 vs HI 40.4 °C; 09:00 apparent 33.3 vs HI 51.5 °C; 12:00 apparent 38.6 vs HI 47.2 °C; 18:00 apparent 41.2 vs HI 36.5 °C.
- env_params range call applies one input temperature (40.8 °C) to every hour's heat_index_celsius. Using the API value as-is would be off by up to 13.6 °C (at 06:00: API 54.0 °C vs 40.4 °C from that hour's heatmap temperature 35.7 °C). The table uses the local value.
- Solar irradiance from the range call is a single average, not hourly (clear-sky GHI 618.41 W/m²).

## API calls

| Call | Status | Latency (s) | Cached | activity_id |
|---|---|---|---|---|
| heatmap 06:00 | Completed | 78.43 | yes | `ba7c4cdf-2d43-45ba-ac4d-8665440ebb0b` |
| heatmap 09:00 | Completed | 45.42 | yes | `245ea52c-6909-4588-ac9d-615687f8616a` |
| heatmap 12:00 | Completed | 41.54 | yes | `36fb3e09-2fb9-427b-b4a3-a69390e892c5` |
| heatmap 15:00 | Completed | 44.68 | yes | `c3b11ac4-c6c1-4a71-96d4-23439f9db0ae` |
| heatmap 18:00 | Completed | 42.38 | yes | `6c0fcdd7-66d3-4dbf-a46b-a62ca8dfe84e` |
| env_params 06:00–18:00 | Completed | 28.26 | yes | `3e9ca426-ab02-4e05-bb01-5e534bc9e7e4` |

Expected credits for this run: 0.
Credits used according to `/v1/system/fetch-api-key-usage` (before → after): 0 (total), 0 (cycle).

_Not medical or legal advice. For shift-planning review of a past day only._
