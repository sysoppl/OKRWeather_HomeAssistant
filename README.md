# OKRWeather — Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Home Assistant custom integration for **Pogoda OKR / OKRWeather** — a hyperlocal weather network for Powiat Krapkowicki / Opolski (Opolskie, Poland) with physical sensor stations in Gogolin, Ligota Prószkowska, Zielina and surrounding villages.

The integration talks directly to the OKRWeather Appwrite backend at `api.skydark.pl`. No middleware, no cloud account required for free data.

## Architecture (v2)

One **hub** entry holds the backend connection and the optional premium API key. Each **station** is a *subentry* of that hub — added, removed or extended at any time from the integration page (**Add weather station**) without re-entering credentials. Every station becomes its own device with a weather entity and a full set of sensors.

Three independent polling loops keep traffic minimal and data fresh:

| Loop | Default | What it fetches |
|---|---|---|
| Live | 5 min | Station readings, air quality, lightning, government alerts |
| AI insights | 10 min | The premium AI tables (single batched request per table for all stations) |
| Forecast | 30 min | Hourly + daily forecasts per city |

## Features

### Free tier (no API key required)

- **Weather entity** per station — live measurements merged with hourly, daily and twice-daily forecasts for the city nearest the station. When the station's rain gauge is measuring precipitation, the current condition reflects the *actual* rain, not the forecast.
- **Live sensors** — temperature, apparent temperature, dew point, humidity, pressure, wind speed/gust/direction, max daily gust, precipitation rate, daily precipitation, UV index, solar radiation, light level, UV irradiance, ground temperature, soil moisture, snow depth, vapor pressure deficit, ionizing radiation.
- **Air quality** — PM2.5, PM10, computed US-EPA AQI, CO, NO₂, NH₃ (for stations with an air probe).
- **Weather alerts** — filtered to the station's own alert area (`powiat`), as a count sensor and a binary sensor with full details.
- **Diagnostics** — *Station online* binary sensor (goes off when the station stops reporting) and *Last station update* timestamp.

### Premium tier (API key required)

The key unlocks the **active** AI analysis tables — each exposed with proper `ENUM` sensors (translated states, usable in automations) plus rich attributes including the advisory text in your language (PL/EN, configurable):

- **Comfort Index** — 0–100 score + level enum with per-factor score breakdown
- **AI Radar Analysis** — rain intensity & trend enums, radar rain rate, rain ETA, closest rain distance, 30/60-min rain probability, plus *radar rain* and *rain approaching* binary sensors
- **Storm Tracker** — proximity & intensity enums, storm ETA, lightning count/distance, *storm detected* binary sensor
- **Pressure Alert** — alert level & trend enums, change rate, *pressure alert* binary sensor
- **Frost Alert** — probability, level enum, frost window, *frost alert* binary sensor
- **Solar Forecast** — today's kWh, peak kW, efficiency, production label enum, parsed hourly production curve as attribute
- **Air Quality Trend** — trend enum (waiting for AQ hardware; stays unknown until sensors exist)

Stale AI rows are dropped automatically — if a backend function stops publishing, the entities go `unknown` instead of freezing on old data. If the API key is revoked, Home Assistant starts a re-authentication flow.

## Installation

### HACS (recommended)

1. In HACS, open **Integrations** → top-right **⋮** → **Custom repositories**.
2. Add `https://github.com/sysoppl/OKRWeather_HomeAssistant` with category **Integration**.
3. Install **OKRWeather (Pogoda OKR)** from the list.
4. Restart Home Assistant.

### Manual

Copy `custom_components/okrweather/` into your Home Assistant `config/custom_components/` directory, then restart.

## Configuration

1. **Settings → Devices & Services → Add Integration → OKRWeather**.
2. (Optional) Paste your premium API key. Advanced mode also exposes the endpoint/project fields.
3. Tick the stations you want — all are pre-selected.
4. Later:
   - **Add weather station** on the integration page adds another station.
   - Deleting a station subentry removes its device and entities.
   - **Configure** adjusts the three polling intervals and the advisory language.
   - **Reconfigure** changes the endpoint/project/API key without losing stations.

