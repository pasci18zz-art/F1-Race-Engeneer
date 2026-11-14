"""Eigene Befehle und Katalog der eingebauten Befehle.

Ein eigener Befehl besteht aus
  * Ausloesern: Woerter, bei denen er antwortet (z. B. "reifen nachbarn"),
  * einem Ziel: von welchem Fahrer die Infos kommen (ich, Vordermann, fester
    Platz, "wen ich in der Frage nenne", die ersten fuenf, ...),
  * Infos: was gesagt wird (Reifen, Reifenalter, Abstand, Wetter, ...),
  * optional einem eigenen Antworttext mit Platzhaltern wie {reifen}.

Eigene Befehle haben Vorrang vor den eingebauten. Sie werden in
eigene_befehle.json gespeichert und gelten sofort, ohne Neustart.

Beispiel:
    {"name": "Nachbarn", "ausloeser": ["reifen nachbarn"],
     "ziel": {"art": "um_mich", "n": 1}, "infos": ["reifen", "reifenalter"]}
    "Wie sind die Reifen von meinen Nachbarn?" ->
    "Vorne Norris: Reifen Medium, Reifenalter 5 Runden. Hinten Kumpel: ..."
"""

from __future__ import annotations

import copy
import json
import logging
import re
import statistics
import threading
import unicodedata
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import analyse
from . import formulierung as f
from .telemetrie import konstanten as k

log = logging.getLogger(__name__)

DATEI = "eigene_befehle.json"
MAX_BEFEHLE = 100
MAX_LISTE = 10  # so viele Fahrer nennt ein Befehl hoechstens auf einmal
ERS_MAX_J = 4_000_000.0


def norm(text: str) -> str:
    """ "Hülkenberg!" -> "hulkenberg" """
    text = text.lower().replace("ß", "ss")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


# ==========================================================================
# Infos
# ==========================================================================
class Ctx:
    """Alles, was eine Info zum Berechnen braucht."""

    def __init__(self, z, a, ich, t, verlust_standard: float = 22.0):
        self.z, self.a, self.ich, self.t = z, a, ich, t
        self.verlust_standard = verlust_standard

    @property
    def oeffentlich(self) -> bool:
        """Eigene Daten und die von KI-Fahrern sind immer da, die von Mitspielern nur bei 'Oeffentlich'."""
        return self.a.idx == self.ich.idx or self.a.telemetrie_oeffentlich


@dataclass(frozen=True)
class Info:
    key: str
    titel: str
    beschreibung: str
    gruppe: str
    fahrer: bool  # False = allgemeine Info, braucht keinen Fahrer
    funktion: Callable[[Ctx], "tuple[str, str] | None"]  # -> (kurzer Wert, ganzer Satzteil)


def _anzahl_runden(n: int) -> str:
    return "eine Runde" if n == 1 else f"{n} Runden"


# --- Platz und Abstand -----------------------------------------------------
def _position(c: Ctx):
    return f"Platz {c.a.position}", f"Platz {c.a.position}"


def _abstand_vorne(c: Ctx):
    a = c.a
    if a.position == 1:
        return "führt", "führt das Rennen"
    if a.delta_vorne_ms <= 0:
        return None
    s = f.zeitspanne(c.t, a.delta_vorne_ms)
    return s, f"{s} hinter dem Vordermann"


def _abstand_fuehrender(c: Ctx):
    a, z = c.a, c.z
    if a.position == 1:
        return "führt", "führt das Rennen"
    fuehrer = z.fuehrender()
    s = f.abstand(c.t, z, a, fuehrer) if fuehrer else None
    return (s, f"{s} Rückstand auf den Führenden") if s else None


def _abstand_zu_mir(c: Ctx):
    if c.a.idx == c.ich.idx:
        return None
    s = f.abstand(c.t, c.z, c.a, c.ich)
    if not s:
        return None
    return s, f"{s} {'vor' if c.a.position < c.ich.position else 'hinter'} dir"


def _startplatz(c: Ctx):
    a = c.a
    if not a.startplatz:
        return None
    diff = a.startplatz - a.position
    if diff > 0:
        zusatz = f", {'einen Platz' if diff == 1 else f'{diff} Plätze'} gutgemacht"
    elif diff < 0:
        zusatz = f", {'einen Platz' if diff == -1 else f'{-diff} Plätze'} verloren"
    else:
        zusatz = ", auf dem Startplatz"
    return f"Platz {a.startplatz}", f"Start von Platz {a.startplatz}{zusatz}"


def _tempo_zu_mir(c: Ctx):
    if c.a.idx == c.ich.idx:
        return None
    d = analyse.tempo_unterschied(c.ich, c.a)
    if d is None:
        return None
    ms = d[0]  # positiv: ich bin langsamer
    if abs(ms) < 50:
        return "gleich schnell", "gleich schnell wie du"
    s = f"{f.komma(abs(ms) / 1000)} Sekunden pro Runde {'schneller' if ms > 0 else 'langsamer'}"
    return s, f"{s} als du"


# --- Reifen ---------------------------------------------------------------
def _reifen(c: Ctx):
    a = c.a
    if not a.status_bekannt:
        return None
    return a.reifen_name, f"Reifen {a.reifen_name}"


def _reifenalter(c: Ctx):
    a = c.a
    if not a.status_bekannt:
        return None
    if a.reifenalter <= 0:
        return "neu", "neue Reifen"
    return _anzahl_runden(a.reifenalter), f"Reifenalter {_anzahl_runden(a.reifenalter)}"


