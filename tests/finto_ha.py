"""Un Home Assistant finto, quanto basta per provare Nexus Irrigation a tavolino.

Si iniettano moduli con i soli nomi che l'integrazione importa. Il meteo finto
risponde a `weather.get_forecasts` con le previsioni orarie che la prova gli
da', e l'orologio si sposta a mano: dodici ore di pioggia passata si provano
in un istante.

Con la variabile d'ambiente NEXUS_IRRIGATION_SRC si puo' puntare a un'altra
copia di `custom_components` (per esempio la versione precedente) e vedere
quali prove falliscono li': una prova che passa su entrambe non discrimina.

Per config flow, sensore di stato e registrazione della scheda ci sono anche
voluptuous (finto: gli schemi si leggono, non si validano), i selettori, il
registro delle entita' e i pezzi di frontend e http che l'integrazione usa.
Le valvole finte rispondono ai comandi, tranne quelle messe fra le guaste.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import types
from datetime import datetime, timedelta, timezone

FUSO = timezone(timedelta(hours=2))
INIZIO = datetime(2026, 9, 11, 23, 0, tzinfo=FUSO)


def _modulo(nome: str, **attributi):
    m = types.ModuleType(nome)
    for chiave, valore in attributi.items():
        setattr(m, chiave, valore)
    sys.modules[nome] = m
    genitore, _, figlio = nome.rpartition(".")
    if genitore and genitore in sys.modules:
        setattr(sys.modules[genitore], figlio, m)
    return m


# --- orologio -----------------------------------------------------------------
class Orologio:
    def __init__(self) -> None:
        self.adesso = INIZIO

    def avanza(self, **delta) -> None:
        self.adesso += timedelta(**delta)


OROLOGIO = Orologio()


# --- moduli di Home Assistant -------------------------------------------------
class _Platform(str):
    BINARY_SENSOR = "binary_sensor"
    BUTTON = "button"
    NUMBER = "number"
    SELECT = "select"
    SENSOR = "sensor"
    SWITCH = "switch"
    TIME = "time"


def callback(funzione):
    return funzione


class Stato:
    def __init__(self, entity_id: str, state: str, attributes: dict | None = None) -> None:
        self.entity_id = entity_id
        self.state = state
        self.attributes = dict(attributes or {})


class Evento:
    def __init__(self, data: dict) -> None:
        self.data = data


NOTIFICHE: list[dict] = []
_ASCOLTATORI_STATO: list[tuple[set, object]] = []


def _consegna(azione, evento) -> None:
    risultato = azione(evento)
    if asyncio.iscoroutine(risultato):
        asyncio.ensure_future(risultato)


def async_track_state_change_event(hass, entity_ids, action):
    ids = {entity_ids} if isinstance(entity_ids, str) else set(entity_ids)
    voce = (ids, action)
    _ASCOLTATORI_STATO.append(voce)
    return lambda: _ASCOLTATORI_STATO.remove(voce)


def async_track_time_interval(hass, action, interval):
    return lambda: None


def async_track_point_in_time(hass, action, point):
    return lambda: None


def _crea_notifica(hass, message, title=None, notification_id=None):
    NOTIFICHE.append({"message": message, "title": title, "id": notification_id})


_modulo("homeassistant")
_modulo("homeassistant.components")
_modulo(
    "homeassistant.components.persistent_notification",
    async_create=_crea_notifica,
    async_dismiss=lambda hass, notification_id: None,
)
sys.modules["homeassistant.components"].persistent_notification = sys.modules[
    "homeassistant.components.persistent_notification"
]
_modulo(
    "homeassistant.core", CALLBACK_TYPE=object, Event=object, HomeAssistant=object, callback=callback
)


# --- voluptuous -----------------------------------------------------------------
class _Marcatore(str):
    def __new__(cls, nome, default=None, description=None):
        s = super().__new__(cls, nome)
        s.default = default
        s.description = description
        return s


class Required(_Marcatore):
    pass


class Optional(_Marcatore):
    pass


class Schema(dict):
    pass


_modulo("voluptuous", Schema=Schema, Required=Required, Optional=Optional)


# --- config flow ------------------------------------------------------------------
class _Flusso:
    def async_show_form(self, step_id, data_schema=None, errors=None, description_placeholders=None):
        return {"type": "form", "step_id": step_id, "schema": data_schema, "errors": errors or {}}

    def async_show_menu(self, step_id, menu_options):
        return {"type": "menu", "step_id": step_id, "menu_options": menu_options}

    def async_create_entry(self, title=None, data=None):
        return {"type": "create_entry", "title": title, "data": data}

    def add_suggested_values_to_schema(self, data_schema, suggested_values):
        """Come Home Assistant: copia le chiavi e ci mette il valore suggerito."""
        nuovo = Schema()
        for chiave, valore in data_schema.items():
            if chiave in suggested_values:
                chiave = type(chiave)(
                    str(chiave),
                    default=chiave.default,
                    description={"suggested_value": suggested_values[chiave]},
                )
            nuovo[chiave] = valore
        return nuovo


class ConfigFlow(_Flusso):
    def __init_subclass__(cls, domain=None, **kw):
        super().__init_subclass__(**kw)
        cls.DOMAIN = domain

    def _async_abort_entries_match(self, match_dict=None) -> None:
        return None


class OptionsFlow(_Flusso):
    config_entry = None


_modulo(
    "homeassistant.config_entries",
    ConfigEntry=object,
    ConfigFlow=ConfigFlow,
    ConfigFlowResult=dict,
    OptionsFlow=OptionsFlow,
)
_modulo(
    "homeassistant.const",
    EVENT_HOMEASSISTANT_STARTED="homeassistant_started",
    STATE_UNAVAILABLE="unavailable",
    STATE_UNKNOWN="unknown",
    Platform=_Platform,
)
_modulo("homeassistant.helpers")
_modulo(
    "homeassistant.helpers.event",
    async_track_point_in_time=async_track_point_in_time,
    async_track_state_change_event=async_track_state_change_event,
    async_track_time_interval=async_track_time_interval,
)
_modulo("homeassistant.util")
_modulo(
    "homeassistant.util.dt",
    now=lambda: OROLOGIO.adesso,
    utcnow=lambda: OROLOGIO.adesso.astimezone(timezone.utc),
    as_local=lambda d: d.astimezone(FUSO),
    as_utc=lambda d: (d if d.tzinfo else d.replace(tzinfo=FUSO)).astimezone(timezone.utc),
    parse_datetime=lambda s: datetime.fromisoformat(s),
)
sys.modules["homeassistant.util"].dt = sys.modules["homeassistant.util.dt"]


# --- entita' (solo per leggere gli attributi del sensore pioggia) -------------
class _Entity:
    hass = None

    async def async_added_to_hass(self) -> None:
        return None

    def async_on_remove(self, funzione) -> None:
        return None

    def async_write_ha_state(self) -> None:
        return None


class _RestoreEntity:
    ultimo_stato = None

    async def async_get_last_state(self):
        return self.ultimo_stato


class _DeviceClass:
    MOISTURE = "moisture"
    RUNNING = "running"
    OPENING = "opening"


class _BinarySensorEntity:
    # Non `object`: tra le basi di una classe con altri genitori romperebbe
    # l'ordine di risoluzione dei metodi.
    pass


_modulo("homeassistant.helpers.entity", Entity=_Entity)
_modulo("homeassistant.helpers.device_registry", DeviceInfo=dict)
_modulo("homeassistant.helpers.entity_platform", AddEntitiesCallback=object)
_modulo("homeassistant.helpers.restore_state", RestoreEntity=_RestoreEntity)
_modulo(
    "homeassistant.components.binary_sensor",
    BinarySensorDeviceClass=_DeviceClass,
    BinarySensorEntity=_BinarySensorEntity,
)


# --- sensori e registro delle entita' -------------------------------------------
class _SensorEntity:
    pass


class _SensorDeviceClass:
    ENUM = "enum"
    TIMESTAMP = "timestamp"


class _SensorStateClass:
    MEASUREMENT = "measurement"


_modulo(
    "homeassistant.components.sensor",
    SensorDeviceClass=_SensorDeviceClass,
    SensorEntity=_SensorEntity,
    SensorStateClass=_SensorStateClass,
)


class Registro:
    """Ogni entita' dell'integrazione esiste, con l'entity_id tratto dall'unique_id."""

    def async_get_entity_id(self, dominio: str, piattaforma: str, unique_id: str) -> str:
        return f"{dominio}.{unique_id}"


_modulo("homeassistant.helpers.entity_registry", async_get=lambda hass: Registro())


# --- selettori ----------------------------------------------------------------------
class _Selettore:
    def __init__(self, config) -> None:
        self.config = config


class _Modo:
    BOX = "box"
    SLIDER = "slider"
    LIST = "list"
    DROPDOWN = "dropdown"


_modulo(
    "homeassistant.helpers.selector",
    EntitySelector=type("EntitySelector", (_Selettore,), {}),
    EntitySelectorConfig=dict,
    NumberSelector=type("NumberSelector", (_Selettore,), {}),
    NumberSelectorConfig=dict,
    NumberSelectorMode=_Modo,
    SelectSelector=type("SelectSelector", (_Selettore,), {}),
    SelectSelectorConfig=dict,
    SelectSelectorMode=_Modo,
)


# --- frontend, http e loader, per la registrazione della scheda ---------------------
# URL aggiunti con add_extra_js_url, il ripiego senza risorse Lovelace.
JS_EXTRA: list[str] = []


class StaticPathConfig:
    def __init__(self, url_path: str, path: str, cache_headers: bool = True) -> None:
        self.url_path = url_path
        self.path = path
        self.cache_headers = cache_headers


async def async_get_integration(hass, dominio: str):
    """L'integrazione con la versione del manifest della copia sotto prova."""
    with open(os.path.join(_SRC, dominio, "manifest.json"), encoding="utf-8") as f:
        return types.SimpleNamespace(version=json.load(f)["version"])


