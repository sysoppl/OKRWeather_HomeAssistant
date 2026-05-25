"""Typed runtime data structures for the OKRWeather integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.loader import Integration

    from .api import OKRWeatherApiClient
    from .coordinator import (
        OKRWeatherForecastCoordinator,
        OKRWeatherLiveCoordinator,
    )


type OKRWeatherConfigEntry = ConfigEntry[OKRWeatherData]


@dataclass
class StationInfo:
    """Resolved metadata for the configured station."""

    appwrite_id: str
    slug: str
    name: str
    latitude: float | None
    longitude: float | None
    city_id: str | None = None  # nearest forecast cityId; None until resolved


@dataclass
class OKRWeatherData:
    """Container stored on `ConfigEntry.runtime_data`."""

    client: OKRWeatherApiClient
    live_coordinator: OKRWeatherLiveCoordinator
    forecast_coordinator: OKRWeatherForecastCoordinator
    station: StationInfo
    integration: Integration
    premium_enabled: bool = False
    premium_tables_blocked: set[str] = field(default_factory=set)
