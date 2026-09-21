"""Prove a tavolino della mappa per la scheda animata (1.6.0).

Il sensore Stato porta alla scheda il tipo di ogni zona e il giro: le zone che
ne fanno parte, quelle fatte, quelle che non hanno aperto, la valvola in attesa
di conferma, la zona avviata a mano. Piu' pioggia e riserva per la testata, e
l'integrazione serve e registra la scheda come risorsa Lovelace.

    python tests/test_mappa.py

Il tempo del controller e' finto: ogni attesa resta ferma finche' la prova non
la libera, cosi' il giro si guarda a meta', in pausa o con una valvola che non
risponde. Con NEXUS_IRRIGATION_SRC puntato alla 1.5.0 le prove devono fallire;
quelle marcate «controllo» passano su entrambe e dicono che il banco regge.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import finto_ha  # noqa: E402
from finto_ha import JS_EXTRA, OROLOGIO, Entry, Esiti, Hass, azzera  # noqa: E402

import nexus_irrigation as integrazione  # noqa: E402
from nexus_irrigation import controller as modulo_controller  # noqa: E402
from nexus_irrigation.config_flow import (  # noqa: E402
    NexusIrrigationConfigFlow,
    NexusIrrigationOptionsFlow,
)
from nexus_irrigation.controller import IrrigationController  # noqa: E402
from nexus_irrigation.sensor import Et0Sensor, StatusSensor  # noqa: E402

esiti = Esiti("MAPPA")
v = esiti.verifica

URL_SCHEDA = "/nexus_irrigation/nexus-irrigation-card.js"
VECCHIA = {
    "id": "r1",
    "res_type": "module",
    "url": "/hacsfiles/nexus_irrigation_card/nexus-irrigation-card.js?hacstag=436958211",
}


# --- log ------------------------------------------------------------------------
class _Registro(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.WARNING)
        self.messaggi: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messaggi.append(record.getMessage())


LOG = _Registro()
logging.getLogger("nexus_irrigation").addHandler(LOG)


# --- tempo finto ------------------------------------------------------------------
async def cedi(volte: int = 10) -> None:
    for _ in range(volte):
        await asyncio.sleep(0)


class Tempo:
    """Prende il posto di asyncio.sleep nel controller.

    Ogni attesa resta ferma finche' la prova non la libera, e il tempo liberato
    fa avanzare l'orologio finto: anche quello con cui il controller conta i
    sei secondi di attesa della conferma di apertura.
    """

    def __init__(self) -> None:
        self.attese: list[tuple[float, asyncio.Future]] = []
        self.modulo = types.SimpleNamespace(
            sleep=self.sleep, CancelledError=asyncio.CancelledError, Task=asyncio.Task
        )

    async def sleep(self, secondi: float) -> None:
        voce = (secondi, asyncio.get_running_loop().create_future())
        self.attese.append(voce)
        try:
            await voce[1]
        finally:
            if voce in self.attese:
                self.attese.remove(voce)

    async def libera(self) -> None:
        """Lascia finire l'attesa in corso."""
        await cedi()
        if self.attese:
            secondi, attesa = self.attese[0]
            OROLOGIO.avanza(seconds=secondi)
            if not attesa.done():
                attesa.set_result(None)
        await cedi()

    async def fino_a(self, condizione, massimo: int = 200) -> bool:
        for _ in range(massimo):
            await cedi()
            if condizione():
                return True
            if not self.attese:
                return False
            await self.libera()
        return condizione()


# --- impianto finto ---------------------------------------------------------------
def zona(n: int, minuti: float = 10, **extra) -> dict:
    """Una zona come la salva il config flow; senza `type` e' una zona della 1.5.0."""
    return {
        "id": f"zone_{n}",
        "name": f"Zona {n}",
        "entity_id": f"switch.valvola_{n}",
        "minutes": minuti,
        **extra,
    }


async def impianto(zone: list[dict], **cfg):
    azzera()
    LOG.messaggi.clear()
    hass = Hass()
    # Il controller conta l'attesa dell'apertura con l'orologio del loop.
    hass.loop = types.SimpleNamespace(time=lambda: OROLOGIO.adesso.timestamp())
    tempo = Tempo()
    modulo_controller.asyncio = tempo.modulo
    c = IrrigationController(hass, Entry({"name": "Prova", "zones": zone, "rain_mode": "none", **cfg}))
    await c.async_setup()
    await cedi()
    sensore = StatusSensor(c)
    sensore.hass = hass
    return hass, c, sensore, tempo


