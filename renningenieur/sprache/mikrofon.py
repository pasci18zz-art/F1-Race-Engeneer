"""Mikrofonaufnahme mit Vorlauf.

Das Mikrofon laeuft dauerhaft mit und fuellt einen kleinen Ringpuffer
(Standard 0,5 Sekunden). Beim Druck auf die Funktaste beginnt die Aufnahme
mit dem Inhalt dieses Puffers - der Satzanfang geht also nicht verloren,
auch wenn man schon beim Druecken losspricht.

Aufgenommen wird Mono, 16 Bit, in der Abtastrate des Geraets.
"""

from __future__ import annotations

import collections
import logging
import threading
import time

log = logging.getLogger(__name__)


def eingabegeraete() -> list[tuple[int, str, str]]:
    """Liste (Nummer, Name, Treiber) aller Mikrofone."""
    import sounddevice as sd

    apis = sd.query_hostapis()
    return [
        (i, d["name"], apis[d["hostapi"]]["name"])
        for i, d in enumerate(sd.query_devices())
        if d["max_input_channels"] > 0
    ]


def geraet_finden(wahl: str | int) -> int | None:
    """Nummer oder Namensteil -> Geraetenummer. None = Windows-Standard."""
    if wahl in ("", None):
        return None
    if isinstance(wahl, int) or str(wahl).isdigit():
        return int(wahl)
    gesucht = str(wahl).lower()
    for nummer, name, _ in eingabegeraete():
        if gesucht in name.lower():
            return nummer
    log.warning("Mikrofon %r nicht gefunden - nehme das Windows-Standardmikrofon.", wahl)
    return None


class Mikrofon:
    def __init__(self, geraet: str | int = "", vorlauf: float = 0.5, nachlauf: float = 0.3,
                 max_sekunden: float = 10.0):
        self.wahl = geraet
        self.vorlauf = vorlauf
        self.nachlauf = nachlauf
        self.max_sekunden = max_sekunden
        self.samplerate = 16000
        self._lock = threading.Lock()
        self._ring: collections.deque[bytes] = collections.deque()
        self._aufnahme: list[bytes] | None = None
        self._aufnahme_bytes = 0
        self._stream = None

    def start(self) -> None:
        import sounddevice as sd

        nummer = geraet_finden(self.wahl)
        info = sd.query_devices(nummer, "input")
        self.samplerate = int(info["default_samplerate"])
        block = max(self.samplerate // 20, 256)  # 50 ms
        self._ring = collections.deque(
            maxlen=max(int(self.vorlauf * self.samplerate / block) + 1, 1))
        self._max_bytes = int(self.max_sekunden * self.samplerate) * 2
        self._stream = sd.RawInputStream(
            samplerate=self.samplerate, blocksize=block, device=nummer,
            channels=1, dtype="int16", callback=self._callback)
        self._stream.start()
        log.info("Mikrofon: %s (%s Hz)", info["name"], self.samplerate)

    def stop(self) -> None:
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def _callback(self, indata, frames, zeit, status) -> None:
        daten = bytes(indata)
        with self._lock:
            if self._aufnahme is not None:
                if self._aufnahme_bytes < self._max_bytes:
                    self._aufnahme.append(daten)
                    self._aufnahme_bytes += len(daten)
            else:
                self._ring.append(daten)

    def aufnahme_start(self) -> None:
        with self._lock:
            if self._aufnahme is None:
                self._aufnahme = list(self._ring)  # Vorlauf uebernehmen
                self._aufnahme_bytes = sum(len(c) for c in self._aufnahme)
                self._ring.clear()

    def aufnahme_stopp(self) -> bytes:
        """Beendet die Aufnahme (nach dem Nachlauf) und gibt die PCM-Daten zurueck."""
        if self._aufnahme is None:
            return b""
        time.sleep(self.nachlauf)
        with self._lock:
            daten = b"".join(self._aufnahme or [])
            self._aufnahme = None
        return daten
