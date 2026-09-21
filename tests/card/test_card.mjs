/**
 * Prove a tavolino della scheda: disposizione, orari, stato delle zone e
 * tessere, cioe' tutto quello che sbaglierebbe in silenzio senza che il
 * disegno lo dia a vedere.
 *
 *     node tests/card/test_card.mjs
 *
 * La scheda e' fatta per il browser: qui si mettono al loro posto le poche
 * cose che cerca al caricamento, poi si importa il file vero (non una copia).
 * Il disegno e i comandi si collaudano in tests/card/prova_browser.js.
 */

globalThis.HTMLElement = class {
  attachShadow() {
    return { innerHTML: "", querySelector: () => null, querySelectorAll: () => [] };
  }
};
const definite = {};
globalThis.customElements = { get: (n) => definite[n], define: (n, c) => { definite[n] = c; } };
globalThis.window = globalThis;
globalThis.document = { createElement: () => ({}) };
const annunci = [];
const avvisi = [];
console.info = (...righe) => annunci.push(righe.join(" "));
console.warn = (...righe) => avvisi.push(righe.join(" "));

const PERCORSO = "../../custom_components/nexus_irrigation/www/nexus-irrigation-card.js";
const carta = await import(PERCORSO);
const {
  numero, testoSicuro, orario, durata, minutiEffettivi, scartoGiorni, quando, notaDurata, testoPioggia,
  fasciaAlta, disposizione, firmaScena, quadroImpianto, riquadroCiclo, tessereImpianto, trovaStato,
  RUOLO_MAPPA, VERSIONE_CARD,
} = carta;
const casi = await import("./casi.js");
const { adessoProva, istante, oggiAlle, zona, attributi, STATO } = casi;

let passate = 0;
const fallite = [];
function v(descrizione, condizione, dettaglio = "") {
  if (condizione) {
    passate += 1;
    console.log(`  ok   ${descrizione}`);
  } else {
    fallite.push(descrizione);
    console.log(`  NO   ${descrizione}${dettaglio ? `  [${dettaglio}]` : ""}`);
  }
}
const ADESSO = adessoProva(); // lunedi' 21/09/2026 21:15
const perId = (quadro, id) => quadro.zone.find((z) => z.id === id);
const dettaglio = (quadro) => quadro.zone.map((z) => `${z.id}:${z.classe}:${z.scritta}`).join(" / ");

// -----------------------------------------------------------------------------
console.log("\n1. Leggere e scrivere");
v("un numero e' un numero, la virgola non lo rovina", numero({ state: "9.8" }) === 9.8 && numero("12,5") === 12.5);
v("«unavailable» non e' zero", numero({ state: "unavailable" }) === null);
v("i nomi non diventano HTML", testoSicuro('<img src=x onerror="alert(1)">') === "&lt;img src=x onerror=&quot;alert(1)&quot;&gt;");
v("l'apostrofo si protegge anche negli attributi", testoSicuro("Prato d'ingresso") === "Prato d&#39;ingresso");
v("orario nell'ora locale", orario(new Date(2026, 8, 21, 7, 5).getTime()) === "07:05" && orario(null) === "—");
v("conto alla rovescia m:ss", durata(252) === "4:12" && durata(59.2) === "1:00" && durata(-3) === "0:00" && durata(3900) === "65:00");
v("minuti veri: 420 s = 7 min, 20 s non e' «0 min»", minutiEffettivi(420) === "7 min" && minutiEffettivi(20) === "1 min" && minutiEffettivi(0) === "0 min");
v("oggi, domani, ieri", scartoGiorni(new Date(2026, 8, 21, 23).getTime(), ADESSO) === 0
  && scartoGiorni(new Date(2026, 8, 22, 0, 5).getTime(), ADESSO) === 1
  && scartoGiorni(new Date(2026, 8, 20, 23).getTime(), ADESSO) === -1);
v("il cambio dell'ora legale non sposta i giorni",
  scartoGiorni(new Date(2026, 9, 26, 23).getTime(), new Date(2026, 9, 24, 21).getTime()) === 2
  && scartoGiorni(new Date(2027, 2, 29, 1).getTime(), new Date(2027, 2, 27, 23).getTime()) === 2);