def elenco(attributi: dict, chiave: str) -> list:
    """Un campo di ogni zona, None dove manca."""
    return [z.get(chiave) for z in attributi.get("zones", [])]


# --- 1. tipo di zona ----------------------------------------------------------------
async def caso_tipo_zona() -> None:
    print("\n1. Tipo di zona: le zone salvate prima della 1.6.0 valgono prato")
    hass, c, s, _ = await impianto([zona(1), zona(2, type="drip"), zona(3, type="inventato")])
    v(len(c.zones) == 3, "controllo: tre zone caricate")
    v(getattr(c.zones[0], "tipo", None) == "lawn", "zona senza tipo (salvata dalla 1.5.0): prato")
    v(getattr(c.zones[1], "tipo", None) == "drip", "zona salvata come goccia: goccia")
    v(getattr(c.zones[2], "tipo", None) == "lawn",
      "tipo sconosciuto: prato, la scheda non riceve valori che non sa disegnare")
    a = s.extra_state_attributes
    v(elenco(a, "tipo") == ["lawn", "drip", "lawn"], f"zones[].tipo nel sensore (e' {elenco(a, 'tipo')})")


# --- 2. config flow -----------------------------------------------------------------
def campo(risultato: dict, nome: str):
    """La chiave dello schema con quel nome, o None."""
    return next((k for k in (risultato.get("schema") or {}) if str(k) == nome), None)


def suggerito(risultato: dict, nome: str):
    chiave = campo(risultato, nome)
    return ((chiave.description or {}) if chiave is not None else {}).get("suggested_value")


async def caso_config_flow() -> None:
    print("\n2. Config flow e opzioni: il tipo si sceglie e si salva")
    flusso = NexusIrrigationConfigFlow()
    r = await flusso.async_step_user({"name": "Prova"})
    v(r["step_id"] == "zone", "controllo: dopo il nome si chiede la prima zona")
    chiave = campo(r, "type")
    v(chiave is not None and chiave.default == "lawn", "passo zona: campo tipo, predefinito prato")
    selettore = r["schema"].get(chiave) if chiave is not None else None
    config = getattr(selettore, "config", {}) or {}
    v(config.get("translation_key") == "zone_type" and config.get("options") == ["lawn", "drip"],
      "selettore con translation_key zone_type e le opzioni prato e goccia")

    r = await flusso.async_step_zone(
        {"name": "Aiuola", "entity_id": "switch.valvola_1", "type": "drip", "minutes": 8, "add_another": True}
    )
    r = await flusso.async_step_zone(
        {"name": "Prato", "entity_id": "switch.valvola_2", "type": "lawn", "minutes": 20, "add_another": False}
    )
    r = await flusso.async_step_master({"use_master": False})
    r = await flusso.async_step_rain({"rain_mode": "none"})
    v(r["type"] == "create_entry" and len(r["data"]["zones"]) == 2, "controllo: impianto creato con due zone")
    tipi = [z.get("type") for z in r["data"]["zones"]]
    v(tipi == ["drip", "lawn"], f"il tipo si salva con la zona (e' {tipi})")
    c = IrrigationController(Hass(), Entry(r["data"]))
    v([getattr(z, "tipo", None) for z in c.zones] == ["drip", "lawn"], "e il controller lo legge")

    voce = Entry({"name": "Prova", "zones": [zona(1, type="drip"), zona(2)], "rain_mode": "none"})
    opzioni = NexusIrrigationOptionsFlow()
    opzioni.config_entry = voce
    r = await opzioni.async_step_zones()
    v(r["step_id"] == "zone" and suggerito(r, "name") == "Zona 1", "controllo: opzioni, zona 1 precompilata")
    v(suggerito(r, "type") == "drip", "opzioni, zona 1: proposto il tipo salvato (goccia)")
    r = await opzioni.async_step_zone(
        {"name": "Zona 1", "entity_id": "switch.valvola_1", "type": "drip", "minutes": 10, "add_another": True}
    )
    chiave = campo(r, "type")
    v(chiave is not None and suggerito(r, "type") is None and chiave.default == "lawn",
      "opzioni, zona 2 salvata senza tipo: nessuna proposta, resta il predefinito prato")
    r = await opzioni.async_step_zone(
        {"name": "Zona 2", "entity_id": "switch.valvola_2", "type": "drip", "minutes": 10, "add_another": False}
    )
    tipi = [z.get("type") for z in r["data"]["zones"]]
    v(tipi == ["drip", "drip"], f"il tipo cambiato dalle opzioni si salva (e' {tipi})")


