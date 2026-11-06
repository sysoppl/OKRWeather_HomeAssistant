# Home Assistant integration

HACS custom integration that shows Pogoda OKR stations, forecasts and alerts as Home Assistant sensors.

Released through GitHub releases and HACS; it runs in the users' Home Assistant.

## Inputs

- `weather-data` (station readings, 1 row per minute per station)
- `weather-stations` (active stations)
- `hourly-forecasts` (Google, hourly), `daily-forecasts` (Google, daily)
- `weather-alerts`, `radar-status`, `storm-tracker`, `pressure-alerts`, `frost-alerts`, `comfort-index`, `solar-forecast`

## Outputs

- Home Assistant entities

## Deploy

Tag a release (version in `custom_components/okrweather/manifest.json`); HACS picks it up.

## Credits

Dane: Google
Źródłem pochodzenia danych jest Instytut Meteorologii i Gospodarki Wodnej – Państwowy Instytut Badawczy.

More detail (model, formulas, history): [`docs/DETAILS.md`](docs/DETAILS.md). Operations in this README take precedence.