def _verschleiss(c: Ctx):
    a = c.a
    if not (c.oeffentlich and a.schaden_bekannt):
        return None
    wert, position = f.staerkster_verschleiss(a)
    return f"{int(wert)} Prozent", f"Verschleiß {int(wert)} Prozent, {position} am stärksten"


def _verschleiss_raeder(c: Ctx):
    a = c.a
    if not (c.oeffentlich and a.schaden_bekannt):
        return None
    hl, hr, vl, vr = (int(v) for v in a.reifenverschleiss)
    s = f"vorne links {vl}, vorne rechts {vr}, hinten links {hl}, hinten rechts {hr}"
    return f"{s} Prozent", f"Verschleiß {s} Prozent"


def _reifenfolge(c: Ctx):
    namen = [k.reifen(s.visuell)["name"] for s in c.a.stints]
    if not namen:
        return None
    s = ", ".join(namen)
    return s, f"bisherige Reifen {s}"


def _reifentemperatur(c: Ctx):
    a = c.a
    if not (c.oeffentlich and a.telemetrie_bekannt and any(a.reifen_temp_innen)):
        return None
    grad = round(statistics.mean(a.reifen_temp_innen))
    return f"{grad} Grad", f"Reifentemperatur {grad} Grad"


# --- Boxenstopps -------------------------------------------------------------
def _stopps(c: Ctx):
    n = c.a.boxenstopps_anzahl
    text = "kein Boxenstopp" if n == 0 else "ein Boxenstopp" if n == 1 else f"{n} Boxenstopps"
    return text, text


def _in_box(c: Ctx):
    if c.a.in_box:
        return "ja", "gerade in der Box"
    return "nein", "auf der Strecke"


# --- Zeiten ------------------------------------------------------------------
def _rundenzeit_letzte(c: Ctx):
    if c.a.letzte_runde_ms <= 0:
        return None
    s = f.rundenzeit(c.a.letzte_runde_ms)
    return s, f"letzte Runde {s}"


def _rundenzeit_beste(c: Ctx):
    if c.a.beste_runde_ms <= 0:
        return None
    s = f.rundenzeit(c.a.beste_runde_ms)
    return s, f"beste Runde {s}"


def _runde(c: Ctx):
    a, z = c.a, c.z
    if a.runde <= 0:
        return None
    gesamt = f" von {z.runden_gesamt}" if z.ist_rennen and z.runden_gesamt else ""
    return f"Runde {a.runde}", f"Runde {a.runde}{gesamt}"


# --- Strafen und Schaden -----------------------------------------------------
def _strafen(c: Ctx):
    a = c.a
    teile = []
    if a.strafen_s > 0:
        teile.append(f"{a.strafen_s} Sekunden Strafe")
    if a.offene_durchfahrt:
        teile.append("eine offene Durchfahrtsstrafe")
    if a.offene_stop_go:
        teile.append("eine offene Stop-and-Go-Strafe")
    if not teile:
        return "keine", "keine Strafe"
    s = " und ".join(teile)
    return s, s


def _verwarnungen(c: Ctx):
    n = c.a.verwarnungen
    if n == 0:
        return "keine", "keine Verwarnungen"
    return f"{n} Verwarnung{'en' if n != 1 else ''}", (
        f"{n} Verwarnung{'en' if n != 1 else ''}, davon {c.a.track_limits} für Track Limits")


def _schaden(c: Ctx):
    a = c.a
    if not (c.oeffentlich and a.schaden_bekannt):
        return None
    teile = [("Frontflügel links", a.fluegel_vl), ("Frontflügel rechts", a.fluegel_vr),
             ("Heckflügel", a.heckfluegel), ("Unterboden", a.unterboden),
             ("Diffusor", a.diffusor), ("Seitenkasten", a.seitenkasten)]
    liste = ", ".join(f"{name} {wert} Prozent" for name, wert in teile if wert > 0)
    if not liste:
        return "keiner", "kein Schaden"
    return liste, f"Schaden: {liste}"


# --- Auto --------------------------------------------------------------------
def _sprit(c: Ctx):
    a = c.a
    if not a.status_bekannt:
        return None
    r = a.sprit_runden
    s = f"{f.komma(abs(r))} Runden {'Reserve' if r >= 0 else 'zu wenig'}"
    return s, f"Sprit {s}"


def _ers(c: Ctx):
    a = c.a
    if not a.status_bekannt:
        return None
    prozent = round(min(a.ers_energie / ERS_MAX_J, 1.0) * 100)
    return f"{prozent} Prozent", f"ERS {prozent} Prozent"


def _bremsentemperatur(c: Ctx):
    a = c.a
    if not (c.oeffentlich and a.telemetrie_bekannt and any(a.bremsen_temp)):
        return None
    grad = round(statistics.mean(a.bremsen_temp))
    return f"{grad} Grad", f"Bremsen {grad} Grad"


def _team(c: Ctx):
    return c.a.team, f"Team {c.a.team}"


# --- Allgemein ---------------------------------------------------------------
def _wetter(c: Ctx):
    z = c.z
    art = f.wetter_art(z.wetter)
    return art, f"Wetter {art}, Strecke {z.streckentemperatur} Grad, Luft {z.lufttemperatur} Grad"


def _regen(c: Ctx):
    z = c.z
    if k.ist_regen(z.wetter):
        trocken = z.minuten_bis_trocken()
        if trocken is None or trocken[0] <= 0:
            return "bleibt nass", "Es regnet und bleibt vorerst nass"
        return f"trocken in {trocken[0]} Minuten", f"Es regnet, in etwa {trocken[0]} Minuten wird es trocken"
    regen = z.minuten_bis_regen()
    if regen is None:
        return "kein Regen", "Kein Regen in Sicht"
    if regen[0] <= 0:
        return "gleich", "Regen setzt jeden Moment ein"
    return f"in {regen[0]} Minuten", f"Regen in etwa {regen[0]} Minuten"


