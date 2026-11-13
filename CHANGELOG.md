# Changelog

User-facing changes per release. Older releases: see the GitHub releases page.

## 2.6.0 (2026-11-13)

One pressure format everywhere: every pressure the integration shows is **reduced to mean sea level** (the value on weather maps, in forecasts and in the Pogoda OKR app).

- **Pressure** sensor and the weather entity's current pressure: always sea level. When the station's elevation is not known yet, they show "unknown" instead of the raw station value.
- **Same numbers as the app.** The reduction uses the same formula as pogodaokr.pl. When a station's outdoor temperature is briefly missing (Gogolin at night), the last temperature from up to 3 hours earlier is used instead of a fixed 15 °C, so the value no longer jumps by 1-2 hPa at night.
- **Station pressure (raw)**: the unreduced station reading stays available as a diagnostic sensor, disabled by default (enable it under the device's Diagnostic section if you need it).
- Entity IDs and history are unchanged; nothing to reconfigure.

## 2.5.0 (2026-11-06)

**Please update.** The Pogoda OKR backend is renaming and removing some of its tables. Version 2.4.1 stops refreshing a station as soon as one table it reads is gone, so station values freeze. 2.5.0 works with the backend before, during and after this change.

- **Station data keeps updating.** Every data source is now read on its own. If one source is missing or fails, only its own values pause; the rest of the station keeps updating, and the integration never turns unavailable because of a single source.
- **Renamed backend tables.** Station readings, the storm tracker and the solar forecast are read from their new tables, with an automatic fallback to the old ones while they still exist. The newest data wins. Nothing to configure.
- **Air quality from Airly.** PM2.5, PM10 and the computed AQI now come from the Airly sensors near the station (Gogolin: the average of 2 sensors). The sensors appear automatically for stations that have an air-quality source. New attributes: the Polish air-quality level (GIOŚ scale) and the CAQI index.
- **Removed sensors (their data no longer exists):**
  - station lightning distance (the stations have no lightning sensor; the storm tracker still reports lightning distance and count),
  - air-quality trend and tracked AQI (no longer produced; the air-trend card stays hidden),
  - CO, NO₂ and NH₃ (no source).

  Their old entities are removed from Home Assistant automatically when you update.
- **Lighter queries.** The latest station reading is searched only within the last 24 hours, and each AI insight only within its freshness window. A station that has not reported for more than a day shows "unknown" instead of frozen values.

After updating: restart Home Assistant. Your API key, stations and settings stay as they are.