v("prossimo ciclo breve: oggi 23:00", quando(oggiAlle(ADESSO, 23), ADESSO) === "oggi 23:00");
v("breve: domani 23:00", quando(oggiAlle(ADESSO, 23, 0, 1), ADESSO) === "domani 23:00");
v("breve: mer 23:00 (fra due giorni)", quando(oggiAlle(ADESSO, 23, 0, 2), ADESSO) === "mer 23:00");
v("breve: oltre la settimana la data", quando(oggiAlle(ADESSO, 23, 0, 12), ADESSO) === "03/10 23:00");
v("lungo: mercoledì alle 23:00", quando(oggiAlle(ADESSO, 23, 0, 2), ADESSO, "lungo") === "mercoledì alle 23:00");
v("lungo: ieri alle 23:41", quando(oggiAlle(ADESSO, 23, 41, -1), ADESSO, "lungo") === "ieri alle 23:41");
v("zona: Alle 23:00 / Domani 23:00 / Mer 23:00",
  quando(oggiAlle(ADESSO, 23), ADESSO, "zona") === "Alle 23:00"
  && quando(oggiAlle(ADESSO, 23, 0, 1), ADESSO, "zona") === "Domani 23:00"
  && quando(oggiAlle(ADESSO, 23, 0, 2), ADESSO, "zona") === "Mer 23:00");
v("nota della durata col fattore stagionale", notaDurata(10, 70) === "7 min con il fattore stagionale del 70%");
v("nota: 20 minuti al 72,5% (14,5 -> 15 min)", notaDurata(20, 72.5) === "15 min con il fattore stagionale del 72,5%", notaDurata(20, 72.5));
v("nota: a zero minuti la zona non irriga", notaDurata(0, 70) === "A zero minuti la zona non irriga");
const pioggia = (x) => ({ rilevata: false, caduta_mm: 0, prevista_mm: 0, ore_passate: 12, ore_previste: 12, ...x });
v("pioggia: asciutto", testoPioggia(pioggia({})) === "Asciutto");
v("pioggia: caduta nelle ore passate", testoPioggia(pioggia({ rilevata: true, caduta_mm: 4.2 })) === "4,2 mm in 12 h");
v("pioggia: solo prevista", testoPioggia(pioggia({ prevista_mm: 3 })) === "previsti 3,0 mm");
v("pioggia: pluviometro a contatto che segnala", testoPioggia(pioggia({ rilevata: true })) === "Piove");

// -----------------------------------------------------------------------------
console.log("\n2. Disposizione delle zone");
const zone = (n) => Array.from({ length: n }, (_, k) => zona(k + 1));
const perRiga = (d) => d.file.map((f) => f.tessere.length).join("+");
const dentro = (d) => d.file.every((f) => f.tessere.every((t) => t.x >= d.alto.x0 && t.x + t.w <= d.W - 26 + 0.01 && t.y + t.h <= d.H));
const senzaSovrapposizioni = (d) => {
  const tutte = d.file.flatMap((f) => f.tessere);
  return tutte.every((a, i) => tutte.every((b, j) => i === j
    || a.x + a.w <= b.x || b.x + b.w <= a.x || a.y + a.h <= b.y || b.y + b.h <= a.y));
};
const attese = { 1: "1", 2: "2", 3: "3", 4: "2+2", 7: "3+2+2", 12: "3+3+3+3" };
const atteseStrette = { 1: "1", 2: "2", 3: "2+1", 4: "2+2", 7: "2+2+2+1", 12: "2+2+2+2+2+2" };
let altezzaPrima = 0;
[1, 2, 3, 4, 7, 12].forEach((n) => {
  const d = disposizione(zone(n));
  v(`${n} ${n === 1 ? "zona" : "zone"} sulla plancia: ${attese[n]}`, perRiga(d) === attese[n], perRiga(d));
  v(`${n}: tutte dentro il disegno, nessuna sovrapposta, ogni zona una volta`,
    dentro(d) && senzaSovrapposizioni(d) && d.file.flatMap((f) => f.tessere).map((t) => t.zona.id).join() === zone(n).map((z) => z.id).join());
  v(`${n}: il disegno cresce con le righe`, d.H >= altezzaPrima);
  altezzaPrima = d.H;
  const s = disposizione(zone(n), { compatta: true });
  v(`${n} sulla scheda stretta: ${atteseStrette[n]}, larga 640`, perRiga(s) === atteseStrette[n] && s.W === 640, perRiga(s));
  v(`${n} stretta: dentro e senza sovrapposizioni`, dentro(s) && senzaSovrapposizioni(s));
});
v("una zona sola non occupa tutta la riga (al massimo 400)", disposizione(zone(1)).file[0].tessere[0].w === 400);
v("da tre righe in su le aiuole si abbassano", disposizione(zone(7)).file[0].tessere[0].letto === 96 && disposizione(zone(4)).file[0].tessere[0].letto === 132);
v("12 zone strette: sei righe da due", disposizione(zone(12), { compatta: true }).righe === 6);
v("nessuna zona: niente righe", disposizione([]).righe === 0);

