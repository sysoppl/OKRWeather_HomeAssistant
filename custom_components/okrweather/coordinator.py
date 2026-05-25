"""DataUpdateCoordinators for OKRWeather.

Two coordinators sit side-by-side so the live sensor data (cheap, refreshed
often) is decoupled from the forecast + AI data (expensive on the backend,
refreshed at most every few hours).

Both coordinators populate a single dict that downstream entities read from,
keyed by section name (``weather``, ``air``, ``alerts``, ``comfort_index``…).
Premium tables that come back 401/403 are recorded in
``runtime_data.premium_tables_blocked`` so the corresponding entities can mark
themselves unavailable without us re-trying them on every poll.
"""

from __future__ import annotations

import asyncio
import math
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api import (
    OKRWeatherApiAuthError,
    OKRWeatherApiClient,
    OKRWeatherApiCommunicationError,
    OKRWeatherApiError,
    OKRWeatherApiPermissionError,
)
from .const import (
    DOMAIN,
    LOGGER,
    TABLE_AIR_QUALITY_TRENDS,
    TABLE_COMFORT_INDEX,
    TABLE_DRYING_CONDITIONS,
    TABLE_FROST_ALERTS,
    TABLE_OUTFIT_RECS,
    TABLE_PRESSURE_ALERTS,
    TABLE_SOLAR_FORECAST,
    TABLE_SPORT_CONDITIONS,
    TABLE_STORM_TRACKER,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .data import OKRWeatherConfigEntry


# ── Premium-table catalogue ──────────────────────────────────────────────────
# Maps the section name we expose to entities → the Appwrite table id we pull.

PREMIUM_TABLES: dict[str, str] = {
    "comfort_index": TABLE_COMFORT_INDEX,
    "frost_alert": TABLE_FROST_ALERTS,
    "solar_forecast": TABLE_SOLAR_FORECAST,
    "sport_conditions": TABLE_SPORT_CONDITIONS,
    "drying_conditions": TABLE_DRYING_CONDITIONS,
    "outfit_recommendations": TABLE_OUTFIT_RECS,
    "pressure_alert": TABLE_PRESSURE_ALERTS,
    "storm_tracker": TABLE_STORM_TRACKER,
    "air_quality_trend": TABLE_AIR_QUALITY_TRENDS,
}


# ── Helpers ──────────────────────────────────────────────────────────────────


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres."""
    r = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(d_lon / 2) ** 2
    )
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


async def resolve_nearest_city_id(
    client: OKRWeatherApiClient,
    station_lat: float,
    station_lon: float,
) -> str | None:
    """Find the forecast cityId whose lat/lon is nearest to the station.

    Forecasts are stored per OWM city, not per physical station, so we pick the
    closest one once at setup time and reuse it.
    """
    try:
        rows = await client.all_hourly_forecasts(limit=500)
    except OKRWeatherApiError as err:
        LOGGER.warning("Could not enumerate forecast cities: %s", err)
        return None

    cities: dict[str, tuple[float, float]] = {}
    for row in rows:
        city_id = row.get("cityId")
        lat = row.get("lat")
        lon = row.get("lon")
        if city_id and isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
            cities.setdefault(city_id, (float(lat), float(lon)))

    if not cities:
        return None

    nearest = min(
        cities.items(),
        key=lambda item: _haversine_km(station_lat, station_lon, *item[1]),
    )
    LOGGER.debug(
        "Using forecast cityId '%s' (%.1f km from station)",
        nearest[0],
        _haversine_km(station_lat, station_lon, *nearest[1]),
    )
    return nearest[0]


# ── Base ─────────────────────────────────────────────────────────────────────


class _OKRWeatherCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Shared base — gives subclasses access to the config entry and client."""

    config_entry: OKRWeatherConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        name: str,
        update_interval: timedelta,
        entry: OKRWeatherConfigEntry,
    ) -> None:
        super().__init__(
            hass,
            LOGGER,
            name=f"{DOMAIN}_{name}",
            update_interval=update_interval,
            config_entry=entry,
        )

    @property
    def client(self) -> OKRWeatherApiClient:
        """The shared API client living on runtime_data."""
        return self.config_entry.runtime_data.client


