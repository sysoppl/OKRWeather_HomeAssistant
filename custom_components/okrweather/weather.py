"""Weather entities for OKRWeather — one per configured station.

Each entity bridges three sources:

* Current temperature/humidity/pressure/wind come from the **live**
  coordinator (the physical station).
* The current condition comes from the station's live precipitation signal
  when it is actively raining, otherwise from the hourly forecast row that
  brackets *now* — the stations don't report a categorical condition.
* Hourly, daily and twice-daily forecasts come from the **forecast**
  coordinator, using the city each station is mapped to.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.components.weather import (
    Forecast,
    WeatherEntity,
    WeatherEntityFeature,
)
from homeassistant.const import (
    UnitOfLength,
    UnitOfPrecipitationDepth,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
)
from homeassistant.core import callback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, MS_TO_KMH
from .entity import station_device_info
from .util import parse_iso

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from .coordinator import (
        OKRWeatherForecastCoordinator,
        OKRWeatherLiveCoordinator,
    )
    from .data import OKRWeatherConfigEntry, StationConfig

PARALLEL_UPDATES = 0


# ── Condition mapping ───────────────────────────────────────────────────────


def map_condition(raw: str | None, *, is_daytime: bool = True) -> str | None:
    """Translate the API's free-form condition string to an HA condition.

    Mirrors the OKRWeather portal's ``mapConditionType`` but emits HA's
    official condition vocabulary.
    """
    if not raw:
        return None
    s = raw.lower()

    if "thunder" in s and ("rain" in s or "shower" in s):
        return "lightning-rainy"
    if "thunder" in s or "storm" in s:
        return "lightning"
    if "hail" in s:
        return "hail"
    if "sleet" in s or ("snow" in s and "rain" in s):
        return "snowy-rainy"
    if "snow" in s or "blizzard" in s or "flurr" in s or "ice" in s:
        return "snowy"
    if "heavy rain" in s or "pour" in s:
        return "pouring"
    if "rain" in s or "drizzle" in s or "shower" in s:
        return "rainy"
    if "fog" in s or "mist" in s or "haze" in s or "smoke" in s:
        return "fog"
    if "sunny" in s or "clear" in s:
        return "sunny" if is_daytime else "clear-night"
    if "fair" in s or "partly" in s:
        return "partlycloudy"
    if "mostly cloudy" in s or "overcast" in s or "cloudy" in s:
        return "cloudy"
    if "wind" in s:
        return "windy"
    return None


def _kmh(value: Any) -> float | None:
    """m/s → km/h rounded to one decimal, or None.

    Only for LIVE station readings (weather-data stores m/s). The forecast
    tables already store km/h — never run their values through this.
    """
    if not isinstance(value, (int, float)):
        return None
    return round(float(value) * MS_TO_KMH, 1)


# ── Setup ───────────────────────────────────────────────────────────────────


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OKRWeatherConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add one weather entity per station subentry."""
    runtime = entry.runtime_data
    for subentry_id, station in runtime.stations.items():
        async_add_entities(
            [
                OKRStationWeather(
                    live=runtime.live_coordinator,
                    forecast=runtime.forecast_coordinator,
                    station=station,
                )
            ],
            config_subentry_id=subentry_id,
        )


# ── Entity ──────────────────────────────────────────────────────────────────


