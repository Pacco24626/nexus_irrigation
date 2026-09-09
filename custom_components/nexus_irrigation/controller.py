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

from .evapotraspirazione import K_RS_COSTIERO, K_RS_INTERNO, et0

from .const import (
    CONF_MASTER_ENTITY,
    CONF_MASTER_LAG,
    CONF_MASTER_LEAD,
    CONF_RAIN_ENTITY,
    CONF_RAIN_HOURS,
    CONF_COSTA,
    CONF_DAILY_ET,
    CONF_ET0_SENSOR,
    CONF_KC,
    CONF_PRECIP_RATE,
    CONF_RAIN_HOURS_PAST,
    CONF_RAIN_MODE,
    CONF_RAIN_THRESHOLD,
    CONF_RESERVE_THRESHOLD,
    CONF_SOIL_CAPACITY,
    CONF_TIPO_PRATO,
    CONF_ZONE_ENTITY,
    CONF_ZONE_ID,
    CONF_ZONE_MINUTES,
    CONF_ZONE_NAME,
    CONF_ZONES,
    DEFAULT_MASTER_LAG,
    DEFAULT_MASTER_LEAD,
    DEFAULT_RAIN_HOURS,
    DEFAULT_DAILY_ET,
    DEFAULT_PRECIP_RATE,
    DEFAULT_RAIN_HOURS_PAST,
    DEFAULT_RAIN_THRESHOLD,
    DEFAULT_RESERVE_THRESHOLD,
    DEFAULT_SOIL_CAPACITY,
    KC_MACROTERME,
    KC_MICROTERME,
    PRATO_MACROTERME,
    PRATO_MICROTERME,
    DEFAULT_SEASONAL,
    DEFAULT_START_HOUR,
    DOMAIN,
    PAUSE_BETWEEN_ZONES,
    RAIN_NONE,
    RAIN_SAMPLE_MINUTES,
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
        self.rain_hours_past: int = int(
            cfg.get(CONF_RAIN_HOURS_PAST, DEFAULT_RAIN_HOURS_PAST)
        )

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
        self.rain_recent: float = 0.0
        self.rain_forecast: float = 0.0
        # Pioggia caduta, ora per ora: chiave l'ora ISO, valore i mm.
        # Il servizio delle previsioni restituisce solo il futuro, quindi
        # il passato se lo costruisce l'integrazione campionando l'ora in
        # corso. E' una stima di met.no, non la misura di un pluviometro.
        self.rain_log: dict[str, float] = {}

        self.soil_capacity: float = float(
            cfg.get(CONF_SOIL_CAPACITY, DEFAULT_SOIL_CAPACITY)
        )
        self.daily_et: float = float(cfg.get(CONF_DAILY_ET, DEFAULT_DAILY_ET))
        self.reserve_threshold: float = float(
            cfg.get(CONF_RESERVE_THRESHOLD, DEFAULT_RESERVE_THRESHOLD)
        )
        self.precip_rate: float = float(
            cfg.get(CONF_PRECIP_RATE, DEFAULT_PRECIP_RATE)
        )
        self.tipo_prato: str = cfg.get(CONF_TIPO_PRATO, PRATO_MICROTERME)
        self.kc: float = self._kc_da_config(cfg)
        self.costa: bool = bool(cfg.get(CONF_COSTA, False))
        self.et0_sensor: str | None = cfg.get(CONF_ET0_SENSOR)
        self.et0_oggi: float | None = None
        # Si parte a meta' serbatoio: ne' assetato ne' zuppo, cosi' i primi
        # giorni il modello non prende una decisione forte su niente.
        self.reserve: float = self.soil_capacity / 2
        self._reserve_updated: datetime | None = None
        self._unsub_rain: CALLBACK_TYPE | None = None
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
        if self.rain_mode == RAIN_WEATHER and self.rain_hours_past > 0:
            self._unsub_rain = async_track_time_interval(
                self.hass,
                self._async_sample_rain,
                timedelta(minutes=RAIN_SAMPLE_MINUTES),
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
        if self._unsub_rain:
            self._unsub_rain()
            self._unsub_rain = None
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
        # is_running guarda il task: finche' il task non e' concluso davvero
        # resta vero, e la notifica del finally arriva troppo presto. Senza
        # questo richiamo il sensore "in irrigazione" resta acceso a ciclo
        # finito, fino al primo altro evento che ridisegna le entita'.
        self._task.add_done_callback(lambda _task: self.notify())

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

    def _credit_irrigation(self, seconds: int) -> None:
        """Riaccredita nella riserva l'acqua appena distribuita."""
        if self.balance_enabled:
            self._deplete(dt_util.now())
            self.add_water(self._irrigation_mm(seconds))

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
        acqua_da = None
        try:
            await self._async_begin_zone(zone)
            self.zone_ends_at = dt_util.now() + timedelta(seconds=seconds)
            acqua_da = dt_util.now()
            self.notify()
            await asyncio.sleep(seconds)
        finally:
            # Si accredita l'acqua effettivamente distribuita, non quella
            # programmata: un ciclo interrotto a meta' ha bagnato a meta'.
            if acqua_da is not None:
                erogati = (dt_util.now() - acqua_da).total_seconds()
                self._credit_irrigation(int(min(seconds, max(0, erogati))))
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



    @staticmethod
    def _kc_da_config(cfg: dict) -> float:
        """Il coefficiente colturale, dal tipo di prato o dal valore libero."""
        tipo = cfg.get(CONF_TIPO_PRATO, PRATO_MICROTERME)
        if tipo == PRATO_MICROTERME:
            return KC_MICROTERME
        if tipo == PRATO_MACROTERME:
            return KC_MACROTERME
        return float(cfg.get(CONF_KC, KC_MICROTERME))

    # -------------------------------------------------------------------------
    # Evapotraspirazione
    # -------------------------------------------------------------------------
    @property
    def consumo_giornaliero(self) -> float:
        """Millimetri che il prato consuma in un giorno.

        Con l'ET0 disponibile il fattore stagionale non entra: la stagione la
        conta gia' il calcolo, che a dicembre da' mezzo millimetro e a luglio
        cinque. Applicarlo di nuovo la conterebbe due volte.
        """
        if self.et0_oggi is not None:
            return self.et0_oggi * self.kc
        return self.daily_et * (self.seasonal / 100.0)

    async def _async_daily_forecast(self) -> list[dict] | None:
        try:
            response = await self.hass.services.async_call(
                "weather",
                "get_forecasts",
                {"type": "daily"},
                target={"entity_id": self.rain_entity},
                blocking=True,
                return_response=True,
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("%s: previsioni giornaliere non ottenute (%s)", self.name, err)
            return None
        return (response or {}).get(self.rain_entity, {}).get("forecast") or None

    async def _async_update_et0(self) -> None:
        """Ricalcola l'evapotraspirazione di riferimento del giorno.

        Se qualcosa manca si lascia il valore precedente, e se non c'e' mai
        stato si ripiega sul consumo fisso: un dato meteo assente non deve
        fermare l'irrigazione.
        """
        if self.et0_sensor:
            stato = self.hass.states.get(self.et0_sensor)
            if stato is not None and stato.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE):
                try:
                    self.et0_oggi = max(0.0, float(stato.state))
                    return
                except (TypeError, ValueError):
                    pass

        forecast = await self._async_daily_forecast()
        if not forecast:
            return

        oggi = forecast[0]
        try:
            t_max = float(oggi["temperature"])
            t_min = float(oggi["templow"])
            umidita = float(oggi.get("humidity") or 70)
            # met.no da' il vento in km/h a 10 metri.
            vento_ms = float(oggi.get("wind_speed") or 0) / 3.6
        except (KeyError, TypeError, ValueError):
            return

        adesso = dt_util.now()
        self.et0_oggi = et0(
            t_max=t_max,
            t_min=t_min,
            umidita_pct=umidita,
            vento_ms=vento_ms,
            latitudine=self.hass.config.latitude,
            giorno_anno=adesso.timetuple().tm_yday,
            quota_m=self.hass.config.elevation or 0,
            k_rs=K_RS_COSTIERO if self.costa else K_RS_INTERNO,
        )
        _LOGGER.debug(
            "%s: ET0 %.2f mm/g (Tmax %.1f Tmin %.1f UR %.0f%% vento %.1f m/s), "
            "consumo del prato %.2f mm/g",
            self.name, self.et0_oggi, t_max, t_min, umidita, vento_ms,
            self.consumo_giornaliero,
        )

    # -------------------------------------------------------------------------
    # Bilancio idrico
    # -------------------------------------------------------------------------
    @property
    def balance_enabled(self) -> bool:
        """Il bilancio vale solo con la sorgente meteo e una capacita' dichiarata."""
        return self.rain_mode == RAIN_WEATHER and self.soil_capacity > 0

    def _deplete(self, now: datetime) -> None:
        """Toglie dalla riserva l'acqua evaporata dall'ultimo aggiornamento.

        Il consumo giornaliero viene scalato dal fattore stagionale: e' la
        stessa manopola che scala la durata dell'irrigazione, e regola le due
        cose in modo coerente senza chiedere all'utente un secondo concetto.
        """
        if self._reserve_updated is None:
            self._reserve_updated = now
            return

        ore = (now - self._reserve_updated).total_seconds() / 3600.0
        if ore <= 0:
            return
        # Un salto enorme (riavvio lungo, orologio spostato) non deve svuotare
        # il serbatoio in un colpo solo.
        ore = min(ore, 48.0)

        consumo = self.consumo_giornaliero * ore / 24.0
        self.reserve = max(0.0, self.reserve - consumo)
        self._reserve_updated = now

    def add_water(self, mm: float) -> None:
        """Aggiunge acqua alla riserva, senza superare la capacita'.

        Il tetto e' la parte che risolve il caso della settimana di pioggia:
        oltre la capacita' l'acqua drena e non va contata, ma quello che sta
        dentro resta li' per giorni.
        """
        if mm <= 0:
            return
        self.reserve = min(self.soil_capacity, self.reserve + mm)
        self.notify()

    def _irrigation_mm(self, seconds: int) -> float:
        return self.precip_rate * seconds / 3600.0

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

    async def _async_hourly_forecast(self) -> list[dict] | None:
        """Le previsioni orarie, o None se non si riesce a ottenerle."""
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
                "%s: previsioni da %s non ottenute (%s)",
                self.name,
                self.rain_entity,
                err,
            )
            return None

        return (response or {}).get(self.rain_entity, {}).get("forecast") or None

    async def _async_sample_rain(self, _now=None) -> None:
        """Registra la precipitazione dell'ora in corso.

        Si tiene un valore per ciascuna ora, sovrascritto a ogni campione:
        campionare piu' volte la stessa ora non la conta piu' volte.
        """
        forecast = await self._async_hourly_forecast()
        if not forecast:
            return

        try:
            corrente = forecast[0]
            ora = str(corrente.get("datetime"))[:13]
            mm = float(corrente.get("precipitation") or 0)
        except (IndexError, TypeError, ValueError):
            return

        precedente = self.rain_log.get(ora, 0.0)
        self.rain_log[ora] = mm
        self._prune_rain_log()
        self.rain_recent = self.recent_rain_mm()

        if self.balance_enabled:
            # L'ET0 si aggiorna qui: un solo timer per entrambe le cose, e il
            # prelievo che segue usa subito il consumo del giorno.
            await self._async_update_et0()
            self._deplete(dt_util.now())
            # Si accredita solo l'incremento: la stessa ora viene campionata
            # piu' volte, e sommarla ogni volta gonfierebbe la riserva.
            self.add_water(max(0.0, mm - precedente))

        self.notify()

    def _prune_rain_log(self) -> None:
        """Butta via le ore uscite dalla finestra, piu' un margine."""
        if not self.rain_log:
            return
        limite = dt_util.now() - timedelta(hours=max(self.rain_hours_past, 1) + 6)
        soglia = limite.isoformat()[:13]
        for ora in [o for o in self.rain_log if o < soglia]:
            del self.rain_log[ora]

    def recent_rain_mm(self) -> float:
        """Millimetri caduti nelle ore passate della finestra."""
        if self.rain_hours_past <= 0 or not self.rain_log:
            return 0.0
        limite = dt_util.now() - timedelta(hours=self.rain_hours_past)
        soglia = limite.isoformat()[:13]
        return round(sum(mm for ora, mm in self.rain_log.items() if ora >= soglia), 1)

    async def _async_rain_from_weather(self) -> bool:
        """Bilancio della pioggia: quella gia' caduta piu' quella prevista.

        Guardare solo avanti lasciava passare il caso piu' ovvio — ha diluviato
        stamattina e il cielo si e' aperto — in cui il terreno e' zuppo ma la
        previsione e' asciutta.
        """
        forecast = await self._async_hourly_forecast()
        if forecast is None:
            _LOGGER.warning("%s: nessuna previsione disponibile, ciclo eseguito", self.name)
            return False

        prevista = 0.0
        for item in forecast[: self.rain_hours]:
            try:
                prevista += float(item.get("precipitation") or 0)
            except (TypeError, ValueError):
                continue

        caduta = self.recent_rain_mm()
        self.rain_forecast = round(prevista, 1)
        self.rain_recent = caduta

        if self.balance_enabled:
            self._deplete(dt_util.now())
            disponibile = self.reserve + prevista
            _LOGGER.debug(
                "%s: riserva %.1f mm piu' %.1f mm previsti, soglia %.1f",
                self.name,
                self.reserve,
                prevista,
                self.reserve_threshold,
            )
            return disponibile >= self.reserve_threshold

        totale = caduta + prevista
        _LOGGER.debug(
            "%s: %.1f mm caduti nelle ultime %d ore piu' %.1f mm previsti nelle "
            "prossime %d, soglia %.1f",
            self.name,
            caduta,
            self.rain_hours_past,
            prevista,
            self.rain_hours,
            self.rain_threshold,
        )
        return totale >= self.rain_threshold
