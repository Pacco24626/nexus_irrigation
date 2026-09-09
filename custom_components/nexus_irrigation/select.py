"""Select: come si scelgono i giorni di irrigazione.

Quattro modi, gli stessi delle centraline da giardino. Pari e dispari non
sono un vezzo: molti comuni li impongono durante le restrizioni idriche
estive, e senza non si e' conformi. I giorni ciclici tengono un ritmo
costante, mentre "lunedi', mercoledi', venerdi'" lascia due giorni fra
venerdi' e lunedi' e uno fra gli altri.
"""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DEFAULT_MODO_GIORNI, DOMAIN, KEY_DAY_MODE, MODI_GIORNI
from .controller import IrrigationController
from .entity import IrrigationEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    controller: IrrigationController = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([DayModeSelect(controller)])


class DayModeSelect(IrrigationEntity, SelectEntity, RestoreEntity):
    """Settimanale, dispari, pari o ciclico.

    In modalita' settimanale contano gli interruttori dei giorni; nelle altre
    tre vengono ignorati, e la cadenza la decide il calendario.
    """

    _attr_name = "Modalita' giorni"
    _attr_icon = "mdi:calendar-sync"
    _attr_options = MODI_GIORNI
    _attr_translation_key = "day_mode"

    def __init__(self, controller: IrrigationController) -> None:
        super().__init__(controller, KEY_DAY_MODE)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and last.state in MODI_GIORNI:
            self.controller.set_day_mode(last.state)
        else:
            self.controller.set_day_mode(DEFAULT_MODO_GIORNI)

    @property
    def current_option(self) -> str:
        return self.controller.day_mode

    async def async_select_option(self, option: str) -> None:
        self.controller.set_day_mode(option)
