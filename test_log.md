# FortyGuard product evaluation — test log

Tester: Kashaf Fatima · Account plan (per credits endpoint): **Premium**, 1,000,000 one-time credits, 14 Nov – 14 Dec 2026.
City: **Phoenix, AZ** (plus Houston, TX, Las Vegas, NV, Miami, FL for comparison). Main date: **15 Jul 2026**, local wall time.

Raw responses for every Phase A test are in [`phase_a/results/`](phase_a/results/) (base64 images extracted to `phase_a/images/`).
Scripts: [`scripts/phase_a.py`](scripts/phase_a.py) (REST + MCP runner, cached), [`scripts/mcp_client.py`](scripts/mcp_client.py) (raw MCP JSON-RPC), [`scripts/analyze_phase_a.py`](scripts/analyze_phase_a.py).

Legend: ✅ works as expected · ⚠️ works with a caveat · ❌ problem

---

## Phase A — 17 Nov 2026

Credits column = what the call should cost on Premium; failed and rejected jobs are free unless stated otherwise.
Latency = submit → terminal status, measured by the client.

| # | Test | Inputs | Latency | Credits | Result | Verdict |
|---|---|---|---|---|---|---|
| T1 | env_params, range of hours (`filter_type: 2`) | Phoenix 33.4484, −112.0740 · 15 Jul 2026 06:00–18:00 · `temperature` 40.8 | 17.3 s | 2,900 | 13 hourly entries (06:00…18:00, **end inclusive**) + `metadata.timestamps` + `timezone: America/Phoenix`. RH, apparent, wet-bulb, AQI, cloud, precipitation are genuinely hourly, and the 15:00 values exactly match the single-hour call from 14 Nov (A2). **But `heat_index_celsius` applies the single input temperature (40.8 °C) to every hour**: 54.1 °C at 06:00, **60.3 °C at 08:00**, 40.1 °C at 18:00. Solar irradiance is a single 13-hour average (GHI 618), not hourly. | ❌ Heat index in range mode is misleading |
| T2 | env_params, single day (`filter_type: 3`) | same point · 15 Jul 2026 · `temperature` 40.8 | 20.4 s | 2,900 | 24 hourly entries 00:00–23:00. Same issue: heat index 55.4 °C at 23:00 and 58.8 °C at 22:00, because 40.8 °C is applied to night-time humidity. | ❌ Same as T1 |
| T3 | env_params future date | 18 Nov 2026 (tomorrow) 15:00 | 5.4 s | 0 | 400 *"Field 'date_time.start_date' (2026-11-18) is in the future. Requests must be for a past or present date."* — clear message, but `code: "NO_COVERAGE"` is the wrong error code for a date problem. | ✅ / ⚠️ |
| T3b | env_params without `temperature` | — | 5.2 s | 0 | **422** *"Field 'temperature' is required."* with `field` + pydantic `detail`. (Compare A5 on 14 Nov: a bad date format gave a 500.) | ✅ |
| T4a | Heatmap `persistence` | 1 mi² square, downtown Phoenix · 15 Jul full day · 100 m · threshold 40 °C above | 38.3 s | 4,220 | 270 tiles, **every tile = 4 hours** (std 0). `stats_data` = `min/max/mean`, plus `window_utc`, `threshold_celsius`, `calculation_version: 2`, `value_representation: nearest_catalog_cell`. | ❌ No spatial signal |
| T4b | Heatmap `time_of_measure` | same AOI, full day | 53.1 s | 4,220 | 270 tiles; value is the **UTC** hour of the peak: 21 (102 tiles) or 22 (168 tiles) = 14:00–15:00 Phoenix time. Inputs are local wall time but output is UTC hour; no local-hour field. Plausible peak time. | ⚠️ UTC output |
| T5a | Heatmap, varied area — Houston | downtown + Buffalo Bayou, 2.04 mi² · 15 Jul 15:00 · 60 m | 8.8 s* | 4,220 | 1,263 tiles, **29.48–30.16 °C (range 0.68 °C)**, std 0.15. Coolest tile is the downtown core, hottest is the south-east edge (EaDo). More variation than Phoenix but still narrow for a mix of towers, freeway and bayou. *Latency is from resuming the poll after the outage. | ⚠️ |
| T5b | Heatmap, varied area — Las Vegas Strip | 36.1147, −115.1728, 2.04 mi² · 15 Jul 15:00 · 60 m | 50.6 s | 4,220 | 1,455 tiles, **41.10–41.28 °C (range 0.18 °C)**, std 0.03 across casinos, pools, golf and parking. The near-flat result is **not Phoenix-specific**. | ❌ Near-flat |
| T6 | Satellite segmentation via API | `sat` 33.4300, −112.0600 · 15 Jul (`filter_type: 3`) · 100 m | 49 s → 133 s | 0 | First attempt: status 504 (outage). Re-submitted: **`Failed` after 133 s, no reason** (`raw_status` has only `activity_id`, `status`, `task_id`). | ❌ |
| T6b | Satellite, retry with docs-style body | `sat` = downtown Phoenix · 15 Jul 15:00 `filter_type: 1` · default granularity | 283 s | 0 | Status polling returned 504 for several minutes (while other activity IDs returned 200), then `Processing` for 10+ minutes, then **`Failed`, no reason**. Three attempts with three different bodies; satellite segmentation **never completed via the API** (it did work in the dashboard on 14 Nov). | ❌ |
| T7 | Street View at a road centreline | Central Ave, 33.4560, −112.07399 · vertical 0°, horizontal 0°, back view | 105 s → 123 s | 0 | Two attempts, both **`Failed`, no reason given**. (A17 on 14 Nov did complete, at City Hall, with indoor imagery.) | ❌ |
| T7b | Street View, docs' own Python example | NYC 40.7128, −74.0060 · vertical 10°, horizontal 90°, no back view | 142 s | 0 | TLS handshake failures, then **504 on submit** during the second incident. The credit ledger shows no new Street View charge (count stayed at 1). Not retried further. | ❌ (outage) |
| T8 | MCP `monitoring` → `list_monitors`, `list_alerts` | MCP, no arguments | 1.8 s / 1.2 s | 0 | `list_monitors` ✅ returns `monitors: []`. `list_alerts` ❌ returns `invalid_input` / *"The request input is invalid."* with no hint of which field is missing (the tool description calls it free and lists no required fields besides `operation`). Undocumented tool; it works. | ⚠️ |
| T9a | MCP `heatmap` → `heatmap_read` | 300 m × 300 m square at the Phoenix site · 15 Jul 15:00 · 100 m | 47.5 s (3 reads) | 4,220 | Submit returns `activity_id` plus `billing.submission_kind: "new"` and `credits_reserved_this_request: 4220`, which is excellent transparency. `heatmap_read` gives stats only: **min = max = mean = 40.78 °C, std 0.0** (9 tiles). heatmap_read is free. | ✅ flow / ❌ data |
| T9b | MCP `report` → `report_read` | Phoenix site · 105 °F · 15 Jul · `environmental` + `urban` | 349 s (14 reads) | 8,600 | Completed; `report_read` returns a signed S3 PDF URL (expires in 600 s). Submit's `report_url`, `docx_url`, `data_uri` and `data_url` are all `null` while processing. | ✅ |
| T10 | Status `?result_delivery=links` | Houston heatmap (T5a) | 0.7 s vs 5.1 s | 0 | Default: **526 KB** inline JSON. Links: **1 KB** with `map_download_url` + `stats_download_url` (signed S3, `X-Amz-Expires=600`). Works well; the 10-minute expiry should be documented. | ✅ |

