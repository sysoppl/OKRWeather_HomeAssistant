"""Sensor platform — exposes every numeric reading and label from OKRWeather.

Sensors are grouped by source:

* ``LIVE_*`` — drawn from the fast coordinator (weather + air quality).
* ``PREMIUM_*`` — drawn from the slow coordinator and only spawned when an
  API key was configured. Each premium description names the section key the
  forecast coordinator publishes (``comfort_index``, ``frost_alert``, …),
  which lets us flip the entity to ``unavailable`` once a section is recorded
  as blocked.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    DEGREE,
    PERCENTAGE,
    UnitOfEnergy,
    UnitOfIrradiance,
    UnitOfLength,
    UnitOfPower,
    UnitOfPrecipitationDepth,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
    UnitOfTime,
    UnitOfVolumetricFlux,
)

from .const import MS_TO_KMH
from .entity import OKRWeatherEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import (
        OKRWeatherForecastCoordinator,
        OKRWeatherLiveCoordinator,
    )
    from .data import OKRWeatherConfigEntry, StationInfo


# ── Description ──────────────────────────────────────────────────────────────


@dataclass(frozen=True, kw_only=True)
class OKRSensorDescription(SensorEntityDescription):
    """Adds a value-extractor callback to the standard description."""

    value_fn: Callable[[dict[str, Any]], Any]
    # For premium sensors: the section key in the forecast coordinator data
    # (e.g. "comfort_index"). For live sensors it's the section in the live
    # coordinator ("weather", "air"). Used to look up the source row.
    section: str


# ── Value helpers ────────────────────────────────────────────────────────────


def _ms_to_kmh(value: Any) -> float | None:
    """Convert m/s to km/h, rounded to 1 decimal."""
    if value is None:
        return None
    try:
        return round(float(value) * MS_TO_KMH, 1)
    except (TypeError, ValueError):
        return None


def _passthrough(key: str) -> Callable[[dict[str, Any]], Any]:
    return lambda row: row.get(key) if row else None


def _wind_kmh(key: str) -> Callable[[dict[str, Any]], Any]:
    return lambda row: _ms_to_kmh(row.get(key)) if row else None


# ── Live sensors (always available) ─────────────────────────────────────────


LIVE_WEATHER_SENSORS: tuple[OKRSensorDescription, ...] = (
    OKRSensorDescription(
        key="temperature",
        translation_key="temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
        section="weather",
        value_fn=_passthrough("air_temperature_c"),
    ),
    OKRSensorDescription(
        key="apparent_temperature",
        translation_key="apparent_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
        section="weather",
        value_fn=_passthrough("sensed_temperature_c"),
    ),
    OKRSensorDescription(
        key="dew_point",
        translation_key="dew_point",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
        section="weather",
        value_fn=_passthrough("dew_point_c"),
    ),
    OKRSensorDescription(
        key="humidity",
        translation_key="humidity",
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=0,
        section="weather",
        value_fn=_passthrough("air_humidity_pct"),
    ),
    OKRSensorDescription(
        key="pressure",
        translation_key="pressure",
        device_class=SensorDeviceClass.ATMOSPHERIC_PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPressure.HPA,
        suggested_display_precision=1,
        section="weather",
        value_fn=_passthrough("air_pressure_hpa"),
    ),
    OKRSensorDescription(
        key="wind_speed",
        translation_key="wind_speed",
        device_class=SensorDeviceClass.WIND_SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        suggested_display_precision=1,
        section="weather",
        value_fn=_wind_kmh("wind_speed_m_s"),
    ),
    OKRSensorDescription(
        key="wind_gust",
        translation_key="wind_gust",
        device_class=SensorDeviceClass.WIND_SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        suggested_display_precision=1,
        section="weather",
        value_fn=_wind_kmh("wind_gust_m_s"),
    ),
    OKRSensorDescription(
        key="wind_max_daily_gust",
        translation_key="wind_max_daily_gust",
        device_class=SensorDeviceClass.WIND_SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        suggested_display_precision=1,
        section="weather",
        value_fn=_wind_kmh("wind_max_daily_gust_m_s"),
    ),
    OKRSensorDescription(
        key="wind_bearing",
        translation_key="wind_bearing",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=DEGREE,
        suggested_display_precision=0,
        section="weather",
        value_fn=_passthrough("wind_direction_deg"),
    ),
    OKRSensorDescription(
        key="precipitation_rate",
        translation_key="precipitation_rate",
        device_class=SensorDeviceClass.PRECIPITATION_INTENSITY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfVolumetricFlux.MILLIMETERS_PER_HOUR,
        suggested_display_precision=2,
        section="weather",
        value_fn=_passthrough("precipitation_mm_h"),
    ),
    OKRSensorDescription(
        key="precipitation_today",
        translation_key="precipitation_today",
        device_class=SensorDeviceClass.PRECIPITATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfPrecipitationDepth.MILLIMETERS,
        suggested_display_precision=1,
        section="weather",
        value_fn=_passthrough("precipitation_mm_daily"),
    ),
    OKRSensorDescription(
        key="uv_index",
        translation_key="uv_index",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        section="weather",
        value_fn=_passthrough("uv_index"),
    ),
    OKRSensorDescription(
        key="solar_radiation",
        translation_key="solar_radiation",
        device_class=SensorDeviceClass.IRRADIANCE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfIrradiance.WATTS_PER_SQUARE_METER,
        suggested_display_precision=0,
        section="weather",
        value_fn=_passthrough("solar_radiation_w_m2"),
    ),
    OKRSensorDescription(
        key="ground_temperature",
        translation_key="ground_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
        entity_registry_enabled_default=False,
        section="weather",
        value_fn=_passthrough("ground_temperature_c"),
    ),
    OKRSensorDescription(
        key="soil_moisture",
        translation_key="soil_moisture",
        device_class=SensorDeviceClass.MOISTURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=0,
        entity_registry_enabled_default=False,
        section="weather",
        value_fn=_passthrough("soil_moisture_pct"),
    ),
    OKRSensorDescription(
        key="snow_depth",
        translation_key="snow_depth",
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfLength.CENTIMETERS,
        suggested_display_precision=1,
        entity_registry_enabled_default=False,
        section="weather",
        value_fn=_passthrough("snow_depth_cm"),
    ),
    OKRSensorDescription(
        key="vapor_pressure_deficit",
        translation_key="vapor_pressure_deficit",
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPressure.KPA,
        suggested_display_precision=2,
        entity_registry_enabled_default=False,
        section="weather",
        value_fn=_passthrough("vapor_pressure_deficit_kpa"),
    ),
)

LIVE_AIR_SENSORS: tuple[OKRSensorDescription, ...] = (
    OKRSensorDescription(
        key="pm2_5",
        translation_key="pm2_5",
        device_class=SensorDeviceClass.PM25,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="µg/m³",
        suggested_display_precision=1,
        section="air",
        value_fn=_passthrough("pm2_5_ug_m3"),
    ),
    OKRSensorDescription(
        key="pm10",
        translation_key="pm10",
        device_class=SensorDeviceClass.PM10,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="µg/m³",
        suggested_display_precision=1,
        section="air",
        value_fn=_passthrough("pm10_ug_m3"),
    ),
    OKRSensorDescription(
        key="carbon_monoxide",
        translation_key="carbon_monoxide",
        device_class=SensorDeviceClass.CO,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="ppm",
        suggested_display_precision=3,
        entity_registry_enabled_default=False,
        section="air",
        value_fn=_passthrough("carbon_monoxide_ppm"),
    ),
    OKRSensorDescription(
        key="nitrogen_dioxide",
        translation_key="nitrogen_dioxide",
        device_class=SensorDeviceClass.NITROGEN_DIOXIDE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="ppm",
        suggested_display_precision=3,
        entity_registry_enabled_default=False,
        section="air",
        value_fn=_passthrough("nitrogen_dioxide_ppm"),
    ),
    OKRSensorDescription(
        key="ammonia",
        translation_key="ammonia",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="ppm",
        suggested_display_precision=3,
        entity_registry_enabled_default=False,
        section="air",
        value_fn=_passthrough("ammonia_ppm"),
    ),
)

LIVE_ALERT_SENSORS: tuple[OKRSensorDescription, ...] = (
    OKRSensorDescription(
        key="active_alerts_count",
        translation_key="active_alerts_count",
        state_class=SensorStateClass.MEASUREMENT,
        section="alerts",
        value_fn=lambda rows: len(rows) if isinstance(rows, list) else 0,
    ),
)


# ── Premium sensors ─────────────────────────────────────────────────────────


PREMIUM_SENSORS: tuple[OKRSensorDescription, ...] = (
    # Comfort index
    OKRSensorDescription(
        key="comfort_score",
        translation_key="comfort_score",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=0,
        section="comfort_index",
        value_fn=_passthrough("comfort_score"),
    ),
    OKRSensorDescription(
        key="comfort_label",
        translation_key="comfort_label",
        section="comfort_index",
        value_fn=_passthrough("comfort_label"),
    ),
    # Frost alert
    OKRSensorDescription(
        key="frost_probability",
        translation_key="frost_probability",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=0,
        section="frost_alert",
        value_fn=_passthrough("frost_probability"),
    ),
    OKRSensorDescription(
        key="frost_level",
        translation_key="frost_level",
        section="frost_alert",
        value_fn=_passthrough("frost_level"),
    ),
    OKRSensorDescription(
        key="frost_window",
        translation_key="frost_window",
        section="frost_alert",
        value_fn=lambda row: (
            f"{row.get('frost_window_start') or '—'} → "
            f"{row.get('frost_window_end') or '—'}"
            if row else None
        ),
    ),
    # Solar forecast
    OKRSensorDescription(
        key="solar_total_kwh",
        translation_key="solar_total_kwh",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=1,
        section="solar_forecast",
        value_fn=_passthrough("total_kwh"),
    ),
    OKRSensorDescription(
        key="solar_peak_kw",
        translation_key="solar_peak_kw",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        suggested_display_precision=2,
        section="solar_forecast",
        value_fn=_passthrough("peak_kw"),
    ),
    OKRSensorDescription(
        key="solar_efficiency",
        translation_key="solar_efficiency",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=0,
        section="solar_forecast",
        value_fn=_passthrough("efficiency_percent"),
    ),
    OKRSensorDescription(
        key="solar_production_label",
        translation_key="solar_production_label",
        section="solar_forecast",
        value_fn=_passthrough("production_label"),
    ),
    # Sport — running
    OKRSensorDescription(
        key="running_score",
        translation_key="running_score",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=0,
        section="sport_conditions",
        value_fn=_passthrough("running_score"),
    ),
    OKRSensorDescription(
        key="running_label",
        translation_key="running_label",
        section="sport_conditions",
        value_fn=_passthrough("running_label"),
    ),
    # Sport — cycling
    OKRSensorDescription(
        key="cycling_score",
        translation_key="cycling_score",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=0,
        section="sport_conditions",
        value_fn=_passthrough("cycling_score"),
    ),
    OKRSensorDescription(
        key="cycling_label",
        translation_key="cycling_label",
        section="sport_conditions",
        value_fn=_passthrough("cycling_label"),
    ),
    # Drying conditions
    OKRSensorDescription(
        key="drying_score",
        translation_key="drying_score",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=0,
        section="drying_conditions",
        value_fn=_passthrough("drying_score"),
    ),
    OKRSensorDescription(
        key="drying_label",
        translation_key="drying_label",
        section="drying_conditions",
        value_fn=_passthrough("drying_label"),
    ),
    OKRSensorDescription(
        key="drying_estimated_hours",
        translation_key="drying_estimated_hours",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTime.HOURS,
        suggested_display_precision=1,
        section="drying_conditions",
        value_fn=_passthrough("est_drying_hours"),
    ),
    # Outfit
    OKRSensorDescription(
        key="outfit_recommendation",
        translation_key="outfit_recommendation",
        section="outfit_recommendations",
        value_fn=_passthrough("outfit_label"),
    ),
    # Pressure alert
    OKRSensorDescription(
        key="pressure_alert_label",
        translation_key="pressure_alert_label",
        section="pressure_alert",
        value_fn=_passthrough("alert_label"),
    ),
    # Storm tracker
    OKRSensorDescription(
        key="storm_status",
        translation_key="storm_status",
        section="storm_tracker",
        value_fn=_passthrough("status"),
    ),
    # Air quality trend
    OKRSensorDescription(
        key="air_quality_trend",
        translation_key="air_quality_trend",
        section="air_quality_trend",
        value_fn=_passthrough("trend_label"),
    ),
)


# ── Setup ────────────────────────────────────────────────────────────────────


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OKRWeatherConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add live + premium sensors for this entry."""
    runtime = entry.runtime_data
    station = runtime.station

    entities: list[SensorEntity] = []

    # Live weather + alerts always.
    for desc in LIVE_WEATHER_SENSORS + LIVE_ALERT_SENSORS:
        entities.append(
            OKRWeatherLiveSensor(
                coordinator=runtime.live_coordinator,
                description=desc,
                station=station,
            )
        )

    # Air sensors only when the station has reported air data at least once.
    live_data = runtime.live_coordinator.data or {}
    if live_data.get("air"):
        for desc in LIVE_AIR_SENSORS:
            entities.append(
                OKRWeatherLiveSensor(
                    coordinator=runtime.live_coordinator,
                    description=desc,
                    station=station,
                )
            )

    # Premium sensors only when an API key is present.
    if runtime.premium_enabled:
        for desc in PREMIUM_SENSORS:
            entities.append(
                OKRWeatherPremiumSensor(
                    coordinator=runtime.forecast_coordinator,
                    description=desc,
                    station=station,
                )
            )

    async_add_entities(entities)


