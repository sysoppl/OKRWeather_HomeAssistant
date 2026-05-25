# OKRWeather — Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Home Assistant custom integration for **Pogoda OKR / OKRWeather** — a hyperlocal weather network for Powiat Krapkowicki (Opolskie, Poland) with physical sensor stations in Gogolin, Krapkowice, Zdzieszowice and surrounding villages.

The integration talks directly to the OKRWeather Appwrite backend at `api.skydark.pl`. No middleware, no cloud account required for free data.

## Features

### Free tier (no API key required)

Pulled from public Appwrite tables (`read("any")` permission):

- **Weather entity** with hourly + daily forecasts for the city nearest your station
- **Live sensors** — temperature, apparent temperature, dew point, humidity, pressure, wind speed/gust/bearing, precipitation rate, daily precipitation, UV index, solar radiation, ground temperature, soil moisture, snow depth, vapor pressure deficit
- **Air quality sensors** — PM2.5, PM10, CO, NO₂, NH₃ (where the station has an air-quality probe)
- **Weather alerts** — count sensor + binary sensor with full alert details as attributes

### Premium tier (API key required)

Requires an Appwrite API key with `rows.read` scope, issued by the OKRWeather team to active subscribers. The key unlocks AI-derived advisory tables:

- **Comfort Index** (0–100 score with PL/EN label)
- **Frost alert** (probability, level, time window, advisory text)
- **Solar forecast** (today's kWh, peak kW, panel efficiency, production label)
- **Sport conditions** (running and cycling scores + labels)
- **Drying conditions** (VPD-based laundry-drying score and estimated hours)
- **Outfit recommendation**
- **Pressure-headache alert**
- **Storm tracker** (binary sensor + status)
- **Air-quality trend** label

If your API key loses access (e.g. subscription expires), the premium entities go `unavailable` and the integration falls back to free-tier behavior without breaking your dashboard.

## Installation

### HACS (recommended)

1. In HACS, open **Integrations** → top-right **⋮** → **Custom repositories**.
2. Add `https://github.com/jelitop/OKRWeather_HomeAssistant` with category **Integration**.
3. Install **OKRWeather (Pogoda OKR)** from the list.
4. Restart Home Assistant.

### Manual

Copy `custom_components/okrweather/` into your Home Assistant `config/custom_components/` directory, then restart.

## Configuration

1. **Settings → Devices & Services → Add Integration → OKRWeather**.
2. Pick your station from the dropdown (populated from the live `weather-stations` table).
3. (Optional) Paste your Appwrite API key to enable premium features. Leave blank for free data.
4. Set the refresh intervals:
   - **Live data**: 60 s – 24 h (default 300 s / 5 min). The backend updates physical sensor readings about every 60 s.
   - **Forecasts and premium tables**: 1 h – 24 h (default 1 h). The backend regenerates these every 4–6 h, so polling faster is wasted bandwidth.

You can change either interval, or swap the API key, at any time via **Configure** without removing the integration.

## How to get a premium API key

Premium features are part of the OKRWeather subscription tiers (3/6/12-month plans). Sign up at [pogodaokr.pl](https://pogodaokr.pl) and ask support to issue an API key for Home Assistant — they'll grant a key scoped to the premium tables your subscription covers.

## Entity reference

| Domain | Entity ID pattern | Free / Premium |
|---|---|---|
| `weather` | `weather.<station>` | Free |
| `sensor` | `sensor.<station>_temperature` etc. | Free |
| `sensor` | `sensor.<station>_pm2_5` etc. | Free (if station has air probe) |
| `sensor` | `sensor.<station>_active_alerts_count` | Free |
| `binary_sensor` | `binary_sensor.<station>_weather_alert_active` | Free |
| `sensor` | `sensor.<station>_comfort_score` etc. | Premium |
| `sensor` | `sensor.<station>_frost_probability` etc. | Premium |
| `sensor` | `sensor.<station>_solar_total_kwh` etc. | Premium |
| `sensor` | `sensor.<station>_running_score` etc. | Premium |
| `sensor` | `sensor.<station>_drying_score` etc. | Premium |
| `binary_sensor` | `binary_sensor.<station>_frost_alert_active` | Premium |
| `binary_sensor` | `binary_sensor.<station>_storm_alert_active` | Premium |

Some sensors are disabled by default (ground temperature, soil moisture, snow depth, gas concentrations) — enable them from the device page if your station reports them.

## Notes for users in non-Polish locales

The OKRWeather backend is regional and only covers `Powiat Krapkowicki, PL`. If you're outside this area, the live sensor data will not be relevant — but the integration still works as a learning resource for talking to an Appwrite backend from Home Assistant.

## Languages

UI is translated to English and Polish.

## Troubleshooting

- **"Could not reach the OKRWeather backend"** — check that `api.skydark.pl` resolves and is reachable from your Home Assistant host. The integration uses CloudFlare-fronted endpoints.
- **Premium sensors stay `unavailable`** — your API key may not include the required scope, or it may have been revoked. Reconfigure via **Configure** to enter a new key.
- **Weather entity shows `unknown` condition** — the forecast condition string from the backend didn't map to any of HA's condition vocabulary. Enable debug logging and open an issue with the raw value.

Enable debug logging:

```yaml
logger:
  default: info
  logs:
    custom_components.okrweather: debug
```

## Development

The integration follows the modern (Home Assistant ≥ 2026.3) custom-component patterns:

- `runtime_data` on `ConfigEntry`
- Typed config entry alias (`OKRWeatherConfigEntry`)
- Two `DataUpdateCoordinator`s (live + forecast)
- Pure-aiohttp REST client (no Appwrite SDK)
- `has_entity_name = True` with translation keys

## License

[MIT](LICENSE)

## Credits

- Data: [Pogoda OKR](https://pogodaokr.pl) — public weather network for Powiat Krapkowicki
- Scaffolding inspired by [ludeeus/integration_blueprint](https://github.com/ludeeus/integration_blueprint)