# --- 3. da fermo --------------------------------------------------------------------
async def caso_da_fermo() -> None:
    print("\n3. Da fermo: il prossimo giro, senza la zona «ogni 2» e senza quella a 0 minuti")
    hass, c, s, _ = await impianto([zona(1), zona(2), zona(3, minuti=0)])
    c.set_zone_divider("zone_2", 2)
    c.cycle_count = 1
    c.set_seasonal(70.0)
    a = s.extra_state_attributes
    v(a["active_zone"] is None and c.status == "idle", "controllo: impianto fermo")
    v(a.get("ruolo") == "mappa_irrigazione", "ruolo «mappa_irrigazione»")
    v(a.get("ciclo") == ["zone_1"], f"ciclo = solo la zona 1 (e' {a.get('ciclo')})")
    v(elenco(a, "in_ciclo") == [True, False, False], f"in_ciclo per zona (e' {elenco(a, 'in_ciclo')})")
    v(a.get("ciclo_fatte") == [] and a.get("ciclo_non_aperte") == [], "niente di fatto e niente di fallito")
    v(a.get("in_apertura") is False and a.get("manuale") is False, "in_apertura e manuale false")
    v(a.get("pausa_fra_zone") == 15 and a.get("master_lead") == 0, "senza master: pausa 15 s, anticipo 0")
    v(a.get("seasonal") == 70.0, f"seasonal 70.0 (e' {a.get('seasonal')})")
    v(a.get("consumo_prato_mm") == 2.8, f"consumo del prato senza ET0: 4 mm x 70% = 2.8 (e' {a.get('consumo_prato_mm')})")

    c.cycle_count = 2
    a = s.extra_state_attributes
    v(a.get("ciclo") == ["zone_1", "zone_2"], "al giro pari la zona 2 rientra")
    c.set_zone_duration("zone_1", 12.5)
    minuti = elenco(s.extra_state_attributes, "minutes")
    v(minuti == [12.5, 10.0, 0.0] and all(isinstance(m, float) for m in minuti),
      f"minutes e' la durata base corrente, in float (e' {minuti})")

    hass, c, s, _ = await impianto([zona(1)], master_entity="switch.pompa", master_lead=4, master_lag=20)
    a = s.extra_state_attributes
    v(a["master_valve"] == "switch.pompa", "controllo: master configurato")
    v(a.get("pausa_fra_zone") == 25 and a.get("master_lead") == 4,
      "con master: pausa = lag + 5 = 25 s, anticipo 4 s, come nel ciclo vero")
    hass, c, s, _ = await impianto([zona(1)], master_entity="switch.pompa", master_lead=3, master_lag=3)
    v(s.extra_state_attributes.get("pausa_fra_zone") == 15, "con master e lag corto la pausa resta 15 s")


