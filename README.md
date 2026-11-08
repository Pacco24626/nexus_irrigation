<img src="icons/logo.png" alt="Nexus Irrigation" width="360">

# Nexus Irrigation

Centralina irrigazione multizona per Home Assistant, configurabile interamente
dall'interfaccia. Nessuno YAML da scrivere.

- **Zone in numero libero**, ognuna con la sua valvola (`valve.*` o `switch.*`) e la sua durata.
- **Sequenza garantita**: le zone irrigano una alla volta, mai in parallelo.
- **Valvola master o pompa** facoltativa, con la sequenza di apertura e chiusura corretta.
- **Fattore stagionale**: un solo cursore scala tutte le durate.
- **Salta se il terreno è già bagnato**: bilancio idrico con pioggia caduta, prevista e
  consumo del prato.
- **Chiusura garantita**: la valvola si chiude anche se il ciclo viene interrotto, e un
  watchdog chiude qualunque valvola resti aperta senza un ciclo attivo.
- **Scheda animata inclusa**: disegna l'impianto e il giro in corso, e si registra da sola.

## Requisiti

Home Assistant 2024.12 o superiore. Per il bilancio idrico serve un'integrazione meteo
che fornisca le previsioni giornaliere; nessuna chiave API e nessun servizio esterno.

## Installazione

1. In **HACS** — da Home Assistant 2026.11 si chiama **Marketplace**, in *Impostazioni* — cerca **Nexus Irrigation** e installala
2. **Riavvia Home Assistant**
3. **Impostazioni → Dispositivi e servizi → Aggiungi integrazione → Nexus Irrigation**

> Per provare una versione non ancora pubblicata si può aggiungere questo repository a mano, come *repository personalizzato* di categoria **Integration**: `https://github.com/Pacco24626/nexus_irrigation`

> **Chi aveva la vecchia «Nexus Irrigation Card»**, il repository separato, la rimuova da
> HACS: la scheda è inclusa dalla 1.6.0 e con due file che definiscono la stessa scheda
> vince quello che arriva prima. Le plance esistenti non vanno modificate.

## Configurazione

Il config flow chiede, nell'ordine:

1. **Nome impianto** — puoi crearne più d'uno (giardino, orto, serra), ognuno indipendente.
2. **Zone** — nome, valvola, tipo (prato con irrigatori o goccia), durata base. La spunta
   *"Aggiungi un'altra zona"* ricicla lo step: nessun limite al numero di zone.
3. **Valvola master o pompa** — una spunta. Se l'impianto ha un'elettrovalvola generale a
   monte o un relè che avvia la pompa, la spunti e scegli l'entità. Due ritardi di
   sequenza, 3 secondi di default.
4. **Sorgente pioggia** — una fra:
   - *Nessuna*: irriga sempre.
   - *Sensore*: un `binary_sensor` (attivo = piove) o un `sensor` numerico confrontato con
     la soglia in mm.
   - *Previsioni meteo*: bilancio idrico del terreno.

Tutto è rimodificabile da **Configura** sulla card dell'integrazione.

### Quando irrigare

Quattro modi, scelti dal selettore **modalità giorni**:

| Modo | Cosa fa |
|---|---|
| Giorni della settimana | Gli interruttori lunedì…domenica |
| Giorni dispari | 1, 3, 5… del mese |
| Giorni pari | 2, 4, 6… del mese |
| Ogni N giorni | Passo costante, intervallo da 1 a 30 |

Negli ultimi tre modi gli interruttori dei giorni vengono ignorati.

Ogni zona ha poi un numero **ogni**: 1 significa a tutti i cicli, 3 una volta su tre —
il prato a ogni giro, la siepe una volta su tre.

L'interruttore **ignora la pioggia** sospende il controllo pioggia finché resta acceso:
serve dopo una semina o la posa di un tappeto erboso.

### Il bilancio idrico

Con la sorgente *previsioni meteo* l'integrazione non conta la pioggia, ma **l'acqua che
c'è nel terreno**:

```
riserva = limita(riserva + pioggia + irrigazione − consumo, 0, capacità)

si salta il ciclo se   riserva + pioggia prevista ≥ soglia
```

| Parametro | Predefinito | Come si sceglie |
|---|---|---|
| Capacità del terreno | 25 mm | Acqua utile della zona radicale: un terreno medio ne trattiene 140-180 mm al metro, un prato radica sui 15-25 cm. Su sabbia si dimezza. |
| Riserva sotto cui irrigare | 10 mm | Circa metà della capacità. |
| Consumo giornaliero | *calcolato* | Evapotraspirazione FAO 56. Il valore fisso di 4 mm/g resta come ripiego se mancano i dati meteo. |
| Portata degli irrigatori | 10 mm/h | Serve a riaccreditare nella riserva l'acqua distribuita. |

