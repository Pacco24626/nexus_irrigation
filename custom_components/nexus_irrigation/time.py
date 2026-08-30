"""Time: ora di avvio del ciclo automatico."""

from __future__ import annotations

from datetime import time as dt_time

from homeassistant.components.time import TimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DEFAULT_START_HOUR, DOMAIN, KEY_START_TIME
from .controller import IrrigationController
from .entity import IrrigationEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    controller: IrrigationController = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([StartTimeEntity(controller)])


class StartTimeEntity(IrrigationEntity, TimeEntity, RestoreEntity):
    """Ora di partenza del ciclo, modificabile dalla dashboard."""

    _attr_name = "Ora di avvio"
    _attr_icon = "mdi:clock-outline"

    def __init__(self, controller: IrrigationController) -> None:
        super().__init__(controller, KEY_START_TIME)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None:
            try:
                hour, minute, *_ = last.state.split(":")
                self.controller.set_start_time(dt_time(int(hour), int(minute)))
            except (AttributeError, TypeError, ValueError):
                self.controller.set_start_time(dt_time(DEFAULT_START_HOUR, 0))

    @property
    def native_value(self) -> dt_time:
        return self.controller.start_time

    async def async_set_value(self, value: dt_time) -> None:
        self.controller.set_start_time(value)
