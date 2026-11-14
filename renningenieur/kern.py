"""Der Kern verbindet die Module: Paket -> Auswertung -> Regeln/Datenbank.

    kern = Kern(cfg, texte, stimme)
    kern.paket(udp_daten)          # fuer jedes empfangene Paket
    kern.frage("wie ist das wetter")

Der Kern kennt weder Netzwerk noch Mikrofon. Dadurch laesst er sich in
Tests direkt mit simulierten Paketen fuettern.
"""

from __future__ import annotations

from typing import Callable

from .auswertung import Auswertung, Ereignis
from .config import Texte
from .fragen import Fragen
from .regeln import Regeln
from .sprache.funk import HOCH, Funk
from .zustand import Rennzustand


class Kern:
    def __init__(self, cfg: dict, texte: Texte, stimme, datenbank=None):
        self.cfg = cfg
        self.texte = texte
        self.zustand = Rennzustand()
        self.auswertung = Auswertung(self.zustand)
        self.funk = Funk(stimme, cfg.get("sprachausgabe", {}).get("max_wartezeit", 20))
        self.regeln = Regeln(self.zustand, cfg.get("warnungen", {}), texte, self.funk)
        self.fragen = Fragen(self.zustand, cfg.get("fahrer", {}), texte, cfg.get("strategie", {}))
        self.datenbank = datenbank
        self.hoerer: list[Callable[[Ereignis], None]] = [self.regeln.ereignis]
        if datenbank is not None:
            self.hoerer.append(lambda e: datenbank.ereignis(e, self.zustand))

    def paket(self, data: bytes) -> None:
        for e in self.auswertung.verarbeite(data):
            for hoerer in self.hoerer:
                hoerer(e)

    def frage(self, text: str) -> str:
        """Beantwortet eine Frage (als Text) und spricht die Antwort."""
        antwort = self.fragen.antwort(text)
        self.funk.sagen(antwort, HOCH, haltbar=30)
        return antwort
