"""Laedt config.toml und texte.toml.

Die Standardwerte liegen im Programmordner (renningenieur/standard/). Beim
ersten Start werden beide Dateien in den Arbeitsordner kopiert; dort kannst
du sie aendern. Eintraege, die in deiner Datei fehlen, kommen aus dem
Standard.
"""

from __future__ import annotations

import logging
import random
import shutil
import tomllib
from pathlib import Path

log = logging.getLogger(__name__)
STANDARD = Path(__file__).parent / "standard"


def _mischen(basis: dict, eigene: dict) -> dict:
    out = dict(basis)
    for key, wert in eigene.items():
        if isinstance(wert, dict) and isinstance(out.get(key), dict):
            out[key] = _mischen(out[key], wert)
        else:
            out[key] = wert
    return out


def _laden(name: str, ordner: Path | None, kopieren: bool) -> dict:
    with open(STANDARD / name, "rb") as f:
        daten = tomllib.load(f)
    if ordner is None:
        return daten
    eigene = ordner / name
    if not eigene.exists():
        if kopieren:
            shutil.copy(STANDARD / name, eigene)
            log.info("%s angelegt - dort kannst du alles einstellen.", eigene)
        return daten
    try:
        with open(eigene, "rb") as f:
            return _mischen(daten, tomllib.load(f))
    except tomllib.TOMLDecodeError as e:
        raise SystemExit(f"Fehler in {eigene}: {e}") from e


def config_laden(ordner: Path | None = None, kopieren: bool = False) -> dict:
    """ordner=None: nur Standardwerte (fuer Tests)."""
    cfg = _laden("config.toml", ordner, kopieren)
    # Aliase gelten als Ganzes: Standard-Aliase ergaenzen eigene nur, wenn
    # der Fahrer dort nicht vorkommt (das erledigt _mischen bereits).
    return cfg


def adressen(eintraege: list[str]) -> list[tuple[str, int]]:
    """["127.0.0.1:20778"] -> [("127.0.0.1", 20778)]"""
    out = []
    for e in eintraege:
        host, _, port = str(e).rpartition(":")
        out.append((host or "127.0.0.1", int(port)))
    return out


class Texte:
    """Zugriff auf die Sprueche: texte.sag("warnung.box_vorne", name="Norris")"""

    def __init__(self, daten: dict, zufall: random.Random | None = None):
        self._daten = daten
        self._zufall = zufall or random.Random()

    def sag(self, schluessel: str, **werte) -> str:
        bereich, _, name = schluessel.partition(".")
        varianten = self._daten.get(bereich, {}).get(name)
        if varianten is None:
            log.warning("Text %s fehlt in texte.toml", schluessel)
            return ""
        if isinstance(varianten, str):
            varianten = [varianten]
        if not varianten:
            return ""  # absichtlich stumm geschaltet
        vorlage = self._zufall.choice(varianten)
        try:
            return vorlage.format(**werte)
        except (KeyError, IndexError, ValueError) as e:
            log.warning("Text %s: Platzhalter %s gibt es hier nicht", schluessel, e)
            return ""


def texte_laden(ordner: Path | None = None, kopieren: bool = False) -> Texte:
    return Texte(_laden("texte.toml", ordner, kopieren))
