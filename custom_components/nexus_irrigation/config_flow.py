"""Config flow: impianto, zone in numero libero, sorgente pioggia."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_ADD_ANOTHER,
    CONF_MASTER_ENTITY,
    CONF_MASTER_LAG,
    CONF_MASTER_LEAD,
    CONF_RAIN_ENTITY,
    CONF_RAIN_HOURS,
    CONF_RAIN_MODE,
    CONF_RAIN_THRESHOLD,
    CONF_ZONE_ENTITY,
    CONF_ZONE_ID,
    CONF_ZONE_MINUTES,
    CONF_ZONE_NAME,
    CONF_ZONES,
    CONF_USE_MASTER,
    DEFAULT_MASTER_LAG,
    DEFAULT_MASTER_LEAD,
    DEFAULT_MINUTES,
    DEFAULT_RAIN_HOURS,
    DEFAULT_RAIN_THRESHOLD,
    DOMAIN,
    RAIN_MODES,
    RAIN_NONE,
    RAIN_WEATHER,
)


def _zone_schema(number: int) -> vol.Schema:
    """Schema di una zona. La valvola puo' essere valve.* o switch.*."""
    return vol.Schema(
        {
            vol.Required(CONF_ZONE_NAME, default=f"Zona {number}"): str,
            vol.Required(CONF_ZONE_ENTITY): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=["valve", "switch"])
            ),
            vol.Required(CONF_ZONE_MINUTES, default=DEFAULT_MINUTES): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0, max=120, step=1, unit_of_measurement="min",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Optional(CONF_ADD_ANOTHER, default=False): bool,
        }
    )


_MASTER_SCHEMA = vol.Schema({vol.Required(CONF_USE_MASTER, default=False): bool})


def _master_details_schema(defaults: dict[str, Any]) -> vol.Schema:
    """Entita' del master e ritardi di sequenza."""
    return vol.Schema(
        {
            vol.Required(
                CONF_MASTER_ENTITY, default=defaults.get(CONF_MASTER_ENTITY)
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=["valve", "switch"])
            ),
            vol.Required(
                CONF_MASTER_LEAD, default=defaults.get(CONF_MASTER_LEAD, DEFAULT_MASTER_LEAD)
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0, max=120, step=1, unit_of_measurement="s",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Required(
                CONF_MASTER_LAG, default=defaults.get(CONF_MASTER_LAG, DEFAULT_MASTER_LAG)
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0, max=120, step=1, unit_of_measurement="s",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
        }
    )


_RAIN_MODE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_RAIN_MODE, default=RAIN_NONE): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=RAIN_MODES,
                translation_key="rain_mode",
                mode=selector.SelectSelectorMode.LIST,
            )
        )
    }
)


def _rain_details_schema(mode: str, defaults: dict[str, Any]) -> vol.Schema:
    """Schema dei dettagli pioggia, diverso per sensore e meteo."""
    domains = ["weather"] if mode == RAIN_WEATHER else ["binary_sensor", "sensor"]
    fields: dict[Any, Any] = {
        vol.Required(
            CONF_RAIN_ENTITY, default=defaults.get(CONF_RAIN_ENTITY)
        ): selector.EntitySelector(selector.EntitySelectorConfig(domain=domains)),
        vol.Required(
            CONF_RAIN_THRESHOLD,
            default=defaults.get(CONF_RAIN_THRESHOLD, DEFAULT_RAIN_THRESHOLD),
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=0, max=50, step=0.5, unit_of_measurement="mm",
                mode=selector.NumberSelectorMode.BOX,
            )
        ),
    }
    if mode == RAIN_WEATHER:
        fields[
            vol.Required(
                CONF_RAIN_HOURS, default=defaults.get(CONF_RAIN_HOURS, DEFAULT_RAIN_HOURS)
            )
        ] = selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=1, max=48, step=1, unit_of_measurement="h",
                mode=selector.NumberSelectorMode.BOX,
            )
        )
    return vol.Schema(fields)


