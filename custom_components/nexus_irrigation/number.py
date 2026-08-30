"""Number: durata base per zona e fattore stagionale."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DEFAULT_SEASONAL, DOMAIN, KEY_SEASONAL, zone_duration_key
from .controller import IrrigationController, Zone
from .entity import IrrigationEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    controller: IrrigationController = hass.data[DOMAIN][entry.entry_id]
    entities: list[NumberEntity] = [SeasonalNumber(controller)]
    entities += [ZoneDurationNumber(controller, zone) for zone in controller.zones]
    async_add_entities(entities)


class SeasonalNumber(IrrigationEntity, NumberEntity, RestoreEntity):
    """Scala tutte le durate con un solo cursore: 60% a maggio, 130% a luglio."""

    _attr_name = "Fattore stagionale"
    _attr_icon = "mdi:sun-thermometer"
    _attr_native_min_value = 0
    _attr_native_max_value = 200
    _attr_native_step = 5
    _attr_native_unit_of_measurement = "%"
    _attr_mode = NumberMode.SLIDER

    def __init__(self, controller: IrrigationController) -> None:
        super().__init__(controller, KEY_SEASONAL)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None:
            try:
                self.controller.set_seasonal(float(last.state))
            except (TypeError, ValueError):
                self.controller.set_seasonal(DEFAULT_SEASONAL)

    @property
    def native_value(self) -> float:
        return self.controller.seasonal

    async def async_set_native_value(self, value: float) -> None:
        self.controller.set_seasonal(value)


class ZoneDurationNumber(IrrigationEntity, NumberEntity, RestoreEntity):
    """Durata base della zona, prima del fattore stagionale."""

    _attr_icon = "mdi:timer-outline"
    _attr_native_min_value = 0
    _attr_native_max_value = 120
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "min"
    _attr_mode = NumberMode.SLIDER

    def __init__(self, controller: IrrigationController, zone: Zone) -> None:
        super().__init__(controller, zone_duration_key(zone.id))
        self._zone_id = zone.id
        self._default = zone.minutes
        self._attr_name = f"{zone.name} durata"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None:
            try:
                self.controller.set_zone_duration(self._zone_id, float(last.state))
            except (TypeError, ValueError):
                self.controller.set_zone_duration(self._zone_id, self._default)

    @property
    def native_value(self) -> float:
        zone = self.controller.get_zone(self._zone_id)
        return zone.duration if zone else self._default

    async def async_set_native_value(self, value: float) -> None:
        self.controller.set_zone_duration(self._zone_id, value)
