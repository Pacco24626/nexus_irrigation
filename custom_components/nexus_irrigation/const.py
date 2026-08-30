"""Costanti dell'integrazione Nexus Irrigation."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "nexus_irrigation"
MANUFACTURER = "Nexus-T"
MODEL = "Centralina irrigazione"

PLATFORMS: list[Platform] = [
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

CONF_RAIN_MODE = "rain_mode"
CONF_RAIN_ENTITY = "rain_entity"
CONF_RAIN_THRESHOLD = "rain_threshold"
CONF_RAIN_HOURS = "rain_hours"

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
KEY_RUNNING = "running"

KEY_DAY_PREFIX = "day_"
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

DEFAULT_MINUTES = 15
DEFAULT_SEASONAL = 100.0
DEFAULT_RAIN_THRESHOLD = 2.0
DEFAULT_RAIN_HOURS = 12
DEFAULT_START_HOUR = 6
