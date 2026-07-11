"""DataUpdateCoordinators for OKRWeather.

Three coordinators per hub entry, each on its own cadence:

* **Live** (fast, public) — station readings, air quality, lightning, alerts.
* **Insights** (medium, premium) — the active AI tables: comfort index, radar
  analysis, storm tracker, pressure alerts, frost alerts, solar forecast and
  air-quality trend. Skipped entirely when no API key is configured.
* **Forecast** (slow, public) — hourly + daily forecasts per city.

All coordinators publish dicts keyed by station subentry_id so entities for
every configured station share the same requests. AI rows are fetched once
per table (newest N rows) and grouped per station client-side, instead of
one request per station per table.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    OKRWeatherApiAuthError,
    OKRWeatherApiCommunicationError,
    OKRWeatherApiError,
    OKRWeatherApiPermissionError,
)
from .const import (
    DOMAIN,
    INSIGHT_MAX_AGE_MIN,
    INSIGHT_TABLES,
    LOGGER,
    SECTION_RADAR,
    TABLE_AIR,
    TABLE_LIGHTNING,
    TABLE_WEATHER,
)
from .util import age_minutes, match_city, parse_iso, row_matches_station

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .api import OKRWeatherApiClient
    from .data import OKRWeatherConfigEntry, StationConfig


class OKRWeatherCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Shared base — access to the config entry, client and station list."""

    config_entry: OKRWeatherConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: OKRWeatherConfigEntry,
        *,
        name: str,
        update_interval: timedelta,
    ) -> None:
        super().__init__(
            hass,
            LOGGER,
            name=f"{DOMAIN}_{name}",
            update_interval=update_interval,
            config_entry=entry,
        )

    @property
    def client(self) -> OKRWeatherApiClient:
        """The shared API client living on runtime_data."""
        return self.config_entry.runtime_data.client

    @property
    def stations(self) -> dict[str, StationConfig]:
        """Configured stations keyed by subentry_id."""
        return self.config_entry.runtime_data.stations


# ── Live coordinator ────────────────────────────────────────────────────────


class OKRWeatherLiveCoordinator(OKRWeatherCoordinator):
    """Polls live readings (weather, air, lightning) and alerts.

    Public tables only, so this works with or without an API key.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry: OKRWeatherConfigEntry,
        update_interval: timedelta,
    ) -> None:
        super().__init__(hass, entry, name="live", update_interval=update_interval)
        self._station_meta_refreshed = False

    async def _async_update_data(self) -> dict[str, Any]:
        stations = self.stations

        # Refresh station metadata once per setup — subentry data may be
        # stale (v1-migrated entries lack city/alert-location entirely).
        if not self._station_meta_refreshed:
            try:
                rows = {row["$id"]: row for row in await self.client.list_stations()}
                for station in stations.values():
                    if row := rows.get(station.appwrite_id):
                        station.refresh_from_row(row)
                self._station_meta_refreshed = True
            except OKRWeatherApiError as err:
                LOGGER.debug("Station metadata refresh failed, will retry: %s", err)

        async def fetch_station(station: StationConfig) -> dict[str, Any]:
            weather, air, lightning = await asyncio.gather(
                self.client.latest_station_row(TABLE_WEATHER, station.appwrite_id),
                self.client.latest_station_row(TABLE_AIR, station.appwrite_id),
                self.client.latest_station_row(TABLE_LIGHTNING, station.appwrite_id),
            )
            return {"weather": weather, "air": air, "lightning": lightning}

        try:
            results = await asyncio.gather(
                self.client.recent_alerts(),
                *(fetch_station(s) for s in stations.values()),
            )
        except OKRWeatherApiAuthError as err:
            # Live tables are public — a 401 here means the endpoint or
            # project id is wrong. Reauth only asks for an API key and could
            # never fix that, so fail the update and point at reconfigure.
            raise UpdateFailed(
                f"Backend rejected the project — fix endpoint/project via "
                f"reconfigure: {err}"
            ) from err
        except OKRWeatherApiError as err:
            raise UpdateFailed(str(err)) from err

        alerts, *station_rows = results
        now = datetime.now(UTC)
        active_alerts = [
            alert
            for alert in alerts
            if (expires := parse_iso(alert.get("expirationTime"))) is None
            or expires > now
        ]

        return {
            "alerts": active_alerts,
            "stations": dict(zip(stations.keys(), station_rows, strict=True)),
        }


# ── Insights (premium AI) coordinator ───────────────────────────────────────


class OKRWeatherInsightsCoordinator(OKRWeatherCoordinator):
    """Polls the active premium AI tables.

    Each table is fetched once (newest rows across all stations) and grouped
    client-side. Rows older than the per-feature freshness window are
    discarded so entities report *unknown* instead of freezing on stale data.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry: OKRWeatherConfigEntry,
        update_interval: timedelta,
    ) -> None:
        super().__init__(hass, entry, name="insights", update_interval=update_interval)

    async def _async_update_data(self) -> dict[str, Any]:
        runtime = self.config_entry.runtime_data
        stations = self.stations
        if not runtime.premium_enabled or not stations:
            return {"stations": {sid: {} for sid in stations}}

        sections = list(INSIGHT_TABLES)
        row_limit = max(12, 4 * len(stations))

        fetches = [
            self.client.recent_insight_rows(INSIGHT_TABLES[section], row_limit)
            for section in sections
        ]
        fetches.append(self.client.radar_rows())
        results = await asyncio.gather(*fetches, return_exceptions=True)
        radar_result = results.pop()

        table_rows: dict[str, list[dict[str, Any]]] = {}
        for section, result in zip(sections, results, strict=True):
            if isinstance(result, (OKRWeatherApiAuthError, OKRWeatherApiPermissionError)):
                # The key itself is bad or lacks scope — reauth is the fix.
                raise ConfigEntryAuthFailed(str(result))
            if isinstance(result, BaseException):
                LOGGER.warning(
                    "Fetch of AI table '%s' failed (keeping previous data): %s",
                    INSIGHT_TABLES[section],
                    result,
                )
                table_rows[section] = self._previous_rows(section)
            else:
                table_rows[section] = result

        data: dict[str, Any] = {"stations": {}}
        for sid, station in stations.items():
            per_station: dict[str, Any] = {}
            for section in sections:
                per_station[section] = self._pick_row(
                    table_rows[section], station, section
                )
            per_station[SECTION_RADAR] = None
            data["stations"][sid] = per_station

        self._attach_radar(data, radar_result)
        return data

    def _previous_rows(self, section: str) -> list[dict[str, Any]]:
        """Recover the previously-published rows of a section after a failed fetch."""
        if not self.data:
            return []
        return [
            row
            for per_station in self.data.get("stations", {}).values()
            if (row := per_station.get(section)) is not None
        ]

    @staticmethod
    def _pick_row(
        rows: list[dict[str, Any]],
        station: StationConfig,
        section: str,
    ) -> dict[str, Any] | None:
        """Newest fresh row of a section belonging to the given station."""
        max_age = INSIGHT_MAX_AGE_MIN.get(section)
        for row in rows:
            if not row_matches_station(row, station):
                continue
            age = age_minutes(row.get("analyzed_at") or row.get("$createdAt"))
            if max_age is not None and age is not None and age > max_age:
                return None  # rows are newest-first; older ones are staler
            return row
        return None

    def _attach_radar(self, data: dict[str, Any], radar_result: Any) -> None:
        """Group radar rows by city and attach the right city to each station."""
        if isinstance(radar_result, (OKRWeatherApiAuthError, OKRWeatherApiPermissionError)):
            raise ConfigEntryAuthFailed(str(radar_result))
        if isinstance(radar_result, BaseException):
            LOGGER.warning("Radar fetch failed (keeping previous data): %s", radar_result)
            for sid, per_station in data["stations"].items():
                if self.data:
                    previous = self.data.get("stations", {}).get(sid, {})
                    per_station[SECTION_RADAR] = previous.get(SECTION_RADAR)
            return

        newest_per_city: dict[str, dict[str, Any]] = {}
        for row in radar_result:
            city_id = row.get("city_id")
            if not city_id:
                continue
            current = newest_per_city.get(city_id)
            if current is None or (
                (parse_iso(row.get("analyzed_at")) or datetime.min.replace(tzinfo=UTC))
                > (parse_iso(current.get("analyzed_at")) or datetime.min.replace(tzinfo=UTC))
            ):
                newest_per_city[city_id] = row

        cities = {
            cid: {"name": row.get("city_name")}
            for cid, row in newest_per_city.items()
        }
        max_age = INSIGHT_MAX_AGE_MIN[SECTION_RADAR]
        for sid, station in self.stations.items():
            station.radar_city_id = match_city(station, cities)
            row = newest_per_city.get(station.radar_city_id or "")
            if row is not None:
                age = age_minutes(row.get("analyzed_at"))
                if age is not None and age > max_age:
                    row = None
            data["stations"][sid][SECTION_RADAR] = row