# ── Entity classes ──────────────────────────────────────────────────────────


class OKRWeatherLiveSensor(OKRWeatherEntity, SensorEntity):
    """Sensor backed by the live coordinator (weather / air / alerts)."""

    entity_description: OKRSensorDescription

    def __init__(
        self,
        coordinator: OKRWeatherLiveCoordinator,
        description: OKRSensorDescription,
        station: StationInfo,
    ) -> None:
        super().__init__(coordinator, station)
        self.entity_description = description
        self._attr_unique_id = f"{station.appwrite_id}_{description.key}"

    @property
    def native_value(self) -> Any:
        if not self.coordinator.data:
            return None
        section = self.coordinator.data.get(self.entity_description.section)
        if section is None:
            return None
        return self.entity_description.value_fn(section)


class OKRWeatherPremiumSensor(OKRWeatherEntity, SensorEntity):
    """Sensor backed by the forecast coordinator (premium tables)."""

    entity_description: OKRSensorDescription

    def __init__(
        self,
        coordinator: OKRWeatherForecastCoordinator,
        description: OKRSensorDescription,
        station: StationInfo,
    ) -> None:
        super().__init__(coordinator, station)
        self.entity_description = description
        self._attr_unique_id = f"{station.appwrite_id}_{description.key}"

    @property
    def available(self) -> bool:
        """Premium entities go unavailable when the source table is blocked."""
        if not super().available:
            return False
        runtime = self.coordinator.config_entry.runtime_data
        return self.entity_description.section not in runtime.premium_tables_blocked

    @property
    def native_value(self) -> Any:
        if not self.coordinator.data:
            return None
        row = self.coordinator.data.get(self.entity_description.section)
        if row is None:
            return None
        return self.entity_description.value_fn(row)
