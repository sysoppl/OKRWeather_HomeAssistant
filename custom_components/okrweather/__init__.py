"""OKRWeather custom integration for Home Assistant."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from homeassistant.const import Platform
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.loader import async_get_loaded_integration

from .api import OKRWeatherApiClient
from .const import (
    CONF_API_KEY,
    CONF_ENDPOINT,
    CONF_FORECAST_INTERVAL,
    CONF_LIVE_INTERVAL,
    CONF_PROJECT_ID,
    CONF_STATION_ID,
    CONF_STATION_LAT,
    CONF_STATION_LON,
    CONF_STATION_NAME,
    CONF_STATION_SLUG,
    DEFAULT_ENDPOINT,
    DEFAULT_FORECAST_INTERVAL,
    DEFAULT_LIVE_INTERVAL,
    DEFAULT_PROJECT_ID,
    LOGGER,
)
from .coordinator import (
    OKRWeatherForecastCoordinator,
    OKRWeatherLiveCoordinator,
)
from .data import OKRWeatherData, StationInfo

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .data import OKRWeatherConfigEntry


PLATFORMS: list[Platform] = [
    Platform.WEATHER,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OKRWeatherConfigEntry,
) -> bool:
    """Set up an OKRWeather config entry."""
    options = entry.options or {}
    data = entry.data

    api_key: str | None = options.get(CONF_API_KEY) or data.get(CONF_API_KEY) or None
    endpoint: str = data.get(CONF_ENDPOINT, DEFAULT_ENDPOINT)
    project_id: str = data.get(CONF_PROJECT_ID, DEFAULT_PROJECT_ID)
    live_interval: int = int(
        options.get(CONF_LIVE_INTERVAL, DEFAULT_LIVE_INTERVAL)
    )
    forecast_interval: int = int(
        options.get(CONF_FORECAST_INTERVAL, DEFAULT_FORECAST_INTERVAL)
    )

    client = OKRWeatherApiClient(
        session=async_get_clientsession(hass),
        endpoint=endpoint,
        project_id=project_id,
        api_key=api_key,
    )

    station = StationInfo(
        appwrite_id=data[CONF_STATION_ID],
        slug=data.get(CONF_STATION_SLUG, data[CONF_STATION_ID]),
        name=data.get(CONF_STATION_NAME, data[CONF_STATION_ID]),
        latitude=data.get(CONF_STATION_LAT),
        longitude=data.get(CONF_STATION_LON),
    )

    live_coordinator = OKRWeatherLiveCoordinator(
        hass,
        entry,
        update_interval=timedelta(seconds=live_interval),
    )
    forecast_coordinator = OKRWeatherForecastCoordinator(
        hass,
        entry,
        update_interval=timedelta(seconds=forecast_interval),
    )

    entry.runtime_data = OKRWeatherData(
        client=client,
        live_coordinator=live_coordinator,
        forecast_coordinator=forecast_coordinator,
        station=station,
        integration=async_get_loaded_integration(hass, entry.domain),
        premium_enabled=bool(api_key),
    )

    # First refresh blocks setup so entities get initial data — if it fails the
    # entry is retried by HA, no need for us to manage that.
    await live_coordinator.async_config_entry_first_refresh()
    # Forecast coordinator may take longer (it discovers cityId on first run).
    # Don't block setup on it; let it populate in the background.
    await forecast_coordinator.async_refresh()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    LOGGER.debug(
        "OKRWeather setup complete (station=%s, premium=%s, live=%ss, forecast=%ss)",
        station.slug,
        bool(api_key),
        live_interval,
        forecast_interval,
    )
    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: OKRWeatherConfigEntry,
) -> bool:
    """Tear down a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_options_updated(
    hass: HomeAssistant,
    entry: OKRWeatherConfigEntry,
) -> None:
    """Reload when the user tweaks API key or refresh intervals."""
    await hass.config_entries.async_reload(entry.entry_id)
