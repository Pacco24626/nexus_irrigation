"""Prove a tavolino del sensore pioggia e dei cicli saltati.

Il caso di partenza e' quello visto sul campo l'11/09/2026: bilancio idrico
attivo, riserva a 24,2 mm sopra la soglia di 10, un solo millimetro di pioggia
fra caduta e prevista. Il ciclo va saltato, ma per la riserva: il sensore
«Pioggia» non deve accendersi e lo stato non deve dire «Saltato per pioggia».

    python tests/test_pioggia.py

Con NEXUS_IRRIGATION_SRC puntato alla 1.4.1 le prove che riguardano il
difetto devono fallire; quelle di controllo devono passare su entrambe.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import finto_ha  # noqa: E402
from finto_ha import NOTIFICHE, OROLOGIO, Entry, Esiti, Hass, azzera  # noqa: E402

from nexus_irrigation import const  # noqa: E402
from nexus_irrigation.binary_sensor import RainBinarySensor  # noqa: E402
from nexus_irrigation.controller import IrrigationController  # noqa: E402

esiti = Esiti("PIOGGIA")
v = esiti.verifica

BASE = {
    "name": "Prova",
    "zones": [],
    "rain_mode": "weather",
    "rain_entity": "weather.casa",
    "rain_threshold": 2.0,
    "rain_hours": 12,
    "rain_hours_past": 12,
    "soil_capacity": 25.0,
    "reserve_threshold": 10.0,
}


async def cedi(volte: int = 10) -> None:
    for _ in range(volte):
        await asyncio.sleep(0)


async def impianto(pioggia_oraria=None, stati=None, **cfg):
    azzera()
    hass = Hass()
    hass.services.pioggia_oraria = list(pioggia_oraria or [0.0] * 12)
    for entita, valore in (stati or {}).items():
        hass.states.imposta(entita, valore)
    controller = IrrigationController(hass, Entry({**BASE, **cfg}))
    await controller.async_setup()
    await cedi()
    return hass, controller


def ora(delta_ore: int) -> str:
    """Chiave del registro pioggia (ora UTC, come le previsioni) relativa all'orologio."""
    from datetime import timedelta, timezone

    return (OROLOGIO.adesso + timedelta(hours=delta_ore)).astimezone(timezone.utc).isoformat()[:13]


def attributi(controller) -> dict:
    return RainBinarySensor(controller).extra_state_attributes


def acceso(controller) -> bool:
    return RainBinarySensor(controller).is_on


async def caso_campo() -> None:
    print("\n1. Il caso dell'11/09: salto per riserva, un millimetro di pioggia")
    hass, c = await impianto()
    c.reserve = 24.2
    c.rain_log[ora(-3)] = 1.0
    await c._async_run_cycle(True)
    v(c.last_cycle is None, "il ciclo non parte (riserva 24,2 sopra la soglia 10)")
    v(c.status == "reserve_skipped", f"stato «reserve_skipped», non «rain_skipped» (e' {c.status})")
    v(not acceso(c), "il sensore Pioggia resta spento: 1 mm e' sotto la soglia di 2")
    motivo = attributi(c).get("motivo", "")
    v("riserva" not in motivo.lower(), "il sensore Pioggia non porta il motivo della riserva")
    v(len(NOTIFICHE) == 1 and "riserva" in NOTIFICHE[0]["message"].lower(),
      "la notifica spiega che ha deciso la riserva")
    v(attributi(c).get("threshold_mm") == 2.0 and attributi(c).get("total_mm") == 1.0,
      "gli attributi del sensore Pioggia descrivono la pioggia (1 mm su soglia 2)")