def _runden_rest(c: Ctx):
    z = c.z
    if not (z.ist_rennen and z.runden_gesamt):
        return None
    rest = max(z.runden_gesamt - c.ich.runde, 0)
    return (_anzahl_runden(rest) if rest else "keine"), (
        "Das ist die letzte Runde" if rest == 0 else f"Noch {_anzahl_runden(rest)}")


def _safety_car(c: Ctx):
    z = c.z
    if z.rote_flagge:
        return "rote Flagge", "Rote Flagge"
    name = {0: "Strecke frei", 1: "Safety Car", 2: "Virtuelles Safety Car",
            3: "Einführungsrunde"}.get(z.safety_car, "Strecke frei")
    return name, name


def _strecke(c: Ctx):
    return c.z.strecke, f"Strecke {c.z.strecke}"


def _boxenfenster(c: Ctx):
    z = c.z
    if z.boxenfenster_ideal <= 0:
        return None
    spaet = max(z.boxenfenster_spaetestens, z.boxenfenster_ideal)
    return f"Runde {z.boxenfenster_ideal} bis {spaet}", f"Boxenfenster Runde {z.boxenfenster_ideal} bis {spaet}"


def _boxenverlust(c: Ctx):
    v = analyse.boxenverlust(c.z, c.verlust_standard)
    s = f"{f.komma(v.ms / 1000)} Sekunden"
    return s, f"Ein Stopp kostet etwa {s}"


def _rueckkehrplatz(c: Ctx):
    if not c.ich.im_rennen:
        return None
    r = analyse.rueckkehr(c.z, c.ich, analyse.boxenverlust(c.z, c.verlust_standard).ms)
    return f"Platz {r.position}", f"Nach einem Stopp jetzt Platz {r.position}"


def _ausgefallen(c: Ctx):
    raus = [a.anzeigename for a in c.z.gueltige_autos() if a.result_status in (4, 5, 6, 7)]
    if not raus:
        return "niemand", "bisher niemand ausgefallen"
    s = ", ".join(raus)
    return s, f"ausgefallen: {s}"


_I = Info
INFOS: dict[str, Info] = {i.key: i for i in [
    # Platz und Abstand
    _I("position", "Platz", "Auf welchem Platz der Fahrer liegt.", "Platz und Abstand", True, _position),
    _I("abstand_vorne", "Abstand nach vorne", "Wie viele Sekunden der Fahrer hinter seinem Vordermann liegt.",
       "Platz und Abstand", True, _abstand_vorne),
    _I("abstand_fuehrender", "Rückstand auf den Führenden", "Abstand des Fahrers zur Spitze.",
       "Platz und Abstand", True, _abstand_fuehrender),
    _I("abstand_zu_mir", "Abstand zu dir", "Wie weit der Fahrer vor oder hinter dir liegt.",
       "Platz und Abstand", True, _abstand_zu_mir),
    _I("startplatz", "Startplatz und Plätze", "Von wo er gestartet ist und wie viele Plätze er gewonnen oder verloren hat.",
       "Platz und Abstand", True, _startplatz),
    _I("tempo_zu_mir", "Tempo gegenüber dir", "Wie viel schneller oder langsamer er pro Runde ist als du (Schätzung).",
       "Platz und Abstand", True, _tempo_zu_mir),
    # Reifen
    _I("reifen", "Reifenmischung", "Soft, Medium, Hard, Intermediate oder Regenreifen.", "Reifen", True, _reifen),
    _I("reifenalter", "Reifenalter", "Wie viele Runden die Reifen alt sind.", "Reifen", True, _reifenalter),
    _I("verschleiss", "Reifenverschleiß", "Verschleiß des am stärksten abgenutzten Reifens in Prozent.",
       "Reifen", True, _verschleiss),
    _I("verschleiss_raeder", "Verschleiß je Reifen", "Alle vier Reifen einzeln.", "Reifen", True, _verschleiss_raeder),
    _I("reifenfolge", "Bisherige Reifen", "Welche Mischungen er schon gefahren ist.", "Reifen", True, _reifenfolge),
    _I("reifentemperatur", "Reifentemperatur", "Durchschnitt der Innentemperatur der Reifen.",
       "Reifen", True, _reifentemperatur),
    # Boxenstopps
    _I("stopps", "Anzahl Boxenstopps", "Wie oft er schon an der Box war.", "Boxenstopps", True, _stopps),
    _I("in_box", "In der Box?", "Ob er gerade in der Boxengasse ist.", "Boxenstopps", True, _in_box),
    # Zeiten
    _I("rundenzeit_letzte", "Letzte Rundenzeit", "Die zuletzt gefahrene Runde.", "Zeiten", True, _rundenzeit_letzte),
    _I("rundenzeit_beste", "Beste Rundenzeit", "Seine schnellste Runde im Rennen.", "Zeiten", True, _rundenzeit_beste),
    _I("runde", "Aktuelle Runde", "In welcher Runde er gerade ist.", "Zeiten", True, _runde),
    # Strafen und Schaden
    _I("strafen", "Strafen", "Zeitstrafen und offene Durchfahrts- oder Stop-and-Go-Strafen.",
       "Strafen und Schaden", True, _strafen),
    _I("verwarnungen", "Verwarnungen", "Anzahl der Verwarnungen, davon Track Limits.",
       "Strafen und Schaden", True, _verwarnungen),
    _I("schaden", "Schaden am Auto", "Flügel, Unterboden, Diffusor und Seitenkasten in Prozent.",
       "Strafen und Schaden", True, _schaden),
    # Auto
    _I("sprit", "Sprit", "Wie viele Runden Reserve oder wie viel zu wenig.", "Auto", True, _sprit),
    _I("ers", "ERS", "Ladestand des Hybridsystems in Prozent.", "Auto", True, _ers),
    _I("bremsentemperatur", "Bremsentemperatur", "Durchschnitt der Bremsentemperaturen.",
       "Auto", True, _bremsentemperatur),
    _I("team", "Team", "Für welches Team er fährt.", "Auto", True, _team),
    # Allgemein (ohne Fahrer)
    _I("wetter", "Wetter", "Aktuelles Wetter und Temperaturen.", "Allgemein", False, _wetter),
    _I("regen", "Regen", "Ob und wann Regen kommt oder aufhört.", "Allgemein", False, _regen),
    _I("runden_rest", "Restrunden", "Wie viele Runden noch zu fahren sind.", "Allgemein", False, _runden_rest),
    _I("safety_car", "Safety Car und Flaggen", "Ob Safety Car oder rote Flagge.", "Allgemein", False, _safety_car),
    _I("strecke", "Strecke", "Name der Strecke.", "Allgemein", False, _strecke),
    _I("boxenfenster", "Boxenfenster", "Das vom Spiel vorgeschlagene Fenster.", "Allgemein", False, _boxenfenster),
    _I("boxenverlust", "Zeitverlust eines Stopps", "Gemessen an den Stopps in diesem Rennen.",
       "Allgemein", False, _boxenverlust),
    _I("rueckkehrplatz", "Platz nach einem Stopp", "Wo du herauskämst, wenn du jetzt stoppst.",
       "Allgemein", False, _rueckkehrplatz),
    _I("ausgefallen", "Ausgefallene Fahrer", "Wer schon draußen ist.", "Allgemein", False, _ausgefallen),
]}

