"""Fragen verstehen (Stichwoerter und Regeln, kein LLM) und beantworten.

    fragen = Fragen(zustand, cfg_fahrer, texte)
    fragen.antwort("wie viele sekunden zum auto vor mir")

Ablauf:
  1. Text vereinheitlichen (Kleinbuchstaben, Umlaute vereinfachen).
  2. Thema am Stichwort erkennen (Wetter, Abstand, Reifen, ...).
  3. Gemeinten Fahrer finden ("vor mir", "Platz drei", Name, Alias, Team).
  4. Antwort aus dem Rennzustand berechnen und mit texte.toml formulieren.

Neue Frage ergaenzen: Stichwoerter in THEMEN eintragen und eine Methode
_antwort_<thema> schreiben.
"""

from __future__ import annotations

import difflib
import re

from . import analyse
from . import formulierung as f
from .befehle import EigeneBefehle, norm
from .config import Texte
from .telemetrie import konstanten as k
from .zustand import Auto, Rennzustand


# --- Zahlen ---------------------------------------------------------------
_EINER = {
    "null": 0, "ein": 1, "eins": 1, "eine": 1, "einer": 1, "einen": 1, "zwei": 2, "zwo": 2,
    "drei": 3, "vier": 4, "funf": 5, "sechs": 6, "sieben": 7, "acht": 8, "neun": 9,
    "zehn": 10, "elf": 11, "zwolf": 12, "dreizehn": 13, "vierzehn": 14, "funfzehn": 15,
    "sechzehn": 16, "siebzehn": 17, "achtzehn": 18, "neunzehn": 19,
}
_ZEHNER = {
    "zwanzig": 20, "dreissig": 30, "vierzig": 40, "funfzig": 50, "sechzig": 60,
    "siebzig": 70, "achtzig": 80, "neunzig": 90,
}
_ORDNUNG_STAMM = {
    "erst": 1, "zweit": 2, "dritt": 3, "viert": 4, "funft": 5, "sechst": 6, "siebt": 7,
    "acht": 8, "neunt": 9, "zehnt": 10, "elft": 11, "zwolft": 12, "dreizehnt": 13,
    "vierzehnt": 14, "funfzehnt": 15, "sechzehnt": 16, "siebzehnt": 17, "achtzehnt": 18,
    "neunzehnt": 19, "zwanzigst": 20, "einundzwanzigst": 21, "zweiundzwanzigst": 22,
}


def zahl(wort: str) -> int | None:
    """Zahlwort oder Ziffern -> Zahl ("funf" -> 5, "einundzwanzig" -> 21)."""
    if wort.isdigit():
        return int(wort)
    if wort in _EINER:
        return _EINER[wort]
    if wort in _ZEHNER:
        return _ZEHNER[wort]
    m = re.fullmatch(r"([a-z]+?)und([a-z]+)", wort)
    if m and m.group(1) in _EINER and m.group(2) in _ZEHNER:
        return _EINER[m.group(1)] + _ZEHNER[m.group(2)]
    return None


def ordnungszahl(wort: str) -> int | None:
    """ "dritten" -> 3, "achter" -> 8; normale Woerter -> None."""
    for endung in ("en", "er", "es", "em", "e"):
        if wort.endswith(endung):
            stamm = wort[: -len(endung)]
            if stamm in _ORDNUNG_STAMM:
                return _ORDNUNG_STAMM[stamm]
    return None


# --- Themen: Reihenfolge = Rangfolge bei mehreren Treffern -----------------
# Ein Stichwort trifft, wenn ein Wort der Frage damit beginnt. Stichwoerter
# mit Leerzeichen muessen woertlich vorkommen. Schreibweise wie nach norm().
# Stichwoerter mit "=" am Anfang muessen exakt ein Wort sein (z. B. "=ers",
# damit "erster" nicht trifft).
THEMEN: list[tuple[str, tuple[str, ...]]] = [
    ("plaetze", ("platze", "seit dem start", "seit start", "seit beginn", "startplatz")),
    ("sektor", ("sektor",)),
    ("temperatur", ("temperatur", "warm", "heiss", "kalt", "grad")),
    ("ers", ("=ers", "batterie", "akku", "energie", "hybrid", "deploy")),
    ("verwarnungen", ("verwarnung", "warnung", "track limit", "tracklimit", "limit",
                      "abkurz", "streckenbegrenzung")),
    ("entwicklung", ("verlor", "gewonn", "aufgeholt", "gutgemacht", "verlier", "gewinn",
                     "eingebuss", "hole ich", "holt er", "holt sie")),
    ("trend", ("holt", "aufhol", "einhol", "eingeholt", "naher", "ranfahr", "dran")),
    ("wetter", ("wetter", "regen", "regn", "trocken", "nass", "schauer", "gewitter")),
    ("strafen", ("straf",)),
    ("sprit", ("sprit", "benzin", "kraftstoff", "tank")),
    ("schaden", ("schaden", "schaden", "flugel", "beschadig", "kaputt", "unterboden")),
    ("ausfall", ("ausgefall", "ausfall", "aufgegeben", "dnf", "wer ist raus")),
    ("undercut", ("undercut", "overcut")),
    ("rueckkehr", ("rauskomm", "raus", "wo komme", "wo lande", "rejoin")),
    ("stoppzeit", ("kostet", "dauert", "zeitverlust", "boxenverlust", "standzeit")),
    ("haltbarkeit", ("halten", "haltbar", "durchhalt", "reich")),
    ("reifensaetze", ("reifensatz", "satz", "satze", "reifen habe ich noch",
                      "reifen hab ich noch", "welche reifen noch")),
    ("frisch", ("frisch",)),
    ("box", ("boxenfenster", "boxenstopp", "boxen", "box", "stopp", "strategie",
             "reinkommen", "rein kommen", "wechseln")),
    ("reifen", ("reifen", "mischung", "gummi", "verschleiss", "abnutzung")),
    ("konstanz", ("konstan", "schnitt", "durchschnitt", "gleichmass", "streuung")),
    ("schnellste", ("schnellst",)),
    ("rundenzeit", ("rundenzeit", "schnellste runde", "beste runde", "letzte runde",
                    "meine zeit", "wie schnell")),
    ("abstand", ("abstand", "sekunden", "ruckstand", "vorsprung", "lucke", "weit",
                 "delta", "gap", "entfernt", "wo ist", "wo liegt")),
    ("runden", ("runden noch", "noch runden", "wie viele runden", "wieviele runden",
                "wie lange", "restrunden", "noch zu fahren", "welche runde",
                "welcher runde")),
    ("position", ("position", "platz", "wievielter", "wo bin ich", "wo liege ich",
                  "wo stehe ich", "reihenfolge", "rangfolge", "top", "fuhrt")),
]