# --- 4. durante un giro -------------------------------------------------------------
async def caso_giro() -> None:
    print("\n4. Un giro: fatta, pausa, valvola che non apre, arresto a meta'")
    hass, c, s, tempo = await impianto([zona(1, minuti=1), zona(2, minuti=1), zona(3, minuti=1)])
    hass.services.guaste.add("switch.valvola_2")
    await c.async_start_cycle(check_rain=False)
    await cedi()
    a = s.extra_state_attributes
    v(c.status == "running" and a["active_zone"] == "zone_1", "controllo: parte la zona 1")
    v(a.get("ciclo") == ["zone_1", "zone_2", "zone_3"], f"ciclo = le zone del giro (e' {a.get('ciclo')})")
    v(a.get("ciclo_fatte") == [] and a.get("in_apertura") is False and a.get("manuale") is False,
      "zona 1 aperta al primo colpo: non in apertura, niente di fatto, non a mano")
    doppia = s.extra_state_attributes
    v(isinstance(a.get("ciclo"), list) and a["ciclo"] is not doppia["ciclo"],
      "durante il giro il ciclo e' una lista nuova a ogni lettura")
    c.set_zone_divider("zone_3", 5)
    c.cycle_count = 1
    v(s.extra_state_attributes.get("ciclo") == ["zone_1", "zone_2", "zone_3"],
      "il giro e' fissato alla partenza: la zona 3 passata a «ogni 5» resta nel giro in corso")
    c.set_zone_divider("zone_3", 1)
    c.cycle_count = 0
    salvati = dict(s.extra_state_attributes)

    await tempo.libera()
    a = s.extra_state_attributes
    v(c.status == "running" and a["active_zone"] is None, "controllo: pausa fra la zona 1 e la 2")
    v(a.get("ciclo_fatte") == ["zone_1"], f"finita la zona 1: fatta (e' {a.get('ciclo_fatte')})")
    v(salvati.get("ciclo_fatte") == [] and a != salvati,
      "gli attributi salvati non cambiano sotto i piedi: Home Assistant vede la differenza")

    await tempo.libera()
    a = s.extra_state_attributes
    v(a["active_zone"] == "zone_2", "controllo: tocca alla zona 2")
    v(a.get("in_apertura") is True, "la valvola 2 e' comandata e non conferma: in apertura")

    await tempo.fino_a(lambda: c.active_zone != "zone_2")
    a = s.extra_state_attributes
    v(a["zone_non_aperte"] == ["Zona 2"], "controllo: la zona 2 finisce fra le non aperte (per nome)")
    v(a.get("ciclo_non_aperte") == ["zone_2"], f"ciclo_non_aperte = zona 2 (e' {a.get('ciclo_non_aperte')})")
    v(a.get("ciclo_fatte") == ["zone_1"], "la zona 2 non e' fatta")
    v(a.get("in_apertura") is False, "finiti i tentativi, non piu' in apertura")

    await tempo.libera()
    v(c.active_zone == "zone_3", "controllo: parte la zona 3")
    c.set_zone_duration("zone_2", 0)
    v(s.extra_state_attributes.get("ciclo") == ["zone_1", "zone_2", "zone_3"],
      "la zona 2 portata a 0 minuti resta nel giro: e' fra le non aperte")
    await c.async_stop()
    a = s.extra_state_attributes
    v(c.status == "idle" and a["active_zone"] is None, "controllo: arrestato")
    v(a.get("ciclo_fatte") == ["zone_1"], f"la zona 3 interrotta non e' fatta (fatte: {a.get('ciclo_fatte')})")
    v(a.get("ciclo_non_aperte") == ["zone_2"], "le non aperte restano fino al prossimo giro")
    v(a.get("in_apertura") is False and a.get("manuale") is False, "in_apertura e manuale false")
    v(a.get("ciclo") == ["zone_1", "zone_3"], f"da fermo di nuovo il prossimo giro, senza la zona a 0 minuti (e' {a.get('ciclo')})")


async def caso_durata_in_giro() -> None:
    print("\n4b. Durate cambiate a giro in corso: il ciclo segue quello che il giro irrighera' davvero")
    hass, c, s, tempo = await impianto([zona(1, minuti=1), zona(2, minuti=0), zona(3, minuti=1)])
    await c.async_start_cycle(check_rain=False)
    await cedi()
    v(c.active_zone == "zone_1", "controllo: parte la zona 1")
    v(s.extra_state_attributes.get("ciclo") == ["zone_1", "zone_3"],
      "alla partenza la zona 2 a 0 minuti non e' nel ciclo")
    c.set_zone_duration("zone_2", 1)
    a = s.extra_state_attributes
    v(a.get("ciclo") == ["zone_1", "zone_2", "zone_3"] and elenco(a, "in_ciclo") == [True, True, True],
      f"riportata a 1 minuto durante la zona 1 rientra, perche' al suo turno verra' irrigata (e' {a.get('ciclo')})")
    await tempo.fino_a(lambda: c.active_zone == "zone_2")
    v(c.active_zone == "zone_2", "e infatti il giro la irriga")

    hass, c, s, tempo = await impianto([zona(1, minuti=1), zona(2, minuti=1), zona(3, minuti=1)])
    await c.async_start_cycle(check_rain=False)
    await cedi()
    v(c.active_zone == "zone_1", "controllo: parte la zona 1")
    c.set_zone_duration("zone_2", 0)
    v(s.extra_state_attributes.get("ciclo") == ["zone_1", "zone_3"],
      "portata a 0 minuti durante la zona 1 esce dal ciclo: il giro la saltera'")
    c.set_zone_duration("zone_1", 0)
    v(s.extra_state_attributes.get("ciclo") == ["zone_1", "zone_3"],
      "la zona in corso resta nel ciclo anche portata a 0 minuti")
    await tempo.fino_a(lambda: c.active_zone == "zone_3")
    v(c.active_zone == "zone_3" and "zone_2" not in c.ciclo_fatte, "controllo: il giro salta davvero la zona 2")


