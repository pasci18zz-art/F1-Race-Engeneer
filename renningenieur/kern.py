"""Der Kern verbindet die Module: Paket -> Auswertung -> Regeln/Datenbank.

    kern = Kern(cfg, texte, stimme)
    kern.paket(udp_daten)          # fuer jedes empfangene Paket
    kern.frage("wie ist das wetter")

Der Kern kennt weder Netzwerk noch Mikrofon. Dadurch laesst er sich in
Tests direkt mit simulierten Paketen fuettern.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from . import bericht
from .auswertung import Auswertung, Ereignis
from .befehle import DATEI, EigeneBefehle
from .config import Texte
from .fragen import Fragen
from .regeln import Regeln
from .schnappschuss import schnappschuss
from .sprache.funk import HOCH, Funk
from .zustand import Rennzustand

log = logging.getLogger(__name__)


class Kern:
    def __init__(self, cfg: dict, texte: Texte, stimme, datenbank=None, ordner=None):
        self.cfg = cfg
        self.texte = texte
        self.zustand = Rennzustand()
        self.auswertung = Auswertung(self.zustand)
        sprint = cfg.get("sprint", {})
        self.auswertung.sprint_auto = bool(sprint.get("auto", True))
        self.auswertung.sprint_max_runden = int(sprint.get("max_runden", 0))
        self.funk = Funk(stimme, cfg.get("sprachausgabe", {}).get("max_wartezeit", 20))
        self.regeln = Regeln(self.zustand, cfg.get("warnungen", {}), texte, self.funk)
        self.eigene = EigeneBefehle(Path(ordner) / DATEI if ordner else None)
        self.fragen = Fragen(self.zustand, cfg.get("fahrer", {}), texte, cfg.get("strategie", {}),
                             self.eigene)
        self.datenbank = datenbank
        if datenbank is not None:
            self.auswertung.wochenende_info = datenbank.wochenende_info
        self.hoerer: list[Callable[[Ereignis], None]] = [self.regeln.ereignis]
        if datenbank is not None:
            self.hoerer.append(lambda e: datenbank.ereignis(e, self.zustand))
        export = cfg.get("export", {})
        self.export_ordner = (Path(ordner) / export.get("ordner", "exporte")
                              if ordner and export.get("aktiv", True) else None)
        self.export_training = bool(export.get("training", False))
        self.letzter_export: dict | None = None
        self._quali_teile: dict[tuple, dict] = {}  # (Saison, Wochenende, Typ) -> Daten des Teils
        self.hoerer.append(self._quali_merken)
        if self.export_ordner is not None:
            self.hoerer.append(self._auto_export)

    def _quali_merken(self, e: Ereignis) -> None:
        """Merkt sich fertige Qualifying-Teile (Q1, Q2, Q3), um sie zusammenzufassen."""
        z = self.zustand
        if e.typ == "klassifizierung" and z.ist_quali and bericht.quali_gruppe(z.session_typ):
            self._quali_teile[(z.saison_id, z.wochenende_id, z.session_typ)] = \
                schnappschuss(z, mit_runden=True)

    def quali_teile(self, aktuell: dict) -> list[dict]:
        """Alle Teile (Q1-Q3) dieses Wochenendes, nach Teil sortiert. `aktuell` ist einer davon."""
        s = aktuell["session"]
        typ = int(s.get("session_typ") or 0)
        gruppe = bericht.quali_gruppe(typ)
        if gruppe is None:
            return [aktuell]
        saison, woche = s.get("saison_id"), s.get("wochenende_id")
        teile: dict[int, dict] = {}
        typen = bericht.GRUPPEN[gruppe]["typen"]
        if self.datenbank is not None and woche:
            for t, sid in self.datenbank.wochenende_sessions(saison, woche, typen).items():
                daten = self.datenbank.session(sid)
                if daten:
                    teile[t] = daten
        for t in typen:
            if (saison, woche, t) in self._quali_teile:
                teile[t] = self._quali_teile[(saison, woche, t)]
        teile[typ] = aktuell
        return [teile[t] for t in sorted(teile)]

    def _auto_export(self, e: Ereignis) -> None:
        """Schreibt am Ende von Rennen und Qualifying den Bericht in den Export-Ordner."""
        if e.typ != "klassifizierung":
            return
        z = self.zustand
        if not (z.ist_rennen or z.ist_quali or self.export_training):
            return
        try:
            daten = schnappschuss(z, mit_runden=True)
            pfade = bericht.exportieren(daten, self.export_ordner)
            if z.ist_quali and bericht.quali_gruppe(z.session_typ):
                # Q1, Q2 und Q3 zusammen in einer Datei (bei jedem Teil aktualisiert)
                pfade["gesamt"] = bericht.exportieren_gesamt(self.quali_teile(daten), self.export_ordner)
        except Exception:
            log.exception("Bericht konnte nicht gespeichert werden")
            return
        self.letzter_export = pfade
        log.info("Bericht gespeichert: %s", pfade.get("gesamt", pfade)["txt"] if "gesamt" in pfade else pfade["txt"])

    def paket(self, data: bytes) -> None:
        for e in self.auswertung.verarbeite(data):
            for hoerer in self.hoerer:
                hoerer(e)

    def frage(self, text: str) -> str:
        """Beantwortet eine Frage (als Text) und spricht die Antwort."""
        antwort = self.fragen.antwort(text)
        self.funk.sagen(antwort, HOCH, haltbar=30)
        return antwort
