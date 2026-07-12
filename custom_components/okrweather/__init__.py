"""OKRWeather custom integration for Home Assistant."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from types import MappingProxyType
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigSubentry
from homeassistant.const import Platform
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import OKRWeatherApiClient
from .config_flow import station_subentry_data
from .const import (
    CONF_API_KEY,
    CONF_ENDPOINT,
    CONF_FORECAST_INTERVAL,
    CONF_INSIGHTS_INTERVAL,
    CONF_LANGUAGE,
    CONF_LIVE_INTERVAL,
    CONF_PROJECT_ID,
    CONF_STATION_ID,
    CONF_STATION_KEY,
    CONF_STATION_LAT,
    CONF_STATION_LON,
    CONF_STATION_NAME,
    CONF_STATION_SLUG,
    DEFAULT_ENDPOINT,
    DEFAULT_FORECAST_INTERVAL,
    DEFAULT_INSIGHTS_INTERVAL,
    DEFAULT_LANGUAGE,
    DEFAULT_LIVE_INTERVAL,
    DEFAULT_PROJECT_ID,
    DOMAIN,
    LOGGER,
    MAX_FORECAST_INTERVAL,
    MAX_LIVE_INTERVAL,
    MIN_FORECAST_INTERVAL,
    MIN_LIVE_INTERVAL,
    SUBENTRY_TYPE_STATION,
)
from .coordinator import (
    OKRWeatherForecastCoordinator,
    OKRWeatherInsightsCoordinator,
    OKRWeatherLiveCoordinator,
)
from .data import OKRWeatherData, StationConfig

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
    """Set up an OKRWeather hub entry and its station subentries."""
    data = entry.data
    options = entry.options

    api_key: str | None = data.get(CONF_API_KEY) or None
    client = OKRWeatherApiClient(
        session=async_get_clientsession(hass),
        endpoint=data.get(CONF_ENDPOINT, DEFAULT_ENDPOINT),
        project_id=data.get(CONF_PROJECT_ID, DEFAULT_PROJECT_ID),
        api_key=api_key,
    )

    stations = {
        subentry.subentry_id: StationConfig.from_subentry(subentry)
        for subentry in entry.subentries.values()
        if subentry.subentry_type == SUBENTRY_TYPE_STATION
    }

    live = OKRWeatherLiveCoordinator(
        hass,
        entry,
        update_interval=timedelta(
            seconds=int(options.get(CONF_LIVE_INTERVAL, DEFAULT_LIVE_INTERVAL))
        ),
    )
    insights = OKRWeatherInsightsCoordinator(
        hass,
        entry,
        update_interval=timedelta(
            seconds=int(options.get(CONF_INSIGHTS_INTERVAL, DEFAULT_INSIGHTS_INTERVAL))
        ),
    )
    forecast = OKRWeatherForecastCoordinator(
        hass,
        entry,
        update_interval=timedelta(
            seconds=int(options.get(CONF_FORECAST_INTERVAL, DEFAULT_FORECAST_INTERVAL))
        ),
    )

    entry.runtime_data = OKRWeatherData(
        client=client,
        live_coordinator=live,
        insights_coordinator=insights,
        forecast_coordinator=forecast,
        stations=stations,
        premium_enabled=bool(api_key),
    )

    # The live refresh blocks setup so entities start with data; the slower
    # coordinators refresh concurrently (their failures don't block setup —
    # they retry on their own schedule).
    await live.async_config_entry_first_refresh()
    if entry.runtime_data.premium_enabled:
        await asyncio.gather(forecast.async_refresh(), insights.async_refresh())
    else:
        await forecast.async_refresh()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_entry_updated))

    LOGGER.debug(
        "OKRWeather hub ready (%d station(s), premium=%s)",
        len(stations),
        bool(api_key),
    )
    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: OKRWeatherConfigEntry,
) -> bool:
    """Tear down a hub entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_entry_updated(
    hass: HomeAssistant,
    entry: OKRWeatherConfigEntry,
) -> None:
    """Reload on options changes and on station subentries being added/removed."""
    await hass.config_entries.async_reload(entry.entry_id)


# ── Migration ────────────────────────────────────────────────────────────────


