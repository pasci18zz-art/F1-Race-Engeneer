"""Mikrofontest: aufnehmen, Pegel pruefen, anhoeren, Erkennungen vergleichen.

    mikrofontest.bat

Du sprichst einen Satz, das Programm zeigt, wie laut die Aufnahme war, und
was jede installierte Spracherkennung daraus macht. So findest du heraus,
ob das Mikrofon oder die Erkennung das Problem ist, und kannst Mikrofon,
Abstand und Lautstaerke ausprobieren, ohne ein Rennen zu fahren.
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

from . import audio
from .sprechfunk import HINWEISE

log = logging.getLogger(__name__)

BEISPIELSAETZE = [
    "Wie viele Sekunden zum Auto vor mir?",
    "Wie ist der Reifenverschleiß von Verstappen?",
    "Wo komme ich nach einem Stopp raus?",
]


def erkennungen_laden(cfg: dict, ordner: Path, fragen, ausgabe=print) -> list:
    """Alle Erkennungen, die hier laufen: Vosk und, falls vorhanden, Whisper."""
    from . import erkennung

    cfg_stt = cfg.get("spracherkennung", {})
    namen = list(cfg.get("fahrer", {}).get("aliase", {}))
    gefunden = []
    try:
        gefunden.append(erkennung.Erkennung(
            str(ordner / cfg_stt.get("modell", "modelle/vosk-model-small-de-0.15")),
            fragen.wortliste() if cfg_stt.get("wortliste") else None))
    except Exception as e:
        ausgabe(f"  (Vosk nicht verfügbar: {e})")
    modell = cfg_stt.get("whisper_modell", "small")
    ordner_w = ordner / "modelle" / "whisper"
    if cfg_stt.get("engine") == "whisper" or list(ordner_w.glob(f"models--*faster-whisper-{modell}")):
        try:
            gefunden.append(erkennung.WhisperErkennung(
                modell, ordner_w, erkennung.whisper_prompt(namen), cfg_stt.get("whisper_threads", 4)))
        except Exception as e:
            ausgabe(f"  (Whisper nicht verfügbar: {e})")
    return gefunden


def testen(cfg: dict, ordner: Path, ausgabe=print, eingabe=input, mikrofon=None,
           erkennungen: list | None = None, sekunden: float = 5.0, warten=time.sleep,
           pieps=None) -> int:
    from ..config import texte_laden
    from ..fragen import Fragen
    from ..zustand import Rennzustand

    if mikrofon is None:
        from .mikrofon import Mikrofon

        m = cfg.get("mikrofon", {})
        mikrofon = Mikrofon(m.get("geraet", ""), m.get("vorlauf_sekunden", 0.5),
                            m.get("nachlauf_sekunden", 0.5), m.get("max_sekunden", 10))
        try:
            mikrofon.start()
        except Exception as e:
            ausgabe(f"Das Mikrofon lässt sich nicht öffnen: {e}")
            ausgabe("Mit geraete.bat siehst du alle Mikrofone und trägst den Namen in config.toml ein.")
            return 1
    fragen = Fragen(Rennzustand(), cfg.get("fahrer", {}), texte_laden(ordner))
    if erkennungen is None:
        ausgabe("Lade die Spracherkennung ...")
        erkennungen = erkennungen_laden(cfg, ordner, fragen, ausgabe)
    if pieps is None:
        def pieps() -> None:
            if sys.platform == "win32":
                import winsound

                winsound.Beep(1000, 200)

    ausgabe(f"\nMikrofon: {mikrofon.name or 'Standard'} ({mikrofon.samplerate} Hz)")
    ausgabe("Erkennung: " + (", ".join(e.name for e in erkennungen) or "keine"))
    ausgabe(f"\nDie Aufnahme dauert {sekunden:.0f} Sekunden. Sprich nach dem Piepton einen Satz, z. B.:")
    for satz in BEISPIELSAETZE:
        ausgabe(f'   "{satz}"')
    nr = 0
    while True:
        antwort = eingabe("\nEnter = Aufnahme starten, q + Enter = beenden: ").strip().lower()
        if antwort.startswith("q"):
            break
        for zahl in (3, 2, 1):
            ausgabe(f"  {zahl} ...")
            warten(1)
        pieps()
        ausgabe("  >>> Jetzt sprechen!")
        mikrofon.aufnahme_start()
        warten(sekunden)
        pcm = mikrofon.aufnahme_stopp()
        ausgabe("  Aufnahme beendet.")
        rate = mikrofon.samplerate
        pegel = audio.messen(pcm, rate)
        ausgabe(f"\n  Pegel: {pegel.text()}")
        ausgabe("  Urteil: " + {"gut": "gut", "leise": "zu leise", "leer": "fast leer",
                              "uebersteuert": "übersteuert", "kurz": "zu kurz"}[pegel.urteil])
        if pegel.urteil in HINWEISE:
            ausgabe(f"  -> {HINWEISE[pegel.urteil]}")
        if pegel.urteil in ("kurz", "leer"):
            continue
        pcm2, verstaerkung = audio.aufbereiten(pcm, rate)
        nr += 1
        wav = ordner / "mikrofontest.wav"
        try:
            audio.als_wav(pcm2, rate, wav)
            ausgabe(f"  Aufnahme gespeichert (zum Anhören): {wav}")
        except OSError:
            pass
        ausgabe(f"  Aufbereitung: Verstärkung {verstaerkung:.0f} dB\n")
        for e in erkennungen:
            start = time.monotonic()
            try:
                text = e.erkennen(pcm2, rate)
            except Exception as fehler:
                ausgabe(f"  {e.name}: Fehler ({fehler})")
                continue
            dauer = time.monotonic() - start
            thema = fragen.thema(text) if text else None
            ausgabe(f"  {e.name:<14} ({dauer:.1f} s): {text or '(nichts verstanden)'}")
            ausgabe(f"  {'':<14}          Thema: {thema or 'nicht erkannt'}")
    mikrofon.stop()
    return 0
