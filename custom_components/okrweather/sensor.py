"""Sensor platform for OKRWeather.

Two families of sensors, both per station:

* **Live** — every reading of the physical station plus a data-age
  timestamp, and measured air quality (PM2.5/PM10 from Airly sensors, with a
  computed US-EPA AQI) for stations that have an air-quality source.
* **Insight** — the active premium AI features: comfort index, radar
  analysis, storm tracker, pressure alerts, frost alerts and solar forecast.
  Created only when the hub has an API key. Categorical
  results are proper ``ENUM`` sensors so they translate and can be used in
  automations without string guessing.
"""

from __future__ import annotations

import json
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
    CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
    DEGREE,
    PERCENTAGE,
    EntityCategory,
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

from .const import (
    COMFORT_LABELS,
    FROST_LEVELS,
    MS_TO_KMH,
    PRESSURE_ALERT_LEVELS,
    PRESSURE_TRENDS,
    RADAR_INTENSITIES,
    RADAR_TRENDS,
    SECTION_COMFORT,
    SECTION_FROST,
    SECTION_PRESSURE,
    SECTION_RADAR,
    SECTION_SOLAR,
    SECTION_STORM,
    SOLAR_LABELS,
    STORM_INTENSITY_LEVELS,
    STORM_PROXIMITY_LEVELS,
)
from homeassistant.core import callback

from .entity import OKRWeatherEntity
from .util import compute_epa_aqi, normalize_enum, reading_time

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from .coordinator import OKRWeatherCoordinator
    from .data import OKRWeatherConfigEntry, StationConfig

PARALLEL_UPDATES = 0

# loc("advisory") returns the advisory in the user's configured language.
type Localizer = Callable[[str], Any]


@dataclass(frozen=True, kw_only=True)
class OKRSensorDescription(SensorEntityDescription):
    """Sensor description with a value extractor and optional attributes."""

    section: str
    value_fn: Callable[[dict[str, Any]], Any]
    attributes_fn: Callable[[dict[str, Any], Localizer], dict[str, Any]] | None = None


# ── Value helpers ────────────────────────────────────────────────────────────


def _get(key: str) -> Callable[[dict[str, Any]], Any]:
    return lambda row: row.get(key)


def _kmh(key: str) -> Callable[[dict[str, Any]], Any]:
    def _value(row: dict[str, Any]) -> float | None:
        value = row.get(key)
        if not isinstance(value, (int, float)):
            return None
        return round(float(value) * MS_TO_KMH, 1)

    return _value


def _enum(key: str) -> Callable[[dict[str, Any]], Any]:
    return lambda row: normalize_enum(row.get(key))


def _percent_probability(key: str) -> Callable[[dict[str, Any]], Any]:
    """Probabilities that may be stored as 0-1 fractions or 0-100 percents."""

    def _value(row: dict[str, Any]) -> float | None:
        value = row.get(key)
        if not isinstance(value, (int, float)):
            return None
        return round(float(value) * 100, 1) if value <= 1 else round(float(value), 1)

    return _value


def _row_timestamp(row: dict[str, Any]) -> Any:
    return reading_time(row)


def _air_attributes(row: dict[str, Any], loc: Localizer) -> dict[str, Any]:
    """Context of a measured air-quality value (air-quality-readings row)."""
    return {
        "air_quality_level": row.get("gios_level"),
        "air_quality_level_name": row.get("gios_level_name"),
        "caqi": row.get("index_value"),
        "caqi_level": row.get("index_level"),
        "quality_check": row.get("qc_status"),
        "sensors": row.get("members_used"),
        "measured_until": row.get("till_at"),
        "credit": "Dane: Airly",
    }


def _solar_hourly(row: dict[str, Any]) -> Any:
    raw = row.get("hourly_forecast")
    if not isinstance(raw, str) or not raw:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return None


# ── Live sensors ─────────────────────────────────────────────────────────────

