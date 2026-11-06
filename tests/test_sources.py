"""TableResolver: rename fallback, newest-wins, caches and station column."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from conftest import COLUMNS, GOG, LPR, ago

from custom_components.okrweather.api import OKRWeatherApiError
from custom_components.okrweather.sources import (
    INSIGHT_SOURCES,
    STATION_READINGS,
    TableResolver,
)

NEW, OLD = "station-readings", "weather-data"


class Clock:
    def __init__(self) -> None:
        self.now = datetime.now(UTC)

    def __call__(self) -> datetime:
        return self.now


def new_row(minutes: float, station: str = GOG, **extra):
    return {"station_id": station, "measured_at": ago(minutes), **extra}


def old_row(minutes: float, station: str = GOG, **extra):
    return {"station": station, "measurementDate": ago(minutes), **extra}


async def latest(resolver: TableResolver, station: str = GOG):
    now = datetime.now(UTC)
    return await resolver.read(
        STATION_READINGS,
        station_id=station,
        since=now - timedelta(hours=24),
        stale_before=now - timedelta(minutes=15),
        limit=1,
    )


async def test_new_only_old_gone_is_cached(api):
    api.add(NEW, COLUMNS[NEW], [new_row(1, air_temperature_c=5.0)])
    resolver = TableResolver(api)

    lookup = await latest(resolver)
    assert lookup.row["air_temperature_c"] == 5.0
    assert resolver.is_gone(OLD)

    api.calls.clear()
    await latest(resolver)
    assert api.tables_called() == [NEW]


async def test_old_only_new_missing(api):
    api.add(OLD, COLUMNS[OLD], [old_row(1, air_temperature_c=4.0)])
    resolver = TableResolver(api)

    lookup = await latest(resolver)
    assert lookup.row["air_temperature_c"] == 4.0
    assert not lookup.failed
    assert resolver.is_gone(NEW)

    api.calls.clear()
    await latest(resolver)
    assert set(api.tables_called()) == {OLD}


async def test_old_only_new_still_empty(api):
    api.add(NEW, COLUMNS[NEW], [])
    api.add(OLD, COLUMNS[OLD], [old_row(1, air_temperature_c=4.0)])
    resolver = TableResolver(api)

    assert (await latest(resolver)).row["air_temperature_c"] == 4.0
    assert not resolver.is_complete(STATION_READINGS, GOG)
    api.calls.clear()
    await latest(resolver)
    assert NEW in api.tables_called() and OLD in api.tables_called()


async def test_both_present_old_newer_wins(api):
    api.add(NEW, COLUMNS[NEW], [new_row(30, air_temperature_c=1.0)])
    api.add(OLD, COLUMNS[OLD], [old_row(1, air_temperature_c=2.0)])
    resolver = TableResolver(api)

    assert (await latest(resolver)).row["air_temperature_c"] == 2.0
    assert not resolver.is_complete(STATION_READINGS, GOG)


async def test_both_present_new_newer_wins_and_marks_complete(api):
    api.add(NEW, COLUMNS[NEW], [new_row(1, air_temperature_c=3.0)])
    api.add(OLD, COLUMNS[OLD], [old_row(30, air_temperature_c=2.0)])
    resolver = TableResolver(api)

    assert (await latest(resolver)).row["air_temperature_c"] == 3.0
    assert resolver.is_complete(STATION_READINGS, GOG)

    api.calls.clear()
    assert (await latest(resolver)).row["air_temperature_c"] == 3.0
    assert api.tables_called() == [NEW]


async def test_dual_write_tie_prefers_new_and_keeps_reading_both(api):
    stamp = ago(1)
    api.add(NEW, COLUMNS[NEW], [{"station_id": GOG, "measured_at": stamp, "air_temperature_c": 7.0}])
    api.add(OLD, COLUMNS[OLD], [{"station": GOG, "measurementDate": stamp, "air_temperature_c": 7.0}])
    resolver = TableResolver(api)

    lookup = await latest(resolver)
    assert lookup.row["$tableId"] == NEW
    # Equal rows prove nothing (a copy looks the same): no shortcut yet.
    assert not resolver.is_complete(STATION_READINGS, GOG)


async def test_complete_source_that_goes_stale_probes_old_again(api):
    api.add(NEW, COLUMNS[NEW], [new_row(1, air_temperature_c=3.0)])
    api.add(OLD, COLUMNS[OLD], [old_row(10, air_temperature_c=2.0)])
    resolver = TableResolver(api)
    await latest(resolver)
    assert resolver.is_complete(STATION_READINGS, GOG)

    # The writer moves back to the old table: new stops, old continues.
    api.tables[NEW]["rows"][0]["measured_at"] = ago(60)
    api.tables[OLD]["rows"][0]["measurementDate"] = ago(0.5)
    api.calls.clear()
    lookup = await latest(resolver)
    assert lookup.row["air_temperature_c"] == 2.0
    assert api.tables_called().count(OLD) >= 1
    assert not resolver.is_complete(STATION_READINGS, GOG)


async def test_gone_and_complete_are_rechecked_daily(api):
    clock = Clock()
    api.add(NEW, COLUMNS[NEW], [new_row(1)])
    resolver = TableResolver(api, clock=clock)
    await latest(resolver)
    assert resolver.is_gone(OLD)

    clock.now += timedelta(hours=25)
    api.calls.clear()
    await latest(resolver)
    assert OLD in api.tables_called()


async def test_station_column_detection_and_cache(api):
    clock = Clock()
    api.add(NEW, COLUMNS[NEW], [new_row(2, air_temperature_c=1.0)])
    api.add(OLD, COLUMNS[OLD], [old_row(1, air_temperature_c=2.0)])
    resolver = TableResolver(api, clock=clock)

    assert (await latest(resolver)).row["air_temperature_c"] == 2.0
    attrs = [q[0]["attribute"] for t, q in api.calls if t == OLD]
    assert attrs == ["station_id", "station"]  # one probe, then the relationship

    api.calls.clear()
    await latest(resolver)
    assert [q[0]["attribute"] for t, q in api.calls if t == OLD] == ["station"]
    assert [q[0]["attribute"] for t, q in api.calls if t == NEW] == ["station_id"]

    clock.now += timedelta(hours=25)
    api.calls.clear()
    await latest(resolver)
    assert [q[0]["attribute"] for t, q in api.calls if t == OLD] == ["station_id", "station"]


async def test_station_column_rechecked_after_error(api):
    api.add(NEW, COLUMNS[NEW], [])
    api.add(OLD, COLUMNS[OLD], [old_row(1)])
    resolver = TableResolver(api)
    await latest(resolver)
    api.fail[OLD] = 503
    await latest(resolver)
    del api.fail[OLD]
    api.calls.clear()
    await latest(resolver)
    assert [q[0]["attribute"] for t, q in api.calls if t == OLD] == ["station_id", "station"]


async def test_station_filter_is_per_station(api):
    api.add(NEW, COLUMNS[NEW], [new_row(1, GOG, air_temperature_c=1.0), new_row(1, LPR, air_temperature_c=9.0)])
    resolver = TableResolver(api)
    assert (await latest(resolver, LPR)).row["air_temperature_c"] == 9.0
    assert (await latest(resolver, GOG)).row["air_temperature_c"] == 1.0


async def test_latest_query_is_time_bounded_newest_first_limit_1(api):
    api.add(NEW, COLUMNS[NEW], [new_row(1)])
    resolver = TableResolver(api)
    await latest(resolver)
    _, queries = next(c for c in api.calls if c[0] == NEW)
    methods = [(q["method"], q.get("attribute")) for q in queries]
    assert methods == [
        ("equal", "station_id"),
        ("greaterThanEqual", "measured_at"),
        ("orderDesc", "measured_at"),
        ("limit", None),
    ]
    assert queries[-1]["values"] == [1]


async def test_error_skips_piece_and_logs_once(api, caplog):
    api.add(OLD, COLUMNS[OLD], [old_row(1)])
    api.fail[NEW] = 500
    api.fail[OLD] = 500
    resolver = TableResolver(api)
    with caplog.at_level(logging.DEBUG):
        first = await latest(resolver)
        second = await latest(resolver)
    assert first.failed and second.failed
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 2  # once per table, not once per poll


async def test_one_candidate_failing_still_answers(api):
    api.add(OLD, COLUMNS[OLD], [old_row(1, air_temperature_c=2.0)])
    api.add(NEW, COLUMNS[NEW], [])
    api.fail[NEW] = 502
    lookup = await latest(TableResolver(api))
    assert not lookup.failed
    assert lookup.row["air_temperature_c"] == 2.0


async def test_every_candidate_gone_is_no_data_not_failure(api):
    lookup = await latest(TableResolver(api))
    assert lookup.row is None and not lookup.failed and not lookup.errors


async def test_unexpected_exception_is_contained(api):
    api.fail[NEW] = RuntimeError("bug")
    api.add(OLD, COLUMNS[OLD], [old_row(1)])
    lookup = await latest(TableResolver(api))
    assert lookup.row is not None
    assert isinstance(lookup.errors[0], OKRWeatherApiError)


async def test_insight_merge_newest_per_station(api):
    now = datetime.now(UTC)
    api.add("storm-alerts", COLUMNS["storm-alerts"], [
        {"station_id": GOG, "proximity_level": "new", "analyzed_at": ago(2)},
    ])
    api.add("storm-tracker", COLUMNS["storm-tracker"], [
        {"station_id": GOG, "station": GOG, "proximity_level": "old", "analyzed_at": ago(1)},
        {"station_id": LPR, "station": LPR, "proximity_level": "old-lpr", "analyzed_at": ago(3)},
    ])
    lookup = await TableResolver(api).read(
        INSIGHT_SOURCES["storm_tracker"], since=now - timedelta(minutes=30), limit=12
    )
    assert [r["proximity_level"] for r in lookup.rows] == ["old", "new", "old-lpr"]
