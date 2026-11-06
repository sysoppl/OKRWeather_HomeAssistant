"""Live and insights coordinators: per-table isolation in every backend state."""

from __future__ import annotations

from datetime import timedelta

import pytest
from conftest import (
    COLUMNS,
    GOG,
    LPR,
    ConfigEntryAuthFailed,
    UpdateFailed,
    ago,
    entry,
    station,
)

from custom_components.okrweather.coordinator import (
    OKRWeatherInsightsCoordinator,
    OKRWeatherLiveCoordinator,
)

STATIONS = [station(GOG, "pl-opo-gog-01", "Gogolin"), station(LPR, "pl-opo-lpr-01", "Lipno")]
DELETED = {"air-quality-data", "lightning-data", "air-quality-trends"}
LIVE_TABLES = ["station-readings", "weather-data", "air-quality-readings", "weather-alerts"]
INSIGHT_TABLES = [
    "comfort-index", "storm-alerts", "storm-tracker", "pressure-alerts",
    "frost-alerts", "solar-forecasts", "solar-forecast", "radar-status",
]


def seed_live(api, *, new=True, old=True):
    api.add("weather-stations", {"is_active"}, [
        {"$id": GOG, "is_active": True, "station_id": "pl-opo-gog-01", "city": "Gogolin"},
        {"$id": LPR, "is_active": True, "station_id": "pl-opo-lpr-01", "city": "Lipno"},
    ])
    if new:
        api.add("station-readings", COLUMNS["station-readings"], [
            {"station_id": GOG, "measured_at": ago(1), "air_temperature_c": 6.0, "air_pressure_hpa": 1000.0},
            {"station_id": LPR, "measured_at": ago(1), "air_temperature_c": 8.0, "air_pressure_hpa": 1001.0},
        ])
    if old:
        api.add("weather-data", COLUMNS["weather-data"], [
            {"station": GOG, "measurementDate": ago(1), "air_temperature_c": 6.0, "air_pressure_hpa": 1000.0},
            {"station": LPR, "measurementDate": ago(1), "air_temperature_c": 8.0, "air_pressure_hpa": 1001.0},
        ])
    api.add("air-quality-readings", COLUMNS["air-quality-readings"], [
        {"installation_id": "gogolin-avg", "station_id": GOG, "kind": "current", "source": "aggregate",
         "till_at": ago(20), "pm25": 18.8, "pm10": 25.1, "gios_level": 1, "gios_level_name": "Dobry",
         "qc_status": "suspect", "members_used": "2723"},
        {"installation_id": "2723", "station_id": GOG, "kind": "current", "source": "airly-api",
         "till_at": ago(10), "pm25": 99.0, "pm10": 99.0, "qc_status": "ok"},
        {"installation_id": "gogolin-avg", "station_id": GOG, "kind": "hourly", "source": "aggregate",
         "till_at": ago(5), "pm25": 50.0, "pm10": 60.0, "qc_status": "ok"},
    ])
    api.add("weather-alerts", COLUMNS["weather-alerts"], [
        {"status": "active", "expirationTime": ago(-60), "locationId": "loc-1", "alertTitle": "Wiatr"},
    ])


def seed_insights(api, *, new=True, old=True):
    for t in ("comfort-index", "pressure-alerts", "frost-alerts"):
        api.add(t, COLUMNS[t], [
            {"station_id": s, "station": s, "analyzed_at": ago(2)} for s in (GOG, LPR)
        ])
    if new:
        api.add("storm-alerts", COLUMNS["storm-alerts"], [
            {"station_id": s, "proximity_level": "none", "analyzed_at": ago(2)} for s in (GOG, LPR)
        ])
        api.add("solar-forecasts", COLUMNS["solar-forecasts"], [
            {"station_id": s, "total_kwh": 1.5, "analyzed_at": ago(2)} for s in (GOG, LPR)
        ])
    if old:
        api.add("storm-tracker", COLUMNS["storm-tracker"], [
            {"station_id": s, "station": s, "proximity_level": "distant", "analyzed_at": ago(4)} for s in (GOG, LPR)
        ])
        api.add("solar-forecast", COLUMNS["solar-forecast"], [
            {"station_id": s, "station": s, "total_kwh": 0.5, "analyzed_at": ago(4)} for s in (GOG, LPR)
        ])
    api.add("radar-status", COLUMNS["radar-status"], [
        {"city_id": "gogolin_pl", "city_name": "Gogolin", "intensity": "none", "analyzed_at": ago(3)},
    ])


def live(api):
    return OKRWeatherLiveCoordinator(None, entry(api, STATIONS), timedelta(minutes=5))


def insights(api):
    return OKRWeatherInsightsCoordinator(None, entry(api, STATIONS), timedelta(minutes=10))


def gog(data):
    return data["stations"][f"sub-{GOG}"]


# ── Live ────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("missing", LIVE_TABLES)
async def test_live_any_table_404_never_fails_the_slice(api, missing):
    seed_live(api)
    del api.tables[missing]
    data = await live(api).poll()
    g = gog(data)
    if missing != "weather-alerts":
        assert g["alerts"]
    if missing != "air-quality-readings":
        assert g["air"]["pm25"] == 18.8
    else:
        assert g["air"] is None
    # Weather survives either rename state (only one of the two is missing).
    assert g["weather"]["air_temperature_c"] == 6.0
    assert g["weather"]["sea_level_pressure_hpa"] is not None


async def test_live_both_weather_tables_gone_is_unknown_not_unavailable(api):
    seed_live(api, new=False, old=False)
    data = await live(api).poll()
    assert gog(data)["weather"] is None
    assert gog(data)["air"] is not None