LIVE_WEATHER_SENSORS: tuple[OKRSensorDescription, ...] = (
    OKRSensorDescription(
        key="temperature",
        translation_key="temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
        section="weather",
        value_fn=_get("air_temperature_c"),
    ),
    OKRSensorDescription(
        key="apparent_temperature",
        translation_key="apparent_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
        section="weather",
        value_fn=_get("sensed_temperature_c"),
    ),
    OKRSensorDescription(
        key="dew_point",
        translation_key="dew_point",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
        section="weather",
        value_fn=_get("dew_point_c"),
    ),
    OKRSensorDescription(
        key="humidity",
        translation_key="humidity",
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=0,
        section="weather",
        value_fn=_get("air_humidity_pct"),
    ),
    OKRSensorDescription(
        # Sea-level reduced — comparable with forecasts and other weather
        # services. The raw reading lives on the station_pressure sensor.
        key="pressure",
        translation_key="pressure",
        device_class=SensorDeviceClass.ATMOSPHERIC_PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPressure.HPA,
        suggested_display_precision=1,
        section="weather",
        value_fn=lambda row: row.get("sea_level_pressure_hpa")
        if row.get("sea_level_pressure_hpa") is not None
        else row.get("air_pressure_hpa"),
    ),
    OKRSensorDescription(
        key="station_pressure",
        translation_key="station_pressure",
        device_class=SensorDeviceClass.ATMOSPHERIC_PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPressure.HPA,
        suggested_display_precision=1,
        entity_registry_enabled_default=False,
        section="weather",
        value_fn=_get("air_pressure_hpa"),
    ),
    OKRSensorDescription(
        key="wind_speed",
        translation_key="wind_speed",
        device_class=SensorDeviceClass.WIND_SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        suggested_display_precision=1,
        section="weather",
        value_fn=_kmh("wind_speed_m_s"),
    ),
    OKRSensorDescription(
        key="wind_gust",
        translation_key="wind_gust",
        device_class=SensorDeviceClass.WIND_SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        suggested_display_precision=1,
        section="weather",
        value_fn=_kmh("wind_gust_m_s"),
    ),
    OKRSensorDescription(
        key="wind_max_daily_gust",
        translation_key="wind_max_daily_gust",
        device_class=SensorDeviceClass.WIND_SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        suggested_display_precision=1,
        section="weather",
        value_fn=_kmh("wind_max_daily_gust_m_s"),
    ),
    OKRSensorDescription(
        key="wind_bearing",
        translation_key="wind_bearing",
        device_class=SensorDeviceClass.WIND_DIRECTION,
        state_class=SensorStateClass.MEASUREMENT_ANGLE,
        native_unit_of_measurement=DEGREE,
        suggested_display_precision=0,
        section="weather",
        value_fn=_get("wind_direction_deg"),
    ),
    OKRSensorDescription(
        key="precipitation_rate",
        translation_key="precipitation_rate",
        device_class=SensorDeviceClass.PRECIPITATION_INTENSITY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfVolumetricFlux.MILLIMETERS_PER_HOUR,
        suggested_display_precision=2,
        section="weather",
        value_fn=_get("precipitation_mm_h"),
    ),
    OKRSensorDescription(
        key="precipitation_today",
        translation_key="precipitation_today",
        device_class=SensorDeviceClass.PRECIPITATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfPrecipitationDepth.MILLIMETERS,
        suggested_display_precision=1,
        section="weather",
        value_fn=_get("precipitation_mm_daily"),
    ),
    OKRSensorDescription(
        key="uv_index",
        translation_key="uv_index",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        section="weather",
        value_fn=_get("uv_index"),
    ),
    OKRSensorDescription(
        key="solar_radiation",
        translation_key="solar_radiation",
        device_class=SensorDeviceClass.IRRADIANCE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfIrradiance.WATTS_PER_SQUARE_METER,
        suggested_display_precision=0,
        section="weather",
        value_fn=_get("solar_radiation_w_m2"),
    ),
    OKRSensorDescription(
        key="light_level",
        translation_key="light_level",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=0,
        entity_registry_enabled_default=False,
        section="weather",
        value_fn=_get("light_level_pct"),
    ),
    OKRSensorDescription(
        key="uv_irradiance",
        translation_key="uv_irradiance",
        device_class=SensorDeviceClass.IRRADIANCE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfIrradiance.WATTS_PER_SQUARE_METER,
        suggested_display_precision=1,
        entity_registry_enabled_default=False,
        section="weather",
        value_fn=_get("uv_irradiance_w_m2"),
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
        value_fn=_get("ground_temperature_c"),
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
        value_fn=_get("soil_moisture_pct"),
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
        value_fn=_get("snow_depth_cm"),
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
        value_fn=_get("vapor_pressure_deficit_kpa"),
    ),
    OKRSensorDescription(
        key="radiation",
        translation_key="radiation",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="µSv/h",
        suggested_display_precision=3,
        entity_registry_enabled_default=False,
        section="weather",
        value_fn=_get("radiation_usv_h"),
    ),
    OKRSensorDescription(
        key="last_update",
        translation_key="last_update",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        section="weather",
        value_fn=_row_timestamp,
    ),
)