### Upgrading from v1

Config entries are migrated automatically: each old entry becomes a hub with its station attached as a subentry — entities keep their IDs and history. If you had several v1 entries you'll end up with several hubs; keep one, delete the rest and re-add those stations via **Add weather station**.

## How to get a premium API key

Premium features are part of the OKRWeather subscription tiers (3/6/12-month plans). Sign up at [pogodaokr.pl](https://pogodaokr.pl) and ask support to issue an API key for Home Assistant.

## Entity reference

| Domain | Entity ID pattern | Free / Premium |
|---|---|---|
| `weather` | `weather.<station>` | Free |
| `sensor` | `sensor.<station>_temperature` etc. | Free |
| `sensor` | `sensor.<station>_pm2_5`, `_aqi` etc. | Free (air probe) |
| `sensor` | `sensor.<station>_active_weather_alerts` | Free |
| `binary_sensor` | `binary_sensor.<station>_weather_alert`, `_station_online` | Free |
| `sensor` | `sensor.<station>_comfort_index`, `_comfort_level` | Premium |
| `sensor` | `sensor.<station>_radar_*`, `_rain_probability_*` | Premium |
| `sensor` | `sensor.<station>_storm_*`, `_lightning_*` | Premium |
| `sensor` | `sensor.<station>_pressure_alert_level`, `_pressure_trend` | Premium |
| `sensor` | `sensor.<station>_frost_*` | Premium |
| `sensor` | `sensor.<station>_solar_*` | Premium |
| `sensor` | `sensor.<station>_air_quality_trend` | Premium |
| `binary_sensor` | `_frost_alert`, `_storm_detected`, `_radar_rain`, `_rain_approaching`, `_pressure_alert` | Premium |

Some sensors are disabled by default (ground temperature, soil moisture, snow depth, gas concentrations, radiation, light level, lightning distance) — enable them from the device page if your station reports them.

## Automation ideas

```yaml
# Close the awning when a storm is approaching
trigger:
  - platform: state
    entity_id: binary_sensor.gogolin_rondo_rain_approaching
    to: "on"
condition:
  - condition: numeric_state
    entity_id: sensor.gogolin_rondo_rain_eta
    below: 30
action:
  - service: cover.close_cover
    target: { entity_id: cover.awning }
```

## Languages

UI is translated to English and Polish. AI advisory texts follow the HA language by default and can be forced to PL/EN in the options.

## Troubleshooting

- **"Could not reach the OKRWeather backend"** — check that `api.skydark.pl` resolves and is reachable from your Home Assistant host.
- **Premium sensors stay `unknown`** — either the backend function hasn't published a fresh row (rows older than the per-feature freshness window are ignored), or the station has no data for that feature (e.g. air-quality trend without AQ hardware).
- **Re-authentication keeps appearing** — the API key was revoked or lost its scope; paste a new one or leave blank to drop to the free tier.
- Download **diagnostics** from the integration page when filing an issue — the API key is redacted automatically.

Enable debug logging:

```yaml
logger:
  default: info
  logs:
    custom_components.okrweather: debug
```

## Development

The integration follows the modern (Home Assistant ≥ 2026.3) custom-component patterns:

- Hub entry + **config subentries** for stations (`ConfigSubentryFlow`)
- `runtime_data` with a typed config entry alias (`OKRWeatherConfigEntry`)
- Three `DataUpdateCoordinator`s (live / insights / forecast) with batched queries
- `ENUM` sensors with translated states, `icons.json`, diagnostics, reauth + reconfigure flows
- Automatic v1 → v2 entry migration that moves devices/entities onto subentries
- Pure-aiohttp REST client (no Appwrite SDK)

## License

[MIT](LICENSE)

## Credits

- Data: [Pogoda OKR](https://pogodaokr.pl) — public weather network for Powiat Krapkowicki / Opolski