# ── Live coordinator ────────────────────────────────────────────────────────


class OKRWeatherLiveCoordinator(_OKRWeatherCoordinator):
    """Polls live sensor data (weather + air quality) and alerts.

    These are public tables, so this coordinator works with or without an API
    key.  Alerts get folded into the same update so the binary-sensor and
    weather-entity attributes stay in sync.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry: OKRWeatherConfigEntry,
        update_interval: timedelta,
    ) -> None:
        super().__init__(
            hass,
            name="live",
            update_interval=update_interval,
            entry=entry,
        )

    async def _async_update_data(self) -> dict[str, Any]:
        station_id = self.config_entry.runtime_data.station.appwrite_id
        try:
            weather, air, alerts = await asyncio.gather(
                self.client.latest_weather(station_id),
                self.client.latest_air(station_id),
                self.client.active_alerts(),
                return_exceptions=False,
            )
        except OKRWeatherApiAuthError as err:
            # Live tables are public — auth errors here mean the project ID or
            # endpoint are wrong, which the user must fix in the config flow.
            raise ConfigEntryAuthFailed(str(err)) from err
        except (OKRWeatherApiCommunicationError, OKRWeatherApiError) as err:
            raise UpdateFailed(str(err)) from err

        return {
            "weather": weather,
            "air": air,
            "alerts": alerts or [],
        }


# ── Forecast + premium coordinator ──────────────────────────────────────────


class OKRWeatherForecastCoordinator(_OKRWeatherCoordinator):
    """Polls forecasts and premium AI tables on a slower cadence.

    Premium tables are skipped automatically when no API key is configured, or
    when a prior call returned 403 (recorded on ``runtime_data``). One bad
    table never knocks out the rest of the update.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry: OKRWeatherConfigEntry,
        update_interval: timedelta,
    ) -> None:
        super().__init__(
            hass,
            name="forecast",
            update_interval=update_interval,
            entry=entry,
        )

    async def _async_update_data(self) -> dict[str, Any]:
        runtime = self.config_entry.runtime_data
        station = runtime.station
        result: dict[str, Any] = {}

        # ── Forecasts (public) ────────────────────────────────────────────
        if station.city_id is None and station.latitude and station.longitude:
            station.city_id = await resolve_nearest_city_id(
                self.client, station.latitude, station.longitude
            )

        if station.city_id:
            try:
                hourly, daily = await asyncio.gather(
                    self.client.hourly_forecasts(station.city_id, hours=48),
                    self.client.daily_forecasts(station.city_id, days=10),
                )
                result["hourly_forecast"] = hourly
                result["daily_forecast"] = daily
            except OKRWeatherApiError as err:
                LOGGER.warning("Forecast fetch failed: %s", err)
                result["hourly_forecast"] = []
                result["daily_forecast"] = []
        else:
            result["hourly_forecast"] = []
            result["daily_forecast"] = []

        # ── Premium tables ────────────────────────────────────────────────
        if not runtime.premium_enabled:
            return result

        blocked = runtime.premium_tables_blocked
        active_keys = [k for k in PREMIUM_TABLES if k not in blocked]
        if not active_keys:
            return result

        rows = await asyncio.gather(
            *(
                self.client.latest_premium_row(
                    PREMIUM_TABLES[key], station.station_key
                )
                for key in active_keys
            ),
            return_exceptions=True,
        )

        for key, row_or_err in zip(active_keys, rows, strict=True):
            if isinstance(row_or_err, OKRWeatherApiPermissionError):
                LOGGER.info(
                    "Premium table '%s' returned 403 — disabling for this entry",
                    PREMIUM_TABLES[key],
                )
                blocked.add(key)
                result[key] = None
            elif isinstance(row_or_err, OKRWeatherApiAuthError):
                # The API key itself is bad → bail loud.
                raise ConfigEntryAuthFailed(str(row_or_err))
            elif isinstance(row_or_err, Exception):
                LOGGER.warning(
                    "Premium table '%s' fetch failed (will retry): %s",
                    PREMIUM_TABLES[key],
                    row_or_err,
                )
                result[key] = None
            else:
                result[key] = row_or_err

        return result
