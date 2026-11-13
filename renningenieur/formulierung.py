"""Kleine Helfer, die Zahlen und Zustaende in sprechbare Bausteine wandeln.

Wird von den Warnregeln und von den Antworten gemeinsam benutzt.
"""

from __future__ import annotations

from .config import Texte
from .telemetrie import konstanten as k
from .zustand import Auto, Rennzustand


def komma(wert: float, stellen: int = 1) -> str:
    """1.34 -> "1,3" (so liest es die deutsche Stimme richtig vor)."""
    return f"{wert:.{stellen}f}".replace(".", ",")


def zeitspanne(texte: Texte, ms: float) -> str:
    """Abstand als gesprochener Text: "1,3 Sekunden", "eine Minute 4 Sekunden"."""
    s = abs(ms) / 1000.0
    if s >= 60:
        minuten, rest = int(s // 60), int(round(s % 60))
        if rest == 60:
            minuten, rest = minuten + 1, 0
        if minuten == 1:
            return texte.sag("teile.eine_minute_sekunden", sekunden=rest)
        return texte.sag("teile.minuten_sekunden", minuten=minuten, sekunden=rest)
    return texte.sag("teile.sekunden", sekunden=komma(max(s, 0.1)))


def rundenzeit(ms: int) -> str:
    """92345 -> "1 Minute 32,3" """
    if ms <= 0:
        return "keine Zeit"
    minuten, rest = divmod(ms / 1000.0, 60)
    if minuten:
        return f"{int(minuten)} Minute{'n' if minuten > 1 else ''} {komma(rest)}"
    return f"{komma(rest)} Sekunden"


def reifenbeschreibung(texte: Texte, auto: Auto) -> str:
    """ "neuen Soft" oder "Medium, 12 Runden alt" """
    name = auto.reifen_name
    if auto.reifenalter <= 0:
        return texte.sag("teile.reifen_neu", reifen=name)
    if auto.reifenalter == 1:
        return texte.sag("teile.reifen_eine_runde", reifen=name)
    return texte.sag("teile.reifen_gebraucht", reifen=name, alter=auto.reifenalter)


def abstand(texte: Texte, z: Rennzustand, hinten: Auto, vorne: Auto) -> str | None:
    """Abstand zwischen zwei Autos als Text; None, wenn keine Daten da sind.

    Liegt eine oder mehr Runden dazwischen, wird das statt Sekunden gesagt.
    """
    if hinten.position < vorne.position:
        hinten, vorne = vorne, hinten
    if hinten.position == vorne.position + 1:
        ms = hinten.delta_vorne_ms
    else:
        ms = z.rueckstand_ms(hinten, vorne)
    runden = _runden_rueckstand(z, hinten, vorne)
    if runden >= 1:
        if runden == 1:
            return texte.sag("teile.ueberrundet_eine")
        return texte.sag("teile.ueberrundet", runden=runden)
    if ms <= 0:
        return None
    return zeitspanne(texte, ms)


def _runden_rueckstand(z: Rennzustand, hinten: Auto, vorne: Auto) -> int:
    """Volle Runden Rueckstand (0 = gleiche Runde)."""
    if z.streckenlaenge <= 0:
        return 0
    diff = vorne.gesamtdistanz - hinten.gesamtdistanz
    return max(int(diff // z.streckenlaenge), 0)


def wetter_art(weather: int) -> str:
    return k.WETTER.get(weather, "unbekanntes Wetter")


def staerkster_verschleiss(auto: Auto) -> tuple[float, str]:
    """(Prozent, "vorne links") des am staerksten abgenutzten Reifens."""
    wert = max(auto.reifenverschleiss)
    return wert, k.REIFEN_POSITIONEN[auto.reifenverschleiss.index(wert)]
