<img src="icons/logo.png" alt="Nexus Irrigation" width="360">

# Nexus Irrigation

Centralina irrigazione multizona per Home Assistant, configurabile interamente
dall'interfaccia. Nessuno YAML da scrivere.

## Cosa fa

- **Zone in numero libero**, ognuna con la sua valvola (`valve.*` o `switch.*`) e la sua durata.
- **Sequenza garantita**: le zone irrigano una alla volta, mai in parallelo, per non dimezzare la pressione.
- **Valvola master o pompa** facoltativa, con sequenza di apertura e chiusura corretta.
- **Fattore stagionale**: un solo cursore scala tutte le durate. 60% a maggio, 130% a luglio.
- **Salta se il terreno è già bagnato**: bilancio idrico che tiene conto della pioggia caduta, di quella prevista e dell'acqua che il prato consuma ogni giorno.
- **Giorni della settimana** selezionabili singolarmente.
- **Chiusura garantita**: la valvola si chiude anche se il ciclo viene interrotto, e un
  watchdog chiude qualunque valvola resti aperta senza un ciclo attivo.

## Installazione via HACS

1. HACS → menu ⋮ → **Repository personalizzate**
2. URL `https://github.com/Pacco24626/nexus_irrigation`, categoria **Integration**
3. Installa, poi **riavvia Home Assistant**
4. **Impostazioni → Dispositivi e servizi → Aggiungi integrazione → Nexus Irrigation**

Requisiti: Home Assistant 2024.12 o superiore.

## Configurazione

Il config flow chiede, nell'ordine:

1. **Nome impianto** — puoi crearne più d'uno (giardino, orto, serra), ognuno indipendente.
2. **Zone** — nome, valvola, durata base. La spunta *"Aggiungi un'altra zona"* ricicla lo
   step: nessun limite al numero di zone.
3. **Valvola master o pompa** — una spunta. Se l'impianto ha un'elettrovalvola generale
   a monte dei settori o un relè che avvia la pompa, la spunti e scegli l'entità; altrimenti
   tiri dritto. Puoi regolare i due ritardi di sequenza, 3 secondi di default.
4. **Sorgente pioggia** — una fra:
   - *Nessuna*: irriga sempre.
   - *Sensore*: un `binary_sensor` (attivo = piove) o un `sensor` numerico confrontato con la soglia in mm.
   - *Previsioni meteo*: bilancio idrico del terreno, descritto qui sotto.

Tutto è rimodificabile da **Configura** sulla card dell'integrazione.

## Entità generate

Per ogni impianto viene creato un dispositivo con:

| Entità | Descrizione |
|---|---|
| `switch.<impianto>_abilitata` | Interruttore generale |
| `switch.<impianto>_<giorno>` | Uno per giorno della settimana |
| `switch.<impianto>_<zona>` | Avvia la singola zona a mano |
| `number.<impianto>_<zona>_durata` | Durata base della zona |
| `number.<impianto>_fattore_stagionale` | Scala tutte le durate |
| `time.<impianto>_ora_di_avvio` | Orario del ciclo automatico |
| `button.<impianto>_avvia_ciclo` | Giro extra, salta il controllo pioggia |
| `button.<impianto>_arresta` | Arresto immediato, chiude tutto |
| `sensor.<impianto>_stato` | `idle` / `running` / `rain_skipped` |
| `sensor.<impianto>_ultimo_ciclo` | Timestamp |
| `sensor.<impianto>_prossimo_ciclo` | Timestamp del prossimo avvio |
| `sensor.<impianto>_riserva_idrica` | Millimetri stimati nella zona radicale |
| `sensor.<impianto>_evapotraspirazione` | ET₀ del giorno, calcolata con FAO 56 |
| `binary_sensor.<impianto>_pioggia` | Esito dell'ultimo controllo pioggia |
| `binary_sensor.<impianto>_in_irrigazione` | Acceso mentre una zona irriga |
| `binary_sensor.<impianto>_master` | Solo con master configurato: stato della valvola generale |

## Il bilancio idrico

Contare la pioggia su una finestra fissa non basta, per quanto la si allunghi:
**ogni finestra ha un bordo**. Una settimana di pioggia seguita da due giornate
di sole è il caso in cui fallisce peggio — il terreno è al massimo della sua
capacità proprio quando il conteggio è appena scaduto, e l'impianto irriga un
prato zuppo.

Con la sorgente *previsioni meteo* l'integrazione non conta quindi la pioggia,
ma **l'acqua che c'è nel terreno**:

```
riserva = limita(riserva + pioggia + irrigazione − consumo, 0, capacità)

si salta il ciclo se   riserva + pioggia prevista ≥ soglia
```

| Parametro | Predefinito | Da dove viene |
|---|---|---|
| Capacità del terreno | 25 mm | Acqua utile della zona radicale: un terreno medio ne trattiene 140-180 mm al metro, un prato radica sui 15-25 cm. Su sabbia si dimezza. |
| Riserva sotto cui irrigare | 10 mm | Circa metà della capacità: oltre quel prelievo l'erba fatica a estrarre acqua. |
| Consumo giornaliero | *calcolato* | Evapotraspirazione FAO 56, vedi sotto. Il valore fisso di 4 mm/g resta solo come ripiego se mancano i dati meteo. |
| Portata degli irrigatori | 10 mm/h | Serve a riaccreditare nella riserva l'acqua distribuita, altrimenti il modello crede che il terreno sia sempre asciutto. |

Sono valori di partenza tratti dalla letteratura agronomica (FAO 56), non
costanti di natura: dipendono da tessitura del suolo, profondità radicale,
specie del tappeto erboso ed esposizione. Il sensore **riserva idrica** mette
il ragionamento in vista, così guardando quel numero e guardando il prato si
capisce in due settimane se la taratura regge.

