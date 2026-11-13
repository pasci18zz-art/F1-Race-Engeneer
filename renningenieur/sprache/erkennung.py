"""Spracherkennung mit Vosk (laeuft komplett lokal, ohne Internet).

Erkannt wird erst nach dem Loslassen der Funktaste, und nur die wenigen
Sekunden der Aufnahme. Waehrend der Fahrt braucht die Erkennung also keine
Rechenzeit.

Eine andere Erkennung laesst sich einbauen, indem man eine Klasse mit
derselben Methode erkennen(pcm, samplerate) -> str schreibt.
"""

from __future__ import annotations

import json
import logging
import urllib.request
import zipfile
from pathlib import Path

log = logging.getLogger(__name__)

MODELL_NAME = "vosk-model-small-de-0.15"
MODELL_URL = f"https://alphacephei.com/vosk/models/{MODELL_NAME}.zip"


class Erkennung:
    def __init__(self, modellpfad: str, wortliste: list[str] | None = None):
        from vosk import KaldiRecognizer, Model, SetLogLevel

        if not Path(modellpfad).is_dir():
            raise FileNotFoundError(
                f"Vosk-Modell nicht gefunden: {modellpfad}. "
                f"Herunterladen mit: python -m renningenieur modell")
        SetLogLevel(-1)
        self._KaldiRecognizer = KaldiRecognizer
        self._modell = Model(modellpfad)
        # "[unk]" faengt alles auf, was nicht in der Wortliste steht
        self._grammatik = (json.dumps(sorted(set(wortliste)) + ["[unk]"], ensure_ascii=False)
                           if wortliste else None)

    def erkennen(self, pcm: bytes, samplerate: int) -> str:
        """PCM (Mono, 16 Bit) -> erkannter Text in Kleinbuchstaben."""
        if not pcm:
            return ""
        if self._grammatik:
            rec = self._KaldiRecognizer(self._modell, samplerate, self._grammatik)
        else:
            rec = self._KaldiRecognizer(self._modell, samplerate)
        schritt = 8000
        for i in range(0, len(pcm), schritt):
            rec.AcceptWaveform(pcm[i : i + schritt])
        text = json.loads(rec.FinalResult()).get("text", "")
        return text.replace("[unk]", " ").strip()


def modell_laden(ordner: Path, ausgabe=print) -> Path:
    """Laedt das kleine deutsche Vosk-Modell herunter (ca. 45 MB, einmalig)."""
    ziel = ordner / MODELL_NAME
    if ziel.is_dir():
        ausgabe(f"Modell ist schon da: {ziel}")
        return ziel
    ordner.mkdir(parents=True, exist_ok=True)
    zip_pfad = ordner / (MODELL_NAME + ".zip")
    ausgabe(f"Lade {MODELL_URL} ...")
    urllib.request.urlretrieve(MODELL_URL, zip_pfad)
    ausgabe("Entpacke ...")
    with zipfile.ZipFile(zip_pfad) as z:
        z.extractall(ordner)
    zip_pfad.unlink()
    ausgabe(f"Fertig: {ziel}")
    return ziel
