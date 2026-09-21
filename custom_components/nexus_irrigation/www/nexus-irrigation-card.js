/**
 * Nexus Irrigation — scheda del sinottico animato, con i comandi dentro.
 *
 * Contatore, master, collettore, valvole e aiuole (a irrigatori o a goccia):
 * l'acqua scorre verso la zona in funzione, i getti girano, le gocce cadono.
 * Toccando una zona se ne regola la durata, il suo ▶ la avvia da sola; in
 * fondo giorni, ora di avvio, «Avvia ciclo» e «Arresta».
 *
 * La scheda non si configura con le entita': legge il sensore «Stato»
 * dell'integrazione, dove stanno le zone, le entita' di comando e lo stato del
 * giro. Il disegno si costruisce per qualunque numero di zone e si rifa' solo
 * quando cambia l'impianto (la «firma»): durate, stati e comandi cambiano
 * soltanto colori, testi e animazioni.
 *
 * Le funzioni di calcolo sono esportate e si provano a tavolino:
 * tests/card/test_card.mjs; il disegno e i comandi: tests/card/prova_browser.js
 */

const VERSIONE_CARD = "1.6.0";
const DOMINIO = "nexus_irrigation";
const RUOLO_MAPPA = "mappa_irrigazione";
const ELEMENTO = "nexus-irrigation-card";
const NOME_INTEGRAZIONE = "Nexus Irrigation";
const DESCRIZIONE_CARD = "Irrigazione animata: zone, valvole e getti si muovono con l'impianto vero, e i comandi stanno dentro la scheda.";

const BLU = "#3C84C6";
const GIORNI = ["Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom"];
const GIORNI_BREVI = ["lun", "mar", "mer", "gio", "ven", "sab", "dom"];
const GIORNI_LUNGHI = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"];
const CONFERMA_MS = 4000; // quanto resta armato «Conferma: irriga ora»
const LARGHEZZA_COMPATTA = 560; // sotto questa larghezza due zone per riga
const DURATA_MASSIMA_CURSORE = 60; // minuti

// -----------------------------------------------------------------------------
// Logica: tutto cio' che si puo' sbagliare in silenzio, e che si prova da solo
// -----------------------------------------------------------------------------
const NON_VALIDI = new Set(["unknown", "unavailable", "none", ""]);

/** Il numero di uno stato di Home Assistant, o null se non e' un numero. */
export function numero(stato) {
  if (stato === null || stato === undefined) return null;
  const grezzo = typeof stato === "object" ? stato.state : stato;
  if (grezzo === null || grezzo === undefined) return null;
  const testo = String(grezzo).trim();
  if (NON_VALIDI.has(testo.toLowerCase())) return null;
  const valore = Number(testo.replace(",", "."));
  return Number.isFinite(valore) ? valore : null;
}

/** Vero se lo stato c'e' ed e' utilizzabile (non sconosciuto, non non-disponibile). */
export function valido(stato) {
  if (!stato || stato.state === undefined) return false;
  return !NON_VALIDI.has(String(stato.state).trim().toLowerCase());
}

