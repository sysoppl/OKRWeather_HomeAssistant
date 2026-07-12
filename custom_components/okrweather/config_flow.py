"""Config, options and subentry flows for OKRWeather.

Layout (v2):

* One **hub** config entry per backend (endpoint + project + optional API
  key). Refresh intervals and the advisory language live in its options.
* One **station subentry** per weather station. Stations can be added and
  removed at any time from the integration page without touching the hub.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryData,
    ConfigSubentryFlow,
    OptionsFlow,
    SubentryFlowResult,
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
    CONF_ALERT_LOCATION_ID,
    CONF_API_KEY,
    CONF_ENDPOINT,
    CONF_FORECAST_INTERVAL,
    CONF_INSIGHTS_INTERVAL,
    CONF_LANGUAGE,
    CONF_LIVE_INTERVAL,
    CONF_PROJECT_ID,
    CONF_STATION_CITY,
    CONF_STATION_ID,
    CONF_STATION_KEY,
    CONF_STATION_LAT,
    CONF_STATION_LON,
    CONF_STATION_NAME,
    CONF_STATION_SLUG,
    CONF_STATIONS,
    DEFAULT_ENDPOINT,
    DEFAULT_FORECAST_INTERVAL,
    DEFAULT_INSIGHTS_INTERVAL,
    DEFAULT_LANGUAGE,
    DEFAULT_LIVE_INTERVAL,
    DEFAULT_PROJECT_ID,
    DOMAIN,
    LANG_AUTO,
    LANG_EN,
    LANG_PL,
    LOGGER,
    MAX_FORECAST_INTERVAL,
    MAX_INSIGHTS_INTERVAL,
    MAX_LIVE_INTERVAL,
    MIN_FORECAST_INTERVAL,
    MIN_INSIGHTS_INTERVAL,
    MIN_LIVE_INTERVAL,
    SUBENTRY_TYPE_STATION,
    TABLE_COMFORT_INDEX,
)

# ── Shared helpers ───────────────────────────────────────────────────────────


def station_subentry_data(row: dict[str, Any]) -> dict[str, Any]:
    """Map a weather-stations row to the data stored on a station subentry."""
    return {
        CONF_STATION_ID: row["$id"],
        CONF_STATION_KEY: row.get("station_id") or row["$id"],
        CONF_STATION_SLUG: row.get("slug") or row["$id"],
        CONF_STATION_NAME: row.get("name") or row["$id"],
        CONF_STATION_CITY: row.get("city"),
        CONF_STATION_LAT: row.get("latitude"),
        CONF_STATION_LON: row.get("longitude"),
        CONF_ALERT_LOCATION_ID: row.get("alert_location_id"),
    }


def _station_label(row: dict[str, Any]) -> str:
    name = row.get("name") or row["$id"]
    city = row.get("city")
    return f"{name} ({city})" if city and city != name else str(name)


async def _validate_backend(
    hass: Any,
    *,
    endpoint: str,
    project_id: str,
    api_key: str | None,
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    """Validate connectivity (and the API key if given); return stations."""
    errors: dict[str, str] = {}
    client = OKRWeatherApiClient(
        session=async_get_clientsession(hass),
        endpoint=endpoint,
        project_id=project_id,
        api_key=None,
    )
    stations: list[dict[str, Any]] = []
    try:
        stations = await client.list_stations()
    except OKRWeatherApiCommunicationError:
        errors["base"] = "cannot_connect"
    except OKRWeatherApiAuthError:
        errors["base"] = "invalid_project"
    except OKRWeatherApiError as err:
        LOGGER.error("Unexpected API error while listing stations: %s", err)
        errors["base"] = "unknown"

    if not errors and api_key:
        premium = OKRWeatherApiClient(
            session=async_get_clientsession(hass),
            endpoint=endpoint,
            project_id=project_id,
            api_key=api_key,
        )
        try:
            # Any authorised read proves the key works; empty results are fine.
            await premium.recent_insight_rows(TABLE_COMFORT_INDEX, 1)
        except (OKRWeatherApiAuthError, OKRWeatherApiPermissionError):
            errors[CONF_API_KEY] = "invalid_auth"
        except OKRWeatherApiCommunicationError:
            errors["base"] = "cannot_connect"
        except OKRWeatherApiError as err:
            LOGGER.error("Unexpected API error while validating key: %s", err)
            errors["base"] = "unknown"

    return errors, stations


# ── Hub config flow ──────────────────────────────────────────────────────────


class OKRWeatherConfigFlow(ConfigFlow, domain=DOMAIN):
    """Hub setup: credentials first, then pick the stations to add."""

    VERSION = 2
    MINOR_VERSION = 1

    def __init__(self) -> None:
        self._endpoint: str = DEFAULT_ENDPOINT
        self._project_id: str = DEFAULT_PROJECT_ID
        self._api_key: str | None = None
        self._stations: list[dict[str, Any]] = []

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Stations are managed as subentries of the hub."""
        return {SUBENTRY_TYPE_STATION: StationSubentryFlowHandler}

    # ── Step 1: backend + optional API key ─────────────────────────────────

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Collect endpoint (advanced) and the optional premium API key."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._api_key = (user_input.get(CONF_API_KEY) or "").strip() or None
            self._endpoint = (
                user_input.get(CONF_ENDPOINT) or DEFAULT_ENDPOINT
            ).strip().rstrip("/")
            self._project_id = (
                user_input.get(CONF_PROJECT_ID) or DEFAULT_PROJECT_ID
            ).strip()

            for entry in self._async_current_entries(include_ignore=False):
                if (
                    entry.data.get(CONF_ENDPOINT, DEFAULT_ENDPOINT) == self._endpoint
                    and entry.data.get(CONF_PROJECT_ID, DEFAULT_PROJECT_ID)
                    == self._project_id
                ):
                    return self.async_abort(reason="already_configured")

            errors, self._stations = await _validate_backend(
                self.hass,
                endpoint=self._endpoint,
                project_id=self._project_id,
                api_key=self._api_key,
            )
            if not errors:
                if not self._stations:
                    return self.async_abort(reason="no_stations")
                return await self.async_step_stations()

        schema: dict[Any, Any] = {
            vol.Optional(CONF_API_KEY, default=""): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            ),
        }
        if self.show_advanced_options:
            schema[vol.Optional(CONF_ENDPOINT, default=self._endpoint)] = (
                selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.URL)
                )
            )
            schema[vol.Optional(CONF_PROJECT_ID, default=self._project_id)] = str

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(schema),
            errors=errors,
        )

    # ── Step 2: pick stations ───────────────────────────────────────────────

    async def async_step_stations(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Multi-select the stations to add; each becomes a subentry."""
        errors: dict[str, str] = {}

        if user_input is not None:
            chosen = [
                row
                for row in self._stations
                if row["$id"] in user_input.get(CONF_STATIONS, [])
            ]
            if not chosen:
                errors[CONF_STATIONS] = "no_station_selected"
            else:
                data: dict[str, Any] = {
                    CONF_ENDPOINT: self._endpoint,
                    CONF_PROJECT_ID: self._project_id,
                }
                if self._api_key:
                    data[CONF_API_KEY] = self._api_key
                return self.async_create_entry(
                    title="OKRWeather",
                    data=data,
                    options={
                        CONF_LIVE_INTERVAL: DEFAULT_LIVE_INTERVAL,
                        CONF_INSIGHTS_INTERVAL: DEFAULT_INSIGHTS_INTERVAL,
                        CONF_FORECAST_INTERVAL: DEFAULT_FORECAST_INTERVAL,
                        CONF_LANGUAGE: DEFAULT_LANGUAGE,
                    },
                    subentries=[
                        ConfigSubentryData(
                            subentry_type=SUBENTRY_TYPE_STATION,
                            title=row.get("name") or row["$id"],
                            unique_id=row["$id"],
                            data=station_subentry_data(row),
                        )
                        for row in chosen
                    ],
                )

        options = [
            selector.SelectOptionDict(value=row["$id"], label=_station_label(row))
            for row in self._stations
        ]
        return self.async_show_form(
            step_id="stations",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_STATIONS,
                        default=[row["$id"] for row in self._stations],
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=options,
                            multiple=True,
                            mode=selector.SelectSelectorMode.LIST,
                        )
                    ),
                }
            ),
            errors=errors,
        )

    # ── Reauth (API key rejected at runtime) ────────────────────────────────

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Start reauth after the backend rejected the stored API key."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Ask for a new API key (blank falls back to the free tier)."""
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()

        if user_input is not None:
            api_key = (user_input.get(CONF_API_KEY) or "").strip() or None
            errors, _ = await _validate_backend(
                self.hass,
                endpoint=entry.data.get(CONF_ENDPOINT, DEFAULT_ENDPOINT),
                project_id=entry.data.get(CONF_PROJECT_ID, DEFAULT_PROJECT_ID),
                api_key=api_key,
            )
            if not errors:
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
                            type=selector.TextSelectorType.PASSWORD
                        )
                    ),
                }
            ),
            errors=errors,
        )

    # ── Reconfigure (endpoint / project / API key) ──────────────────────────

    async def async_step_reconfigure(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Let the user change backend settings without re-adding stations."""
        errors: dict[str, str] = {}
        entry = self._get_reconfigure_entry()

        if user_input is not None:
            endpoint = (
                user_input.get(CONF_ENDPOINT) or DEFAULT_ENDPOINT
            ).strip().rstrip("/")
            project_id = (
                user_input.get(CONF_PROJECT_ID) or DEFAULT_PROJECT_ID
            ).strip()
            api_key = (user_input.get(CONF_API_KEY) or "").strip() or None

            errors, _ = await _validate_backend(
                self.hass, endpoint=endpoint, project_id=project_id, api_key=api_key
            )
            if not errors:
                new_data = {
                    CONF_ENDPOINT: endpoint,
                    CONF_PROJECT_ID: project_id,
                }
                if api_key:
                    new_data[CONF_API_KEY] = api_key
                return self.async_update_reload_and_abort(entry, data=new_data)

        current = entry.data
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_API_KEY,
                        default=current.get(CONF_API_KEY, ""),
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.PASSWORD
                        )
                    ),
                    vol.Optional(
                        CONF_ENDPOINT,
                        default=current.get(CONF_ENDPOINT, DEFAULT_ENDPOINT),
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(type=selector.TextSelectorType.URL)
                    ),
                    vol.Optional(
                        CONF_PROJECT_ID,
                        default=current.get(CONF_PROJECT_ID, DEFAULT_PROJECT_ID),
                    ): str,
                }
            ),
            errors=errors,
        )

    # ── Options ─────────────────────────────────────────────────────────────

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow handler."""
        return OKRWeatherOptionsFlow()


# ── Options flow (intervals + language) ─────────────────────────────────────


class OKRWeatherOptionsFlow(OptionsFlow):
    """Runtime tweaks that don't require touching credentials."""

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Edit polling intervals and the advisory language."""
        if user_input is not None:
            return self.async_create_entry(
                data={
                    CONF_LIVE_INTERVAL: int(user_input[CONF_LIVE_INTERVAL]),
                    CONF_INSIGHTS_INTERVAL: int(user_input[CONF_INSIGHTS_INTERVAL]),
                    CONF_FORECAST_INTERVAL: int(user_input[CONF_FORECAST_INTERVAL]),
                    CONF_LANGUAGE: user_input[CONF_LANGUAGE],
                }
            )

        options = self.config_entry.options

        def _interval(key: str, default: int, lo: int, hi: int) -> Any:
            return vol.Required(key, default=options.get(key, default)), (
                selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=lo,
                        max=hi,
                        step=10,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="s",
                    )
                )
            )

        live_key, live_sel = _interval(
            CONF_LIVE_INTERVAL, DEFAULT_LIVE_INTERVAL, MIN_LIVE_INTERVAL, MAX_LIVE_INTERVAL
        )
        insights_key, insights_sel = _interval(
            CONF_INSIGHTS_INTERVAL,
            DEFAULT_INSIGHTS_INTERVAL,
            MIN_INSIGHTS_INTERVAL,
            MAX_INSIGHTS_INTERVAL,
        )
        forecast_key, forecast_sel = _interval(
            CONF_FORECAST_INTERVAL,
            DEFAULT_FORECAST_INTERVAL,
            MIN_FORECAST_INTERVAL,
            MAX_FORECAST_INTERVAL,
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    live_key: live_sel,
                    insights_key: insights_sel,
                    forecast_key: forecast_sel,
                    vol.Required(
                        CONF_LANGUAGE,
                        default=options.get(CONF_LANGUAGE, DEFAULT_LANGUAGE),
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[LANG_AUTO, LANG_EN, LANG_PL],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                            translation_key="language",
                        )
                    ),
                }
            ),
        )


# ── Station subentry flow ────────────────────────────────────────────────────


class StationSubentryFlowHandler(ConfigSubentryFlow):
    """Add another station to an existing hub."""

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> SubentryFlowResult:
        """Pick one of the stations that isn't configured yet."""
        entry = self._get_entry()
        errors: dict[str, str] = {}

        client = OKRWeatherApiClient(
            session=async_get_clientsession(self.hass),
            endpoint=entry.data.get(CONF_ENDPOINT, DEFAULT_ENDPOINT),
            project_id=entry.data.get(CONF_PROJECT_ID, DEFAULT_PROJECT_ID),
        )
        try:
            stations = await client.list_stations()
        except OKRWeatherApiCommunicationError:
            return self.async_abort(reason="cannot_connect")
        except OKRWeatherApiError:
            return self.async_abort(reason="unknown")

        configured = {
            sub.data.get(CONF_STATION_ID)
            for sub in entry.subentries.values()
            if sub.subentry_type == SUBENTRY_TYPE_STATION
        }
        available = [row for row in stations if row["$id"] not in configured]
        if not available:
            return self.async_abort(reason="no_stations_left")

        if user_input is not None:
            row = next(
                (r for r in available if r["$id"] == user_input[CONF_STATION_ID]),
                None,
            )
            if row is None:
                errors[CONF_STATION_ID] = "unknown_station"
            else:
                return self.async_create_entry(
                    title=row.get("name") or row["$id"],
                    data=station_subentry_data(row),
                    unique_id=row["$id"],
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_STATION_ID): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                selector.SelectOptionDict(
                                    value=row["$id"], label=_station_label(row)
                                )
                                for row in available
                            ],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
            errors=errors,
        )