# ==========================================================================
# Ziele: von welchem Fahrer die Infos kommen
# ==========================================================================
ZIELE = [
    {"art": "keiner", "titel": "Kein Fahrer", "parameter": None,
     "beschreibung": "Nur allgemeine Infos wie Wetter oder Restrunden."},
    {"art": "ich", "titel": "Ich", "parameter": None, "beschreibung": "Dein eigenes Auto."},
    {"art": "aus_frage", "titel": "Der Fahrer, den ich in der Frage nenne", "parameter": None,
     "beschreibung": "Zum Beispiel „… von Verstappen“, „… vom Hintermann“ oder „… Platz drei“. "
                     "Nennst du niemanden, geht es um dich."},
    {"art": "vordermann", "titel": "Der Fahrer vor mir", "parameter": None, "beschreibung": ""},
    {"art": "hintermann", "titel": "Der Fahrer hinter mir", "parameter": None, "beschreibung": ""},
    {"art": "fuehrender", "titel": "Der Führende", "parameter": None, "beschreibung": ""},
    {"art": "kumpel", "titel": "Mein Kumpel (Mitspieler)", "parameter": None,
     "beschreibung": "Der andere menschliche Fahrer."},
    {"art": "teamkollege", "titel": "Mein Teamkollege", "parameter": None, "beschreibung": ""},
    {"art": "platz", "titel": "Ein fester Platz", "parameter": "platz",
     "beschreibung": "Immer wer gerade auf diesem Platz liegt, z. B. Platz 3."},
    {"art": "name", "titel": "Ein fester Fahrer", "parameter": "name",
     "beschreibung": "Immer derselbe Fahrer, z. B. Verstappen."},
    {"art": "top", "titel": "Die ersten Fahrer", "parameter": "n",
     "beschreibung": "Die ersten N Fahrer, nacheinander aufgezählt (höchstens 10)."},
    {"art": "um_mich", "titel": "Die Fahrer um mich herum", "parameter": "n",
     "beschreibung": "N Fahrer vor und N hinter dir (höchstens 5)."},
]
ZIEL_ARTEN = {z["art"] for z in ZIELE}
LISTEN_ZIELE = ("top", "um_mich")


def infos_katalog() -> list[dict]:
    return [{"key": i.key, "titel": i.titel, "beschreibung": i.beschreibung, "gruppe": i.gruppe,
             "fahrer": i.fahrer} for i in INFOS.values()]


