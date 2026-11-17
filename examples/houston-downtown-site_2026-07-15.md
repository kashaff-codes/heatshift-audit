# Heat Shift Audit — Houston downtown site

- **Site:** 29.7604, -95.3698  
- **Date:** 2026-07-15, 06:00–18:00 local (America/Chicago), sampled every 3 h  
- **Data:** FortyGuard Temperature API — `/v1/heatmap` (100 m, 1000 m × 1000 m AOI) → `/v1/env_params` (range mode)  

**Safest window: 06:00. Extreme Caution at 09:00, 12:00, 15:00, 18:00.**

| Hour | Site temp °C / °F | Heat index °C (local / API) | Apparent °C | Wet-bulb °C | RH % | AQI | Category |
|---|---|---|---|---|---|---|---|
| 06:00 | 26.5 / 79.7 | 29.8 / 44.4 | 29.0 | 23.7 | 95.5 | 66 | Caution |
| 09:00 | 27.5 / 81.5 | 32.6 / 42.3 | 29.7 | 23.7 | 90.0 | 67 | Extreme Caution |
| 12:00 | 29.2 / 84.6 | 35.3 / 39.0 | 32.5 | 24.6 | 80.0 | 70 | Extreme Caution |
| 15:00 | 29.5 / 85.1 | 34.7 / 37.0 | 32.2 | 23.9 | 73.5 | 76 | Extreme Caution |
| 18:00 | 30.4 / 86.8 | 37.6 / 37.6 | 32.4 | 24.2 | 75.3 | 80 | Extreme Caution |

Category = NWS heat index category (°F bands: <80 OK, 80–90 Caution, 90–103 Extreme Caution, 103–124 Danger, ≥125 Extreme Danger) from the locally computed heat index (NWS Rothfusz regression) using the FortyGuard heatmap temperature and FortyGuard relative humidity. ⚠ on AQI = EPA AQI ≥ 101. ⚠ on wet-bulb = ≥ 28 °C, an **illustrative** threshold, not official guidance. The safe window is based on the sampled hours only.

## Site temperature detail

| Hour | Site tile °C | AOI min | AOI mean | AOI max | AOI range | Tiles | Cloud (octas) | Precip mm |
|---|---|---|---|---|---|---|---|---|
| 06:00 | 26.5 | 26.5 | 26.5 | 26.6 | 0.038 | 108 | 6.0 | 0.0 |
| 09:00 | 27.5 | 27.3 | 27.5 | 27.5 | 0.188 | 108 | 4.0 | 0.2 |
| 12:00 | 29.2 | 29.2 | 29.2 | 29.3 | 0.081 | 108 | 8.0 | 0.0 |
| 15:00 | 29.5 | 29.5 | 29.5 | 29.6 | 0.038 | 108 | 8.0 | 0.0 |
| 18:00 | 30.4 | 30.4 | 30.4 | 30.5 | 0.081 | 108 | 3.0 | 0.0 |

## Data-quality notes

- Heatmap AOI temperature range < 0.1 °C at 06:00, 12:00, 15:00, 18:00 (max 0.081 °C across 108 tiles of 100 m): spatial variation negligible at this site, so the 100 m tiles carry no more detail than a single value.
- Provider apparent temperature and heat index differ by > 3 °C (two 'feels-like' metrics disagree): 18:00 apparent 32.4 vs HI 37.6 °C.
- env_params range call applies one input temperature (30.4 °C) to every hour's heat_index_celsius. Using the API value as-is would be off by up to 14.6 °C (at 06:00: API 44.4 °C vs 29.8 °C from that hour's heatmap temperature 26.5 °C). The table uses the local value.
- Solar irradiance from the range call is a single average, not hourly (clear-sky GHI 548.55 W/m²).

## API calls

| Call | Status | Latency (s) | Cached | activity_id |
|---|---|---|---|---|
| heatmap 06:00 | Completed | 42.91 | yes | `2cb9cae9-efc8-4f7b-9cc1-c19a3a6d3e68` |
| heatmap 09:00 | Completed | 52.87 | yes | `e559e09e-6b42-496b-b869-e3939b58697c` |
| heatmap 12:00 | Completed | 35.9 | yes | `829ac62d-dc79-4833-af51-1dfb9ebbb80f` |
| heatmap 15:00 | Completed | 7.2 | yes | `4f35b5e3-3020-45d3-9fc4-3bb65b0b8880` |
| heatmap 18:00 | Completed | 39.12 | yes | `c3f690ca-7acc-4ba3-ba9c-61c0f0b658d2` |
| env_params 06:00–18:00 | Completed | 6.36 | no | `ffcf0925-77ea-456e-9efd-8532317248d4` |

Expected credits for this run: 2,900.
Credits used according to `/v1/system/fetch-api-key-usage` (before → after): 0 (total), 0 (cycle).

_Not medical or legal advice. For shift-planning review of a past day only._
