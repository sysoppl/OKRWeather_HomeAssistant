"""Weather entity for OKRWeather.

Bridges three sources into a single ``WeatherEntity``:

* Current temperature/humidity/pressure/wind come from the **live** coordinator
  (the physical sensor).
* Current condition string comes from the nearest **hourly forecast** row in
  the forecast coordinator — the sensors don't report a categorical condition.
* Hourly + daily forecasts are served from the forecast coordinator's lists.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from homeassistant.components.weather import (
    Forecast,
    WeatherEntity,
    WeatherEntityFeature,
)
from homeassistant.const import (
    UnitOfPrecipitationDepth,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
)
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, DOMAIN, MANUFACTURER, MS_TO_KMH

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import (
        OKRWeatherForecastCoordinator,
        OKRWeatherLiveCoordinator,
    )
    from .data import OKRWeatherConfigEntry


# ── Condition mapping ───────────────────────────────────────────────────────


def _map_condition(raw: str | None, *, is_daytime: bool = True) -> str | None:
    """Translate the API's free-form condition string to an HA condition.

    Mirrors the logic in OKRWeather Portal's ``mapConditionType`` but emits
    HA's official condition vocabulary
    (``clear-night, cloudy, fog, hail, lightning, lightning-rainy,
    partlycloudy, pouring, rainy, snowy, snowy-rainy, sunny, windy``).
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
    if "snow" in s or "blizzard" in s or "flurr" in s:
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


def _parse_iso(value: Any) -> datetime | None:
    """Parse an ISO-8601 string; tolerate trailing Z and unaware datetimes."""
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


# ── Setup ───────────────────────────────────────────────────────────────────


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OKRWeatherConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime = entry.runtime_data
    async_add_entities(
        [
            OKRWeather(
                live=runtime.live_coordinator,
                forecast=runtime.forecast_coordinator,
                station_appwrite_id=runtime.station.appwrite_id,
                station_name=runtime.station.name,
            )
        ]
    )


# ── Entity ──────────────────────────────────────────────────────────────────