/** I testi che vengono dall'utente (nomi, titolo, motivi) non diventano mai HTML. */
export function testoSicuro(testo) {
  return String(testo).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

/** Accorcia un nome che non ci sta: `spazio` in unita' del disegno, `dim` la dimensione del carattere. */
export function tronca(testo, spazio, dim) {
  const massimo = Math.max(4, Math.floor(spazio / (dim * 0.56)));
  return testo.length > massimo ? `${testo.slice(0, massimo - 1)}…` : testo;
}

/**
 * Accorcia i nomi delle zone misurandoli davvero, fino al bottone ▶: la stima a
 * caratteri di `tronca` sbaglia con le maiuscole (sforano) e con le minuscole
 * (tagliano quando c'e' posto). Restituisce false se la scheda non e' ancora a
 * video e non si puo' misurare.
 */
export function adattaNomi(radice) {
  let misurati = true;
  radice.querySelectorAll("[data-nome-zona]").forEach((nodo) => {
    const nome = nodo.getAttribute("data-nome") || "";
    const spazio = Number(nodo.getAttribute("data-spazio")) || 0;
    nodo.textContent = nome;
    let larghezza = 0;
    try {
      larghezza = nodo.getComputedTextLength();
    } catch (errore) {
      larghezza = 0;
    }
    if (larghezza <= 0) {
      if (nome) misurati = false;
      nodo.textContent = tronca(nome, spazio + 56, 24);
      return;
    }
    let lunghezza = nome.length;
    while (larghezza > spazio && lunghezza > 1) {
      lunghezza -= 1;
      nodo.textContent = `${nome.slice(0, lunghezza).trimEnd()}…`;
      larghezza = nodo.getComputedTextLength();
    }
  });
  return misurati;
}

/** Un istante (ISO o millisecondi) in millisecondi, o null. */
export function tempo(istante) {
  if (istante === null || istante === undefined || istante === "") return null;
  const valore = typeof istante === "number" ? istante : Date.parse(istante);
  return Number.isFinite(valore) ? valore : null;
}

function dueCifre(n) {
  return String(n).padStart(2, "0");
}

/** HH:MM nell'ora locale. */
export function orario(istante) {
  const t = tempo(istante);
  if (t === null) return "—";
  const d = new Date(t);
  return `${dueCifre(d.getHours())}:${dueCifre(d.getMinutes())}`;
}

/** Conto alla rovescia: m:ss. */
export function durata(secondi) {
  const s = Math.max(0, Math.ceil(Number(secondi) || 0));
  return `${Math.floor(s / 60)}:${dueCifre(s % 60)}`;
}

/** I minuti d'acqua veri di una zona: «0 min» solo se davvero non irriga. */
export function minutiEffettivi(secondi) {
  const s = Number(secondi) || 0;
  if (s <= 0) return "0 min";
  return `${Math.max(1, Math.round(s / 60))} min`;
}

/** Quanti giorni di calendario separano `istante` da `adesso` (0 oggi, 1 domani, -1 ieri). */
export function scartoGiorni(istante, adesso) {
  const a = new Date(adesso);
  const b = new Date(istante);
  const giornoA = new Date(a.getFullYear(), a.getMonth(), a.getDate());
  const giornoB = new Date(b.getFullYear(), b.getMonth(), b.getDate());
  // Math.round: con l'ora legale un giorno puo' durare 23 o 25 ore
  return Math.round((giornoB - giornoA) / 86400000);
}

/**
 * Quando, detto come lo direbbe una persona.
 * - "breve": «oggi 23:00», «domani 23:00», «mer 23:00» (il riquadro)
 * - "lungo": «oggi alle 23:00», «mercoledì alle 23:00» (le tessere)
 * - "zona":  «Alle 23:00», «Domani 23:00», «Mer 23:00» (lo stato di una zona)
 * Oltre la settimana: la data, «12/10 23:00».
 */
export function quando(istante, adesso = Date.now(), forma = "breve") {
  const t = tempo(istante);
  if (t === null) return "";
  const s = scartoGiorni(t, adesso);
  const d = new Date(t);
  const ora = orario(t);
  const indice = (d.getDay() + 6) % 7; // da lunedi'
  const data = `${dueCifre(d.getDate())}/${dueCifre(d.getMonth() + 1)}`;
  const vicino = Math.abs(s) < 7;
  if (forma === "lungo") {
    const giorno = s === 0 ? "oggi" : s === 1 ? "domani" : s === -1 ? "ieri" : vicino ? GIORNI_LUNGHI[indice] : `il ${data}`;
    return `${giorno} alle ${ora}`;
  }
  if (forma === "zona") {
    const giorno = s === 0 ? "Alle" : s === 1 ? "Domani" : vicino ? GIORNI[indice] : data;
    return `${giorno} ${ora}`;
  }
  const giorno = s === 0 ? "oggi" : s === 1 ? "domani" : s === -1 ? "ieri" : vicino ? GIORNI_BREVI[indice] : data;
  return `${giorno} ${ora}`;
}

/** Un numero scritto come si scrive nella lingua dell'utente. */
export function numeroTesto(valore, decimaliMax = 1, lingua = "it", decimaliMin = 0) {
  const v = Number(valore);
  try {
    return v.toLocaleString(lingua, { minimumFractionDigits: decimaliMin, maximumFractionDigits: decimaliMax });
  } catch (errore) {
    return String(Math.round(v * 10 ** decimaliMax) / 10 ** decimaliMax);
  }
}

/** La nota sotto il cursore: la durata vera, fattore stagionale compreso. */
export function notaDurata(minuti, stagionale, lingua = "it") {
  const m = Number(minuti) || 0;
  if (m <= 0) return "A zero minuti la zona non irriga";
  const fattore = Number(stagionale);
  if (!Number.isFinite(fattore)) return `${numeroTesto(m, 1, lingua)} min`;
  // Lo stesso conto dell'integrazione: round(durata * fattore / 100 * 60) secondi
  const secondi = Math.round(m * (fattore / 100) * 60);
  return `${minutiEffettivi(secondi)} con il fattore stagionale del ${numeroTesto(fattore, 1, lingua)}%`;
}

/** Cosa dice il blocco della pioggia. */
export function testoPioggia(pioggia, lingua = "it") {
  if (!pioggia) return "—";
  const caduta = Number(pioggia.caduta_mm) || 0;
  const prevista = Number(pioggia.prevista_mm) || 0;
  const orePassate = Number(pioggia.ore_passate) || 0;
  if (caduta > 0 && orePassate > 0) return `${numeroTesto(caduta, 1, lingua, 1)} mm in ${orePassate} h`;
  if (prevista > 0) return `previsti ${numeroTesto(prevista, 1, lingua, 1)} mm`;
  return pioggia.rilevata ? "Piove" : "Asciutto";
}

// -----------------------------------------------------------------------------
// Disposizione: dove va ogni cosa, per qualunque numero di zone
// -----------------------------------------------------------------------------
/**
 * La fascia alta: contatore (e master) a sinistra, poi pioggia e riserva se ci
 * sono, poi i due riquadri. Quello che manca non lascia il buco: gli altri si
 * ricompattano. Sul telefono i riquadri scendono sotto, a meno che pioggia e
 * riserva manchino entrambe: allora salgono accanto al contatore.
 */
export function fasciaAlta({ compatta = false, pioggia = true, riserva = true } = {}) {
  if (!compatta) {
    const alto = { W: 1000, sx: 80, x0: 150, contatore: [80, 110], master: [80, 232], piccolo: false, inizio: 360, meteo: null, misura: null };
    let x = 240;
    if (pioggia) {
      alto.meteo = [x + 90, 118];
      x += 200;
    }
    if (riserva) {
      alto.misura = [x, 76];
      x += 220;
    }
    alto.riquadri = [{ x, y: 44, w: 970 - x }, { x, y: 156, w: 970 - x }];
    return alto;
  }
  const alto = { W: 640, sx: 62, x0: 108, contatore: [62, 110], master: [62, 232], piccolo: true, inizio: 480, meteo: null, misura: null };
  if (pioggia && riserva) {
    alto.meteo = [272, 118];
    alto.misura = [380, 76];
  } else if (pioggia) {
    alto.meteo = [398, 118];
  } else if (riserva) {
    alto.misura = [294, 76];
  }
  if (pioggia || riserva) {
    alto.riquadri = [{ x: 108, y: 318, w: 243 }, { x: 371, y: 318, w: 243 }];
  } else {
    alto.riquadri = [{ x: 214, y: 44, w: 400 }, { x: 214, y: 156, w: 400 }];
    alto.inizio = 360;
  }
  return alto;
}

/**
 * La griglia delle zone: tre per riga sulla plancia, due sulla scheda stretta,
 * righe bilanciate (7 = 3+2+2, mai una zona da sola se si puo' evitare) e
 * 4 zone = 2+2. Da tre righe in su le aiuole si abbassano.
 */
export function disposizione(zone, { compatta = false, pioggia = true, riserva = true } = {}) {
  const alto = fasciaAlta({ compatta, pioggia, riserva });
  const n = zone.length;
  if (n === 0) return { alto, compatta, colonne: 0, righe: 0, file: [], W: alto.W, H: alto.inizio };
  const maxColonne = compatta ? 2 : 3;
  let colonne = Math.min(maxColonne, n);
  if (!compatta && n === 4) colonne = 2;
  const righe = Math.ceil(n / colonne);
  const base = Math.floor(n / righe);
  const extra = n % righe;
  const x1 = alto.W - 26;
  const spazio = 22;
  const larghezza = Math.min((x1 - alto.x0 - spazio * (colonne - 1)) / colonne, 400);
  const letto = righe >= 3 ? 96 : 132;
  const altezza = letto + 118;
  const passo = altezza + 70;
  const file = [];
  let k = 0;
  for (let r = 0; r < righe; r += 1) {
    const quante = base + (r < extra ? 1 : 0);
    const y = alto.inizio + r * passo;
    const tessere = [];
    for (let c = 0; c < quante; c += 1) {
      const x = alto.x0 + c * (larghezza + spazio);
      tessere.push({ zona: zone[k], indice: k, x, y, w: larghezza, h: altezza, letto, vx: x + larghezza / 2 });
      k += 1;
    }
    file.push({ y, lineaY: y - 44, tessere });
  }
  return { alto, compatta, colonne, righe, file, W: alto.W, H: alto.inizio + righe * passo - 70 + 24 };
}

/** Quando rifare il disegno: solo se cambia l'impianto, mai per uno stato. */
export function firmaScena(attr, compatta) {
  const zone = Array.isArray(attr.zones) ? attr.zones : [];
  return [
    compatta ? "stretta" : "larga",
    attr.master_valve ? "master" : "",
    attr.pioggia ? "pioggia" : "",
    attr.riserva ? "riserva" : "",
    zone.map((z) => `${z.id}:${z.name}:${z.tipo === "drip" ? "drip" : "lawn"}`).join(","),
  ].join("|");
}

// -----------------------------------------------------------------------------
// Stato delle zone: dai dati del sensore a quello che la scheda mostra
// -----------------------------------------------------------------------------
function limita(valore, minimo, massimo) {
  return Math.max(minimo, Math.min(massimo, valore));
}

/**
 * Il quadro dell'impianto in questo istante: per ogni zona classe, scritta,
 * avanzamento, se il suo comando avvia o ferma; e gli orari stimati.
 *
 * `pausaDa`: quando la scheda ha visto cominciare la pausa fra due zone (null
 * se non lo sa): serve solo a stimare meglio gli orari in coda.
 */
export function quadroImpianto(attr, stato, adesso = Date.now(), pausaDa = null) {
  const zone = Array.isArray(attr.zones) ? attr.zones : [];
  const inCorso = stato === "running";
  const saltato = stato === "rain_skipped" || stato === "reserve_skipped";
  const manuale = inCorso && Boolean(attr.manuale);
  const perId = new Map(zone.map((z) => [z.id, z]));
  const attiva = inCorso && attr.active_zone ? perId.get(attr.active_zone) || null : null;
  const apertura = Boolean(attiva) && Boolean(attr.in_apertura);
  const pausa = inCorso && !attiva && !manuale;
  const fatte = new Set(Array.isArray(attr.ciclo_fatte) ? attr.ciclo_fatte : []);
  const nonAperte = new Set(Array.isArray(attr.ciclo_non_aperte) ? attr.ciclo_non_aperte : []);
  const secondi = (z) => Math.max(0, Number(z && z.seconds) || 0);
  const ordine = Array.isArray(attr.ciclo) ? attr.ciclo : zone.filter((z) => secondi(z) > 0).map((z) => z.id);
  const pausaFra = Math.max(0, Number(attr.pausa_fra_zone) || 0);
  const anticipo = Math.max(0, Number(attr.master_lead) || 0);
  // Una zona occupa il suo anticipo del master piu' i suoi secondi d'acqua
  const occupa = (z) => (secondi(z) + anticipo) * 1000;

  const fine = tempo(attr.zone_ends_at);
  const rimanenti = attiva ? (fine === null ? secondi(attiva) : Math.max(0, (fine - adesso) / 1000)) : null;
  // In pausa aspetta la prima zona del giro non ancora fatta e non fallita
  const inAttesa = pausa ? ordine.find((id) => !fatte.has(id) && !nonAperte.has(id) && perId.has(id)) || null : null;
  const restoPausa = pausa ? (pausaDa === null ? pausaFra : Math.max(0, pausaFra - (adesso - pausaDa) / 1000)) : 0;

  // Quando parte ogni zona ancora da fare
  const partenze = {};
  let fineCiclo = null;
  if (inCorso && !manuale) {
    let t = adesso;
    let coda = [];
    let pausaPrima = pausaFra;
    if (attiva) {
      t += rimanenti * 1000;
      coda = ordine.slice(ordine.indexOf(attiva.id) + 1);
    } else if (inAttesa) {
      pausaPrima = restoPausa;
      coda = ordine.slice(ordine.indexOf(inAttesa));
    }
    coda.forEach((id) => {
      const z = perId.get(id);
      // Come l'integrazione: una zona a zero secondi si salta, senza pausa
      if (!z || (attiva && id === attiva.id) || fatte.has(id) || nonAperte.has(id) || secondi(z) <= 0) return;
      t += pausaPrima * 1000;
      partenze[id] = t;
      t += occupa(z);
      pausaPrima = pausaFra;
    });
    fineCiclo = attiva || inAttesa ? t : null;
  } else if (manuale) {
    fineCiclo = fine;
  } else {
    const prossimo = tempo(attr.next_cycle);
    if (prossimo !== null) {
      let t = prossimo;
      let primo = true;
      ordine.forEach((id) => {
        const z = perId.get(id);
        if (!z || secondi(z) <= 0) return;
        if (!primo) t += pausaFra * 1000;
        partenze[id] = t;
        t += occupa(z);
        primo = false;
      });
    }
  }

  const righe = zone.map((z) => {
    const eff = minutiEffettivi(z.seconds);
    const inCiclo = typeof z.in_ciclo === "boolean" ? z.in_ciclo : ordine.includes(z.id);
    const riga = {
      id: z.id,
      nome: String(z.name === undefined || z.name === null ? z.id : z.name),
      tipo: z.tipo === "drip" ? "drip" : "lawn",
      minuti: Number(z.minutes),
      secondi: secondi(z),
      classe: "ferma",
      scritta: eff,
      avanzamento: 0,
      bagnato: 0,
      puoFermare: false,
      // L'integrazione ignora l'avvio di una zona se qualcosa sta gia' irrigando
      puoAvviare: !inCorso && Boolean(z.manual_entity),
    };
    const fuori = () => {
      riga.classe = "fuori";
      riga.scritta = secondi(z) > 0 ? "Non in questo giro" : "Durata a zero";
    };
    if (inCorso) {
      if (attiva && z.id === attiva.id) {
        // Spegnere la zona in funzione ferma tutto, come l'arresto
        riga.puoFermare = Boolean(z.manual_entity);
        if (apertura) {
          riga.classe = "tentativo";
          riga.scritta = "Apertura…";
        } else {
          riga.classe = "attiva";
          riga.avanzamento = secondi(z) > 0 ? limita(1 - rimanenti / secondi(z), 0, 1) : 1;
          riga.scritta = `${manuale ? "A mano" : "In funzione"} · ${durata(rimanenti)}`;
          riga.bagnato = 0.05 + 0.15 * riga.avanzamento;
        }
      } else if (nonAperte.has(z.id)) {
        riga.classe = "errore";
        riga.scritta = "Non aperta";
      } else if (fatte.has(z.id)) {
        riga.classe = "fatta";
        riga.scritta = `Fatta · ${eff}`;
        riga.avanzamento = 1;
        riga.bagnato = 0.2;
      } else if (manuale) {
        // Una zona a mano non e' un giro: le altre restano come sono
      } else if (z.id === inAttesa) {
        riga.classe = "pausa";
        riga.scritta = "In attesa";
      } else if (inCiclo) {
        riga.classe = "coda";
        riga.scritta = partenze[z.id] !== undefined ? `Alle ${orario(partenze[z.id])} · ${eff}` : eff;
      } else {
        fuori();
      }
    } else if (!inCiclo) {
      fuori();
    } else if (saltato) {
      riga.classe = "saltata";
      riga.scritta = "Saltata";
    } else if (nonAperte.has(z.id)) {
      riga.classe = "errore";
      riga.scritta = "Non aperta";
    } else if (partenze[z.id] !== undefined) {
      riga.scritta = `${quando(partenze[z.id], adesso, "zona")} · ${eff}`;
    }
    if (stato === "rain_skipped") riga.bagnato = 0.16;
    return riga;
  });

  const quale = attiva ? attiva.id : inAttesa;
  const posizione = inCorso && !manuale && quale && ordine.includes(quale)
    ? { k: ordine.indexOf(quale) + 1, n: ordine.length }
    : null;

  return {
    inCorso,
    manuale,
    pausa,
    apertura,
    acquaInMoto: Boolean(attiva) && !apertura,
    attiva,
    rimanenti,
    restoPausa,
    inAttesa,
    fineCiclo,
    posizione,
    zone: righe,
  };
}

/** Il riquadro in alto: prossimo ciclo da fermo, fine prevista durante un giro. */
export function riquadroCiclo(attr, quadro, abilitata = true, adesso = Date.now()) {
  if (quadro.inCorso) {
    return {
      etichetta: quadro.manuale ? "FINE ZONA" : "FINE PREVISTA",
      valore: quadro.fineCiclo !== null ? orario(quadro.fineCiclo) : "—",
    };
  }
  const prossimo = tempo(attr.next_cycle);
  if (prossimo !== null) return { etichetta: "PROSSIMO CICLO", valore: quando(prossimo, adesso, "breve") };
  return { etichetta: "PROSSIMO CICLO", valore: abilitata === false ? "sospeso" : "nessuno" };
}

/** Le tessere sotto il disegno: cosa sta succedendo, cosa succedera', cosa non va. */
export function tessereImpianto(attr, stato, quadro, { abilitata = true, riservaMm = null, adesso = Date.now(), lingua = "it" } = {}) {
  const lista = [];
  const zone = Array.isArray(attr.zones) ? attr.zones : [];
  const nome = (id) => {
    const z = zone.find((x) => x.id === id);
    return z ? String(z.name) : String(id);
  };
  const aggiungi = (testo, classe = "") => lista.push({ testo, classe });

  if (abilitata === false) aggiungi("Programma sospeso: nessun ciclo automatico", "caldo");
  if (quadro.inCorso) {
    const a = quadro.attiva;
    const nomeAttiva = a ? nome(a.id) : "";
    if (a && quadro.apertura) aggiungi(`${nomeAttiva}: apertura della valvola`);
    else if (a && quadro.manuale) aggiungi(`A mano · ${nomeAttiva} · ${durata(quadro.rimanenti)}`, "freddo");
    else if (a) aggiungi(`In irrigazione · ${nomeAttiva} · ${durata(quadro.rimanenti)}`, "freddo");
    // Senza una zona che aspetta non e' una pausa: e' l'istante fra l'ultima zona e la fine del giro
    else if (quadro.pausa && quadro.inAttesa) {
      aggiungi(quadro.restoPausa > 0 ? `Pausa fra le zone · ${Math.ceil(quadro.restoPausa)} s` : "Pausa fra le zone");
    }
    if (quadro.posizione) aggiungi(`Zona ${quadro.posizione.k} di ${quadro.posizione.n}`);
    if (attr.master_valve && attr.master_open) aggiungi("Master aperta");
  } else {
    const motivo = attr.skip_reason ? String(attr.skip_reason) : "";
    const ultimo = tempo(attr.last_cycle);
    if (stato === "rain_skipped") aggiungi(motivo ? `Saltato per pioggia: ${motivo}` : "Saltato per pioggia", "freddo");
    else if (stato === "reserve_skipped") aggiungi(motivo ? `Saltato per la riserva: ${motivo}` : "Saltato: la riserva del terreno basta", "buono");
    else if (ultimo !== null) aggiungi(`Ultimo ciclo ${quando(ultimo, adesso, "lungo")}`);
    const prossimo = tempo(attr.next_cycle);
    if (prossimo !== null) {
      aggiungi(`Prossimo ciclo ${quando(prossimo, adesso, "lungo")}`);
      const r = attr.riserva;
      const soglia = r ? Number(r.soglia) : NaN;
      const prevista = attr.pioggia ? Number(attr.pioggia.prevista_mm) || 0 : 0;
      // Solo quello che si puo' dire con certezza: la riserva cala fino al ciclo
      if (stato === "idle" && riservaMm !== null && Number.isFinite(soglia) && riservaMm + prevista < soglia) {
        aggiungi(`Riserva ${numeroTesto(riservaMm, 1, lingua, 1)} mm sotto la soglia di ${numeroTesto(soglia, 1, lingua)}: al prossimo ciclo si irriga`, "caldo");
      }
    } else if (abilitata !== false) {
      aggiungi("Nessun ciclo in programma", "caldo");
    }
  }
  (Array.isArray(attr.ciclo_non_aperte) ? attr.ciclo_non_aperte : []).forEach((id) => {
    aggiungi(`${nome(id)} non si è aperta: zona saltata`, "avviso allarme");
  });
  return lista;
}

/** Il sensore «Stato» di questa integrazione, se in Home Assistant ce n'e' uno. */
export function trovaStato(hass) {
  const stati = (hass && hass.states) || {};
  const ids = Object.keys(stati);
  const conRuolo = ids.find((id) => stati[id].attributes && stati[id].attributes.ruolo === RUOLO_MAPPA);
  if (conRuolo) return conRuolo;
  return ids.find((id) => id.startsWith("sensor.") && stati[id].attributes && Array.isArray(stati[id].attributes.zones)) || "";
}

// -----------------------------------------------------------------------------
// Stile: colori del tema, animazioni, e il rispetto di chi non vuole movimento
// -----------------------------------------------------------------------------
const STILE = `
:host {
  display: block;
  /* I comandi prendono i colori dal tema di Home Assistant */
  --acqua: var(--primary-color, #2F7FC1);
  --su-acqua: var(--text-primary-color, #FFFFFF);
  --filo: var(--divider-color, #D9E0E7);
  --inchiostro: var(--primary-text-color, #1F2933);
  --tenue: var(--secondary-text-color, #56616F);
  --superficie: var(--card-background-color, #FFFFFF);
}
ha-card { overflow: hidden; }
.testata {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 14px 18px 2px;
}
.titolo {
  min-width: 0;
  font-size: var(--ha-card-header-font-size, 22px);
  font-weight: 500;
  line-height: 1.2;
  color: var(--ha-card-header-color, var(--inchiostro));
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.interruttore { display: inline-flex; align-items: center; gap: 8px; font-size: 14px; color: var(--tenue); cursor: pointer; flex: none; }
.interruttore input {
  appearance: none;
  -webkit-appearance: none;
  margin: 0;
  width: 38px; height: 22px;
  border-radius: 999px;
  background: var(--filo);
  position: relative;
  cursor: pointer;
  transition: background 0.2s ease;
}
.interruttore input::before {
  content: "";
  position: absolute;
  top: 3px; left: 3px;
  width: 16px; height: 16px;
  border-radius: 50%;
  background: #FFFFFF;
  box-shadow: 0 1px 2px rgba(0,0,0,0.25);
  transition: transform 0.2s ease;
}
.interruttore input:checked { background: var(--acqua); }
.interruttore input:checked::before { transform: translateX(16px); }
.interruttore input:disabled { opacity: 0.45; cursor: default; }
button:focus-visible, input:focus-visible { outline: 2px solid var(--acqua); outline-offset: 2px; }

/* Il disegno: gli stessi colori delle altre schede Nexus */
.scena {
  padding: 8px 8px 12px;
  --blu-testo: #2F6FA8;
  --verde-testo: #2E8A5F;
  --ambra-testo: #A96A14;
  --rosso-testo: #C93C43;
  --ns-fondo: #F4F8FC;
  --ns-riquadro: #FFFFFF;
  --ns-bordo: #E1E6EC;
  --ns-testo: #1F2933;
  --ns-etichetta: #56616F;
  --ns-metallo-chiaro: #FFFFFF;
  --ns-metallo: #E9EDF2;
  --ns-metallo-scuro: #DCE2E9;
  --ns-bordo-metallo: #C5CED8;
  --ns-tubo: #A3B3C2;
  --ns-quadrante: #F7FAFD;
  --ns-nuvola: #CBD5DF;
  --ns-prato-a: #A3D08C;
  --ns-prato-b: #6FAE5E;
  --ns-erba: #4F8F43;
  --ns-terra-a: #BF946A;
  --ns-terra-b: #8E6440;
  --ns-radici: #F3E3CF;
  --ns-tubo-goccia: #4A4F55;
}
.scena.scuro {
  --blu-testo: #8CC4F2;
  --verde-testo: #6FD3A2;
  --ambra-testo: #F2B866;
  --rosso-testo: #FF8A8F;
  --ns-fondo: #151B22;
  --ns-riquadro: #1E262F;
  --ns-bordo: #2E3945;
  --ns-testo: #E8ECF1;
  --ns-etichetta: #9AA5B1;
  --ns-metallo-chiaro: #2B343E;
  --ns-metallo: #232B34;
  --ns-metallo-scuro: #1B222A;
  --ns-bordo-metallo: #3A4653;
  --ns-tubo: #52667A;
  --ns-quadrante: #1B222A;
  --ns-nuvola: #4A5663;
  --ns-prato-a: #4F8545;
  --ns-prato-b: #3A6A33;
  --ns-erba: #6FA862;
  --ns-terra-a: #7A5A3E;
  --ns-terra-b: #56402C;
  --ns-radici: #A88A6A;
  --ns-tubo-goccia: #1C2126;
}
.disegno svg { display: block; width: 100%; height: auto; }
.avviso-mappa { padding: 18px 20px; color: var(--tenue); line-height: 1.5; }

/* Pannello della zona toccata */
.pannello {
  margin: 10px 4px 0;
  padding: 12px 14px 14px;
  border: 1px solid var(--filo);
  border-radius: 12px;
  background: var(--ns-fondo);
  color: var(--inchiostro);
  display: grid;
  gap: 8px;
}
.pannello[hidden] { display: none; }
.pannello-testa { display: flex; align-items: center; gap: 10px; min-width: 0; }
.pannello-testa strong { font-size: 16px; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tipo {
  flex: none;
  font-size: 12px; font-weight: 500;
  padding: 2px 9px; border-radius: 999px;
  border: 1px solid var(--filo); color: var(--tenue);
}
.chiudi {
  flex: none;
  margin-left: auto;
  width: 30px; height: 30px;
  border-radius: 50%;
  border: 1px solid var(--filo);
  background: var(--superficie); color: var(--inchiostro);
  font-family: inherit; font-size: 18px; font-weight: 400; line-height: 1;
  cursor: pointer;
}
.pannello-riga { display: flex; justify-content: space-between; align-items: baseline; gap: 10px; font-size: 14px; color: var(--tenue); }
.pannello-riga output { font-weight: 500; font-size: 15px; color: var(--inchiostro); font-variant-numeric: tabular-nums; }
.pannello input[type="range"] { width: 100%; accent-color: var(--acqua); margin: 0; }
.pannello-nota { margin: 0; font-size: 13px; color: var(--tenue); }
.pannello .bottone { justify-self: start; }

.tessere { display: flex; flex-wrap: wrap; gap: 8px; padding: 10px 10px 2px; }
.tessere:empty { display: none; }
.tessera {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 5px 12px; border-radius: 14px;
  font-size: 13px; font-weight: 600; line-height: 1.3;
  background: rgba(86,97,111,0.10);
  color: var(--tenue);
  border: 1px solid rgba(86,97,111,0.22);
  font-variant-numeric: tabular-nums;
}
.tessera.freddo { background: rgba(60,132,198,0.12); color: var(--blu-testo); border-color: rgba(60,132,198,0.35); }
.tessera.buono { background: rgba(46,158,107,0.12); color: var(--verde-testo); border-color: rgba(46,158,107,0.35); }
.tessera.caldo { background: rgba(227,155,50,0.14); color: var(--ambra-testo); border-color: rgba(227,155,50,0.38); }
.tessera.avviso { background: rgba(222,74,81,0.12); color: var(--rosso-testo); border-color: rgba(222,74,81,0.35); }
.tessera.allarme { animation: ni-pulsa 1.8s ease-in-out infinite; }

/* Comandi dentro la scheda */
.comandi-scheda {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: center;
  gap: 12px 16px;
  margin: 12px 4px 0;
  padding: 12px 6px 0;
  border-top: 1px solid var(--filo);
}
.programma { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 10px; }
.giorni { display: flex; flex-wrap: wrap; gap: 4px; }
.giorni.fuori-uso { opacity: 0.5; }
.giorno {
  min-width: 42px;
  border: 1px solid var(--filo);
  border-radius: 999px;
  padding: 5px 9px;
  font-family: inherit; font-size: 13px; font-weight: 500; line-height: 1.2;
  background: transparent;
  color: var(--tenue);
  cursor: pointer;
}
.giorno[aria-pressed="true"] { background: var(--acqua); border-color: var(--acqua); color: var(--su-acqua); }
.giorno:disabled { opacity: 0.45; cursor: default; }
.ora-avvio { display: inline-flex; align-items: center; gap: 6px; font-size: 13px; color: var(--tenue); }
.ora-avvio input {
  border: 1px solid var(--filo);
  border-radius: 999px;
  padding: 4px 10px;
  font-family: inherit; font-size: 13px; font-weight: 500;
  font-variant-numeric: tabular-nums;
  background: var(--superficie);
  color: var(--inchiostro);
  color-scheme: light;
}
.scena.scuro .ora-avvio input { color-scheme: dark; }
.azioni { display: flex; flex-wrap: wrap; gap: 8px; }
.bottone {
  display: inline-flex; align-items: center; gap: 7px;
  border-radius: 999px;
  padding: 8px 15px;
  font-family: inherit; font-size: 14px; font-weight: 500; line-height: 1.2;
  border: 1px solid var(--filo);
  background: transparent;
  color: var(--inchiostro);
  cursor: pointer;
}
.bottone svg { width: 14px; height: 14px; fill: currentColor; }
.bottone.primario { background: var(--acqua); border-color: var(--acqua); color: var(--su-acqua); }
.bottone.conferma { background: #E39B32; border-color: #E39B32; color: #1F2933; }
.bottone:disabled { opacity: 0.45; cursor: default; }

/* Scena: animazioni, come nelle altre schede Nexus */
.flusso { stroke-dasharray: 16 22; stroke-linecap: round; opacity: 0; }
.flusso.in-moto { opacity: 1; animation: ni-scorri 1s linear infinite; }
@keyframes ni-scorri { to { stroke-dashoffset: -38; } }
.acqua { opacity: 0; transition: opacity 0.5s ease; }
.acqua.piena { opacity: 1; }
.ventola { transform-box: fill-box; transform-origin: center; }
.ventola.in-moto { animation: ni-gira 1.1s linear infinite; }
@keyframes ni-gira { to { transform: rotate(360deg); } }
.rotore { transform-box: fill-box; transform-origin: center; }
.rotore.in-moto { animation: ni-oscilla 2.6s ease-in-out infinite alternate; }
@keyframes ni-oscilla { from { transform: rotate(-50deg); } to { transform: rotate(50deg); } }
.arco, .getto-centrale { opacity: 0; }
.getto.in-moto .getto-centrale { opacity: 0.85; }
.getto.in-moto path.getto-centrale[fill] { opacity: 0.32; }
.getto.in-moto .arco { animation: ni-spruzzo 1.1s linear infinite; }
.getto.in-moto .a2 { animation-delay: 0.37s; }
.getto.in-moto .a3 { animation-delay: 0.73s; }
@keyframes ni-spruzzo { 0% { opacity: 0; } 25% { opacity: 0.95; } 100% { opacity: 0; } }
.stilla { opacity: 0; }
.gocciolatoio.in-moto .stilla { animation: ni-stilla 1.6s ease-in infinite; }
@keyframes ni-stilla { 0% { opacity: 0; transform: translateY(-3px); } 40% { opacity: 1; } 100% { opacity: 0; transform: translateY(7px); } }
.pioggia line { opacity: 0; }
.pioggia.in-moto line { animation: ni-cade 0.9s linear infinite; }
@keyframes ni-cade { 0% { opacity: 0; transform: translate(0, -6px); } 30% { opacity: 1; } 100% { opacity: 0; transform: translate(-5px, 18px); } }
.bagnato { transition: opacity 0.8s ease; }
.zona { cursor: pointer; outline: none; }
.zona-sfondo { transition: stroke 0.3s ease; }
.zona:hover .zona-sfondo, .zona:focus-visible .zona-sfondo { stroke: var(--acqua); }
.zona.scelta .zona-sfondo { stroke: var(--acqua); stroke-width: 3; stroke-dasharray: 8 6; }
.zona.attiva .zona-sfondo { stroke: ${BLU}; stroke-width: 3; stroke-dasharray: none; }
.zona.errore .zona-sfondo { stroke: #DE4A51; stroke-width: 3; stroke-dasharray: none; animation: ni-pulsa 1.8s ease-in-out infinite; }
.stato-zona { fill: var(--ns-etichetta); }
.zona.attiva .stato-zona, .zona.pausa .stato-zona, .zona.tentativo .stato-zona { fill: var(--blu-testo); }
.zona.fatta .stato-zona { fill: var(--verde-testo); }
.zona.errore .stato-zona { fill: var(--rosso-testo); }
.comando-zona { cursor: pointer; outline: none; }
.comando-zona circle { transition: stroke 0.15s ease; }
.comando-zona:hover circle, .comando-zona:focus-visible circle { stroke: var(--acqua); stroke-width: 3; }
.comando-zona.spento { opacity: 0.35; cursor: default; }
.spia.acceso { animation: ni-pulsa 2.2s ease-in-out infinite; }
@keyframes ni-pulsa { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }

@media (prefers-reduced-motion: reduce) {
  .flusso.in-moto, .ventola.in-moto, .rotore.in-moto, .getto.in-moto .arco,
  .gocciolatoio.in-moto .stilla, .pioggia.in-moto line, .spia.acceso,
  .zona.errore .zona-sfondo, .tessera.allarme { animation: none; }
  .getto.in-moto .arco, .gocciolatoio.in-moto .stilla, .pioggia.in-moto line { opacity: 0.85; }
}
.senza-moto .flusso.in-moto, .senza-moto .ventola.in-moto, .senza-moto .rotore.in-moto,
.senza-moto .getto.in-moto .arco, .senza-moto .gocciolatoio.in-moto .stilla,
.senza-moto .pioggia.in-moto line, .senza-moto .spia.acceso,
.senza-moto .zona.errore .zona-sfondo, .senza-moto .tessera.allarme { animation: none; }
.senza-moto .getto.in-moto .arco, .senza-moto .gocciolatoio.in-moto .stilla,
.senza-moto .pioggia.in-moto line { opacity: 0.85; }
`;

// -----------------------------------------------------------------------------
// Disegno
// -----------------------------------------------------------------------------
function riquadro({ slot, x, y, w, etichetta, colore, coloreEtichetta, piccolo }) {
  const h = 96;
  const dimE = piccolo ? 19 : 22;
  const dimV = piccolo ? 27 : 32;
  return `
    <g class="riquadro" data-slot="${slot}">
      <rect class="sfondo" x="${x}" y="${y}" width="${w}" height="${h}" rx="16"
            fill="var(--ns-riquadro)" stroke="var(--ns-bordo)" stroke-width="2" filter="url(#ni-ombra)"/>
      <rect x="${x}" y="${y + 16}" width="6" height="${h - 32}" rx="3" fill="${colore}"/>
      <text data-etichetta="${slot}" x="${x + 22}" y="${y + (piccolo ? 32 : 36)}" font-size="${dimE}" font-weight="700"
            letter-spacing="1.2" fill="${coloreEtichetta}">${etichetta}</text>
      <text data-valore="${slot}" x="${x + 22}" y="${y + (piccolo ? 70 : 76)}" font-size="${dimV}" font-weight="700"
            fill="var(--ns-testo)">—</text>
    </g>`;
}

function etichetta(x, y, testo) {
  return `<text x="${x}" y="${y}" text-anchor="middle" font-size="23" font-weight="700" letter-spacing="1.5" fill="var(--ns-etichetta)">${testo}</text>`;
}

function contatore(cx, cy) {
  return `
    ${etichetta(cx, 56, "ACQUA")}
    <circle cx="${cx}" cy="${cy}" r="38" fill="url(#ni-lamiera)" stroke="var(--ns-bordo-metallo)" stroke-width="3"/>
    <circle cx="${cx}" cy="${cy}" r="27" fill="var(--ns-quadrante)" stroke="var(--ns-bordo-metallo)" stroke-width="2"/>
    <g stroke="var(--ns-bordo-metallo)" stroke-width="2" stroke-linecap="round">
      <line x1="${cx}" y1="${cy - 24}" x2="${cx}" y2="${cy - 19}"/>
      <line x1="${cx + 24}" y1="${cy}" x2="${cx + 19}" y2="${cy}"/>
      <line x1="${cx}" y1="${cy + 24}" x2="${cx}" y2="${cy + 19}"/>
      <line x1="${cx - 24}" y1="${cy}" x2="${cx - 19}" y2="${cy}"/>
    </g>
    <g class="ventola" data-ventola="contatore">
      <circle cx="${cx}" cy="${cy}" r="27" fill="none" stroke="none"/>
      <path d="M${cx} ${cy} L${cx} ${cy - 20}" stroke="${BLU}" stroke-width="4" stroke-linecap="round"/>
    </g>
    <circle cx="${cx}" cy="${cy}" r="4.5" fill="${BLU}"/>`;
}

function pompa(cx, cy, piccolo = false) {
  // Sulla scheda stretta la scritta si stringe: accanto c'e' il testo della pioggia
  const dim = piccolo ? 16 : 20;
  const spaziatura = piccolo ? 1 : 1.4;
  const pale = [0, 120, 240].map((a) => {
    const r = (a * Math.PI) / 180;
    const x = Math.round(Math.sin(r) * 17 * 10) / 10;
    const y = Math.round(-Math.cos(r) * 17 * 10) / 10;
    return `<path d="M${cx} ${cy} Q${cx + x * 0.2 + y * 0.45} ${cy + y * 0.2 - x * 0.45} ${cx + x} ${cy + y}" stroke="var(--ns-etichetta)" stroke-width="5" stroke-linecap="round" fill="none"/>`;
  }).join("");
  return `
    <g data-blocco="master">
      <circle cx="${cx}" cy="${cy}" r="31" fill="url(#ni-lamiera)" stroke="var(--ns-bordo-metallo)" stroke-width="3"/>
      <g class="ventola" data-ventola="master">
        <circle cx="${cx}" cy="${cy}" r="22" fill="none" stroke="none"/>
        ${pale}
      </g>
      <circle cx="${cx}" cy="${cy}" r="5" fill="var(--ns-bordo-metallo)"/>
      <circle class="spia" data-spia="master" cx="${cx + 23}" cy="${cy - 23}" r="5" fill="var(--ns-bordo-metallo)"/>
      <text x="${cx + 40}" y="${cy + 6}" font-size="${dim}" font-weight="700" letter-spacing="${spaziatura}" fill="var(--ns-etichetta)">MASTER</text>
    </g>`;
}

function meteo(cx, cy) {
  const gocce = [0, 1, 2, 3, 4, 5].map((k) => {
    const x = cx - 42 + k * 17;
    return `<line x1="${x}" y1="${cy + 40}" x2="${x - 5}" y2="${cy + 56}" style="animation-delay:${(k * 0.15).toFixed(2)}s"/>`;
  }).join("");
  return `
    <g data-blocco="pioggia">
      ${etichetta(cx, 56, "PIOGGIA")}
      <circle data-sole="disco" cx="${cx + 38}" cy="${cy - 24}" r="17" fill="#F6C453"/>
      <g fill="var(--ns-nuvola)">
        <circle cx="${cx - 34}" cy="${cy + 6}" r="22"/>
        <circle cx="${cx - 4}" cy="${cy - 10}" r="30"/>
        <circle cx="${cx + 30}" cy="${cy + 4}" r="24"/>
        <rect x="${cx - 56}" y="${cy + 6}" width="110" height="22" rx="11"/>
      </g>
      <g class="pioggia" data-pioggia="gocce" stroke="${BLU}" stroke-width="4" stroke-linecap="round">${gocce}</g>
      <text data-valore="pioggia" x="${cx}" y="${cy + 104}" text-anchor="middle" font-size="22" font-weight="700" fill="var(--ns-testo)">—</text>
    </g>`;
}

function misuraRiserva(gx, gy) {
  const suoloAlto = gy + 18;
  const suoloBasso = gy + 160;
  return `
    <g data-blocco="riserva">
      ${etichetta(gx + 60, 56, "RISERVA")}
      <rect x="${gx}" y="${gy + 12}" width="120" height="148" rx="10" fill="url(#ni-terra)" stroke="var(--ns-bordo-metallo)" stroke-width="2"/>
      <rect data-livello="riserva" data-basso="${suoloBasso}" x="${gx + 6}" y="${suoloBasso}" width="108" height="0" rx="6" fill="#4A9BE0" opacity="0.8"/>
      <path d="M${gx + 30} ${gy + 16} q -7 30 4 60 M${gx + 60} ${gy + 16} q 9 40 -2 80 M${gx + 90} ${gy + 16} q 6 26 -6 52"
            stroke="var(--ns-radici)" stroke-width="2.5" fill="none" stroke-linecap="round" opacity="0.6"/>
      <rect x="${gx}" y="${gy}" width="120" height="18" rx="8" fill="var(--ns-prato-b)"/>
      <path d="M${gx + 12} ${gy + 2} l3 -9 M${gx + 30} ${gy + 2} l-2 -10 M${gx + 50} ${gy + 2} l3 -8 M${gx + 72} ${gy + 2} l-2 -10 M${gx + 92} ${gy + 2} l3 -9 M${gx + 108} ${gy + 2} l-2 -7"
            stroke="var(--ns-prato-b)" stroke-width="3" stroke-linecap="round"/>
      <g data-soglia="riserva" data-alto="${suoloAlto}" data-basso="${suoloBasso}">
        <line x1="${gx - 6}" y1="${suoloBasso}" x2="${gx + 126}" y2="${suoloBasso}" stroke="#E39B32" stroke-width="3" stroke-dasharray="7 5"/>
        <text x="${gx + 132}" y="${suoloBasso + 6}" font-size="17" font-weight="500" fill="var(--ns-etichetta)">soglia</text>
      </g>
      <text data-valore="riserva" x="${gx + 60}" y="${gy + 196}" text-anchor="middle" font-size="26" font-weight="700" fill="var(--ns-testo)">—</text>
    </g>`;
}

function getto(hx, hy, id) {
  const archi = [22, 36, 50].map((r, k) => {
    const dx = Math.round(r * 0.5 * 10) / 10;
    const dy = Math.round(r * 0.866 * 10) / 10;
    return `<path class="arco a${k + 1}" d="M${-dx} ${-dy} A${r} ${r} 0 0 1 ${dx} ${-dy}" stroke="#FFFFFF" stroke-width="4" stroke-dasharray="3 7" stroke-linecap="round" fill="none"/>`;
  }).join("");
  return `
      <rect x="${hx - 6}" y="${hy - 2}" width="12" height="10" rx="3" fill="var(--ns-bordo-metallo)"/>
      <ellipse cx="${hx}" cy="${hy - 2}" rx="8" ry="3.5" fill="var(--ns-metallo-scuro)" stroke="var(--ns-bordo-metallo)" stroke-width="1.5"/>
      <g class="getto" data-getto="${id}" transform="translate(${hx} ${hy - 4})">
        <g class="rotore">
          <circle r="58" fill="none" stroke="none"/>
          <path class="getto-centrale" d="M0 0 L-27 -46.8 A54 54 0 0 1 27 -46.8 Z" fill="#E8F6FF" opacity="0.32"/>
          <path class="getto-centrale" d="M0 0 L0 -54" stroke="#FFFFFF" stroke-width="2.5" stroke-linecap="round"/>
          ${archi}
        </g>
      </g>`;
}

function aiuolaGoccia(t, id) {
  const { x, y, w, vx, letto } = t;
  const sinistra = x + 40;
  const destra = x + w - 40;
  const [r1, r2, r3] = [0.21, 0.48, 0.76].map((f) => Math.round(y + 16 + letto * f));
  const tubo = `M${vx} ${y + 22} V${r1} H${destra} V${r2} H${sinistra} V${r3} H${destra}`;
  const stille = [];
  const corse = [[vx, destra, r1], [sinistra, destra, r2], [sinistra, destra, r3]];
  let k = 0;
  corse.forEach(([a, b, yy]) => {
    for (let xx = Math.min(a, b) + 14; xx <= Math.max(a, b) - 8; xx += 34) {
      stille.push(`<circle class="stilla" cx="${xx.toFixed(1)}" cy="${yy + 8}" r="3.8" fill="#6DB6F0" style="animation-delay:${((k * 0.23) % 1.6).toFixed(2)}s"/>`);
      k += 1;
    }
  });
  const piante = [];
  for (let xx = sinistra + 24; xx <= destra - 20; xx += 58) {
    piante.push(`<circle cx="${xx}" cy="${(r1 + r2) / 2}" r="9" fill="var(--ns-prato-b)"/>`);
    piante.push(`<circle cx="${xx + 29}" cy="${(r2 + r3) / 2}" r="9" fill="var(--ns-prato-b)"/>`);
  }
  return `
      <rect x="${x + 14}" y="${y + 16}" width="${w - 28}" height="${letto}" rx="14" fill="url(#ni-terra)"/>
      ${piante.join("")}
      <path d="${tubo}" stroke="var(--ns-tubo-goccia)" stroke-width="5" fill="none" stroke-linejoin="round" stroke-linecap="round"/>
      <g class="gocciolatoio" data-getto="${id}">${stille.join("")}</g>`;
}

function aiuolaPrato(t, id) {
  const { x, y, w, letto } = t;
  const teste = w >= 380 ? 3 : 2;
  let disegno = `
      <rect x="${x + 14}" y="${y + 16}" width="${w - 28}" height="${letto}" rx="14" fill="url(#ni-prato)"/>
      <rect x="${x + 14}" y="${y + 16}" width="${w - 28}" height="${letto}" rx="14" fill="url(#ni-erba)" opacity="0.55"/>`;
  for (let j = 0; j < teste; j += 1) {
    const hx = Math.round((x + 14 + ((w - 28) * (j + 1)) / (teste + 1)) * 10) / 10;
    disegno += getto(hx, y + 16 + letto - 26, id);
  }
  return disegno;
}

const ICONA_AVVIA = (bx, by) => `M${bx - 6} ${by - 9} L${bx + 9} ${by} L${bx - 6} ${by + 9} Z`;
const ICONA_FERMA = (bx, by) => `M${bx - 7} ${by - 7} H${bx + 7} V${by + 7} H${bx - 7} Z`;

function zonaDisegno(t) {
  const { x, y, w, h, letto, zona } = t;
  const id = testoSicuro(zona.id);
  const nome = String(zona.name === undefined || zona.name === null ? zona.id : zona.name);
  const base = y + 16 + letto;
  const bx = Math.round(x + w - 40);
  const by = base + 29;
  return `
    <g class="zona ferma" data-zona="${id}" data-apri="${id}" role="button" tabindex="0" aria-label="Durata di ${testoSicuro(nome)}">
      <rect class="zona-sfondo" x="${x}" y="${y}" width="${w}" height="${h}" rx="18"
            fill="var(--ns-riquadro)" stroke="var(--ns-bordo)" stroke-width="2" filter="url(#ni-ombra)"/>
      ${zona.tipo === "drip" ? aiuolaGoccia(t, id) : aiuolaPrato(t, id)}
      <rect class="bagnato" data-bagnato="${id}" x="${x + 14}" y="${y + 16}" width="${w - 28}" height="${letto}" rx="14" fill="${BLU}" opacity="0"/>
      <text data-nome-zona="${id}" data-nome="${testoSicuro(nome)}" data-spazio="${Math.round(bx - 21 - 8 - (x + 18))}"
            x="${x + 18}" y="${base + 36}" font-size="24" font-weight="700" fill="var(--ns-testo)">${testoSicuro(tronca(nome, w - 36 - 56, 24))}</text>
      <text class="stato-zona" data-stato-zona="${id}" x="${x + 18}" y="${base + 68}" font-size="19" font-weight="600">—</text>
      <rect x="${x + 18}" y="${base + 80}" width="${w - 36}" height="7" rx="3.5" fill="var(--ns-bordo)"/>
      <rect data-avanzamento="${id}" data-larghezza="${w - 36}" x="${x + 18}" y="${base + 80}" width="0" height="7" rx="3.5" fill="${BLU}"/>
      <g class="comando-zona" data-avvia="${id}" role="button" tabindex="0" aria-label="Avvia ${testoSicuro(nome)}">
        <circle cx="${bx}" cy="${by}" r="21" fill="var(--ns-metallo)" stroke="var(--ns-bordo-metallo)" stroke-width="2"/>
        <path data-icona="${id}" d="${ICONA_AVVIA(bx, by)}" data-bx="${bx}" data-by="${by}" fill="var(--blu-testo)"/>
      </g>
    </g>`;
}

function valvola(t) {
  const { vx, y } = t;
  return `
    <g>
      <rect x="${vx - 17}" y="${y - 31}" width="34" height="22" rx="6" fill="url(#ni-lamiera)" stroke="var(--ns-bordo-metallo)" stroke-width="2.5"/>
      <rect x="${vx + 17}" y="${y - 28}" width="14" height="16" rx="3" fill="var(--ns-metallo-scuro)" stroke="var(--ns-bordo-metallo)" stroke-width="2"/>
      <circle class="spia" data-spia="${testoSicuro(t.zona.id)}" cx="${vx + 24}" cy="${y - 20}" r="3.6" fill="var(--ns-bordo-metallo)"/>
    </g>`;
}

/** Tutto il disegno, costruito dalla disposizione. */
function scena(d, { master }) {
  const a = d.alto;
  const [sx, sy] = a.contatore;
  const partenza = sy + 38;
  const ultima = d.file[d.file.length - 1].lineaY;
  const tutte = d.file.flatMap((f) => f.tessere.map((t) => ({ ...t, lineaY: f.lineaY })));

  const righe = d.file.map((f) => `M${sx} ${f.lineaY} H${f.tessere[f.tessere.length - 1].vx}`);
  const calate = tutte.map((t) => `M${t.vx} ${t.lineaY} V${t.y + 20}`);
  const tubi = [`M${sx} ${partenza} V${ultima}`, ...righe, ...calate].join(" ");
  const percorsi = tutte.map((t) => ({ id: testoSicuro(t.zona.id), d: `M${sx} ${partenza} V${t.lineaY} H${t.vx} V${t.y + 20}` }));
  const quante = tutte.length === 1 ? "1 zona" : `${tutte.length} zone`;

  return `
<svg viewBox="0 0 ${d.W} ${d.H}" preserveAspectRatio="xMidYMid meet" xmlns="http://www.w3.org/2000/svg"
     role="group" aria-label="Schema animato dell'impianto con ${quante}"
     font-family="var(--ha-font-family-body, Roboto, system-ui, sans-serif)">
  <defs>
    <linearGradient id="ni-lamiera" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" style="stop-color:var(--ns-metallo-chiaro)"/>
      <stop offset="1" style="stop-color:var(--ns-metallo)"/>
    </linearGradient>
    <linearGradient id="ni-prato" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" style="stop-color:var(--ns-prato-a)"/>
      <stop offset="1" style="stop-color:var(--ns-prato-b)"/>
    </linearGradient>
    <linearGradient id="ni-terra" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" style="stop-color:var(--ns-terra-a)"/>
      <stop offset="1" style="stop-color:var(--ns-terra-b)"/>
    </linearGradient>
    <pattern id="ni-erba" width="18" height="14" patternUnits="userSpaceOnUse">
      <path d="M3 12 l2 -6 M9 13 l-1 -7 M14 12 l2 -5" stroke="var(--ns-erba)" stroke-width="1.6" stroke-linecap="round" fill="none"/>
    </pattern>
    <filter id="ni-ombra" x="-20%" y="-20%" width="140%" height="160%">
      <feDropShadow dx="0" dy="3" stdDeviation="5" flood-color="#1F2933" flood-opacity="0.09"/>
    </filter>
  </defs>

  <rect width="${d.W}" height="${d.H}" rx="12" fill="var(--ns-fondo)"/>

  ${tutte.map(zonaDisegno).join("")}

  <g fill="none" stroke-linecap="round" stroke-linejoin="round" pointer-events="none">
    <path d="${tubi}" stroke="var(--ns-tubo)" stroke-width="14"/>
    <path d="${tubi}" stroke="var(--ns-metallo-chiaro)" stroke-width="3" opacity="0.5"/>
    ${percorsi.map((p) => `<path class="acqua" data-acqua="${p.id}" d="${p.d}" stroke="${BLU}" stroke-width="14"/>`).join("")}
    ${percorsi.map((p) => `<path class="flusso" data-flusso="${p.id}" d="${p.d}" stroke="#FFFFFF" stroke-width="6"/>`).join("")}
  </g>
  ${d.file.map((f) => `<circle cx="${sx}" cy="${f.lineaY}" r="10" fill="var(--ns-tubo)"/>`).join("")}
  ${tutte.map(valvola).join("")}

  ${contatore(sx, sy)}
  ${master ? pompa(sx, a.master[1], a.piccolo) : ""}
  ${a.meteo ? meteo(a.meteo[0], a.meteo[1]) : ""}
  ${a.misura ? misuraRiserva(a.misura[0], a.misura[1]) : ""}
  ${riquadro({ slot: "prossimo", ...a.riquadri[0], etichetta: "PROSSIMO CICLO", colore: BLU, coloreEtichetta: "var(--blu-testo)", piccolo: a.piccolo })}
  ${riquadro({ slot: "consumo", ...a.riquadri[1], etichetta: "CONSUMO PRATO", colore: "#6FAE5E", coloreEtichetta: "var(--verde-testo)", piccolo: a.piccolo })}
</svg>`;
}

// -----------------------------------------------------------------------------
// Aiuti sul disegno: si tocca il DOM solo se il valore cambia davvero
// -----------------------------------------------------------------------------
function perDato(radice, dato) {
  const mappa = {};
  radice.querySelectorAll(`[data-${dato}]`).forEach((n) => {
    const chiave = n.getAttribute(`data-${dato}`);
    (mappa[chiave] = mappa[chiave] || []).push(n);
  });
  return mappa;
}

function riferimenti(radice) {
  return {
    zone: perDato(radice, "zona"),
    stati: perDato(radice, "stato-zona"),
    barre: perDato(radice, "avanzamento"),
    bagnati: perDato(radice, "bagnato"),
    getti: perDato(radice, "getto"),
    acque: perDato(radice, "acqua"),
    flussi: perDato(radice, "flusso"),
    spie: perDato(radice, "spia"),
    ventole: perDato(radice, "ventola"),
    valori: perDato(radice, "valore"),
    etichette: perDato(radice, "etichetta"),
    livelli: perDato(radice, "livello"),
    soglie: perDato(radice, "soglia"),
    icone: perDato(radice, "icona"),
    comandi: perDato(radice, "avvia"),
    pioggia: radice.querySelector('[data-pioggia="gocce"]'),
    sole: radice.querySelector('[data-sole="disco"]'),
  };
}

function tutti(lista, funzione) {
  (lista || []).forEach(funzione);
}

function testo(nodo, valore) {
  if (nodo && nodo.textContent !== valore) nodo.textContent = valore;
}

function attributo(nodo, nome, valore) {
  if (nodo && nodo.getAttribute(nome) !== valore) nodo.setAttribute(nome, valore);
}

// -----------------------------------------------------------------------------
// La card
// -----------------------------------------------------------------------------
class NexusIrrigationCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._firma = null;
    this._struttura = false;
    this._rif = null;
    this._scelta = null; // id della zona col pannello aperto
    this._confermaDa = 0; // quando e' stata premuta la prima volta «Avvia ciclo»
    this._pausaDa = null; // quando la scheda ha visto cominciare la pausa fra le zone
    this._trascina = false; // il cursore della durata e' in mano all'utente
  }

  static getConfigElement() {
    return document.createElement(`${ELEMENTO}-editor`);
  }

  static getStubConfig(hass) {
    return { entity: trovaStato(hass) };
  }

  setConfig(config) {
    if (!config || !config.entity) {
      throw new Error(`Indica il sensore «Stato» di ${NOME_INTEGRAZIONE}`);
    }
    this._config = { ...config };
    this._firma = null;
    this._struttura = false;
    this._rif = null;
    this.shadowRoot.innerHTML = "";
    if (this._hass) this._aggiorna();
  }

  set hass(hass) {
    this._hass = hass;
    this._aggiorna();
  }

  getCardSize() {
    const attr = this._attributi();
    const n = attr && Array.isArray(attr.zones) ? attr.zones.length : 2;
    return 6 + 3 * Math.ceil(Math.max(1, n) / 3);
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6, rows: "auto" };
  }

  connectedCallback() {
    // Il conto alla rovescia non aspetta Home Assistant: batte da solo
    if (!this._orologio) this._orologio = setInterval(() => this._batti(), 1000);
    if (this._osservatore && this._scena) this._osservatore.observe(this._scena);
    this._aggiorna();
  }

  disconnectedCallback() {
    if (this._orologio) {
      clearInterval(this._orologio);
      this._orologio = null;
    }
    if (this._timerConferma) {
      clearTimeout(this._timerConferma);
      this._timerConferma = null;
    }
    if (this._osservatore) this._osservatore.disconnect();
  }

  _statoSensore() {
    return this._hass && this._config ? this._hass.states[this._config.entity] : null;
  }

  _attributi() {
    const stato = this._statoSensore();
    return stato && stato.attributes ? stato.attributes : null;
  }

  _titolo(attr) {
    if (this._config.title !== undefined && this._config.title !== null) return String(this._config.title);
    return attr.installation ? String(attr.installation) : "";
  }

  _chiama(dominio, servizio, dati) {
    if (!this._hass || !dati.entity_id) return;
    try {
      Promise.resolve(this._hass.callService(dominio, servizio, dati)).catch((errore) => {
        console.error(`${NOME_INTEGRAZIONE}: ${dominio}.${servizio} non riuscito`, errore);
      });
    } catch (errore) {
      console.error(`${NOME_INTEGRAZIONE}: ${dominio}.${servizio} non riuscito`, errore);
    }
  }

  _lingua() {
    return (this._hass && this._hass.locale && this._hass.locale.language) || "it";
  }

  _avviso(testoAvviso) {
    const firma = `avviso|${testoAvviso}`;
    if (this._firma === firma) return;
    if (this._osservatore) this._osservatore.disconnect();
    this._firma = firma;
    this._struttura = false;
    this._rif = null;
    this._scena = null;
    this.shadowRoot.innerHTML = `<style>${STILE}</style><ha-card><div class="avviso-mappa">${testoSicuro(testoAvviso)}</div></ha-card>`;
  }

  /** Testata, contenitore del disegno, pannello, tessere e comandi: si fanno una volta sola. */
  _costruisciStruttura() {
    const radice = this.shadowRoot;
    radice.innerHTML = `<style>${STILE}</style>
      <ha-card>
        <div class="testata">
          <div class="titolo"></div>
          <label class="interruttore">Abilitata <input type="checkbox" role="switch" data-comando="abilita"></label>
        </div>
        <div class="scena">
          <div class="disegno"></div>
          <div class="pannello" hidden>
            <div class="pannello-testa">
              <strong data-pannello="nome"></strong>
              <span class="tipo" data-pannello="tipo"></span>
              <button type="button" class="chiudi" data-comando="chiudi" aria-label="Chiudi">×</button>
            </div>
            <div class="pannello-riga"><span>Durata base</span><output data-pannello="minuti"></output></div>
            <input type="range" min="0" max="${DURATA_MASSIMA_CURSORE}" step="1" value="0" data-comando="durata" aria-label="Durata base in minuti">
            <p class="pannello-nota" data-pannello="nota"></p>
            <button type="button" class="bottone" data-comando="zona-pannello"></button>
          </div>
          <div class="tessere"></div>
          <div class="comandi-scheda">
            <div class="programma">
              <div class="giorni" role="group" aria-label="Giorni del programma">
                ${GIORNI.map((g, i) => `<button type="button" class="giorno" data-giorno="${i}" aria-pressed="false">${g}</button>`).join("")}
              </div>
              <label class="ora-avvio">alle <input type="time" step="60" data-comando="ora"></label>
            </div>
            <div class="azioni">
              <button type="button" class="bottone primario" data-comando="avvia-ciclo" title="Parte subito, anche se piove o la riserva basta">
                <svg viewBox="0 0 14 14" aria-hidden="true"><path d="M3 1.5 L12 7 L3 12.5 Z"/></svg><span>Avvia ciclo</span>
              </button>
              <button type="button" class="bottone" data-comando="arresta">
                <svg viewBox="0 0 14 14" aria-hidden="true"><rect x="2" y="2" width="10" height="10" rx="1.5"/></svg><span>Arresta</span>
              </button>
            </div>
          </div>
        </div>
      </ha-card>`;
    const q = (sel) => radice.querySelector(sel);
    this._el = {
      titolo: q(".titolo"),
      abilita: q('[data-comando="abilita"]'),
      pannello: q(".pannello"),
      pannelloNome: q('[data-pannello="nome"]'),
      pannelloTipo: q('[data-pannello="tipo"]'),
      pannelloMinuti: q('[data-pannello="minuti"]'),
      pannelloNota: q('[data-pannello="nota"]'),
      durata: q('[data-comando="durata"]'),
      pannelloZona: q('[data-comando="zona-pannello"]'),
      tessere: q(".tessere"),
      giorni: q(".giorni"),
      bottoniGiorno: Array.from(radice.querySelectorAll("[data-giorno]")),
      ora: q('[data-comando="ora"]'),
      avvia: q('[data-comando="avvia-ciclo"]'),
      arresta: q('[data-comando="arresta"]'),
    };
    this._scena = q(".scena");
    this._disegno = q(".disegno");
    this._firma = null;
    this._firmaTessere = null;
    this._struttura = true;

    // Un solo ascoltatore sul disegno: sopravvive ai ridisegni
    this._disegno.addEventListener("click", (evento) => this._suDisegno(evento));
    this._disegno.addEventListener("keydown", (evento) => {
      if (evento.key === "Enter" || evento.key === " ") {
        evento.preventDefault();
        this._suDisegno(evento);
      }
    });
    this._el.abilita.addEventListener("change", () => {
      const attr = this._attributi();
      if (attr) this._chiama("switch", this._el.abilita.checked ? "turn_on" : "turn_off", { entity_id: attr.enable_entity });
    });
    q('[data-comando="chiudi"]').addEventListener("click", () => {
      this._scelta = null;
      this._aggiorna();
    });
    // Il cursore scrive mentre si trascina, ma chiama Home Assistant solo al rilascio
    this._el.durata.addEventListener("input", () => {
      this._trascina = true;
      const attr = this._attributi();
      this._scriviDurata(Number(this._el.durata.value), attr ? attr.seasonal : null);
    });
    this._el.durata.addEventListener("change", () => {
      this._trascina = false;
      const zona = this._zonaScelta();
      if (!zona) return;
      const valore = Number(this._el.durata.value);
      // Fino alla risposta di Home Assistant il cursore resta dove l'ha lasciato
      // l'utente, invece di tornare per un attimo al valore vecchio.
      this._durataInviata = { id: zona.id, valore, fino: Date.now() + 5000 };
      this._chiama("number", "set_value", { entity_id: zona.duration_entity, value: valore });
    });
    this._el.pannelloZona.addEventListener("click", () => {
      if (this._scelta !== null) this._comandoZona(this._scelta);
    });
    this._el.giorni.addEventListener("click", (evento) => {
      const bottone = evento.target.closest("[data-giorno]");
      const attr = this._attributi();
      if (!bottone || bottone.disabled || !attr || !Array.isArray(attr.day_entities)) return;
      const entita = attr.day_entities[Number(bottone.dataset.giorno)];
      const stato = entita ? this._hass.states[entita] : null;
      this._chiama("switch", stato && stato.state === "on" ? "turn_off" : "turn_on", { entity_id: entita });
    });
    // L'ora si manda solo a modifica finita (uscita dal campo o Invio): scrivendo
    // «0630» il campo cambia a ogni cifra, e ogni valore intermedio riprogrammerebbe
    // il ciclo automatico.
    const mandaOra = () => {
      const attr = this._attributi();
      const valore = String(this._el.ora.value || "").slice(0, 5);
      if (!attr || !/^\d{2}:\d{2}$/.test(valore)) return;
      const attuale = attr.start_time_entity ? this._hass.states[attr.start_time_entity] : null;
      if (attuale && String(attuale.state).slice(0, 5) === valore) return;
      this._chiama("time", "set_value", { entity_id: attr.start_time_entity, time: `${valore}:00` });
    };
    this._el.ora.addEventListener("blur", mandaOra);
    this._el.ora.addEventListener("keydown", (evento) => {
      if (evento.key === "Enter") this._el.ora.blur();
    });
    this._el.avvia.addEventListener("click", () => this._premiAvvia());
    this._el.arresta.addEventListener("click", () => {
      const attr = this._attributi();
      const stato = this._statoSensore();
      if (attr && stato && stato.state === "running") this._chiama("button", "press", { entity_id: attr.stop_button });
    });

    if (this._osservatore) this._osservatore.disconnect();
    if (typeof ResizeObserver !== "undefined") {
      // Il disegno si rifa' solo se si passa il confine fra scheda larga e stretta
      this._osservatore = new ResizeObserver(() => {
        const attr = this._attributi();
        if (attr && this._struttura && firmaScena(attr, this._compatta()) !== this._firma) this._aggiorna();
        // La prima volta a video e' anche il primo momento in cui i nomi si possono misurare
        else if (this._struttura && !this._nomiMisurati) this._misuraNomi();
      });
      this._osservatore.observe(this._scena);
    }
  }

  /** I nomi delle zone si misurano a scheda visibile; se non lo e' ancora, si riprova una volta al disegno. */
  _misuraNomi() {
    if (!this._disegno) return;
    this._nomiMisurati = adattaNomi(this._disegno);
    if (!this._nomiMisurati && !this._attesaNomi && typeof requestAnimationFrame === "function") {
      this._attesaNomi = true;
      requestAnimationFrame(() => {
        this._attesaNomi = false;
        if (this._disegno) this._nomiMisurati = adattaNomi(this._disegno);
      });
    }
  }

  _compatta() {
    const larghezza = this._scena ? this._scena.clientWidth : 0;
    return larghezza > 0 && larghezza < LARGHEZZA_COMPATTA;
  }

  _zonaScelta() {
    const attr = this._attributi();
    if (!attr || !Array.isArray(attr.zones) || this._scelta === null) return null;
    return attr.zones.find((z) => z.id === this._scelta) || null;
  }

  _suDisegno(evento) {
    const comando = evento.target.closest("[data-avvia]");
    if (comando) {
      this._comandoZona(comando.getAttribute("data-avvia"));
      return;
    }
    const tessera = evento.target.closest("[data-apri]");
    if (tessera) {
      const id = tessera.getAttribute("data-apri");
      this._scelta = this._scelta === id ? null : id;
      this._aggiorna();
    }
  }

  /** ▶ avvia la zona se tutto e' fermo; ■ sulla zona in funzione ferma tutto. */
  _comandoZona(id) {
    const stato = this._statoSensore();
    const attr = this._attributi();
    if (!stato || !attr || !Array.isArray(attr.zones)) return;
    const zona = attr.zones.find((z) => z.id === id);
    if (!zona) return;
    if (stato.state === "running") {
      if (attr.active_zone === id) this._chiama("switch", "turn_off", { entity_id: zona.manual_entity });
      return;
    }
    this._chiama("switch", "turn_on", { entity_id: zona.manual_entity });
  }

  _inConferma() {
    return this._confermaDa > 0 && Date.now() - this._confermaDa < CONFERMA_MS;
  }

  /** «Avvia ciclo» irriga subito e salta pioggia e riserva: la prima pressione chiede conferma. */
  _premiAvvia() {
    const stato = this._statoSensore();
    const attr = this._attributi();
    if (!stato || !attr || stato.state === "running") return;
    if (this._timerConferma) clearTimeout(this._timerConferma);
    this._timerConferma = null;
    if (this._inConferma()) {
      this._confermaDa = 0;
      this._chiama("button", "press", { entity_id: attr.start_button });
    } else {
      this._confermaDa = Date.now();
      this._timerConferma = setTimeout(() => {
        this._timerConferma = null;
        this._confermaDa = 0;
        this._aggiorna();
      }, CONFERMA_MS);
    }
    this._aggiorna();
  }

  _batti() {
    const stato = this._statoSensore();
    if (this._struttura && stato && stato.state === "running") this._aggiorna();
  }

  _aggiorna() {
    if (!this._config || !this._hass) return;
    const stato = this._statoSensore();
    if (!stato) {
      this._avviso(`${this._config.entity} non esiste: controlla l'integrazione ${NOME_INTEGRAZIONE}.`);
      return;
    }
    const attr = stato.attributes || {};
    // Durante un riavvio o una ricarica dell'integrazione il sensore c'e' ma e'
    // «non disponibile», senza gli attributi: non e' una plancia configurata male.
    if (["unavailable", "unknown"].includes(String(stato.state)) && !Array.isArray(attr.zones)) {
      this._avviso(`${this._config.entity} non disponibile: ${NOME_INTEGRAZIONE} non e' caricata o si sta riavviando.`);
      return;
    }
    if (attr.ruolo !== RUOLO_MAPPA && !Array.isArray(attr.zones)) {
      this._avviso(`${this._config.entity} non e' il sensore «Stato» di ${NOME_INTEGRAZIONE}.`);
      return;
    }
    if (!Array.isArray(attr.zones) || attr.zones.length === 0) {
      this._avviso(`${this._titolo(attr) || NOME_INTEGRAZIONE}: nessuna zona configurata.`);
      return;
    }
    if (!this._struttura) this._costruisciStruttura();

    const compatta = this._compatta();
    const firma = firmaScena(attr, compatta);
    if (firma !== this._firma) {
      this._firma = firma;
      const d = disposizione(attr.zones, { compatta, pioggia: Boolean(attr.pioggia), riserva: Boolean(attr.riserva) });
      this._disegno.innerHTML = scena(d, { master: Boolean(attr.master_valve) });
      this._rif = riferimenti(this._disegno);
      this._misuraNomi();
    }
    this._scena.classList.toggle("scuro", Boolean(this._hass.themes && this._hass.themes.darkMode));
    this._scena.classList.toggle("senza-moto", this._config.animazioni === false);
    testo(this._el.titolo, this._titolo(attr));

    try {
      this._aggiornaStato(stato, attr);
    } catch (errore) {
      console.error(`${NOME_INTEGRAZIONE}: scheda non aggiornata`, errore);
    }
  }

  _aggiornaStato(stato, attr) {
    const adesso = Date.now();
    const lingua = this._lingua();
    const inPausa = stato.state === "running" && !attr.active_zone && !attr.manuale;
    if (!inPausa) this._pausaDa = null;
    else if (this._pausaDa === null) this._pausaDa = adesso;
    const quadro = quadroImpianto(attr, stato.state, adesso, this._pausaDa);
    const abilitaStato = attr.enable_entity ? this._hass.states[attr.enable_entity] : null;
    const abilitata = abilitaStato ? abilitaStato.state === "on" : null;
    const rif = this._rif;

    // Zone
    quadro.zone.forEach((z) => {
      const scelta = this._scelta === z.id ? " scelta" : "";
      tutti(rif.zone[z.id], (n) => attributo(n, "class", `zona ${z.classe}${scelta}`));
      tutti(rif.stati[z.id], (n) => testo(n, z.scritta));
      tutti(rif.barre[z.id], (n) => {
        const larghezza = Number(n.dataset.larghezza) || 0;
        attributo(n, "width", String(Math.round(limita(z.avanzamento, 0, 1) * larghezza * 10) / 10));
      });
      tutti(rif.bagnati[z.id], (n) => attributo(n, "opacity", z.bagnato.toFixed(3)));
      const attiva = z.classe === "attiva";
      tutti(rif.getti[z.id], (n) => {
        n.classList.toggle("in-moto", attiva);
        const rotore = n.querySelector(".rotore");
        if (rotore) rotore.classList.toggle("in-moto", attiva);
      });
      tutti(rif.acque[z.id], (n) => n.classList.toggle("piena", attiva));
      tutti(rif.flussi[z.id], (n) => n.classList.toggle("in-moto", attiva));
      tutti(rif.spie[z.id], (n) => {
        const colore = z.classe === "errore" ? "#DE4A51" : attiva ? "#2E9E6B" : z.classe === "tentativo" ? "#E39B32" : "var(--ns-bordo-metallo)";
        attributo(n, "fill", colore);
        n.classList.toggle("acceso", attiva || z.classe === "tentativo");
      });
      tutti(rif.icone[z.id], (n) => {
        const bx = Number(n.dataset.bx);
        const by = Number(n.dataset.by);
        attributo(n, "d", z.puoFermare ? ICONA_FERMA(bx, by) : ICONA_AVVIA(bx, by));
        attributo(n, "fill", z.puoFermare ? "var(--rosso-testo)" : "var(--blu-testo)");
      });
      const spento = !z.puoFermare && !z.puoAvviare;
      tutti(rif.comandi[z.id], (n) => {
        n.classList.toggle("spento", spento);
        attributo(n, "aria-disabled", String(spento));
        attributo(n, "aria-label", `${z.puoFermare ? "Ferma" : "Avvia"} ${z.nome}`);
      });
    });

    // Master e contatore: la master dice lei se e' aperta, il contatore gira con l'acqua
    const masterAperto = Boolean(attr.master_valve) && Boolean(attr.master_open);
    tutti(rif.ventole.master, (n) => n.classList.toggle("in-moto", masterAperto));
    tutti(rif.spie.master, (n) => {
      attributo(n, "fill", masterAperto ? "#2E9E6B" : "var(--ns-bordo-metallo)");
      n.classList.toggle("acceso", masterAperto);
    });
    tutti(rif.ventole.contatore, (n) => n.classList.toggle("in-moto", quadro.acquaInMoto));

    // Pioggia
    const pioggia = attr.pioggia || null;
    if (pioggia) {
      const piove = Boolean(pioggia.rilevata);
      const nuvole = (Number(pioggia.caduta_mm) || 0) > 0 || (Number(pioggia.prevista_mm) || 0) > 0;
      if (rif.pioggia) rif.pioggia.classList.toggle("in-moto", piove);
      attributo(rif.sole, "opacity", piove ? "0" : nuvole ? "0.4" : "1");
      tutti(rif.valori.pioggia, (n) => testo(n, testoPioggia(pioggia, lingua)));
    }

    // Riserva: livello, soglia e valore
    const riserva = attr.riserva || null;
    let riservaMm = null;
    if (riserva) {
      const statoRiserva = riserva.entita ? this._hass.states[riserva.entita] : null;
      riservaMm = numero(statoRiserva);
      const capacita = Number(riserva.capacita) > 0 ? Number(riserva.capacita) : null;
      tutti(rif.valori.riserva, (n) => testo(n, this._testoRiserva(statoRiserva, riservaMm, lingua)));
      tutti(rif.livelli.riserva, (n) => {
        const basso = Number(n.dataset.basso);
        const altezza = capacita && riservaMm !== null ? 142 * limita(riservaMm / capacita, 0, 1) : 0;
        attributo(n, "height", altezza.toFixed(1));
        attributo(n, "y", (basso - altezza).toFixed(1));
      });
      tutti(rif.soglie.riserva, (g) => {
        const soglia = Number(riserva.soglia);
        const visibile = capacita !== null && Number.isFinite(soglia);
        attributo(g, "opacity", visibile ? "1" : "0");
        if (!visibile) return;
        const alto = Number(g.dataset.alto);
        const basso = Number(g.dataset.basso);
        const y = basso - (basso - alto) * limita(soglia / capacita, 0, 1);
        const linea = g.querySelector("line");
        const scritta = g.querySelector("text");
        attributo(linea, "y1", y.toFixed(1));
        attributo(linea, "y2", y.toFixed(1));
        attributo(scritta, "y", (y + 6).toFixed(1));
        testo(scritta, `soglia ${numeroTesto(soglia, 1, lingua)}`);
      });
    }

    // Riquadri
    const ciclo = riquadroCiclo(attr, quadro, abilitata, adesso);
    tutti(rif.etichette.prossimo, (n) => testo(n, ciclo.etichetta));
    tutti(rif.valori.prossimo, (n) => testo(n, ciclo.valore));
    const consumo = numero(attr.consumo_prato_mm);
    tutti(rif.valori.consumo, (n) => testo(n, consumo === null ? "—" : `${numeroTesto(consumo, 1, lingua, 1)} mm/giorno`));

    this._disegnaTessere(tessereImpianto(attr, stato.state, quadro, { abilitata, riservaMm, adesso, lingua }));
    this._aggiornaComandi(stato, attr, quadro, abilitaStato);
  }

  _testoRiserva(statoRiserva, riservaMm, lingua) {
    if (!valido(statoRiserva) || riservaMm === null) return "—";
    // Il numero lo scrive Home Assistant, con la sua precisione e la sua lingua
    if (typeof this._hass.formatEntityState === "function") {
      try {
        return this._hass.formatEntityState(statoRiserva);
      } catch (errore) {
        /* si continua col ripiego */
      }
    }
    return `${numeroTesto(riservaMm, 1, lingua, 1)} mm`;
  }

  _scriviDurata(minuti, stagionale) {
    const lingua = this._lingua();
    testo(this._el.pannelloMinuti, `${numeroTesto(minuti, 1, lingua)} min`);
    testo(this._el.pannelloNota, notaDurata(minuti, stagionale, lingua));
  }

  _aggiornaComandi(stato, attr, quadro, abilitaStato) {
    const el = this._el;
    const inCorso = stato.state === "running";

    // Pannello della zona scelta
    const zona = this._zonaScelta();
    if (!zona) this._scelta = null;
    el.pannello.hidden = !zona;
    if (zona) {
      const riga = quadro.zone.find((z) => z.id === zona.id);
      testo(el.pannelloNome, riga.nome);
      testo(el.pannelloTipo, riga.tipo === "drip" ? "goccia" : "prato");
      const minuti = Number.isFinite(riga.minuti) ? riga.minuti : numero(this._hass.states[zona.duration_entity]) || 0;
      // Solo il trascinamento tiene fermo il cursore: il fuoco no, perche' dopo un
      // tocco resta sul cursore anche per ore (tablet a muro) e il pannello smetterebbe
      // di seguire Home Assistant. Dopo il rilascio si aspetta la conferma del valore
      // inviato, al massimo 5 secondi.
      const inviata = this._durataInviata;
      const inAttesa = Boolean(inviata) && inviata.id === zona.id && Date.now() < inviata.fino
        && Math.round(minuti) !== inviata.valore;
      if (inviata && !inAttesa) this._durataInviata = null;
      if (!this._trascina && !inAttesa) {
        // Oltre i 60 minuti il cursore si allunga: non deve tagliare una durata gia' impostata
        const massimo = String(Math.max(DURATA_MASSIMA_CURSORE, Math.ceil(minuti)));
        if (el.durata.max !== massimo) el.durata.max = massimo;
        el.durata.value = String(Math.round(minuti));
        this._scriviDurata(minuti, attr.seasonal);
      }
      el.durata.disabled = !zona.duration_entity;
      let etichettaZona = "Avvia solo questa zona";
      if (riga.puoFermare) etichettaZona = quadro.manuale ? "Ferma" : "Ferma tutto il ciclo";
      testo(el.pannelloZona, etichettaZona);
      el.pannelloZona.disabled = !riga.puoFermare && !riga.puoAvviare;
    }

    // Interruttore del programma, giorni e ora
    el.abilita.checked = Boolean(abilitaStato) && abilitaStato.state === "on";
    el.abilita.disabled = !abilitaStato;
    const giorni = Array.isArray(attr.day_entities) ? attr.day_entities : [];
    el.bottoniGiorno.forEach((b, i) => {
      const s = giorni[i] ? this._hass.states[giorni[i]] : null;
      attributo(b, "aria-pressed", String(Boolean(s) && s.state === "on"));
      b.disabled = !s;
    });
    const fuoriUso = Boolean(attr.day_mode) && attr.day_mode !== "weekly";
    el.giorni.classList.toggle("fuori-uso", fuoriUso);
    if (fuoriUso) el.giorni.title = "I giorni della settimana valgono solo con la modalità settimanale";
    else el.giorni.removeAttribute("title");
    const ora = attr.start_time_entity ? this._hass.states[attr.start_time_entity] : null;
    el.ora.disabled = !ora;
    if (valido(ora) && this.shadowRoot.activeElement !== el.ora) {
      const valore = String(ora.state).slice(0, 5);
      if (el.ora.value !== valore) el.ora.value = valore;
    }

    // Avvia ciclo (con conferma) e Arresta
    const inConferma = this._inConferma();
    if (!inConferma) this._confermaDa = 0;
    el.avvia.disabled = inCorso || !attr.start_button;
    el.avvia.classList.toggle("conferma", inConferma && !inCorso);
    el.avvia.classList.toggle("primario", !inConferma || inCorso);
    testo(el.avvia.querySelector("span"), inConferma && !inCorso ? "Conferma: irriga ora" : "Avvia ciclo");
    el.arresta.disabled = !inCorso || !attr.stop_button;
  }

  _disegnaTessere(tessere) {
    const firma = tessere.map((t) => `${t.testo}|${t.classe}`).join("§");
    if (firma === this._firmaTessere) return;
    this._firmaTessere = firma;
    this._el.tessere.innerHTML = tessere
      .map((t) => `<span class="tessera ${t.classe}">${testoSicuro(t.testo)}</span>`)
      .join("");
  }
}
// Distingue questa scheda dalla vecchia «Nexus Irrigation Card» di HACS, che usava lo stesso nome
NexusIrrigationCard.inclusaNellIntegrazione = true;