LIVE_AIR_SENSORS: tuple[OKRSensorDescription, ...] = (
    OKRSensorDescription(
        key="pm2_5",
        translation_key="pm2_5",
        device_class=SensorDeviceClass.PM25,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
        suggested_display_precision=1,
        section="air",
        value_fn=_get("pm25"),
        attributes_fn=_air_attributes,
    ),
    OKRSensorDescription(
        key="pm10",
        translation_key="pm10",
        device_class=SensorDeviceClass.PM10,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
        suggested_display_precision=1,
        section="air",
        value_fn=_get("pm10"),
        attributes_fn=_air_attributes,
    ),
    OKRSensorDescription(
        key="aqi",
        translation_key="aqi",
        device_class=SensorDeviceClass.AQI,
        state_class=SensorStateClass.MEASUREMENT,
        section="air",
        value_fn=lambda row: compute_epa_aqi(row.get("pm25")),
        attributes_fn=_air_attributes,
    ),
)


# ── Insight (premium AI) sensors ─────────────────────────────────────────────

INSIGHT_SENSORS: tuple[OKRSensorDescription, ...] = (
    # Comfort index — cron */5
    OKRSensorDescription(
        key="comfort_score",
        translation_key="comfort_score",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=0,
        section=SECTION_COMFORT,
        value_fn=_get("comfort_score"),
        attributes_fn=lambda row, loc: {
            "label": loc("comfort_label"),
            "description": loc("description"),
            "temperature_score": row.get("temperature_score"),
            "humidity_score": row.get("humidity_score"),
            "wind_score": row.get("wind_score"),
            "uv_score": row.get("uv_score"),
            "aqi_score": row.get("aqi_score"),
            "analyzed_at": row.get("analyzed_at"),
        },
    ),
    OKRSensorDescription(
        key="comfort_label",
        translation_key="comfort_label",
        device_class=SensorDeviceClass.ENUM,
        options=COMFORT_LABELS,
        section=SECTION_COMFORT,
        value_fn=_enum("comfort_label"),
    ),
    # Frost alert — cron 0 */3
    OKRSensorDescription(
        key="frost_probability",
        translation_key="frost_probability",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=0,
        section=SECTION_FROST,
        value_fn=_get("frost_probability"),
        attributes_fn=lambda row, loc: {
            "advisory": loc("advisory"),
            "window_start": row.get("frost_window_start"),
            "window_end": row.get("frost_window_end"),
            "ice_risk": row.get("ice_risk"),
            "min_forecast_temp_c": row.get("min_forecast_temp_c"),
            "ground_temp_c": row.get("ground_temp_c"),
            "analyzed_at": row.get("analyzed_at"),
        },
    ),
    OKRSensorDescription(
        key="frost_level",
        translation_key="frost_level",
        device_class=SensorDeviceClass.ENUM,
        options=FROST_LEVELS,
        section=SECTION_FROST,
        value_fn=_enum("frost_level"),
    ),
    # Solar forecast — cron 0 */4
    OKRSensorDescription(
        key="solar_total_kwh",
        translation_key="solar_total_kwh",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=1,
        section=SECTION_SOLAR,
        value_fn=_get("total_kwh"),
        attributes_fn=lambda row, loc: {
            "summary": loc("summary"),
            "sunrise": row.get("sunrise"),
            "sunset": row.get("sunset"),
            "peak_hour": row.get("peak_hour"),
            "panel_capacity_kwp": row.get("panel_capacity_kwp"),
            "avg_cloud_cover": row.get("avg_cloud_cover"),
            "daylight_hours": row.get("daylight_hours"),
            "hourly_forecast": _solar_hourly(row),
            "analyzed_at": row.get("analyzed_at"),
        },
    ),
    OKRSensorDescription(
        key="solar_peak_kw",
        translation_key="solar_peak_kw",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        suggested_display_precision=2,
        section=SECTION_SOLAR,
        value_fn=_get("peak_kw"),
    ),
    OKRSensorDescription(
        key="solar_efficiency",
        translation_key="solar_efficiency",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=0,
        section=SECTION_SOLAR,
        value_fn=_get("efficiency_percent"),
    ),
    OKRSensorDescription(
        key="solar_production_label",
        translation_key="solar_production_label",
        device_class=SensorDeviceClass.ENUM,
        options=SOLAR_LABELS,
        section=SECTION_SOLAR,
        value_fn=_enum("production_label"),
    ),
    # Pressure alert — cron */10
    OKRSensorDescription(
        key="pressure_alert_level",
        translation_key="pressure_alert_level",
        device_class=SensorDeviceClass.ENUM,
        options=PRESSURE_ALERT_LEVELS,
        section=SECTION_PRESSURE,
        value_fn=_enum("alert_level"),
        attributes_fn=lambda row, loc: {
            "alert_text": loc("alert_text"),
            "risk_score": row.get("risk_score"),
            "delta_3h_hpa": row.get("delta_3h_hpa"),
            "delta_6h_hpa": row.get("delta_6h_hpa"),
            "variability": row.get("variability"),
            "readings_count": row.get("readings_count"),
            "analyzed_at": row.get("analyzed_at"),
        },
    ),
    OKRSensorDescription(
        key="pressure_trend",
        translation_key="pressure_trend",
        device_class=SensorDeviceClass.ENUM,
        options=PRESSURE_TRENDS,
        section=SECTION_PRESSURE,
        value_fn=_enum("trend"),
    ),
    OKRSensorDescription(
        key="pressure_change_rate",
        translation_key="pressure_change_rate",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="hPa/h",
        suggested_display_precision=2,
        entity_registry_enabled_default=False,
        section=SECTION_PRESSURE,
        value_fn=_get("rate_hpa_per_hour"),
    ),
    # Storm tracker — cron */5
    OKRSensorDescription(
        key="storm_proximity",
        translation_key="storm_proximity",
        device_class=SensorDeviceClass.ENUM,
        options=STORM_PROXIMITY_LEVELS,
        section=SECTION_STORM,
        value_fn=_enum("proximity_level"),
        attributes_fn=lambda row, loc: {
            "advisory": loc("advisory"),
            "storm_detected": row.get("storm_detected"),
            "lightning_trend": row.get("lightning_trend"),
            "radar_intensity": row.get("radar_intensity"),
            "radar_direction": row.get("radar_direction"),
            "radar_speed_kmh": row.get("radar_speed_kmh"),
            "clear_minutes": row.get("clear_minutes"),
            "pressure_rate_hpa_h": row.get("pressure_rate_hpa_h"),
            "wind_gust_kmh": row.get("wind_gust_kmh"),
            "analyzed_at": row.get("analyzed_at"),
        },
    ),
    OKRSensorDescription(
        key="storm_intensity",
        translation_key="storm_intensity",
        device_class=SensorDeviceClass.ENUM,
        options=STORM_INTENSITY_LEVELS,
        section=SECTION_STORM,
        value_fn=_enum("storm_intensity"),
    ),
    OKRSensorDescription(
        key="storm_eta",
        translation_key="storm_eta",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        section=SECTION_STORM,
        value_fn=_get("eta_minutes"),
    ),
    OKRSensorDescription(
        key="lightning_count_30min",
        translation_key="lightning_count_30min",
        state_class=SensorStateClass.MEASUREMENT,
        section=SECTION_STORM,
        value_fn=_get("lightning_count_30min"),
    ),
    OKRSensorDescription(
        key="storm_lightning_distance",
        translation_key="storm_lightning_distance",
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        suggested_display_precision=1,
        section=SECTION_STORM,
        value_fn=_get("lightning_distance_km"),
    ),
    # Radar analysis — refreshed roughly every 10 minutes
    OKRSensorDescription(
        key="radar_intensity",
        translation_key="radar_intensity",
        device_class=SensorDeviceClass.ENUM,
        options=RADAR_INTENSITIES,
        section=SECTION_RADAR,
        value_fn=_enum("intensity"),
        attributes_fn=lambda row, loc: {
            "city": row.get("city_name"),
            "is_raining": row.get("is_raining"),
            "is_approaching": row.get("is_approaching"),
            "coverage_percent": row.get("coverage_percent"),
            "avg_dbz": row.get("avg_dbz"),
            "max_dbz": row.get("max_dbz"),
            "movement_direction": row.get("movement_direction"),
            "movement_speed_kmh": row.get("movement_speed_kmh"),
            "closest_rain_direction": row.get("closest_rain_direction"),
            "cells_tracked": row.get("cells_tracked"),
            "frames_used": row.get("frames_used"),
            "analyzed_at": row.get("analyzed_at"),
        },
    ),
    OKRSensorDescription(
        key="radar_trend",
        translation_key="radar_trend",
        device_class=SensorDeviceClass.ENUM,
        options=RADAR_TRENDS,
        section=SECTION_RADAR,
        value_fn=_enum("trend"),
    ),
    OKRSensorDescription(
        key="radar_rain_rate",
        translation_key="radar_rain_rate",
        device_class=SensorDeviceClass.PRECIPITATION_INTENSITY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfVolumetricFlux.MILLIMETERS_PER_HOUR,
        suggested_display_precision=1,
        section=SECTION_RADAR,
        value_fn=_get("rain_rate_mmh"),
    ),
    OKRSensorDescription(
        key="radar_rain_eta",
        translation_key="radar_rain_eta",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        section=SECTION_RADAR,
        value_fn=_get("eta_minutes"),
        attributes_fn=lambda row, loc: {
            "eta_minutes_p25": row.get("eta_minutes_p25"),
            "eta_minutes_p75": row.get("eta_minutes_p75"),
        },
    ),
    OKRSensorDescription(
        key="radar_closest_rain",
        translation_key="radar_closest_rain",
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        suggested_display_precision=1,
        section=SECTION_RADAR,
        value_fn=_get("closest_rain_km"),
    ),
    OKRSensorDescription(
        key="rain_probability_30min",
        translation_key="rain_probability_30min",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=0,
        section=SECTION_RADAR,
        value_fn=_percent_probability("p_rain_30min"),
    ),
    OKRSensorDescription(
        key="rain_probability_60min",
        translation_key="rain_probability_60min",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=0,
        section=SECTION_RADAR,
        value_fn=_percent_probability("p_rain_60min"),
    ),
)


