> Model and implementation notes moved here from the README on 2026-11-06. Operations (schedule, deploy, configuration) are in `README.md`, which takes precedence where the two differ.

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
| Live | 5 min | Station readings, measured air quality (Airly), government alerts |
| AI insights | 10 min | The premium AI tables (single batched request per table for all stations) |
| Forecast | 30 min | Hourly + daily forecasts per city |

## Features

### Free tier (no API key required)

- **Weather entity** per station — live measurements merged with hourly, daily and twice-daily forecasts for the city nearest the station. When the station's rain gauge is measuring precipitation, the current condition reflects the *actual* rain, not the forecast.
- **Live sensors** — temperature, apparent temperature, dew point, humidity, pressure (reduced to mean sea level using the station's elevation from `weather-stations` and its air temperature, carried up to 3 h when missing — same formula as the portal; the raw station-level reading is a diagnostic, disabled-by-default *Station pressure (raw)* sensor), wind speed/gust/direction, max daily gust, precipitation rate, daily precipitation, UV index, solar radiation, light level, UV irradiance, ground temperature, soil moisture, snow depth, vapor pressure deficit, ionizing radiation.
- **Air quality** — PM2.5, PM10 and a computed US-EPA AQI, measured by nearby Airly sensors (Gogolin: the average of 2 sensors). Created only for stations with an air-quality source; attributes carry the Polish air-quality level (GIOŚ scale) and the CAQI index. Dane: Airly.
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
| `sensor` | `sensor.<station>_pm2_5`, `_pm10`, `_aqi` | Free (stations with an air-quality source) |
| `sensor` | `sensor.<station>_active_weather_alerts` | Free |
| `binary_sensor` | `binary_sensor.<station>_weather_alert`, `_station_online` | Free |
| `sensor` | `sensor.<station>_comfort_index`, `_comfort_level` | Premium |
| `sensor` | `sensor.<station>_radar_*`, `_rain_probability_*` | Premium |
| `sensor` | `sensor.<station>_storm_*`, `_lightning_*` | Premium |
| `sensor` | `sensor.<station>_pressure_alert_level`, `_pressure_trend` | Premium |
| `sensor` | `sensor.<station>_frost_*` | Premium |
| `sensor` | `sensor.<station>_solar_*` | Premium |
| `binary_sensor` | `_frost_alert`, `_storm_detected`, `_radar_rain`, `_rain_approaching`, `_pressure_alert` | Premium |

Some sensors are disabled by default (ground temperature, soil moisture, snow depth, radiation, light level) — enable them from the device page if your station reports them.

## Dashboard cards

The integration bundles its own family of Lovelace cards — served and registered automatically. No HACS frontend install, no manual resource entry: after setting up the integration (and one page refresh), they appear in the card picker under *Custom: OKRWeather …*.

All cards share one design language, resolve their sensors through the device registry (renamed/non-English entity IDs just work), open the more-info dialog on click, and have full **visual editors** (English and Polish).

### Backgrounds

Every card takes a `background` option (with an intensity slider in the editor):

- `condition` — the accent palette and background wash follow the live weather (default for the full card)
- `none` — flat theme background; the accent still follows the weather (default for feature cards)
- `sunrise` / `amber` / `forest` / `ocean` / `dusk` / `midnight` / `graphite` — fixed ambient presets that adapt to light and dark themes
- `custom` — pick your own accent + two wash colors in the editor (or via YAML: `custom_accent`, `custom_wash_a`, `custom_wash_b`)

```yaml
type: custom:okrweather-forecast-card
entity: weather.gogolin_rondo
background: ocean
background_intensity: 140   # 0–200, default 100
```

### The full station card

`custom:okrweather-card` shows the station header with a condition-adaptive accent palette, a details grid, the EPA-banded AQI meter, a government-alert banner, the premium AI insight tiles (comfort, radar, storm, pressure, frost, solar) and the forecast strip. Sections without data hide themselves — a free-tier setup simply shows no AI tiles.

```yaml
type: custom:okrweather-card
entity: weather.gogolin_rondo   # the station's weather entity (required)
name: Gogolin                   # optional title override
show_current: true              # header with condition + temperature
show_details: true              # humidity/pressure/wind/… grid
show_air_quality: true          # AQI / PM2.5 / PM10 chips
show_alerts: true               # government weather alert banner
show_forecast: true
forecast_type: daily            # daily | hourly | twice_daily
forecast_slots: 5               # 3–8 forecast entries
background: condition           # condition | none | preset name | custom
background_intensity: 100       # 0–200 wash strength
insights:                       # premium AI tiles to render (default: all)
  - comfort
  - radar
  - storm
  - pressure
  - frost
  - solar
compact: false                  # true hides captions and advisory texts
```

### Feature cards

Smaller single-purpose widgets for composing your own dashboard. Every feature card takes `entity` (the station's weather entity, required), `name` (title override) and `show_title`; insight cards add `show_note` for the advisory text.

| Card type | Shows | Extra options |
|---|---|---|
| `custom:okrweather-forecast-card` | Forecast strip with temperature range bars | `forecast_type`, `forecast_slots` |
| `custom:okrweather-details-card` | Live readings grid | `fields` — pick exactly which values |
| `custom:okrweather-air-quality-card` | EPA-banded AQI meter + PM2.5/PM10 | — |
| `custom:okrweather-alerts-card` | All active government alerts (or a calm "no alerts") | — |
| `custom:okrweather-comfort-card` | Comfort ring + label | `show_factors` — per-factor meters |
| `custom:okrweather-radar-card` | Radar trend, intensity, ETA, rain probabilities | — |
| `custom:okrweather-storm-card` | Storm proximity, intensity, ETA, lightning | — |
| `custom:okrweather-pressure-card` | Pressure alert level, trend, Δ3h/Δ6h | — |
| `custom:okrweather-frost-card` | Frost probability, level, window | — |
| `custom:okrweather-solar-card` | Today's kWh, peak kW, efficiency | — |
| `custom:okrweather-air-trend-card` | AI air-quality trend (no data since 2.5.0; the card hides itself) | — |

```yaml
# Example: a compact premium row
type: custom:okrweather-details-card
entity: weather.gogolin_rondo
fields: [temperature, wind_speed, wind_gust, humidity, pressure]
```

Premium feature cards show a quiet "No data available" state when the hub has no API key or the backend hasn't published a fresh row.

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
- **Premium sensors stay `unknown`** — either the backend function hasn't published a fresh row (rows older than the per-feature freshness window are ignored), or the station has no data for that feature.
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