async def caso_arresto_in_apertura() -> None:
    print("\n5. Arresto mentre la valvola non ha ancora confermato")
    hass, c, s, tempo = await impianto([zona(1, minuti=1), zona(2, minuti=1)])
    hass.services.guaste.add("switch.valvola_1")
    await c.async_start_zone("zone_1")
    await cedi()
    a = s.extra_state_attributes
    v(a["active_zone"] == "zone_1", "controllo: zona 1 avviata a mano")
    v(a.get("in_apertura") is True and a.get("manuale") is True, "in apertura e a mano")
    await c.async_stop()
    a = s.extra_state_attributes
    v(a["active_zone"] is None and not notifiche_zona(), "controllo: fermo, nessuna notifica di zona non aperta")
    v(a.get("in_apertura") is False and a.get("manuale") is False, "dopo l'arresto in_apertura e manuale tornano false")
    v(a.get("ciclo_non_aperte") == [] and a.get("ciclo_fatte") == [],
      "interrotta durante i tentativi: ne' fatta ne' non aperta")


def notifiche_zona() -> list:
    return [n for n in finto_ha.NOTIFICHE if "_zona_" in (n["id"] or "")]


# --- 6. zona a mano -----------------------------------------------------------------
async def caso_zona_a_mano() -> None:
    print("\n6. Zona a mano dopo un giro completo")
    hass, c, s, tempo = await impianto([zona(1, minuti=1), zona(2, minuti=1)])
    await c.async_start_cycle(check_rain=False)
    await tempo.fino_a(lambda: not c.is_running)
    a = s.extra_state_attributes
    v(c.cycle_count == 1 and c.last_cycle is not None, "controllo: giro completo")
    v(a.get("ciclo_fatte") == ["zone_1", "zone_2"], "a giro finito le fatte dicono com'e' andato")

    await c.async_start_zone("zone_2")
    await cedi()
    a = s.extra_state_attributes
    v(c.status == "running" and a["active_zone"] == "zone_2", "controllo: zona 2 avviata a mano")
    v(a.get("manuale") is True, "manuale true")
    v(a.get("ciclo") == ["zone_2"], f"ciclo = [zona 2] (e' {a.get('ciclo')})")
    v(elenco(a, "in_ciclo") == [False, True], "solo la zona 2 e' nel giro")
    v(a.get("ciclo_fatte") == [], "la partenza a mano azzera le fatte")

    await tempo.fino_a(lambda: not c.is_running)
    a = s.extra_state_attributes
    v(c.status == "idle", "controllo: finita")
    v(a.get("manuale") is False, "finita la zona, manuale false")
    v(a.get("ciclo_fatte") == ["zone_2"], "la zona a mano e' fatta")
    v(a.get("ciclo") == ["zone_1", "zone_2"], "da fermo il ciclo torna il prossimo giro")


# --- 7. liste nuove -----------------------------------------------------------------
async def caso_liste_nuove() -> None:
    print("\n7. Liste e dizionari nuovi a ogni lettura")
    hass, c, s, _ = await impianto(
        [zona(1)], rain_mode="weather", rain_entity="weather.casa", soil_capacity=25.0
    )
    prima = s.extra_state_attributes
    dopo = s.extra_state_attributes
    v(prima["zones"] is not dopo["zones"], "controllo: zones e' gia' nuova a ogni lettura")
    for chiave in ("ciclo", "ciclo_fatte", "ciclo_non_aperte"):
        v(isinstance(prima.get(chiave), list) and prima[chiave] is not dopo[chiave],
          f"{chiave}: lista nuova a ogni lettura")
    v(prima.get("ciclo_fatte") is not getattr(c, "ciclo_fatte", None)
      and prima.get("ciclo_non_aperte") is not getattr(c, "ciclo_non_aperte", None),
      "mai le liste del controller")
    for chiave in ("riserva", "pioggia"):
        v(isinstance(prima.get(chiave), dict) and prima[chiave] is not dopo[chiave],
          f"{chiave}: dizionario nuovo a ogni lettura")


