"""Mikrofonaufnahme mit Vorlauf.

Das Mikrofon laeuft dauerhaft mit und fuellt einen kleinen Ringpuffer
(Standard 0,5 Sekunden). Beim Druck auf die Funktaste beginnt die Aufnahme
mit dem Inhalt dieses Puffers - der Satzanfang geht also nicht verloren,
auch wenn man schon beim Druecken losspricht.

Aufgenommen wird Mono, 16 Bit. Zuerst wird 16 kHz versucht (das erwarten
die Spracherkennungen); geht das nicht, wird die Abtastrate des Geraets
benutzt.
"""

from __future__ import annotations

import collections
import logging
import threading
import time

log = logging.getLogger(__name__)

MIN_NACHLAUF = 0.4  # kuerzer schneidet oft das letzte Wort ab


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
    def __init__(self, geraet: str | int = "", vorlauf: float = 0.5, nachlauf: float = 0.5,
                 max_sekunden: float = 10.0):
        self.wahl = geraet
        self.vorlauf = vorlauf
        self.nachlauf = max(nachlauf, MIN_NACHLAUF)
        self.max_sekunden = max_sekunden
        self.samplerate = 16000
        self.name = ""
        self._lock = threading.Lock()
        self._ring: collections.deque[bytes] = collections.deque()
        self._aufnahme: list[bytes] | None = None
        self._aufnahme_bytes = 0
        self._max_bytes = 0
        self._stream = None

    def start(self) -> None:
        import sounddevice as sd

        nummer = geraet_finden(self.wahl)
        info = sd.query_devices(nummer, "input")
        self.name = info["name"]
        standard = int(info["default_samplerate"])
        letzter: Exception | None = None
        for rate in dict.fromkeys((16000, standard)):
            try:
                self._oeffnen(sd, nummer, rate)
                break
            except Exception as e:  # PortAudioError: Rate wird nicht unterstuetzt
                letzter = e
                log.debug("Mikrofon mit %s Hz nicht moeglich: %s", rate, e)
        else:
            raise RuntimeError(f"Mikrofon lässt sich nicht öffnen: {letzter}")
        log.info("Mikrofon: %s (%s Hz)", self.name, self.samplerate)

    def _oeffnen(self, sd, nummer, rate: int) -> None:
        block = max(rate // 20, 256)  # 50 ms
        self._ring = collections.deque(maxlen=max(int(self.vorlauf * rate / block) + 1, 1))
        self._max_bytes = int(self.max_sekunden * rate) * 2
        stream = sd.RawInputStream(samplerate=rate, blocksize=block, device=nummer,
                                   channels=1, dtype="int16", callback=self._callback)
        stream.start()
        self._stream = stream
        self.samplerate = rate

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
