"""Binary sensors for OKRWeather.

Per station:

* ``weather_alert`` — an unexpired government alert covers the station area.
* ``station_online`` — the station delivered data recently (diagnostic).

And, with premium enabled: frost alert, storm detected, radar rain /
rain-approaching and pressure alert flags driven by the AI tables.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory

from .const import (
    LIVE_STALE_MINUTES,
    SECTION_FROST,
    SECTION_PRESSURE,
    SECTION_RADAR,
    SECTION_STORM,
)
from .entity import OKRWeatherEntity
from .util import age_minutes, normalize_enum

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from .coordinator import OKRWeatherCoordinator
    from .data import OKRWeatherConfigEntry, StationConfig

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class OKRBinarySensorDescription(BinarySensorEntityDescription):
    """Binary sensor description driven by one section row."""

    section: str
    is_on_fn: Callable[[dict[str, Any]], bool]
    attributes_fn: (
        Callable[[dict[str, Any], Callable[[str], Any]], dict[str, Any]] | None
    ) = None


def _not_none_level(key: str) -> Callable[[dict[str, Any]], bool]:
    return lambda row: normalize_enum(row.get(key)) not in (None, "none")


INSIGHT_BINARY_SENSORS: tuple[OKRBinarySensorDescription, ...] = (
    OKRBinarySensorDescription(
        key="frost_alert",
        translation_key="frost_alert",
        device_class=BinarySensorDeviceClass.COLD,
        section=SECTION_FROST,
        is_on_fn=_not_none_level("frost_level"),
        attributes_fn=lambda row, loc: {
            "level": normalize_enum(row.get("frost_level")),
            "probability": row.get("frost_probability"),
            "window_start": row.get("frost_window_start"),
            "window_end": row.get("frost_window_end"),
            "ice_risk": row.get("ice_risk"),
            "advisory": loc("advisory"),
        },
    ),
    OKRBinarySensorDescription(
        key="storm_detected",
        translation_key="storm_detected",
        device_class=BinarySensorDeviceClass.SAFETY,
        section=SECTION_STORM,
        is_on_fn=lambda row: bool(row.get("storm_detected")),
        attributes_fn=lambda row, loc: {
            "proximity": normalize_enum(row.get("proximity_level")),
            "intensity": normalize_enum(row.get("storm_intensity")),
            "eta_minutes": row.get("eta_minutes"),
            "lightning_distance_km": row.get("lightning_distance_km"),
            "advisory": loc("advisory"),
        },
    ),
    OKRBinarySensorDescription(
        key="radar_raining",
        translation_key="radar_raining",
        device_class=BinarySensorDeviceClass.MOISTURE,
        section=SECTION_RADAR,
        is_on_fn=lambda row: bool(row.get("is_raining")),
        attributes_fn=lambda row, loc: {
            "intensity": normalize_enum(row.get("intensity")),
            "rain_rate_mmh": row.get("rain_rate_mmh"),
            "coverage_percent": row.get("coverage_percent"),
        },
    ),
    OKRBinarySensorDescription(
        key="radar_rain_approaching",
        translation_key="radar_rain_approaching",
        section=SECTION_RADAR,
        is_on_fn=lambda row: bool(row.get("is_approaching")),
        attributes_fn=lambda row, loc: {
            "eta_minutes": row.get("eta_minutes"),
            "closest_rain_km": row.get("closest_rain_km"),
            "closest_rain_direction": row.get("closest_rain_direction"),
        },
    ),
    OKRBinarySensorDescription(
        key="pressure_alert",
        translation_key="pressure_alert",
        device_class=BinarySensorDeviceClass.PROBLEM,
        section=SECTION_PRESSURE,
        is_on_fn=_not_none_level("alert_level"),
        attributes_fn=lambda row, loc: {
            "level": normalize_enum(row.get("alert_level")),
            "risk_score": row.get("risk_score"),
            "trend": normalize_enum(row.get("trend")),
            "alert_text": loc("alert_text"),
        },
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OKRWeatherConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add binary sensors for every station subentry."""
    runtime = entry.runtime_data

    for subentry_id, station in runtime.stations.items():
        entities: list[BinarySensorEntity] = [
            OKRWeatherAlertBinarySensor(runtime.live_coordinator, station),
            OKRStationOnlineBinarySensor(runtime.live_coordinator, station),
        ]
        if runtime.premium_enabled:
            entities.extend(
                OKRInsightBinarySensor(runtime.insights_coordinator, station, desc)
                for desc in INSIGHT_BINARY_SENSORS
            )
        async_add_entities(entities, config_subentry_id=subentry_id)


# ── Entities ─────────────────────────────────────────────────────────────────


class OKRInsightBinarySensor(OKRWeatherEntity, BinarySensorEntity):
    """Binary sensor driven by one premium AI section."""

    entity_description: OKRBinarySensorDescription

    def __init__(
        self,
        coordinator: OKRWeatherCoordinator,
        station: StationConfig,
        description: OKRBinarySensorDescription,
    ) -> None:
        super().__init__(coordinator, station, description)

    @property
    def _row(self) -> dict[str, Any] | None:
        row = self.section_row(self.entity_description.section)
        return row if isinstance(row, dict) else None

    @property
    def is_on(self) -> bool | None:
        if (row := self._row) is None:
            return None
        return self.entity_description.is_on_fn(row)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        attributes_fn = self.entity_description.attributes_fn
        if attributes_fn is None or (row := self._row) is None:
            return None
        attrs = attributes_fn(row, lambda base: self.localized(row, base))
        return {k: v for k, v in attrs.items() if v is not None} or None


class OKRWeatherAlertBinarySensor(OKRWeatherEntity, BinarySensorEntity):
    """On when at least one unexpired alert covers the station's area."""

    entity_description = BinarySensorEntityDescription(
        key="weather_alert",
        translation_key="weather_alert",
        device_class=BinarySensorDeviceClass.SAFETY,
    )

    def __init__(
        self,
        coordinator: OKRWeatherCoordinator,
        station: StationConfig,
    ) -> None:
        super().__init__(coordinator, station)
        self._attr_unique_id = f"{station.appwrite_id}_weather_alert_active"

    def _alerts(self) -> list[dict[str, Any]]:
        # Pre-filtered per station by the live coordinator.
        return self.section_row("alerts") or []

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


class OKRStationOnlineBinarySensor(OKRWeatherEntity, BinarySensorEntity):
    """On when the station delivered a weather reading recently."""

    entity_description = BinarySensorEntityDescription(
        key="station_online",
        translation_key="station_online",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
    )

    def __init__(
        self,
        coordinator: OKRWeatherCoordinator,
        station: StationConfig,
    ) -> None:
        super().__init__(coordinator, station)
        self._attr_unique_id = f"{station.appwrite_id}_station_online"

    @property
    def is_on(self) -> bool | None:
        row = self.section_row("weather")
        if not isinstance(row, dict):
            return False
        age = age_minutes(row.get("measurementDate") or row.get("$createdAt"))
        if age is None:
            return None
        return age <= LIVE_STALE_MINUTES
