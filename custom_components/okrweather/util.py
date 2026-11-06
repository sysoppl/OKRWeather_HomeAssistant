"""Small shared helpers for OKRWeather."""

from __future__ import annotations

import math
import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .data import StationConfig


def parse_iso(value: Any) -> datetime | None:
    """Parse an ISO-8601 string; tolerate trailing Z and naive datetimes."""
    if not isinstance(value, str) or not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def reading_time(row: dict[str, Any]) -> datetime | None:
    """Observation time of a station reading.

    ``measured_at`` in station-readings, ``measurementDate`` in the old
    weather-data table, ``$createdAt`` as the last resort.
    """
    return parse_iso(
        row.get("measured_at") or row.get("measurementDate") or row.get("$createdAt")
    )


def age_minutes(value: Any, *, now: datetime | None = None) -> float | None:
    """Age of an ISO timestamp in minutes, or None if unparseable."""
    dt = parse_iso(value)
    if dt is None:
        return None
    now = now or datetime.now(UTC)
    return (now - dt).total_seconds() / 60


def normalize_enum(value: Any) -> str | None:
    """Normalise a backend label to lower_snake_case ("Very Poor" → "very_poor")."""
    if not isinstance(value, str) or not value.strip():
        return None
    return re.sub(r"[\s\-]+", "_", value.strip().lower())


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres."""
    r = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(d_lon / 2) ** 2
    )
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def row_station_id(row: dict[str, Any]) -> str | None:
    """Extract the station reference from an AI-table row.

    Prefers the ``station`` relationship (expanded object or plain id string),
    then falls back to the ``station_id`` business-key column — mirroring the
    portal frontend's resolveStationId().
    """
    station = row.get("station")
    if isinstance(station, dict) and station.get("$id"):
        return str(station["$id"])
    if isinstance(station, str) and station:
        return station
    if row.get("station_id"):
        return str(row["station_id"])
    return None


def row_matches_station(row: dict[str, Any], station: StationConfig) -> bool:
    """Whether an AI-table row belongs to the given station."""
    ref = row_station_id(row)
    if ref is not None and ref in (station.appwrite_id, station.station_key):
        return True
    name = row.get("station_name")
    return bool(
        isinstance(name, str)
        and name
        and name.strip().lower() == station.name.strip().lower()
    )


def match_city(
    station: StationConfig,
    cities: dict[str, dict[str, Any]],
) -> str | None:
    """Pick the city (from ``{city_id: {"name", "lat", "lon"}}``) for a station.

    Tries the station's ``city``, ``name`` and ``slug`` against each city's
    id and display name — exact, id-prefix, and bidirectional containment
    (mirrors the portal's fuzzy matching, so "Gogolin Rondo" still finds
    "gogolin_pl"). Radar rows carry no coordinates, so the name pass must
    catch those; forecast cities additionally fall back to nearest-by-distance.
    """
    if not cities:
        return None

    for candidate in (station.city, station.name, station.slug):
        wanted = (candidate or "").strip().lower()
        if len(wanted) < 3:
            continue
        slug_wanted = _slugify(wanted)
        for city_id, info in cities.items():
            cid = city_id.lower()
            cname = str(info.get("name") or "").strip().lower()
            if (
                wanted in (cid, cname)
                or cid.startswith(slug_wanted)
                or (len(cname) >= 3 and (cname in wanted or wanted in cname))
            ):
                return city_id

    if station.latitude is None or station.longitude is None:
        return None
    located = {
        cid: info
        for cid, info in cities.items()
        if isinstance(info.get("lat"), (int, float))
        and isinstance(info.get("lon"), (int, float))
    }
    if not located:
        return None
    return min(
        located,
        key=lambda cid: haversine_km(
            station.latitude,  # type: ignore[arg-type]
            station.longitude,  # type: ignore[arg-type]
            float(located[cid]["lat"]),
            float(located[cid]["lon"]),
        ),
    )


def _slugify(value: str) -> str:
    """ASCII-ish slug used to compare city names with city ids."""
    replacements = str.maketrans("ąćęłńóśźż -", "acelnoszz__")
    return value.lower().translate(replacements)


def sea_level_pressure(
    pressure_hpa: Any,
    elevation_m: float | None,
    temperature_c: Any,
) -> float | None:
    """Reduce station pressure to sea level (temperature-compensated).

    Standard barometric reduction: P0 = P · (1 − L·h / (T + L·h + 273.15))^−5.257
    with L = 0.0065 K/m. Falls back to the ISA temperature (15 °C) when the
    station temperature is missing, and to the raw value when the station
    has no elevation on record.
    """
    if not isinstance(pressure_hpa, (int, float)):
        return None
    if not isinstance(elevation_m, (int, float)) or elevation_m == 0:
        return round(float(pressure_hpa), 2)
    temp = float(temperature_c) if isinstance(temperature_c, (int, float)) else 15.0
    lapse = 0.0065 * float(elevation_m)
    return round(
        float(pressure_hpa) * (1 - lapse / (temp + lapse + 273.15)) ** -5.257,
        2,
    )


def compute_epa_aqi(pm25: float | None) -> int | None:
    """US EPA AQI from a PM2.5 concentration (µg/m³).

    Same breakpoints the OKRWeather portal uses for its AQI figure.
    """
    if pm25 is None or pm25 < 0:
        return None
    breakpoints = (
        (0.0, 12.0, 0, 50),
        (12.1, 35.4, 51, 100),
        (35.5, 55.4, 101, 150),
        (55.5, 150.4, 151, 200),
        (150.5, 250.4, 201, 300),
        (250.5, 350.4, 301, 400),
        (350.5, 500.4, 401, 500),
    )
    for c_lo, c_hi, a_lo, a_hi in breakpoints:
        if pm25 <= c_hi:
            return round((a_hi - a_lo) / (c_hi - c_lo) * (max(pm25, c_lo) - c_lo) + a_lo)
    return 500