console.log("\n3. Fascia alta: pioggia e riserva si ricompattano");
const piena = fasciaAlta();
v("plancia completa come l'anteprima: pioggia 330, riserva 440, riquadri 660 larghi 310",
  piena.meteo[0] === 330 && piena.misura[0] === 440 && piena.riquadri[0].x === 660 && piena.riquadri[0].w === 310);
const senzaPioggia = fasciaAlta({ pioggia: false });
v("senza pioggia la riserva prende il suo posto e i riquadri si allargano",
  senzaPioggia.meteo === null && senzaPioggia.misura[0] === 240 && senzaPioggia.riquadri[0].x === 460 && senzaPioggia.riquadri[0].w === 510);
const senzaRiserva = fasciaAlta({ riserva: false });
v("senza riserva i riquadri vengono subito dopo la pioggia", senzaRiserva.misura === null && senzaRiserva.riquadri[0].x === 440);
const nessuna = fasciaAlta({ pioggia: false, riserva: false });
v("senza nessuna delle due i riquadri stanno accanto al contatore", nessuna.riquadri[0].x === 240 && nessuna.riquadri[1].y === 156);
const strettaPiena = fasciaAlta({ compatta: true });
v("stretta completa: riquadri sotto, in due colonne", strettaPiena.riquadri[0].y === 318 && strettaPiena.riquadri[1].x === 371 && strettaPiena.inizio === 480);
const strettaSola = fasciaAlta({ compatta: true, riserva: false });
v("stretta con la sola pioggia: la nuvola si centra nello spazio", strettaSola.meteo[0] === 398 && strettaSola.misura === null);
const strettaNessuna = fasciaAlta({ compatta: true, pioggia: false, riserva: false });
v("stretta senza pioggia ne' riserva: i riquadri salgono e le zone con loro",
  strettaNessuna.riquadri[0].y === 44 && strettaNessuna.inizio === 360 && strettaNessuna.riquadri[0].x > 200);
v("la disposizione porta con se' la fascia giusta",
  disposizione(zone(2), { compatta: true, pioggia: false, riserva: false }).file[0].y === 360);

console.log("\n4. Firma del ridisegno");
const a0 = attributi(ADESSO);
const f0 = firmaScena(a0, false);
v("stato, secondi e zona attiva non ridisegnano",
  firmaScena({ ...a0, active_zone: "zone_1", zones: a0.zones.map((z) => ({ ...z, seconds: 99, running: true, minutes: 3 })) }, false) === f0);
v("un nome nuovo ridisegna", firmaScena({ ...a0, zones: [{ ...a0.zones[0], name: "Prato" }, a0.zones[1]] }, false) !== f0);
v("un tipo nuovo ridisegna", firmaScena({ ...a0, zones: [{ ...a0.zones[0], tipo: "drip" }, a0.zones[1]] }, false) !== f0);
v("master, pioggia, riserva e larghezza ridisegnano",
  firmaScena({ ...a0, master_valve: "switch.pompa" }, false) !== f0 && firmaScena({ ...a0, pioggia: null }, false) !== f0
  && firmaScena({ ...a0, riserva: null }, false) !== f0 && firmaScena(a0, true) !== f0);

// -----------------------------------------------------------------------------
console.log("\n5. Stato delle zone: fermo");
let q = quadroImpianto(a0, "idle", ADESSO);
v("fermo con next_cycle oggi: «Alle 23:00 · 7 min», la seconda dopo durata e pausa (23:07)",
  perId(q, "zone_1").scritta === "Alle 23:00 · 7 min" && perId(q, "zone_2").scritta === "Alle 23:07 · 7 min", dettaglio(q));