# --- 8. riserva e pioggia -----------------------------------------------------------
async def caso_riserva_pioggia() -> None:
    print("\n8. Riserva e pioggia per la testata")
    hass, c, s, _ = await impianto([zona(1)])
    a = s.extra_state_attributes
    v(a["rain_mode"] == "none", "controllo: senza sorgente pioggia")
    v("riserva" in a and a["riserva"] is None, "senza bilancio: riserva null")
    v("pioggia" in a and a["pioggia"] is None, "senza sorgente: pioggia null")

    hass, c, s, _ = await impianto(
        [zona(1)], rain_mode="weather", rain_entity="weather.casa", rain_threshold=2.0,
        rain_hours=12, rain_hours_past=6, soil_capacity=25.0, reserve_threshold=10.0,
    )
    c.rain_detected = True
    c.rain_recent = 1.26
    c.rain_forecast = 3.04
    c.et0_oggi = 4.123
    a = s.extra_state_attributes
    v(c.balance_enabled, "controllo: bilancio attivo")
    v(a.get("riserva") == {"entita": "sensor.prova_reserve", "soglia": 10.0, "capacita": 25.0},
      f"riserva con entita', soglia e capacita' (e' {a.get('riserva')})")
    v(a.get("pioggia") == {"rilevata": True, "caduta_mm": 1.3, "prevista_mm": 3.0,
                           "ore_passate": 6, "ore_previste": 12},
      f"pioggia arrotondata a un decimale (e' {a.get('pioggia')})")
    et0 = Et0Sensor(c).extra_state_attributes["consumo_prato_mm"]
    v(a.get("consumo_prato_mm") == et0 == 3.5,
      f"consumo del prato uguale a quello del sensore Evapotraspirazione (3.5; e' {a.get('consumo_prato_mm')})")

    hass, c, s, _ = await impianto(
        [zona(1)], rain_mode="weather", rain_entity="weather.casa", soil_capacity=0.0
    )
    a = s.extra_state_attributes
    v(not c.balance_enabled, "controllo: capacita' a zero, bilancio spento")
    v("riserva" in a and a["riserva"] is None and isinstance(a.get("pioggia"), dict),
      "meteo senza bilancio: riserva null, pioggia presente")

    hass, c, s, _ = await impianto(
        [zona(1)], rain_mode="sensor", rain_entity="binary_sensor.pluviometro"
    )
    hass.states.imposta("binary_sensor.pluviometro", "on")
    await cedi()
    a = s.extra_state_attributes
    v(c.rain_detected, "controllo: pluviometro bagnato")
    v((a.get("pioggia") or {}).get("rilevata") is True and "riserva" in a and a["riserva"] is None,
      "pluviometro: pioggia rilevata, riserva null")


# --- 9. traduzioni e manifest -------------------------------------------------------
def caso_file() -> None:
    print("\n9. Traduzioni e manifest")
    base = os.path.join(finto_ha._SRC, "nexus_irrigation")
    attese = {
        "strings.json": {"lawn": "Prato (irrigatori)", "drip": "Goccia"},
        "translations/it.json": {"lawn": "Prato (irrigatori)", "drip": "Goccia"},
        "translations/en.json": {"lawn": "Lawn (sprinklers)", "drip": "Drip"},
    }
    for nome, opzioni in attese.items():
        with open(os.path.join(base, nome), encoding="utf-8") as f:
            testi = json.load(f)
        v("rain_mode" in testi["selector"], f"controllo: {nome} letto")
        v(testi["selector"].get("zone_type", {}).get("options") == opzioni,
          f"{nome}: opzioni del tipo di zona sotto «selector»")
        etichette = [testi[flusso]["step"]["zone"]["data"].get("type") for flusso in ("config", "options")]
        v(all(etichette), f"{nome}: etichetta del campo tipo nel config flow e nelle opzioni ({etichette})")
    with open(os.path.join(base, "manifest.json"), encoding="utf-8") as f:
        manifest = json.load(f)
    v(manifest["domain"] == "nexus_irrigation", "controllo: manifest letto")
    v(manifest["version"] == "1.6.0", f"versione 1.6.0 (e' {manifest['version']})")
    v(set(manifest["dependencies"]) == {"persistent_notification", "http", "frontend", "lovelace"},
      f"dipendenze per servire e registrare la scheda (sono {manifest['dependencies']})")


