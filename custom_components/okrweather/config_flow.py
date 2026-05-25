"""Config and options flow for OKRWeather."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    OKRWeatherApiAuthError,
    OKRWeatherApiClient,
    OKRWeatherApiCommunicationError,
    OKRWeatherApiError,
    OKRWeatherApiPermissionError,
)
from .const import (
    CONF_API_KEY,
    CONF_ENDPOINT,
    CONF_FORECAST_INTERVAL,
    CONF_LIVE_INTERVAL,
    CONF_PROJECT_ID,
    CONF_STATION_ID,
    CONF_STATION_KEY,
    CONF_STATION_LAT,
    CONF_STATION_LON,
    CONF_STATION_NAME,
    CONF_STATION_SLUG,
    DEFAULT_ENDPOINT,
    DEFAULT_FORECAST_INTERVAL,
    DEFAULT_LIVE_INTERVAL,
    DEFAULT_PROJECT_ID,
    DOMAIN,
    LOGGER,
    MAX_FORECAST_INTERVAL,
    MAX_LIVE_INTERVAL,
    MIN_FORECAST_INTERVAL,
    MIN_LIVE_INTERVAL,
    TABLE_COMFORT_INDEX,
)


class OKRWeatherConfigFlow(ConfigFlow, domain=DOMAIN):
    """Two-step setup: pick station, then (optionally) provide API key."""

    VERSION = 1
    MINOR_VERSION = 1

    def __init__(self) -> None:
        self._stations: list[dict[str, Any]] = []
        self._endpoint: str = DEFAULT_ENDPOINT
        self._project_id: str = DEFAULT_PROJECT_ID
        self._chosen_station: dict[str, Any] | None = None

    # ── Step 1: pick a station ──────────────────────────────────────────────

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Initial step — list stations from the public API."""
        errors: dict[str, str] = {}

        if not self._stations:
            try:
                client = OKRWeatherApiClient(
                    session=async_get_clientsession(self.hass),
                    endpoint=self._endpoint,
                    project_id=self._project_id,
                )
                self._stations = await client.list_stations()
            except OKRWeatherApiCommunicationError as err:
                LOGGER.error("Could not reach OKRWeather API: %s", err)
                errors["base"] = "cannot_connect"
            except OKRWeatherApiError as err:
                LOGGER.error("Unexpected API error: %s", err)
                errors["base"] = "unknown"

        if errors:
            return self.async_show_form(
                step_id="user",
                errors=errors,
                data_schema=vol.Schema({}),
            )

        if not self._stations:
            return self.async_abort(reason="no_stations")

        # Build station selector options.
        station_options = [
            selector.SelectOptionDict(
                value=row["$id"],
                label=f"{row.get('name', row['$id'])} ({row.get('slug', '')})",
            )
            for row in self._stations
        ]

        if user_input is not None:
            station_id = user_input[CONF_STATION_ID]
            chosen = next(
                (s for s in self._stations if s["$id"] == station_id),
                None,
            )
            if chosen is None:
                errors[CONF_STATION_ID] = "unknown_station"
            else:
                await self.async_set_unique_id(station_id)
                self._abort_if_unique_id_configured()
                self._chosen_station = chosen
                return await self.async_step_credentials()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_STATION_ID): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=station_options,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
            errors=errors,
        )

    # ── Step 2: optional API key + intervals ────────────────────────────────

    async def async_step_credentials(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Capture an optional API key and the refresh intervals."""
        assert self._chosen_station is not None
        errors: dict[str, str] = {}

        if user_input is not None:
            api_key = (user_input.get(CONF_API_KEY) or "").strip() or None

            if api_key:
                ok, reason = await self._validate_api_key(api_key)
                if not ok:
                    errors[CONF_API_KEY] = reason or "invalid_key"

            if not errors:
                station = self._chosen_station
                data = {
                    CONF_STATION_ID: station["$id"],
                    # station_id column on weather-stations is the business
                    # key the AI writer functions use when populating premium
                    # tables — store it separately so we can query premium
                    # tables that lack a `station` relationship field.
                    CONF_STATION_KEY: station.get("station_id") or station["$id"],
                    CONF_STATION_SLUG: station.get("slug", station["$id"]),
                    CONF_STATION_NAME: station.get("name", station["$id"]),
                    CONF_STATION_LAT: station.get("latitude"),
                    CONF_STATION_LON: station.get("longitude"),
                    CONF_ENDPOINT: self._endpoint,
                    CONF_PROJECT_ID: self._project_id,
                }
                if api_key:
                    data[CONF_API_KEY] = api_key

                options = {
                    CONF_LIVE_INTERVAL: int(user_input[CONF_LIVE_INTERVAL]),
                    CONF_FORECAST_INTERVAL: int(user_input[CONF_FORECAST_INTERVAL]),
                }

                return self.async_create_entry(
                    title=station.get("name", station["$id"]),
                    data=data,
                    options=options,
                )

        return self.async_show_form(
            step_id="credentials",
            data_schema=self._credentials_schema(user_input),
            errors=errors,
            description_placeholders={
                "station_name": self._chosen_station.get(
                    "name", self._chosen_station["$id"]
                ),
            },
        )

    def _credentials_schema(self, prefill: dict[str, Any] | None) -> vol.Schema:
        prefill = prefill or {}
        return vol.Schema(
            {
                vol.Optional(
                    CONF_API_KEY,
                    default=prefill.get(CONF_API_KEY, ""),
                ): selector.TextSelector(
                    selector.TextSelectorConfig(
                        type=selector.TextSelectorType.PASSWORD,
                    )
                ),
                vol.Required(
                    CONF_LIVE_INTERVAL,
                    default=prefill.get(CONF_LIVE_INTERVAL, DEFAULT_LIVE_INTERVAL),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=MIN_LIVE_INTERVAL,
                        max=MAX_LIVE_INTERVAL,
                        step=10,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="s",
                    )
                ),
                vol.Required(
                    CONF_FORECAST_INTERVAL,
                    default=prefill.get(
                        CONF_FORECAST_INTERVAL, DEFAULT_FORECAST_INTERVAL
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=MIN_FORECAST_INTERVAL,
                        max=MAX_FORECAST_INTERVAL,
                        step=60,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="s",
                    )
                ),
            }
        )

    # ── Reauth ──────────────────────────────────────────────────────────────

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Triggered when the existing API key stops working."""
        self._endpoint = entry_data.get(CONF_ENDPOINT, DEFAULT_ENDPOINT)
        self._project_id = entry_data.get(CONF_PROJECT_ID, DEFAULT_PROJECT_ID)
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            api_key = (user_input.get(CONF_API_KEY) or "").strip() or None
            if api_key:
                ok, reason = await self._validate_api_key(api_key)
                if not ok:
                    errors[CONF_API_KEY] = reason or "invalid_key"

            if not errors:
                entry = self._get_reauth_entry()
                new_data = {**entry.data}
                if api_key:
                    new_data[CONF_API_KEY] = api_key
                else:
                    new_data.pop(CONF_API_KEY, None)
                return self.async_update_reload_and_abort(entry, data=new_data)

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_API_KEY, default=""): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.PASSWORD,
                        )
                    ),
                }
            ),
            errors=errors,
        )

    # ── Helpers ─────────────────────────────────────────────────────────────

    async def _validate_api_key(self, api_key: str) -> tuple[bool, str | None]:
        """Hit a premium table — a 200 (or empty result) means the key works.

        We tolerate empty result sets because the station may simply have no
        recent comfort-index row, which is fine; what we care about is that
        the request was authenticated and authorised.
        """
        client = OKRWeatherApiClient(
            session=async_get_clientsession(self.hass),
            endpoint=self._endpoint,
            project_id=self._project_id,
            api_key=api_key,
        )
        try:
            assert self._chosen_station is not None
            station_key = (
                self._chosen_station.get("station_id") or self._chosen_station["$id"]
            )
            await client.latest_premium_row(TABLE_COMFORT_INDEX, station_key)
        except OKRWeatherApiAuthError:
            return False, "invalid_auth"
        except OKRWeatherApiPermissionError:
            return False, "no_premium"
        except OKRWeatherApiCommunicationError:
            return False, "cannot_connect"
        except OKRWeatherApiError as err:
            LOGGER.warning("API key validation hit unexpected error: %s", err)
            return False, "unknown"
        return True, None

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> OptionsFlow:
        return OKRWeatherOptionsFlow()


