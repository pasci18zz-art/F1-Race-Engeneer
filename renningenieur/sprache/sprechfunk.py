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
        self.letzter_pegel = None
        self._arbeitet = threading.Lock()

    def start(self) -> bool:
        """Laedt die Erkennung und oeffnet, je nach [mikrofon] quelle, das PC-Mikrofon.

        quelle = "pc"      nur das Mikrofon am PC (Funktaste am Lenkrad/Tastatur)
        quelle = "tablet"  nur das Mikrofon des Tablets (Taste auf der Tablet-Seite)
        quelle = "beides"  beides (Standard)
        """
        cfg_stt = self.cfg.get("spracherkennung", {})
        if not cfg_stt.get("aktiv", True):
            log.info("Spracherkennung ist in config.toml abgeschaltet.")
            return False
        try:
            from .erkennung import erkennung_erzeugen

            namen = list(self.cfg.get("fahrer", {}).get("aliase", {}))
            self.erkennung = erkennung_erzeugen(cfg_stt, self.ordner, self.kern.fragen, namen)
        except ImportError as e:
            log.warning("Spracheingabe aus: Paket fehlt (%s). Installieren mit: "
                        "installieren.bat", e.name)
            return False
        except Exception as e:
            log.warning("Spracheingabe aus: %s", e)
            return False
        log.info("Spracherkennung: %s", self.erkennung.name)
        quelle = self.cfg.get("mikrofon", {}).get("quelle", "beides")
        if quelle in ("pc", "beides"):
            self._pc_mikrofon_starten()
        else:
            log.info("Spracheingabe über das Tablet (config.toml, [mikrofon] quelle).")
        return True

    def _pc_mikrofon_starten(self) -> bool:
        try:
            from .mikrofon import Mikrofon

            m = self.cfg.get("mikrofon", {})
            self.mikrofon = Mikrofon(m.get("geraet", ""), m.get("vorlauf_sekunden", 0.5),
                                     m.get("nachlauf_sekunden", 0.5), m.get("max_sekunden", 10))
            self.mikrofon.start()
        except ImportError as e:
            log.warning("PC-Mikrofon aus: Paket fehlt (%s). Installieren mit: installieren.bat", e.name)
            return False
        except Exception as e:
            log.warning("PC-Mikrofon aus: %s", e)
            self.mikrofon = None
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

    def tablet_frage(self, pcm: bytes, rate: int) -> dict:
        """Aufnahme vom Tablet -> Erkennung -> Antwort (wird auch gesprochen).

        Gibt ein dict fuer die Tablet-Seite zurueck: ok, text, antwort, hinweis.
        """
        if self.erkennung is None:
            return {"ok": False, "fehler": "Die Spracherkennung läuft nicht. Siehe Fenster am PC."}
        text = ""
        with self._arbeitet:
            try:
                text = self.verstehen(pcm, rate, "Tablet-Aufnahme")
            except Exception:
                log.exception("Spracherkennung fehlgeschlagen")
                self.kern.funk.stumm_fuer(0)
                return {"ok": False, "fehler": "Die Erkennung ist fehlgeschlagen. Siehe Fenster am PC."}
        self.kern.funk.stumm_fuer(0)
        hinweis = HINWEISE.get(self.letzter_pegel.urteil, "") if self.letzter_pegel else ""
        if not text:
            antwort = self.kern.texte.sag("antwort.nichts_gehoert")
            self.kern.funk.sagen(antwort, 2, haltbar=10)
            return {"ok": True, "text": "", "antwort": antwort, "hinweis": hinweis}
        return {"ok": True, "text": text, "antwort": self.kern.frage(text), "hinweis": hinweis}

    def verstehen(self, pcm: bytes, rate: int, bezeichnung: str = "Aufnahme") -> str:
        """Aufnahme -> Text. Schreibt Pegel und Ergebnis ins Fenster."""
        pegel = audio.messen(pcm, rate)
        self.letzter_pegel = pegel
        log.info("%s: %s", bezeichnung, pegel.text())
        if pegel.urteil in ("kurz", "leer"):
            log.warning("%s", HINWEISE[pegel.urteil])
            return ""
        if pegel.urteil in HINWEISE:
            log.warning("%s", HINWEISE[pegel.urteil])
        pcm, verstaerkung = audio.aufbereiten(pcm, rate)
        if rate != audio.SPRACHRATE:  # Tablet nimmt meist mit 44,1 oder 48 kHz auf
            pcm = audio.als_pcm(audio.auf_16k(audio.als_float(pcm), rate))
            rate = audio.SPRACHRATE
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
