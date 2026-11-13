"""OKRWeather pressure contract (2026-11-13): everything shown to people is pressure reduced to mean
sea level. Same formula as the portal (src/lib/pressure.ts):
    P0 = P * (1 - 0.0065 h / (T + 0.0065 h + 273.15)) ** -5.257
Canonical copy: _audit/templates/pressure/ (vectors.json). Do not edit locally."""
import math


def sea_level_pressure(station_hpa, elevation_m, temperature_c=None):
    if station_hpa is None or not math.isfinite(station_hpa) or station_hpa <= 0:
        return None
    if elevation_m is None or not math.isfinite(elevation_m) or elevation_m <= 0:
        return station_hpa
    t_k = temperature_c + 273.15 if temperature_c is not None and math.isfinite(temperature_c) else 288.15
    denom = t_k + 0.0065 * elevation_m
    if denom <= 0:
        return station_hpa
    return station_hpa * (1 - (0.0065 * elevation_m) / denom) ** -5.257