# ── Options flow (runtime tweaks) ───────────────────────────────────────────


class OKRWeatherOptionsFlow(OptionsFlow):
    """Runtime tweaks — change API key, intervals, language, without re-pairing."""

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self.config_entry
        current = {**entry.data, **entry.options}

        if user_input is not None:
            api_key = (user_input.get(CONF_API_KEY) or "").strip() or None

            if api_key and api_key != current.get(CONF_API_KEY):
                client = OKRWeatherApiClient(
                    session=async_get_clientsession(self.hass),
                    endpoint=current.get(CONF_ENDPOINT, DEFAULT_ENDPOINT),
                    project_id=current.get(CONF_PROJECT_ID, DEFAULT_PROJECT_ID),
                    api_key=api_key,
                )
                try:
                    await client.latest_premium_row(
                        TABLE_COMFORT_INDEX,
                        current.get(CONF_STATION_KEY) or current[CONF_STATION_ID],
                    )
                except OKRWeatherApiAuthError:
                    errors[CONF_API_KEY] = "invalid_auth"
                except OKRWeatherApiPermissionError:
                    errors[CONF_API_KEY] = "no_premium"
                except OKRWeatherApiCommunicationError:
                    errors[CONF_API_KEY] = "cannot_connect"
                except OKRWeatherApiError:
                    errors[CONF_API_KEY] = "unknown"

            if not errors:
                new_options: dict[str, Any] = {
                    CONF_LIVE_INTERVAL: int(user_input[CONF_LIVE_INTERVAL]),
                    CONF_FORECAST_INTERVAL: int(user_input[CONF_FORECAST_INTERVAL]),
                }
                if api_key:
                    new_options[CONF_API_KEY] = api_key
                return self.async_create_entry(title="", data=new_options)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_API_KEY,
                        default=current.get(CONF_API_KEY, ""),
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.PASSWORD,
                        )
                    ),
                    vol.Required(
                        CONF_LIVE_INTERVAL,
                        default=current.get(
                            CONF_LIVE_INTERVAL, DEFAULT_LIVE_INTERVAL
                        ),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=MIN_LIVE_INTERVAL,
                            max=MAX_LIVE_INTERVAL,
                            step=10,
                            mode=selector.NumberSelectorMode.BOX,
                            unit_of_measurement="s",
                        )
                    ),
                    vol.Required(
                        CONF_FORECAST_INTERVAL,
                        default=current.get(
                            CONF_FORECAST_INTERVAL, DEFAULT_FORECAST_INTERVAL
                        ),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=MIN_FORECAST_INTERVAL,
                            max=MAX_FORECAST_INTERVAL,
                            step=60,
                            mode=selector.NumberSelectorMode.BOX,
                            unit_of_measurement="s",
                        )
                    ),
                }
            ),
            errors=errors,
        )
