"""Async Appwrite REST client for OKRWeather.

The client speaks Appwrite's TablesDB REST API directly so we don't pull in the
full Appwrite SDK (which would ship its own aiohttp session and complicate
HA's lifecycle). Two access modes:

* **Anonymous** (no API key) — only tables with `read("any")` permission are
  reachable. That covers stations, live readings, forecasts and alerts.
* **API key** — bypasses document-level label gating so premium AI tables
  (comfort, frost, solar, etc.) become readable too.

The query format follows Appwrite ≥ 1.6: each query is a JSON-encoded string
like ``{"method":"equal","attribute":"station","values":["xyz"]}`` passed in
the ``queries[]`` array.
"""

from __future__ import annotations

import asyncio
import json
import socket
from typing import Any

import aiohttp
from yarl import URL

from .const import (
    DATABASE_ID,
    DEFAULT_ENDPOINT,
    DEFAULT_PROJECT_ID,
    LOGGER,
)


# ── Exceptions ──────────────────────────────────────────────────────────────


class OKRWeatherApiError(Exception):
    """Base exception for the API client."""


class OKRWeatherApiCommunicationError(OKRWeatherApiError):
    """Raised when the API cannot be reached (timeout, DNS, connection drop)."""


class OKRWeatherApiAuthError(OKRWeatherApiError):
    """Raised when the API key is missing, malformed, or lacks the right scope."""


class OKRWeatherApiPermissionError(OKRWeatherApiError):
    """Raised when the request is rejected for permission reasons.

    Distinct from auth errors: the credentials are *valid*, but the caller is
    not allowed to read the requested table (e.g. anonymous call to a premium
    table). The coordinator uses this signal to disable premium entities
    gracefully instead of failing the whole setup.
    """


# ── Query builder ────────────────────────────────────────────────────────────


def _q(method: str, attribute: str | None = None, values: Any = None) -> str:
    """Build one Appwrite query string.

    Appwrite expects each query as a compact JSON object. Examples::

        _q("equal", "station", ["abc"])       -> {"method":"equal",...}
        _q("orderDesc", "$createdAt")          -> {"method":"orderDesc",...}
        _q("limit", values=1)                  -> {"method":"limit","values":[1]}
    """
    payload: dict[str, Any] = {"method": method}
    if attribute is not None:
        payload["attribute"] = attribute
    if values is not None:
        payload["values"] = values if isinstance(values, list) else [values]
    return json.dumps(payload, separators=(",", ":"))


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
        """Initialise the client.

        The session is borrowed from HA — never close it here.
        """
        self._session = session
        self._endpoint = endpoint.rstrip("/")
        self._project_id = project_id
        self._api_key = api_key or None
        self._timeout = request_timeout

    @property
    def has_api_key(self) -> bool:
        """Whether a non-empty API key was supplied."""
        return bool(self._api_key)

    # ── Public table fetches ────────────────────────────────────────────────

    async def list_stations(self) -> list[dict[str, Any]]:
        """Return all active weather stations."""
        return await self._list_rows(
            "weather-stations",
            queries=[_q("equal", "is_active", [True]), _q("limit", values=50)],
        )

    async def latest_weather(self, station_id: str) -> dict[str, Any] | None:
        """Return the most recent weather row for the given station, or None."""
        rows = await self._list_rows(
            "weather-data",
            queries=[
                _q("equal", "station", [station_id]),
                _q("orderDesc", "$createdAt"),
                _q("limit", values=1),
            ],
        )
        return rows[0] if rows else None

    async def latest_air(self, station_id: str) -> dict[str, Any] | None:
        """Return the most recent air-quality row, or None when not available."""
        rows = await self._list_rows(
            "air-quality-data",
            queries=[
                _q("equal", "station", [station_id]),
                _q("orderDesc", "$createdAt"),
                _q("limit", values=1),
            ],
        )
        return rows[0] if rows else None

    async def active_alerts(self) -> list[dict[str, Any]]:
        """Return weather alerts (we filter for unexpired ones client-side)."""
        return await self._list_rows(
            "weather-alerts",
            queries=[
                _q("orderDesc", "$createdAt"),
                _q("limit", values=25),
            ],
        )

    async def hourly_forecasts(self, city_id: str, hours: int = 48) -> list[dict[str, Any]]:
        """Return up to `hours` hourly forecast rows for `city_id`."""
        return await self._list_rows(
            "hourly-forecasts",
            queries=[
                _q("equal", "cityId", [city_id]),
                _q("orderAsc", "forecastTime"),
                _q("limit", values=hours),
            ],
        )

    async def daily_forecasts(self, city_id: str, days: int = 10) -> list[dict[str, Any]]:
        """Return up to `days` daily forecast rows for `city_id`."""
        return await self._list_rows(
            "daily-forecasts",
            queries=[
                _q("equal", "cityId", [city_id]),
                _q("orderAsc", "forecastDate"),
                _q("limit", values=days),
            ],
        )

    async def all_hourly_forecasts(self, limit: int = 500) -> list[dict[str, Any]]:
        """Return the latest hourly forecast rows across *all* cities.

        Used during setup to discover the cityId nearest the chosen station.
        """
        return await self._list_rows(
            "hourly-forecasts",
            queries=[
                _q("orderDesc", "fetchedAt"),
                _q("limit", values=limit),
            ],
        )

    # ── Premium tables (require API key) ────────────────────────────────────

    async def latest_premium_row(
        self,
        table: str,
        station_key: str,
    ) -> dict[str, Any] | None:
        """Return the most recent row for a premium table tied to a station.

        Filters by the ``station_id`` *string column* (not the ``station``
        relationship), because not every premium table has the relationship —
        e.g. ``sport-conditions`` and ``drying-conditions`` only carry the
        plain string column. All premium tables share ``station_id`` though,
        so this query is portable across every premium table.

        ``station_key`` is the value stored in that column (sourced from the
        weather-stations ``station_id`` column at config time).
        """
        rows = await self._list_rows(
            table,
            queries=[
                _q("equal", "station_id", [station_key]),
                _q("orderDesc", "$createdAt"),
                _q("limit", values=1),
            ],
        )
        return rows[0] if rows else None

    # ── Internal HTTP ───────────────────────────────────────────────────────

    async def _list_rows(
        self,
        table_id: str,
        *,
        queries: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Wrap GET /tablesdb/{db}/tables/{t}/rows and return the row list.

        Path note: Appwrite renamed `/databases/.../tables/...` to
        `/tablesdb/.../tables/...` in the August 2025 TablesDB API release
        (Appwrite 1.8). The old path now returns 404.
        """
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
                            f"Invalid credentials ({resp.status}): {text[:200]}"
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
        except asyncio.TimeoutError as exc:
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
