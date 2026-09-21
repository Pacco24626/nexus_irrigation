"""Integrazione Nexus Irrigation: centralina irrigazione multizona.

La scheda animata la serve e la registra l'integrazione: nessuna risorsa da
aggiungere a mano, e l'URL porta la versione, cosi' dopo un aggiornamento il
browser ricarica il file invece di usare quello in cache.
"""

from __future__ import annotations

import logging
import os
from urllib.parse import urlsplit

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from .const import CARD_FILE, CARD_URL_BASE, DOMAIN, PLATFORMS
from .controller import IrrigationController

_LOGGER = logging.getLogger(__name__)

# La risorsa della scheda si riconosce dal percorso completo. Dal solo nome del
# file si prenderebbe anche quella della vecchia card separata, che HACS serve
# da /hacsfiles/nexus_irrigation_card/ con lo stesso nome.
CARD_PATH = f"{CARD_URL_BASE}/{CARD_FILE}"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Configura un impianto."""
    try:
        await _async_registra_card(hass)
    except Exception as err:  # noqa: BLE001
        # La scheda e' una vetrina: se non si registra, l'impianto deve partire
        # lo stesso, con le valvole chiuse e il watchdog attivo.
        _LOGGER.warning("Scheda non registrata (%s): l'impianto funziona comunque", err)

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


# -----------------------------------------------------------------------------
# Scheda Lovelace
# -----------------------------------------------------------------------------
async def _async_registra_card(hass: HomeAssistant) -> None:
    """Serve la scheda e la registra come risorsa, una volta sola per avvio."""
    dominio = hass.data.setdefault(DOMAIN, {})
    if dominio.get("card_registrata"):
        return

    www = os.path.join(os.path.dirname(__file__), "www")
    if not await hass.async_add_executor_job(os.path.isdir, www):
        _LOGGER.warning("Cartella www assente: la scheda non verra' servita")
        return

    try:
        await hass.http.async_register_static_paths([StaticPathConfig(CARD_URL_BASE, www, False)])
    except RuntimeError as err:
        _LOGGER.debug("Percorso statico gia' registrato: %s", err)

    integrazione = await async_get_integration(hass, DOMAIN)
    url = f"{CARD_PATH}?v={integrazione.version}"

    if hass.is_running:
        await _async_registra_risorsa(hass, url)
    else:
        async def _dopo_avvio(_event) -> None:
            await _async_registra_risorsa(hass, url)

        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _dopo_avvio)

    dominio["card_registrata"] = True


def _percorso(risorsa: dict) -> str:
    """Il percorso dell'URL di una risorsa, senza la versione in coda."""
    return urlsplit(risorsa.get("url") or "").path


async def _async_registra_risorsa(hass: HomeAssistant, url: str) -> None:
    """Registra la scheda come risorsa Lovelace.

    E' l'unico meccanismo che Lovelace attende prima di disegnare: con il solo
    add_extra_js_url la plancia puo' disegnare prima che la scheda sia definita
    e mostrare «Custom element doesn't exist». Il ripiego resta per chi ha
    Lovelace in modalita' YAML, dove le risorse non si scrivono da codice.
    """
    lovelace = hass.data.get("lovelace")
    risorse = getattr(lovelace, "resources", None)
    if risorse is None and isinstance(lovelace, dict):
        risorse = lovelace.get("resources")
    if risorse is None:
        add_extra_js_url(hass, url)
        return

    try:
        await risorse.async_get_info()
        voci = list(risorse.async_items())
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning(
            "Impossibile leggere le risorse Lovelace (%s). Aggiungi a mano la scheda come modulo JavaScript: %s",
            err,
            url,
        )
        add_extra_js_url(hass, url)
        return

    esistente = next((r for r in voci if _percorso(r) == CARD_PATH), None)
    if not hasattr(risorse, "async_create_item"):
        # Lovelace in modalita' YAML: le risorse le scrive l'utente e da codice
        # si possono solo leggere. Se la scheda c'e' gia' la si lascia com'e',
        # altrimenti la si carica come modulo extra, senza allarmi nel log.
        if esistente is None:
            add_extra_js_url(hass, url)
            _LOGGER.info("Lovelace in modalita' YAML: scheda caricata come modulo extra (%s)", url)
        elif esistente.get("url") != url:
            _LOGGER.info(
                "Lovelace in modalita' YAML: la risorsa della scheda e' %s, aggiornala a %s",
                esistente.get("url"),
                url,
            )
    else:
        try:
            if esistente is None:
                await risorse.async_create_item({"res_type": "module", "url": url})
                _LOGGER.info("Risorsa Lovelace della scheda creata: %s", url)
            elif esistente.get("url") != url:
                await risorse.async_update_item(esistente["id"], {"url": url})
                _LOGGER.info("Risorsa Lovelace della scheda aggiornata: %s", url)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning(
                "Impossibile registrare la risorsa Lovelace (%s). Aggiungila a mano come modulo JavaScript: %s",
                err,
                url,
            )
            add_extra_js_url(hass, url)

    # Due file che definiscono lo stesso elemento: vince chi arriva prima, e
    # potrebbe essere la vecchia card.
    vecchie = [
        r.get("url")
        for r in voci
        if _percorso(r) != CARD_PATH and _percorso(r).endswith(f"/{CARD_FILE}")
    ]
    if vecchie:
        _LOGGER.warning(
            "La vecchia Nexus Irrigation Card e' ancora fra le risorse (%s): "
            "rimuovila da HACS, la scheda ora e' inclusa nell'integrazione",
            ", ".join(vecchie),
        )
