"""DataUpdateCoordinators for OKRWeather.

Three coordinators per hub entry, each on its own cadence:

* **Live** (fast, public) — station readings, measured air quality, alerts.
* **Insights** (medium, premium) — the active AI tables: comfort index, radar
  analysis, storm tracker, pressure alerts, frost alerts and solar forecast.
  Skipped entirely when no API key is configured.
* **Forecast** (slow, public) — hourly + daily forecasts per city.

All coordinators publish dicts keyed by station subentry_id so entities for
every configured station share the same requests. AI rows are fetched once
per table (newest N rows) and grouped per station client-side, instead of
one request per station per table.

Live and insight reads go through :class:`~.sources.TableResolver`: every
table is read on its own, so a missing (renamed or removed) table or a
failing request only blanks or freezes its own piece of data.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    OKRWeatherApiAuthError,
    OKRWeatherApiError,
    OKRWeatherApiPermissionError,
    _q,
)
from .const import (
    AIR_MAX_AGE_MIN,
    DOMAIN,
    INSIGHT_MAX_AGE_MIN,
    INSIGHT_TABLES,
    LIVE_LOOKBACK_HOURS,
    LIVE_STALE_MINUTES,
    LOGGER,
    SECTION_RADAR,
)
from .sources import (
    AIR_QUALITY,
    ALERTS,
    INSIGHT_SOURCES,
    RADAR,
    STATION_READINGS,
    Lookup,
    TableResolver,
)
from .util import (
    age_minutes,
    match_city,
    parse_iso,
    row_matches_station,
    sea_level_pressure,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .api import OKRWeatherApiClient
    from .data import OKRWeatherConfigEntry, StationConfig

# Current aggregate air-quality row of a station (AIRLY contract: the
# averaged Gogolin sensors are written with source "aggregate").
_AIR_CURRENT = (
    _q("equal", "kind", ["current"]),
    _q("equal", "source", ["aggregate"]),
)


def _keep_or(lookup: Lookup, previous: Any) -> Any:
    """The newest row, or the previous value when every candidate failed."""
    return previous if lookup.failed else lookup.row


def valid_air(row: Any, now: datetime) -> dict[str, Any] | None:
    """Measured air-quality row, or None when it must read as "no data".

    Rules from the backend contract: offline status, no PM value at all, or
    a measurement older than AIR_MAX_AGE_MIN all mean no data.
    """
    if not isinstance(row, dict) or row.get("qc_status") == "offline":
        return None
    if row.get("pm25") is None and row.get("pm10") is None:
        return None
    till = parse_iso(row.get("till_at"))
    if till is None or now - till > timedelta(minutes=AIR_MAX_AGE_MIN):
        return None
    return row


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
        self._sources: TableResolver | None = None

    @property
    def client(self) -> OKRWeatherApiClient:
        """The shared API client living on runtime_data."""
        return self.config_entry.runtime_data.client

    @property
    def sources(self) -> TableResolver:
        """Table reader with rename fallback; caches live for this session."""
        if self._sources is None:
            self._sources = TableResolver(self.client)
        return self._sources

    @property
    def stations(self) -> dict[str, StationConfig]:
        """Configured stations keyed by subentry_id."""
        return self.config_entry.runtime_data.stations


# ── Live coordinator ────────────────────────────────────────────────────────


class OKRWeatherLiveCoordinator(OKRWeatherCoordinator):
    """Polls live readings (station, measured air quality) and alerts.

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
        runtime = self.config_entry.runtime_data
        stations = self.stations

        # Refresh station metadata once per setup — subentry data may be
        # stale (v1-migrated entries lack city/alert-location entirely).
        if not self._station_meta_refreshed:
            try:
                station_rows = await self.client.list_stations()
                rows = {row["$id"]: row for row in station_rows}
                for station in stations.values():
                    if row := rows.get(station.appwrite_id):
                        station.refresh_from_row(row)
                runtime.backend_station_count = len(station_rows)
                self._station_meta_refreshed = True
            except OKRWeatherApiError as err:
                LOGGER.debug("Station metadata refresh failed, will retry: %s", err)

        now = datetime.now(UTC)
        sources = self.sources

        async def fetch_station(station: StationConfig) -> tuple[Lookup, Lookup]:
            weather, air = await asyncio.gather(
                sources.read(
                    STATION_READINGS,
                    station_id=station.appwrite_id,
                    since=now - timedelta(hours=LIVE_LOOKBACK_HOURS),
                    stale_before=now - timedelta(minutes=LIVE_STALE_MINUTES),
                    limit=1,
                ),
                sources.read(
                    AIR_QUALITY,
                    station_id=station.appwrite_id,
                    since=now - timedelta(minutes=AIR_MAX_AGE_MIN),
                    extra=_AIR_CURRENT,
                    limit=1,
                ),
            )
            return weather, air

        # Every table is read independently (TableResolver never raises), so
        # one missing or failing table only affects its own piece.
        alerts_lookup, *station_lookups = await asyncio.gather(
            sources.read(ALERTS, limit=50),
            *(fetch_station(s) for s in stations.values()),
        )

        lookups = [alerts_lookup, *(lk for pair in station_lookups for lk in pair)]
        if not any(lk.answered for lk in lookups):
            errors = [err for lk in lookups for err in lk.errors]
            if any(isinstance(err, OKRWeatherApiAuthError) for err in errors):
                # Live tables are public — 401 everywhere means the endpoint
                # or project id is wrong. Reauth only asks for an API key and
                # could never fix that, so point at reconfigure.
                raise UpdateFailed(
                    f"Backend rejected the project — fix endpoint/project "
                    f"via reconfigure: {errors[0]}"
                )
            if errors:
                raise UpdateFailed(f"Backend unreachable: {errors[0]}")

        previous = self.data or {}
        if alerts_lookup.failed:
            active_alerts: list[dict[str, Any]] = previous.get("alerts") or []
        else:
            # Alert rows are kept as history; only active (or legacy, status
            # null) rows that have not expired are current.
            active_alerts = [
                alert
                for alert in alerts_lookup.rows
                if alert.get("status") in (None, "active")
                and (
                    (expires := parse_iso(alert.get("expirationTime"))) is None
                    or expires > now
                )
            ]

        data: dict[str, Any] = {"alerts": active_alerts, "stations": {}}
        for (sid, station), (weather_lookup, air_lookup) in zip(
            stations.items(), station_lookups, strict=True
        ):
            before = previous.get("stations", {}).get(sid) or {}
            weather = _keep_or(weather_lookup, before.get("weather"))
            air = valid_air(_keep_or(air_lookup, before.get("air")), now)
            # Stations report absolute pressure at their elevation; derive
            # the sea-level value once here so every consumer agrees.
            if isinstance(weather, dict):
                weather = {
                    **weather,
                    "sea_level_pressure_hpa": sea_level_pressure(
                        weather.get("air_pressure_hpa"),
                        station.elevation_m,
                        weather.get("air_temperature_c"),
                    ),
                }
            # Alerts are regional — publish each station's pre-filtered slice
            # so all entities agree. No alert_location_id means no alerts
            # (conservative; the metadata refresh normally fills it in).
            data["stations"][sid] = {
                "weather": weather,
                "air": air,
                "alerts": self._station_alerts(active_alerts, station),
            }
        return data

    @staticmethod
    def _station_alerts(
        alerts: list[dict[str, Any]], station: StationConfig
    ) -> list[dict[str, Any]]:
        """Alerts covering the given station's alert area."""
        if not station.alert_location_id:
            return []
        return [
            alert
            for alert in alerts
            if alert.get("locationId") == station.alert_location_id
        ]