class OKRStationWeather(CoordinatorEntity["OKRWeatherLiveCoordinator"], WeatherEntity):
    """Weather entity for a single station."""

    _attr_attribution = ATTRIBUTION
    _attr_has_entity_name = True
    _attr_name = None  # take the device (station) name
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_native_pressure_unit = UnitOfPressure.HPA
    _attr_native_wind_speed_unit = UnitOfSpeed.KILOMETERS_PER_HOUR
    _attr_native_precipitation_unit = UnitOfPrecipitationDepth.MILLIMETERS
    _attr_native_visibility_unit = UnitOfLength.KILOMETERS
    _attr_supported_features = (
        WeatherEntityFeature.FORECAST_HOURLY
        | WeatherEntityFeature.FORECAST_DAILY
        | WeatherEntityFeature.FORECAST_TWICE_DAILY
    )

    def __init__(
        self,
        live: OKRWeatherLiveCoordinator,
        forecast: OKRWeatherForecastCoordinator,
        station: StationConfig,
    ) -> None:
        # The live coordinator drives the state refresh cadence.
        super().__init__(live)
        self._forecast_coordinator = forecast
        self._station = station
        self._attr_unique_id = f"{station.appwrite_id}_weather"
        self._attr_device_info = station_device_info(station)

    async def async_added_to_hass(self) -> None:
        """Subscribe to both coordinators so the entity refreshes on either."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self._forecast_coordinator.async_add_listener(
                self._handle_forecast_update
            )
        )

    @callback
    def _handle_forecast_update(self) -> None:
        """Write state AND push fresh forecasts to subscribed dashboards.

        async_write_ha_state alone only updates current conditions —
        weather/subscribe_forecast listeners are pushed exclusively through
        async_update_listeners.
        """
        self.async_write_ha_state()
        assert self._forecast_coordinator.config_entry is not None
        self._forecast_coordinator.config_entry.async_create_task(
            self.hass, self.async_update_listeners(None)
        )

    # ── Source rows ─────────────────────────────────────────────────────────

    @property
    def _live_row(self) -> dict[str, Any] | None:
        data = self.coordinator.data or {}
        station_data = data.get("stations", {}).get(self._station.subentry_id) or {}
        return station_data.get("weather")

    def _city_forecasts(self, kind: str) -> list[dict[str, Any]]:
        city_id = self._station.forecast_city_id
        if not city_id:
            return []
        data = self._forecast_coordinator.data or {}
        return data.get("cities", {}).get(city_id, {}).get(kind) or []

    @property
    def _current_hourly(self) -> dict[str, Any] | None:
        """The hourly forecast row that brackets *now*, else the next one."""
        rows = self._city_forecasts("hourly")
        if not rows:
            return None
        now = datetime.now(UTC)
        chosen: dict[str, Any] | None = None
        for row in rows:
            t = parse_iso(row.get("forecastTime"))
            if t is None:
                continue
            if t <= now:
                chosen = row
            else:
                break
        return chosen or rows[0]

    def _live(self, key: str) -> float | None:
        row = self._live_row
        if row and isinstance(row.get(key), (int, float)):
            return float(row[key])
        return None

    # ── Current state ───────────────────────────────────────────────────────

    @property
    def condition(self) -> str | None:
        """Condition, preferring what the station is actually measuring."""
        rain_rate = self._live("precipitation_mm_h")
        if rain_rate is not None and rain_rate > 0.2:
            temp = self._live("air_temperature_c")
            if temp is not None and temp <= 0.5:
                return "snowy"
            return "pouring" if rain_rate >= 4 else "rainy"

        row = self._current_hourly
        if not row:
            return None
        return map_condition(
            row.get("weatherConditionType"),
            is_daytime=bool(row.get("isDaytime", True)),
        )

    @property
    def native_temperature(self) -> float | None:
        if (value := self._live("air_temperature_c")) is not None:
            return value
        cur = self._current_hourly
        if cur and isinstance(cur.get("temperature"), (int, float)):
            return float(cur["temperature"])
        return None

    @property
    def native_apparent_temperature(self) -> float | None:
        if (value := self._live("sensed_temperature_c")) is not None:
            return value
        cur = self._current_hourly
        if cur and isinstance(cur.get("feelsLikeTemperature"), (int, float)):
            return float(cur["feelsLikeTemperature"])
        return None

    @property
    def native_dew_point(self) -> float | None:
        return self._live("dew_point_c")

    @property
    def humidity(self) -> float | None:
        return self._live("air_humidity_pct")

    @property
    def native_pressure(self) -> float | None:
        # Sea-level reduced (derived by the live coordinator) — matches what
        # forecasts and other weather services report.
        if (value := self._live("sea_level_pressure_hpa")) is not None:
            return value
        return self._live("air_pressure_hpa")

    @property
    def native_wind_speed(self) -> float | None:
        return _kmh(self._live("wind_speed_m_s"))

    @property
    def native_wind_gust_speed(self) -> float | None:
        return _kmh(self._live("wind_gust_m_s"))

    @property
    def wind_bearing(self) -> float | None:
        return self._live("wind_direction_deg")

    @property
    def uv_index(self) -> float | None:
        if (value := self._live("uv_index")) is not None:
            return value
        cur = self._current_hourly
        if cur and isinstance(cur.get("uvIndex"), (int, float)):
            return float(cur["uvIndex"])
        return None

    @property
    def cloud_coverage(self) -> float | None:
        cur = self._current_hourly
        if cur and isinstance(cur.get("cloudCover"), (int, float)):
            return float(cur["cloudCover"])
        return None

    @property
    def native_visibility(self) -> float | None:
        cur = self._current_hourly
        if cur and isinstance(cur.get("visibility"), (int, float)):
            return float(cur["visibility"])
        return None

    # ── Forecast methods ────────────────────────────────────────────────────

    async def async_forecast_hourly(self) -> list[Forecast] | None:
        out: list[Forecast] = []
        for row in self._city_forecasts("hourly"):
            dt = parse_iso(row.get("forecastTime"))
            if dt is None:
                continue
            out.append(
                Forecast(
                    datetime=dt.isoformat(),
                    condition=map_condition(
                        row.get("weatherConditionType"),
                        is_daytime=bool(row.get("isDaytime", True)),
                    ),
                    native_temperature=row.get("temperature"),
                    native_apparent_temperature=row.get("feelsLikeTemperature"),
                    native_dew_point=row.get("dewPoint"),
                    humidity=row.get("relativeHumidity"),
                    native_pressure=row.get("airPressureMsl"),
                    # Forecast tables store wind in km/h already.
                    native_wind_speed=row.get("windSpeed"),
                    native_wind_gust_speed=row.get("windGust"),
                    wind_bearing=row.get("windDirection"),
                    cloud_coverage=row.get("cloudCover"),
                    uv_index=row.get("uvIndex"),
                    precipitation_probability=row.get("precipProbability"),
                    native_precipitation=row.get("precipQpf"),
                )
            )
        return out or None

    async def async_forecast_daily(self) -> list[Forecast] | None:
        out: list[Forecast] = []
        for row in self._city_forecasts("daily"):
            dt = parse_iso(row.get("forecastStartTime")) or parse_iso(
                f"{row.get('forecastDate')}T00:00:00+00:00"
            )
            if dt is None:
                continue
            # `is not None` on purpose — an explicit 0 mm / 0 % dry day must
            # come through as 0, not unknown.
            qpf_values = [
                v
                for v in (row.get("dayPrecipQpf"), row.get("nightPrecipQpf"))
                if v is not None
            ]
            precip = float(sum(qpf_values)) if qpf_values else None
            prob_values = [
                v
                for v in (row.get("dayPrecipProb"), row.get("nightPrecipProb"))
                if v is not None
            ]
            precip_prob = max(prob_values) if prob_values else None
            out.append(
                Forecast(
                    datetime=dt.isoformat(),
                    condition=map_condition(row.get("dayWeatherType")),
                    native_temperature=row.get("maxTemperature"),
                    native_templow=row.get("minTemperature"),
                    native_apparent_temperature=row.get("feelsLikeMaxTemp"),
                    humidity=row.get("dayHumidity"),
                    cloud_coverage=row.get("dayCloudCover"),
                    uv_index=row.get("dayUvIndex"),
                    wind_bearing=row.get("dayWindDirection"),
                    native_wind_speed=row.get("dayWindSpeed"),
                    native_wind_gust_speed=row.get("dayWindGust"),
                    precipitation_probability=precip_prob,
                    native_precipitation=precip,
                )
            )
        return out or None

    async def async_forecast_twice_daily(self) -> list[Forecast] | None:
        out: list[Forecast] = []
        for row in self._city_forecasts("daily"):
            dt = parse_iso(row.get("forecastStartTime")) or parse_iso(
                f"{row.get('forecastDate')}T00:00:00+00:00"
            )
            if dt is None:
                continue
            # Anchor the night half at sunset so the two halves don't share
            # one timestamp; fall back to +12 h when sunset is missing.
            night_dt = parse_iso(row.get("sunsetTime")) or dt + timedelta(hours=12)
            for prefix, is_day in (("day", True), ("night", False)):
                out.append(
                    Forecast(
                        datetime=(dt if is_day else night_dt).isoformat(),
                        is_daytime=is_day,
                        condition=map_condition(
                            row.get(f"{prefix}WeatherType"), is_daytime=is_day
                        ),
                        native_temperature=(
                            row.get("maxTemperature")
                            if is_day
                            else row.get("minTemperature")
                        ),
                        humidity=row.get(f"{prefix}Humidity"),
                        cloud_coverage=row.get(f"{prefix}CloudCover"),
                        uv_index=row.get(f"{prefix}UvIndex"),
                        wind_bearing=row.get(f"{prefix}WindDirection"),
                        native_wind_speed=row.get(f"{prefix}WindSpeed"),
                        native_wind_gust_speed=row.get(f"{prefix}WindGust"),
                        precipitation_probability=row.get(f"{prefix}PrecipProb"),
                        native_precipitation=row.get(f"{prefix}PrecipQpf"),
                    )
                )
        return out or None
