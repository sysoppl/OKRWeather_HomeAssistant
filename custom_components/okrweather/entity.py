"""Shared entity base for OKRWeather."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTRIBUTION,
    CONF_LANGUAGE,
    DOMAIN,
    LANG_AUTO,
    LANG_PL,
    MANUFACTURER,
)

if TYPE_CHECKING:
    from homeassistant.helpers.entity import EntityDescription

    from .coordinator import OKRWeatherCoordinator
    from .data import StationConfig


def station_device_info(station: StationConfig) -> DeviceInfo:
    """Device metadata for one weather station."""
    return DeviceInfo(
        identifiers={(DOMAIN, station.appwrite_id)},
        name=station.name,
        manufacturer=MANUFACTURER,
        model="Weather Station",
        serial_number=station.station_key,
        configuration_url="https://pogodaokr.pl",
    )


class OKRWeatherEntity(CoordinatorEntity["OKRWeatherCoordinator"]):
    """Base class — wires up the station device and shared attribution."""

    _attr_attribution = ATTRIBUTION
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: OKRWeatherCoordinator,
        station: StationConfig,
        description: EntityDescription | None = None,
    ) -> None:
        super().__init__(coordinator)
        self._station = station
        if description is not None:
            self.entity_description = description
            self._attr_unique_id = f"{station.appwrite_id}_{description.key}"
        self._attr_device_info = station_device_info(station)

    @property
    def station_data(self) -> dict[str, Any]:
        """This station's slice of the coordinator data."""
        data = self.coordinator.data or {}
        return data.get("stations", {}).get(self._station.subentry_id) or {}

    def section_row(self, section: str) -> Any:
        """One section (weather / air / comfort_index / …) of the station data."""
        return self.station_data.get(section)

    @property
    def advisory_language(self) -> str:
        """Language for advisory/description attributes ('en' or 'pl')."""
        lang = self.coordinator.config_entry.options.get(CONF_LANGUAGE, LANG_AUTO)
        if lang != LANG_AUTO:
            return lang
        ha_lang = (self.coordinator.hass.config.language or "en").lower()
        return LANG_PL if ha_lang.startswith("pl") else "en"

    def localized(self, row: dict[str, Any], base: str) -> Any:
        """Pick `{base}_pl` or `{base}_en` from a row based on the language."""
        suffix = "_pl" if self.advisory_language == LANG_PL else "_en"
        return row.get(f"{base}{suffix}") or row.get(f"{base}_en") or row.get(base)