Mettendo la capacità a **zero** il bilancio si disattiva e si torna al semplice
confronto fra i millimetri della finestra e la soglia.

Una precisazione: il servizio delle previsioni restituisce solo il futuro. La
pioggia già caduta la costruisce l'integrazione campionando ogni quarto d'ora
la precipitazione dell'ora in corso, un valore per ciascuna ora. È una stima
del servizio meteo, non la misura di un pluviometro, ed esiste solo da quando
l'integrazione è in funzione. Con una sonda di umidità nel terreno si usa la
modalità *sensore* e il modello non serve più.

## Il consumo del prato lo calcola, non lo stima

Con la sorgente *previsioni meteo* il consumo giornaliero non è un numero
fisso: è **evapotraspirazione di riferimento secondo FAO 56**, l'equazione di
Penman-Monteith, calcolata ogni giorno sui dati meteo reali.

```
        0,408 Δ (Rn − G) + γ · 900/(T+273) · u₂ (es − ea)
ET₀ = ───────────────────────────────────────────────────
                    Δ + γ (1 + 0,34 u₂)

consumo del prato = ET₀ × Kc
```

**Non serve configurare niente di geografico.** Latitudine e quota le sa già
Home Assistant, e dalla latitudine si calcola la radiazione extraterrestre —
quanta energia solare arriva in cima all'atmosfera in quel giorno dell'anno.
È astronomia, esatta, e funziona a qualunque latitudine, emisfero sud
compreso: a Nove l'estate cade a luglio, in Brasile a dicembre, e il conto se
ne accorge da solo.

Temperatura massima e minima, umidità e vento vengono dalle previsioni
giornaliere. L'unico ingrediente non misurato dai servizi meteo di consumo è
la **radiazione solare**, e la FAO documenta come stimarla dall'escursione
termica: una giornata limpida ha massime alte e minime basse, una coperta ha
l'escursione schiacciata. La precisione attesa è entro il 10-20% di una
stazione agrometeorologica — molto meglio di un valore fisso che non cambia
mai, perché segue da sé la stagione e il tempo che fa.

Nessuna chiave API, nessun servizio esterno: il calcolo gira offline.

### L'unica domanda che resta

Il **coefficiente colturale Kc** è una proprietà dell'erba, non del luogo, e
non si può dedurre dalla posizione: chi ha piantato una macroterma al nord si
ritroverebbe il consumo sovrastimato di un terzo senza capire perché. Si
sceglie quindi il tipo di prato:

| Tipo | Kc | Dove |
|---|---|---|
| Microterme | 0,85 | Loietto, festuca, poa — centro e nord Europa |
| Macroterme | 0,75 | Gramigna, zoysia — clima mediterraneo e subtropicale |
| Personalizzato | libero | Per chi sa cosa sta facendo |

Il Kc è anche **la manopola di taratura**: l'ET₀ calcola ciò che è
calcolabile, il Kc assorbe in un solo numero tutto ciò che è locale — suolo,
esposizione, altezza di taglio, quanto verde si vuole il prato. Se il prato
ingiallisce mentre la riserva è alta, alzalo; se resta lussureggiante mentre
la riserva si svuota, abbassalo.

C'è poi una spunta per la **posizione costiera**, che cambia il coefficiente
della stima di radiazione: sul mare la brezza smorza l'escursione termica.

Chi ha una stazione meteo vera o un feed regionale può indicare un **sensore
ET₀ esterno**, che ha la precedenza sul calcolo interno.

Quando l'ET₀ è disponibile il **fattore stagionale non scala più il consumo**:
la stagione la conta già il calcolo, che a dicembre dà mezzo millimetro e a
luglio cinque. Continua a scalare le durate di irrigazione, come prima.

## Valvola master e pompa

Facoltativa. Quando c'è, la sequenza di ogni zona diventa:

```
apre il settore → attende il lead → avvia il master → irriga →
ferma il master → attende il lag → chiude il settore
```

**L'ordine non è arbitrario.** Avviare una pompa contro valvole ancora chiuse la manda in
pressione a vuoto: colpo d'ariete alla partenza e, sulle autoclavi, intervento del
pressostato. Alla chiusura vale lo specchio: si toglie pressione e solo dopo si chiude il
settore, così la colonna d'acqua si ferma contro una valvola aperta.

I ritardi predefiniti sono 3 secondi per parte e vanno bene quasi sempre; alzali se le
elettrovalvole sono lente. Il conto alla rovescia della zona parte a valle dell'avvio del
master, quindi i minuti impostati sono minuti d'acqua, non di sequenza.

Il master viene chiuso **per primo** da ogni arresto — pulsante, riavvio, scaricamento
dell'integrazione — e il watchdog lo sorveglia come le altre valvole: se resta aperto
senza un ciclo attivo viene chiuso, perché su un impianto con autoclave significa pompa
che gira a secco.

## Sicurezza

Il comando di chiusura della valvola sta in un blocco `finally`, quindi viene eseguito
anche quando il ciclo viene annullato — cosa che uno script YAML con un `delay` **non**
garantisce: se lo script viene interrotto, il delay muore e la valvola resta aperta.

In più, ogni minuto un watchdog verifica le valvole: quella che risulta aperta per due
rilevazioni consecutive senza un ciclo attivo viene chiusa e viene creata una notifica.
Le valvole vengono chiuse anche all'avvio di Home Assistant e allo scaricamento
dell'integrazione.

## Card dedicata

[Nexus Irrigation Card](https://github.com/Pacco24626/nexus_irrigation_card) — facoltativa.
Senza di essa l'impianto si comanda benissimo con le card standard.

## Licenza

Apache 2.0 — Copyright 2026 Automatic Systems. Vedi [LICENSE](LICENSE).