# --- 10. registrazione della scheda -------------------------------------------------
class Risorse:
    """Le risorse Lovelace in modalita' interfaccia."""

    def __init__(self, voci: list[dict]) -> None:
        self.voci = [dict(voce) for voce in voci]
        self.create: list[dict] = []
        self.aggiornate: list[str] = []

    async def async_get_info(self) -> dict:
        return {"resources": len(self.voci)}

    def async_items(self) -> list[dict]:
        return list(self.voci)

    async def async_create_item(self, dati: dict) -> dict:
        voce = {"id": f"r{len(self.voci) + 1}", **dati}
        self.voci.append(voce)
        self.create.append(voce)
        return voce

    async def async_update_item(self, id_voce: str, dati: dict) -> dict:
        voce = next(r for r in self.voci if r["id"] == id_voce)
        voce.update(dati)
        self.aggiornate.append(id_voce)
        return voce


class RisorseYaml:
    """Le risorse Lovelace in modalita' YAML: si leggono e basta, come in Home Assistant."""

    def __init__(self, voci: list[dict]) -> None:
        self.voci = [dict(voce) for voce in voci]

    async def async_get_info(self) -> dict:
        return {"resources": len(self.voci)}

    def async_items(self) -> list[dict]:
        return list(self.voci)


def con_www(hass, esiste: bool = True) -> None:
    """La cartella www della scheda c'e' o non c'e', qualunque cosa ci sia sul disco."""
    async def lavoro(funzione, *argomenti):
        if funzione is os.path.isdir:
            return esiste
        return funzione(*argomenti)

    hass.async_add_executor_job = lavoro


async def caso_registrazione() -> None:
    print("\n10. La scheda si serve e si registra da sola, senza toccare la vecchia card")
    registra = getattr(integrazione, "_async_registra_card", None)
    v(registra is not None, "l'integrazione ha la registrazione della scheda")
    if registra is None:
        return
    url = f"{URL_SCHEDA}?v=1.6.0"

    azzera()
    LOG.messaggi.clear()
    hass = Hass()
    con_www(hass)
    risorse = Risorse([VECCHIA])
    hass.data["lovelace"] = types.SimpleNamespace(resources=risorse)
    await registra(hass)
    percorsi = [(p.url_path, os.path.basename(p.path)) for p in hass.http.percorsi]
    v(percorsi == [("/nexus_irrigation", "www")], f"cartella www servita su /nexus_irrigation ({percorsi})")
    v(risorse.voci[0] == VECCHIA and not risorse.aggiornate,
      "la risorsa della vecchia card (/hacsfiles/...) non viene presa per la nostra")
    v([r["url"] for r in risorse.create] == [url] and risorse.create[0]["res_type"] == "module",
      f"la nostra risorsa creata accanto, con la versione ({[r['url'] for r in risorse.create]})")
    v(any("vecchia Nexus Irrigation Card" in m for m in LOG.messaggi), "il log chiede di rimuovere la vecchia card")
    await registra(hass)
    v(len(hass.http.percorsi) == 1 and len(risorse.create) == 1, "una volta sola per avvio")

    hass = Hass()
    con_www(hass)
    risorse = Risorse([VECCHIA, {"id": "r2", "res_type": "module", "url": f"{URL_SCHEDA}?v=1.5.9"}])
    hass.data["lovelace"] = types.SimpleNamespace(resources=risorse)
    await registra(hass)
    v(risorse.aggiornate == ["r2"] and risorse.voci[1]["url"] == url and not risorse.create,
      "risorsa nostra di una versione precedente: aggiornata, non duplicata")
    v(risorse.voci[0] == VECCHIA, "e la vecchia card resta com'e'")

    LOG.messaggi.clear()
    hass = Hass()
    con_www(hass)
    risorse = Risorse([{"id": "r1", "res_type": "module", "url": url}])
    hass.data["lovelace"] = types.SimpleNamespace(resources=risorse)
    await registra(hass)
    v(not risorse.create and not risorse.aggiornate and not LOG.messaggi,
      "risorsa gia' giusta e nessuna vecchia card: niente da fare, niente avvisi")

    hass = Hass()
    con_www(hass)
    await registra(hass)
    v(JS_EXTRA == [url], f"senza risorse Lovelace: ripiego su add_extra_js_url ({JS_EXTRA})")

    # Lovelace in YAML: la collezione delle risorse esiste ma si puo' solo leggere.
    azzera()
    LOG.messaggi.clear()
    hass = Hass()
    con_www(hass)
    yaml = RisorseYaml([VECCHIA])
    hass.data["lovelace"] = types.SimpleNamespace(resources=yaml)
    await registra(hass)
    v(JS_EXTRA == [url], f"Lovelace in YAML senza la scheda: caricata come modulo extra ({JS_EXTRA})")
    v(not any("Impossibile" in m for m in LOG.messaggi),
      f"e senza avvisi di errore a ogni avvio ({LOG.messaggi})")
    v(any("vecchia Nexus Irrigation Card" in m for m in LOG.messaggi),
      "anche in YAML il log chiede di rimuovere la vecchia card")

    azzera()
    LOG.messaggi.clear()
    hass = Hass()
    con_www(hass)
    yaml = RisorseYaml([{"id": "y1", "res_type": "module", "url": f"{URL_SCHEDA}?v=1.5.9"}])
    hass.data["lovelace"] = types.SimpleNamespace(resources=yaml)
    # Il suggerimento di aggiornare e' un'informazione, non un avviso: per vederlo
    # il registro scende per un momento al livello info.
    registratore = logging.getLogger("nexus_irrigation")
    livelli = (registratore.level, LOG.level)
    registratore.setLevel(logging.INFO)
    LOG.setLevel(logging.INFO)
    try:
        await registra(hass)
    finally:
        registratore.setLevel(livelli[0])
        LOG.setLevel(livelli[1])
    v(JS_EXTRA == [], f"Lovelace in YAML con la scheda gia' fra le risorse: nessun doppio caricamento ({JS_EXTRA})")
    v(any("aggiornala" in m for m in LOG.messaggi) and not any("Impossibile" in m for m in LOG.messaggi),
      f"con la versione vecchia il log dice di aggiornarla, senza errori ({LOG.messaggi})")

    LOG.messaggi.clear()
    hass = Hass()
    con_www(hass, esiste=False)
    risorse = Risorse([])
    hass.data["lovelace"] = types.SimpleNamespace(resources=risorse)
    await registra(hass)
    v(not hass.http.percorsi and not risorse.create, "cartella www assente: niente servito, niente registrato")
    v(any("www" in m for m in LOG.messaggi), "e un avviso nel log")

    hass = Hass()
    con_www(hass)
    hass.is_running = False
    risorse = Risorse([])
    hass.data["lovelace"] = types.SimpleNamespace(resources=risorse)
    await registra(hass)
    v(not risorse.create and [e for e, _ in hass.bus.una_volta] == ["homeassistant_started"],
      "a boot in corso si aspetta l'avvio completo")
    for _, azione in hass.bus.una_volta:
        await azione(None)
    v([r["url"] for r in risorse.create] == [url], "e ad avvio completato la risorsa si crea")


