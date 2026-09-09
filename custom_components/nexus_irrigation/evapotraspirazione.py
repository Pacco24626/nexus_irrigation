"""Evapotraspirazione di riferimento secondo FAO 56 (Penman-Monteith).

Nessuna dipendenza da Home Assistant: sono funzioni pure, verificabili a
tavolino. E' voluto — un errore in questa aritmetica non si vedrebbe se non
mesi dopo, guardando un prato ingiallito.

Il riferimento e' Allen et al., *Crop evapotranspiration*, FAO Irrigation and
Drainage Paper 56 (1998), che e' lo standard internazionale in materia. La
formula chiede la radiazione solare misurata; quando manca — ed e' il caso
normale con i servizi meteo di consumo — la stessa pubblicazione documenta
come stimarla dall'escursione termica giornaliera: una giornata limpida ha
massime alte e minime basse, una coperta ha l'escursione schiacciata.
"""

from __future__ import annotations

import math

# Costante solare, MJ per metro quadro al minuto.
COSTANTE_SOLARE = 0.0820

# Costante di Stefan-Boltzmann, MJ K^-4 m^-2 giorno^-1.
STEFAN_BOLTZMANN = 4.903e-9

# Albedo di una superficie erbosa di riferimento.
ALBEDO = 0.23

# Coefficiente della stima di radiazione: 0,16 nell'entroterra, 0,19 sulla
# costa, dove la brezza di mare smorza l'escursione termica.
K_RS_INTERNO = 0.16
K_RS_COSTIERO = 0.19


def pressione_atmosferica(quota_m: float) -> float:
    """Pressione media in kPa alla quota data."""
    return 101.3 * ((293.0 - 0.0065 * quota_m) / 293.0) ** 5.26


def costante_psicrometrica(quota_m: float) -> float:
    """Gamma, in kPa/°C."""
    return 0.000665 * pressione_atmosferica(quota_m)


def pressione_vapore_saturo(temperatura: float) -> float:
    """e0(T), in kPa."""
    return 0.6108 * math.exp(17.27 * temperatura / (temperatura + 237.3))


def pendenza_curva_vapore(temperatura: float) -> float:
    """Delta, in kPa/°C."""
    return (
        4098.0
        * pressione_vapore_saturo(temperatura)
        / (temperatura + 237.3) ** 2
    )


def radiazione_extraterrestre(latitudine: float, giorno_anno: int) -> float:
    """Ra in MJ/m² al giorno.

    E' pura astronomia: quanta energia solare arriva in cima all'atmosfera a
    quella latitudine in quel giorno. Non serve nessun dato meteo, e non c'e'
    incertezza da stimare.
    """
    phi = math.radians(latitudine)
    dr = 1.0 + 0.033 * math.cos(2.0 * math.pi * giorno_anno / 365.0)
    declinazione = 0.409 * math.sin(2.0 * math.pi * giorno_anno / 365.0 - 1.39)

    # Angolo orario al tramonto, con i poli gestiti senza far esplodere l'arcocoseno.
    x = -math.tan(phi) * math.tan(declinazione)
    omega = math.acos(max(-1.0, min(1.0, x)))

    return (
        (24.0 * 60.0 / math.pi)
        * COSTANTE_SOLARE
        * dr
        * (
            omega * math.sin(phi) * math.sin(declinazione)
            + math.cos(phi) * math.cos(declinazione) * math.sin(omega)
        )
    )


def radiazione_da_escursione(
    ra: float, t_max: float, t_min: float, k_rs: float = K_RS_INTERNO
) -> float:
    """Rs stimata dall'escursione termica, in MJ/m² al giorno.

    E' la formula di ripiego prevista dalla FAO quando la radiazione non e'
    misurata. Il risultato viene limitato alla radiazione di cielo sereno:
    senza il tetto, un'escursione anomala produrrebbe piu' energia di quanta
    ne arrivi dal sole.
    """
    escursione = max(0.0, t_max - t_min)
    rs = k_rs * math.sqrt(escursione) * ra
    return min(rs, 0.75 * ra)


def vento_a_2_metri(velocita_ms: float, altezza_m: float = 10.0) -> float:
    """Riporta il vento all'altezza di 2 m, come vuole la formula."""
    if altezza_m <= 0 or abs(altezza_m - 2.0) < 1e-6:
        return velocita_ms
    return velocita_ms * 4.87 / math.log(67.8 * altezza_m - 5.42)


def et0(
    t_max: float,
    t_min: float,
    umidita_pct: float,
    vento_ms: float,
    latitudine: float,
    giorno_anno: int,
    quota_m: float = 0.0,
    radiazione_mj: float | None = None,
    altezza_vento_m: float = 10.0,
    k_rs: float = K_RS_INTERNO,
) -> float:
    """Evapotraspirazione di riferimento in mm al giorno.

    Se `radiazione_mj` e' None viene stimata dall'escursione termica.
    """
    t_media = (t_max + t_min) / 2.0

    delta = pendenza_curva_vapore(t_media)
    gamma = costante_psicrometrica(quota_m)
    u2 = max(0.0, vento_a_2_metri(vento_ms, altezza_vento_m))

    # La pressione di vapore saturo si media sui due estremi, non si calcola
    # sulla media: la curva e' esponenziale e farlo al contrario sottostima.
    es = (pressione_vapore_saturo(t_max) + pressione_vapore_saturo(t_min)) / 2.0
    ea = es * max(0.0, min(100.0, umidita_pct)) / 100.0
    deficit = max(0.0, es - ea)

    ra = radiazione_extraterrestre(latitudine, giorno_anno)
    rs = radiazione_mj if radiazione_mj is not None else radiazione_da_escursione(
        ra, t_max, t_min, k_rs
    )
    rso = (0.75 + 2e-5 * quota_m) * ra

    rns = (1.0 - ALBEDO) * rs

    rapporto = 1.0 if rso <= 0 else max(0.0, min(1.0, rs / rso))
    rnl = (
        STEFAN_BOLTZMANN
        * (((t_max + 273.16) ** 4 + (t_min + 273.16) ** 4) / 2.0)
        * (0.34 - 0.14 * math.sqrt(max(0.0, ea)))
        * (1.35 * rapporto - 0.35)
    )
    rn = rns - rnl

    # Su base giornaliera il flusso di calore nel terreno e' trascurabile.
    g = 0.0

    numeratore = 0.408 * delta * (rn - g) + gamma * (900.0 / (t_media + 273.0)) * u2 * deficit
    denominatore = delta + gamma * (1.0 + 0.34 * u2)
    if denominatore <= 0:
        return 0.0

    return max(0.0, numeratore / denominatore)