v("fermo: tutte le zone si possono avviare, nessuna fermare", q.zone.every((z) => z.puoAvviare && !z.puoFermare && z.classe === "ferma"));
v("riquadro: PROSSIMO CICLO oggi 23:00", JSON.stringify(riquadroCiclo(a0, q, true, ADESSO)) === JSON.stringify({ etichetta: "PROSSIMO CICLO", valore: "oggi 23:00" }));
q = quadroImpianto(attributi(ADESSO, { next_cycle: oggiAlle(ADESSO, 23, 0, 2) }), "idle", ADESSO);
v("fermo con next_cycle mercoledi': «Mer 23:00 · 7 min»", perId(q, "zone_1").scritta === "Mer 23:00 · 7 min", dettaglio(q));
q = quadroImpianto(attributi(ADESSO, { next_cycle: oggiAlle(ADESSO, 23, 0, 1) }), "idle", ADESSO);
v("fermo con next_cycle domani: «Domani 23:00 · 7 min»", perId(q, "zone_1").scritta === "Domani 23:00 · 7 min", dettaglio(q));
// Valori larghi apposta: senza anticipo e con la pausa normale verrebbe 23:07
const conAnticipo = attributi(ADESSO, { master_valve: "switch.pompa", master_lead: 60, pausa_fra_zone: 70 });
q = quadroImpianto(conAnticipo, "idle", ADESSO);
v("con la master: la seconda parte dopo anticipo + durata + pausa (23:09:10)", perId(q, "zone_2").scritta === "Alle 23:09 · 7 min", dettaglio(q));
const senzaProssimo = attributi(ADESSO, { next_cycle: null });
q = quadroImpianto(senzaProssimo, "idle", ADESSO);
v("senza next_cycle solo i minuti", perId(q, "zone_1").scritta === "7 min");
v("riquadro: sospeso col programma spento, nessuno senza giorni",
  riquadroCiclo(senzaProssimo, q, false, ADESSO).valore === "sospeso" && riquadroCiclo(senzaProssimo, q, true, ADESSO).valore === "nessuno");

console.log("\n6. Stato delle zone: durante un giro");
const tre = [zona(1), zona(2), zona(3)];
const inFunzione = attributi(ADESSO, { zones: tre.map((z) => ({ ...z, running: z.id === "zone_1" })), active_zone: "zone_1", zone_ends_at: istante(ADESSO, { secondi: 252 }) });
q = quadroImpianto(inFunzione, "running", ADESSO);
const z1 = perId(q, "zone_1");
v("in funzione: conto alla rovescia da zone_ends_at", z1.classe === "attiva" && z1.scritta === "In funzione · 4:12", dettaglio(q));
v("barra = 1 - rimanenti/seconds (0,4)", Math.abs(z1.avanzamento - 0.4) < 1e-9);
v("■ sulla zona in funzione, ▶ spento sulle altre", z1.puoFermare && !perId(q, "zone_2").puoAvviare && !perId(q, "zone_2").puoFermare);
v("acqua in moto e posizione nel giro", q.acquaInMoto && q.posizione.k === 1 && q.posizione.n === 3);
// 21:15 + 252 s + 15 s = 21:19:27; + 420 s + 15 s = 21:26:42; + 336 s (8 min al 70%) = 21:32:18
v("in coda con l'orario stimato: ora + rimanenti + pausa + durate",
  perId(q, "zone_2").classe === "coda" && perId(q, "zone_2").scritta === "Alle 21:19 · 7 min" && perId(q, "zone_3").scritta === "Alle 21:26 · 6 min", dettaglio(q));
v("riquadro: FINE PREVISTA alle 21:32", riquadroCiclo(inFunzione, q, true, ADESSO).valore === "21:32" && riquadroCiclo(inFunzione, q, true, ADESSO).etichetta === "FINE PREVISTA",
  riquadroCiclo(inFunzione, q, true, ADESSO).valore);