class OKRWeather(CoordinatorEntity, WeatherEntity):
    """Single weather entity per configured station."""

    _attr_attribution = ATTRIBUTION
    _attr_has_entity_name = True
    _attr_name = None  # use the device name as-is
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_native_pressure_unit = UnitOfPressure.HPA
    _attr_native_wind_speed_unit = UnitOfSpeed.KILOMETERS_PER_HOUR
    _attr_native_precipitation_unit = UnitOfPrecipitationDepth.MILLIMETERS
    _attr_supported_features = (
        WeatherEntityFeature.FORECAST_HOURLY | WeatherEntityFeature.FORECAST_DAILY
    )

    def __init__(
        self,
        live: OKRWeatherLiveCoordinator,
        forecast: OKRWeatherForecastCoordinator,
        station_appwrite_id: str,
        station_name: str,
    ) -> None:
        # CoordinatorEntity wants one primary coordinator — we use the live one
        # since that's what drives the state refresh cadence the user expects.
        super().__init__(live)
        self._forecast_coordinator = forecast
        self._station_appwrite_id = station_appwrite_id
        self._attr_unique_id = f"{station_appwrite_id}_weather"
        self._attr_device_info = self._build_device_info(station_appwrite_id, station_name)

    @staticmethod
    def _build_device_info(station_appwrite_id: str, station_name: str) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, station_appwrite_id)},
            name=station_name,
            manufacturer=MANUFACTURER,
            model="Weather Station",
            configuration_url="https://pogodaokr.pl",
        )

    async def async_added_to_hass(self) -> None:
        """Subscribe to *both* coordinators so the entity refreshes on either."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self._forecast_coordinator.async_add_listener(self.async_write_ha_state)
        )

    # ── Source rows ─────────────────────────────────────────────────────────

    @property
    def _weather_row(self) -> dict[str, Any] | None:
        data = self.coordinator.data or {}
        return data.get("weather")

    @property
    def _hourly_rows(self) -> list[dict[str, Any]]:
        data = self._forecast_coordinator.data or {}
        return data.get("hourly_forecast") or []

    @property
    def _daily_rows(self) -> list[dict[str, Any]]:
        data = self._forecast_coordinator.data or {}
        return data.get("daily_forecast") or []

    @property
    def _current_hourly(self) -> dict[str, Any] | None:
        """The hourly forecast row that brackets *now*, else the next one."""
        rows = self._hourly_rows
        if not rows:
            return None
        now = datetime.now(timezone.utc)
        chosen: dict[str, Any] | None = None
        for row in rows:
            t = _parse_iso(row.get("forecastTime"))
            if t is None:
                continue
            if t <= now:
                chosen = row
            else:
                break
        return chosen or rows[0]

    # ── Current state ───────────────────────────────────────────────────────

    @property
    def condition(self) -> str | None:
        row = self._current_hourly
        if not row:
            return None
        return _map_condition(
            row.get("weatherConditionType"),
            is_daytime=bool(row.get("isDaytime", True)),
        )

    @property
    def native_temperature(self) -> float | None:
        w = self._weather_row
        if w and w.get("air_temperature_c") is not None:
            return float(w["air_temperature_c"])
        cur = self._current_hourly
        return float(cur["temperature"]) if cur and cur.get("temperature") is not None else None

    @property
    def native_apparent_temperature(self) -> float | None:
        w = self._weather_row
        if w and w.get("sensed_temperature_c") is not None:
            return float(w["sensed_temperature_c"])
        cur = self._current_hourly
        if cur and cur.get("feelsLikeTemperature") is not None:
            return float(cur["feelsLikeTemperature"])
        return None

    @property
    def native_dew_point(self) -> float | None:
        w = self._weather_row
        if w and w.get("dew_point_c") is not None:
            return float(w["dew_point_c"])
        return None

    @property
    def humidity(self) -> float | None:
        w = self._weather_row
        if w and w.get("air_humidity_pct") is not None:
            return float(w["air_humidity_pct"])
        return None

    @property
    def native_pressure(self) -> float | None:
        w = self._weather_row
        if w and w.get("air_pressure_hpa") is not None:
            return float(w["air_pressure_hpa"])
        return None

    @property
    def native_wind_speed(self) -> float | None:
        w = self._weather_row
        if w and w.get("wind_speed_m_s") is not None:
            return round(float(w["wind_speed_m_s"]) * MS_TO_KMH, 1)
        return None

    @property
    def native_wind_gust_speed(self) -> float | None:
        w = self._weather_row
        if w and w.get("wind_gust_m_s") is not None:
            return round(float(w["wind_gust_m_s"]) * MS_TO_KMH, 1)
        return None

    @property
    def wind_bearing(self) -> float | None:
        w = self._weather_row
        if w and w.get("wind_direction_deg") is not None:
            return float(w["wind_direction_deg"])
        return None

    @property
    def uv_index(self) -> float | None:
        w = self._weather_row
        if w and w.get("uv_index") is not None:
            return float(w["uv_index"])
        cur = self._current_hourly
        if cur and cur.get("uvIndex") is not None:
            return float(cur["uvIndex"])
        return None

    @property
    def cloud_coverage(self) -> float | None:
        cur = self._current_hourly
        if cur and cur.get("cloudCover") is not None:
            return float(cur["cloudCover"])
        return None

    # ── Forecast methods ────────────────────────────────────────────────────

    async def async_forecast_hourly(self) -> list[Forecast] | None:
        out: list[Forecast] = []
        for row in self._hourly_rows:
            dt = _parse_iso(row.get("forecastTime"))
            if dt is None:
                continue
            wind = row.get("windSpeed")
            gust = row.get("windGust")
            out.append(
                {
                    "datetime": dt.isoformat(),
                    "condition": _map_condition(
                        row.get("weatherConditionType"),
                        is_daytime=bool(row.get("isDaytime", True)),
                    ),
                    "native_temperature": row.get("temperature"),
                    "native_apparent_temperature": row.get("feelsLikeTemperature"),
                    "native_dew_point": row.get("dewPoint"),
                    "humidity": row.get("relativeHumidity"),
                    "native_pressure": row.get("airPressureMsl"),
                    "native_wind_speed": round(float(wind) * MS_TO_KMH, 1) if isinstance(wind, (int, float)) else None,
                    "native_wind_gust_speed": round(float(gust) * MS_TO_KMH, 1) if isinstance(gust, (int, float)) else None,
                    "wind_bearing": row.get("windDirection"),
                    "cloud_coverage": row.get("cloudCover"),
                    "uv_index": row.get("uvIndex"),
                    "precipitation_probability": row.get("precipProbability"),
                    "native_precipitation": row.get("precipQpf"),
                }
            )
        return out or None

    async def async_forecast_daily(self) -> list[Forecast] | None:
        out: list[Forecast] = []
        for row in self._daily_rows:
            # daily-forecasts uses 'forecastDate' (YYYY-MM-DD) plus a 'forecastStartTime' ISO.
            dt = (
                _parse_iso(row.get("forecastStartTime"))
                or _parse_iso(f"{row.get('forecastDate')}T00:00:00+00:00")
            )
            if dt is None:
                continue
            wind = row.get("dayWindSpeed")
            gust = row.get("dayWindGust")
            # Day + night precip add up to a daily total.
            day_qpf = row.get("dayPrecipQpf") or 0
            night_qpf = row.get("nightPrecipQpf") or 0
            precip = float(day_qpf) + float(night_qpf) if (day_qpf or night_qpf) else None
            precip_prob = max(
                row.get("dayPrecipProb") or 0,
                row.get("nightPrecipProb") or 0,
            ) or None
            out.append(
                {
                    "datetime": dt.isoformat(),
                    "condition": _map_condition(row.get("dayWeatherType")),
                    "native_temperature": row.get("maxTemperature"),
                    "native_templow": row.get("minTemperature"),
                    "native_apparent_temperature": row.get("feelsLikeMaxTemp"),
                    "humidity": row.get("dayHumidity"),
                    "cloud_coverage": row.get("dayCloudCover"),
                    "uv_index": row.get("dayUvIndex"),
                    "wind_bearing": row.get("dayWindDirection"),
                    "native_wind_speed": round(float(wind) * MS_TO_KMH, 1) if isinstance(wind, (int, float)) else None,
                    "native_wind_gust_speed": round(float(gust) * MS_TO_KMH, 1) if isinstance(gust, (int, float)) else None,
                    "precipitation_probability": precip_prob,
                    "native_precipitation": precip,
                }
            )
        return out or None