# Bezuege auf andere Fahrer
_VORNE = ("vor mir", "vor uns", "vordermann", "vorder", "vorne", "vor dem ich")
_HINTEN = ("hinter mir", "hinter uns", "hintermann", "hinten", "verfolger")
_FUEHRENDER = ("fuhrend", "fuhrt", "spitze", "leader", "spitzenreiter")
_TEAMKOLLEGE = ("teamkolleg", "team kolleg")
_KUMPEL = ("kumpel", "freund", "mitspieler", "partner", "kollege", "kollegen")
_ALLE = ("alle", "wer", "feld", "jeder", "gegner", "anderen", "ubersicht")

# Beispielfragen: fuer die README und als Wortliste fuer die Spracherkennung
BEISPIELE = [
    "Kommt Regen",
    "Wie ist das Wetter",
    "Wann kommt Regen",
    "Wann wird es trocken",
    "Wie viele Sekunden zum Auto vor mir",
    "Wie groß ist der Abstand nach hinten",
    "Wie viel Rückstand habe ich auf den Führenden",
    "Wie weit ist Platz drei weg",
    "Abstand zu meinem Kumpel",
    "Abstand zum Teamkollegen",
    "Wie viel habe ich in den letzten fünf Runden auf den Vordermann verloren",
    "Wie viel habe ich in den letzten drei Runden auf den Hintermann gewonnen",
    "Wie viel habe ich in der letzten Runde auf meinen Kumpel verloren",
    "Wie sind meine Reifen",
    "Wie alt sind meine Reifen",
    "Wie hoch ist der Reifenverschleiß",
    "Welche Reifen hat der Hintermann",
    "Welche Mischung fährt der Führende",
    "Welche Mischung fährt wer",
    "Wann ist das Boxenfenster",
    "Wie ist die Strategie",
    "Auf welchem Platz bin ich",
    "Wer ist auf Position siebzehn",
    "Auf welchem Platz ist Verstappen",
    "Wer führt",
    "Wie ist die Reihenfolge",
    "Wie ist die Strategie von Verstappen",
    "War der Hintermann schon an der Box",
    "Wer war noch nicht an der Box",
    "Wie ist der Reifenverschleiß von Verstappen",
    "Wie viele Runden noch",
    "Wie viel Sprit habe ich",
    "Habe ich einen Schaden",
    "Habe ich Strafen",
    "Wie war meine Rundenzeit",
    "Holt der Hintermann auf",
    "Wann habe ich den Vordermann eingeholt",
    "Wer ist gerade am schnellsten",
    "Wer hat die schnellste Runde",
    "Wie schnell war der Vordermann in der letzten Runde",
    "In welchem Sektor verliere ich auf den Vordermann",
    "Wer ist ausgefallen",
    "Wer hat Strafen",
    "Hat der Vordermann eine Strafe",
    "Hat der Vordermann Schaden",
    "Wer hat um mich herum die frischesten Reifen",
    "Wie viele Plätze habe ich seit dem Start gutgemacht",
    "Wo komme ich nach einem Stopp raus",
    "Lohnt sich ein Undercut auf den Vordermann",
    "Wie lange halten meine Reifen noch",
    "Welche Reifensätze habe ich noch",
    "Wie viel Zeit kostet hier ein Boxenstopp",
    "Wie warm sind meine Reifen",
    "Wie warm sind meine Bremsen",
    "Wie viel ERS habe ich",
    "Wie viele Verwarnungen für Track Limits habe ich",
    "Wie konstant fahre ich",
]