const conZero = { ...inFunzione, zones: inFunzione.zones.map((z) => (z.id === "zone_2" ? { ...z, seconds: 0 } : z)) };
q = quadroImpianto(conZero, "running", ADESSO);
v("una zona portata a zero durante il giro si salta senza pausa (terza alle 21:19)", perId(q, "zone_3").scritta === "Alle 21:19 · 6 min", dettaglio(q));

const aMano = attributi(ADESSO, {
  zones: [zona(1, { in_ciclo: false }), zona(2, { running: true })],
  active_zone: "zone_2", manuale: true, ciclo: ["zone_2"], zone_ends_at: istante(ADESSO, { secondi: 400 }),
});
q = quadroImpianto(aMano, "running", ADESSO);
v("a mano: «A mano · 6:40»", perId(q, "zone_2").scritta === "A mano · 6:40" && perId(q, "zone_2").classe === "attiva", dettaglio(q));
v("a mano: l'altra zona resta ferma coi suoi minuti, non «fuori giro», e col ▶ spento",
  perId(q, "zone_1").classe === "ferma" && perId(q, "zone_1").scritta === "7 min" && !perId(q, "zone_1").puoAvviare, dettaglio(q));
v("a mano: FINE ZONA e niente «Zona k di n»", riquadroCiclo(aMano, q, true, ADESSO).etichetta === "FINE ZONA" && q.posizione === null);

const apertura = { ...inFunzione, in_apertura: true, zone_ends_at: istante(ADESSO, { secondi: 425 }) };
q = quadroImpianto(apertura, "running", ADESSO);
v("in apertura: «Apertura…», acqua ferma, ■ disponibile",
  perId(q, "zone_1").classe === "tentativo" && perId(q, "zone_1").scritta === "Apertura…" && !q.acquaInMoto && perId(q, "zone_1").puoFermare, dettaglio(q));

const pausa = attributi(ADESSO, { zones: tre, active_zone: null, ciclo_fatte: ["zone_1"] });
q = quadroImpianto(pausa, "running", ADESSO);
v("pausa: la prima fatta, la prossima «In attesa»", perId(q, "zone_1").classe === "fatta" && perId(q, "zone_1").scritta === "Fatta · 7 min"
  && perId(q, "zone_2").classe === "pausa" && perId(q, "zone_2").scritta === "In attesa", dettaglio(q));
// 21:15 + 15 s di pausa + 420 s + 15 s = 21:22:30
v("pausa: la terza dopo la pausa intera (21:22)", perId(q, "zone_3").scritta === "Alle 21:22 · 6 min", dettaglio(q));
v("pausa: nessun ■ e nessun ▶", q.zone.every((z) => !z.puoFermare && !z.puoAvviare));
q = quadroImpianto(pausa, "running", ADESSO, ADESSO - 10000);
v("pausa vista cominciare 10 s fa: restano 5 s", Math.abs(q.restoPausa - 5) < 1e-9);

const fallita = attributi(ADESSO, { zones: tre.map((z) => ({ ...z, running: z.id === "zone_2" })), active_zone: "zone_2", ciclo_non_aperte: ["zone_1"], zone_ends_at: istante(ADESSO, { secondi: 60 }) });
q = quadroImpianto(fallita, "running", ADESSO);
v("non aperta: la zona che non ha confermato resta rossa", perId(q, "zone_1").classe === "errore" && perId(q, "zone_1").scritta === "Non aperta", dettaglio(q));
q = quadroImpianto({ ...a0, ciclo_non_aperte: ["zone_2"] }, "idle", ADESSO);
v("non aperta: resta segnalata anche a giro finito", perId(q, "zone_2").classe === "errore" && perId(q, "zone_1").scritta === "Alle 23:00 · 7 min", dettaglio(q));

const fuoriGiro = attributi(ADESSO, { zones: [zona(1), zona(2, { in_ciclo: false }), zona(3, { in_ciclo: false, seconds: 0, minutes: 0 })] });
q = quadroImpianto(fuoriGiro, "idle", ADESSO);
v("fuori giro: «Non in questo giro»; a durata zero lo dice", perId(q, "zone_2").scritta === "Non in questo giro" && perId(q, "zone_3").scritta === "Durata a zero"
  && perId(q, "zone_2").classe === "fuori", dettaglio(q));
