"""Constants for the OKRWeather integration."""

from __future__ import annotations

from logging import Logger, getLogger
from typing import Final

LOGGER: Logger = getLogger(__package__)

DOMAIN: Final = "okrweather"
MANUFACTURER: Final = "OKRWeather"

# ── Bundled Lovelace card ────────────────────────────────────────────────────
# Served from custom_components/okrweather/frontend/ and auto-registered on
# every dashboard. The manifest version cache-busts browsers on release.
FRONTEND_URL_BASE: Final = f"/{DOMAIN}-frontend"
FRONTEND_CARD_FILENAME: Final = "okrweather-card.js"

ATTRIBUTION: Final = "Data from Pogoda OKR (pogodaokr.pl)"

# ── Appwrite endpoint ────────────────────────────────────────────────────────
# Production project. The custom domain is CloudFlare-fronted; the integration
# can be pointed at a different endpoint via the config flow's advanced fields.
DEFAULT_ENDPOINT: Final = "https://api.skydark.pl/v1"
DEFAULT_PROJECT_ID: Final = "69984f5500258ad65c55"
DATABASE_ID: Final = "pogodaokr-data"

# ── Subentries ───────────────────────────────────────────────────────────────
SUBENTRY_TYPE_STATION: Final = "station"

# ── Tables (free, read("any")) ───────────────────────────────────────────────
# Some backend tables were renamed in 2026-11. Each "*_OLD" id is the previous
# name; reads try the new id first and fall back to the old one while it
# still exists (see sources.py), so every backend state keeps working.
TABLE_STATIONS: Final = "weather-stations"
TABLE_STATION_READINGS: Final = "station-readings"
TABLE_STATION_READINGS_OLD: Final = "weather-data"
# Measured PM (Airly sensors); only stations with an air-quality source.
TABLE_AIR_QUALITY: Final = "air-quality-readings"
TABLE_HOURLY_FORECASTS: Final = "hourly-forecasts"
TABLE_DAILY_FORECASTS: Final = "daily-forecasts"
TABLE_ALERTS: Final = "weather-alerts"

# ── Tables (premium, read("label:sub*"), only ACTIVE AI functions) ──────────
# Disabled backend functions (sport, drying, outfit) are intentionally absent.
TABLE_COMFORT_INDEX: Final = "comfort-index"
TABLE_RADAR_STATUS: Final = "radar-status"
TABLE_STORM_ALERTS: Final = "storm-alerts"
TABLE_STORM_ALERTS_OLD: Final = "storm-tracker"
TABLE_PRESSURE_ALERTS: Final = "pressure-alerts"
TABLE_FROST_ALERTS: Final = "frost-alerts"
TABLE_SOLAR_FORECASTS: Final = "solar-forecasts"
TABLE_SOLAR_FORECASTS_OLD: Final = "solar-forecast"

# ── Insight sections (coordinator data keys) ─────────────────────────────────
SECTION_COMFORT: Final = "comfort_index"
SECTION_RADAR: Final = "radar"
SECTION_STORM: Final = "storm_tracker"
SECTION_PRESSURE: Final = "pressure_alert"
SECTION_FROST: Final = "frost_alert"
SECTION_SOLAR: Final = "solar_forecast"

# Section → candidate premium tables, new id first. Radar is handled
# separately (keyed by city, not station), so it is not part of this map.
INSIGHT_TABLES: Final[dict[str, tuple[str, ...]]] = {
    SECTION_COMFORT: (TABLE_COMFORT_INDEX,),
    SECTION_STORM: (TABLE_STORM_ALERTS, TABLE_STORM_ALERTS_OLD),
    SECTION_PRESSURE: (TABLE_PRESSURE_ALERTS,),
    SECTION_FROST: (TABLE_FROST_ALERTS,),
    SECTION_SOLAR: (TABLE_SOLAR_FORECASTS, TABLE_SOLAR_FORECASTS_OLD),
}

# Maximum acceptable age (minutes) of an insight row before its data is
# treated as gone (entities become unknown instead of freezing on stale
# values). Roughly 4-6× each backend function's cron cadence.
INSIGHT_MAX_AGE_MIN: Final[dict[str, int]] = {
    SECTION_COMFORT: 30,       # cron */5
    SECTION_RADAR: 60,         # radar analysis ~every 10 min
    SECTION_STORM: 30,         # cron */5
    SECTION_PRESSURE: 60,      # cron */10
    SECTION_FROST: 12 * 60,    # cron 0 */3
    SECTION_SOLAR: 16 * 60,    # cron 0 */4
}

