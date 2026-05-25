"""Shared entity base for OKRWeather."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, DOMAIN, MANUFACTURER

if TYPE_CHECKING:
    from .coordinator import _OKRWeatherCoordinator
    from .data import StationInfo


class OKRWeatherEntity(CoordinatorEntity["_OKRWeatherCoordinator"]):
    """Base class — wires up the station device and shared attribution."""

    _attr_attribution = ATTRIBUTION
    _attr_has_entity_name = True

    def __init__(self, coordinator: _OKRWeatherCoordinator, station: StationInfo) -> None:
        super().__init__(coordinator)
        self._station = station
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, station.appwrite_id)},
            name=station.name,
            manufacturer=MANUFACTURER,
            model="Weather Station",
            configuration_url="https://pogodaokr.pl",
        )