v("fuori giro: il ▶ resta (a mano si puo' sempre)", perId(q, "zone_2").puoAvviare);
q = quadroImpianto({ ...fuoriGiro, active_zone: "zone_1", zone_ends_at: istante(ADESSO, { secondi: 100 }) }, "running", ADESSO);
v("fuori giro anche durante il giro", perId(q, "zone_2").scritta === "Non in questo giro", dettaglio(q));

console.log("\n7. Stato delle zone: giri saltati");
const pioveva = attributi(ADESSO, { skip_reason: "Sono caduti 4.2 mm nelle ultime 12 ore.", zones: [zona(1), zona(2, { in_ciclo: false })] });
q = quadroImpianto(pioveva, "rain_skipped", ADESSO);
v("rain_skipped: «Saltata», prato bagnato, ▶ disponibile", perId(q, "zone_1").scritta === "Saltata" && perId(q, "zone_1").bagnato === 0.16 && perId(q, "zone_1").puoAvviare, dettaglio(q));
v("rain_skipped: la zona fuori giro resta fuori giro", perId(q, "zone_2").scritta === "Non in questo giro");
let t = tessereImpianto(pioveva, "rain_skipped", q, { adesso: ADESSO });
v("rain_skipped: la tessera porta skip_reason", t[0].testo === "Saltato per pioggia: Sono caduti 4.2 mm nelle ultime 12 ore." && t[0].classe === "freddo", JSON.stringify(t));
v("rain_skipped: e dice quando si riprova", t.some((x) => x.testo === "Prossimo ciclo oggi alle 23:00"));
q = quadroImpianto({ ...a0, skip_reason: "Il terreno ha 17.7 mm di riserva." }, "reserve_skipped", ADESSO);
t = tessereImpianto({ ...a0, skip_reason: "Il terreno ha 17.7 mm di riserva." }, "reserve_skipped", q, { adesso: ADESSO, riservaMm: 17.7 });
v("reserve_skipped: «Saltata» e tessera verde col motivo", perId(q, "zone_1").scritta === "Saltata" && perId(q, "zone_1").bagnato === 0
  && t[0].testo === "Saltato per la riserva: Il terreno ha 17.7 mm di riserva." && t[0].classe === "buono", JSON.stringify(t));

console.log("\n8. Tessere");
q = quadroImpianto(a0, "idle", ADESSO);
t = tessereImpianto(a0, "idle", q, { abilitata: true, riservaMm: 9.8, adesso: ADESSO });
v("fermo: ultimo ciclo, prossimo ciclo e riserva sotto soglia", t.map((x) => x.testo).join(" | ")
  === "Ultimo ciclo venerdì alle 23:41 | Prossimo ciclo oggi alle 23:00 | Riserva 9,8 mm sotto la soglia di 10: al prossimo ciclo si irriga",
  t.map((x) => x.testo).join(" | "));
t = tessereImpianto({ ...a0, pioggia: { ...a0.pioggia, prevista_mm: 0.5 } }, "idle", q, { riservaMm: 9.8, adesso: ADESSO });
v("con la pioggia prevista che porta sopra soglia non si promette l'irrigazione", !t.some((x) => x.testo.startsWith("Riserva")));
t = tessereImpianto({ ...senzaProssimo }, "idle", quadroImpianto(senzaProssimo, "idle", ADESSO), { abilitata: false, adesso: ADESSO });
v("programma spento: sospeso, e niente «Nessun ciclo»", t[0].testo === "Programma sospeso: nessun ciclo automatico" && !t.some((x) => x.testo === "Nessun ciclo in programma"));
t = tessereImpianto(senzaProssimo, "idle", quadroImpianto(senzaProssimo, "idle", ADESSO), { abilitata: true, adesso: ADESSO });
v("programma acceso ma nessun ciclo: lo dice", t.some((x) => x.testo === "Nessun ciclo in programma" && x.classe === "caldo"));
q = quadroImpianto(inFunzione, "running", ADESSO);
t = tessereImpianto({ ...inFunzione, master_valve: "switch.pompa", master_open: true }, "running", q, { adesso: ADESSO });
v("in funzione: zona e conto alla rovescia, posizione nel giro, master aperta",
  t.map((x) => x.testo).join(" | ") === "In irrigazione · Zona 1 · 4:12 | Zona 1 di 3 | Master aperta", t.map((x) => x.testo).join(" | "));
