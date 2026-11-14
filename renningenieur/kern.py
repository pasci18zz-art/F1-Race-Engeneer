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
        self.funk = Funk(stimme, cfg.get("sprachausgabe", {}).get("max_wartezeit", 20))
        self.regeln = Regeln(self.zustand, cfg.get("warnungen", {}), texte, self.funk)
        self.eigene = EigeneBefehle(Path(ordner) / DATEI if ordner else None)
        self.fragen = Fragen(self.zustand, cfg.get("fahrer", {}), texte, cfg.get("strategie", {}),
                             self.eigene)
        self.datenbank = datenbank
        self.hoerer: list[Callable[[Ereignis], None]] = [self.regeln.ereignis]
        if datenbank is not None:
            self.hoerer.append(lambda e: datenbank.ereignis(e, self.zustand))
        export = cfg.get("export", {})
        self.export_ordner = (Path(ordner) / export.get("ordner", "exporte")
                              if ordner and export.get("aktiv", True) else None)
        self.export_training = bool(export.get("training", False))
        self.letzter_export: dict | None = None
        if self.export_ordner is not None:
            self.hoerer.append(self._auto_export)

    def _auto_export(self, e: Ereignis) -> None:
        """Schreibt am Ende von Rennen und Qualifying den Bericht in den Export-Ordner."""
        if e.typ != "klassifizierung":
            return
        z = self.zustand
        if not (z.ist_rennen or z.ist_quali or self.export_training):
            return
        try:
            pfade = bericht.exportieren(schnappschuss(z, mit_runden=True), self.export_ordner)
        except Exception:
            log.exception("Bericht konnte nicht gespeichert werden")
            return
        self.letzter_export = pfade
        log.info("Bericht gespeichert: %s", pfade["txt"])

    def paket(self, data: bytes) -> None:
        for e in self.auswertung.verarbeite(data):
            for hoerer in self.hoerer:
                hoerer(e)

    def frage(self, text: str) -> str:
        """Beantwortet eine Frage (als Text) und spricht die Antwort."""
        antwort = self.fragen.antwort(text)
        self.funk.sagen(antwort, HOCH, haltbar=30)
        return antwort
