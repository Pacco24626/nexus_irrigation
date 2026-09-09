"""Costanti dell'integrazione Nexus Irrigation."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "nexus_irrigation"
MANUFACTURER = "Nexus-T"
MODEL = "Centralina irrigazione"

PLATFORMS: list[Platform] = [
    Platform.SELECT,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.TIME,
]

# --- Chiavi di configurazione -------------------------------------------------
CONF_ZONES = "zones"
CONF_ZONE_ID = "id"
CONF_ZONE_NAME = "name"
CONF_ZONE_ENTITY = "entity_id"
CONF_ZONE_MINUTES = "minutes"
CONF_ADD_ANOTHER = "add_another"

CONF_USE_MASTER = "use_master"
CONF_MASTER_ENTITY = "master_entity"
CONF_MASTER_LEAD = "master_lead"
CONF_MASTER_LAG = "master_lag"

CONF_RAIN_MODE = "rain_mode"
CONF_RAIN_ENTITY = "rain_entity"
CONF_RAIN_THRESHOLD = "rain_threshold"
CONF_RAIN_HOURS = "rain_hours"
CONF_RAIN_HOURS_PAST = "rain_hours_past"
CONF_SOIL_CAPACITY = "soil_capacity"
CONF_DAILY_ET = "daily_et"
CONF_RESERVE_THRESHOLD = "reserve_threshold"
CONF_PRECIP_RATE = "precip_rate"
CONF_TIPO_PRATO = "grass_type"
CONF_KC = "crop_coefficient"
CONF_COSTA = "coastal"
CONF_ET0_SENSOR = "et0_sensor"
CONF_ZONE_DIVIDER = "divider"

# --- Modalita' sorgente pioggia ----------------------------------------------
RAIN_NONE = "none"
RAIN_SENSOR = "sensor"
RAIN_WEATHER = "weather"
RAIN_MODES = [RAIN_NONE, RAIN_SENSOR, RAIN_WEATHER]

# --- Stati del controller -----------------------------------------------------
STATUS_IDLE = "idle"
STATUS_RUNNING = "running"
STATUS_RAIN_SKIPPED = "rain_skipped"
STATUS_OPTIONS = [STATUS_IDLE, STATUS_RUNNING, STATUS_RAIN_SKIPPED]

# --- Chiavi delle entita' -----------------------------------------------------
# Usate sia per gli unique_id sia dalla card per risalire alle entita'.
KEY_ENABLE = "enable"
KEY_SEASONAL = "seasonal_factor"
KEY_START_TIME = "start_time"
KEY_START_CYCLE = "start_cycle"
KEY_STOP = "stop"
KEY_STATUS = "status"
KEY_LAST_CYCLE = "last_cycle"
KEY_NEXT_CYCLE = "next_cycle"
KEY_RAIN = "rain"
KEY_RESERVE = "reserve"
KEY_ET0 = "et0"
KEY_RAIN_BYPASS = "rain_bypass"
KEY_DAY_MODE = "day_mode"
KEY_CYCLE_DAYS = "cycle_days"
KEY_ZONE_DIVIDER_PREFIX = "divider_"


def zone_divider_key(zone_id: str) -> str:
    return f"{KEY_ZONE_DIVIDER_PREFIX}{zone_id}"
KEY_RUNNING = "running"
KEY_MASTER = "master"

KEY_DAY_PREFIX = "day_"
# --- Modalita' dei giorni di irrigazione --------------------------------------
# Le prime tre vengono dalle centraline da giardino. Pari e dispari non sono
# un vezzo: molti comuni li impongono durante le restrizioni idriche estive.
# I giorni ciclici sono agronomicamente migliori dei giorni fissi, perche'
# tengono un ritmo costante invece di lasciare due giorni fra venerdi' e
# lunedi' e uno fra gli altri.
MODO_SETTIMANALE = "weekly"
MODO_DISPARI = "odd"
MODO_PARI = "even"
MODO_CICLICO = "cyclic"
MODI_GIORNI = [MODO_SETTIMANALE, MODO_DISPARI, MODO_PARI, MODO_CICLICO]
DEFAULT_MODO_GIORNI = MODO_SETTIMANALE
DEFAULT_CICLO_GIORNI = 3

# Quanto si attende che una valvola confermi l'apertura, e quante volte si
# ripete il comando. Una zona che non apre irriga per zero minuti in
# silenzio, e te ne accorgi dal prato tre settimane dopo.
ATTESA_APERTURA = 6.0
TENTATIVI_APERTURA = 3

DAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

def zone_duration_key(zone_id: str) -> str:
    """Chiave del number con la durata base della zona."""
    return f"{zone_id}_duration"

def zone_manual_key(zone_id: str) -> str:
    """Chiave dello switch di apertura manuale della zona."""
    return f"{zone_id}_manual"

# --- Parametri operativi ------------------------------------------------------
# Pausa fra una zona e la successiva: da' tempo alla valvola di chiudere
# davvero prima che la seguente apra, evitando il colpo d'ariete.
PAUSE_BETWEEN_ZONES = 15

# Il watchdog gira ogni minuto; una valvola aperta senza che il controller
# la stia pilotando viene chiusa dopo questo numero di rilevazioni.
WATCHDOG_INTERVAL = 60
WATCHDOG_STRIKES = 2

# Master/pompa: ritardo fra apertura della zona e avvio del master, e fra
# arresto del master e chiusura della zona. Servono a non mandare mai in
# pressione una pompa contro valvole chiuse.
DEFAULT_MASTER_LEAD = 3
DEFAULT_MASTER_LAG = 3

DEFAULT_MINUTES = 15
DEFAULT_SEASONAL = 100.0
DEFAULT_RAIN_THRESHOLD = 2.0
DEFAULT_RAIN_HOURS = 12

# Ore all'indietro considerate nel bilancio della pioggia. Il servizio delle
# previsioni restituisce solo il futuro: la pioggia gia' caduta se la
# costruisce l'integrazione campionando l'ora corrente, quindi esiste solo da
# quando l'integrazione e' in funzione.
DEFAULT_RAIN_HOURS_PAST = 12

# Ogni quanto si campiona la precipitazione dell'ora in corso.
RAIN_SAMPLE_MINUTES = 15

# --- Bilancio idrico del terreno ----------------------------------------------
# I due valori vengono dalla letteratura agronomica (FAO 56), non da una
# media inventata, ma restano un punto di partenza da correggere guardando
# il prato: dipendono da tessitura del suolo, profondita' radicale, specie
# del tappeto erboso ed esposizione.
#
# Capacita': l'acqua utile trattenuta dalla zona radicale. Un terreno medio
# ne trattiene 140-180 mm per metro di profondita', e un prato radica sui
# 15-25 cm. Su sabbia scende alla meta'.
DEFAULT_SOIL_CAPACITY = 25.0

# Evapotraspirazione giornaliera di riferimento in piena estate alle nostre
# latitudini. D'inverno vale un quarto: la scala il fattore stagionale, lo
# stesso che scala la durata dell'irrigazione.
DEFAULT_DAILY_ET = 4.0

# Sotto questa riserva il prato comincia a soffrire e si irriga. E' circa
# meta' della capacita': oltre quel prelievo l'erba fatica a estrarre acqua.
DEFAULT_RESERVE_THRESHOLD = 10.0

# Quanti millimetri l'ora distribuiscono gli irrigatori: serve a riaccreditare
# nella riserva l'acqua che diamo noi, altrimenti il modello crede che il
# terreno sia sempre asciutto.
DEFAULT_PRECIP_RATE = 10.0

# --- Coefficiente colturale ---------------------------------------------------
# Il Kc e' una proprieta' dell'erba, non del luogo: la latitudine suggerisce
# quale specie sia probabile, ma dedurlo da li' sarebbe inventare precisione.
# Chi ha piantato una macroterma al nord si ritroverebbe il consumo
# sovrastimato di un terzo senza capire perche'. Si chiede quindi, e si
# chiede nella forma che l'utente sa rispondere: che erba hai.
PRATO_MICROTERME = "cool_season"
PRATO_MACROTERME = "warm_season"
PRATO_PERSONALIZZATO = "custom"
TIPI_PRATO = [PRATO_MICROTERME, PRATO_MACROTERME, PRATO_PERSONALIZZATO]

# Loietto, festuca, poa: i prati del centro e nord Europa.
KC_MICROTERME = 0.85
# Gramigna, zoysia, cynodon: i prati mediterranei e subtropicali.
KC_MACROTERME = 0.75
DEFAULT_KC = KC_MICROTERME

# Il Kc e' anche la manopola di taratura: l'ET0 calcola cio' che e'
# calcolabile, il Kc assorbe tutto il resto — suolo, esposizione, altezza
# di taglio, quanto verde si vuole il prato.
KC_MIN = 0.3
KC_MAX = 1.5
DEFAULT_START_HOUR = 6
