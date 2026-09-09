"""Sensori: stato dell'impianto, ultimo e prossimo ciclo.

Il sensore di stato porta negli attributi la mappa completa delle entita'
dell'impianto: e' cosi' che la card grafica si configura da sola sapendo
soltanto il proprio entity_id.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util

from .const import (
    DAY_KEYS,
    DOMAIN,
    KEY_DAY_PREFIX,
    KEY_ENABLE,
    KEY_LAST_CYCLE,
    KEY_RESERVE,
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
        [
            StatusSensor(controller),
            LastCycleSensor(controller),
            NextCycleSensor(controller),
            ReserveSensor(controller),
        ]
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


class LastCycleSensor(IrrigationEntity, SensorEntity, RestoreEntity):
    """Quando e' finito l'ultimo ciclo andato a buon fine.

    Il valore vive nel controller, che riparte vuoto a ogni avvio: senza
    ripristino l'ultimo ciclo spariva a ogni riavvio di Home Assistant, anche
    se l'irrigazione era andata regolarmente la notte prima.
    """

    _attr_name = "Ultimo ciclo"
    _attr_icon = "mdi:history"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, controller: IrrigationController) -> None:
        super().__init__(controller, KEY_LAST_CYCLE)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if self.controller.last_cycle is not None:
            return
        last = await self.async_get_last_state()
        if last and last.state not in (None, "unknown", "unavailable"):
            ripristinato = dt_util.parse_datetime(last.state)
            if ripristinato is not None:
                self.controller.last_cycle = ripristinato

    @property
    def native_value(self) -> datetime | None:
        return self.controller.last_cycle


class ReserveSensor(IrrigationEntity, SensorEntity, RestoreEntity):
    """L'acqua stimata nella zona radicale, in millimetri.

    E' il ragionamento del bilancio idrico messo in vista: guardando questo
    numero e guardando il prato si capisce in due settimane se la capacita' e
    il consumo giornaliero sono tarati bene. Senza, il modello deciderebbe di
    nascosto.
    """

    _attr_name = "Riserva idrica"
    _attr_icon = "mdi:water-percent"
    _attr_native_unit_of_measurement = "mm"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    def __init__(self, controller: IrrigationController) -> None:
        super().__init__(controller, KEY_RESERVE)

    async def async_added_to_hass(self) -> None:
        """Ripristina la riserva: e' uno stato del terreno, non del programma.

        Azzerarla a ogni riavvio farebbe credere al modello che il prato sia
        asciutto proprio dopo un temporale.
        """
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last and last.state not in (None, "unknown", "unavailable"):
            try:
                self.controller.reserve = min(
                    self.controller.soil_capacity, max(0.0, float(last.state))
                )
            except (TypeError, ValueError):
                pass

    @property
    def available(self) -> bool:
        return self.controller.balance_enabled

    @property
    def native_value(self) -> float:
        return round(self.controller.reserve, 1)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        c = self.controller
        return {
            "capacity_mm": c.soil_capacity,
            "threshold_mm": c.reserve_threshold,
            "daily_et_mm": c.daily_et,
            "daily_et_applied_mm": round(c.daily_et * c.seasonal / 100.0, 1),
            "precip_rate_mm_h": c.precip_rate,
            "fill_pct": round(100 * c.reserve / c.soil_capacity) if c.soil_capacity else 0,
        }

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
