/**
 * Prova della scheda nel browser: Chromium senza finestra (il puppeteer di
 * md-to-pdf), la scheda vera caricata come modulo, un finto hass che si segna
 * le chiamate ai servizi.
 *
 *     node tests/card/prova_browser.js
 *
 * Controlla il disegno, i comandi (dominio, servizio e dati di ogni chiamata),
 * i casi senza pioggia e senza riserva, la master, 12 zone, la scheda larga
 * 360 px, il tema scuro, un nome di zona con dentro dell'HTML, la console
 * pulita, e che un aggiornamento con lo stesso impianto non ridisegni l'svg.
 * Salva le schermate in tests/card/schermate/.
 *
 * I moduli ES non si caricano da file://: la pagina si serve da un piccolo
 * server locale sulla cartella del repository, solo per la durata della prova.
 */
const http = require("http");
const fs = require("fs");
const path = require("path");
const puppeteer = require(path.join(process.env.APPDATA, "npm", "node_modules", "md-to-pdf", "node_modules", "puppeteer"));

const RADICE = path.resolve(__dirname, "..", "..");
const SCHERMATE = path.join(__dirname, "schermate");
const TIPI = { ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".png": "image/png" };
const attesa = (ms) => new Promise((r) => setTimeout(r, ms));

function avviaServer() {
  return new Promise((pronto) => {
    const server = http.createServer((richiesta, risposta) => {
      const percorso = decodeURIComponent(new URL(richiesta.url, "http://locale").pathname);
      const file = path.normalize(path.join(RADICE, percorso));
      if (!file.startsWith(RADICE) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
        risposta.writeHead(404);
        risposta.end();
        return;
      }
      risposta.writeHead(200, { "Content-Type": TIPI[path.extname(file)] || "application/octet-stream", "Cache-Control": "no-store" });
      fs.createReadStream(file).pipe(risposta);
    });
    server.listen(0, "127.0.0.1", () => pronto(server));
  });
}