### Reliability incidents during testing (17 Nov 2026)

| When (UTC) | What happened |
|---|---|
| ~16:55–17:01 | **Full outage.** Every endpoint, including the free credits endpoint, status for already-completed jobs and `dashboard.fortyguard.com`, returned `504 upstream request timeout` after ~16 s. MCP `notifications/initialized` also returned 504. Recovered by 17:01:22 (probe log: [`phase_a/outage_probe.log`](phase_a/outage_probe.log)). It began while 8 Phase A jobs were in flight, so 8 concurrent requests may have contributed. |
| ~17:18–17:26 | **Second incident** (with only one request in flight). TLS handshake timeouts, `504` on submit and on the credits endpoint. Recovered by 17:25:58. |
| both | **A 504 on submit does not mean the job was not created.** T4a and T5b got `504` on `POST /v1/heatmap` and never received an `activity_id`, yet the heatmap count in `activity_breakdown` rose by two and **8,440 credits were charged** for results the client can never retrieve. A REST idempotency key (MCP already has `idempotency_key`) or a "list my activities" endpoint would fix this. |
| both | Separately, status polling for a submitted satellite job (T6b) returned 504 for several minutes while other activity IDs returned 200; it then reported `Processing` for more than 10 minutes. |
| ~17:35–17:36 | **Third incident.** The first Phoenix demo run got 504 on all 5 heatmap submits (before the circuit breaker existed). **None were charged**, so 504-on-submit is inconsistent: sometimes charged (first incident), sometimes not. |
| ~17:50–17:56, ~18:10 | **Fourth and fifth incidents.** 504s on the credits endpoint and on submit. The Heat Shift Audit pre-flight check refused to start (0 credits spent). During a Miami run, the circuit breaker stopped after the first 504 submit; only the 06:00 heatmap (completed) was charged. |