// -----------------------------------------------------------------------------
// Editor
// -----------------------------------------------------------------------------
const SCHEMA_EDITOR = [
  { name: "entity", required: true, selector: { entity: { integration: DOMINIO, domain: "sensor" } } },
  { name: "title", selector: { text: {} } },
  { name: "animazioni", selector: { boolean: {} } },
];
const ETICHETTE_EDITOR = {
  entity: "Sensore «Stato» dell'impianto",
  title: "Titolo (vuoto: il nome dell'impianto)",
  animazioni: "Animazioni",
};

class NexusIrrigationCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = config;
    this._aggiorna();
  }

  set hass(hass) {
    this._hass = hass;
    this._aggiorna();
  }

  _aggiorna() {
    if (!this._config || !this._hass) return;
    if (!this._form) {
      this._form = document.createElement("ha-form");
      this._form.schema = SCHEMA_EDITOR;
      this._form.computeLabel = (voce) => ETICHETTE_EDITOR[voce.name] || voce.name;
      this._form.addEventListener("value-changed", (evento) => {
        const valore = { ...evento.detail.value };
        if (valore.animazioni !== false) delete valore.animazioni;
        if (!valore.title) delete valore.title;
        this.dispatchEvent(new CustomEvent("config-changed", { detail: { config: valore }, bubbles: true, composed: true }));
      });
      this.appendChild(this._form);
    }
    this._form.hass = this._hass;
    this._form.data = { ...this._config, animazioni: this._config.animazioni !== false };
  }
}