# ── Forecast coordinator ────────────────────────────────────────────────────


class OKRWeatherForecastCoordinator(OKRWeatherCoordinator):
    """Polls hourly + daily forecasts for every city the stations map to.

    Forecasts are stored per city (not per station); each station is matched
    to its city by name, falling back to nearest-by-distance.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry: OKRWeatherConfigEntry,
        update_interval: timedelta,
    ) -> None:
        super().__init__(hass, entry, name="forecast", update_interval=update_interval)

    async def _async_update_data(self) -> dict[str, Any]:
        stations = self.stations

        try:
            recent = await self.client.recent_hourly_forecasts()
        except OKRWeatherApiError as err:
            raise UpdateFailed(f"Could not enumerate forecast cities: {err}") from err

        cities: dict[str, dict[str, Any]] = {}
        for row in recent:
            city_id = row.get("cityId")
            if city_id and city_id not in cities:
                cities[city_id] = {
                    "name": row.get("cityName"),
                    "lat": row.get("lat"),
                    "lon": row.get("lon"),
                }

        for station in stations.values():
            station.forecast_city_id = match_city(station, cities)

        wanted = sorted(
            {s.forecast_city_id for s in stations.values() if s.forecast_city_id}
        )
        results = await asyncio.gather(
            *(self._fetch_city(city_id) for city_id in wanted),
            return_exceptions=True,
        )

        data: dict[str, Any] = {"cities": {}}
        for city_id, result in zip(wanted, results, strict=True):
            if isinstance(result, BaseException):
                LOGGER.warning("Forecast fetch for '%s' failed: %s", city_id, result)
                if self.data:
                    data["cities"][city_id] = self.data.get("cities", {}).get(
                        city_id, {"hourly": [], "daily": []}
                    )
                else:
                    data["cities"][city_id] = {"hourly": [], "daily": []}
            else:
                data["cities"][city_id] = result
        return data

    async def _fetch_city(self, city_id: str) -> dict[str, list[dict[str, Any]]]:
        hourly, daily = await asyncio.gather(
            self.client.hourly_forecasts(city_id, hours=48),
            self.client.daily_forecasts(city_id, days=10),
        )
        cutoff = datetime.now(UTC) - timedelta(hours=1)
        hourly = [
            row
            for row in hourly
            if (t := parse_iso(row.get("forecastTime"))) is None or t >= cutoff
        ]
        return {"hourly": hourly, "daily": daily}
