"""Sprechfunk: Funktaste -> Mikrofon -> Erkennung -> Frage an den Kern.

Fehlt etwas (Paket nicht installiert, kein Modell, kein Mikrofon), wird das
gemeldet und das Programm laeuft ohne Spracheingabe weiter. Fragen lassen
sich dann immer noch im Programmfenster oder auf der Tablet-Seite tippen.

Nach jeder Frage steht im Fenster, wie laut die Aufnahme war und was
verstanden wurde. Die Aufnahme liegt als letzte_aufnahme.wav im
Programmordner, damit man nachhoeren kann, was die Erkennung gehoert hat.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from . import audio
from .funktaste import Funktaste

log = logging.getLogger(__name__)

HINWEISE = {
    "kurz": "Aufnahme zu kurz. Taste halten, bis der Satz zu Ende ist.",
    "leer": "Fast nichts aufgenommen. Falsches Mikrofon, stummgeschaltet oder viel zu leise?",
    "leise": "Aufnahme sehr leise. Windows-Eingabelautstärke auf 100 und näher ans Mikrofon.",
    "uebersteuert": "Aufnahme übersteuert. Windows-Eingabelautstärke senken.",
}


class Sprechfunk:
    def __init__(self, kern, cfg: dict, ordner):
        self.kern = kern
        self.cfg = cfg
        self.ordner = Path(ordner)
        self.mikrofon = None
        self.erkennung = None
        self.taste: Funktaste | None = None
        self._arbeitet = threading.Lock()

    def start(self) -> bool:
        cfg_stt = self.cfg.get("spracherkennung", {})
        if not cfg_stt.get("aktiv", True):
            log.info("Spracherkennung ist in config.toml abgeschaltet.")
            return False
        try:
            from .erkennung import erkennung_erzeugen
            from .mikrofon import Mikrofon

            namen = list(self.cfg.get("fahrer", {}).get("aliase", {}))
            self.erkennung = erkennung_erzeugen(cfg_stt, self.ordner, self.kern.fragen, namen)
            m = self.cfg.get("mikrofon", {})
            self.mikrofon = Mikrofon(m.get("geraet", ""), m.get("vorlauf_sekunden", 0.5),
                                     m.get("nachlauf_sekunden", 0.5), m.get("max_sekunden", 10))
            self.mikrofon.start()
        except ImportError as e:
            log.warning("Spracheingabe aus: Paket fehlt (%s). Installieren mit: "
                        "installieren.bat", e.name)
            return False
        except Exception as e:
            log.warning("Spracheingabe aus: %s", e)
            return False
        log.info("Spracherkennung: %s", self.erkennung.name)
        self.taste = Funktaste(self.cfg.get("funktaste", {}), self._druck, self._los)
        self.taste.start()
        t = self.cfg.get("funktaste", {})
        log.info("Funktaste bereit (Tastatur: %s, Lenkradtaste: %s)",
                 t.get("tastatur") or "keine", t.get("taste", -1) if t.get("taste", -1) >= 0 else "keine")
        return True

    def stop(self) -> None:
        if self.taste:
            self.taste.stop()
        if self.mikrofon:
            self.mikrofon.stop()

    def _druck(self) -> None:
        self.kern.funk.stumm = True  # der Ingenieur redet nicht dazwischen
        self.mikrofon.aufnahme_start()

    def _los(self) -> None:
        threading.Thread(target=self._auswerten, name="erkennung", daemon=True).start()

    def _auswerten(self) -> None:
        with self._arbeitet:
            text = ""
            try:
                text = self.verstehen(self.mikrofon.aufnahme_stopp(), self.mikrofon.samplerate)
            except Exception:
                log.exception("Spracherkennung fehlgeschlagen")
            finally:
                self.kern.funk.stumm = False
            if text:
                self.kern.frage(text)
            else:
                self.kern.funk.sagen(self.kern.texte.sag("antwort.nichts_gehoert"), 2, haltbar=10)

    def verstehen(self, pcm: bytes, rate: int) -> str:
        """Aufnahme -> Text. Schreibt Pegel und Ergebnis ins Fenster."""
        pegel = audio.messen(pcm, rate)
        log.info("Aufnahme: %s", pegel.text())
        if pegel.urteil in ("kurz", "leer"):
            log.warning("%s", HINWEISE[pegel.urteil])
            return ""
        if pegel.urteil in HINWEISE:
            log.warning("%s", HINWEISE[pegel.urteil])
        pcm, verstaerkung = audio.aufbereiten(pcm, rate)
        if self.cfg.get("mikrofon", {}).get("aufnahme_speichern", True):
            try:
                audio.als_wav(pcm, rate, self.ordner / "letzte_aufnahme.wav")
            except OSError:
                pass
        start = time.monotonic()
        text = self.erkennung.erkennen(pcm, rate)
        dauer = time.monotonic() - start
        log.info("Verstanden: %s  (%s, %.1f s, Verstärkung %.0f dB)",
                 text or "(nichts)", self.erkennung.name, dauer, verstaerkung)
        return text
