"""Typed runtime data structures for the OKRWeather integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .const import (
    CONF_ALERT_LOCATION_ID,
    CONF_STATION_CITY,
    CONF_STATION_ID,
    CONF_STATION_KEY,
    CONF_STATION_LAT,
    CONF_STATION_LON,
    CONF_STATION_NAME,
    CONF_STATION_SLUG,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry, ConfigSubentry

    from .api import OKRWeatherApiClient
    from .coordinator import (
        OKRWeatherForecastCoordinator,
        OKRWeatherInsightsCoordinator,
        OKRWeatherLiveCoordinator,
    )


type OKRWeatherConfigEntry = ConfigEntry[OKRWeatherData]


@dataclass
class StationConfig:
    """Resolved metadata for one configured station (one subentry)."""

    subentry_id: str
    appwrite_id: str      # weather-stations row $id — used for relationship queries
    station_key: str      # weather-stations.station_id column — used to match AI rows
    slug: str
    name: str
    city: str | None      # display city; links the station to forecast/radar cities
    latitude: float | None
    longitude: float | None
    alert_location_id: str | None

    # Resolved lazily against live data; not persisted.
    forecast_city_id: str | None = None
    radar_city_id: str | None = None

    @classmethod
    def from_subentry(cls, subentry: ConfigSubentry) -> StationConfig:
        """Build a StationConfig from a station subentry."""
        data = subentry.data
        return cls(
            subentry_id=subentry.subentry_id,
            appwrite_id=data[CONF_STATION_ID],
            station_key=data.get(CONF_STATION_KEY) or data[CONF_STATION_ID],
            slug=data.get(CONF_STATION_SLUG) or data[CONF_STATION_ID],
            name=data.get(CONF_STATION_NAME) or data[CONF_STATION_ID],
            city=data.get(CONF_STATION_CITY),
            latitude=data.get(CONF_STATION_LAT),
            longitude=data.get(CONF_STATION_LON),
            alert_location_id=data.get(CONF_ALERT_LOCATION_ID),
        )

    def refresh_from_row(self, row: dict[str, Any]) -> None:
        """Update mutable metadata from a live weather-stations row.

        Subentry data can go stale (or, for entries migrated from v1, lack
        the city/alert fields entirely); the live table is authoritative.
        """
        self.station_key = row.get("station_id") or self.station_key
        self.slug = row.get("slug") or self.slug
        self.name = row.get("name") or self.name
        self.city = row.get("city") or self.city
        if isinstance(row.get("latitude"), (int, float)):
            self.latitude = float(row["latitude"])
        if isinstance(row.get("longitude"), (int, float)):
            self.longitude = float(row["longitude"])
        self.alert_location_id = row.get("alert_location_id") or self.alert_location_id


@dataclass
class OKRWeatherData:
    """Container stored on ``ConfigEntry.runtime_data``."""

    client: OKRWeatherApiClient
    live_coordinator: OKRWeatherLiveCoordinator
    insights_coordinator: OKRWeatherInsightsCoordinator
    forecast_coordinator: OKRWeatherForecastCoordinator
    stations: dict[str, StationConfig]  # keyed by subentry_id
    premium_enabled: bool = False