async def caso_riserva_bassa_con_pioggia() -> None:
    print("\n2. Bilancio attivo, riserva bassa, 3 mm previsti: si irriga, ma piove")
    hass, c = await impianto(pioggia_oraria=[1.0, 1.0, 1.0] + [0.0] * 9)
    c.reserve = 5.0
    await c._async_run_cycle(True)
    v(c.last_cycle is not None, "il ciclo parte (5 + 3 = 8 mm, sotto la soglia di 10)")
    v(c.status == "idle", f"a ciclo finito lo stato e' «idle» (e' {c.status})")
    v(acceso(c), "il sensore Pioggia e' acceso: 3 mm previsti, sopra la soglia di 2")
    v("3.0" in attributi(c).get("motivo", ""), "il motivo cita i millimetri previsti")


async def caso_senza_bilancio() -> None:
    print("\n3. Senza bilancio (controllo): la soglia pioggia decide come prima")
    hass, c = await impianto(pioggia_oraria=[1.0, 1.0, 1.0] + [0.0] * 9, soil_capacity=0.0)
    await c._async_run_cycle(True)
    v(c.last_cycle is None, "3 mm sopra la soglia di 2: ciclo saltato")
    v(c.status == "rain_skipped", f"stato «rain_skipped» (e' {c.status})")
    v(acceso(c), "sensore Pioggia acceso")
    v(len(NOTIFICHE) == 1 and "previsti" in NOTIFICHE[0]["message"], "la notifica spiega la pioggia")

    hass, c = await impianto(pioggia_oraria=[1.0] + [0.0] * 11, soil_capacity=0.0)
    await c._async_run_cycle(True)
    v(c.last_cycle is not None, "1 mm sotto la soglia: il ciclo parte")
    v(not acceso(c) and not NOTIFICHE, "sensore spento e nessuna notifica")


async def caso_aggiornamento_continuo() -> None:
    print("\n4. Meteo: il sensore segue la pioggia anche senza un ciclo")
    hass, c = await impianto()
    v(not acceso(c), "all'avvio, cielo asciutto: spento")
    hass.services.pioggia_oraria = [2.0, 2.0, 1.0] + [0.0] * 9
    await c._async_sample_rain()
    v(acceso(c), "arrivano 5 mm previsti: si accende al campione, senza aspettare un ciclo")
    v(c.status == "idle" and not NOTIFICHE, "lo stato dell'impianto non cambia e non parte nessuna notifica")
    hass.services.pioggia_oraria = [0.0] * 12
    OROLOGIO.avanza(hours=15)
    await c._async_sample_rain()
    v(not acceso(c), "quindici ore dopo, pioggia fuori dalla finestra di 12 e cielo sereno: si spegne")


async def caso_sensore_binario() -> None:
    print("\n5. Pluviometro a contatto: il sensore segue lo stato, non l'ultimo ciclo")
    hass, c = await impianto(
        stati={"binary_sensor.pluviometro": "on"},
        rain_mode="sensor", rain_entity="binary_sensor.pluviometro",
    )
    await c._async_run_cycle(True)
    v(c.status == "rain_skipped" and acceso(c), "bagnato: ciclo saltato per pioggia, sensore acceso")
    hass.states.imposta("binary_sensor.pluviometro", "off")
    await cedi()
    v(not acceso(c), "il pluviometro si asciuga: il sensore si spegne senza aspettare il ciclo")


async def caso_sensore_numerico() -> None:
    print("\n6. Pluviometro in millimetri")
    hass, c = await impianto(
        stati={"sensor.pioggia_mm": "3.5"}, rain_mode="sensor", rain_entity="sensor.pioggia_mm",
    )
    v(acceso(c), "3,5 mm sopra la soglia: acceso gia' all'avvio")
    await c._async_run_cycle(True)
    v(c.status == "rain_skipped", "ciclo saltato per pioggia")
    hass.states.imposta("sensor.pioggia_mm", "0.5")
    await cedi()
    v(not acceso(c), "scende a 0,5 mm: spento")
    hass.states.imposta("sensor.pioggia_mm", "unavailable")
    await cedi()
    await c._async_run_cycle(True)
    v(c.last_cycle is not None and not acceso(c), "pluviometro non disponibile: si irriga, sensore spento")


