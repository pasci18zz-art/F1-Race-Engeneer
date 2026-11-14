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
import unicodedata

from . import formulierung as f
from .config import Texte
from .telemetrie import konstanten as k
from .zustand import Auto, Rennzustand


def norm(text: str) -> str:
    """ "Hülkenberg!" -> "hulkenberg" """
    text = text.lower().replace("ß", "ss")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


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
THEMEN: list[tuple[str, tuple[str, ...]]] = [
    ("entwicklung", ("verlor", "gewonn", "aufgeholt", "gutgemacht", "verlier", "gewinn",
                     "eingebuss", "hole ich", "holt er", "holt sie")),
    ("wetter", ("wetter", "regen", "regn", "trocken", "nass", "schauer", "gewitter")),
    ("strafen", ("straf", "verwarnung")),
    ("sprit", ("sprit", "benzin", "kraftstoff", "tank")),
    ("schaden", ("schaden", "schaden", "flugel", "beschadig", "kaputt", "unterboden")),
    ("box", ("boxenfenster", "boxenstopp", "boxen", "box", "stopp", "strategie",
             "reinkommen", "rein kommen", "wechseln")),
    ("reifen", ("reifen", "mischung", "gummi", "verschleiss", "abnutzung")),
    ("rundenzeit", ("rundenzeit", "schnellste runde", "beste runde", "letzte runde",
                    "meine zeit")),
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
]


class Fragen:
    def __init__(self, zustand: Rennzustand, cfg_fahrer: dict, texte: Texte):
        self.z = zustand
        self.t = texte
        self.kumpel_name = norm(cfg_fahrer.get("kumpel", ""))
        # Alias (vereinheitlicht) -> Fahrername (vereinheitlicht)
        self.aliase: dict[str, str] = {}
        for fahrer, liste in cfg_fahrer.get("aliase", {}).items():
            for alias in [fahrer, *liste]:
                self.aliase[norm(alias)] = norm(fahrer)

    # ------------------------------------------------------------------
    def antwort(self, frage: str) -> str:
        text = norm(frage)
        if not text:
            return self.t.sag("antwort.nicht_verstanden")
        woerter = text.split()
        thema = self._thema(text, woerter)
        with self.z.lock:
            ich = self.z.spieler
            if ich is None:
                return self.t.sag("antwort.keine_daten")
            bezug, auto = self._bezug(text, woerter, ich)
            if thema is None:
                if bezug in ("vorne", "hinten", "fuehrender", "fahrer"):
                    thema = "abstand"  # "Was ist mit Verstappen?" -> Abstand
                else:
                    return self.t.sag("antwort.nicht_verstanden")
            methode = getattr(self, "_antwort_" + thema)
            antwort = methode(text, woerter, ich, bezug, auto)
        return antwort or self.t.sag("antwort.keine_daten")

    def thema(self, frage: str) -> str | None:
        text = norm(frage)
        return self._thema(text, text.split())

    @staticmethod
    def _hat(text: str, woerter: list[str], stichwoerter: tuple[str, ...]) -> bool:
        for s in stichwoerter:
            if " " in s:
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

    def _antwort_schaden(self, text, woerter, ich, bezug, auto) -> str:
        if not ich.schaden_bekannt:
            return ""
        teile = [
            ("Frontflügel links", ich.fluegel_vl), ("Frontflügel rechts", ich.fluegel_vr),
            ("Heckflügel", ich.heckfluegel), ("Unterboden", ich.unterboden),
            ("Diffusor", ich.diffusor), ("Seitenkasten", ich.seitenkasten),
        ]
        liste = ", ".join(f"{name} {wert} Prozent" for name, wert in teile if wert > 0)
        if not liste:
            return self.t.sag("antwort.kein_schaden")
        return self.t.sag("antwort.schaden", liste=liste)

    def _antwort_strafen(self, text, woerter, ich, bezug, auto) -> str:
        if ich.strafen_s > 0:
            return self.t.sag("antwort.strafen", sekunden=ich.strafen_s)
        return self.t.sag("antwort.keine_strafen")

    def _antwort_rundenzeit(self, text, woerter, ich, bezug, auto) -> str:
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
        for team in k.TEAMS.values():
            woerter.update(team["name"].lower().split())
        return sorted(woerter)
