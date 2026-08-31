"""Controller dell'impianto: sequenza zone, meteo, watchdog, pianificazione.

Tutta la logica sta qui. Le entita' sono solo una vetrina: leggono lo stato
del controller e ne pilotano i parametri.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.const import (
    EVENT_HOMEASSISTANT_STARTED,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.helpers.event import (
    async_track_point_in_time,
    async_track_time_interval,
)
from homeassistant.util import dt as dt_util

from .const import (
    CONF_MASTER_ENTITY,
    CONF_MASTER_LAG,
    CONF_MASTER_LEAD,
    CONF_RAIN_ENTITY,
    CONF_RAIN_HOURS,
    CONF_RAIN_MODE,
    CONF_RAIN_THRESHOLD,
    CONF_ZONE_ENTITY,
    CONF_ZONE_ID,
    CONF_ZONE_MINUTES,
    CONF_ZONE_NAME,
    CONF_ZONES,
    DEFAULT_MASTER_LAG,
    DEFAULT_MASTER_LEAD,
    DEFAULT_RAIN_HOURS,
    DEFAULT_RAIN_THRESHOLD,
    DEFAULT_SEASONAL,
    DEFAULT_START_HOUR,
    DOMAIN,
    PAUSE_BETWEEN_ZONES,
    RAIN_NONE,
    RAIN_SENSOR,
    RAIN_WEATHER,
    STATUS_IDLE,
    STATUS_RAIN_SKIPPED,
    STATUS_RUNNING,
    WATCHDOG_INTERVAL,
    WATCHDOG_STRIKES,
)

_LOGGER = logging.getLogger(__name__)

# Stati che, su una valvola, significano "sta passando acqua".
OPEN_STATES = {"open", "opening", "on"}


@dataclass
class Zone:
    """Una zona irrigua."""

    id: str
    name: str
    entity_id: str
    minutes: float
    # Durata base corrente, modificabile a caldo dal number associato.
    duration: float = field(default=0.0)

    def __post_init__(self) -> None:
        if not self.duration:
            self.duration = float(self.minutes)


class IrrigationController:
    """Orchestra un singolo impianto (una config entry)."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry

        cfg = {**entry.data, **entry.options}
        self.name: str = cfg.get("name", "Irrigazione")
        self.zones: list[Zone] = [
            Zone(
                id=z[CONF_ZONE_ID],
                name=z[CONF_ZONE_NAME],
                entity_id=z[CONF_ZONE_ENTITY],
                minutes=float(z[CONF_ZONE_MINUTES]),
            )
            for z in cfg.get(CONF_ZONES, [])
        ]
        # Valvola master o rele' pompa: facoltativo, comune sugli impianti
        # con autoclave o con elettrovalvola generale a monte dei settori.
        self.master_entity: str | None = cfg.get(CONF_MASTER_ENTITY)
        self.master_lead: int = int(cfg.get(CONF_MASTER_LEAD, DEFAULT_MASTER_LEAD))
        self.master_lag: int = int(cfg.get(CONF_MASTER_LAG, DEFAULT_MASTER_LAG))

        self.rain_mode: str = cfg.get(CONF_RAIN_MODE, RAIN_NONE)
        self.rain_entity: str | None = cfg.get(CONF_RAIN_ENTITY)
        self.rain_threshold: float = float(
            cfg.get(CONF_RAIN_THRESHOLD, DEFAULT_RAIN_THRESHOLD)
        )
        self.rain_hours: int = int(cfg.get(CONF_RAIN_HOURS, DEFAULT_RAIN_HOURS))

        # --- Stato runtime, pilotato dalle entita' ---------------------------
        self.enabled: bool = True
        self.start_time: time = time(DEFAULT_START_HOUR, 0)
        self.seasonal: float = DEFAULT_SEASONAL
        self.days: list[bool] = [True] * 7

        # --- Stato osservabile ------------------------------------------------
        self.status: str = STATUS_IDLE
        self.active_zone: str | None = None
        self.zone_ends_at: datetime | None = None
        self.last_cycle: datetime | None = None
        self.next_cycle: datetime | None = None
        self.rain_detected: bool = False
        self.master_open: bool = False

        self._task: asyncio.Task | None = None
        self._unsub_schedule: CALLBACK_TYPE | None = None
        self._unsub_watchdog: CALLBACK_TYPE | None = None
        self._listeners: list[CALLBACK_TYPE] = []
        self._strikes: dict[str, int] = {}

    # -------------------------------------------------------------------------
    # Ciclo di vita
    # -------------------------------------------------------------------------
    async def async_setup(self) -> None:
        """Riparte da uno stato certo: valvole chiuse, watchdog attivo."""
        if self.hass.is_running:
            await self.async_close_all()
        else:
            # A boot in corso l'integrazione delle valvole potrebbe non aver
            # ancora registrato i propri servizi: si aspetta l'avvio completo.
            self.hass.bus.async_listen_once(
                EVENT_HOMEASSISTANT_STARTED, self._async_close_on_started
            )

        self._unsub_watchdog = async_track_time_interval(
            self.hass, self._async_watchdog, timedelta(seconds=WATCHDOG_INTERVAL)
        )
        self.reschedule()

    async def _async_close_on_started(self, _event) -> None:
        """Chiusura di sicurezza appena Home Assistant e' completamente avviato."""
        await self.async_close_all()

    async def async_shutdown(self) -> None:
        """Chiude tutto: e' l'ultima cosa che gira prima di scaricare l'entry."""
        await self.async_stop()
        if self._unsub_schedule:
            self._unsub_schedule()
            self._unsub_schedule = None
        if self._unsub_watchdog:
            self._unsub_watchdog()
            self._unsub_watchdog = None
        await self.async_close_all()

    @callback
    def async_add_listener(self, update: CALLBACK_TYPE) -> CALLBACK_TYPE:
        """Registra un'entita' che vuole essere ridisegnata a ogni cambio."""
        self._listeners.append(update)

        @callback
        def _remove() -> None:
            self._listeners.remove(update)

        return _remove

    @callback
    def notify(self) -> None:
        """Ridisegna tutte le entita' dell'impianto."""
        for update in list(self._listeners):
            update()

    # -------------------------------------------------------------------------
    # Parametri pilotati dalle entita'
    # -------------------------------------------------------------------------
    @callback
    def set_enabled(self, value: bool) -> None:
        self.enabled = value
        self.reschedule()

    @callback
    def set_start_time(self, value: time) -> None:
        self.start_time = value
        self.reschedule()

    @callback
    def set_seasonal(self, value: float) -> None:
        self.seasonal = value
        self.notify()

    @callback
    def set_day(self, index: int, value: bool) -> None:
        self.days[index] = value
        self.reschedule()

    @callback
    def set_zone_duration(self, zone_id: str, value: float) -> None:
        for zone in self.zones:
            if zone.id == zone_id:
                zone.duration = value
                break
        self.notify()

    def get_zone(self, zone_id: str) -> Zone | None:
        return next((z for z in self.zones if z.id == zone_id), None)

    # -------------------------------------------------------------------------
    # Pianificazione
    # -------------------------------------------------------------------------
    @callback
    def reschedule(self) -> None:
        """Ricalcola e riarma il prossimo avvio automatico."""
        if self._unsub_schedule:
            self._unsub_schedule()
            self._unsub_schedule = None

        self.next_cycle = self._compute_next()
        if self.next_cycle is not None:
            self._unsub_schedule = async_track_point_in_time(
                self.hass, self._async_scheduled_start, self.next_cycle
            )
        self.notify()

    def _compute_next(self) -> datetime | None:
        """Prossima occorrenza valida, o None se non ne esistono."""
        if not self.enabled or not any(self.days):
            return None

        now = dt_util.now()
        base = now.replace(
            hour=self.start_time.hour,
            minute=self.start_time.minute,
            second=0,
            microsecond=0,
        )
        for offset in range(8):
            candidate = base + timedelta(days=offset)
            if candidate > now and self.days[candidate.weekday()]:
                return candidate
        return None

    async def _async_scheduled_start(self, _now: datetime) -> None:
        self._unsub_schedule = None
        await self.async_start_cycle()

    # -------------------------------------------------------------------------
    # Esecuzione
    # -------------------------------------------------------------------------
    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def async_start_cycle(self, check_rain: bool = True) -> None:
        """Avvia il ciclo completo. Ignorato se ne e' gia' in corso uno."""
        if self.is_running:
            _LOGGER.debug("%s: ciclo gia' in corso, avvio ignorato", self.name)
            return
        self._task = self.entry.async_create_background_task(
            self.hass, self._async_run_cycle(check_rain), f"{DOMAIN}_cycle"
        )

    async def async_start_zone(self, zone_id: str) -> None:
        """Avvia una singola zona a mano (salta il controllo pioggia)."""
        if self.is_running:
            return
        zone = self.get_zone(zone_id)
        if zone is None:
            return
        self._task = self.entry.async_create_background_task(
            self.hass, self._async_single_zone(zone), f"{DOMAIN}_zone"
        )

    async def async_stop(self) -> None:
        """Interrompe qualunque cosa sia in corso e chiude le valvole."""
        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        self._task = None
        await self.async_close_all()
        self.status = STATUS_IDLE
        self.active_zone = None
        self.zone_ends_at = None
        self.notify()

    def zone_seconds(self, zone: Zone) -> int:
        """Durata effettiva della zona, fattore stagionale applicato."""
        return int(round(zone.duration * (self.seasonal / 100.0) * 60))

    async def _async_run_cycle(self, check_rain: bool) -> None:
        try:
            if check_rain and await self._async_rain_blocks():
                self.status = STATUS_RAIN_SKIPPED
                self.notify()
                persistent_notification.async_create(
                    self.hass,
                    f"Ciclo di {self.name} non eseguito: pioggia rilevata o "
                    f"prevista oltre la soglia di {self.rain_threshold} mm.",
                    title="Irrigazione saltata",
                    notification_id=f"{DOMAIN}_{self.entry.entry_id}_rain",
                )
                return

            for index, zone in enumerate(self.zones):
                seconds = self.zone_seconds(zone)
                if seconds <= 0:
                    continue
                await self._async_run_zone(zone, seconds)
                if index < len(self.zones) - 1:
                    # La pausa deve coprire anche il lag del master, altrimenti
                    # il settore successivo aprirebbe mentre il precedente si
                    # sta ancora chiudendo, con due zone in pressione insieme.
                    await asyncio.sleep(
                        max(PAUSE_BETWEEN_ZONES, self.master_lag + 5)
                        if self.master_entity
                        else PAUSE_BETWEEN_ZONES
                    )

            self.last_cycle = dt_util.now()
            self.status = STATUS_IDLE
        finally:
            self.active_zone = None
            self.zone_ends_at = None
            if self.status == STATUS_RUNNING:
                self.status = STATUS_IDLE
            self.reschedule()

    async def _async_single_zone(self, zone: Zone) -> None:
        seconds = self.zone_seconds(zone)
        try:
            if seconds > 0:
                await self._async_run_zone(zone, seconds)
            self.last_cycle = dt_util.now()
        finally:
            self.status = STATUS_IDLE
            self.active_zone = None
            self.zone_ends_at = None
            self.notify()

    async def _async_run_zone(self, zone: Zone, seconds: int) -> None:
        """Apre, attende, chiude.

        La chiusura sta in un finally, quindi vale anche in caso di
        annullamento del task: e' la differenza sostanziale rispetto a un
        delay in uno script YAML, che se interrotto lascia la valvola aperta.
        """
        self.status = STATUS_RUNNING
        self.active_zone = zone.id
        # Il conto alla rovescia parte a valle dell'avvio del master: i
        # secondi impostati sono secondi d'acqua, non di sequenza.
        self.zone_ends_at = dt_util.now() + timedelta(
            seconds=seconds + (self.master_lead if self.master_entity else 0)
        )
        self.notify()
        try:
            await self._async_begin_zone(zone)
            self.zone_ends_at = dt_util.now() + timedelta(seconds=seconds)
            self.notify()
            await asyncio.sleep(seconds)
        finally:
            # Non si attende qui: durante un cancel l'await verrebbe
            # interrotto a sua volta e le valvole resterebbero aperte.
            self.hass.async_create_task(self._async_end_zone(zone))
            self.active_zone = None
            self.zone_ends_at = None
            self.notify()

    async def _async_begin_zone(self, zone: Zone) -> None:
        """Apertura ordinata: prima il settore, poi il master.

        L'ordine non e' arbitrario. Avviare una pompa contro valvole ancora
        chiuse la manda in pressione a vuoto: colpo d'ariete alla partenza e,
        sulle autoclavi, intervento del pressostato.
        """
        await self._async_set_valve(zone.entity_id, True)
        if not self.master_entity:
            return
        if self.master_lead:
            await asyncio.sleep(self.master_lead)
        await self._async_set_master(True)

    async def _async_end_zone(self, zone: Zone) -> None:
        """Chiusura ordinata: prima il master, poi il settore.

        Speculare all'apertura: si toglie pressione e solo dopo si chiude il
        settore, cosi' la colonna d'acqua si ferma contro una valvola aperta.
        """
        if self.master_entity:
            await self._async_set_master(False)
            if self.master_lag:
                await asyncio.sleep(self.master_lag)
        await self._async_set_valve(zone.entity_id, False)

    # -------------------------------------------------------------------------
    # Valvole
    # -------------------------------------------------------------------------
    async def _async_set_valve(self, entity_id: str, open_it: bool) -> None:
        domain = entity_id.split(".", 1)[0]
        if domain == "valve":
            service = "open_valve" if open_it else "close_valve"
        else:
            service = "turn_on" if open_it else "turn_off"
        try:
            await self.hass.services.async_call(
                domain, service, {"entity_id": entity_id}, blocking=True
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("%s: comando %s su %s fallito: %s", self.name, service, entity_id, err)

    async def _async_set_master(self, open_it: bool) -> None:
        """Comanda la valvola master o il rele' della pompa."""
        if not self.master_entity:
            return
        await self._async_set_valve(self.master_entity, open_it)
        self.master_open = open_it
        self.notify()

    async def async_close_all(self) -> None:
        """Chiusura generale: prima il master, poi i settori."""
        await self._async_set_master(False)
        for zone in self.zones:
            await self._async_set_valve(zone.entity_id, False)

    def valve_is_open(self, entity_id: str) -> bool:
        state = self.hass.states.get(entity_id)
        return state is not None and state.state in OPEN_STATES

    # -------------------------------------------------------------------------
    # Watchdog
    # -------------------------------------------------------------------------
    async def _async_watchdog(self, _now: datetime) -> None:
        """Chiude qualunque valvola aperta che il controller non sta pilotando.

        Copre il caso in cui qualcuno apra la valvola a mano e se ne dimentichi,
        e quello in cui un comando di chiusura sia andato perso sul bus.
        """
        for zone in self.zones:
            owned = self.is_running and self.active_zone == zone.id
            await self._async_watch_valve(
                zone.id, zone.entity_id, f"della zona {zone.name}", owned
            )

        if self.master_entity:
            # Il master e' legittimo solo mentre una zona sta irrigando: se
            # resta aperto da solo, la pompa sta girando a secco.
            await self._async_watch_valve(
                "master",
                self.master_entity,
                "master",
                self.is_running and self.active_zone is not None,
            )

    async def _async_watch_valve(
        self, key: str, entity_id: str, etichetta: str, owned: bool
    ) -> None:
        """Chiude una valvola aperta che il controller non sta pilotando."""
        if owned or not self.valve_is_open(entity_id):
            self._strikes[key] = 0
            return

        self._strikes[key] = self._strikes.get(key, 0) + 1
        if self._strikes[key] < WATCHDOG_STRIKES:
            return

        self._strikes[key] = 0
        _LOGGER.warning(
            "%s: watchdog chiude %s, aperta senza ciclo attivo", self.name, entity_id
        )
        await self._async_set_valve(entity_id, False)
        if key == "master":
            self.master_open = False
            self.notify()
        persistent_notification.async_create(
            self.hass,
            f"La valvola {etichetta} risultava aperta senza un ciclo attivo "
            f"ed e' stata chiusa dal watchdog.",
            title="Irrigazione: chiusura di emergenza",
            notification_id=f"{DOMAIN}_{self.entry.entry_id}_wd_{key}",
        )

    # -------------------------------------------------------------------------
    # Pioggia
    # -------------------------------------------------------------------------
    async def _async_rain_blocks(self) -> bool:
        """True se il ciclo va saltato per pioggia."""
        blocked = False
        if self.rain_mode == RAIN_SENSOR and self.rain_entity:
            blocked = self._rain_from_sensor()
        elif self.rain_mode == RAIN_WEATHER and self.rain_entity:
            blocked = await self._async_rain_from_weather()
        self.rain_detected = blocked
        self.notify()
        return blocked

    def _rain_from_sensor(self) -> bool:
        state = self.hass.states.get(self.rain_entity)
        if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            _LOGGER.warning(
                "%s: sensore pioggia %s non disponibile, ciclo eseguito",
                self.name,
                self.rain_entity,
            )
            return False

        if self.rain_entity.startswith("binary_sensor."):
            return state.state == "on"
        try:
            return float(state.state) >= self.rain_threshold
        except (TypeError, ValueError):
            _LOGGER.warning(
                "%s: valore non numerico da %s (%s)",
                self.name,
                self.rain_entity,
                state.state,
            )
            return False

    async def _async_rain_from_weather(self) -> bool:
        try:
            response = await self.hass.services.async_call(
                "weather",
                "get_forecasts",
                {"type": "hourly"},
                target={"entity_id": self.rain_entity},
                blocking=True,
                return_response=True,
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning(
                "%s: previsioni da %s non ottenute (%s), ciclo eseguito",
                self.name,
                self.rain_entity,
                err,
            )
            return False

        forecast = (response or {}).get(self.rain_entity, {}).get("forecast") or []
        if not forecast:
            _LOGGER.warning(
                "%s: %s non fornisce previsioni orarie, ciclo eseguito",
                self.name,
                self.rain_entity,
            )
            return False

        total = 0.0
        for item in forecast[: self.rain_hours]:
            try:
                total += float(item.get("precipitation") or 0)
            except (TypeError, ValueError):
                continue

        _LOGGER.debug("%s: %.1f mm previsti nelle prossime %d ore", self.name, total, self.rain_hours)
        return total >= self.rain_threshold
