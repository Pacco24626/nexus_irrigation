"""Sensori: stato dell'impianto, ultimo e prossimo ciclo.

Il sensore di stato porta negli attributi la mappa completa delle entita'
dell'impianto: e' cosi' che la card grafica si configura da sola sapendo
soltanto il proprio entity_id.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DAY_KEYS,
    DOMAIN,
    KEY_DAY_PREFIX,
    KEY_ENABLE,
    KEY_LAST_CYCLE,
    KEY_MASTER,
    KEY_NEXT_CYCLE,
    KEY_RAIN,
    KEY_SEASONAL,
    KEY_START_CYCLE,
    KEY_START_TIME,
    KEY_STATUS,
    KEY_STOP,
    STATUS_OPTIONS,
    zone_duration_key,
    zone_manual_key,
)
from .controller import IrrigationController
from .entity import IrrigationEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    controller: IrrigationController = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [StatusSensor(controller), LastCycleSensor(controller), NextCycleSensor(controller)]
    )


class StatusSensor(IrrigationEntity, SensorEntity):
    """Stato corrente dell'impianto, piu' la mappa delle entita' per la card."""

    _attr_name = "Stato"
    _attr_icon = "mdi:sprinkler"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = STATUS_OPTIONS
    _attr_translation_key = "status"

    def __init__(self, controller: IrrigationController) -> None:
        super().__init__(controller, KEY_STATUS)

    @property
    def native_value(self) -> str:
        return self.controller.status

    def _entity_id(self, platform: str, key: str) -> str | None:
        return er.async_get(self.hass).async_get_entity_id(
            platform, DOMAIN, f"{self.controller.entry.entry_id}_{key}"
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        controller = self.controller
        active = controller.active_zone

        zones = []
        for zone in controller.zones:
            zones.append(
                {
                    "id": zone.id,
                    "name": zone.name,
                    "valve": zone.entity_id,
                    "duration_entity": self._entity_id("number", zone_duration_key(zone.id)),
                    "manual_entity": self._entity_id("switch", zone_manual_key(zone.id)),
                    "running": active == zone.id,
                    "seconds": controller.zone_seconds(zone),
                }
            )

        return {
            "installation": controller.name,
            "zones": zones,
            "active_zone": active,
            "zone_ends_at": controller.zone_ends_at.isoformat()
            if controller.zone_ends_at
            else None,
            "enable_entity": self._entity_id("switch", KEY_ENABLE),
            "start_time_entity": self._entity_id("time", KEY_START_TIME),
            "seasonal_entity": self._entity_id("number", KEY_SEASONAL),
            "start_button": self._entity_id("button", KEY_START_CYCLE),
            "stop_button": self._entity_id("button", KEY_STOP),
            "rain_entity": self._entity_id("binary_sensor", KEY_RAIN),
            "master_entity": self._entity_id("binary_sensor", KEY_MASTER)
            if controller.master_entity
            else None,
            "master_valve": controller.master_entity,
            "master_open": controller.master_open,
            "day_entities": [
                self._entity_id("switch", f"{KEY_DAY_PREFIX}{day}") for day in DAY_KEYS
            ],
            "rain_mode": controller.rain_mode,
            "rain_source": controller.rain_entity,
            "next_cycle": controller.next_cycle.isoformat() if controller.next_cycle else None,
            "last_cycle": controller.last_cycle.isoformat() if controller.last_cycle else None,
        }


class LastCycleSensor(IrrigationEntity, SensorEntity):
    """Quando e' finito l'ultimo ciclo andato a buon fine."""

    _attr_name = "Ultimo ciclo"
    _attr_icon = "mdi:history"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, controller: IrrigationController) -> None:
        super().__init__(controller, KEY_LAST_CYCLE)

    @property
    def native_value(self) -> datetime | None:
        return self.controller.last_cycle


class NextCycleSensor(IrrigationEntity, SensorEntity):
    """Prossimo avvio automatico, o niente se l'impianto e' disabilitato."""

    _attr_name = "Prossimo ciclo"
    _attr_icon = "mdi:calendar-clock"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, controller: IrrigationController) -> None:
        super().__init__(controller, KEY_NEXT_CYCLE)

    @property
    def native_value(self) -> datetime | None:
        return self.controller.next_cycle
