"""Table reads that survive backend table renames and removals.

The backend renames some tables (for example ``weather-data`` became
``station-readings``). During the switch the old id, the new id or both may
exist, and the new table may still be filling up. Every logical source
therefore lists its candidate tables, preferred (new) id first, and all reads
go through :class:`TableResolver`:

* Every candidate that still exists is read with a time-bounded,
  newest-first query, and the newest row wins.
* A 404 marks a table as gone. An answer where the new table is strictly
  newer than every old one marks the source as complete. Both stop the extra
  request until the daily recheck. If a complete source later looks stale,
  the old ids are probed again in the same poll.
* The station filter uses the plain ``station_id`` column or the legacy
  ``station`` relationship, whichever the table has. The choice is learned
  from the first answer and rechecked daily or after an error.

Nothing escapes as an exception: a failing table is logged once and only
that piece is skipped, so one table can never black out a station or the
whole integration.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from .api import (
    OKRWeatherApiError,
    OKRWeatherApiNotFoundError,
    OKRWeatherApiPermissionError,
    _q,
)
from .const import (
    INSIGHT_TABLES,
    LOGGER,
    SECTION_RADAR,
    TABLE_AIR_QUALITY,
    TABLE_ALERTS,
    TABLE_RADAR_STATUS,
    TABLE_STATION_READINGS,
    TABLE_STATION_READINGS_OLD,
)
from .util import parse_iso

if TYPE_CHECKING:
    from .api import OKRWeatherApiClient

# How long a learned fact (table gone, new table complete, station column)
# is trusted before it is checked again.
RECHECK_AFTER = timedelta(hours=24)

# Station filter columns, in the order they are tried.
STATION_ATTRS: tuple[str, ...] = ("station_id", "station")

_EPOCH = datetime.min.replace(tzinfo=UTC)


@dataclass(frozen=True)
class Table:
    """One candidate table and the time column it is ordered by."""

    id: str
    time_attr: str


@dataclass(frozen=True)
class Source:
    """A logical data source: candidate tables, preferred (new) id first."""

    name: str
    tables: tuple[Table, ...]


@dataclass
class Lookup:
    """Result of one source read. Never raised, always returned."""

    rows: list[dict[str, Any]] = field(default_factory=list)
    # At least one candidate answered (a 404 counts as "no such table", not
    # as an answer). rows may be empty even when answered.
    answered: bool = False
    # Non-404 failures (timeouts, 5xx, 401/403, bad queries).
    errors: list[OKRWeatherApiError] = field(default_factory=list)

    @property
    def row(self) -> dict[str, Any] | None:
        """The newest row, or None."""
        return self.rows[0] if self.rows else None

    @property
    def failed(self) -> bool:
        """Every reachable candidate failed: callers keep their previous data."""
        return bool(self.errors) and not self.answered


# ── Sources used by the coordinators ────────────────────────────────────────

STATION_READINGS = Source(
    "station_readings",
    (
        Table(TABLE_STATION_READINGS, "measured_at"),
        Table(TABLE_STATION_READINGS_OLD, "measurementDate"),
    ),
)
AIR_QUALITY = Source("air_quality", (Table(TABLE_AIR_QUALITY, "till_at"),))
ALERTS = Source("alerts", (Table(TABLE_ALERTS, "$createdAt"),))
RADAR = Source(SECTION_RADAR, (Table(TABLE_RADAR_STATUS, "analyzed_at"),))
INSIGHT_SOURCES: dict[str, Source] = {
    section: Source(section, tuple(Table(t, "analyzed_at") for t in tables))
    for section, tables in INSIGHT_TABLES.items()
}


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _row_time(row: dict[str, Any], table: Table) -> datetime:
    return (
        parse_iso(row.get(table.time_attr))
        or parse_iso(row.get("$createdAt"))
        or _EPOCH
    )


class TableResolver:
    """Reads sources with per-table isolation and rename fallback.

    One instance lives per coordinator, so its caches last for the config
    entry's session and are rebuilt on reload.
    """

    def __init__(
        self,
        client: OKRWeatherApiClient,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._client = client
        self._clock = clock or (lambda: datetime.now(UTC))
        self._gone: dict[str, datetime] = {}
        self._complete: dict[tuple[str, str | None], datetime] = {}
        self._station_attr: dict[str, tuple[str, datetime]] = {}
        self._failing: set[str] = set()

    # ── Cache helpers ───────────────────────────────────────────────────────

    def _known(self, cache: dict[Any, datetime], key: Any) -> bool:
        seen = cache.get(key)
        if seen is None:
            return False
        if self._clock() - seen >= RECHECK_AFTER:
            del cache[key]
            return False
        return True

    def is_gone(self, table_id: str) -> bool:
        """Whether the table answered 404 within the recheck window."""
        return self._known(self._gone, table_id)

    def is_complete(self, source: Source, station_id: str | None = None) -> bool:
        """Whether the preferred table was proven current for this read."""
        return self._known(self._complete, (source.name, station_id))

    # ── Public read ─────────────────────────────────────────────────────────

    async def read(
        self,
        source: Source,
        *,
        limit: int,
        since: datetime | None = None,
        station_id: str | None = None,
        extra: Sequence[str] = (),
        stale_before: datetime | None = None,
    ) -> Lookup:
        """Read the newest rows of a source; see the module docstring.

        ``since`` bounds the time column from below. ``stale_before`` (default:
        ``since``) is the age past which a complete source's preferred table
        looks stale and the old ids are probed again.
        """
        key = (source.name, station_id)
        preferred = source.tables[0]
        tables = [t for t in source.tables if not self.is_gone(t.id)]
        if not tables:
            return Lookup()  # every candidate is gone: no data, not an error

        shortcut = tables[0] is preferred and self._known(self._complete, key)
        batch = tables[:1] if shortcut else tables
        results = await self._read_all(batch, limit, since, station_id, extra)

        if shortcut:
            first = results[0]
            threshold = stale_before or since
            newest = (
                _row_time(first[0], preferred)
                if isinstance(first, list) and first
                else None
            )
            if newest is None or (threshold is not None and newest < threshold):
                # The new table looks stale: drop the shortcut and probe the
                # old ids in this same poll.
                self._complete.pop(key, None)
                rest = tables[1:]
                if rest:
                    results += await self._read_all(rest, limit, since, station_id, extra)
                    batch = tables

        lookup = Lookup()
        merged: list[tuple[datetime, int, dict[str, Any]]] = []
        newest_by_table: dict[str, datetime | None] = {}
        for order, (table, result) in enumerate(zip(batch, results, strict=True)):
            if isinstance(result, OKRWeatherApiNotFoundError):
                self._mark_gone(table)
                continue
            if isinstance(result, OKRWeatherApiError):
                self._note_error(table, result)
                lookup.errors.append(result)
                continue
            self._note_ok(table)
            lookup.answered = True
            newest_by_table[table.id] = _row_time(result[0], table) if result else None
            merged.extend((_row_time(row, table), order, row) for row in result)

        # Newest first; on equal times the preferred (new) table wins.
        merged.sort(key=lambda item: (-item[0].timestamp(), item[1]))
        lookup.rows = [row for _, _, row in merged]

        self._update_complete(source, key, batch, newest_by_table)
        return lookup

    # ── Internals ───────────────────────────────────────────────────────────

    def _update_complete(
        self,
        source: Source,
        key: tuple[str, str | None],
        batch: list[Table],
        newest_by_table: dict[str, datetime | None],
    ) -> None:
        """Mark the source complete once the new table is strictly ahead."""
        preferred = source.tables[0]
        if len(source.tables) < 2 or preferred not in batch:
            return
        new_newest = newest_by_table.get(preferred.id)
        if new_newest is None:
            return
        for table in source.tables[1:]:
            if self.is_gone(table.id):
                continue
            if table.id not in newest_by_table:
                return  # not read this poll or failed: nothing proven
            old_newest = newest_by_table[table.id]
            if old_newest is not None and old_newest >= new_newest:
                return  # old is as new or newer: keep reading both
        if key not in self._complete:
            LOGGER.debug(
                "Source '%s' (%s): table '%s' is current; old ids are skipped "
                "until the daily recheck",
                source.name,
                key[1] or "all stations",
                preferred.id,
            )
        self._complete[key] = self._clock()

    async def _read_all(
        self,
        tables: Sequence[Table],
        limit: int,
        since: datetime | None,
        station_id: str | None,
        extra: Sequence[str],
    ) -> list[Any]:
        results = await asyncio.gather(
            *(self._read_table(t, limit, since, station_id, extra) for t in tables),
            return_exceptions=True,
        )
        out: list[Any] = []
        for result in results:
            if isinstance(result, BaseException) and not isinstance(result, Exception):
                raise result  # cancellation and friends must propagate
            if isinstance(result, Exception) and not isinstance(result, OKRWeatherApiError):
                result = OKRWeatherApiError(f"Unexpected error: {result!r}")
            out.append(result)
        return out

    async def _read_table(
        self,
        table: Table,
        limit: int,
        since: datetime | None,
        station_id: str | None,
        extra: Sequence[str],
    ) -> list[dict[str, Any]]:
        base = list(extra)
        if since is not None:
            base.append(_q("greaterThanEqual", table.time_attr, _iso(since)))
        base += [_q("orderDesc", table.time_attr), _q("limit", values=limit)]
        if station_id is None:
            return await self._client.rows(table.id, base)

        cached = self._station_attr.get(table.id)
        if cached is not None and self._clock() - cached[1] >= RECHECK_AFTER:
            cached = None
        attrs = list(STATION_ATTRS)
        if cached is not None:
            attrs.remove(cached[0])
            attrs.insert(0, cached[0])
        for attr in attrs:
            try:
                rows = await self._client.rows(
                    table.id, [_q("equal", attr, [station_id]), *base]
                )
            except OKRWeatherApiError as err:
                if err.unknown_attribute(attr):
                    continue  # this table has the other station column
                self._station_attr.pop(table.id, None)  # recheck after errors
                raise
            if cached is None or cached[0] != attr:
                self._station_attr[table.id] = (attr, self._clock())
            return rows
        self._station_attr.pop(table.id, None)
        raise OKRWeatherApiError(
            f"Table '{table.id}' has no station column ({', '.join(STATION_ATTRS)})",
            status=400,
        )

    def _mark_gone(self, table: Table) -> None:
        if table.id not in self._gone:
            LOGGER.debug(
                "Table '%s' does not exist (renamed or removed on the backend); "
                "skipping it, next check in 24 h",
                table.id,
            )
        self._gone[table.id] = self._clock()
        self._failing.discard(table.id)
        self._station_attr.pop(table.id, None)

    def _note_error(self, table: Table, err: OKRWeatherApiError) -> None:
        if table.id in self._failing:
            LOGGER.debug("Reading table '%s' still fails: %s", table.id, err)
            return
        self._failing.add(table.id)
        if isinstance(err, OKRWeatherApiPermissionError):
            LOGGER.warning(
                "API key lacks access to table '%s'; its entities stay unknown "
                "until access is granted: %s",
                table.id,
                err,
            )
        else:
            LOGGER.warning(
                "Reading table '%s' failed; skipping it (previous values are "
                "kept) until it answers again: %s",
                table.id,
                err,
            )

    def _note_ok(self, table: Table) -> None:
        if table.id in self._failing:
            self._failing.discard(table.id)
            LOGGER.info("Reading table '%s' works again", table.id)
