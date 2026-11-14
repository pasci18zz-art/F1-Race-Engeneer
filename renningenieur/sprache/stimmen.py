"""Sprachausgaben ("Stimmen"). Jede Stimme hat sprechen(text) und schliessen().

  WindowsStimme  - Windows-Sprachausgabe (SAPI) ueber einen PowerShell-
                   Hilfsprozess. Braucht keine zusaetzlichen Python-Pakete.
  KonsolenStimme - schreibt den Text nur ins Fenster (Test, Linux/Mac).
  StummeStimme   - merkt sich die Texte nur (fuer automatische Tests).

  PiperStimme    - natuerliche neuronale Stimme, ebenfalls lokal
                   (siehe piper_stimme.py, Einrichtung mit stimmen.bat).

Eine weitere Sprachausgabe laesst sich ergaenzen, indem man eine Klasse mit
denselben zwei Methoden schreibt und sie in stimme_erzeugen() eintraegt.
"""

from __future__ import annotations

import base64
import logging
import subprocess
import sys
import threading
from pathlib import Path

log = logging.getLogger(__name__)
WORKER = Path(__file__).parent / "sapi_worker.ps1"


class StummeStimme:
    def __init__(self) -> None:
        self.gesagt: list[str] = []

    def sprechen(self, text: str) -> None:
        self.gesagt.append(text)

    def schliessen(self) -> None:
        pass


class KonsolenStimme:
    def sprechen(self, text: str) -> None:
        print(f"[FUNK] {text}", flush=True)

    def schliessen(self) -> None:
        pass


def _powershell(args: list[str], **kw) -> subprocess.Popen:
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.Popen(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(WORKER)]
        + args,
        creationflags=flags,
        **kw,
    )


class WindowsStimme:
    def __init__(self, stimme: str = "", geraet: str = "", tempo: int = 0,
                 lautstaerke: int = 100):
        self._args = ["-Tempo", str(int(tempo)), "-Lautstaerke", str(int(lautstaerke))]
        if stimme:
            self._args += ["-Stimme", stimme]
        if geraet:
            self._args += ["-Geraet", geraet]
        self._proc: subprocess.Popen | None = None
        self._starten()

    def _starten(self) -> None:
        self._proc = _powershell(
            self._args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        threading.Thread(target=self._stderr_lesen, args=(self._proc,), daemon=True).start()
        zeile = self._proc.stdout.readline().strip()
        if zeile != "BEREIT":
            raise RuntimeError(f"Windows-Sprachausgabe startet nicht ({zeile or 'keine Antwort'})")

    @staticmethod
    def _stderr_lesen(proc: subprocess.Popen) -> None:
        for zeile in proc.stderr:
            zeile = zeile.strip()
            if zeile:
                log.info("Sprachausgabe: %s", zeile)

    def sprechen(self, text: str) -> None:
        for versuch in (1, 2):
            try:
                if self._proc is None or self._proc.poll() is not None:
                    self._starten()
                daten = base64.b64encode(text.encode("utf-8")).decode("ascii")
                self._proc.stdin.write(daten + "\n")
                self._proc.stdin.flush()
                antwort = self._proc.stdout.readline().strip()
                if antwort.startswith("FEHLER"):
                    log.warning("Sprachausgabe: %s", antwort)
                if antwort:
                    return
                raise RuntimeError("Hilfsprozess antwortet nicht")
            except (OSError, RuntimeError) as e:
                log.warning("Sprachausgabe wird neu gestartet (%s)", e)
                self.schliessen()
                if versuch == 2:
                    print(f"[FUNK] {text}", flush=True)

    def schliessen(self) -> None:
        if self._proc:
            try:
                self._proc.stdin.close()
                self._proc.terminate()
            except OSError:
                pass
            self._proc = None


def stimme_erzeugen(cfg: dict, ordner: Path | None = None):
    """Erzeugt die Stimme laut [sprachausgabe] in der config.toml."""
    engine = cfg.get("engine", "windows")
    if engine == "aus":
        return StummeStimme()
    if engine == "piper":
        try:
            from .piper_stimme import STIMMEN_ORDNER, PiperStimme

            name = cfg.get("piper_stimme", "") or "de_DE-thorsten-high"
            return PiperStimme(
                (ordner or Path(".")) / STIMMEN_ORDNER / f"{name}.onnx",
                tempo=cfg.get("tempo", 0),
                lautstaerke=cfg.get("lautstaerke", 100),
                geraet=cfg.get("ausgabegeraet", ""),
                funk=cfg.get("funkeffekt", False),
            )
        except ImportError:
            log.error("Piper ist nicht installiert - stimmen.bat ausführen. Nehme die Windows-Stimme.")
        except Exception as e:
            log.error("Piper-Stimme nicht verfügbar (%s) - nehme die Windows-Stimme.", e)
        engine = "windows"
    if engine == "windows" and sys.platform == "win32":
        try:
            return WindowsStimme(
                cfg.get("stimme", ""),
                cfg.get("ausgabegeraet", ""),
                cfg.get("tempo", 0),
                cfg.get("lautstaerke", 100),
            )
        except Exception as e:
            log.error("Windows-Sprachausgabe nicht verfügbar: %s - es wird nur Text angezeigt.", e)
    elif engine == "windows":
        log.info("Kein Windows: Meldungen werden nur als Text angezeigt.")
    return KonsolenStimme()


def geraete_auflisten() -> str:
    """Stimmen und Ausgabegeraete der Windows-Sprachausgabe als Text."""
    if sys.platform != "win32":
        return "Windows-Sprachausgabe gibt es nur unter Windows."
    try:
        proc = _powershell(["-Liste"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           text=True, encoding="utf-8", errors="replace")
        ausgabe, _ = proc.communicate(timeout=20)
        return ausgabe.strip()
    except Exception as e:
        return f"Windows-Sprachausgabe konnte nicht abgefragt werden: {e}"