async def async_migrate_entry(
    hass: HomeAssistant,
    entry: OKRWeatherConfigEntry,
) -> bool:
    """Migrate old config entries to the current version.

    v1 → v2: every v1 entry was a single station carrying its own copy of the
    backend credentials. It becomes a hub entry with one station subentry;
    the existing device and entities move onto the subentry so their history
    and entity ids survive.
    """
    if entry.version > 2:
        return False  # downgrade from a future version — bail out

    if entry.version == 1:
        old_data = {**entry.data}
        old_options = {**entry.options}
        station_id = old_data.get(CONF_STATION_ID)
        if not station_id:
            LOGGER.error("Cannot migrate entry %s: no station id", entry.entry_id)
            return False

        api_key = (
            old_options.get(CONF_API_KEY) or old_data.get(CONF_API_KEY) or None
        )
        new_data = {
            CONF_ENDPOINT: old_data.get(CONF_ENDPOINT, DEFAULT_ENDPOINT),
            CONF_PROJECT_ID: old_data.get(CONF_PROJECT_ID, DEFAULT_PROJECT_ID),
        }
        if api_key:
            new_data[CONF_API_KEY] = api_key

        # v1 had no insights interval; its forecast interval (min 1 h) also
        # covered the AI tables. Adopt the new defaults and clamp the rest.
        forecast_interval = int(
            old_options.get(CONF_FORECAST_INTERVAL, DEFAULT_FORECAST_INTERVAL)
        )
        live_interval = int(
            old_options.get(CONF_LIVE_INTERVAL, DEFAULT_LIVE_INTERVAL)
        )
        new_options = {
            # v1 allowed live polling up to 24 h; v2 caps it at 1 h. Clamp so
            # the options form isn't pre-filled with an unsaveable value.
            CONF_LIVE_INTERVAL: min(
                max(live_interval, MIN_LIVE_INTERVAL), MAX_LIVE_INTERVAL
            ),
            CONF_INSIGHTS_INTERVAL: DEFAULT_INSIGHTS_INTERVAL,
            CONF_FORECAST_INTERVAL: min(
                max(forecast_interval, MIN_FORECAST_INTERVAL), MAX_FORECAST_INTERVAL
            ),
            CONF_LANGUAGE: DEFAULT_LANGUAGE,
        }

        subentry = ConfigSubentry(
            data=MappingProxyType(
                station_subentry_data(
                    {
                        "$id": station_id,
                        "station_id": old_data.get(CONF_STATION_KEY),
                        "slug": old_data.get(CONF_STATION_SLUG),
                        "name": old_data.get(CONF_STATION_NAME),
                        # v1 never stored these; the live coordinator
                        # re-reads them from the stations table at setup.
                        "city": None,
                        "latitude": old_data.get(CONF_STATION_LAT),
                        "longitude": old_data.get(CONF_STATION_LON),
                        "alert_location_id": None,
                    }
                )
            ),
            subentry_type=SUBENTRY_TYPE_STATION,
            title=old_data.get(CONF_STATION_NAME) or station_id,
            unique_id=station_id,
        )

        hass.config_entries.async_update_entry(
            entry,
            title="OKRWeather",
            data=new_data,
            options=new_options,
            unique_id=None,
            version=2,
            minor_version=1,
        )
        hass.config_entries.async_add_subentry(entry, subentry)

        # Move the station device and all its entities onto the subentry so
        # nothing is orphaned and long-term statistics stay intact.
        #
        # ORDER MATTERS: entities must be re-pointed at the subentry BEFORE
        # the device's (entry, None) association is removed — the entity
        # registry reacts synchronously to that device update and deletes
        # every entity whose config_subentry_id just vanished from the
        # device's association set.
        device_registry = dr.async_get(hass)
        entity_registry = er.async_get(hass)

        # unique_ids that changed meaning in v2, and v1 entities whose
        # backing AI feature was retired (sport/drying/outfit + label-style
        # sensors replaced by ENUM sensors).
        renamed_suffixes = {
            "frost_alert_active": "frost_alert",
            "storm_alert_active": "storm_detected",
            "pressure_alert_label": "pressure_alert_level",
        }
        removed_suffixes = {
            "running_score",
            "running_label",
            "cycling_score",
            "cycling_label",
            "drying_score",
            "drying_label",
            "drying_estimated_hours",
            "outfit_recommendation",
            "storm_status",
            "frost_window",
        }
        for entity in er.async_entries_for_config_entry(
            entity_registry, entry.entry_id
        ):
            suffix = entity.unique_id.removeprefix(f"{station_id}_")
            if suffix in removed_suffixes:
                entity_registry.async_remove(entity.entity_id)
                continue
            if suffix in renamed_suffixes:
                entity_registry.async_update_entity(
                    entity.entity_id,
                    config_subentry_id=subentry.subentry_id,
                    new_unique_id=f"{station_id}_{renamed_suffixes[suffix]}",
                )
            else:
                entity_registry.async_update_entity(
                    entity.entity_id,
                    config_subentry_id=subentry.subentry_id,
                )

        if device := device_registry.async_get_device(
            identifiers={(DOMAIN, station_id)}
        ):
            # Two separate calls on purpose: combining add+remove in one call
            # would drop the freshly-added subentry association, because the
            # registry's remove branch rebuilds from the pre-update state.
            device_registry.async_update_device(
                device.id,
                add_config_entry_id=entry.entry_id,
                add_config_subentry_id=subentry.subentry_id,
            )
            device_registry.async_update_device(
                device.id,
                remove_config_entry_id=entry.entry_id,
                remove_config_subentry_id=None,
            )

        LOGGER.info(
            "Migrated OKRWeather entry %s to v2 (station '%s' became a subentry)",
            entry.entry_id,
            subentry.title,
        )

    return True
