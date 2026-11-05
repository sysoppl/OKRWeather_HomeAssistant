"""Async Appwrite REST client for OKRWeather.

The client speaks Appwrite's TablesDB REST API directly so we don't pull in
the full Appwrite SDK (which would ship its own aiohttp session and
complicate HA's lifecycle). Two access modes:

* **Anonymous** (no API key) — only tables with ``read("any")`` permission are
  reachable: stations, live readings, lightning, forecasts and alerts.
* **API key** — bypasses row-level label gating so the premium AI tables
  (comfort, radar, storm, pressure, frost, solar, air-trend) become readable.

The query format follows Appwrite ≥ 1.6: each query is a JSON-encoded string
like ``{"method":"equal","attribute":"station","values":["xyz"]}`` passed in
the ``queries[]`` array.
"""

from __future__ import annotations

import asyncio
import json
import socket
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import aiohttp
from yarl import URL

from .const import (
    DATABASE_ID,
    DEFAULT_ENDPOINT,
    DEFAULT_PROJECT_ID,
    LOGGER,
    TABLE_ALERTS,
    TABLE_DAILY_FORECASTS,
    TABLE_HOURLY_FORECASTS,
    TABLE_RADAR_STATUS,
    TABLE_STATIONS,
)

# ── Exceptions ──────────────────────────────────────────────────────────────


class OKRWeatherApiError(Exception):
    """Base exception for the API client."""


class OKRWeatherApiCommunicationError(OKRWeatherApiError):
    """Raised when the API cannot be reached (timeout, DNS, connection drop)."""


class OKRWeatherApiAuthError(OKRWeatherApiError):
    """Raised when credentials are missing or rejected (HTTP 401).

    Note: Appwrite answers *anonymous* requests to label-gated tables with
    401 as well, so for premium tables this simply means "no valid access".
    """


class OKRWeatherApiPermissionError(OKRWeatherApiError):
    """Raised when valid credentials lack access to a table (HTTP 403)."""


# ── Query builder ────────────────────────────────────────────────────────────


def _q(method: str, attribute: str | None = None, values: Any = None) -> str:
    """Build one Appwrite query string."""
    payload: dict[str, Any] = {"method": method}
    if attribute is not None:
        payload["attribute"] = attribute
    if values is not None:
        payload["values"] = values if isinstance(values, list) else [values]
    return json.dumps(payload, separators=(",", ":"))


_WARSAW = ZoneInfo("Europe/Warsaw")


