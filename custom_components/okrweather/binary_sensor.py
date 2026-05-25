"""Binary sensors for OKRWeather.

Currently exposes a single ``weather_alert_active`` flag plus, when premium is
enabled, ``frost_alert_active`` and ``storm_alert_active``. Detailed alert
attributes (severity, title, expiration) ride along as state attributes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)

from .entity import OKRWeatherEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import (
        OKRWeatherForecastCoordinator,
        OKRWeatherLiveCoordinator,
    )
    from .data import OKRWeatherConfigEntry, StationInfo


# ── Setup ───────────────────────────────────────────────────────────────────


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OKRWeatherConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime = entry.runtime_data
    station = runtime.station

    entities: list[BinarySensorEntity] = [
        WeatherAlertBinarySensor(runtime.live_coordinator, station),
    ]
    if runtime.premium_enabled:
        entities.append(FrostAlertBinarySensor(runtime.forecast_coordinator, station))
        entities.append(StormAlertBinarySensor(runtime.forecast_coordinator, station))

    async_add_entities(entities)


# ── Entities ────────────────────────────────────────────────────────────────


class WeatherAlertBinarySensor(OKRWeatherEntity, BinarySensorEntity):
    """True when at least one weather alert is currently active."""

    entity_description = BinarySensorEntityDescription(
        key="weather_alert_active",
        translation_key="weather_alert_active",
        device_class=BinarySensorDeviceClass.SAFETY,
    )

    def __init__(
        self,
        coordinator: OKRWeatherLiveCoordinator,
        station: StationInfo,
    ) -> None:
        super().__init__(coordinator, station)
        self._attr_unique_id = f"{station.appwrite_id}_weather_alert_active"

    @property
    def is_on(self) -> bool:
        return bool(self._alerts())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        alerts = self._alerts()
        if not alerts:
            return {"count": 0}
        first = alerts[0]
        return {
            "count": len(alerts),
            "title": first.get("alertTitle"),
            "severity": first.get("severity"),
            "event_type": first.get("eventType"),
            "area": first.get("areaName"),
            "expires_at": first.get("expirationTime"),
            "description": first.get("description"),
        }

    def _alerts(self) -> list[dict[str, Any]]:
        data = self.coordinator.data or {}
        return data.get("alerts") or []


class FrostAlertBinarySensor(OKRWeatherEntity, BinarySensorEntity):
    """True when the latest frost row reports any frost level other than 'none'."""

    entity_description = BinarySensorEntityDescription(
        key="frost_alert_active",
        translation_key="frost_alert_active",
        device_class=BinarySensorDeviceClass.COLD,
    )

    def __init__(
        self,
        coordinator: OKRWeatherForecastCoordinator,
        station: StationInfo,
    ) -> None:
        super().__init__(coordinator, station)
        self._attr_unique_id = f"{station.appwrite_id}_frost_alert_active"

    @property
    def available(self) -> bool:
        if not super().available:
            return False
        runtime = self.coordinator.config_entry.runtime_data
        return "frost_alert" not in runtime.premium_tables_blocked

    @property
    def is_on(self) -> bool:
        row = self._row()
        if not row:
            return False
        level = (row.get("frost_level") or "").lower()
        return level not in ("", "none", "no_frost")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        row = self._row()
        if not row:
            return {}
        return {
            "level": row.get("frost_level"),
            "probability": row.get("frost_probability"),
            "window_start": row.get("frost_window_start"),
            "window_end": row.get("frost_window_end"),
            "advisory": row.get("advisory_pl") or row.get("advisory_en"),
            "ice_risk": row.get("ice_risk"),
        }

    def _row(self) -> dict[str, Any] | None:
        data = self.coordinator.data or {}
        return data.get("frost_alert")


class StormAlertBinarySensor(OKRWeatherEntity, BinarySensorEntity):
    """True when the storm tracker reports a storm in range."""

    entity_description = BinarySensorEntityDescription(
        key="storm_alert_active",
        translation_key="storm_alert_active",
        device_class=BinarySensorDeviceClass.PROBLEM,
    )

    def __init__(
        self,
        coordinator: OKRWeatherForecastCoordinator,
        station: StationInfo,
    ) -> None:
        super().__init__(coordinator, station)
        self._attr_unique_id = f"{station.appwrite_id}_storm_alert_active"

    @property
    def available(self) -> bool:
        if not super().available:
            return False
        runtime = self.coordinator.config_entry.runtime_data
        return "storm_tracker" not in runtime.premium_tables_blocked

    @property
    def is_on(self) -> bool:
        row = self._row()
        if not row:
            return False
        # The storm-tracker row format isn't strictly known; treat any value
        # other than null/'none'/'clear' as "storm active".
        status = (row.get("status") or row.get("storm_level") or "").lower()
        return status not in ("", "none", "clear", "no_storm")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        row = self._row()
        if not row:
            return {}
        # Pass through everything except Appwrite metadata so the user can
        # surface whichever columns the backend exposes.
        return {
            k: v
            for k, v in row.items()
            if not k.startswith("$") and k != "station"
        }

    def _row(self) -> dict[str, Any] | None:
        data = self.coordinator.data or {}
        return data.get("storm_tracker")