# ==========================================================================
# Katalog der eingebauten Befehle (fuer die Uebersicht im Browser)
# ==========================================================================
EINGEBAUT_DOKU: dict[str, dict] = {
    "abstand": {"titel": "Abstand", "fahrer": True,
                "beschreibung": "Sekunden zum Auto vor oder hinter dir, zum Führenden oder zu einem bestimmten Fahrer.",
                "beispiele": ["Wie viele Sekunden zum Auto vor mir?", "Abstand nach hinten",
                              "Rückstand auf den Führenden", "Abstand zu Verstappen"]},
    "entwicklung": {"titel": "Verloren oder gewonnen", "fahrer": True,
                    "beschreibung": "Wie viel du in den letzten Runden auf einen Fahrer verloren oder gewonnen hast.",
                    "beispiele": ["Wie viel habe ich in den letzten fünf Runden auf den Vordermann verloren?"]},
    "trend": {"titel": "Holt er auf?", "fahrer": True,
              "beschreibung": "Ob ein Fahrer aufholt oder wegzieht, und in wie vielen Runden er dran ist (Schätzung).",
              "beispiele": ["Holt der Hintermann auf?", "Wann habe ich den Vordermann eingeholt?"]},
    "wetter": {"titel": "Wetter und Regen", "fahrer": False,
               "beschreibung": "Aktuelles Wetter, wann Regen kommt oder wann es trocken wird.",
               "beispiele": ["Kommt Regen?", "Wie ist das Wetter?", "Wann wird es trocken?"]},
    "reifen": {"titel": "Reifen", "fahrer": True,
               "beschreibung": "Mischung, Alter und Verschleiß, bei dir oder einem anderen Fahrer. "
                               "Mit „wer“ oder „alle“ bekommst du eine Übersicht aller Mischungen.",
               "beispiele": ["Wie sind meine Reifen?", "Welche Reifen hat der Hintermann?",
                             "Wie ist der Reifenverschleiß von Verstappen?", "Welche Mischung fährt wer?"]},
    "haltbarkeit": {"titel": "Wie lange halten die Reifen?", "fahrer": True,
                    "beschreibung": "Hochrechnung, wie viele Runden die Reifen bis zur Verschleißgrenze noch halten.",
                    "beispiele": ["Wie lange halten meine Reifen noch?"]},
    "reifensaetze": {"titel": "Verfügbare Reifensätze", "fahrer": False,
                     "beschreibung": "Welche Reifensätze du noch hast, neu oder gebraucht.",
                     "beispiele": ["Welche Reifensätze habe ich noch?"]},
    "frisch": {"titel": "Frischeste Reifen ringsum", "fahrer": False,
               "beschreibung": "Wer in deiner Umgebung (drei Plätze vor und hinter dir) die frischesten Reifen hat.",
               "beispiele": ["Wer hat um mich herum die frischesten Reifen?"]},
    "box": {"titel": "Boxenfenster und Strategie", "fahrer": True,
            "beschreibung": "Das Boxenfenster des Spiels, und bei einem anderen Fahrer seine bisherige Strategie. "
                            "Mit „wer“ siehst du, wer noch nicht an der Box war.",
            "beispiele": ["Wann ist das Boxenfenster?", "Wie ist die Strategie von Verstappen?",
                          "War der Hintermann schon an der Box?", "Wer war noch nicht an der Box?"]},
    "rueckkehr": {"titel": "Wo komme ich nach einem Stopp raus?", "fahrer": False,
                  "beschreibung": "Platz und Abstände nach einem Stopp jetzt, gerechnet mit dem gemessenen Zeitverlust.",
                  "beispiele": ["Wo komme ich nach einem Stopp raus?"]},
    "undercut": {"titel": "Lohnt sich ein Undercut?", "fahrer": True,
                 "beschreibung": "Grobe Einschätzung, ob früheres Stoppen vor einem Gegner etwas bringt.",
                 "beispiele": ["Lohnt sich ein Undercut auf den Vordermann?"]},
    "stoppzeit": {"titel": "Was kostet ein Boxenstopp?", "fahrer": False,
                  "beschreibung": "Zeitverlust und Standzeit eines Stopps, gemessen in diesem Rennen.",
                  "beispiele": ["Wie viel Zeit kostet hier ein Boxenstopp?"]},
    "position": {"titel": "Position und Reihenfolge", "fahrer": True,
                 "beschreibung": "Auf welchem Platz du oder ein anderer Fahrer liegt, wer auf einem Platz liegt, "
                                 "die Reihenfolge der ersten fünf.",
                 "beispiele": ["Auf welchem Platz bin ich?", "Wer ist auf Position siebzehn?",
                               "Auf welchem Platz ist Leclerc?", "Wer führt?", "Wie ist die Reihenfolge?"]},
    "plaetze": {"titel": "Plätze seit dem Start", "fahrer": True,
                "beschreibung": "Wie viele Plätze du oder ein anderer Fahrer seit dem Start gewonnen oder verloren hat.",
                "beispiele": ["Wie viele Plätze habe ich seit dem Start gutgemacht?"]},
    "runden": {"titel": "Restrunden", "fahrer": False,
               "beschreibung": "Wie viele Runden noch zu fahren sind.", "beispiele": ["Wie viele Runden noch?"]},
    "sprit": {"titel": "Sprit", "fahrer": False,
              "beschreibung": "Wie viele Runden Reserve du hast.", "beispiele": ["Wie viel Sprit habe ich?"]},
    "schaden": {"titel": "Schaden", "fahrer": True,
                "beschreibung": "Schaden an deinem Auto oder, wenn öffentlich, an dem eines anderen Fahrers.",
                "beispiele": ["Habe ich einen Schaden?", "Hat der Vordermann Schaden?"]},
    "strafen": {"titel": "Strafen", "fahrer": True,
                "beschreibung": "Strafen von dir, von einem anderen Fahrer oder von allen („wer“).",
                "beispiele": ["Habe ich Strafen?", "Wer hat Strafen?", "Hat der Vordermann eine Strafe?"]},
    "verwarnungen": {"titel": "Verwarnungen und Track Limits", "fahrer": True,
                     "beschreibung": "Anzahl der Verwarnungen, davon Track Limits.",
                     "beispiele": ["Wie viele Verwarnungen für Track Limits habe ich?"]},
    "ausfall": {"titel": "Ausfälle", "fahrer": False,
                "beschreibung": "Wer schon ausgefallen ist.", "beispiele": ["Wer ist ausgefallen?"]},
    "rundenzeit": {"titel": "Rundenzeit", "fahrer": True,
                   "beschreibung": "Deine letzte und beste Runde oder die eines anderen Fahrers im Vergleich.",
                   "beispiele": ["Wie war meine Rundenzeit?", "Wie schnell war der Vordermann in der letzten Runde?"]},
    "schnellste": {"titel": "Wer ist am schnellsten?", "fahrer": False,
                   "beschreibung": "Schnellste letzte Runde im Feld und schnellste Runde des Rennens.",
                   "beispiele": ["Wer ist gerade am schnellsten?", "Wer hat die schnellste Runde?"]},
    "sektor": {"titel": "Sektoren", "fahrer": True,
               "beschreibung": "In welchem Sektor du auf einen Fahrer verlierst, oder deine Sektoren gegen deine Bestwerte.",
               "beispiele": ["In welchem Sektor verliere ich auf den Vordermann?", "Wie war mein erster Sektor?"]},
    "konstanz": {"titel": "Konstanz", "fahrer": True,
                 "beschreibung": "Wie gleichmäßig die letzten Runden waren.",
                 "beispiele": ["Wie konstant fahre ich?"]},
    "temperatur": {"titel": "Temperaturen", "fahrer": False,
                   "beschreibung": "Reifen-, Bremsen-, Motor- oder Streckentemperatur.",
                   "beispiele": ["Wie warm sind meine Reifen?", "Wie warm sind meine Bremsen?",
                                 "Wie warm ist die Strecke?"]},
    "ers": {"titel": "ERS", "fahrer": False,
            "beschreibung": "Ladestand des Hybridsystems und Einsatzmodus.", "beispiele": ["Wie viel ERS habe ich?"]},
}

