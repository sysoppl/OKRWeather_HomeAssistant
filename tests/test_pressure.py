"""Pressure contract (2026-11-13): every pressure shown is reduced to mean sea level."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest
from conftest import COLUMNS, GOG, ago, entry, station

from custom_components.okrweather.coordinator import OKRWeatherLiveCoordinator
from custom_components.okrweather.pressure import sea_level_pressure as contract_msl
from custom_components.okrweather.util import sea_level_pressure

VECTORS = json.loads((Path(__file__).parent / "pressure_vectors.json").read_text())


@pytest.mark.parametrize("case", VECTORS["cases"])
def test_vendored_formula_matches_contract_vectors(case):
    got = contract_msl(case["station_hpa"], case["elevation_m"], case["temperature_c"])
    if case["expected_hpa"] is None:
        assert got is None
    else:
        assert got == pytest.approx(case["expected_hpa"], abs=VECTORS["tolerance_hpa"])


def test_integration_wrapper_rounds_and_never_passes_raw_off_as_msl():
    assert sea_level_pressure(995.2, 176, 8.4) == pytest.approx(1016.64, abs=0.01)
    assert sea_level_pressure(1003.4, 176, None) == pytest.approx(1024.52, abs=0.01)
    # Unknown elevation: unknown, not the station-level value.
    assert sea_level_pressure(990.5, None, 5) is None
    # Elevation 0 really is sea level.
    assert sea_level_pressure(1013.2, 0, 10) == 1013.2
    assert sea_level_pressure(None, 176, 10) is None
    assert sea_level_pressure("x", 176, 10) is None


def _readings(api, temp, minutes_ago):
    api.add("weather-stations", {"is_active"}, [
        {"$id": GOG, "is_active": True, "station_id": "pl-opo-gog-01", "city": "Gogolin", "elevation_m": 169},
    ])
    api.add("station-readings", COLUMNS["station-readings"], [
        {"station_id": GOG, "measured_at": ago(minutes_ago), "air_temperature_c": temp, "air_pressure_hpa": 995.0},
    ])


async def test_live_carries_last_temperature_like_the_portal(api):
    coord = OKRWeatherLiveCoordinator(None, entry(api, [station()]), timedelta(minutes=5))
    _readings(api, 2.0, 60)
    first = (await coord.poll())["stations"][f"sub-{GOG}"]["weather"]
    # Elevation comes from the weather-stations row (169 m), not the subentry.
    assert first["sea_level_pressure_hpa"] == pytest.approx(sea_level_pressure(995.0, 169, 2.0))
    # Night: outdoor temperature NULL, pressure still reported -> reuse 2.0 °C.
    _readings(api, None, 1)
    second = (await coord.poll())["stations"][f"sub-{GOG}"]["weather"]
    assert second["sea_level_pressure_hpa"] == first["sea_level_pressure_hpa"]
    assert second["air_pressure_hpa"] == 995.0  # raw kept for the diagnostic sensor


async def test_live_temperature_carry_expires_after_3_hours(api):
    coord = OKRWeatherLiveCoordinator(None, entry(api, [station()]), timedelta(minutes=5))
    _readings(api, 2.0, 200)
    await coord.poll()
    _readings(api, None, 1)
    data = (await coord.poll())["stations"][f"sub-{GOG}"]["weather"]
    assert data["sea_level_pressure_hpa"] == pytest.approx(sea_level_pressure(995.0, 169, None))