Total: five 504 incidents in about 75 minutes, on a weekday afternoon in US time zones. In each case the gateway answered and the upstream didn't.

### Findings while building Heat Shift Audit (Phase B demo runs)

| # | Observation | Evidence | Verdict |
|---|---|---|---|
| B1 | **Phoenix: a 300 m × 300 m AOI at 100 m returns 9 tiles with exactly the same value at every hour** (range 0.000 °C). The MCP `heatmap_read` for the same request also reported min = max = 40.78 °C, std 0.0. There, the 100 m grid looks like a resampled coarser cell (the analytics' `stats_data` says `value_representation: nearest_catalog_cell`). By contrast, the same 300 m AOI in **Miami varied 0.12–0.46 °C**, and a 1 km AOI in Houston varied 0.04–0.19 °C across 108 tiles. So effective resolution differs by city, and nothing in the response says which. | `runs/*_2026-07-15.md`, T9a | ❌ Phoenix / ⚠️ elsewhere |
| B2 | Phoenix 15 Jul: site temperature 35.7 °C at 06:00 → 40.8 °C at 15:00 → 38.0 °C at 18:00. A sensible diurnal shape, with a monsoon morning (RH 53 %, 2.2 mm rain at 09:00). | same | ✅ Plausible |
| B3 | Range-mode `heat_index_celsius` would have been off by **13.6 °C at 06:00** (API 54.0 °C vs 40.4 °C from the 06:00 heatmap temperature). For the temperature it *was* given, the API's heat index matches the NWS formula within 1 °C at every hour. | same | ❌ Design / docs |
| B4 | Provider `apparent_temperature_celsius` and heat index disagree by up to **18.2 °C** (09:00: apparent 33.3 °C vs heat index 51.5 °C). Two "feels-like" numbers in one response with no explanation of which to use. | same | ⚠️ Docs |
| B5 | **Houston heatmaps for a 300 m AOI `Failed` (no reason) at all 5 hours**, at 100 m and at 60 m. The 2 mi² Houston heatmap at 15:00 (T5a) completed. Phoenix and Miami 300 m AOIs completed. A **1 km × 1 km** Houston AOI worked at every hour, so the final Houston demo uses `--aoi-side 1000`. Failed activity IDs: 356b26fb…, 87750ffc…, f98e8351…, 5c561419…, 8ff0cd16…, d7ce8fe5… | `runs_houston` history, this log | ❌ Silent failure; no minimum-area rule documented |
| B6 | Heatmap latency in normal conditions: 40–80 s per hour sampled (Phoenix: 78, 45, 42, 45, 42 s); env_params range 28 s. | run JSON `latency_s` | ✅ |
| B7 | Credits charged matched the plan exactly (Phoenix: 24,000 expected = 24,000 by the usage endpoint). A second identical Phoenix run: 6/6 calls from the local cache, **0 credits**. | run JSON `credits` | ✅ |
| B8 | Range-mode heat index error vs per-hour heatmap temperature at 06:00: Phoenix 13.6 °C, **Houston 14.6 °C, Miami 17.6 °C**. Humid cities are worse, because the single input temperature is applied to high early-morning humidity. | run notes | ❌ |
| B9 | Results: Phoenix: no safe window (Danger 06:00–15:00, monsoon humidity in the morning). Houston: 06:00 only (Caution), then Extreme Caution. Miami: 06:00 only (Caution), then Extreme Caution. AQI stayed Good/Moderate (49–80) everywhere; wet-bulb peaked at 25.6 °C (Miami 15:00). | `runs/` | — |

### Credit reconciliation

From `/v1/system/fetch-api-key-usage`:

| Point | `total_remaining_credits` | Heatmap count | env_params count |
|---|---|---|---|
| Start of 17 Nov session | 943,220 | 4 | 3 |
| After Phase A | 899,280 | 11 | 5 |
| After Phase B demo runs | 823,060 | 27 | 8 |

- **Phase A: 43,940 credits.** That's T1 + T2 (5,800), T4a/T4b/T5a/T5b (16,880), MCP heatmap + report (12,820), plus **8,440 for two heatmaps that returned 504 on submit and were charged without an `activity_id`**.
- **Phase B: 76,220 credits.** That's 3 audits × 24,000, plus **4,220 for one more orphaned heatmap** (Miami 09:00: 504 on submit, charged later; heatmap count 27 vs 26 results retrieved).
- **Orphaned charges in total: 12,660 credits (3 heatmaps)**, paid for results that can never be retrieved.
- Failed jobs (satellite ×3, street view ×2, Houston 300 m heatmaps ×6) were not charged, as documented.
- `cycle_credits_used` (162,940) vs `total_credits_used` (176,940) still differ by 14,000 = 4 routing calls from 14 Nov. Routing still doesn't appear in `activity_breakdown` at all.
- The MCP `heatmap` submit reports `credits_reserved_this_request`; REST gives no per-call cost.

---

## Earlier tests — 14 Nov 2026 (from the evaluation notes)

### Dashboard

| # | Test | Result | Verdict |
|---|---|---|---|
| D1 | Onboarding | Form says "U.S. states only"; welcome screen says "explore temperature conditions for any location worldwide". | ❌ Contradiction |
| D2 | Interactive tour | 11 steps, skippable, Back/Next. Cannot be replayed; "Monitor Configuration" not covered. | ⚠️ |
| D3 | Sidebar icons | Hover tooltips exist; icons are non-semantic divs (not buttons). | ⚠️ Accessibility |
| D4 | Location search "Karachi" | Silently returns "Karachi Way, Socorro, TX" and "Karachi Street, MI". No coverage message. | ❌ |
| D5 | Demo heatmap | Auto-created at signup: 20 Jan 2022, winter, 45.9–60.5 °F, 104 mi², "City Name: N/A". Counts against daily quota. ~20 s to load. | ❌ Weak showcase |
| D6 | Create heatmap | ~47.6 mi², 60 m, 15 Jul 2026 15:00. ~40 s with step-by-step progress. Did not auto-open; list kept collapsing. No cost step. Time picker shows no timezone. Circle tool labelled "Area of polygon". | ⚠️ |
| D7 | Heatmap statistics | 104.88–105.64 °F (0.75 °F) across 47.6 mi², std 0.14. 12 legend bands each ~0.02–0.2 °F wide, so the map looks dramatically red-to-blue. | ❌ Misleading visual |
| D8 | Spatial pattern | Hotter south/industrial, cooler north (Arcadia/Biltmore). | ✅ |
| D9 | Accuracy panel | Explains a 7-tier accuracy index but doesn't say which tier this heatmap is. | ⚠️ |
| D10 | Monitor Configuration | Name, area, rules, forecast window ≤ 12 h, email alerts, PDF per alert. Rule unit defaults to °C while settings are °F. | ⚠️ |
| D11 | Environmental Parameters panel | Empty galleries trigger 404 console errors ("statusText: OK"). | ⚠️ Minor |
| D12 | Satellite segmentation | ~25 s. Building 54.7 %, Road 34.8 %, Tree 3.7 %, Plant 3.5 %, Others 3.3 %. No parking/pavement class. Instruction text doesn't match the button label. | ✅ / ⚠️ |
| D13 | Heat Intelligence report | Description says it improves "efficiency in heating systems". Long, general AI-style text. Factual error: Salt River "3–5 miles north" (it is adjacent, to the south). Queue said Completed while gallery said "No reports saved yet". | ❌ |
| D14 | Coolest Route | Driving only. Phoenix → Tempe "Leave now": 1 route labelled both "Only route" and "Balanced route". 34.62 °C avg at ~4 AM in November. °C despite °F setting. | ❌ |
| D15 | Selesious AI agent | After choosing the Phoenix heatmap from its own list: "I couldn't find Phoenix near this map." | ❌ |
| D16 | Settings / Usage | Units configurable; 30 heatmaps/day; separate from API credits. | ✅ |
| D17 | Branding | "™" vs "®"; welcome email "Hi ," (blank name); credentials emailed in plain text. | ⚠️ Minor |

### REST API

| # | Test | Result | Verdict |
|---|---|---|---|
| A1 | Credits endpoint | Undocumented `POST /v1/system/fetch-api-key-usage`. Plan = Premium (email said Free). `cycle_remaining_credits` ≠ `total_remaining_credits` (gap = routing charges, missing from `activity_breakdown`). | ❌ Docs + data |
| A2 | env_params Phoenix 15 Jul 15:00, 40.8 °C | ~8 s. HI 41.7, apparent 41.5, wet-bulb 23.7, RH 23.2 %, AQI 48.7, GHI 813.65. | ✅ |
| A3 | Same with temperature 20 | HI 20.0, apparent 41.5 (unchanged). HI is computed from the caller's temperature. | ⚠️ Design + docs |
| A4 | env_params Karachi | 400 `OUT_OF_COVERAGE`, clear. | ✅ |
| A5 | Bad date format `15-07-2026` | **500** instead of a 400 validation error. | ❌ |
| A6 | Invalid key | 401, clear. | ✅ |
| A7 | Heatmap 60 m, ~1.2 mi² downtown | ~29 s, 854 tiles, 40.7696–40.7813 °C (0.012 °C). | ❌ Near-flat |
| A8 | Heatmap 20 m | Failed after ~10 s, no reason. | ❌ |
| A9 | Heatmap exceedance > 40 °C | Every tile = 5 h. Stats keys differ between analytics and from the docs. | ⚠️ |
| A10 | FeatureCollection AOI | Works. | ✅ |
| A11 | Heatmap > 50 mi² | Clear 400. | ✅ |
| A12 | Recent date (12 Nov) | Works. | ✅ |
| A13 | Routing Phoenix → Tempe 15 Jul 15:00 | 3 candidates, 1 distinct route, `no_cooling_available: true`. | ⚠️ |
| A14 | Routing "now" (Nov, ~4 AM) | Mean 34.6 °C, implausible. | ❌ |
| A15 | Routing Glendale → Scottsdale | Coolest route: +4.1 min to save 0.06 °C. | ⚠️ |
| A16 | Same trip 06:00 | 1 route, 34.3 °C. | — |
| A17 | Street View, Phoenix City Hall | Indoor law-office imagery (2015); back image segmented as "others 100 %". | ❌ |
| A18 | Heat Intelligence API | ~292 s, 22-page PDF. Docs contradict themselves on °F vs °C. | ⚠️ |

### MCP

| # | Test | Result | Verdict |
|---|---|---|---|
| M1 | Connect + initialize | Works first time with the Bearer header. Server `FortyGuard` 4.0.11. | ✅ |
| M2 | tools/list | 11 tools (docs say 9): `credit_balance` and `monitoring` are undocumented. | ⚠️ Docs |
| M3 | `env_params` docs example | ~8 s. | ✅ |
| M4 | `credit_balance` | Free; matches the REST credits endpoint (943,220 on 17 Nov). | ✅ |

### Documentation inconsistencies

- Plan names: Basic / Premium (intro), "Startup" (QGIS, endpoints, MCP), "Free" (email), "hackathon" (MCP pricing).
- Earliest date: REST heatmap 2019-01-01; MCP 2021-01-01; satellite "from 2019-01-01"; dashboard date picker back to 2003.
- Granularity: REST docs 20/60/80/100 (satellite docs also list 20); MCP, dashboard and QGIS 60/80/100; 20 m heatmap failed (A8).
- Heat Intelligence: MCP says Premium max 2 analysis types; the dashboard allowed all 5.
- Credits endpoint labelled GET in the docs; it is POST, and the path is not shown.
- Satellite result field documented as `Orignal_image` (typo, kept as a "legacy alias").
- MCP heatmap: `end_time` is end-exclusive (MCP schema); REST env_params range is end-inclusive (T1).
- Product naming: "Enterprise API" (Quickstart, MCP), "Temperature API®" (email), "API Services" (intro).
