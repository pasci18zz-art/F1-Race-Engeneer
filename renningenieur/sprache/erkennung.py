"""Spracherkennung, komplett lokal (ohne Internet im Betrieb).

Zwei Moeglichkeiten, einstellbar in config.toml unter [spracherkennung]:

  engine = "vosk"     klein und schnell, macht aber viele Fehler
  engine = "whisper"  deutlich genauer (faster-whisper), braucht pro Frage
                      etwa 1 bis 3 Sekunden Rechenzeit auf dem Prozessor

Erkannt wird erst nach dem Loslassen der Funktaste, und nur die wenigen
Sekunden der Aufnahme. Waehrend der Fahrt braucht die Erkennung also keine
Rechenzeit.

Eine weitere Erkennung laesst sich einbauen, indem man eine Klasse mit
der Methode erkennen(pcm, samplerate) -> str und dem Attribut `name`
schreibt und sie in erkennung_erzeugen() eintraegt.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.request
import zipfile
from pathlib import Path

from . import audio

log = logging.getLogger(__name__)

MODELL_NAME = "vosk-model-small-de-0.15"
MODELL_URL = f"https://alphacephei.com/vosk/models/{MODELL_NAME}.zip"

WHISPER_MODELLE = {
    "tiny": "sehr schnell, ungenau (ca. 75 MB)",
    "base": "schnell, brauchbar (ca. 145 MB)",
    "small": "empfohlen: gut und noch flott (ca. 480 MB)",
    "medium": "sehr genau, aber langsam (ca. 1,5 GB)",
}

# Saetze, die Whisper bei Stille oder Rauschen gern erfindet
_ERFUNDEN = ("untertitel", "vielen dank", "danke furs zuschauen", "tschuss", "bis zum nachsten mal")


class Erkennung:
    """Vosk."""

    name = "Vosk"

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


def whisper_prompt(namen: list[str]) -> str:
    """Hinweistext: hilft Whisper bei Fachwoertern und Fahrernamen."""
    return ("Funk an den Renningenieur in der Formel 1. Fragen zu Abstand, Reifen, Boxenstopp, "
            "Undercut, Wetter, Regen, Strafen, Rundenzeit, Sektor. Fahrer: "
            + ", ".join(namen) + ".")


class WhisperErkennung:
    """faster-whisper (OpenAI Whisper, lokal auf dem Prozessor)."""

    def __init__(self, modell: str, ordner: Path, prompt: str = "", threads: int = 4):
        from faster_whisper import WhisperModel

        self.name = f"Whisper {modell}"
        self._prompt = prompt
        self._modell = WhisperModel(modell, device="cpu", compute_type="int8",
                                    cpu_threads=int(threads), download_root=str(ordner))

    def erkennen(self, pcm: bytes, samplerate: int) -> str:
        if not pcm:
            return ""
        x = audio.auf_16k(audio.als_float(pcm), samplerate)
        segmente, _ = self._modell.transcribe(
            x, language="de", beam_size=2, temperature=0.0, vad_filter=False,
            condition_on_previous_text=False, without_timestamps=True,
            initial_prompt=self._prompt or None, no_speech_threshold=0.6,
        )
        teile = []
        for s in segmente:
            if s.no_speech_prob > 0.7 and s.avg_logprob < -1.0:
                continue  # vermutlich nur Rauschen
            teile.append(s.text)
        text = " ".join(t.strip() for t in teile).strip()
        return "" if _erfunden(text, self._prompt) else text


def _norm(text: str) -> str:
    text = text.lower().replace("ß", "ss")
    for alt, neu in (("ä", "a"), ("ö", "o"), ("ü", "u")):
        text = text.replace(alt, neu)
    return re.sub(r"[^a-z0-9 ]+", " ", text).strip()


def _erfunden(text: str, prompt: str) -> bool:
    """Erkennt typische Erfindungen: Standardsaetze oder der Hinweistext selbst."""
    n = _norm(text)
    if not n:
        return True
    if any(n.startswith(e) for e in _ERFUNDEN):
        return True
    woerter = n.split()
    if prompt and len(woerter) >= 4:
        bekannt = set(_norm(prompt).split())
        if sum(w in bekannt for w in woerter) / len(woerter) >= 0.85 and n.startswith("funk"):
            return True
    return False


def erkennung_erzeugen(cfg_stt: dict, ordner: Path, fragen=None, namen: list[str] | None = None):
    """Baut die Erkennung laut [spracherkennung]. Faellt bei Problemen auf Vosk zurueck."""
    if cfg_stt.get("engine", "vosk") == "whisper":
        try:
            return WhisperErkennung(
                cfg_stt.get("whisper_modell", "small"),
                ordner / "modelle" / "whisper",
                whisper_prompt(namen or []),
                cfg_stt.get("whisper_threads", 4),
            )
        except ImportError:
            log.warning("Whisper ist nicht installiert (whisper.bat ausführen) - nehme Vosk.")
        except Exception as e:
            log.warning("Whisper nicht verfügbar (%s) - nehme Vosk.", e)
    modell = ordner / cfg_stt.get("modell", "modelle/vosk-model-small-de-0.15")
    wortliste = fragen.wortliste() if (fragen is not None and cfg_stt.get("wortliste")) else None
    return Erkennung(str(modell), wortliste)


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