Mettendo la capacità a **zero** il bilancio si disattiva e si torna al confronto fra i
millimetri della finestra e la soglia.

Con il bilancio attivo lo stato del salto diventa `reserve_skipped`. Il sensore
**pioggia** resta un fatto meteo: dice se sta piovendo abbastanza da contare, non se il
ciclo è stato saltato.

### Il tipo di prato (Kc)

**Non serve configurare niente di geografico**: latitudine e quota le sa già Home
Assistant. L'unica scelta è il tipo di prato, perché il coefficiente colturale è una
proprietà dell'erba e non del luogo:

| Tipo | Kc | Dove |
|---|---|---|
| Microterme | 0,85 | Loietto, festuca, poa — centro e nord Europa |
| Macroterme | 0,75 | Gramigna, zoysia — clima mediterraneo e subtropicale |
| Personalizzato | libero | Per chi sa cosa sta facendo |

**Il Kc è anche la manopola di taratura**: se il prato ingiallisce mentre la riserva è
alta, alzalo; se resta lussureggiante mentre la riserva si svuota, abbassalo.

C'è poi una spunta per la **posizione costiera**, e chi ha una stazione meteo vera può
indicare un **sensore ET₀ esterno**, che ha la precedenza sul calcolo interno.

Quando l'ET₀ è disponibile il **fattore stagionale non scala più il consumo**: continua a
scalare le durate di irrigazione.

### Valvola master e pompa

Quando c'è, la sequenza di ogni zona diventa:

```
apre il settore → attende il lead → avvia il master → irriga →
ferma il master → attende il lag → chiude il settore
```

L'ordine serve a non mandare la pompa in pressione contro valvole chiuse. I ritardi
predefiniti sono 3 secondi per parte: **alzali se le elettrovalvole sono lente**. Il conto
alla rovescia della zona parte a valle dell'avvio del master, quindi i minuti impostati
sono minuti d'acqua.

Il master viene chiuso **per primo** da ogni arresto, e il watchdog lo sorveglia come le
altre valvole.

## Che cosa succede se qualcosa va storto

- **Una valvola che non si apre**: dopo il comando si controlla che la valvola si dichiari
  aperta, con tre tentativi da sei secondi. Se non risponde la zona viene **saltata**,
  arriva una notifica col nome della zona, e il nome resta negli attributi del sensore di
  stato.
- **Un ciclo interrotto**: la chiusura sta in un blocco `finally`, quindi viene eseguita
  anche su annullamento.
- **Una valvola rimasta aperta**: ogni minuto un watchdog la verifica; aperta per due
  rilevazioni consecutive senza un ciclo attivo, viene chiusa con notifica. Le valvole
  vengono chiuse anche all'avvio di Home Assistant e allo scaricamento dell'integrazione.

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
| `sensor.<impianto>_stato` | `idle` / `running` / `rain_skipped` / `reserve_skipped`. L'attributo `skip_reason` dice perché |
| `sensor.<impianto>_ultimo_ciclo` | Timestamp |
| `sensor.<impianto>_prossimo_ciclo` | Timestamp del prossimo avvio |
| `sensor.<impianto>_riserva_idrica` | Millimetri stimati nella zona radicale |
| `sensor.<impianto>_evapotraspirazione` | ET₀ del giorno, calcolata con FAO 56 |
| `binary_sensor.<impianto>_pioggia` | Acceso se piove abbastanza da contare |
| `select.<impianto>_modalita_giorni` | Settimanale, dispari, pari o ciclico |
| `number.<impianto>_intervallo_giorni` | Ogni quanti giorni, in modalità ciclica |
| `number.<impianto>_<zona>_ogni` | Ogni quanti cicli tocca a quella zona |
| `switch.<impianto>_ignora_la_pioggia` | Bypass del controllo pioggia |
| `binary_sensor.<impianto>_in_irrigazione` | Acceso mentre una zona irriga |
| `binary_sensor.<impianto>_master` | Solo con master configurato: stato della valvola generale |

## La scheda

È inclusa nell'integrazione, che la serve e la registra da sola: nessun file da aggiungere
a mano. Si aggiunge alla plancia cercando *Nexus Irrigation* fra le schede personalizzate.

```yaml
type: custom:nexus-irrigation-card
entity: sensor.giardino_stato
title: Giardino     # facoltativo
animazioni: true    # facoltativo: false ferma le animazioni
```

Il **tipo di zona** (prato o goccia) serve solo al disegno, si sceglie nel config flow e da
**Configura → Zone**; le zone create prima della 1.6.0 valgono prato.

Senza la scheda l'impianto si comanda benissimo con le card standard.

## Licenza

Apache 2.0 — Copyright 2026 Automatic Systems. Vedi [LICENSE](LICENSE).