FAHRER_NENNEN = [
    {"wie": "vor mir, Vordermann, nach vorne", "wen": "Der Fahrer direkt vor dir"},
    {"wie": "hinter mir, Hintermann, nach hinten", "wen": "Der Fahrer direkt hinter dir"},
    {"wie": "Führender, Spitze, Erster", "wen": "Wer vorne liegt"},
    {"wie": "Platz drei, Position 17, der Fünfte", "wen": "Wer gerade auf diesem Platz liegt"},
    {"wie": "Verstappen, Leclerc, Norris …", "wen": "Der Fahrer mit diesem Namen (Aliase unter [fahrer.aliase] in config.toml)"},
    {"wie": "Ferrari, McLaren …", "wen": "Das Auto dieses Teams, das dir am nächsten liegt"},
    {"wie": "Teamkollege", "wen": "Dein Teamkollege"},
    {"wie": "Kumpel, Mitspieler", "wen": "Der andere menschliche Fahrer"},
    {"wie": "wer, alle", "wen": "Alle Fahrer (nicht bei jedem Befehl)"},
]


def katalog_eingebaut(themen: list[tuple[str, tuple[str, ...]]]) -> list[dict]:
    """Eingebaute Befehle mit Beschreibung und Ausloesewoertern (aus fragen.THEMEN)."""
    out = []
    for name, stichwoerter in themen:
        d = EINGEBAUT_DOKU.get(name, {"titel": name, "fahrer": False, "beschreibung": "", "beispiele": []})
        out.append({"thema": name, "titel": d["titel"], "beschreibung": d["beschreibung"],
                    "beispiele": d["beispiele"], "fahrer": d["fahrer"],
                    "stichwoerter": [s.lstrip("=") for s in stichwoerter]})
    return out


# ==========================================================================
# Eigene Befehle: pruefen, speichern, auswerten
# ==========================================================================
PLATZHALTER = re.compile(r"\{([a-z_]+)\}")


def ausloeser_trifft(ausloeser: str, woerter: list[str]) -> bool:
    """Alle Woerter des Ausloesers muessen (als Wortanfang) in der Frage vorkommen."""
    teile = norm(ausloeser).split()
    return bool(teile) and all(any(w.startswith(t) for w in woerter) for t in teile)