class EntryCompleta(Entry):
    def add_update_listener(self, funzione):
        return lambda: None

    def async_on_unload(self, funzione) -> None:
        return None


async def caso_setup_non_fatale() -> None:
    print("\n11. Una scheda che non si registra non ferma l'impianto")
    azzera()
    LOG.messaggi.clear()
    hass = Hass()
    con_www(hass)
    hass.http = None

    async def inoltra(entry, piattaforme) -> None:
        return None

    hass.config_entries = types.SimpleNamespace(async_forward_entry_setups=inoltra)
    entry = EntryCompleta({"name": "Prova", "zones": [zona(1)], "rain_mode": "none"})
    esito = await integrazione.async_setup_entry(hass, entry)
    v(esito is True and "prova" in hass.data["nexus_irrigation"], "controllo: impianto configurato")
    v(any("Scheda non registrata" in m for m in LOG.messaggi),
      "la registrazione fallita finisce nel log, e il setup va avanti")
    await hass.data["nexus_irrigation"]["prova"].async_shutdown()


async def main() -> None:
    for caso in (
        caso_tipo_zona,
        caso_config_flow,
        caso_da_fermo,
        caso_giro,
        caso_durata_in_giro,
        caso_arresto_in_apertura,
        caso_zona_a_mano,
        caso_liste_nuove,
        caso_riserva_pioggia,
        caso_file,
        caso_registrazione,
        caso_setup_non_fatale,
    ):
        try:
            risultato = caso()
            if asyncio.iscoroutine(risultato):
                await risultato
        except Exception as err:  # noqa: BLE001
            v(False, f"{caso.__name__} interrotta: {type(err).__name__}: {err}")
    esiti.chiudi()


asyncio.run(main())
