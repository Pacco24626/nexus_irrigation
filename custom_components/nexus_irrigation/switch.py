"""Switch: abilitazione impianto, giorni della settimana, apertura manuale."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DAY_KEYS, DOMAIN, KEY_DAY_PREFIX, KEY_ENABLE, zone_manual_key
from .controller import IrrigationController, Zone
from .entity import IrrigationEntity

DAY_NAMES = ["Lunedi", "Martedi", "Mercoledi", "Giovedi", "Venerdi", "Sabato", "Domenica"]


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    controller: IrrigationController = hass.data[DOMAIN][entry.entry_id]
    entities: list[SwitchEntity] = [EnableSwitch(controller)]
    entities += [DaySwitch(controller, index) for index in range(7)]
    entities += [ZoneManualSwitch(controller, zone) for zone in controller.zones]
    async_add_entities(entities)


class EnableSwitch(IrrigationEntity, SwitchEntity, RestoreEntity):
    """Interruttore generale: da spegnere in vacanza o a stagione finita."""

    _attr_name = "Abilitata"
    _attr_icon = "mdi:sprinkler-variant"

    def __init__(self, controller: IrrigationController) -> None:
        super().__init__(controller, KEY_ENABLE)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_state()) is not None:
            self.controller.set_enabled(last.state == "on")

    @property
    def is_on(self) -> bool:
        return self.controller.enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        self.controller.set_enabled(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        self.controller.set_enabled(False)


class DaySwitch(IrrigationEntity, SwitchEntity, RestoreEntity):
    """Un giorno della settimana in cui il ciclo automatico puo' partire."""

    _attr_icon = "mdi:calendar"
    _attr_entity_category = None

    def __init__(self, controller: IrrigationController, index: int) -> None:
        super().__init__(controller, f"{KEY_DAY_PREFIX}{DAY_KEYS[index]}")
        self._index = index
        self._attr_name = DAY_NAMES[index]

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_state()) is not None:
            self.controller.set_day(self._index, last.state == "on")

    @property
    def is_on(self) -> bool:
        return self.controller.days[self._index]

    async def async_turn_on(self, **kwargs: Any) -> None:
        self.controller.set_day(self._index, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        self.controller.set_day(self._index, False)


class ZoneManualSwitch(IrrigationEntity, SwitchEntity):
    """Avvia la singola zona per la sua durata, saltando il controllo pioggia."""

    _attr_icon = "mdi:water"

    def __init__(self, controller: IrrigationController, zone: Zone) -> None:
        super().__init__(controller, zone_manual_key(zone.id))
        self._zone_id = zone.id
        self._attr_name = zone.name

    @property
    def is_on(self) -> bool:
        return self.controller.is_running and self.controller.active_zone == self._zone_id

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        zone = self.controller.get_zone(self._zone_id)
        return {
            "valve_entity": zone.entity_id if zone else None,
            "zone_id": self._zone_id,
            "ends_at": self.controller.zone_ends_at.isoformat()
            if self.is_on and self.controller.zone_ends_at
            else None,
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.controller.async_start_zone(self._zone_id)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.controller.async_stop()