async def test_live_never_requests_deleted_tables(api):
    seed_live(api)
    coord = live(api)
    await coord.poll()
    await coord.poll()
    assert DELETED.isdisjoint(api.tables_called())


async def test_live_air_quality_contract(api):
    seed_live(api)
    coord = live(api)
    air = gog(await coord.poll())["air"]
    assert air["installation_id"] == "gogolin-avg" and air["kind"] == "current"
    # LPR has no air-quality source.
    assert (await coord.poll())["stations"][f"sub-{LPR}"]["air"] is None

    api.tables["air-quality-readings"]["rows"][0]["qc_status"] = "offline"
    assert gog(await coord.poll())["air"] is None
    api.tables["air-quality-readings"]["rows"][0].update(qc_status="ok", pm25=None, pm10=None)
    assert gog(await coord.poll())["air"] is None
    api.tables["air-quality-readings"]["rows"][0].update(pm25=5.0, till_at=ago(180))
    assert gog(await coord.poll())["air"] is None


async def test_live_new_only_and_old_only(api):
    seed_live(api, old=False)
    assert gog(await live(api).poll())["weather"]["$tableId"] == "station-readings"
    api2 = type(api)()
    seed_live(api2, new=False)
    assert gog(await live(api2).poll())["weather"]["$tableId"] == "weather-data"


async def test_live_transient_error_keeps_previous_piece(api):
    seed_live(api)
    coord = live(api)
    await coord.poll()
    api.fail["station-readings"] = 503
    api.fail["weather-data"] = 503
    data = await coord.poll()
    assert gog(data)["weather"]["air_temperature_c"] == 6.0
    assert gog(data)["air"]["pm25"] == 18.8


async def test_live_everything_unreachable_raises(api, network_down):
    seed_live(api)
    for t in [*LIVE_TABLES, "weather-stations"]:
        api.fail[t] = network_down
    with pytest.raises(UpdateFailed):
        await live(api).poll()


async def test_live_wrong_project_points_at_reconfigure(api):
    seed_live(api)
    for t in [*LIVE_TABLES, "weather-stations"]:
        api.fail[t] = 401
    with pytest.raises(UpdateFailed, match="reconfigure"):
        await live(api).poll()


async def test_live_one_table_401_is_skipped(api):
    seed_live(api)
    api.fail["air-quality-readings"] = 401
    data = await live(api).poll()
    assert gog(data)["air"] is None and gog(data)["weather"] is not None


async def test_live_request_count_after_transition(api):
    seed_live(api, old=False)
    coord = live(api)
    await coord.poll()
    api.calls.clear()
    await coord.poll()
    # alerts + per station (readings + air); the gone old table is not retried.
    assert len(api.calls) == 1 + 2 * len(STATIONS)


# ── Insights ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("missing", INSIGHT_TABLES)
async def test_insights_any_table_404_skips_only_that_section(api, missing):
    seed_insights(api)
    del api.tables[missing]
    data = await insights(api).poll()
    g = gog(data)
    for section in ("comfort_index", "pressure_alert", "frost_alert", "storm_tracker", "solar_forecast"):
        expect_none = {
            "comfort-index": "comfort_index",
            "pressure-alerts": "pressure_alert",
            "frost-alerts": "frost_alert",
        }.get(missing) == section
        assert (g[section] is None) == expect_none, section
    assert (g["radar"] is None) == (missing == "radar-status")


async def test_insights_newest_wins_between_old_and_new(api):
    seed_insights(api)
    coord = insights(api)
    g = gog(await coord.poll())
    assert g["storm_tracker"]["$tableId"] == "storm-alerts"   # new is newer
    assert g["solar_forecast"]["total_kwh"] == 1.5

    # The old writer is ahead (not switched yet): the old table wins.
    api2 = type(api)()
    seed_insights(api2)
    for row in api2.tables["storm-tracker"]["rows"]:
        row["analyzed_at"] = ago(0.5)
    g2 = gog(await insights(api2).poll())
    assert g2["storm_tracker"]["$tableId"] == "storm-tracker"


async def test_insights_relationship_and_station_id_rows_both_match(api):
    seed_insights(api, new=False)
    api.add("storm-alerts", COLUMNS["storm-alerts"], [
        {"station_id": LPR, "proximity_level": "none", "analyzed_at": ago(1)},
    ])
    api.tables["storm-tracker"]["rows"] = [
        {"$id": "x", "$tableId": "storm-tracker", "$createdAt": ago(0),
         "station": GOG, "proximity_level": "distant", "analyzed_at": ago(1)},
    ]
    data = await insights(api).poll()
    assert gog(data)["storm_tracker"]["proximity_level"] == "distant"
    assert data["stations"][f"sub-{LPR}"]["storm_tracker"]["proximity_level"] == "none"


async def test_insights_bad_key_everywhere_asks_for_reauth(api):
    seed_insights(api)
    for t in INSIGHT_TABLES:
        api.fail[t] = 401
    with pytest.raises(ConfigEntryAuthFailed):
        await insights(api).poll()


async def test_insights_one_table_401_or_403_is_skipped(api):
    seed_insights(api)
    api.fail["comfort-index"] = 401
    api.fail["frost-alerts"] = 403
    g = gog(await insights(api).poll())
    assert g["comfort_index"] is None and g["frost_alert"] is None
    assert g["pressure_alert"] is not None


async def test_insights_never_requests_deleted_tables_and_count(api):
    seed_insights(api, old=False)
    coord = insights(api)
    await coord.poll()
    assert DELETED.isdisjoint(api.tables_called())
    api.calls.clear()
    await coord.poll()
    assert len(api.calls) == 6  # 5 sections + radar; gone old ids are skipped