def hourly_since(now: datetime | None = None) -> str:
    """Lower bound for hourly forecast rows: the start of the previous hour (UTC).

    The forecast tables keep past rows (the last issued forecast for each
    hour), so every forecast query needs a time bound; without one an
    ascending query with a limit returns the oldest rows.
    """
    now = now or datetime.now(UTC)
    start = (now.astimezone(UTC) - timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    return start.strftime("%Y-%m-%dT%H:%M:%SZ")


def daily_since(now: datetime | None = None) -> str:
    """First current forecast date (YYYY-MM-DD).

    The forecast day runs 07:00 -> 07:00 Europe/Warsaw, so before 07:00 local
    the first current day still carries the previous calendar date.
    """
    now = now or datetime.now(UTC)
    return (now.astimezone(_WARSAW) - timedelta(hours=7)).date().isoformat()


# ── Client ───────────────────────────────────────────────────────────────────


class OKRWeatherApiClient:
    """Lightweight Appwrite REST wrapper for read-only weather queries."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        *,
        endpoint: str = DEFAULT_ENDPOINT,
        project_id: str = DEFAULT_PROJECT_ID,
        api_key: str | None = None,
        request_timeout: int = 15,
    ) -> None:
        """Initialise the client. The session is borrowed from HA."""
        self._session = session
        self._endpoint = endpoint.rstrip("/")
        self._project_id = project_id
        self._api_key = api_key or None
        self._timeout = request_timeout

    @property
    def has_api_key(self) -> bool:
        """Whether a non-empty API key was supplied."""
        return bool(self._api_key)

    # ── Public tables ───────────────────────────────────────────────────────

    async def list_stations(self, *, active_only: bool = True) -> list[dict[str, Any]]:
        """Return the weather stations."""
        queries = [_q("limit", values=100)]
        if active_only:
            queries.insert(0, _q("equal", "is_active", [True]))
        return await self._list_rows(TABLE_STATIONS, queries=queries)

    async def latest_station_row(
        self, table: str, station_appwrite_id: str
    ) -> dict[str, Any] | None:
        """Return the newest row of a station-related public table, or None."""
        rows = await self._list_rows(
            table,
            queries=[
                _q("equal", "station", [station_appwrite_id]),
                _q("orderDesc", "$createdAt"),
                _q("limit", values=1),
            ],
        )
        return rows[0] if rows else None

    async def recent_alerts(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return recent weather alerts (expiry is filtered client-side)."""
        return await self._list_rows(
            TABLE_ALERTS,
            queries=[_q("orderDesc", "$createdAt"), _q("limit", values=limit)],
        )

    async def hourly_forecasts(self, city_id: str, hours: int = 48) -> list[dict[str, Any]]:
        """Return up to `hours` upcoming hourly forecast rows for a city."""
        return await self._list_rows(
            TABLE_HOURLY_FORECASTS,
            queries=[
                _q("equal", "cityId", [city_id]),
                _q("greaterThanEqual", "forecastTime", hourly_since()),
                _q("orderAsc", "forecastTime"),
                _q("limit", values=hours),
            ],
        )

    async def daily_forecasts(self, city_id: str, days: int = 10) -> list[dict[str, Any]]:
        """Return up to `days` daily forecast rows for a city."""
        return await self._list_rows(
            TABLE_DAILY_FORECASTS,
            queries=[
                _q("equal", "cityId", [city_id]),
                _q("greaterThanEqual", "forecastDate", daily_since()),
                _q("orderAsc", "forecastDate"),
                _q("limit", values=days),
            ],
        )

    async def discover_forecast_cities(self, limit: int = 500) -> list[dict[str, Any]]:
        """Return slim rows for discovering which forecast cities exist.

        Uses the daily-forecasts table (≈10 rows per city instead of ≈240 in
        hourly-forecasts, so the window can't silently drop a whole city) and
        selects only the columns needed for matching.
        """
        return await self._list_rows(
            TABLE_DAILY_FORECASTS,
            queries=[
                _q("select", values=["cityId", "cityName", "lat", "lon"]),
                _q("orderDesc", "fetchedAt"),
                _q("limit", values=limit),
            ],
        )

    # ── Premium tables (require API key) ────────────────────────────────────

    async def recent_insight_rows(self, table: str, limit: int) -> list[dict[str, Any]]:
        """Return the newest rows of a premium AI table (all stations mixed).

        The caller groups rows per station client-side — one request serves
        every configured station instead of one request per station.
        """
        return await self._list_rows(
            table,
            queries=[_q("orderDesc", "$createdAt"), _q("limit", values=limit)],
        )

    async def radar_rows(self, limit: int = 25) -> list[dict[str, Any]]:
        """Return recent radar-status rows (one row per analysed city)."""
        return await self._list_rows(
            TABLE_RADAR_STATUS,
            queries=[_q("orderDesc", "analyzed_at"), _q("limit", values=limit)],
        )

    # ── Internal HTTP ───────────────────────────────────────────────────────

    async def _list_rows(
        self,
        table_id: str,
        *,
        queries: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Wrap GET /tablesdb/{db}/tables/{t}/rows and return the row list."""
        data = await self._request(
            "GET",
            f"/tablesdb/{DATABASE_ID}/tables/{table_id}/rows",
            params={"queries[]": queries or []},
        )
        return data.get("rows", []) if isinstance(data, dict) else []

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """Issue one HTTP request and translate failure modes into our errors."""
        url = URL(f"{self._endpoint}{path}")

        # yarl's URL.with_query doesn't repeat keys for list values the way
        # aiohttp.MultiDict does, so build the query string ourselves.
        if params:
            multi: list[tuple[str, str]] = []
            for key, value in params.items():
                if isinstance(value, list):
                    multi.extend((key, str(v)) for v in value)
                else:
                    multi.append((key, str(value)))
            url = url.with_query(multi)

        headers = {
            "X-Appwrite-Project": self._project_id,
            "X-Appwrite-Response-Format": "1.8.0",
            "Accept": "application/json",
        }
        if self._api_key:
            headers["X-Appwrite-Key"] = self._api_key

        try:
            async with asyncio.timeout(self._timeout):
                async with self._session.request(method, url, headers=headers) as resp:
                    text = await resp.text()
                    if resp.status == 401:
                        raise OKRWeatherApiAuthError(
                            f"Unauthorized ({resp.status}) on {path}: {text[:200]}"
                        )
                    if resp.status == 403:
                        raise OKRWeatherApiPermissionError(
                            f"Permission denied ({resp.status}): {text[:200]}"
                        )
                    if resp.status >= 400:
                        raise OKRWeatherApiError(
                            f"HTTP {resp.status} on {path}: {text[:200]}"
                        )
                    if not text:
                        return {}
                    try:
                        return json.loads(text)
                    except json.JSONDecodeError as exc:
                        raise OKRWeatherApiError(
                            f"Invalid JSON from {path}: {exc}"
                        ) from exc
        except TimeoutError as exc:
            raise OKRWeatherApiCommunicationError(
                f"Timeout fetching {path} after {self._timeout}s"
            ) from exc
        except (aiohttp.ClientError, socket.gaierror) as exc:
            raise OKRWeatherApiCommunicationError(
                f"Network error fetching {path}: {exc}"
            ) from exc
        except OKRWeatherApiError:
            raise
        except Exception as exc:
            LOGGER.exception("Unexpected error talking to Appwrite")
            raise OKRWeatherApiError(str(exc)) from exc
