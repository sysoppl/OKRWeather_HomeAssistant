"""Diagnostics support for OKRWeather."""

from __future__ import annotations

from dataclasses import asdict
from typing import TYPE_CHECKING, Any

from homeassistant.components.diagnostics import async_redact_data

from .const import CONF_API_KEY

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .data import OKRWeatherConfigEntry

TO_REDACT = {CONF_API_KEY}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: OKRWeatherConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a hub entry."""
    runtime = entry.runtime_data

    def _trim_forecasts(data: dict[str, Any] | None) -> Any:
        """Keep forecast payloads small — 3 rows per list is plenty."""
        if not data:
            return data
        return {
            "cities": {
                city_id: {
                    kind: rows[:3] if isinstance(rows, list) else rows
                    for kind, rows in city.items()
                }
                for city_id, city in data.get("cities", {}).items()
            }
        }

    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
            "premium_enabled": runtime.premium_enabled,
        },
        "stations": {
            subentry_id: asdict(station)
            for subentry_id, station in runtime.stations.items()
        },
        "live": runtime.live_coordinator.data,
        "insights": runtime.insights_coordinator.data,
        "forecast": _trim_forecasts(runtime.forecast_coordinator.data),
    }
