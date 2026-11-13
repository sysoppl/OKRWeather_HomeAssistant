# Home Assistant integration

HACS custom integration that shows Pogoda OKR stations, forecasts and alerts as Home Assistant sensors.

Released through GitHub releases and HACS; it runs in the users' Home Assistant.

## Inputs

- `station-readings` (station readings, 1 row per minute per station)
- `weather-stations` (active stations)
- `air-quality-readings` (measured PM from Airly, stations with an air-quality source)
- `hourly-forecasts` (Google, hourly), `daily-forecasts` (Google, daily)
- `weather-alerts`, `radar-status`, `storm-alerts`, `pressure-alerts`, `frost-alerts`, `comfort-index`, `solar-forecasts`

Renamed tables fall back to their old ids (`weather-data`, `storm-tracker`, `solar-forecast`) while those still exist; the newest row wins (`custom_components/okrweather/sources.py`). Every table is read on its own, so a missing table only blanks its own values.

## Outputs

- Home Assistant entities

Pressure contract: `pressure` sensor and the weather entity's current pressure are reduced to mean sea level (vendored `custom_components/okrweather/pressure.py`, same formula as the portal; unknown when the station elevation is unknown); forecast rows use `airPressureMsl`. The raw station-level `air_pressure_hpa` is only the diagnostic, disabled-by-default `station_pressure` sensor ("Station pressure (raw)").

## Tests

`pip install -r requirements_test.txt && pytest -q` (mocked backend, no Home Assistant install needed).

## Deploy

Tag a release (version in `custom_components/okrweather/manifest.json`); HACS picks it up. User-facing changes go in `CHANGELOG.md`.

## Credits

Dane: Google
Dane: Airly
Źródłem pochodzenia danych jest Instytut Meteorologii i Gospodarki Wodnej – Państwowy Instytut Badawczy.

More detail (model, formulas, history): [`docs/DETAILS.md`](docs/DETAILS.md). Operations in this README take precedence.
