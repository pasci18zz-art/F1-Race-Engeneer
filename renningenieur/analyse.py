"""Berechnungen fuer Strategiefragen: Tempo, Boxenverlust, Reifenabbau.

Alles hier sind Schaetzungen aus den Rundenzeiten des laufenden Rennens.
Runden mit Boxenstopp (Einfahrt- und Ausfahrtrunde) und Ausreisser
(Safety Car, Dreher, Verkehr) werden herausgerechnet.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

from .zustand import Auto, Rennzustand

AUSREISSER = 1.07  # Runden, die mehr als 7 % ueber dem Median liegen, zaehlen nicht


def box_runden(a: Auto) -> set[int]:
    """Runden, die ein Boxenstopp verfaelscht (Einfahrt und Ausfahrt)."""
    runden: set[int] = set()
    for s in a.boxenstopps:
        runden.update((s.runde, s.runde + 1))
    for s in a.stints[1:]:
        runden.update((s.start_runde - 1, s.start_runde))
    return runden


def saubere_runden(a: Auto) -> dict[int, int]:
    """Rundenzeiten ohne erste Runde, Boxenrunden, Safety Car und Ausreisser.

    Ausreisser werden mit den Nachbarrunden (je drei davor und danach)
    verglichen, damit ein Wetterwechsel nicht alle Runden danach aussortiert.
    """
    raus = box_runden(a) | a.neutral_runden | {1}
    zeiten = {r: ms for r, ms in a.rundenzeiten.items() if r not in raus and ms > 0}
    sauber = {}
    for r, ms in zeiten.items():
        nachbarn = [z for rr, z in zeiten.items() if abs(rr - r) <= 3]
        if ms <= statistics.median(nachbarn) * AUSREISSER:
            sauber[r] = ms
    return sauber


def tempo_unterschied(a: Auto, b: Auto, runden: int = 3) -> tuple[float, int] | None:
    """Wie viel ms ist a pro Runde langsamer als b? (positiv = a langsamer)

    Gerechnet ueber die letzten gemeinsamen sauberen Runden. None, wenn es
    keine gibt.
    """
    za, zb = saubere_runden(a), saubere_runden(b)
    gemeinsam = sorted(set(za) & set(zb))[-runden:]
    if not gemeinsam:
        return None
    return sum(za[r] - zb[r] for r in gemeinsam) / len(gemeinsam), len(gemeinsam)


@dataclass
class Boxenverlust:
    ms: float
    gemessen: int  # Anzahl Stopps, aus denen gerechnet wurde (0 = Standardwert)
    standzeit_ms: float | None


def boxenverlust(z: Rennzustand, standard_s: float = 22.0) -> Boxenverlust:
    """Zeitverlust eines Boxenstopps, gemessen an allen Stopps dieses Rennens.

    Verlust = Einfahrtrunde + Ausfahrtrunde - 2 x normale Runde des Fahrers.
    Als normale Runde zaehlen die saubere Runde direkt davor und direkt
    danach; so verfaelscht ein Wetterwechsel die Messung nicht.
    """
    verluste, standzeiten = [], []
    for a in z.autos:
        if not a.boxenstopps or not a.gueltig:
            continue
        sauber = saubere_runden(a)
        if len(sauber) < 2:
            continue
        for s in a.boxenstopps:
            if not s.fertig:
                continue
            if {s.runde, s.runde + 1} & a.neutral_runden:
                continue  # unter Safety Car gestoppt: Verlust nicht vergleichbar
            rein, raus = a.rundenzeiten.get(s.runde), a.rundenzeiten.get(s.runde + 1)
            davor = [sauber[r] for r in sorted(sauber) if r < s.runde][-1:]
            danach = [sauber[r] for r in sorted(sauber) if r > s.runde + 1][:1]
            if rein and raus and (davor or danach):
                normal = statistics.mean(davor + danach)
                verlust = rein + raus - 2 * normal
                if 5000 <= verlust <= 60000:
                    verluste.append(verlust)
            if s.standzeit_ms > 0:
                standzeiten.append(s.standzeit_ms)
    stand = statistics.mean(standzeiten) if standzeiten else None
    if not verluste:
        return Boxenverlust(standard_s * 1000, 0, stand)
    return Boxenverlust(statistics.median(verluste), len(verluste), stand)


@dataclass
class Rueckkehr:
    position: int
    vorne: Auto | None
    abstand_vorne_ms: float
    hinten: Auto | None
    abstand_hinten_ms: float


def rueckkehr(z: Rennzustand, ich: Auto, verlust_ms: float) -> Rueckkehr:
    """Wo komme ich heraus, wenn ich jetzt stoppe?"""
    nachher = ich.delta_fuehrender_ms + verlust_ms
    andere = [a for a in z.gueltige_autos() if a.im_rennen and a.idx != ich.idx]
    davor = [a for a in andere if a.delta_fuehrender_ms < nachher]
    dahinter = [a for a in andere if a.delta_fuehrender_ms >= nachher]
    vorne = max(davor, key=lambda a: a.delta_fuehrender_ms, default=None)
    hinten = min(dahinter, key=lambda a: a.delta_fuehrender_ms, default=None)
    return Rueckkehr(
        position=len(davor) + 1,
        vorne=vorne,
        abstand_vorne_ms=nachher - vorne.delta_fuehrender_ms if vorne else 0.0,
        hinten=hinten,
        abstand_hinten_ms=hinten.delta_fuehrender_ms - nachher if hinten else 0.0,
    )


def reifenabbau(a: Auto) -> float | None:
    """Wie viel ms pro Runde verliert das Auto auf dem aktuellen Reifensatz?

    Steigung der sauberen Rundenzeiten im laufenden Stint (mind. 3 Runden).
    Da das Auto gleichzeitig leichter wird, ist das eher eine Untergrenze.
    """
    if not a.stints:
        return None
    start = a.stints[-1].start_runde
    zeiten = sorted((r, ms) for r, ms in saubere_runden(a).items() if r > start)
    if len(zeiten) < 3:
        return None
    xs, ys = [r for r, _ in zeiten], [ms for _, ms in zeiten]
    mx, my = statistics.mean(xs), statistics.mean(ys)
    nenner = sum((x - mx) ** 2 for x in xs)
    if nenner == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / nenner


def verschleiss_pro_runde(a: Auto) -> float | None:
    """Prozentpunkte Verschleiss pro Runde auf dem aktuellen Satz."""
    if not a.schaden_bekannt:
        return None
    if a.stints:
        start = a.stints[-1].start_runde
        punkte = sorted((r, i["verschleiss"]) for r, i in a.runden_info.items()
                        if r >= start and i.get("verschleiss") is not None)
        if len(punkte) >= 2 and punkte[-1][0] > punkte[0][0]:
            (r0, v0), (r1, v1) = punkte[0], punkte[-1]
            if v1 > v0:
                return (v1 - v0) / (r1 - r0)
    if a.reifenalter > 0 and a.max_verschleiss > 0:
        return a.max_verschleiss / a.reifenalter
    return None


def konstanz(a: Auto, runden: int = 5) -> tuple[float, float, int, int, int] | None:
    """(Schnitt, Streuung, beste, langsamste, Anzahl) der letzten sauberen Runden in ms.

    Nur Runden auf dem aktuellen Reifensatz, damit ein Reifen- oder
    Wetterwechsel nicht als Schwankung zaehlt.
    """
    start = a.stints[-1].start_runde if a.stints else 0
    sauber = {r: ms for r, ms in saubere_runden(a).items() if r > start}
    letzte = [sauber[r] for r in sorted(sauber)[-runden:]]
    if len(letzte) < 2:
        return None
    return (statistics.mean(letzte), statistics.pstdev(letzte), min(letzte), max(letzte),
            len(letzte))