async def caso_bypass() -> None:
    print("\n7. Ignora la pioggia (controllo)")
    hass, c = await impianto(pioggia_oraria=[5.0] + [0.0] * 11, soil_capacity=0.0)
    c.set_rain_bypass(True)
    await c._async_run_cycle(True)
    v(c.last_cycle is not None and c.status == "idle", "con il bypass il ciclo parte anche se piove")
    v(not NOTIFICHE, "nessuna notifica di salto")


async def caso_ora_contata_due_volte() -> None:
    print("\n8. La prima ora prevista si conta una volta sola")
    hass, c = await impianto(pioggia_oraria=[1.0] + [0.0] * 11, soil_capacity=0.0)
    v(c.rain_log.get(ora(1)) == 1.0, "il campione ha registrato l'ora successiva (1 mm)")
    await c._async_run_cycle(True)
    v(attributi(c).get("total_mm") == 1.0, f"totale 1 mm, non 2 (e' {attributi(c).get('total_mm')})")
    v(c.last_cycle is not None and not acceso(c), "1 mm sotto la soglia di 2: si irriga, sensore spento")

    hass, c = await impianto()
    c.reserve = 8.0
    hass.services.pioggia_oraria = [1.5] + [0.0] * 11
    await c._async_sample_rain()
    v(abs(c.reserve - 9.5) < 0.01, f"col bilancio la riserva accredita l'ora prevista una volta (9,5; e' {c.reserve:.1f})")
    await c._async_run_cycle(True)
    v(c.last_cycle is not None, "9,5 mm di riserva senza ricontare 1,5 previsti: sotto 10, si irriga")


async def caso_finestra_in_utc() -> None:
    print("\n9. La finestra delle ore passate e' quella giusta anche con il fuso")
    hass, c = await impianto(soil_capacity=0.0)
    c.rain_log[ora(-11)] = 1.0
    c.rain_log[ora(-13)] = 1.5
    v(c.recent_rain_mm() == 1.0, f"conta la pioggia di 11 ore fa e non quella di 13 (e' {c.recent_rain_mm()})")


async def caso_attributi_riscritti() -> None:
    print("\n10. Il registro cambiato arriva a Home Assistant")
    hass, c = await impianto()
    # Home Assistant tiene una copia superficiale degli attributi e riscrive
    # lo stato solo se i nuovi sono diversi da quella.
    salvati = dict(attributi(c))
    OROLOGIO.avanza(hours=1)
    await c._async_sample_rain()
    nuovi = attributi(c)
    v(len(nuovi["rain_log"]) == 2, "dopo un'ora il registro ha una voce in piu'")
    v(nuovi != salvati, "gli attributi risultano cambiati, quindi lo stato viene riscritto")


def caso_traduzioni() -> None:
    print("\n11. Il nuovo stato e' dichiarato e tradotto")
    v("reserve_skipped" in getattr(const, "STATUS_OPTIONS", []), "fra le opzioni del sensore Stato")
    base = os.path.join(os.path.dirname(finto_ha._SRC), "custom_components", "nexus_irrigation")
    if not os.path.isdir(base):
        base = os.path.join(finto_ha._SRC, "nexus_irrigation")
    for nome in ("strings.json", "translations/it.json", "translations/en.json"):
        with open(os.path.join(base, nome), encoding="utf-8") as f:
            stati = json.load(f)["entity"]["sensor"]["status"]["state"]
        v("reserve_skipped" in stati, f"{nome}: «{stati.get('reserve_skipped', '-')}»")


async def main() -> None:
    await caso_campo()
    await caso_riserva_bassa_con_pioggia()
    await caso_senza_bilancio()
    await caso_aggiornamento_continuo()
    await caso_sensore_binario()
    await caso_sensore_numerico()
    await caso_bypass()
    await caso_ora_contata_due_volte()
    await caso_finestra_in_utc()
    await caso_attributi_riscritti()
    caso_traduzioni()
    esiti.chiudi()


asyncio.run(main())