q = quadroImpianto(pausa, "running", ADESSO, ADESSO - 3000);
t = tessereImpianto(pausa, "running", q, { adesso: ADESSO });
v("pausa: «Pausa fra le zone · 12 s» e «Zona 2 di 3»", t.map((x) => x.testo).join(" | ") === "Pausa fra le zone · 12 s | Zona 2 di 3", t.map((x) => x.testo).join(" | "));
const finito = attributi(ADESSO, { ciclo_fatte: ["zone_1", "zone_2"] });
t = tessereImpianto(finito, "running", quadroImpianto(finito, "running", ADESSO), { adesso: ADESSO });
v("l'istante fra l'ultima zona e la fine del giro non e' una pausa", !t.some((x) => x.testo.startsWith("Pausa")), JSON.stringify(t));
q = quadroImpianto(fallita, "running", ADESSO);
t = tessereImpianto(fallita, "running", q, { adesso: ADESSO });
v("zona non aperta: tessera d'allarme col nome", t.some((x) => x.testo === "Zona 1 non si è aperta: zona saltata" && x.classe === "avviso allarme"));
q = quadroImpianto(aMano, "running", ADESSO);
t = tessereImpianto(aMano, "running", q, { adesso: ADESSO });
v("a mano: «A mano · Zona 2 · 6:40»", t[0].testo === "A mano · Zona 2 · 6:40" && t.length === 1, JSON.stringify(t));

// -----------------------------------------------------------------------------
console.log("\n9. Sensore, registrazione e versione");
const hass = {
  states: {
    "sensor.altro": { state: "1", attributes: { ruolo: "mappa_fotovoltaico" } },
    "sensor.vecchio": { state: "idle", attributes: { zones: [] } },
    [STATO]: { state: "idle", attributes: { ruolo: RUOLO_MAPPA, zones: [] } },
  },
};
v("trova il sensore Stato col ruolo, prima di quelli con le sole zone", trovaStato(hass) === STATO);
v("in ripiego quello con le zone", trovaStato({ states: { "sensor.vecchio": hass.states["sensor.vecchio"] } }) === "sensor.vecchio");
v("senza sensori: stringa vuota", trovaStato({ states: {} }) === "");
v("ruolo della mappa", RUOLO_MAPPA === "mappa_irrigazione");
v("versione della scheda: 1.6.0", VERSIONE_CARD === "1.6.0");
v("la scheda si registra col nome della vecchia card, e il suo editor",
  Boolean(definite["nexus-irrigation-card"]) && Boolean(definite["nexus-irrigation-card-editor"]));
v("e si annuncia una volta nel selettore delle card",
  window.customCards.filter((c) => c.type === "nexus-irrigation-card" && c.preview === true).length === 1);
v("proposta di configurazione dal selettore", definite["nexus-irrigation-card"].getStubConfig(hass).entity === STATO);
v("dimensioni per la plancia a griglia", JSON.stringify(new definite["nexus-irrigation-card"]().getGridOptions()) === JSON.stringify({ columns: 12, min_columns: 6, rows: "auto" }));

await import(`${PERCORSO}?seconda`);
v("caricata due volte: nessun errore, nessun avviso, nessun doppione",
  avvisi.length === 0 && window.customCards.filter((c) => c.type === "nexus-irrigation-card").length === 1);
delete definite["nexus-irrigation-card"];
class VecchiaCard extends HTMLElement {}
definite["nexus-irrigation-card"] = VecchiaCard;
await import(`${PERCORSO}?vecchia`);
v("con la vecchia card di HACS gia' definita non la si ridefinisce", definite["nexus-irrigation-card"] === VecchiaCard);
v("e si avvisa in italiano di toglierla da HACS", avvisi.length === 1 && /Rimuovi la vecchia «Nexus Irrigation Card» da HACS/.test(avvisi[0]), avvisi.join(" | "));

const totale = passate + fallite.length;
console.log(fallite.length ? `\nSCHEDA: ${passate}/${totale} superate` : `\nSCHEDA: TUTTI I CONTROLLI SUPERATI (${totale})`);
process.exit(fallite.length ? 1 : 0);