def validiere(b: dict, andere_namen: set[str] | None = None) -> tuple[dict | None, list[str]]:
    """Prueft einen Befehl. Gibt (bereinigter Befehl, Fehlerliste) zurueck."""
    fehler: list[str] = []
    name = str(b.get("name", "")).strip()
    if not name:
        fehler.append("Gib dem Befehl einen Namen.")
    elif len(name) > 40:
        fehler.append("Der Name darf höchstens 40 Zeichen lang sein.")
    elif andere_namen and name.lower() in andere_namen:
        fehler.append(f"Einen Befehl „{name}“ gibt es schon.")

    ausloeser = []
    for a in b.get("ausloeser", []) or []:
        a = str(a).strip()
        if not a:
            continue
        if len(a) > 60:
            fehler.append(f"Der Auslöser „{a[:20]}…“ ist zu lang (höchstens 60 Zeichen).")
        elif not any(len(w) >= 3 for w in norm(a).split()):
            fehler.append(f"Der Auslöser „{a}“ braucht mindestens ein Wort mit drei Buchstaben.")
        else:
            ausloeser.append(a)
    if not ausloeser:
        fehler.append("Trag mindestens einen Auslöser ein: Wörter, bei denen der Befehl antworten soll.")
    if len(ausloeser) > 10:
        fehler.append("Höchstens 10 Auslöser pro Befehl.")

    ziel_roh = b.get("ziel") or {"art": "ich"}
    art = ziel_roh.get("art", "ich")
    ziel = {"art": art}
    if art not in ZIEL_ARTEN:
        fehler.append("Wähle aus, von welchem Fahrer die Infos kommen.")
    elif art == "platz":
        try:
            ziel["platz"] = int(ziel_roh.get("platz"))
            if not 1 <= ziel["platz"] <= 24:
                raise ValueError
        except (TypeError, ValueError):
            fehler.append("Der feste Platz muss eine Zahl von 1 bis 24 sein.")
    elif art == "name":
        ziel["name"] = str(ziel_roh.get("name", "")).strip()[:40]
        if not ziel["name"]:
            fehler.append("Gib den Namen des festen Fahrers ein.")
    elif art in LISTEN_ZIELE:
        grenze = MAX_LISTE if art == "top" else 5
        try:
            ziel["n"] = int(ziel_roh.get("n", 3))
            if not 1 <= ziel["n"] <= grenze:
                raise ValueError
        except (TypeError, ValueError):
            fehler.append(f"Die Anzahl muss eine Zahl von 1 bis {grenze} sein.")

    infos = []
    for key in b.get("infos", []) or []:
        if key not in INFOS:
            fehler.append(f"Die Info „{key}“ gibt es nicht.")
        elif key not in infos:
            infos.append(key)
    if not infos:
        fehler.append("Wähle mindestens eine Info aus, die der Befehl sagen soll.")
    if art == "keiner" and any(INFOS[i].fahrer for i in infos if i in INFOS):
        fehler.append("Für Infos zu einem Fahrer musst du ein Ziel wählen (nicht „Kein Fahrer“).")

    text = str(b.get("text", "") or "").strip()
    if len(text) > 300:
        fehler.append("Der Antworttext darf höchstens 300 Zeichen lang sein.")
    for p in PLATZHALTER.findall(text):
        if p != "name" and p not in infos:
            nebenbei = f" Wähle sie bei den Infos aus." if p in INFOS else ""
            fehler.append(f"Der Platzhalter {{{p}}} ist hier nicht verfügbar.{nebenbei}")
    if text.count("{") != text.count("}"):
        fehler.append("Im Antworttext passt eine geschweifte Klammer nicht.")

    if fehler:
        return None, list(dict.fromkeys(fehler))
    return {
        "id": str(b.get("id") or uuid.uuid4().hex[:8]),
        "name": name,
        "aktiv": bool(b.get("aktiv", True)),
        "ausloeser": ausloeser,
        "ziel": ziel,
        "infos": infos,
        "text": text,
    }, []


