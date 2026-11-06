"""Test setup: minimal Home Assistant stubs and a fake Appwrite backend.

The coordinators only need ``DataUpdateCoordinator``, ``UpdateFailed`` and
``ConfigEntryAuthFailed`` from Home Assistant, so small stand-ins are enough
and the tests run without installing Home Assistant. The package is
registered without executing its ``__init__`` (which wires up HA platforms).
"""

from __future__ import annotations

import json
import sys
import types
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Generic, TypeVar

import pytest

ROOT = Path(__file__).resolve().parents[1]

# ── Home Assistant stand-ins ────────────────────────────────────────────────
_T = TypeVar("_T")


class DataUpdateCoordinator(Generic[_T]):
    def __init__(self, hass, logger, *, name, update_interval, config_entry=None):
        self.hass = hass
        self.logger = logger
        self.name = name
        self.update_interval = update_interval
        self.config_entry = config_entry
        self.data = None

    async def poll(self):
        """Test helper: one update cycle, storing the result like HA does."""
        self.data = await self._async_update_data()
        return self.data


class UpdateFailed(Exception):
    pass


class ConfigEntryAuthFailed(Exception):
    pass


def _module(name: str, **attrs: Any) -> types.ModuleType:
    mod = types.ModuleType(name)
    mod.__dict__.update(attrs)
    sys.modules[name] = mod
    return mod


_module("homeassistant")
_module("homeassistant.exceptions", ConfigEntryAuthFailed=ConfigEntryAuthFailed)
_module("homeassistant.helpers")
_module(
    "homeassistant.helpers.update_coordinator",
    DataUpdateCoordinator=DataUpdateCoordinator,
    UpdateFailed=UpdateFailed,
)

_cc = _module("custom_components")
_cc.__path__ = [str(ROOT / "custom_components")]
_pkg = _module("custom_components.okrweather")
_pkg.__path__ = [str(ROOT / "custom_components" / "okrweather")]

from custom_components.okrweather.api import (  # noqa: E402
    OKRWeatherApiClient,
    OKRWeatherApiCommunicationError,
    raise_for_status,
)
from custom_components.okrweather.data import StationConfig  # noqa: E402

# ── Fake Appwrite TablesDB ──────────────────────────────────────────────────

GOG = "69d4c13e0027e1e6f81b"
LPR = "6a2284280022dc6ee934"


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.000+00:00")


def ago(minutes: float, now: datetime | None = None) -> str:
    return iso((now or datetime.now(UTC)) - timedelta(minutes=minutes))


def _parse(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class FakeAppwrite(OKRWeatherApiClient):
    """OKRWeatherApiClient whose HTTP layer is an in-memory TablesDB.

    Errors use Appwrite 2.6's real bodies (captured from the live server) and
    go through the client's own ``raise_for_status``.
    """

    def __init__(self) -> None:
        super().__init__(session=None, api_key="test")  # type: ignore[arg-type]
        self.tables: dict[str, dict[str, Any]] = {}
        self.calls: list[tuple[str, list[dict[str, Any]]]] = []
        self.fail: dict[str, Any] = {}

    def add(self, table: str, columns: set[str], rows: list[dict[str, Any]] = ()) -> None:
        stored = []
        for i, row in enumerate(rows):
            row = {"$id": f"{table}-{i}", "$createdAt": ago(0), "$tableId": table, **row}
            stored.append(row)
        self.tables[table] = {"columns": set(columns), "rows": stored}

    def tables_called(self) -> list[str]:
        return [table for table, _ in self.calls]

    async def _request(self, method: str, path: str, *, params=None):
        parts = path.split("/")
        table = parts[4]
        queries = [json.loads(q) for q in (params or {}).get("queries[]", [])]
        self.calls.append((table, queries))
        if table in self.fail:
            failure = self.fail[table]
            if isinstance(failure, BaseException):
                raise failure
            raise_for_status(failure, path, json.dumps({"message": "boom", "code": failure}))
        if table not in self.tables:
            raise_for_status(404, path, json.dumps({
                "message": f"Table with the requested ID '{table}' could not be found.",
                "code": 404, "type": "table_not_found", "version": "2.6.2",
            }))
        spec = self.tables[table]
        rows = list(spec["rows"])
        limit = 25
        for q in queries:
            method_, attr, values = q["method"], q.get("attribute"), q.get("values")
            if attr and not attr.startswith("$") and attr not in spec["columns"]:
                raise_for_status(400, path, json.dumps({
                    "message": f"Invalid query: Attribute not found in schema: {attr}",
                    "code": 400, "type": "general_query_invalid", "version": "2.6.2",
                }))
            if method_ == "equal":
                rows = [r for r in rows if r.get(attr) in values]
            elif method_ == "greaterThanEqual":
                bound = _parse(values[0])
                rows = [r for r in rows if (t := _parse(r.get(attr))) and t >= bound]
            elif method_ in ("orderDesc", "orderAsc"):
                rows.sort(
                    key=lambda r: _parse(r.get(attr)) or datetime.min.replace(tzinfo=UTC),
                    reverse=method_ == "orderDesc",
                )
            elif method_ == "limit":
                limit = values[0]
        return {"total": len(rows), "rows": rows[:limit]}


# Live column sets (2026-11-06), trimmed to what the integration reads.
READING_VALUES = {"air_temperature_c", "air_pressure_hpa", "air_humidity_pct"}
COLUMNS = {
    "station-readings": {"station_id", "measured_at", "time_source", "writer", *READING_VALUES},
    "weather-data": {"station", "measurementDate", *READING_VALUES},
    "air-quality-readings": {
        "installation_id", "station_id", "kind", "from_at", "till_at", "pm25", "pm10",
        "gios_level", "gios_level_name", "index_value", "index_level", "qc_status",
        "members_used", "source",
    },
    "weather-alerts": {"status", "expirationTime", "locationId", "alertTitle"},
    "comfort-index": {"station_id", "station", "comfort_score", "analyzed_at"},
    "storm-alerts": {"station_id", "proximity_level", "analyzed_at"},
    "storm-tracker": {"station_id", "station", "proximity_level", "analyzed_at"},
    "pressure-alerts": {"station_id", "station", "alert_level", "analyzed_at"},
    "frost-alerts": {"station_id", "station", "frost_level", "analyzed_at"},
    "solar-forecasts": {"station_id", "total_kwh", "analyzed_at"},
    "solar-forecast": {"station_id", "station", "total_kwh", "analyzed_at"},
    "radar-status": {"city_id", "city_name", "intensity", "analyzed_at"},
}


def station(appwrite_id: str = GOG, key: str = "pl-opo-gog-01", name: str = "Gogolin") -> StationConfig:
    return StationConfig(
        subentry_id=f"sub-{appwrite_id}",
        appwrite_id=appwrite_id,
        station_key=key,
        slug=key,
        name=name,
        city=name,
        latitude=50.49,
        longitude=18.02,
        elevation_m=170.0,
        alert_location_id="loc-1",
    )


def entry(client: FakeAppwrite, stations: list[StationConfig], *, premium: bool = True):
    runtime = types.SimpleNamespace(
        client=client,
        stations={s.subentry_id: s for s in stations},
        backend_station_count=3,
        premium_enabled=premium,
    )
    return types.SimpleNamespace(runtime_data=runtime)


@pytest.fixture
def api() -> FakeAppwrite:
    return FakeAppwrite()


@pytest.fixture
def network_down() -> OKRWeatherApiCommunicationError:
    return OKRWeatherApiCommunicationError("Timeout fetching x after 15s")
