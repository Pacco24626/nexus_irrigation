# Nexus Irrigation

Centralina irrigazione multizona per Home Assistant, configurabile interamente
dall'interfaccia. Nessuno YAML da scrivere.

## Cosa fa

- **Zone in numero libero**, ognuna con la sua valvola (`valve.*` o `switch.*`) e la sua durata.
- **Sequenza garantita**: le zone irrigano una alla volta, mai in parallelo, per non dimezzare la pressione.
- **Fattore stagionale**: un solo cursore scala tutte le durate. 60% a maggio, 130% a luglio.
- **Salta se piove**: sensore pioggia, pluviometro o previsioni meteo, con soglia in millimetri.
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
3. **Sorgente pioggia** — una fra:
   - *Nessuna*: irriga sempre.
   - *Sensore*: un `binary_sensor` (attivo = piove) o un `sensor` numerico confrontato con la soglia in mm.
   - *Previsioni meteo*: somma i millimetri previsti nelle prossime N ore da un'entità `weather.*`.

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
| `binary_sensor.<impianto>_pioggia` | Esito dell'ultimo controllo pioggia |
| `binary_sensor.<impianto>_in_irrigazione` | Acceso mentre una zona irriga |

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