# ── Setup ────────────────────────────────────────────────────────────────────


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OKRWeatherConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add live + insight sensors for every station subentry."""
    runtime = entry.runtime_data

    for subentry_id, station in runtime.stations.items():
        entities: list[SensorEntity] = [
            OKRWeatherSensor(runtime.live_coordinator, station, desc)
            for desc in LIVE_WEATHER_SENSORS
        ]
        entities.append(OKRAlertCountSensor(runtime.live_coordinator, station))

        if runtime.premium_enabled:
            entities.extend(
                OKRWeatherSensor(runtime.insights_coordinator, station, desc)
                for desc in INSIGHT_SENSORS
            )

        async_add_entities(entities, config_subentry_id=subentry_id)

    # Air sensors only for stations that actually report air quality — added
    # as soon as the first air row shows up, not just at setup time.
    air_added: set[str] = set()

    @callback
    def _async_add_air_sensors() -> None:
        data = runtime.live_coordinator.data or {}
        for subentry_id, station in runtime.stations.items():
            if subentry_id in air_added:
                continue
            if (data.get("stations", {}).get(subentry_id) or {}).get("air"):
                air_added.add(subentry_id)
                async_add_entities(
                    [
                        OKRWeatherSensor(runtime.live_coordinator, station, desc)
                        for desc in LIVE_AIR_SENSORS
                    ],
                    config_subentry_id=subentry_id,
                )

    _async_add_air_sensors()
    entry.async_on_unload(
        runtime.live_coordinator.async_add_listener(_async_add_air_sensors)
    )


# ── Entities ─────────────────────────────────────────────────────────────────


class OKRWeatherSensor(OKRWeatherEntity, SensorEntity):
    """Sensor reading one value out of a station's section row."""

    entity_description: OKRSensorDescription

    def __init__(
        self,
        coordinator: OKRWeatherCoordinator,
        station: StationConfig,
        description: OKRSensorDescription,
    ) -> None:
        super().__init__(coordinator, station, description)

    @property
    def _row(self) -> dict[str, Any] | None:
        row = self.section_row(self.entity_description.section)
        return row if isinstance(row, dict) else None

    @property
    def native_value(self) -> Any:
        if (row := self._row) is None:
            return None
        return self.entity_description.value_fn(row)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        attributes_fn = self.entity_description.attributes_fn
        if attributes_fn is None or (row := self._row) is None:
            return None
        attrs = attributes_fn(row, lambda base: self.localized(row, base))
        return {k: v for k, v in attrs.items() if v is not None} or None


class OKRAlertCountSensor(OKRWeatherEntity, SensorEntity):
    """Number of active government weather alerts for the station's area."""

    _attr_translation_key = "active_alerts_count"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: OKRWeatherCoordinator,
        station: StationConfig,
    ) -> None:
        super().__init__(coordinator, station)
        self._attr_unique_id = f"{station.appwrite_id}_active_alerts_count"

    def _alerts(self) -> list[dict[str, Any]]:
        # Pre-filtered per station by the live coordinator.
        return self.section_row("alerts") or []

    @property
    def native_value(self) -> int:
        return len(self._alerts())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "alerts": [
                {
                    "title": a.get("alertTitle"),
                    "severity": a.get("severity"),
                    "event_type": a.get("eventType"),
                    "area": a.get("areaName"),
                    "starts_at": a.get("startTime"),
                    "expires_at": a.get("expirationTime"),
                }
                for a in self._alerts()
            ]
        }