class Fragen:
    def __init__(self, zustand: Rennzustand, cfg_fahrer: dict, texte: Texte,
                 cfg_strategie: dict | None = None, eigene: EigeneBefehle | None = None):
        self.z = zustand
        self.t = texte
        self.cfg_strategie = cfg_strategie or {}
        self.eigene = eigene
        self._cfg_fahrer = cfg_fahrer
        self.kumpel_name = norm(cfg_fahrer.get("kumpel", ""))
        # Alias (vereinheitlicht) -> Fahrername (vereinheitlicht)
        self.aliase: dict[str, str] = {}
        for fahrer, liste in cfg_fahrer.get("aliase", {}).items():
            for alias in [fahrer, *liste]:
                self.aliase[norm(alias)] = norm(fahrer)

    # ------------------------------------------------------------------
    def fuer_zustand(self, zustand: Rennzustand) -> "Fragen":
        """Dieselben Einstellungen und Befehle, aber auf einem anderen Rennzustand
        (z. B. den Beispieldaten fuer die Vorschau im Browser)."""
        return Fragen(zustand, self._cfg_fahrer, self.t, self.cfg_strategie, self.eigene)

    def antwort(self, frage: str) -> str:
        return self.antwort_mit_quelle(frage)[0]

    def antwort_mit_quelle(self, frage: str) -> tuple[str, tuple[str, str]]:
        """Antwort und woher sie kam: ("eigen", Name), ("eingebaut", Thema) oder ("keine", "")."""
        text = norm(frage)
        if not text:
            return self.t.sag("antwort.nicht_verstanden"), ("keine", "")
        woerter = text.split()
        eigener = self.eigene.finde(woerter) if self.eigene else None
        thema = None if eigener else self._thema(text, woerter)
        with self.z.lock:
            ich = self.z.spieler
            if ich is None:
                return self.t.sag("antwort.keine_daten"), ("keine", "")
            bezug, auto = self._bezug(text, woerter, ich)
            if eigener:
                antwort = self.eigene.antwort(eigener, self, ich, bezug, auto)
                return antwort or self.t.sag("antwort.keine_daten"), ("eigen", eigener["name"])
            if thema is None:
                if bezug in ("vorne", "hinten", "fuehrender", "fahrer"):
                    thema = "abstand"  # "Was ist mit Verstappen?" -> Abstand
                else:
                    return self.t.sag("antwort.nicht_verstanden"), ("keine", "")
            methode = getattr(self, "_antwort_" + thema)
            antwort = methode(text, woerter, ich, bezug, auto)
        return antwort or self.t.sag("antwort.keine_daten"), ("eingebaut", thema)

    def thema(self, frage: str) -> str | None:
        text = norm(frage)
        return self._thema(text, text.split())

    @staticmethod
    def _hat(text: str, woerter: list[str], stichwoerter: tuple[str, ...]) -> bool:
        for s in stichwoerter:
            if s.startswith("="):
                if s[1:] in woerter:
                    return True
            elif " " in s:
                if re.search(rf"\b{re.escape(s)}", text):
                    return True
            elif any(w.startswith(s) for w in woerter):
                return True
        return False

    def _thema(self, text: str, woerter: list[str]) -> str | None:
        for name, stichwoerter in THEMEN:
            if self._hat(text, woerter, stichwoerter):
                return name
        return None

    # --- Wen meint die Frage? -----------------------------------------
    def _bezug(self, text: str, woerter: list[str], ich: Auto) -> tuple[str | None, Auto | None]:
        """Gibt (Art, Auto) zurueck. Art: vorne, hinten, fuehrender, fahrer, alle, None."""
        z = self.z
        # "erster Sektor", "zweite Runde" meinen keinen Fahrer
        woerter = [w for i, w in enumerate(woerter)
                   if not (ordnungszahl(w) and i + 1 < len(woerter)
                           and woerter[i + 1].startswith(("sektor", "runde")))]
        text = " ".join(woerter)
        # 1. Platzangabe: "Platz drei", "Position 3", "P 3", "der Dritte"
        for i, w in enumerate(woerter):
            if w in ("platz", "position", "p") and i + 1 < len(woerter):
                n = zahl(woerter[i + 1])
                if n:
                    return self._fahrer(z.auto_auf_position(n), ich)
            m = re.fullmatch(r"p(\d{1,2})", w)
            if m:
                return self._fahrer(z.auto_auf_position(int(m.group(1))), ich)
            n = ordnungszahl(w)
            if n and w not in ("erste", "erster", "ersten", "eine", "einer", "einen", "einem",
                               "eines"):
                return self._fahrer(z.auto_auf_position(n), ich)
        # 2. Namen und Aliase
        auto = self._fahrer_nach_name(text, woerter, ich)
        if auto:
            return self._fahrer(auto, ich)
        # 3. Feste Bezuege
        if self._hat(text, woerter, _TEAMKOLLEGE):
            return self._fahrer(z.teamkollege(ich), ich)
        if self._hat(text, woerter, _KUMPEL):
            return self._fahrer(self._kumpel(), ich)
        if self._hat(text, woerter, _VORNE):
            return "vorne", z.vordermann(ich)
        if self._hat(text, woerter, _HINTEN):
            return "hinten", z.hintermann(ich)
        if self._hat(text, woerter, _FUEHRENDER) or any(
            w in ("erste", "erster", "ersten") for w in woerter
        ):
            return "fuehrender", z.fuehrender()
        if any(w in _ALLE for w in woerter):
            return "alle", None
        return None, None

    @staticmethod
    def _fahrer(auto: Auto | None, ich: Auto) -> tuple[str | None, Auto | None]:
        if auto is None:
            return "unbekannt", None
        return "fahrer", auto

    def _kumpel(self) -> Auto | None:
        z = self.z
        if self.kumpel_name:
            for a in z.gueltige_autos():
                if self.kumpel_name in norm(a.name) and a.idx != z.spieler_idx:
                    return a
        mitspieler = z.menschliche_mitspieler()
        return mitspieler[0] if mitspieler else None

    def _fahrer_nach_name(self, text: str, woerter: list[str], ich: Auto) -> Auto | None:
        z = self.z
        autos = [a for a in z.gueltige_autos() if a.idx != ich.idx]
        namen = {a.idx: norm(a.name) for a in autos}
        # Aliase aus der config.toml (laengste zuerst, damit "le clerc" vor "le" kommt)
        for alias in sorted(self.aliase, key=len, reverse=True):
            if alias and re.search(rf"\b{re.escape(alias)}\b", text):
                ziel = self.aliase[alias]
                for a in autos:
                    if ziel and ziel in namen[a.idx]:
                        return a
        # Direkter oder aehnlicher Name
        bester, beste_quote = None, 0.0
        for a in autos:
            for teil in namen[a.idx].split():
                if len(teil) < 4:
                    continue
                for w in woerter:
                    if len(w) < 4:
                        continue
                    quote = 1.0 if w == teil else difflib.SequenceMatcher(None, w, teil).ratio()
                    if quote > beste_quote:
                        bester, beste_quote = a, quote
        if bester and beste_quote >= 0.82:
            return bester
        # Teamname: das Auto dieses Teams, das mir am naechsten liegt
        for team_id, team in k.TEAMS.items():
            name = norm(team["name"])
            if len(name) >= 4 and re.search(rf"\b{re.escape(name)}\b", text):
                kandidaten = [a for a in autos if a.team_id == team_id]
                if kandidaten:
                    return min(kandidaten, key=lambda a: abs(a.position - ich.position))
        return None

    # --- Wetter -------------------------------------------------------
    def _antwort_wetter(self, text, woerter, ich, bezug, auto) -> str:
        z, t = self.z, self.t
        if not z.session_bekannt:
            return ""
        teile = [t.sag("antwort.wetter_jetzt", art=f.wetter_art(z.wetter),
                       strecke_temp=z.streckentemperatur, luft_temp=z.lufttemperatur)]
        if z.prognose_session():
            if k.ist_regen(z.wetter):
                trocken = z.minuten_bis_trocken()
                if trocken is None or trocken[0] <= 0:
                    teile.append(t.sag("antwort.bleibt_nass"))
                else:
                    teile.append(t.sag("antwort.trocken_in", minuten=trocken[0]))
            else:
                regen = z.minuten_bis_regen()
                if regen is None:
                    teile.append(t.sag("antwort.kein_regen"))
                elif regen[0] <= 0:
                    teile.append(t.sag("antwort.regen_gleich"))
                else:
                    teile.append(t.sag("antwort.regen_in", minuten=regen[0],
                                       art=f.wetter_art(regen[1]["weather"]),
                                       prozent=regen[1]["rain_percentage"]))
            if not z.prognose_genau:
                teile.append(t.sag("antwort.prognose_ungenau"))
        return " ".join(x for x in teile if x)

    # --- Abstaende ----------------------------------------------------
    def _antwort_abstand(self, text, woerter, ich, bezug, auto) -> str:
        z, t = self.z, self.t
        if bezug == "unbekannt":
            return t.sag("antwort.kein_fahrer")
        if bezug == "vorne":
            return self._abstand_vorne(ich)
        if bezug == "hinten":
            return self._abstand_hinten(ich)
        if bezug == "fuehrender":
            if ich.position == 1:
                return t.sag("antwort.du_fuehrst")
            if auto is None:
                return ""
            abstand = f.abstand(t, z, ich, auto)
            return abstand and t.sag("antwort.abstand_fuehrender", abstand=abstand,
                                     name=auto.anzeigename, platz=1)
        if bezug == "fahrer" and auto is not None:
            if auto.idx == ich.idx:
                return self._antwort_position(text, woerter, ich, bezug, auto)
            abstand = f.abstand(t, z, ich, auto)
            if abstand is None:
                return ""
            schluessel = ("abstand_fahrer_vor_dir" if auto.position < ich.position
                          else "abstand_fahrer_hinter_dir")
            return t.sag("antwort." + schluessel, name=auto.anzeigename,
                         platz=auto.position, abstand=abstand)
        # Kein Bezug genannt: beide Richtungen
        return " ".join(x for x in (self._abstand_vorne(ich), self._abstand_hinten(ich)) if x)

    def _abstand_vorne(self, ich: Auto) -> str:
        vorne = self.z.vordermann(ich)
        if vorne is None:
            return self.t.sag("antwort.niemand_vorne")
        abstand = f.abstand(self.t, self.z, ich, vorne)
        return abstand and self.t.sag("antwort.abstand_vorne", name=vorne.anzeigename,
                                      abstand=abstand, platz=vorne.position) or ""

    def _abstand_hinten(self, ich: Auto) -> str:
        hinten = self.z.hintermann(ich)
        if hinten is None:
            return self.t.sag("antwort.niemand_hinten")
        abstand = f.abstand(self.t, self.z, hinten, ich)
        return abstand and self.t.sag("antwort.abstand_hinten", name=hinten.anzeigename,
                                      abstand=abstand, platz=hinten.position) or ""

    # --- Entwicklung ueber die letzten X Runden ------------------------
    def _antwort_entwicklung(self, text, woerter, ich, bezug, auto) -> str:
        z, t = self.z, self.t
        if bezug == "unbekannt":
            return t.sag("antwort.kein_fahrer")
        if auto is None or bezug == "alle":
            auto = z.vordermann(ich) or z.hintermann(ich)
        if auto is None or auto.idx == ich.idx:
            return t.sag("antwort.kein_fahrer")
        n = self._rundenzahl(woerter)
        gemeinsam = sorted(set(ich.rundenzeiten) & set(auto.rundenzeiten))
        fenster = gemeinsam[-n:]
        if not fenster:
            return t.sag("antwort.keine_rundenzeiten", name=auto.anzeigename)
        diff = sum(ich.rundenzeiten[r] for r in fenster) - sum(auto.rundenzeiten[r] for r in fenster)
        werte = dict(runden=len(fenster), name=auto.anzeigename,
                     zeit=f.zeitspanne(t, diff), abstand="")
        if abs(diff) < 50:
            satz = t.sag("antwort.gleich_schnell", **werte)
        elif len(fenster) == 1:
            satz = t.sag("antwort.verloren_eine_runde" if diff > 0 else "antwort.gewonnen_eine_runde",
                         **werte)
        else:
            satz = t.sag("antwort.verloren" if diff > 0 else "antwort.gewonnen", **werte)
        # Boxenstopp im Fenster? (Einfahrrunde oder die Runde danach)
        runden = set(fenster)
        if any(s.runde in runden or s.runde + 1 in runden
               for a in (ich, auto) for s in a.boxenstopps):
            satz += " " + t.sag("antwort.mit_boxenstopp")
        return satz

    @staticmethod
    def _rundenzahl(woerter: list[str]) -> int:
        """ "letzten fuenf runden" -> 5, "letzte runde" -> 1, sonst 3."""
        for i, w in enumerate(woerter):
            if w.startswith("runde"):
                if i > 0:
                    n = zahl(woerter[i - 1])
                    if n and woerter[i - 1] not in ("eine", "einer", "einen", "ein"):
                        return max(1, min(n, 50))
                return 1 if w == "runde" else 3
        return 3

    # --- Reifen -------------------------------------------------------
    def _antwort_reifen(self, text, woerter, ich, bezug, auto) -> str:
        z, t = self.z, self.t
        if bezug == "unbekannt":
            return t.sag("antwort.kein_fahrer")
        if bezug == "alle":
            return self._reifen_uebersicht()
        if auto is not None and auto.idx != ich.idx:
            if not auto.status_bekannt:
                return ""
            teile = [t.sag("antwort.reifen_fahrer", name=auto.anzeigename, platz=auto.position,
                           reifen_beschreibung=f.reifenbeschreibung(t, auto))]
            if auto.schaden_bekannt and auto.telemetrie_oeffentlich and auto.max_verschleiss > 0:
                teile.append(t.sag("antwort.verschleiss_fahrer", prozent=int(auto.max_verschleiss)))
            return " ".join(x for x in teile if x)
        if not ich.status_bekannt:
            return ""
        teile = [t.sag("antwort.reifen_eigene", reifen_beschreibung=f.reifenbeschreibung(t, ich))]
        if ich.schaden_bekannt:
            hl, hr, vl, vr = (int(v) for v in ich.reifenverschleiss)
            teile.append(t.sag("antwort.verschleiss_eigene", vl=vl, vr=vr, hl=hl, hr=hr))
        return " ".join(x for x in teile if x)

    def _reifen_uebersicht(self) -> str:
        gruppen: dict[int, list[str]] = {}
        for a in self.z.gueltige_autos():
            if a.im_rennen and a.status_bekannt:
                gruppen.setdefault(a.reifen_visuell, []).append(a.anzeigename)
        reihenfolge = [16, 17, 18, 7, 8]
        teile = []
        for mischung in sorted(gruppen, key=lambda m: reihenfolge.index(m) if m in reihenfolge else 99):
            teile.append(self.t.sag("antwort.reifen_gruppe", reifen=k.reifen(mischung)["name"],
                                    namen=", ".join(gruppen[mischung])))
        return " ".join(x for x in teile if x)

    # --- Sonstiges ----------------------------------------------------
    def _antwort_position(self, text, woerter, ich, bezug, auto) -> str:
        z, t = self.z, self.t
        if bezug == "unbekannt":
            return t.sag("antwort.kein_fahrer")
        if self._hat(text, woerter, ("reihenfolge", "rangfolge", "top")):
            return self._reihenfolge(ich)
        if bezug in ("fahrer", "vorne", "hinten", "fuehrender") and auto and auto.idx != ich.idx:
            # "Wer ist auf Platz 17?" / "Wo liegt Verstappen?": Name, Platz und Abstand
            antwort = self._antwort_abstand(text, woerter, ich, "fahrer", auto)
            return antwort or t.sag("antwort.position_fahrer", name=auto.anzeigename,
                                    platz=auto.position)
        return t.sag("antwort.position", platz=ich.position, anzahl=len(z.gueltige_autos()))

    def _reihenfolge(self, ich: Auto, anzahl: int = 5) -> str:
        """Die ersten fuenf und, falls weiter hinten, der eigene Platz."""
        autos = self.z.gueltige_autos()
        teile = [self.t.sag("antwort.reihenfolge_eintrag", platz=a.position, name=a.anzeigename)
                 for a in autos[:anzahl]]
        satz = self.t.sag("antwort.reihenfolge", liste=", ".join(x for x in teile if x))
        if ich.position > anzahl:
            satz += " " + self.t.sag("antwort.position", platz=ich.position, anzahl=len(autos))
        return satz

    def _antwort_runden(self, text, woerter, ich, bezug, auto) -> str:
        z = self.z
        if not z.ist_rennen or not z.runden_gesamt:
            return ""
        rest = z.runden_gesamt - ich.runde
        if rest <= 0:
            return self.t.sag("antwort.letzte_runde")
        if rest == 1:
            return self.t.sag("antwort.noch_eine_runde", runde=ich.runde, gesamt=z.runden_gesamt)
        return self.t.sag("antwort.runden_noch", runden=rest, runde=ich.runde,
                          gesamt=z.runden_gesamt)

    def _antwort_sprit(self, text, woerter, ich, bezug, auto) -> str:
        if not ich.status_bekannt:
            return ""
        if ich.sprit_runden >= 0:
            return self.t.sag("antwort.sprit_plus", runden=f.komma(ich.sprit_runden))
        return self.t.sag("antwort.sprit_minus", runden=f.komma(-ich.sprit_runden))

    def _antwort_box(self, text, woerter, ich, bezug, auto) -> str:
        z, t = self.z, self.t
        if not z.ist_rennen:
            return ""
        if bezug == "unbekannt":
            return t.sag("antwort.kein_fahrer")
        if bezug in ("fahrer", "vorne", "hinten", "fuehrender") and auto and auto.idx != ich.idx:
            return self._strategie_fahrer(auto)
        if bezug == "alle":
            return self._box_uebersicht()
        teile = []
        if z.boxenfenster_ideal > 0:
            teile.append(t.sag("antwort.boxenfenster", ideal=z.boxenfenster_ideal,
                               spaetestens=max(z.boxenfenster_spaetestens, z.boxenfenster_ideal)))
        else:
            teile.append(t.sag("antwort.kein_boxenfenster"))
        if z.boxen_rueckkehr_position > 0:
            teile.append(t.sag("antwort.boxen_rueckkehr", platz=z.boxen_rueckkehr_position))
        return " ".join(x for x in teile if x)

    def _strategie_fahrer(self, auto: Auto) -> str:
        """Bisherige Strategie eines Fahrers: Startreifen, Wechsel, aktueller Reifen."""
        t = self.t
        if not auto.stints:
            return ""
        name = auto.anzeigename
        erster = auto.stints[0]
        teile = [t.sag("antwort.strategie_start", name=name,
                       reifen=k.reifen(erster.visuell)["name"])]
        for vorher, stint in zip(auto.stints, auto.stints[1:]):
            teile.append(t.sag("antwort.strategie_wechsel",
                               runde=vorher.end_runde or stint.start_runde,
                               reifen=k.reifen(stint.visuell)["name"]))
        stopps = auto.boxenstopps_anzahl
        if stopps == 0 and len(auto.stints) == 1:
            teile.append(t.sag("antwort.strategie_ohne_stopp", name=name))
        elif stopps == 1:
            teile.append(t.sag("antwort.strategie_ein_stopp"))
        elif stopps > 1:
            teile.append(t.sag("antwort.strategie_stopps", anzahl=stopps))
        if auto.im_rennen and auto.in_box:
            teile.append(t.sag("antwort.strategie_in_box", name=name))
        elif auto.im_rennen and auto.status_bekannt and len(auto.stints) > 1:
            teile.append(t.sag("antwort.strategie_aktuell", name=name,
                               reifen_beschreibung=f.reifenbeschreibung(t, auto)))
        elif auto.im_rennen and auto.status_bekannt and auto.reifenalter > 0:
            teile.append(t.sag("antwort.strategie_alter", alter=auto.reifenalter))
        return " ".join(x for x in teile if x)

    def _box_uebersicht(self) -> str:
        """Wer war noch nicht an der Box?"""
        ohne = [a.anzeigename for a in self.z.gueltige_autos()
                if a.im_rennen and a.boxenstopps_anzahl == 0]
        if not ohne:
            return self.t.sag("antwort.alle_gestoppt")
        return self.t.sag("antwort.ohne_stopp", namen=", ".join(ohne), anzahl=len(ohne))

    def _anderer(self, bezug, auto, ich) -> Auto | None:
        """Das gemeinte andere Auto, oder None, wenn die Frage mich selbst meint."""
        if bezug in ("fahrer", "vorne", "hinten", "fuehrender") and auto and auto.idx != ich.idx:
            return auto
        return None

    def _antwort_schaden(self, text, woerter, ich, bezug, auto) -> str:
        t = self.t
        if bezug == "unbekannt":
            return t.sag("antwort.kein_fahrer")
        anderer = self._anderer(bezug, auto, ich)
        a = anderer or ich
        if not a.schaden_bekannt or (anderer and not anderer.telemetrie_oeffentlich):
            return ""
        teile = [
            ("Frontflügel links", a.fluegel_vl), ("Frontflügel rechts", a.fluegel_vr),
            ("Heckflügel", a.heckfluegel), ("Unterboden", a.unterboden),
            ("Diffusor", a.diffusor), ("Seitenkasten", a.seitenkasten),
        ]
        liste = ", ".join(f"{name} {wert} Prozent" for name, wert in teile if wert > 0)
        if anderer:
            if not liste:
                return t.sag("antwort.kein_schaden_fahrer", name=anderer.anzeigename)
            return t.sag("antwort.schaden_fahrer", name=anderer.anzeigename, liste=liste)
        if not liste:
            return t.sag("antwort.kein_schaden")
        return t.sag("antwort.schaden", liste=liste)

    def _strafen_text(self, a: Auto) -> str:
        """ "5 Sekunden", "eine Durchfahrtsstrafe", ... oder "" """
        teile = []
        if a.strafen_s > 0:
            teile.append(self.t.sag("antwort.strafe_sekunden", sekunden=a.strafen_s))
        if a.offene_durchfahrt:
            teile.append(self.t.sag("antwort.strafe_durchfahrt_offen"))
        if a.offene_stop_go:
            teile.append(self.t.sag("antwort.strafe_stop_go_offen"))
        return " und ".join(x for x in teile if x)

    def _antwort_strafen(self, text, woerter, ich, bezug, auto) -> str:
        t = self.t
        if bezug == "unbekannt":
            return t.sag("antwort.kein_fahrer")
        if bezug == "alle":
            liste = [f"{a.anzeigename} {self._strafen_text(a)}" for a in self.z.gueltige_autos()
                     if self._strafen_text(a)]
            if not liste:
                return t.sag("antwort.niemand_strafen")
            return t.sag("antwort.strafen_liste", liste=", ".join(liste))
        anderer = self._anderer(bezug, auto, ich)
        if anderer:
            strafe = self._strafen_text(anderer)
            if not strafe:
                return t.sag("antwort.keine_strafen_fahrer", name=anderer.anzeigename)
            return t.sag("antwort.strafen_fahrer", name=anderer.anzeigename, strafe=strafe)
        strafe = self._strafen_text(ich)
        if not strafe:
            return t.sag("antwort.keine_strafen")
        return t.sag("antwort.strafen", strafe=strafe, sekunden=ich.strafen_s)

    # --- 1/2: Holt er auf? Wann bin ich dran? ------------------------
    def _antwort_trend(self, text, woerter, ich, bezug, auto) -> str:
        z, t = self.z, self.t
        if bezug == "unbekannt":
            return t.sag("antwort.kein_fahrer")
        anderer = self._anderer(bezug, auto, ich) or z.hintermann(ich)
        if anderer is None:
            return t.sag("antwort.niemand_hinten")
        diff = analyse.tempo_unterschied(ich, anderer)
        if diff is None:
            return t.sag("antwort.keine_rundenzeiten", name=anderer.anzeigename)
        ms, runden = diff  # positiv: ich bin langsamer
        abstand_ms = abs(z.rueckstand_ms(ich, anderer))
        name = anderer.anzeigename
        werte = dict(name=name, zeit=f.zeitspanne(t, abs(ms)), runden=runden,
                     abstand=f.zeitspanne(t, abstand_ms))
        if abs(ms) < 50:
            return t.sag("antwort.trend_gleich", **werte)
        rest = max(z.runden_gesamt - ich.runde, 0) if z.ist_rennen else 0
        if anderer.position > ich.position:  # er ist hinter mir
            if ms < 0:
                return t.sag("antwort.trend_ich_ziehe_weg", **werte)
            bis = abstand_ms / ms
            satz = t.sag("antwort.trend_er_holt_auf", **werte, bis=max(round(bis), 1))
        else:  # er ist vor mir
            if ms > 0:
                return t.sag("antwort.trend_er_zieht_weg", **werte)
            bis = abstand_ms / -ms
            satz = t.sag("antwort.trend_ich_hole_auf", **werte, bis=max(round(bis), 1))
        if rest and bis > rest:
            satz += " " + t.sag("antwort.trend_reicht_nicht", rest=rest)
        return satz

    # --- 3/4: Wer ist am schnellsten? Rundenzeit eines anderen --------
    def _antwort_schnellste(self, text, woerter, ich, bezug, auto) -> str:
        t = self.t
        if any(w in ("mein", "meine", "meiner", "ich") for w in woerter) and "wer" not in woerter:
            return self._antwort_rundenzeit(text, woerter, ich, None, None)
        autos = [a for a in self.z.gueltige_autos() if a.im_rennen and a.letzte_runde_ms > 0
                 and not a.in_box]
        if not autos:
            return ""
        schnell = min(autos, key=lambda a: a.letzte_runde_ms)
        teile = [t.sag("antwort.schnellste_zuletzt", name=self._name(schnell, ich),
                       zeit=f.rundenzeit(schnell.letzte_runde_ms))]
        mit_bestzeit = [a for a in self.z.gueltige_autos() if a.beste_runde_ms > 0]
        if mit_bestzeit:
            beste = min(mit_bestzeit, key=lambda a: a.beste_runde_ms)
            teile.append(t.sag("antwort.schnellste_runde", name=self._name(beste, ich),
                               zeit=f.rundenzeit(beste.beste_runde_ms)))
        return " ".join(x for x in teile if x)

    def _name(self, a: Auto, ich: Auto) -> str:
        return self.t.sag("antwort.du") if a.idx == ich.idx else a.anzeigename

    # --- 5: Sektoren --------------------------------------------------
    def _antwort_sektor(self, text, woerter, ich, bezug, auto) -> str:
        t = self.t
        if bezug == "unbekannt":
            return t.sag("antwort.kein_fahrer")
        anderer = self._anderer(bezug, auto, ich)
        if anderer is None:
            # Eigene letzte Runde gegen eigene Bestwerte
            runden = [i for r, i in sorted(ich.runden_info.items()) if i.get("s1_ms")]
            if len(runden) < 2:
                return ""
            letzte = runden[-1]
            teile = []
            for nr in (1, 2, 3):
                bestwert = min(i[f"s{nr}_ms"] for i in runden if i.get(f"s{nr}_ms"))
                diff = letzte[f"s{nr}_ms"] - bestwert
                teile.append(t.sag("antwort.sektor_eigener", nr=nr,
                                   zeit=f.komma(diff / 1000)) if diff > 50
                             else t.sag("antwort.sektor_bestwert", nr=nr))
            return t.sag("antwort.sektor_eigene_einleitung") + " " + " ".join(teile)
        sauber_ich, sauber_er = analyse.saubere_runden(ich), analyse.saubere_runden(anderer)
        runden = [r for r in sorted(set(sauber_ich) & set(sauber_er))
                  if ich.runden_info.get(r, {}).get("s1_ms")
                  and anderer.runden_info.get(r, {}).get("s1_ms")][-3:]
        if not runden:
            return t.sag("antwort.keine_rundenzeiten", name=anderer.anzeigename)
        diffs = []
        for nr in (1, 2, 3):
            schluessel = f"s{nr}_ms"
            diffs.append(sum(ich.runden_info[r][schluessel] - anderer.runden_info[r][schluessel]
                             for r in runden) / len(runden))
        teile = []
        for nr, d in enumerate(diffs, start=1):
            if d > 50:
                teile.append(t.sag("antwort.sektor_verlierst", nr=nr, zeit=f.komma(d / 1000)))
            elif d < -50:
                teile.append(t.sag("antwort.sektor_gewinnst", nr=nr, zeit=f.komma(-d / 1000)))
            else:
                teile.append(t.sag("antwort.sektor_gleich", nr=nr))
        satz = t.sag("antwort.sektor_einleitung", name=anderer.anzeigename, runden=len(runden))
        satz += " " + " ".join(x for x in teile if x)
        schlimmster = max(range(3), key=lambda i: diffs[i])
        zweiter = sorted(diffs)[-2]
        if diffs[schlimmster] > 50 and diffs[schlimmster] - zweiter > 50:
            satz += " " + t.sag("antwort.sektor_am_meisten", nr=schlimmster + 1)
        return satz

    # --- 6: Ausfaelle -------------------------------------------------
    def _antwort_ausfall(self, text, woerter, ich, bezug, auto) -> str:
        z = self.z
        erfasst = {e["idx"]: e for e in z.ausfaelle}
        teile = []
        for a in z.gueltige_autos():
            if a.result_status not in (4, 5, 6, 7) and a.idx not in erfasst:
                continue
            e = erfasst.get(a.idx)
            teile.append(f"{a.anzeigename} in Runde {e['runde']} ({e['grund']})" if e
                         else a.anzeigename)
        if not teile:
            return self.t.sag("antwort.niemand_ausgefallen")
        return self.t.sag("antwort.ausgefallen", namen=", ".join(teile), anzahl=len(teile))

    # --- 9: frischeste Reifen um mich herum ---------------------------
    def _antwort_frisch(self, text, woerter, ich, bezug, auto) -> str:
        t = self.t
        nachbarn = [a for a in self.z.gueltige_autos()
                    if a.im_rennen and a.status_bekannt and abs(a.position - ich.position) <= 3]
        if len(nachbarn) < 2:
            return ""
        frisch = min(nachbarn, key=lambda a: (a.reifenalter, abs(a.position - ich.position)))
        if frisch.idx == ich.idx:
            return t.sag("antwort.frisch_ich", reifen_beschreibung=f.reifenbeschreibung(t, ich))
        return t.sag("antwort.frisch_er", name=frisch.anzeigename, platz=frisch.position,
                     reifen_beschreibung=f.reifenbeschreibung(t, frisch),
                     eigene=f.reifenbeschreibung(t, ich), alter=ich.reifenalter)

    # --- 10: Plaetze seit dem Start -----------------------------------
    def _antwort_plaetze(self, text, woerter, ich, bezug, auto) -> str:
        t = self.t
        if bezug == "unbekannt":
            return t.sag("antwort.kein_fahrer")
        a = self._anderer(bezug, auto, ich) or ich
        if not a.startplatz:
            return ""
        diff = a.startplatz - a.position
        werte = dict(name=a.anzeigename, start=a.startplatz, platz=a.position, anzahl=abs(diff),
                     plaetze="einen Platz" if abs(diff) == 1 else f"{abs(diff)} Plätze")
        art = "gut" if diff > 0 else "verloren" if diff < 0 else "gleich"
        return t.sag(f"antwort.plaetze_{art}" + ("" if a is ich else "_fahrer"), **werte)

    # --- 11/12/15: Boxenstopp-Rechnungen -------------------------------
    def _verlust(self) -> analyse.Boxenverlust:
        return analyse.boxenverlust(self.z, self.cfg_strategie.get("boxenstopp_verlust", 22))

    def _verlust_text(self, v: analyse.Boxenverlust) -> str:
        if v.gemessen == 1:
            return self.t.sag("antwort.verlust_gemessen_einer", zeit=f.komma(v.ms / 1000))
        if v.gemessen:
            return self.t.sag("antwort.verlust_gemessen", zeit=f.komma(v.ms / 1000),
                              anzahl=v.gemessen)
        return self.t.sag("antwort.verlust_standard", zeit=f.komma(v.ms / 1000))

    def _antwort_rueckkehr(self, text, woerter, ich, bezug, auto) -> str:
        z, t = self.z, self.t
        if not z.ist_rennen or not ich.im_rennen:
            return ""
        v = self._verlust()
        r = analyse.rueckkehr(z, ich, v.ms)
        teile = [t.sag("antwort.rueckkehr_platz", platz=r.position)]
        if r.vorne:
            teile.append(t.sag("antwort.rueckkehr_vorne", name=r.vorne.anzeigename,
                               abstand=f.zeitspanne(t, r.abstand_vorne_ms)))
        if r.hinten:
            teile.append(t.sag("antwort.rueckkehr_hinten", name=r.hinten.anzeigename,
                               abstand=f.zeitspanne(t, r.abstand_hinten_ms)))
            if r.abstand_hinten_ms < 1500:
                teile.append(t.sag("antwort.rueckkehr_knapp"))
        if z.safety_car != 0:
            teile.append(t.sag("antwort.rueckkehr_safety_car"))
        teile.append(self._verlust_text(v))
        return " ".join(x for x in teile if x)

    def _antwort_stoppzeit(self, text, woerter, ich, bezug, auto) -> str:
        v = self._verlust()
        satz = self._verlust_text(v)
        if v.standzeit_ms:
            satz += " " + self.t.sag("antwort.standzeit", zeit=f.komma(v.standzeit_ms / 1000))
        return satz

    def _antwort_undercut(self, text, woerter, ich, bezug, auto) -> str:
        z, t = self.z, self.t
        if bezug == "unbekannt":
            return t.sag("antwort.kein_fahrer")
        if not z.ist_rennen:
            return ""
        ziel = self._anderer(bezug, auto, ich) or z.vordermann(ich)
        if ziel is None:
            return t.sag("antwort.niemand_vorne")
        name = ziel.anzeigename
        if ziel.in_box:
            return t.sag("antwort.undercut_in_box", name=name)
        if ziel.position > ich.position:
            return t.sag("antwort.undercut_hinter_mir", name=name)
        if ziel.reifenalter + 2 <= ich.reifenalter:
            return t.sag("antwort.undercut_frischer", name=name, sein_alter=ziel.reifenalter,
                         mein_alter=ich.reifenalter)
        abbau = analyse.reifenabbau(ziel) or analyse.reifenabbau(ich)
        if abbau is None:
            return t.sag("antwort.undercut_zu_wenig_daten")
        # Frische Reifen sind etwa um den bisherigen Abbau schneller; die
        # Aufwaermrunde kostet etwa eine halbe Sekunde.
        vorteil = max(abbau, 30) * ziel.reifenalter - 500
        abstand = abs(z.rueckstand_ms(ich, ziel))
        werte = dict(name=name, abstand=f.zeitspanne(t, abstand), alter=ziel.reifenalter,
                     vorteil=f.zeitspanne(t, max(vorteil, 0)))
        satz = t.sag("antwort.undercut_rechnung", **werte)
        if vorteil > abstand + 300:
            satz += " " + t.sag("antwort.undercut_ja")
        elif vorteil > abstand - 300:
            satz += " " + t.sag("antwort.undercut_knapp")
        else:
            satz += " " + t.sag("antwort.undercut_nein")
        r = analyse.rueckkehr(z, ich, self._verlust().ms)
        if r.vorne and r.vorne.idx != ziel.idx and r.abstand_vorne_ms < 1500:
            satz += " " + t.sag("antwort.undercut_verkehr", name=r.vorne.anzeigename)
        return satz

    # --- 13: Wie lange halten die Reifen? ------------------------------
    def _antwort_haltbarkeit(self, text, woerter, ich, bezug, auto) -> str:
        z, t = self.z, self.t
        if bezug == "unbekannt":
            return t.sag("antwort.kein_fahrer")
        a = self._anderer(bezug, auto, ich) or ich
        if a is not ich and not a.telemetrie_oeffentlich:
            return ""
        rate = analyse.verschleiss_pro_runde(a)
        if rate is None or rate <= 0:
            return ""
        grenze = self.cfg_strategie.get("reifen_grenze", 70)
        jetzt = a.max_verschleiss
        werte = dict(name=a.anzeigename, prozent=int(jetzt), rate=f.komma(rate), grenze=grenze)
        if jetzt >= grenze:
            return t.sag("antwort.haltbarkeit_ueber", **werte)
        runden = int((grenze - jetzt) / rate)
        satz = t.sag("antwort.haltbarkeit" + ("" if a is ich else "_fahrer"), **werte,
                     runden=runden)
        if z.ist_rennen and z.runden_gesamt:
            rest = max(z.runden_gesamt - a.runde + 1, 0)
            if runden >= rest:
                satz += " " + t.sag("antwort.haltbarkeit_bis_ziel")
            else:
                satz += " " + t.sag("antwort.haltbarkeit_rest", rest=rest)
        return satz

    # --- 14: Reifensaetze ---------------------------------------------
    def _antwort_reifensaetze(self, text, woerter, ich, bezug, auto) -> str:
        z, t = self.z, self.t
        if not z.reifensaetze:
            return ""
        regen = k.ist_regen(z.wetter) or z.minuten_bis_regen() is not None
        gruppen: dict[int, list[int]] = {}
        for s in z.reifensaetze:
            if not s["available"] or s["fitted"]:
                continue
            if s["visual_tyre_compound"] in k.REGENREIFEN_VISUELL and not regen:
                continue
            gruppen.setdefault(s["visual_tyre_compound"], []).append(s["wear"])
        if not gruppen:
            return t.sag("antwort.keine_reifensaetze")
        reihenfolge = [16, 17, 18, 7, 8]
        teile = []
        for mischung in sorted(gruppen, key=lambda m: reihenfolge.index(m) if m in reihenfolge else 99):
            neu = sum(1 for w in gruppen[mischung] if w == 0)
            gebraucht = sorted(w for w in gruppen[mischung] if w > 0)
            stuecke = []
            if neu:
                stuecke.append(t.sag("antwort.satz_neu", anzahl=neu))
            if gebraucht:
                stuecke.append(t.sag("antwort.satz_gebraucht", anzahl=len(gebraucht),
                                     prozent=" und ".join(str(w) for w in gebraucht)))
            teile.append(f"{k.reifen(mischung)['name']}: " + ", ".join(stuecke))
        return t.sag("antwort.reifensaetze", liste=". ".join(teile))

    # --- 16/17: Temperaturen -------------------------------------------
    def _antwort_temperatur(self, text, woerter, ich, bezug, auto) -> str:
        t = self.t
        if self._hat(text, woerter, ("strecke", "luft", "draussen", "asphalt")):
            z = self.z
            return t.sag("antwort.temperatur_strecke", strecke=z.streckentemperatur,
                         luft=z.lufttemperatur) if z.session_bekannt else ""
        if not ich.telemetrie_bekannt:
            return ""
        hl, hr, vl, vr = ich.reifen_temp_innen
        teile = []
        if self._hat(text, woerter, ("bremse",)):
            bhl, bhr, bvl, bvr = ich.bremsen_temp
            return t.sag("antwort.temperatur_bremsen", vl=bvl, vr=bvr, hl=bhl, hr=bhr)
        if self._hat(text, woerter, ("motor",)):
            return t.sag("antwort.temperatur_motor", grad=ich.motor_temp)
        teile.append(t.sag("antwort.temperatur_reifen", vl=vl, vr=vr, hl=hl, hr=hr))
        oberflaeche = ich.reifen_temp_oberflaeche
        if any(oberflaeche):
            teile.append(t.sag("antwort.temperatur_oberflaeche",
                               grad=round(sum(oberflaeche) / 4)))
        return " ".join(x for x in teile if x)

    # --- 18: ERS ------------------------------------------------------
    ERS_MAX_J = 4_000_000.0
    ERS_MODI = {0: "aus", 1: "Mittel", 2: "Hotlap", 3: "Überholen"}

    def _antwort_ers(self, text, woerter, ich, bezug, auto) -> str:
        if not ich.status_bekannt:
            return ""
        prozent = round(min(ich.ers_energie / self.ERS_MAX_J, 1.0) * 100)
        return self.t.sag("antwort.ers", prozent=prozent,
                          modus=self.ERS_MODI.get(ich.ers_modus, "unbekannt"))

    # --- 19: Verwarnungen ---------------------------------------------
    def _antwort_verwarnungen(self, text, woerter, ich, bezug, auto) -> str:
        t = self.t
        if bezug == "unbekannt":
            return t.sag("antwort.kein_fahrer")
        a = self._anderer(bezug, auto, ich) or ich
        werte = dict(name=a.anzeigename, track_limits=a.track_limits, gesamt=a.verwarnungen)
        if a.verwarnungen == 0 and a.track_limits == 0:
            return t.sag("antwort.keine_verwarnungen" + ("" if a is ich else "_fahrer"), **werte)
        return t.sag("antwort.verwarnungen" + ("" if a is ich else "_fahrer"), **werte)

    # --- 20: Konstanz -------------------------------------------------
    def _antwort_konstanz(self, text, woerter, ich, bezug, auto) -> str:
        t = self.t
        a = self._anderer(bezug, auto, ich) or ich
        werte_k = analyse.konstanz(a)
        if werte_k is None:
            return t.sag("antwort.konstanz_zu_wenig")
        schnitt, streuung, beste, langsamste, anzahl = werte_k
        urteil = ("konstanz_sehr_gut" if streuung < 250 else
                  "konstanz_ok" if streuung < 600 else "konstanz_schwankt")
        satz = t.sag("antwort.konstanz", name=a.anzeigename, runden=anzahl,
                     schnitt=f.rundenzeit(round(schnitt)), streuung=f.komma(streuung / 1000),
                     beste=f.rundenzeit(beste), langsamste=f.rundenzeit(langsamste))
        return satz + " " + t.sag("antwort." + urteil)

    def _antwort_rundenzeit(self, text, woerter, ich, bezug, auto) -> str:
        anderer = self._anderer(bezug, auto, ich)
        if anderer is not None:
            if anderer.letzte_runde_ms <= 0:
                return ""
            satz = self.t.sag("antwort.rundenzeit_fahrer", name=anderer.anzeigename,
                              zeit=f.rundenzeit(anderer.letzte_runde_ms),
                              eigene=f.rundenzeit(ich.letzte_runde_ms))
            diff = ich.letzte_runde_ms - anderer.letzte_runde_ms
            if ich.letzte_runde_ms > 0 and abs(diff) >= 50:
                satz += " " + self.t.sag(
                    "antwort.rundenzeit_er_schneller" if diff > 0 else "antwort.rundenzeit_du_schneller",
                    zeit=f.komma(abs(diff) / 1000))
            return satz
        if ich.letzte_runde_ms <= 0:
            return ""
        return self.t.sag("antwort.rundenzeit", letzte=f.rundenzeit(ich.letzte_runde_ms),
                          beste=f.rundenzeit(ich.beste_runde_ms or ich.letzte_runde_ms))

    # --- Wortliste fuer die Spracherkennung ----------------------------
    def wortliste(self) -> list[str]:
        """Alle Woerter, die in Fragen vorkommen koennen (fuer Vosk)."""
        woerter: set[str] = set()
        for satz in BEISPIELE:
            woerter.update(re.sub(r"[^a-zäöüß ]", " ", satz.lower()).split())
        woerter.update(["null", "eins", "zwei", "drei", "vier", "fünf", "sechs", "sieben", "acht",
                        "neun", "zehn", "elf", "zwölf", "dreizehn", "vierzehn", "fünfzehn",
                        "sechzehn", "siebzehn", "achtzehn", "neunzehn", "zwanzig", "dreißig",
                        "platz", "position", "ersten", "zweiten", "dritten", "vierten",
                        "fünften", "sechsten", "siebten", "achten", "neunten", "zehnten",
                        "strafe", "benzin", "verschleiß", "trocken", "vorne", "hinten",
                        "auf", "den", "dem", "der", "die", "das", "zu", "zum", "von", "ist",
                        "hat", "fährt", "abstand", "sekunden", "reifen"])
        for alias in self.aliase:
            woerter.update(alias.split())
        if self.eigene:
            woerter.update(self.eigene.woerter())
        for team in k.TEAMS.values():
            woerter.update(team["name"].lower().split())
        return sorted(woerter)