_modulo("homeassistant.components.frontend", add_extra_js_url=lambda hass, url: JS_EXTRA.append(url))
_modulo("homeassistant.components.http", StaticPathConfig=StaticPathConfig)
_modulo("homeassistant.loader", async_get_integration=async_get_integration)


# --- impianto finto -----------------------------------------------------------
class Stati:
    def __init__(self) -> None:
        self._stati: dict[str, Stato] = {}

    def get(self, entity_id: str):
        return self._stati.get(entity_id)

    def imposta(self, entity_id: str, state: str, attributes: dict | None = None) -> None:
        vecchio = self._stati.get(entity_id)
        nuovo = Stato(entity_id, state, attributes)
        self._stati[entity_id] = nuovo
        evento = Evento({"entity_id": entity_id, "old_state": vecchio, "new_state": nuovo})
        for ids, azione in list(_ASCOLTATORI_STATO):
            if entity_id in ids:
                _consegna(azione, evento)


_VALVOLE = {
    ("switch", "turn_on"): "on",
    ("switch", "turn_off"): "off",
    ("valve", "open_valve"): "open",
    ("valve", "close_valve"): "closed",
}


class Servizi:
    def __init__(self, stati: Stati) -> None:
        self.stati = stati
        # Previsioni orarie: lista di mm, dall'ora successiva in avanti.
        self.pioggia_oraria: list[float] = []
        self.chiamate: list[tuple] = []
        # Valvole che ricevono il comando ma non cambiano stato.
        self.guaste: set[str] = set()

    async def async_call(self, domain, service, data=None, target=None, blocking=False,
                         return_response=False, **_):
        self.chiamate.append((domain, service, data, target))
        if (domain, service) in _VALVOLE:
            entita = (data or {}).get("entity_id")
            if entita not in self.guaste:
                self.stati.imposta(entita, _VALVOLE[(domain, service)])
            return None
        if (domain, service) == ("weather", "get_forecasts"):
            entita = (target or {}).get("entity_id")
            if (data or {}).get("type") != "hourly":
                return {entita: {"forecast": []}}
            # Come met.no in Home Assistant: orari in UTC, e la prima voce e'
            # l'ora successiva, non quella in corso (verificato il 14/09/2026).
            base = OROLOGIO.adesso.astimezone(timezone.utc).replace(
                minute=0, second=0, microsecond=0
            ) + timedelta(hours=1)
            previsioni = [
                {"datetime": (base + timedelta(hours=i)).isoformat(), "precipitation": mm}
                for i, mm in enumerate(self.pioggia_oraria)
            ] or [{"datetime": base.isoformat(), "precipitation": 0}]
            return {entita: {"forecast": previsioni}}
        return None


