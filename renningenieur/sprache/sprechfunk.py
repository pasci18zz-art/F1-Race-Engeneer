"""Sprechfunk: Funktaste -> Mikrofon -> Erkennung -> Frage an den Kern.

Fehlt etwas (Paket nicht installiert, kein Modell, kein Mikrofon), wird das
gemeldet und das Programm laeuft ohne Spracheingabe weiter. Fragen lassen
sich dann immer noch im Programmfenster oder auf der Tablet-Seite tippen.
"""

from __future__ import annotations

import logging
import threading

from .funktaste import Funktaste

log = logging.getLogger(__name__)


class Sprechfunk:
    def __init__(self, kern, cfg: dict, ordner):
        self.kern = kern
        self.cfg = cfg
        self.ordner = ordner
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
            from .erkennung import Erkennung
            from .mikrofon import Mikrofon

            modell = self.ordner / cfg_stt.get("modell", "modelle/vosk-model-small-de-0.15")
            wortliste = self.kern.fragen.wortliste() if cfg_stt.get("wortliste") else None
            self.erkennung = Erkennung(str(modell), wortliste)
            m = self.cfg.get("mikrofon", {})
            self.mikrofon = Mikrofon(m.get("geraet", ""), m.get("vorlauf_sekunden", 0.5),
                                     m.get("nachlauf_sekunden", 0.3), m.get("max_sekunden", 10))
            self.mikrofon.start()
        except ImportError as e:
            log.warning("Spracheingabe aus: Paket fehlt (%s). Installieren mit: "
                        "pip install -r requirements.txt", e.name)
            return False
        except Exception as e:
            log.warning("Spracheingabe aus: %s", e)
            return False
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
            try:
                pcm = self.mikrofon.aufnahme_stopp()
                text = self.erkennung.erkennen(pcm, self.mikrofon.samplerate)
            except Exception:
                log.exception("Spracherkennung fehlgeschlagen")
                text = ""
            finally:
                self.kern.funk.stumm = False
            if not text:
                log.info("Verstanden: (nichts)")
                return
            log.info("Verstanden: %s", text)
            self.kern.frage(text)
