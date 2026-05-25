"""Constants for the OKRWeather integration."""

from __future__ import annotations

from logging import Logger, getLogger
from typing import Final

LOGGER: Logger = getLogger(__package__)

DOMAIN: Final = "okrweather"
MANUFACTURER: Final = "OKRWeather"

ATTRIBUTION: Final = "Data from Pogoda OKR (pogodaokr.pl)"

# ── Appwrite endpoint ────────────────────────────────────────────────────────
# Production project. The custom domain is CloudFlare-fronted; the integration
# can be pointed at a different endpoint via the config flow's advanced step.
DEFAULT_ENDPOINT: Final = "https://api.skydark.pl/v1"
DEFAULT_PROJECT_ID: Final = "69984f5500258ad65c55"
DATABASE_ID: Final = "pogodaokr-data"

# ── Tables (free, read("any")) ────────────────────────────────────────────────
TABLE_STATIONS: Final = "weather-stations"
TABLE_WEATHER: Final = "weather-data"
TABLE_AIR: Final = "air-quality-data"
TABLE_HOURLY_FORECASTS: Final = "hourly-forecasts"
TABLE_DAILY_FORECASTS: Final = "daily-forecasts"
TABLE_AIR_FORECASTS: Final = "air-quality-forecasts"
TABLE_ALERTS: Final = "weather-alerts"

# ── Tables (premium, read("label:sub*")) ─────────────────────────────────────
TABLE_COMFORT_INDEX: Final = "comfort-index"
TABLE_FROST_ALERTS: Final = "frost-alerts"
TABLE_SOLAR_FORECAST: Final = "solar-forecast"
TABLE_SPORT_CONDITIONS: Final = "sport-conditions"
TABLE_DRYING_CONDITIONS: Final = "drying-conditions"
TABLE_OUTFIT_RECS: Final = "outfit-recommendations"
TABLE_PRESSURE_ALERTS: Final = "pressure-alerts"
TABLE_STORM_TRACKER: Final = "storm-tracker"
TABLE_AIR_QUALITY_TRENDS: Final = "air-quality-trends"

# ── Config-entry keys ────────────────────────────────────────────────────────
CONF_API_KEY: Final = "api_key"
CONF_STATION_ID: Final = "station_id"          # Appwrite document $id
CONF_STATION_NAME: Final = "station_name"      # human-readable, for entry title
CONF_STATION_SLUG: Final = "station_slug"
CONF_STATION_LAT: Final = "station_lat"
CONF_STATION_LON: Final = "station_lon"
CONF_LIVE_INTERVAL: Final = "live_interval"
CONF_FORECAST_INTERVAL: Final = "forecast_interval"
CONF_ENDPOINT: Final = "endpoint"
CONF_PROJECT_ID: Final = "project_id"
CONF_LANGUAGE: Final = "language"

# ── Refresh-interval bounds (seconds) ────────────────────────────────────────
# User-facing minimum is 60s — pulling more often would just hammer the backend
# without returning fresh data (the live tables update every ~60s anyway).
MIN_LIVE_INTERVAL: Final = 60
MAX_LIVE_INTERVAL: Final = 86_400  # 24h
DEFAULT_LIVE_INTERVAL: Final = 300  # 5 min

# Forecast tables refresh every 4h on the backend, so polling faster than 1h
# wastes API calls. Capped at 24h.
MIN_FORECAST_INTERVAL: Final = 3_600  # 1h
MAX_FORECAST_INTERVAL: Final = 86_400  # 24h
DEFAULT_FORECAST_INTERVAL: Final = 3_600  # 1h

# ── Language ─────────────────────────────────────────────────────────────────
LANG_PL: Final = "pl"
LANG_EN: Final = "en"
DEFAULT_LANGUAGE: Final = LANG_PL

# ── Misc ─────────────────────────────────────────────────────────────────────
# Wind in the database is stored in m/s; HA uses km/h natively. Multiply by 3.6.
MS_TO_KMH: Final = 3.6
