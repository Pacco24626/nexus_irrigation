"""Binary sensor: pioggia rilevata e ciclo in corso."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN, KEY_MASTER, KEY_RAIN, KEY_RUNNING, RAIN_NONE
from .controller import IrrigationController
from .entity import IrrigationEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    controller: IrrigationController = hass.data[DOMAIN][entry.entry_id]
    entities = [RainBinarySensor(controller), RunningBinarySensor(controller)]
    if controller.master_entity:
        entities.append(MasterBinarySensor(controller))
    async_add_entities(entities)


class RainBinarySensor(IrrigationEntity, BinarySensorEntity, RestoreEntity):
    """Esito dell'ultimo controllo pioggia.

    Vale quanto rilevato all'ultimo tentativo di ciclo: non e' un sensore
    meteo in tempo reale.
    """

    _attr_name = "Pioggia"
    _attr_icon = "mdi:weather-pouring"
    _attr_device_class = BinarySensorDeviceClass.MOISTURE

    def __init__(self, controller: IrrigationController) -> None:
        super().__init__(controller, KEY_RAIN)

    async def async_added_to_hass(self) -> None:
        """Rimette in circolo il registro della pioggia caduta.

        Vive solo in memoria: senza questo, ogni riavvio azzererebbe le ore
        passate proprio nei giorni di maltempo, quando servono.
        """
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last and isinstance(last.attributes.get("rain_log"), dict):
            self.controller.rain_log.update(
                {k: float(v) for k, v in last.attributes["rain_log"].items()}
            )
            self.controller.rain_recent = self.controller.recent_rain_mm()

    @property
    def available(self) -> bool:
        return self.controller.rain_mode != RAIN_NONE

    @property
    def is_on(self) -> bool:
        return self.controller.rain_detected

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "rain_mode": self.controller.rain_mode,
            "source": self.controller.rain_entity,
            "threshold_mm": self.controller.rain_threshold,
            "forecast_hours": self.controller.rain_hours,
            "past_hours": self.controller.rain_hours_past,
            "recent_mm": self.controller.rain_recent,
            "forecast_mm": self.controller.rain_forecast,
            "total_mm": round(
                self.controller.rain_recent + self.controller.rain_forecast, 1
            ),
            "rain_log": self.controller.rain_log,
        }


class RunningBinarySensor(IrrigationEntity, BinarySensorEntity):
    """Acceso mentre una zona sta irrigando."""

    _attr_name = "In irrigazione"
    _attr_icon = "mdi:water-pump"
    _attr_device_class = BinarySensorDeviceClass.RUNNING

    def __init__(self, controller: IrrigationController) -> None:
        super().__init__(controller, KEY_RUNNING)

    @property
    def is_on(self) -> bool:
        return self.controller.is_running


class MasterBinarySensor(IrrigationEntity, BinarySensorEntity):
    """Stato della valvola master o del rele' pompa.

    Creato solo se l'impianto ne ha uno: senza master l'entita' non esiste,
    invece di restare per sempre non disponibile.
    """

    _attr_name = "Master"
    _attr_icon = "mdi:pump"
    _attr_device_class = BinarySensorDeviceClass.OPENING

    def __init__(self, controller: IrrigationController) -> None:
        super().__init__(controller, KEY_MASTER)

    @property
    def is_on(self) -> bool:
        return self.controller.master_open

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "master_valve": self.controller.master_entity,
            "lead_seconds": self.controller.master_lead,
            "lag_seconds": self.controller.master_lag,
        }