class NexusIrrigationConfigFlow(ConfigFlow, domain=DOMAIN):
    """Creazione di un nuovo impianto."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._zones: list[dict[str, Any]] = []

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._async_abort_entries_match({"name": user_input["name"]})
            self._data["name"] = user_input["name"]
            return await self.async_step_zone()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required("name", default="Giardino"): str}),
        )

    async def async_step_zone(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Raccoglie una zona e si richiama finche' l'utente vuole aggiungerne."""
        if user_input is not None:
            add_another = user_input.pop(CONF_ADD_ANOTHER, False)
            self._zones.append(
                {
                    CONF_ZONE_ID: f"zone_{len(self._zones) + 1}",
                    CONF_ZONE_NAME: user_input[CONF_ZONE_NAME],
                    CONF_ZONE_ENTITY: user_input[CONF_ZONE_ENTITY],
                    CONF_ZONE_MINUTES: float(user_input[CONF_ZONE_MINUTES]),
                }
            )
            if add_another:
                return await self.async_step_zone()
            return await self.async_step_master()

        return self.async_show_form(
            step_id="zone",
            data_schema=_zone_schema(len(self._zones) + 1),
            description_placeholders={"number": str(len(self._zones) + 1)},
        )

    async def async_step_master(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Valvola master o pompa: facoltativa, si salta con la spunta."""
        if user_input is not None:
            if user_input[CONF_USE_MASTER]:
                return await self.async_step_master_details()
            return await self.async_step_rain()

        return self.async_show_form(step_id="master", data_schema=_MASTER_SCHEMA)

    async def async_step_master_details(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._data.update(
                {
                    CONF_MASTER_ENTITY: user_input[CONF_MASTER_ENTITY],
                    CONF_MASTER_LEAD: int(user_input[CONF_MASTER_LEAD]),
                    CONF_MASTER_LAG: int(user_input[CONF_MASTER_LAG]),
                }
            )
            return await self.async_step_rain()

        return self.async_show_form(
            step_id="master_details", data_schema=_master_details_schema({})
        )

    async def async_step_rain(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._data[CONF_RAIN_MODE] = user_input[CONF_RAIN_MODE]
            if user_input[CONF_RAIN_MODE] == RAIN_NONE:
                return self._create()
            return await self.async_step_rain_details()

        return self.async_show_form(step_id="rain", data_schema=_RAIN_MODE_SCHEMA)

    async def async_step_rain_details(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return self._create()

        return self.async_show_form(
            step_id="rain_details",
            data_schema=_rain_details_schema(self._data[CONF_RAIN_MODE], {}),
        )

    def _create(self) -> ConfigFlowResult:
        self._data[CONF_ZONES] = self._zones
        return self.async_create_entry(title=self._data["name"], data=self._data)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return NexusIrrigationOptionsFlow()


class NexusIrrigationOptionsFlow(OptionsFlow):
    """Rimette mano a zone e pioggia senza reinstallare l'impianto."""

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._zones: list[dict[str, Any]] = []

    @property
    def _current(self) -> dict[str, Any]:
        return {**self.config_entry.data, **self.config_entry.options}

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_show_menu(step_id="init", menu_options=["zones", "master", "rain"])

    # --- Zone ----------------------------------------------------------------
    async def async_step_zones(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Riscrive l'elenco zone da zero: si ridichiarano tutte."""
        self._zones = []
        return await self.async_step_zone()

    async def async_step_zone(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            add_another = user_input.pop(CONF_ADD_ANOTHER, False)
            self._zones.append(
                {
                    CONF_ZONE_ID: f"zone_{len(self._zones) + 1}",
                    CONF_ZONE_NAME: user_input[CONF_ZONE_NAME],
                    CONF_ZONE_ENTITY: user_input[CONF_ZONE_ENTITY],
                    CONF_ZONE_MINUTES: float(user_input[CONF_ZONE_MINUTES]),
                }
            )
            if add_another:
                return await self.async_step_zone()
            return self._save({CONF_ZONES: self._zones})

        index = len(self._zones)
        existing = self._current.get(CONF_ZONES, [])
        previous = existing[index] if index < len(existing) else {}
        schema = _zone_schema(index + 1)
        if previous:
            schema = self.add_suggested_values_to_schema(schema, previous)

        return self.async_show_form(
            step_id="zone",
            data_schema=schema,
            description_placeholders={"number": str(index + 1)},
        )

    # --- Master ---------------------------------------------------------------
    async def async_step_master(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            if user_input[CONF_USE_MASTER]:
                return await self.async_step_master_details()
            # Togliendo la spunta il master viene dimenticato: da qui in poi
            # l'impianto torna a comandare i soli settori.
            return self._save({CONF_MASTER_ENTITY: None})

        schema = self.add_suggested_values_to_schema(
            _MASTER_SCHEMA, {CONF_USE_MASTER: bool(self._current.get(CONF_MASTER_ENTITY))}
        )
        return self.async_show_form(step_id="master", data_schema=schema)

    async def async_step_master_details(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self._save(
                {
                    CONF_MASTER_ENTITY: user_input[CONF_MASTER_ENTITY],
                    CONF_MASTER_LEAD: int(user_input[CONF_MASTER_LEAD]),
                    CONF_MASTER_LAG: int(user_input[CONF_MASTER_LAG]),
                }
            )

        return self.async_show_form(
            step_id="master_details",
            data_schema=_master_details_schema(self._current),
        )

    # --- Pioggia --------------------------------------------------------------
    async def async_step_rain(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._data[CONF_RAIN_MODE] = user_input[CONF_RAIN_MODE]
            if user_input[CONF_RAIN_MODE] == RAIN_NONE:
                return self._save(
                    {
                        CONF_RAIN_MODE: RAIN_NONE,
                        CONF_RAIN_ENTITY: None,
                    }
                )
            return await self.async_step_rain_details()

        schema = self.add_suggested_values_to_schema(
            _RAIN_MODE_SCHEMA, {CONF_RAIN_MODE: self._current.get(CONF_RAIN_MODE, RAIN_NONE)}
        )
        return self.async_show_form(step_id="rain", data_schema=schema)

    async def async_step_rain_details(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self._save({CONF_RAIN_MODE: self._data[CONF_RAIN_MODE], **user_input})

        return self.async_show_form(
            step_id="rain_details",
            data_schema=_rain_details_schema(self._data[CONF_RAIN_MODE], self._current),
        )

    def _save(self, changes: dict[str, Any]) -> ConfigFlowResult:
        """Le opzioni contengono sempre la configurazione completa."""
        merged = {**self._current, **changes}
        merged.pop("name", None)
        return self.async_create_entry(title="", data=merged)
