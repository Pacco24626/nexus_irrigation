"""Button: avvio ciclo a mano e arresto immediato."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, KEY_START_CYCLE, KEY_STOP
from .controller import IrrigationController
from .entity import IrrigationEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    controller: IrrigationController = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([StartCycleButton(controller), StopButton(controller)])


class StartCycleButton(IrrigationEntity, ButtonEntity):
    """Giro extra a mano: salta il controllo pioggia, non i tempi."""

    _attr_name = "Avvia ciclo"
    _attr_icon = "mdi:play-circle"

    def __init__(self, controller: IrrigationController) -> None:
        super().__init__(controller, KEY_START_CYCLE)

    async def async_press(self) -> None:
        await self.controller.async_start_cycle(check_rain=False)


class StopButton(IrrigationEntity, ButtonEntity):
    """Arresto immediato: interrompe il ciclo e chiude tutte le valvole."""

    _attr_name = "Arresta"
    _attr_icon = "mdi:stop-circle"

    def __init__(self, controller: IrrigationController) -> None:
        super().__init__(controller, KEY_STOP)

    async def async_press(self) -> None:
        await self.controller.async_stop()
