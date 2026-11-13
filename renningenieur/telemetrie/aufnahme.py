"""Echte Telemetrie aufzeichnen und spaeter wieder abspielen.

Dateiformat (binaer, pro Paket):
    float64  Sekunden seit Aufnahmebeginn
    uint16   Laenge
    bytes    Paket
"""

from __future__ import annotations

import socket
import struct
import time
from typing import Iterator

_KOPF = struct.Struct("<dH")


class Aufnahme:
    """Schreibt empfangene Pakete in eine Datei."""

    def __init__(self, pfad: str):
        self._datei = open(pfad, "wb")
        self._start = time.monotonic()
        self.anzahl = 0

    def schreiben(self, data: bytes) -> None:
        self._datei.write(_KOPF.pack(time.monotonic() - self._start, len(data)))
        self._datei.write(data)
        self.anzahl += 1

    def schliessen(self) -> None:
        self._datei.close()


def lesen(pfad: str) -> Iterator[tuple[float, bytes]]:
    """Liefert (Zeitpunkt in Sekunden, Paket) aus einer Aufnahmedatei."""
    with open(pfad, "rb") as f:
        while True:
            kopf = f.read(_KOPF.size)
            if len(kopf) < _KOPF.size:
                return
            t, n = _KOPF.unpack(kopf)
            data = f.read(n)
            if len(data) < n:
                return
            yield t, data


def abspielen(pfad: str, host: str, port: int, tempo: float = 1.0) -> int:
    """Schickt eine Aufnahme per UDP an host:port. Gibt die Paketanzahl zurueck."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    start = time.monotonic()
    anzahl = 0
    try:
        for t, data in lesen(pfad):
            warten = t / tempo - (time.monotonic() - start)
            if warten > 0:
                time.sleep(warten)
            sock.sendto(data, (host, port))
            anzahl += 1
    finally:
        sock.close()
    return anzahl
