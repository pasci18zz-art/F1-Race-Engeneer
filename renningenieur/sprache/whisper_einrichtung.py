"""Genauere Spracherkennung einrichten (whisper.bat).

Installiert faster-whisper, laedt das gewaehlte Modell, misst, wie lange
eine Erkennung auf diesem PC dauert, und stellt config.toml um.
"""

from __future__ import annotations

import logging
import subprocess
import sys
import time
from pathlib import Path

from ..config import eintraege_setzen
from .erkennung import WHISPER_MODELLE

log = logging.getLogger(__name__)


def paket_installieren(ausgabe=print) -> bool:
    try:
        import faster_whisper  # noqa: F401

        return True
    except ImportError:
        pass
    ausgabe("Installiere faster-whisper (einmalig, ein paar Minuten) ...")
    ergebnis = subprocess.run([sys.executable, "-m", "pip", "install", "faster-whisper"])
    if ergebnis.returncode != 0:
        ausgabe("faster-whisper konnte nicht installiert werden.")
        return False
    import importlib

    importlib.invalidate_caches()
    return True


def modell_waehlen(wunsch: str, eingabe=input, ausgabe=print) -> str:
    if wunsch in WHISPER_MODELLE:
        return wunsch
    ausgabe("Welches Modell? Größer = genauer, aber langsamer.")
    namen = list(WHISPER_MODELLE)
    for nr, name in enumerate(namen, start=1):
        ausgabe(f"  {nr}  {name:<7} {WHISPER_MODELLE[name]}")
    while True:
        antwort = eingabe("Nummer eingeben, nur Enter = small: ").strip()
        if not antwort:
            return "small"
        if antwort in WHISPER_MODELLE:
            return antwort
        if antwort.isdigit() and 1 <= int(antwort) <= len(namen):
            return namen[int(antwort) - 1]
        ausgabe("Diese Nummer gibt es nicht.")


def messen(modell: str, ordner: Path, threads: int):
    """Laedt das Modell (falls noetig) und misst die Dauer einer Erkennung."""
    import numpy as np
    from faster_whisper import WhisperModel

    m = WhisperModel(modell, device="cpu", compute_type="int8", cpu_threads=int(threads),
                     download_root=str(ordner))
    stille = np.zeros(16000 * 3, dtype=np.float32)
    list(m.transcribe(stille, language="de", beam_size=2)[0])  # Aufwaermen
    start = time.monotonic()
    list(m.transcribe(stille, language="de", beam_size=2)[0])
    return time.monotonic() - start


def einrichten(ordner: Path, cfg: dict, modell: str = "", eingabe=input, ausgabe=print,
               installieren=paket_installieren, messfunktion=messen) -> int:
    if not installieren(ausgabe):
        return 1
    modell = modell_waehlen(modell, eingabe, ausgabe)
    threads = cfg.get("spracherkennung", {}).get("whisper_threads", 4)
    ausgabe(f"\nLade das Modell '{modell}' ({WHISPER_MODELLE[modell]}) und teste die Geschwindigkeit ...")
    try:
        dauer = messfunktion(modell, ordner / "modelle" / "whisper", threads)
    except Exception as e:
        ausgabe(f"Das Modell konnte nicht geladen werden: {e}")
        ausgabe("Ist der PC mit dem Internet verbunden? Einmalig wird das Modell heruntergeladen.")
        return 1
    ausgabe(f"Eine Erkennung dauert auf diesem PC etwa {dauer:.1f} Sekunden.")
    if dauer > 4:
        ausgabe("Das ist langsam. Mit 'whisper.bat base' gibt es ein schnelleres Modell.")
    eintraege_setzen(ordner / "config.toml", "spracherkennung",
                     {"engine": "whisper", "whisper_modell": modell})
    ausgabe("\nEingetragen in config.toml. Beim nächsten Start von start.bat erkennt Whisper deine Fragen.")
    ausgabe("Ausprobieren ohne Rennen: mikrofontest.bat")
    ausgabe("Zurück zu Vosk: in config.toml bei [spracherkennung] engine = \"vosk\".")
    return 0