// -----------------------------------------------------------------------------
// Registrazione: idempotente e non fatale
// -----------------------------------------------------------------------------
try {
  const esistente = customElements.get(ELEMENTO);
  if (esistente) {
    // Gia' definita: se e' la vecchia card di HACS non la si tocca, lo si dice
    if (!esistente.inclusaNellIntegrazione) {
      console.warn(
        `${NOME_INTEGRAZIONE}: «${ELEMENTO}» e' gia' definita dalla vecchia «Nexus Irrigation Card». ` +
          "Rimuovi la vecchia «Nexus Irrigation Card» da HACS (e la sua risorsa in Lovelace) e ricarica la pagina: " +
          "la scheda animata ora arriva con l'integrazione."
      );
    }
  } else {
    customElements.define(ELEMENTO, NexusIrrigationCard);
    if (!customElements.get(`${ELEMENTO}-editor`)) customElements.define(`${ELEMENTO}-editor`, NexusIrrigationCardEditor);
    window.customCards = window.customCards || [];
    window.customCards.push({
      type: ELEMENTO,
      name: NOME_INTEGRAZIONE,
      description: DESCRIZIONE_CARD,
      preview: true,
      documentationURL: `https://github.com/Pacco24626/${DOMINIO}`,
    });
    console.info(
      `%c NEXUS-IRRIGATION-CARD %c ${VERSIONE_CARD} `,
      "color:#fff;background:#2F7FC1;font-weight:700;",
      "color:#2F7FC1;background:#E6F1FA;font-weight:700;"
    );
  }
} catch (errore) {
  console.error(`${NOME_INTEGRAZIONE}: registrazione della card non riuscita`, errore);
}

export { NexusIrrigationCard, NexusIrrigationCardEditor, VERSIONE_CARD, RUOLO_MAPPA };
