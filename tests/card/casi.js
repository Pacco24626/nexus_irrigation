/**
 * Casi di prova della scheda: gli attributi del sensore «Stato» come li
 * pubblica l'integrazione 1.6.0 (contratto, sezione 2) e un finto hass.
 *
 * Servono sia alle prove a tavolino (test_card.mjs, in node) sia alla prova
 * nel browser (prova_browser.js): per questo e' un modulo senza dipendenze.
 *
 * Il tempo e' sempre un parametro: «adesso» e' lunedi' 21 settembre 2026
 * alle 21:15, ora locale, come nell'anteprima approvata.
 */

export const STATO = "sensor.irrigazione_stato";
export const RISERVA = "sensor.irrigazione_riserva_idrica";
export const ABILITA = "switch.irrigazione_abilitata";
export const ORA = "time.irrigazione_ora_di_avvio";
export const AVVIA = "button.irrigazione_avvia_ciclo";
export const ARRESTA = "button.irrigazione_arresta";
export const GIORNI = ["lunedi", "martedi", "mercoledi", "giovedi", "venerdi", "sabato", "domenica"].map((g) => `switch.irrigazione_${g}`);

/** Lunedi' 21/09/2026 alle 21:15 (ora locale). */
export function adessoProva() {
  return new Date(2026, 8, 21, 21, 15, 0).getTime();
}

/** Un istante a partire da `adesso`: giorni, ore, minuti, secondi. */
export function istante(adesso, { giorni = 0, ore = 0, minuti = 0, secondi = 0 } = {}) {
  return new Date(adesso + (((giorni * 24 + ore) * 60 + minuti) * 60 + secondi) * 1000).toISOString();
}

/** Oggi alle hh:mm (ora locale), in ISO. */
export function oggiAlle(adesso, ore, minuti = 0, piuGiorni = 0) {
  const d = new Date(adesso);
  return new Date(d.getFullYear(), d.getMonth(), d.getDate() + piuGiorni, ore, minuti, 0).toISOString();
}

const NOMI = ["Zona 1", "Zona 2", "Aiuole ingresso", "Siepe", "Prato retro", "Orto", "Bordure", "Vialetto", "Frutteto", "Roseto", "Prato gazebo", "Bordo piscina"];
const TIPI = ["lawn", "lawn", "lawn", "drip", "lawn", "drip", "lawn", "lawn", "drip", "drip", "lawn", "lawn"];
const MINUTI = [10, 10, 8, 20, 12, 15, 8, 6, 20, 10, 10, 8];

/** Una zona come la pubblica il sensore Stato. */
export function zona(i, extra = {}) {
  const k = i - 1;
  const minuti = MINUTI[k % MINUTI.length];
  return {
    id: `zone_${i}`,
    name: NOMI[k % NOMI.length],
    valve: `valve.irrigatori_zona_${i}`,
    duration_entity: `number.irrigazione_zona_${i}_durata`,
    manual_entity: `switch.irrigazione_zona_${i}`,
    running: false,
    seconds: Math.round(minuti * 0.7 * 60),
    tipo: TIPI[k % TIPI.length],
    minutes: minuti,
    in_ciclo: true,
    ...extra,
  };
}

/** Gli attributi del sensore Stato: impianto di casa (2 zone), fermo, prossimo ciclo oggi alle 23. */
export function attributi(adesso, extra = {}) {
  const n = extra.n || 2;
  const zone = extra.zones || Array.from({ length: n }, (_, k) => zona(k + 1));
  const base = {
    installation: "Irrigazione",
    zones: zone,
    active_zone: null,
    zone_ends_at: null,
    enable_entity: ABILITA,
    start_time_entity: ORA,
    seasonal_entity: "number.irrigazione_fattore_stagionale",
    start_button: AVVIA,
    stop_button: ARRESTA,
    rain_entity: "binary_sensor.irrigazione_pioggia",
    master_entity: null,
    master_valve: null,
    master_open: false,
    day_entities: GIORNI,
    rain_mode: "weather",
    next_cycle: oggiAlle(adesso, 23, 0),
    last_cycle: oggiAlle(adesso, 23, 41, -3),
    day_mode: "weekly",
    skip_reason: "",
    zone_non_aperte: [],
    // Nuovi della 1.6.0
    ruolo: "mappa_irrigazione",
    ciclo: zone.filter((z) => z.in_ciclo && z.seconds > 0).map((z) => z.id),
    ciclo_fatte: [],
    ciclo_non_aperte: [],
    in_apertura: false,
    manuale: false,
    pausa_fra_zone: 15,
    master_lead: 0,
    seasonal: 70.0,
    consumo_prato_mm: 1.83,
    riserva: { entita: RISERVA, soglia: 10, capacita: 25 },
    pioggia: { rilevata: false, caduta_mm: 0, prevista_mm: 0, ore_passate: 12, ore_previste: 12 },
  };
  const risultato = { ...base, ...extra };
  delete risultato.n;
  return risultato;
}

/**
 * Tutti gli stati che la scheda legge: il sensore Stato e le entita' collegate.
 * `opzioni.giorni`: i giorni accesi (lun, mer, ven come in casa).
 */
export function stati(attr, statoSensore = "idle", opzioni = {}) {
  const giorniAccesi = opzioni.giorni || [true, false, true, false, true, false, false];
  const tutti = {
    [STATO]: { entity_id: STATO, state: statoSensore, attributes: attr },
    [ABILITA]: { entity_id: ABILITA, state: opzioni.abilitata === false ? "off" : "on", attributes: {} },
    [ORA]: { entity_id: ORA, state: opzioni.ora || "23:00:00", attributes: {} },
    [RISERVA]: { entity_id: RISERVA, state: String(opzioni.riserva ?? 9.8), attributes: { unit_of_measurement: "mm" } },
  };
  GIORNI.forEach((id, i) => {
    tutti[id] = { entity_id: id, state: giorniAccesi[i] ? "on" : "off", attributes: {} };
  });
  (attr.zones || []).forEach((z) => {
    tutti[z.duration_entity] = { entity_id: z.duration_entity, state: String(z.minutes), attributes: { unit_of_measurement: "min" } };
    tutti[z.manual_entity] = { entity_id: z.manual_entity, state: z.running ? "on" : "off", attributes: {} };
  });
  return tutti;
}

/** Un finto hass: stati, tema, lingua, e un callService che si segna le chiamate. */
export function fintoHass(tuttiGliStati, scuro = false, chiamate = []) {
  return {
    states: tuttiGliStati,
    themes: { darkMode: scuro },
    locale: { language: "it" },
    chiamate,
    callService(dominio, servizio, dati) {
      chiamate.push({ dominio, servizio, dati });
      return Promise.resolve();
    },
    formatEntityState(stato) {
      const unita = stato.attributes && stato.attributes.unit_of_measurement;
      const valore = String(stato.state).replace(".", ",");
      return unita ? `${valore} ${unita}` : valore;
    },
  };
}