(async () => {
  fs.mkdirSync(SCHERMATE, { recursive: true });
  const server = await avviaServer();
  const indirizzo = `http://127.0.0.1:${server.address().port}/tests/card/pagina.html`;
  const browser = await puppeteer.launch({ headless: "new", args: ["--no-sandbox"] });
  const page = await browser.newPage();
  const errori = [];
  const dialoghi = [];
  page.on("pageerror", (e) => errori.push(`pageerror: ${e.message}`));
  page.on("console", (m) => {
    if (m.type() === "error" || m.type() === "warn" || m.type() === "warning") errori.push(`${m.type()}: ${m.text()}`);
  });
  page.on("dialog", async (d) => {
    dialoghi.push(d.message());
    await d.dismiss();
  });
  // L'orologio della pagina parte da lunedi' 21/09/2026 alle 21:15, e poi cammina
  await page.evaluateOnNewDocument(() => {
    const Vera = Date;
    const scarto = new Vera(2026, 8, 21, 21, 15, 0).getTime() - Vera.now();
    class Finta extends Vera {
      constructor(...argomenti) {
        if (argomenti.length === 0) super(Vera.now() + scarto);
        else super(...argomenti);
      }
      static now() {
        return Vera.now() + scarto;
      }
    }
    window.Date = Finta;
  });
  await page.setViewport({ width: 1000, height: 900, deviceScaleFactor: 1 });
  await page.goto(indirizzo, { waitUntil: "load" });
  await page.waitForFunction(() => window.pronto === true, { timeout: 10000 });

  const esiti = [];
  const v = (nome, ok, dettaglio = "") => esiti.push([nome, Boolean(ok), dettaglio]);

  // --- aiuti -----------------------------------------------------------------
  /** Crea una scheda: `costruisci` gira nella pagina e restituisce { config, stati, opzioni }. */
  const nuova = (nome, costruisci, argomento = null) => page.evaluate((nome, codice, argomento) => {
    // eslint-disable-next-line no-new-func
    const { config, stati, opzioni } = new Function("casi", "argomento", codice)(window.casi, argomento);
    return window.nuova(nome, config, stati, opzioni || {});
  }, nome, costruisci, argomento);
  const aggiorna = (nome, costruisci, argomento = null, scuro = false) => page.evaluate((nome, codice, argomento, scuro) => {
    // eslint-disable-next-line no-new-func
    const { stati } = new Function("casi", "argomento", codice)(window.casi, argomento);
    return window.aggiorna(nome, stati, scuro);
  }, nome, costruisci, argomento, scuro);
  const chiamate = (nome) => page.evaluate((nome) => JSON.parse(JSON.stringify(window.chiamate(nome))), nome);
  const clicca = (nome, selettore) => page.evaluate((nome, sel) => {
    const n = window.carte[nome].shadowRoot.querySelector(sel);
    if (!n) return false;
    if (typeof n.click === "function") n.click();
    else n.dispatchEvent(new MouseEvent("click", { bubbles: true, composed: true, cancelable: true }));
    return true;
  }, nome, selettore);
  const leggi = (nome) => page.evaluate((nome) => {
    const r = window.carte[nome].shadowRoot;
    const q = (s) => r.querySelector(s);
    const qa = (s) => Array.from(r.querySelectorAll(s));
    const t = (s) => (q(s) ? q(s).textContent : null);
    return {
      titolo: t(".titolo"),
      abilita: q('[data-comando="abilita"]') ? q('[data-comando="abilita"]').checked : null,
      stati: qa("[data-stato-zona]").map((n) => n.textContent),
      classi: qa(".zona").map((n) => n.getAttribute("class")),
      tessere: qa(".tessera").map((n) => n.textContent),
      prossimo: t('[data-valore="prossimo"]'),
      etichettaProssimo: t('[data-etichetta="prossimo"]'),
      consumo: t('[data-valore="consumo"]'),
      riserva: t('[data-valore="riserva"]'),
      pioggia: t('[data-valore="pioggia"]'),
      giorni: qa("[data-giorno]").map((b) => (b.getAttribute("aria-pressed") === "true" ? b.textContent : "-")).join(" "),
      ora: q('[data-comando="ora"]') ? q('[data-comando="ora"]').value : null,
      avvia: t('[data-comando="avvia-ciclo"] span'),
      avviaSpento: q('[data-comando="avvia-ciclo"]') ? q('[data-comando="avvia-ciclo"]').disabled : null,
      avviaConferma: q('[data-comando="avvia-ciclo"]') ? q('[data-comando="avvia-ciclo"]').classList.contains("conferma") : null,
      arrestaSpento: q('[data-comando="arresta"]') ? q('[data-comando="arresta"]').disabled : null,
      pannello: q(".pannello") ? !q(".pannello").hidden : null,
      pannelloNome: t('[data-pannello="nome"]'),
      pannelloTipo: t('[data-pannello="tipo"]'),
      pannelloMinuti: t('[data-pannello="minuti"]'),
      pannelloNota: t('[data-pannello="nota"]'),
      pannelloBottone: t('[data-comando="zona-pannello"]'),
      cursore: q('[data-comando="durata"]') ? q('[data-comando="durata"]').value : null,
      zone: qa(".zona").length,
      viewBox: q("svg") ? q("svg").getAttribute("viewBox") : null,
      testo: r.textContent,
    };
  }, nome);
  const scatta = async (nome, file) => {
    const posto = await page.$(`div.posto[data-nome="${nome}"]`);
    await posto.screenshot({ path: path.join(SCHERMATE, file) });
  };
  const togli = (nome) => page.evaluate((nome) => window.togli(nome), nome);

  // Gli stati si costruiscono nella pagina, con l'orologio della pagina
  const CASA = `
    const adesso = Date.now();
    const attr = casi.attributi(adesso, argomento || {});
    return { config: { entity: casi.STATO }, stati: casi.stati(attr, "idle") };`;
  const CASA_IN_FUNZIONE = `
    const adesso = Date.now();
    const zone = [casi.zona(1, { running: true }), casi.zona(2)];
    const attr = casi.attributi(adesso, { zones: zone, active_zone: "zone_1", zone_ends_at: casi.istante(adesso, { secondi: 252 }), ...(argomento || {}) });
    return { stati: casi.stati(attr, "running") };`;

  // ---------------------------------------------------------------------------
  // 1. L'impianto di casa, fermo
  // ---------------------------------------------------------------------------
  await nuova("casa", CASA);
  await attesa(300);
  let s = await leggi("casa");
  v("disegno: due zone, titolo dall'impianto", s.zone === 2 && s.titolo === "Irrigazione", `${s.zone} ${s.titolo}`);
  v("fermo: le zone dicono quando partono", s.stati.join(" / ") === "Alle 23:00 · 7 min / Alle 23:07 · 7 min", s.stati.join(" / "));
  v("riquadri: prossimo ciclo oggi 23:00, consumo 1,8 mm/giorno",
    s.etichettaProssimo === "PROSSIMO CICLO" && s.prossimo === "oggi 23:00" && s.consumo === "1,8 mm/giorno", `${s.prossimo} | ${s.consumo}`);
  v("riserva da Home Assistant (9,8 mm) e cielo asciutto", s.riserva === "9,8 mm" && s.pioggia === "Asciutto", `${s.riserva} | ${s.pioggia}`);
  v("tessere: ultimo ciclo, prossimo ciclo, riserva sotto soglia", s.tessere.join(" | ")
    === "Ultimo ciclo venerdì alle 23:41 | Prossimo ciclo oggi alle 23:00 | Riserva 9,8 mm sotto la soglia di 10: al prossimo ciclo si irriga", s.tessere.join(" | "));
  v("programma: interruttore acceso, lun mer ven, ore 23:00",
    s.abilita === true && s.giorni === "Lun - Mer - Ven - -" && s.ora === "23:00", `${s.abilita} | ${s.giorni} | ${s.ora}`);
  v("fermo: Avvia ciclo acceso, Arresta spento", s.avviaSpento === false && s.arrestaSpento === true && s.avvia === "Avvia ciclo");
  const soglia = await page.evaluate(() => {
    const g = window.carte.casa.shadowRoot.querySelector('[data-soglia="riserva"]');
    return { y: Number(g.querySelector("line").getAttribute("y1")), testo: g.querySelector("text").textContent,
      livello: Number(window.carte.casa.shadowRoot.querySelector('[data-livello="riserva"]').getAttribute("height")) };
  });
  // Suolo da 94 a 236 (142 unita'): soglia 10 su 25 -> 236 - 56,8; riserva 9,8 su 25 -> 55,7
  v("riserva: soglia e livello in proporzione alla capacita'", Math.abs(soglia.y - 179.2) < 0.01 && soglia.testo === "soglia 10" && Math.abs(soglia.livello - 55.7) < 0.1,
    JSON.stringify(soglia));
  await scatta("casa", "01_fermo.png");

  // ---------------------------------------------------------------------------
  // 2. Comandi da fermo
  // ---------------------------------------------------------------------------
  await clicca("casa", '[data-comando="abilita"]');
  let c = await chiamate("casa");
  v("«Abilitata» spento: switch.turn_off sull'interruttore del programma",
    c.length === 1 && c[0].dominio === "switch" && c[0].servizio === "turn_off" && c[0].dati.entity_id === "switch.irrigazione_abilitata", JSON.stringify(c));

  await clicca("casa", '[data-avvia="zone_1"] circle');
  c = await chiamate("casa");
  v("▶ della zona 1: switch.turn_on sulla sua entita' manuale",
    c.length === 2 && c[1].dominio === "switch" && c[1].servizio === "turn_on" && c[1].dati.entity_id === "switch.irrigazione_zona_1", JSON.stringify(c[1]));

  await clicca("casa", '[data-apri="zone_1"] .zona-sfondo');
  await attesa(100);
  s = await leggi("casa");
  v("tocco sulla zona: si apre il pannello con nome, tipo, durata e nota",
    s.pannello && s.pannelloNome === "Zona 1" && s.pannelloTipo === "prato" && s.cursore === "10" && s.pannelloMinuti === "10 min"
    && s.pannelloNota === "7 min con il fattore stagionale del 70%" && s.pannelloBottone === "Avvia solo questa zona", JSON.stringify(s).slice(0, 400));
  v("la zona scelta si vede tratteggiata", s.classi[0].includes("scelta"), s.classi[0]);

  const prima = (await chiamate("casa")).length;
  await page.evaluate(() => {
    const r = window.carte.casa.shadowRoot.querySelector('[data-comando="durata"]');
    [14, 17, 20].forEach((valore) => {
      r.value = String(valore);
      r.dispatchEvent(new Event("input", { bubbles: true }));
    });
  });
  s = await leggi("casa");
  c = await chiamate("casa");
  v("cursore trascinato: nessuna chiamata finche' non si rilascia", c.length === prima, JSON.stringify(c.slice(prima)));
  v("mentre si trascina il pannello mostra il valore nuovo e la durata vera", s.pannelloMinuti === "20 min" && s.pannelloNota === "14 min con il fattore stagionale del 70%",
    `${s.pannelloMinuti} | ${s.pannelloNota}`);
  await page.evaluate(() => {
    const r = window.carte.casa.shadowRoot.querySelector('[data-comando="durata"]');
    r.dispatchEvent(new Event("change", { bubbles: true }));
  });
  c = await chiamate("casa");
  v("al rilascio una sola chiamata: number.set_value sulla durata, 20",
    c.length === prima + 1 && c[prima].dominio === "number" && c[prima].servizio === "set_value"
    && c[prima].dati.entity_id === "number.irrigazione_zona_1_durata" && c[prima].dati.value === 20, JSON.stringify(c.slice(prima)));

  await page.evaluate(() => {
    const g = window.carte.casa.shadowRoot.querySelector('[data-apri="zone_2"]');
    g.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true, composed: true }));
  });
  s = await leggi("casa");
  v("da tastiera: Invio su un'altra zona apre la sua durata", s.pannello && s.pannelloNome === "Zona 2", s.pannelloNome);

  let n = (await chiamate("casa")).length;
  await clicca("casa", '[data-giorno="1"]');
  await clicca("casa", '[data-giorno="0"]');
  c = (await chiamate("casa")).slice(n);
  v("giorni: martedi' spento si accende, lunedi' acceso si spegne",
    c.length === 2 && c[0].servizio === "turn_on" && c[0].dati.entity_id === "switch.irrigazione_martedi"
    && c[1].servizio === "turn_off" && c[1].dati.entity_id === "switch.irrigazione_lunedi", JSON.stringify(c));

  n = (await chiamate("casa")).length;
  // Scrivendo «0630» il campo cambia a ogni cifra: si manda solo il valore finale, all'uscita dal campo
  await page.evaluate(() => {
    const ora = window.carte.casa.shadowRoot.querySelector('[data-comando="ora"]');
    ["00:00", "06:00", "06:03", "06:30"].forEach((valore) => {
      ora.value = valore;
      ora.dispatchEvent(new Event("input", { bubbles: true }));
      ora.dispatchEvent(new Event("change", { bubbles: true }));
    });
  });
  c = (await chiamate("casa")).slice(n);
  v("ora di avvio: mentre si scrive nessuna chiamata", c.length === 0, JSON.stringify(c));
  await page.evaluate(() => {
    window.carte.casa.shadowRoot.querySelector('[data-comando="ora"]').dispatchEvent(new Event("blur"));
  });
  c = (await chiamate("casa")).slice(n);
  v("ora di avvio: all'uscita dal campo una sola time.set_value con time HH:MM:00",
    c.length === 1 && c[0].dominio === "time" && c[0].servizio === "set_value" && c[0].dati.entity_id === "time.irrigazione_ora_di_avvio" && c[0].dati.time === "06:30:00",
    JSON.stringify(c));
  n = (await chiamate("casa")).length;
  await page.evaluate(() => {
    const ora = window.carte.casa.shadowRoot.querySelector('[data-comando="ora"]');
    ora.value = "23:00";
    ora.dispatchEvent(new Event("blur"));
  });
  c = (await chiamate("casa")).slice(n);
  v("ora di avvio uguale a quella di Home Assistant: nessuna chiamata", c.length === 0, JSON.stringify(c));

  n = (await chiamate("casa")).length;
  await clicca("casa", '[data-comando="avvia-ciclo"]');
  s = await leggi("casa");
  c = (await chiamate("casa")).slice(n);
  v("Avvia ciclo, prima pressione: chiede conferma e non chiama niente", s.avvia === "Conferma: irriga ora" && s.avviaConferma && c.length === 0, `${s.avvia} ${JSON.stringify(c)}`);
  await scatta("casa", "02_conferma_e_pannello.png");
  await clicca("casa", '[data-comando="avvia-ciclo"]');
  c = (await chiamate("casa")).slice(n);
  s = await leggi("casa");
  v("seconda pressione: button.press su Avvia ciclo, e il bottone torna com'era",
    c.length === 1 && c[0].dominio === "button" && c[0].servizio === "press" && c[0].dati.entity_id === "button.irrigazione_avvia_ciclo" && s.avvia === "Avvia ciclo",
    JSON.stringify(c));
  n = (await chiamate("casa")).length;
  await clicca("casa", '[data-comando="avvia-ciclo"]');
  await attesa(4300);
  s = await leggi("casa");
  await clicca("casa", '[data-comando="avvia-ciclo"]');
  c = (await chiamate("casa")).slice(n);
  v("dopo 4 s la conferma scade: la pressione successiva chiede di nuovo conferma",
    s.avvia === "Avvia ciclo" && !s.avviaConferma && c.length === 0, `${s.avvia} ${JSON.stringify(c)}`);
  n = (await chiamate("casa")).length;
  await clicca("casa", '[data-comando="arresta"]');
  c = (await chiamate("casa")).slice(n);
  v("da fermo «Arresta» non chiama niente", c.length === 0, JSON.stringify(c));

  // ---------------------------------------------------------------------------
  // 3. Lo stesso impianto in funzione: stessi nodi, comandi giusti
  // ---------------------------------------------------------------------------
  await page.evaluate(() => { window._svgPrima = window.carte.casa.shadowRoot.querySelector("svg"); });
  await aggiorna("casa", CASA_IN_FUNZIONE);
  await attesa(100);
  const stessoNodo = await page.evaluate(() => window.carte.casa.shadowRoot.querySelector("svg") === window._svgPrima);
  v("aggiornare hass con lo stesso impianto non ridisegna l'svg (stesso nodo)", stessoNodo);
  s = await leggi("casa");
  // L'orologio della pagina e' partito alle 21:15 e intanto e' andato avanti di qualche secondo
  v("in funzione: conto alla rovescia sulla zona 1, la 2 in coda con l'orario", /^In funzione · 4:1\d$/.test(s.stati[0]) && /^Alle 21:(19|20) · 7 min$/.test(s.stati[1]),
    s.stati.join(" / "));
  v("in funzione: Avvia ciclo spento, Arresta acceso", s.avviaSpento === true && s.arrestaSpento === false);
  v("in funzione: tessere del giro", /^In irrigazione · Zona 1 · 4:1\d \| Zona 1 di 2$/.test(s.tessere.join(" | ")), s.tessere.join(" | "));
  v("riquadro: FINE PREVISTA", s.etichettaProssimo === "FINE PREVISTA" && /^21:2[67]$/.test(s.prossimo), `${s.etichettaProssimo} ${s.prossimo}`);
  const animato = await page.evaluate(() => {
    const r = window.carte.casa.shadowRoot;
    return {
      acqua: r.querySelector('[data-acqua="zone_1"]').classList.contains("piena"),
      acquaAltra: r.querySelector('[data-acqua="zone_2"]').classList.contains("piena"),
      getto: r.querySelector('[data-getto="zone_1"]').classList.contains("in-moto"),
      contatore: r.querySelector('[data-ventola="contatore"]').classList.contains("in-moto"),
      animazione: getComputedStyle(r.querySelector('[data-flusso="zone_1"]')).animationName,
      icona: r.querySelector('[data-icona="zone_1"]').getAttribute("fill"),
      spenta: r.querySelector('[data-avvia="zone_2"]').classList.contains("spento"),
      aria: r.querySelector('[data-avvia="zone_2"]').getAttribute("aria-disabled"),
      barra: Number(r.querySelector('[data-avanzamento="zone_1"]').getAttribute("width")),
    };
  });
  v("l'acqua scorre solo verso la zona 1, i getti girano, il contatore gira",
    animato.acqua && !animato.acquaAltra && animato.getto && animato.contatore && animato.animazione === "ni-scorri", JSON.stringify(animato));
  v("■ rosso sulla zona 1, ▶ spento sulla zona 2", animato.icona === "var(--rosso-testo)" && animato.spenta && animato.aria === "true", JSON.stringify(animato));
  v("barra al 40% circa (168 s di 420)", animato.barra > 0.38 * 364 && animato.barra < 0.43 * 364, String(animato.barra));

  const primoConto = s.stati[0];
  // Due battiti almeno: il primo puo' cadere ancora dentro lo stesso secondo
  await attesa(2200);
  s = await leggi("casa");
  v("il conto alla rovescia batte da solo, senza aggiornamenti di Home Assistant", s.stati[0] !== primoConto, `${primoConto} -> ${s.stati[0]}`);

  n = (await chiamate("casa")).length;
  await clicca("casa", '[data-avvia="zone_2"] circle');
  await clicca("casa", '[data-comando="avvia-ciclo"]');
  c = (await chiamate("casa")).slice(n);
  v("durante il giro ▶ della zona 2 e «Avvia ciclo» non chiamano niente", c.length === 0, JSON.stringify(c));
  await clicca("casa", '[data-avvia="zone_1"] circle');
  c = (await chiamate("casa")).slice(n);
  v("■ sulla zona in funzione: switch.turn_off sulla sua entita' manuale",
    c.length === 1 && c[0].dominio === "switch" && c[0].servizio === "turn_off" && c[0].dati.entity_id === "switch.irrigazione_zona_1", JSON.stringify(c));
  n = (await chiamate("casa")).length;
  await clicca("casa", '[data-comando="arresta"]');
  c = (await chiamate("casa")).slice(n);
  v("«Arresta» durante il giro: button.press su Arresta",
    c.length === 1 && c[0].dominio === "button" && c[0].servizio === "press" && c[0].dati.entity_id === "button.irrigazione_arresta", JSON.stringify(c));
  await clicca("casa", '[data-apri="zone_1"] .zona-sfondo');
  s = await leggi("casa");
  v("pannello della zona in funzione: «Ferma tutto il ciclo»", s.pannelloNome === "Zona 1" && s.pannelloBottone === "Ferma tutto il ciclo", s.pannelloBottone);
  await scatta("casa", "03_in_funzione.png");

  // Controllo di sanita': un nome nuovo invece ridisegna
  await aggiorna("casa", `
    const adesso = Date.now();
    const zone = [casi.zona(1, { running: true, name: "Prato davanti" }), casi.zona(2)];
    const attr = casi.attributi(adesso, { zones: zone, active_zone: "zone_1", zone_ends_at: casi.istante(adesso, { secondi: 200 }) });
    return { stati: casi.stati(attr, "running") };`);
  const ridisegnato = await page.evaluate(() => window.carte.casa.shadowRoot.querySelector("svg") !== window._svgPrima);
  v("controllo di sanita': cambiato il nome di una zona l'svg si rifa'", ridisegnato);
  s = await leggi("casa");
  v("e dopo il ridisegno il pannello resta aperto sulla stessa zona", s.pannello && s.pannelloNome === "Prato davanti", s.pannelloNome);

  const orologio = await page.evaluate(() => {
    const carta = window.carte.casa;
    const prima = Boolean(carta._orologio);
    window.togli("casa");
    return { prima, dopo: carta._orologio };
  });
  v("l'intervallo di 1 s c'e' da collegata e si cancella alla disconnessione", orologio.prima && orologio.dopo === null, JSON.stringify(orologio));

  // ---------------------------------------------------------------------------
  // 4. Senza pioggia e senza riserva, con la master aperta
  // ---------------------------------------------------------------------------
  await nuova("master", `
    const adesso = Date.now();
    const zone = [casi.zona(1), casi.zona(2, { running: true }), casi.zona(3)];
    const attr = casi.attributi(adesso, { zones: zone, pioggia: null, riserva: null, master_valve: "switch.pompa_pozzo", master_open: true,
      master_lead: 5, pausa_fra_zone: 15, active_zone: "zone_2", ciclo_fatte: ["zone_1"], zone_ends_at: casi.istante(adesso, { secondi: 300 }) });
    return { config: { entity: casi.STATO }, stati: casi.stati(attr, "running") };`);
  await attesa(200);
  s = await leggi("master");
  const blocchi = await page.evaluate(() => {
    const r = window.carte.master.shadowRoot;
    return {
      pioggia: Boolean(r.querySelector('[data-blocco="pioggia"]')),
      riserva: Boolean(r.querySelector('[data-blocco="riserva"]')),
      master: Boolean(r.querySelector('[data-blocco="master"]')),
      xRiquadro: Number(r.querySelector('[data-slot="prossimo"] .sfondo').getAttribute("x")),
      ventola: r.querySelector('[data-ventola="master"]').classList.contains("in-moto"),
      spia: r.querySelector('[data-spia="master"]').getAttribute("fill"),
    };
  });
  v("senza pioggia ne' riserva i due blocchi non ci sono", !blocchi.pioggia && !blocchi.riserva, JSON.stringify(blocchi));
  v("e i riquadri si ricompattano accanto al contatore (x 240)", blocchi.xRiquadro === 240, String(blocchi.xRiquadro));
  v("master: disegnata, gira ed e' verde quando e' aperta", blocchi.master && blocchi.ventola && blocchi.spia === "#2E9E6B", JSON.stringify(blocchi));
  v("tessere: niente riserva, la master aperta si dice", s.tessere.includes("Master aperta") && !s.tessere.some((x) => x.startsWith("Riserva")), s.tessere.join(" | "));
  v("zona fatta, zona in funzione, zona in coda", s.stati[0] === "Fatta · 7 min" && /^In funzione · 5:0\d$/.test(s.stati[1]) && /^Alle 21:2[01] · 6 min$/.test(s.stati[2]),
    s.stati.join(" / "));
  await scatta("master", "04_master_senza_pioggia_riserva.png");
  await togli("master");

  // ---------------------------------------------------------------------------
  // 5. Dodici zone
  // ---------------------------------------------------------------------------
  await nuova("dodici", `
    const adesso = Date.now();
    const zone = Array.from({ length: 12 }, (_, k) => casi.zona(k + 1, k === 6 ? { in_ciclo: false } : {}));
    const attr = casi.attributi(adesso, { zones: zone, next_cycle: casi.oggiAlle(adesso, 23, 0, 2) });
    return { config: { entity: casi.STATO }, stati: casi.stati(attr, "idle") };`);
  await attesa(200);
  s = await leggi("dodici");
  const righe = await page.evaluate(() => {
    const ys = Array.from(window.carte.dodici.shadowRoot.querySelectorAll(".zona-sfondo")).map((n) => n.getAttribute("y"));
    const conta = {};
    ys.forEach((y) => { conta[y] = (conta[y] || 0) + 1; });
    return Object.values(conta).join("+");
  });
  v("12 zone: quattro righe da tre", s.zone === 12 && righe === "3+3+3+3", `${s.zone} ${righe}`);
  v("12 zone: la settima fuori giro, le altre con giorno e ora", s.stati[6] === "Non in questo giro" && s.stati[0] === "Mer 23:00 · 7 min", s.stati.slice(0, 8).join(" / "));
  v("12 zone: prossimo ciclo mer 23:00", s.prossimo === "mer 23:00", s.prossimo);
  await scatta("dodici", "05_dodici_zone.png");
  await togli("dodici");

  // ---------------------------------------------------------------------------
  // 6. Scheda larga 360 px, 7 zone, in pausa fra due zone
  // ---------------------------------------------------------------------------
  await nuova("telefono", `
    const adesso = Date.now();
    const zone = Array.from({ length: 7 }, (_, k) => casi.zona(k + 1));
    const attr = casi.attributi(adesso, { zones: zone, active_zone: null, ciclo_fatte: ["zone_1", "zone_2"], ciclo_non_aperte: [] });
    return { config: { entity: casi.STATO }, stati: casi.stati(attr, "running"), opzioni: { larghezza: 360 } };`);
  await attesa(400);
  s = await leggi("telefono");
  const misure = await page.evaluate(() => {
    const posto = document.querySelector('div.posto[data-nome="telefono"]');
    const carta = window.carte.telefono;
    const ys = Array.from(carta.shadowRoot.querySelectorAll(".zona-sfondo")).map((n) => n.getAttribute("y"));
    const conta = {};
    ys.forEach((y) => { conta[y] = (conta[y] || 0) + 1; });
    return { larga: carta.getBoundingClientRect().width, scorre: posto.scrollWidth, righe: Object.values(conta).join("+") };
  });
  v("360 px: disegno stretto (640) con due zone per riga", s.viewBox.startsWith("0 0 640") && misure.righe === "2+2+2+1", `${s.viewBox} ${misure.righe}`);
  v("360 px: niente scorrimento orizzontale", misure.larga <= 360 && misure.scorre <= 360, JSON.stringify(misure));
  v("pausa: la prossima zona «In attesa», le fatte verdi, le altre in coda",
    s.stati[0] === "Fatta · 7 min" && s.stati[2] === "In attesa" && /^Alle \d\d:\d\d · 14 min$/.test(s.stati[3]), s.stati.join(" / "));
  v("pausa: tessera della pausa e posizione nel giro", s.tessere[0].startsWith("Pausa fra le zone") && s.tessere.includes("Zona 3 di 7"), s.tessere.join(" | "));
  await scatta("telefono", "06_telefono_360.png");
  await togli("telefono");

  // ---------------------------------------------------------------------------
  // 7. Tema scuro, giro saltato per pioggia
  // ---------------------------------------------------------------------------
  await page.evaluate(() => document.body.classList.add("scuro"));
  await nuova("scuro", `
    const adesso = Date.now();
    const zone = [casi.zona(1), casi.zona(2), casi.zona(3), casi.zona(4)];
    const attr = casi.attributi(adesso, { zones: zone, next_cycle: casi.oggiAlle(adesso, 23, 0, 2),
      skip_reason: "Sono caduti 4.2 mm nelle ultime 12 ore e ne sono previsti 1.0 nelle prossime 12.",
      pioggia: { rilevata: true, caduta_mm: 4.2, prevista_mm: 1, ore_passate: 12, ore_previste: 12 } });
    return { config: { entity: casi.STATO }, stati: casi.stati(attr, "rain_skipped", { riserva: 14 }), opzioni: { scuro: true } };`);
  await attesa(300);
  s = await leggi("scuro");
  const tema = await page.evaluate(() => {
    const r = window.carte.scuro.shadowRoot;
    const scena = r.querySelector(".scena");
    return {
      scuro: scena.classList.contains("scuro"),
      fondo: getComputedStyle(scena).getPropertyValue("--ns-fondo").trim(),
      testo: getComputedStyle(r.querySelector(".titolo")).color,
      piove: r.querySelector('[data-pioggia="gocce"]').classList.contains("in-moto"),
      sole: r.querySelector('[data-sole="disco"]').getAttribute("opacity"),
      righe: Array.from(new Set(Array.from(r.querySelectorAll(".zona-sfondo")).map((n) => n.getAttribute("y")))).length,
    };
  });
  v("tema scuro di Home Assistant: la scena passa ai colori scuri", tema.scuro && tema.fondo === "#151B22", JSON.stringify(tema));
  v("il titolo prende il colore del testo dal tema", tema.testo === "rgb(225, 225, 225)", tema.testo);
  v("pioggia rilevata: piove nel disegno e il sole sparisce", tema.piove && tema.sole === "0" && s.pioggia === "4,2 mm in 12 h", `${JSON.stringify(tema)} ${s.pioggia}`);
  v("rain_skipped: zone «Saltata» e tessera col motivo", s.stati.every((x) => x === "Saltata")
    && s.tessere[0] === "Saltato per pioggia: Sono caduti 4.2 mm nelle ultime 12 ore e ne sono previsti 1.0 nelle prossime 12.", s.tessere.join(" | "));
  v("4 zone = 2+2", tema.righe === 2 && s.zone === 4);
  await scatta("scuro", "07_scuro_pioggia.png");
  await togli("scuro");
  await page.evaluate(() => document.body.classList.remove("scuro"));

  // ---------------------------------------------------------------------------
  // 8. Testi dell'utente con dentro dell'HTML
  // ---------------------------------------------------------------------------
  await nuova("html", `
    const adesso = Date.now();
    const zone = [casi.zona(1, { name: "<img src=x onerror=alert(1)>" }), casi.zona(2)];
    const attr = casi.attributi(adesso, { zones: zone, skip_reason: "<script>alert(2)</script>", ciclo_non_aperte: ["zone_1"] });
    return { config: { entity: casi.STATO, title: "<b>Casa</b>" }, stati: casi.stati(attr, "reserve_skipped", { riserva: 17.7 }) };`);
  await attesa(300);
  await clicca("html", '[data-apri="zone_1"] .zona-sfondo');
  await attesa(200);
  s = await leggi("html");
  const iniettati = await page.evaluate(() => {
    const r = window.carte.html.shadowRoot;
    return {
      img: r.querySelectorAll("img").length,
      b: r.querySelectorAll("b").length,
      script: r.querySelectorAll("script").length,
      nome: r.querySelector('[data-nome-zona="zone_1"]').textContent,
      etichetta: r.querySelector('[data-avvia="zone_1"]').getAttribute("aria-label"),
    };
  });
  v("un nome con dell'HTML resta testo: nessun elemento img, b o script", iniettati.img === 0 && iniettati.b === 0 && iniettati.script === 0, JSON.stringify(iniettati));
  v("e si legge com'e': nel disegno, nel pannello, nel titolo, nelle tessere",
    iniettati.nome.startsWith("<img src=x") && s.pannelloNome === "<img src=x onerror=alert(1)>" && s.titolo === "<b>Casa</b>"
    && s.tessere.includes("Saltato per la riserva: <script>alert(2)</script>") && s.tessere.includes("<img src=x onerror=alert(1)> non si è aperta: zona saltata"),
    `${iniettati.nome} | ${s.titolo} | ${s.tessere.join(" | ")}`);
  v("nessun alert partito", dialoghi.length === 0, dialoghi.join(" | "));
  await togli("html");

  // ---------------------------------------------------------------------------
  // 9. Animazioni spente, movimento ridotto, sensore che non c'e'
  // ---------------------------------------------------------------------------
  const IN_FUNZIONE = `
    const adesso = Date.now();
    const attr = casi.attributi(adesso, { zones: [casi.zona(1, { running: true }), casi.zona(2)], active_zone: "zone_1", zone_ends_at: casi.istante(adesso, { secondi: 200 }) });
    return { config: { entity: casi.STATO, animazioni: argomento }, stati: casi.stati(attr, "running") };`;
  await nuova("ferma", IN_FUNZIONE, false);
  await nuova("mossa", IN_FUNZIONE, true);
  await attesa(200);
  const animazione = (nome) => page.evaluate((nome) => getComputedStyle(window.carte[nome].shadowRoot.querySelector('[data-flusso="zone_1"]')).animationName, nome);
  const ferma = await animazione("ferma");
  const mossa = await animazione("mossa");
  v("animazioni: false ferma davvero (e con le animazioni il flusso corre)", ferma === "none" && mossa === "ni-scorri", `${ferma} / ${mossa}`);
  await page.emulateMediaFeatures([{ name: "prefers-reduced-motion", value: "reduce" }]);
  const ridotta = await animazione("mossa");
  await page.emulateMediaFeatures([{ name: "prefers-reduced-motion", value: "no-preference" }]);
  v("chi chiede meno movimento non ha animazioni", ridotta === "none", ridotta);
  await togli("ferma");
  await togli("mossa");
  await nuova("assente", `return { config: { entity: "sensor.non_esiste" }, stati: casi.stati(casi.attributi(Date.now()), "idle") };`);
  s = await leggi("assente");
  v("sensore inesistente: un avviso, non un errore", /sensor\.non_esiste non esiste/.test(s.testo), s.testo);
  await togli("assente");
  const stub = await page.evaluate(() => customElements.get("nexus-irrigation-card").getStubConfig(window.casi.fintoHass(window.casi.stati(window.casi.attributi(Date.now())))).entity);
  v("nel selettore delle card si propone il sensore Stato", stub === "sensor.irrigazione_stato", stub);

  // ---------------------------------------------------------------------------
  // 9. Correzioni della revisione
  // ---------------------------------------------------------------------------
  await nuova("giu", `
    const st = casi.stati(casi.attributi(Date.now()), "idle");
    st[casi.STATO] = { entity_id: casi.STATO, state: "unavailable", attributes: { friendly_name: "Irrigazione Stato", restored: true } };
    return { config: { entity: casi.STATO }, stati: st };`);
  s = await leggi("giu");
  v("sensore non disponibile (riavvio): avviso di riavvio, non di plancia sbagliata",
    /non disponibile/.test(s.testo) && !/non e' il sensore/.test(s.testo), s.testo);
  await togli("giu");

  // Il cursore, dopo il rilascio, torna a seguire Home Assistant anche se tiene il fuoco
  const DURATA = `
    const attr = casi.attributi(Date.now(), { zones: [casi.zona(1, { minutes: argomento }), casi.zona(2)] });
    return { config: { entity: casi.STATO }, stati: casi.stati(attr, "idle") };`;
  await nuova("cursore", DURATA, 10);
  await attesa(100);
  await clicca("cursore", '[data-apri="zone_1"] .zona-sfondo');
  await page.evaluate(() => {
    const r = window.carte.cursore.shadowRoot.querySelector('[data-comando="durata"]');
    r.focus();
    r.value = "25";
    r.dispatchEvent(new Event("input", { bubbles: true }));
    r.dispatchEvent(new Event("change", { bubbles: true }));
  });
  await aggiorna("cursore", DURATA, 10);
  s = await leggi("cursore");
  v("appena rilasciato, prima della conferma, il cursore resta sul valore inviato", s.cursore === "25" && s.pannelloMinuti === "25 min",
    `${s.cursore} | ${s.pannelloMinuti}`);
  await aggiorna("cursore", DURATA, 25);
  await aggiorna("cursore", DURATA, 5);
  s = await leggi("cursore");
  const fuoco = await page.evaluate(() => {
    const r = window.carte.cursore.shadowRoot;
    return r.activeElement === r.querySelector('[data-comando="durata"]');
  });
  v("confermato il valore, una durata cambiata da fuori arriva anche col fuoco sul cursore",
    fuoco && s.cursore === "5" && s.pannelloMinuti === "5 min", `fuoco ${fuoco} | ${s.cursore} | ${s.pannelloMinuti}`);
  await togli("cursore");

  // Scheda stretta con master e pioggia lunga: le scritte non si toccano
  await nuova("strettamaster", `
    const attr = casi.attributi(Date.now(), { master_valve: "switch.pompa", master_open: false,
      pioggia: { rilevata: true, caduta_mm: 12.5, prevista_mm: 0, ore_passate: 24, ore_previste: 12 } });
    return { config: { entity: casi.STATO }, stati: casi.stati(attr, "idle"), opzioni: { larghezza: 360 } };`);
  await attesa(300);
  const sovrapposte = await page.evaluate(() => {
    const r = window.carte.strettamaster.shadowRoot;
    const a = r.querySelector('[data-blocco="master"] text').getBBox();
    const b = r.querySelector('[data-valore="pioggia"]').getBBox();
    const tocca = a.x < b.x + b.width && b.x < a.x + a.width && a.y < b.y + b.height && b.y < a.y + a.height;
    return { tocca, master: [a.x, a.y, a.width, a.height].map(Math.round), pioggia: [b.x, b.y, b.width, b.height].map(Math.round),
      testo: r.querySelector('[data-valore="pioggia"]').textContent };
  });
  v("scheda stretta: la scritta MASTER non tocca il testo della pioggia", !sovrapposte.tocca && /12,5/.test(sovrapposte.testo),
    JSON.stringify(sovrapposte));
  await togli("strettamaster");

  // Nomi misurati davvero: in maiuscolo non finiscono sotto il ▶
  for (const [nomeScheda, larghezza, quante] of [["maiuscole", 360, 4], ["tre", 1000, 3]]) {
    await nuova(nomeScheda, `
      const nomi = ["PRATO DAVANTI", "WWWWWWWWWWWWWWWW", "Aiuole ingresso", "BORDO PISCINA"];
      const zone = Array.from({ length: argomento.quante }, (_, k) => casi.zona(k + 1, { name: nomi[k] }));
      const attr = casi.attributi(Date.now(), { zones: zone });
      return { config: { entity: casi.STATO }, stati: casi.stati(attr, "idle"), opzioni: { larghezza: argomento.larghezza } };`,
    { larghezza, quante });
    await attesa(400);
    const nomi = await page.evaluate((nomeScheda) => {
      const r = window.carte[nomeScheda].shadowRoot;
      return Array.from(r.querySelectorAll(".zona")).map((g) => {
        const t = g.querySelector("[data-nome-zona]");
        const b = t.getBBox();
        const cx = Number(g.querySelector(".comando-zona circle").getAttribute("cx"));
        return { testo: t.textContent, destra: Math.round(b.x + b.width), bottone: cx - 21 };
      });
    }, nomeScheda);
    v(`${nomeScheda}: ogni nome finisce prima del ▶`, nomi.every((x) => x.destra <= x.bottone - 4 && x.testo.length > 0), JSON.stringify(nomi));
    await togli(nomeScheda);
  }

  // ---------------------------------------------------------------------------
  for (const [nome, ok, dettaglio] of esiti) console.log(`${ok ? "ok   " : "NO   "}${nome}${ok ? "" : `  [${dettaglio}]`}`);
  console.log(`console della pagina: ${errori.length ? errori.join(" | ") : "pulita"}`);
  const fallite = esiti.filter(([, ok]) => !ok).length;
  console.log(fallite || errori.length ? `\nBROWSER: ${esiti.length - fallite}/${esiti.length} superate` : `\nBROWSER: TUTTE SUPERATE (${esiti.length})`);
  await browser.close();
  server.close();
  process.exit(fallite || errori.length ? 1 : 0);
})().catch((errore) => {
  console.error(errore);
  process.exit(2);
});
