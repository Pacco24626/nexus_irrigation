"""Number: durata base per zona e fattore stagionale."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    DEFAULT_CICLO_GIORNI,
    DEFAULT_SEASONAL,
    DOMAIN,
    KEY_CYCLE_DAYS,
    KEY_SEASONAL,
    zone_divider_key,
    zone_duration_key,
)
from .controller import IrrigationController, Zone
from .entity import IrrigationEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    controller: IrrigationController = hass.data[DOMAIN][entry.entry_id]
    entities: list[NumberEntity] = [
        SeasonalNumber(controller),
        CycleDaysNumber(controller),
    ]
    entities += [ZoneDurationNumber(controller, zone) for zone in controller.zones]
    entities += [ZoneDividerNumber(controller, zone) for zone in controller.zones]
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


class CycleDaysNumber(IrrigationEntity, NumberEntity, RestoreEntity):
    """Ogni quanti giorni si irriga, in modalita' ciclica.

    Vale solo quando la modalita' giorni e' impostata su ciclico: negli altri
    modi il valore resta li' senza effetto.
    """

    _attr_name = "Intervallo giorni"
    _attr_icon = "mdi:calendar-refresh"
    _attr_native_min_value = 1
    _attr_native_max_value = 30
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "giorni"
    _attr_mode = NumberMode.BOX

    def __init__(self, controller: IrrigationController) -> None:
        super().__init__(controller, KEY_CYCLE_DAYS)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        try:
            self.controller.set_cycle_days(int(float(last.state)))
        except (AttributeError, TypeError, ValueError):
            self.controller.set_cycle_days(DEFAULT_CICLO_GIORNI)

    @property
    def native_value(self) -> float:
        return self.controller.cycle_days

    async def async_set_native_value(self, value: float) -> None:
        self.controller.set_cycle_days(int(value))


class ZoneDividerNumber(IrrigationEntity, NumberEntity, RestoreEntity):
    """Ogni quanti cicli tocca a questa zona.

    E' la versione economica dei programmi separati per zona: il prato a ogni
    giro, la siepe una volta su tre. Costa un numero invece di un secondo
    calendario, e copre il caso che serve davvero.
    """

    _attr_icon = "mdi:numeric"
    _attr_native_min_value = 1
    _attr_native_max_value = 10
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "cicli"
    _attr_mode = NumberMode.BOX

    def __init__(self, controller: IrrigationController, zone: Zone) -> None:
        super().__init__(controller, zone_divider_key(zone.id))
        self._zone_id = zone.id
        self._attr_name = f"{zone.name} ogni"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        try:
            self.controller.set_zone_divider(self._zone_id, int(float(last.state)))
        except (AttributeError, TypeError, ValueError):
            self.controller.set_zone_divider(self._zone_id, 1)

    @property
    def native_value(self) -> float:
        for zone in self.controller.zones:
            if zone.id == self._zone_id:
                return zone.divider
        return 1

    async def async_set_native_value(self, value: float) -> None:
        self.controller.set_zone_divider(self._zone_id, int(value))

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
