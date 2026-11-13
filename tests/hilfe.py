"""Gemeinsame Helfer fuer die Tests."""

from __future__ import annotations

import random

from renningenieur.config import Texte, config_laden, texte_laden
from renningenieur.kern import Kern
from renningenieur.simulator import Simulator
from renningenieur.sprache.stimmen import StummeStimme


def kern_erzeugen(datenbank=None, **warnungen) -> tuple[Kern, StummeStimme]:
    cfg = config_laden()
    cfg["warnungen"].update(warnungen)
    texte = texte_laden()
    texte._zufall = random.Random(1)  # immer dieselbe Textvariante
    stimme = StummeStimme()
    return Kern(cfg, texte, stimme, datenbank), stimme


def rennen_fahren(szenario: str = "alles", fmt: int = 2025, datenbank=None, bis: float | None = None,
                  **sim_args) -> tuple[Kern, StummeStimme]:
    """Schickt ein simuliertes Rennen direkt (ohne Netzwerk) durch den Kern."""
    kern, stimme = kern_erzeugen(datenbank)
    for t, paket in Simulator(szenario, fmt=fmt, **sim_args).pakete():
        if bis is not None and t > bis:
            break
        kern.paket(paket)
    return kern, stimme


def enthaelt(texte: list[str], teil: str) -> bool:
    return any(teil in t for t in texte)