class EigeneBefehle:
    def __init__(self, pfad: Path | None = None):
        self.pfad = Path(pfad) if pfad else None
        self._lock = threading.RLock()
        self._liste: list[dict] = []
        self.laden()

    # --- Ablage -------------------------------------------------------
    def laden(self) -> None:
        with self._lock:
            self._liste = []
            if not self.pfad or not self.pfad.is_file():
                return
            try:
                roh = json.loads(self.pfad.read_text(encoding="utf-8"))
            except (OSError, ValueError) as e:
                log.warning("eigene_befehle.json konnte nicht gelesen werden (%s)", e)
                return
            for b in roh.get("befehle", []) if isinstance(roh, dict) else []:
                sauber, fehler = validiere(b)
                if sauber:
                    self._liste.append(sauber)
                else:
                    log.warning("Befehl %r übersprungen: %s", b.get("name"), "; ".join(fehler))

    def _schreiben(self) -> None:
        if not self.pfad:
            return
        tmp = self.pfad.with_suffix(".tmp")
        tmp.write_text(json.dumps({"befehle": self._liste}, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        tmp.replace(self.pfad)

    def liste(self) -> list[dict]:
        with self._lock:
            return copy.deepcopy(self._liste)

    def speichern(self, befehl: dict) -> tuple[dict | None, list[str]]:
        """Legt einen Befehl an oder ersetzt den mit gleicher id."""
        with self._lock:
            eigene_id = befehl.get("id")
            namen = {b["name"].lower() for b in self._liste if b["id"] != eigene_id}
            sauber, fehler = validiere(befehl, namen)
            if sauber is None:
                return None, fehler
            for i, b in enumerate(self._liste):
                if b["id"] == sauber["id"]:
                    self._liste[i] = sauber
                    break
            else:
                if len(self._liste) >= MAX_BEFEHLE:
                    return None, [f"Es sind höchstens {MAX_BEFEHLE} eigene Befehle möglich."]
                self._liste.append(sauber)
            self._schreiben()
            return copy.deepcopy(sauber), []

    def loeschen(self, befehl_id: str) -> bool:
        with self._lock:
            vorher = len(self._liste)
            self._liste = [b for b in self._liste if b["id"] != befehl_id]
            if len(self._liste) != vorher:
                self._schreiben()
                return True
            return False

    # --- Anwenden -----------------------------------------------------
    def finde(self, woerter: list[str]) -> dict | None:
        with self._lock:
            for b in self._liste:
                if b["aktiv"] and any(ausloeser_trifft(a, woerter) for a in b["ausloeser"]):
                    return copy.deepcopy(b)
        return None

    def woerter(self) -> set[str]:
        """Alle Woerter der Ausloeser (fuer die Wortliste der Spracherkennung)."""
        with self._lock:
            return {w for b in self._liste for a in b["ausloeser"] for w in norm(a).split()}

    def antwort(self, befehl: dict, fragen, ich, bezug, auto) -> str:
        return auswerten(befehl, fragen, ich, bezug, auto)


def _ziel_autos(ziel: dict, fragen, ich, bezug, auto):
    """Welche Fahrer gemeint sind. Gibt (Autos, Fehlertext oder None) zurueck."""
    z, t = fragen.z, fragen.t
    art = ziel.get("art", "ich")
    if art == "keiner":
        return [], None
    if art == "ich":
        return [ich], None
    if art == "aus_frage":
        if bezug == "unbekannt":
            return [], t.sag("antwort.kein_fahrer")
        if bezug == "vorne" and auto is None:
            return [], t.sag("antwort.niemand_vorne")
        if bezug == "hinten" and auto is None:
            return [], t.sag("antwort.niemand_hinten")
        if bezug in ("fahrer", "vorne", "hinten", "fuehrender") and auto is not None:
            return [auto], None
        return [ich], None
    if art == "vordermann":
        a = z.vordermann(ich)
        return ([a], None) if a else ([], t.sag("antwort.niemand_vorne"))
    if art == "hintermann":
        a = z.hintermann(ich)
        return ([a], None) if a else ([], t.sag("antwort.niemand_hinten"))
    if art == "fuehrender":
        a = z.fuehrender()
        return ([a], None) if a else ([], t.sag("antwort.keine_daten"))
    if art == "kumpel":
        a = fragen._kumpel()
        return ([a], None) if a else ([], t.sag("antwort.kein_mitspieler"))
    if art == "teamkollege":
        a = z.teamkollege(ich)
        return ([a], None) if a else ([], t.sag("antwort.kein_teamkollege"))
    if art == "platz":
        a = z.auto_auf_position(ziel["platz"])
        return ([a], None) if a else ([], t.sag("antwort.niemand_auf_platz", platz=ziel["platz"]))
    if art == "name":
        n = norm(ziel["name"])
        if n and n in norm(ich.name):
            return [ich], None
        a = fragen._fahrer_nach_name(n, n.split(), ich)
        return ([a], None) if a else ([], t.sag("antwort.fahrer_nicht_im_rennen", name=ziel["name"]))
    if art == "top":
        return [a for a in z.gueltige_autos() if a.position <= ziel["n"]][:MAX_LISTE], None
    if art == "um_mich":
        n = ziel["n"]
        return [a for a in z.gueltige_autos()
                if a.idx != ich.idx and abs(a.position - ich.position) <= n][:2 * n], None
    return [], t.sag("antwort.keine_daten")


def _auto_name(a, ich) -> str:
    return "Du" if a.idx == ich.idx else a.anzeigename


def auswerten(befehl: dict, fragen, ich, bezug=None, auto=None) -> str:
    """Baut die Antwort eines eigenen Befehls aus dem aktuellen Rennzustand."""
    z, t = fragen.z, fragen.t
    verlust = fragen.cfg_strategie.get("boxenstopp_verlust", 22)
    infos = [INFOS[k_] for k_ in befehl["infos"] if k_ in INFOS]
    fahrer_infos = [i for i in infos if i.fahrer]
    globale = [i for i in infos if not i.fahrer]
    autos, fehler = _ziel_autos(befehl["ziel"], fragen, ich, bezug, auto)
    if fehler and not globale:
        return fehler
    vorlage = befehl.get("text", "")
    teile: list[str] = [fehler] if fehler else []  # z. B. "Niemand vor dir", die allgemeinen Infos folgen

    def werte_von(a):
        ctx = Ctx(z, a, ich, t, verlust)
        return {i.key: i.funktion(ctx) for i in fahrer_infos}

    def fuelle(werte: dict, name: str) -> str:
        def ersatz(m):
            key = m.group(1)
            if key == "name":
                return name
            erg = werte.get(key)
            return erg[0] if erg else "keine Daten"
        return PLATZHALTER.sub(ersatz, vorlage)

    allgemein = {i.key: i.funktion(Ctx(z, ich, ich, t, verlust)) for i in globale}
    nur_ich = len(autos) == 1 and autos[0].idx == ich.idx
    segmente = []
    for a in autos:
        werte = werte_von(a)
        name = _auto_name(a, ich)
        if vorlage:
            segmente.append(fuelle({**werte, **allgemein}, name))
        else:
            saetze = [w[1] for i in fahrer_infos if (w := werte[i.key])]
            if saetze:
                text = ", ".join(saetze)
                segmente.append(text if nur_ich else f"{name}: {text}")
    if autos and not segmente:
        teile.append(t.sag("antwort.keine_daten"))
    if vorlage and not autos:
        segmente.append(fuelle(allgemein, ""))  # nur allgemeine Infos im eigenen Text
    elif not vorlage:
        # Allgemeine Infos sind ganze Saetze: mit Punkt trennen
        segmente.extend(w[1] for i in globale if (w := allgemein[i.key]))
    antwort = ". ".join(s.strip().rstrip(".") for s in segmente + teile if s and s.strip())
    return (antwort + ".") if antwort else t.sag("antwort.keine_daten")


# ==========================================================================
# Beispieldaten: damit man Befehle auch ohne laufendes Spiel bauen kann
# ==========================================================================
_DEMO = None
_DEMO_LOCK = threading.Lock()


def demo_zustand(bis_sekunden: float = 480.0):
    """Rennzustand aus einem simulierten Rennen (Runde 6 von 12)."""
    global _DEMO
    with _DEMO_LOCK:
        if _DEMO is None:
            from .auswertung import Auswertung
            from .simulator import Simulator
            from .zustand import Rennzustand

            z = Rennzustand()
            auswertung = Auswertung(z)
            for t, paket in Simulator("trocken").pakete():
                if t > bis_sekunden:
                    break
                auswertung.verarbeite(paket)
            _DEMO = z
        return _DEMO