# A station is considered offline when its newest weather row is older than
# this (the stations report roughly once a minute).
LIVE_STALE_MINUTES: Final = 15

# Latest station reading: only rows of the last day are searched, so a
# station that stopped reporting goes unknown instead of freezing forever.
LIVE_LOOKBACK_HOURS: Final = 24

# Measured air quality: the current aggregate row counts while it is at most
# this old (Airly updates every 30-60 min).
AIR_MAX_AGE_MIN: Final = 120

# Entities whose backend data no longer exists (station lightning, the AI
# air-quality trend and gas sensors). Config entry migration 2.2 removes them
# from the entity registry.
RETIRED_ENTITY_KEYS: Final = (
    "lightning_distance",
    "air_quality_trend",
    "aqi_tracked",
    "carbon_monoxide",
    "nitrogen_dioxide",
    "ammonia",
)

# ── Config-entry keys ────────────────────────────────────────────────────────
CONF_API_KEY: Final = "api_key"
CONF_ENDPOINT: Final = "endpoint"
CONF_PROJECT_ID: Final = "project_id"
CONF_STATIONS: Final = "stations"
CONF_LIVE_INTERVAL: Final = "live_interval"
CONF_INSIGHTS_INTERVAL: Final = "insights_interval"
CONF_FORECAST_INTERVAL: Final = "forecast_interval"
CONF_LANGUAGE: Final = "language"

# ── Station subentry keys ────────────────────────────────────────────────────
CONF_STATION_ID: Final = "station_id"          # Appwrite row $id
CONF_STATION_KEY: Final = "station_key"        # weather-stations.station_id column
CONF_STATION_NAME: Final = "station_name"
CONF_STATION_SLUG: Final = "station_slug"
CONF_STATION_CITY: Final = "station_city"
CONF_STATION_LAT: Final = "station_lat"
CONF_STATION_LON: Final = "station_lon"
CONF_STATION_ELEVATION: Final = "station_elevation"
CONF_ALERT_LOCATION_ID: Final = "alert_location_id"

# ── Refresh-interval bounds (seconds) ────────────────────────────────────────
MIN_LIVE_INTERVAL: Final = 60
MAX_LIVE_INTERVAL: Final = 3_600
DEFAULT_LIVE_INTERVAL: Final = 300  # 5 min

# Premium AI tables refresh every 5-15 min on the backend.
MIN_INSIGHTS_INTERVAL: Final = 120
MAX_INSIGHTS_INTERVAL: Final = 3_600
DEFAULT_INSIGHTS_INTERVAL: Final = 600  # 10 min

# Forecast tables refresh every 4 h on the backend.
MIN_FORECAST_INTERVAL: Final = 900
MAX_FORECAST_INTERVAL: Final = 21_600
DEFAULT_FORECAST_INTERVAL: Final = 1_800  # 30 min

# ── Language for advisory/description attributes ────────────────────────────
LANG_AUTO: Final = "auto"
LANG_PL: Final = "pl"
LANG_EN: Final = "en"
DEFAULT_LANGUAGE: Final = LANG_AUTO

# ── Enum vocabularies (as written by the backend AI functions) ──────────────
# Values are normalised to lower_snake_case before being exposed as ENUM
# sensor states, so "Very Poor" → "very_poor".
COMFORT_LABELS: Final = ["excellent", "good", "fair", "poor", "very_poor"]
FROST_LEVELS: Final = ["none", "low", "moderate", "high", "very_high"]
PRESSURE_ALERT_LEVELS: Final = ["none", "low", "moderate", "high", "extreme"]
PRESSURE_TRENDS: Final = ["rising", "falling", "stable"]
STORM_PROXIMITY_LEVELS: Final = [
    "none",
    "distant",
    "approaching",
    "nearby",
    "close",
    "overhead",
]
STORM_INTENSITY_LEVELS: Final = ["none", "mild", "moderate", "severe", "extreme"]
RADAR_INTENSITIES: Final = ["none", "light", "moderate", "heavy", "extreme"]
RADAR_TRENDS: Final = [
    "clear",
    "nearby",
    "approaching",
    "arriving",
    "raining",
    "intensifying",
    "weakening",
    "departing",
]
SOLAR_LABELS: Final = ["excellent", "good", "fair", "poor", "very_poor"]

# ── Misc ─────────────────────────────────────────────────────────────────────
# Wind in the database is stored in m/s; entities expose km/h.
MS_TO_KMH: Final = 3.6
