"""Integrazione Nexus Irrigation: centralina irrigazione multizona."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PLATFORMS
from .controller import IrrigationController


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Configura un impianto."""
    controller = IrrigationController(hass, entry)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = controller

    await controller.async_setup()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Scarica un impianto, chiudendo le valvole."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        controller: IrrigationController = hass.data[DOMAIN].pop(entry.entry_id)
        await controller.async_shutdown()
    return unload_ok


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Ricarica dopo una modifica dalle opzioni."""
    await hass.config_entries.async_reload(entry.entry_id)
