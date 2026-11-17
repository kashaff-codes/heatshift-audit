"""All thresholds, credit costs and their sources in one place."""

# ---------------------------------------------------------------- credit costs
# Premium plan, verified against /v1/system/fetch-api-key-usage on 14-17 Nov 2026
# and the MCP tool descriptions (server v4.0.11).
CREDIT_COST = {
    "/v1/heatmap": 4220,
    "/v1/env_params": 2900,
    "/v1/routing": 3500,
    "/v1/streetview": 8600,
    "/v1/satellite": 14400,
    "/v1/heat_intelligence": 8600,
}

# ---------------------------------------------------------------- data limits
EARLIEST_DATE = "2021-01-01"   # MCP docs: historical temperature requests start 2021-01-01
HEATMAP_GRANULARITY_M = 100    # 60/80/100 work; 20 is documented for REST but failed in testing
AOI_SIDE_M = 300.0             # ~300 m x 300 m square around the site

# ---------------------------------------------------------------- heat index
# NWS heat index categories (degrees F).
# Source: NOAA/NWS Heat Index chart, https://www.weather.gov/safety/heat-index
# and https://www.wpc.ncep.noaa.gov/html/heatindex_equation.shtml (Rothfusz regression).
HEAT_INDEX_CATEGORIES_F = [
    # (lower bound inclusive, label)
    (125.0, "Extreme Danger"),
    (103.0, "Danger"),
    (90.0, "Extreme Caution"),
    (80.0, "Caution"),
    (float("-inf"), "OK"),
]
WORKABLE_CATEGORIES = {"OK", "Caution"}

# ---------------------------------------------------------------- air quality
# US EPA AQI bands. Source: https://www.airnow.gov/aqi/aqi-basics/
AQI_BANDS = [
    (301, "Hazardous"),
    (201, "Very Unhealthy"),
    (151, "Unhealthy"),
    (101, "Unhealthy for Sensitive Groups"),
    (51, "Moderate"),
    (0, "Good"),
]
AQI_FLAG_AT = 101

# ---------------------------------------------------------------- wet-bulb
# Illustrative threshold only, NOT official guidance. Configurable via --wet-bulb-warn.
WET_BULB_WARN_C = 28.0

# ---------------------------------------------------------------- data-quality checks
DQ_FLAT_RANGE_C = 0.1          # AOI temperature range below this = negligible spatial variation
DQ_HEAT_INDEX_MISMATCH_C = 1.0 # API heat index vs local NWS heat index
DQ_APPARENT_GAP_C = 3.0        # apparent temperature vs heat index
SENTINELS = (-999, -9999, -999.0, -9999.0)