# ── Insights (premium AI) coordinator ───────────────────────────────────────


class OKRWeatherInsightsCoordinator(OKRWeatherCoordinator):
    """Polls the active premium AI tables.

    Each table is fetched once (newest rows across all stations, bounded to
    the per-feature freshness window) and grouped client-side. Rows older
    than that window are discarded so entities report *unknown* instead of
    freezing on stale data.
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
        # The tables mix rows from EVERY backend station (one row per station
        # per cron run), so the newest-N window must be sized by the backend
        # fleet — not by how few stations this hub configured.
        fleet = max(len(stations), runtime.backend_station_count)
        row_limit = max(12, 4 * fleet)
        now = datetime.now(UTC)

        lookups = await asyncio.gather(
            *(
                self.sources.read(
                    INSIGHT_SOURCES[section],
                    since=now - timedelta(minutes=INSIGHT_MAX_AGE_MIN[section]),
                    limit=row_limit,
                )
                for section in sections
            ),
            # Radar rows are keyed by city; staleness is judged per city below.
            self.sources.read(RADAR, limit=25),
        )
        radar_lookup = lookups.pop()

        errors = [err for lk in (*lookups, radar_lookup) for err in lk.errors]
        if (
            errors
            and not any(lk.answered for lk in (*lookups, radar_lookup))
            and all(isinstance(err, OKRWeatherApiAuthError) for err in errors)
        ):
            # Every premium table rejected the key — reauth is the fix. A 401
            # on just one table is skipped like any other per-table error.
            raise ConfigEntryAuthFailed(str(errors[0]))

        table_rows: dict[str, list[dict[str, Any]]] = {}
        for section, lookup in zip(sections, lookups, strict=True):
            if not lookup.failed:
                table_rows[section] = lookup.rows
            elif all(
                isinstance(err, OKRWeatherApiPermissionError) for err in lookup.errors
            ):
                # 403: the key lacks this table's scope. Reauth can't fix a
                # per-table gap, so just this section stays empty.
                table_rows[section] = []
            else:
                table_rows[section] = self._previous_rows(section)

        data: dict[str, Any] = {"stations": {}}
        for sid, station in stations.items():
            per_station: dict[str, Any] = {}
            for section in sections:
                per_station[section] = self._pick_row(
                    table_rows[section], station, section
                )
            per_station[SECTION_RADAR] = None
            data["stations"][sid] = per_station

        self._attach_radar(data, radar_lookup)
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

    def _attach_radar(self, data: dict[str, Any], radar_lookup: Lookup) -> None:
        """Group radar rows by city and attach the right city to each station."""
        if radar_lookup.failed:
            if all(
                isinstance(err, OKRWeatherApiPermissionError)
                for err in radar_lookup.errors
            ):
                return  # radar sections stay None
            for sid, per_station in data["stations"].items():
                if self.data:
                    previous = self.data.get("stations", {}).get(sid, {})
                    per_station[SECTION_RADAR] = previous.get(SECTION_RADAR)
            return

        newest_per_city: dict[str, dict[str, Any]] = {}
        for row in radar_lookup.rows:
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
        self._cities: dict[str, dict[str, Any]] | None = None

    async def _async_update_data(self) -> dict[str, Any]:
        stations = self.stations

        # (Re)run city discovery only while any station is still unmapped —
        # the station→city mapping is stable once resolved, so there's no
        # point re-downloading the discovery rows every cycle.
        if self._cities is None or any(
            s.forecast_city_id is None for s in stations.values()
        ):
            try:
                recent = await self.client.discover_forecast_cities()
            except OKRWeatherApiError as err:
                if self._cities is None:
                    raise UpdateFailed(
                        f"Could not enumerate forecast cities: {err}"
                    ) from err
                LOGGER.warning(
                    "City discovery failed (using cached city list): %s", err
                )
            else:
                cities: dict[str, dict[str, Any]] = {}
                for row in recent:
                    city_id = row.get("cityId")
                    if city_id and city_id not in cities:
                        cities[city_id] = {
                            "name": row.get("cityName"),
                            "lat": row.get("lat"),
                            "lon": row.get("lon"),
                        }
                self._cities = cities

            for station in stations.values():
                station.forecast_city_id = match_city(station, self._cities or {})

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