class Bus:
    def __init__(self) -> None:
        self.una_volta: list[tuple[str, object]] = []

    def async_listen_once(self, evento, azione):
        self.una_volta.append((evento, azione))
        return lambda: None


class Config:
    latitude = 41.9
    elevation = 50


class Http:
    def __init__(self) -> None:
        self.percorsi: list[StaticPathConfig] = []

    async def async_register_static_paths(self, configurazioni) -> None:
        self.percorsi.extend(configurazioni)


class Hass:
    def __init__(self) -> None:
        self.states = Stati()
        self.services = Servizi(self.states)
        self.bus = Bus()
        self.config = Config()
        self.http = Http()
        self.data: dict = {}
        self.is_running = True
        self.loop = asyncio.get_event_loop()

    def async_create_task(self, coro, *_args, **_kwargs):
        return asyncio.ensure_future(coro)

    async def async_add_executor_job(self, funzione, *argomenti):
        return funzione(*argomenti)


class Entry:
    def __init__(self, data: dict) -> None:
        self.entry_id = "prova"
        self.data = data
        self.options: dict = {}

    def async_create_background_task(self, hass, coro, name=None):
        return asyncio.ensure_future(coro)


class Esiti:
    def __init__(self, nome: str) -> None:
        self.nome = nome
        self.passate = 0
        self.fallite: list[str] = []

    def verifica(self, condizione: bool, descrizione: str) -> None:
        if condizione:
            self.passate += 1
            print(f"  ok  {descrizione}")
        else:
            self.fallite.append(descrizione)
            print(f"  NO  {descrizione}")

    def chiudi(self) -> None:
        totale = self.passate + len(self.fallite)
        print(f"\n{self.nome}: {self.passate}/{totale} superate")
        if self.fallite:
            sys.exit(1)


def azzera() -> None:
    OROLOGIO.adesso = INIZIO
    NOTIFICHE.clear()
    _ASCOLTATORI_STATO.clear()
    JS_EXTRA.clear()


_SRC = os.environ.get(
    "NEXUS_IRRIGATION_SRC",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "custom_components"),
)
sys.path.insert(0, os.path.abspath(_SRC))
