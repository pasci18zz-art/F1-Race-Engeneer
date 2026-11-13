"""UDP-Empfang und Weiterleitung (Relay).

Das Spiel schickt seine Telemetrie an einen Port (Standard 20777). Dieses
Modul empfaengt dort jedes Paket, schickt es unveraendert an alle Ziele
weiter (z. B. SimHub auf Port 20778) und gibt es danach an den
Renningenieur. Die Weiterleitung passiert zuerst, damit SimHub keine
Verzoegerung durch die Auswertung bekommt.
"""

from __future__ import annotations

import logging
import socket
import threading
from typing import Callable

log = logging.getLogger(__name__)


class Relay:
    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 20777,
        ziele: list[tuple[str, int]] | None = None,
        on_packet: Callable[[bytes], None] | None = None,
    ):
        self.host = host
        self.port = port
        self.ziele = list(ziele or [])
        self.on_packet = on_packet
        self.empfangen = 0
        self.weitergeleitet = 0
        self.sendefehler = 0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._rx: socket.socket | None = None
        self._tx: socket.socket | None = None

    # ------------------------------------------------------------------
    def start(self) -> None:
        self._rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            self._rx.bind((self.host, self.port))
        except OSError as e:
            self._rx.close()
            raise RuntimeError(
                f"UDP-Port {self.port} ist belegt ({e}). Läuft SimHub noch auf "
                f"diesem Port? SimHub muss auf einen anderen Port hören "
                f"(siehe README, Abschnitt SimHub)."
            ) from e
        self._rx.settimeout(0.5)
        # Eigener Socket zum Senden: Fehler beim Weiterleiten (Ziel laeuft
        # nicht) stoeren so den Empfang nicht.
        self._tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.port = self._rx.getsockname()[1]
        self._thread = threading.Thread(target=self._run, name="udp-relay", daemon=True)
        self._thread.start()
        ziele = ", ".join(f"{h}:{p}" for h, p in self.ziele) or "keine"
        log.info("UDP-Empfang auf Port %s, Weiterleitung an: %s", self.port, ziele)

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        for s in (self._rx, self._tx):
            if s:
                s.close()

    # ------------------------------------------------------------------
    def _run(self) -> None:
        assert self._rx and self._tx
        while not self._stop.is_set():
            try:
                data, _ = self._rx.recvfrom(4096)
            except socket.timeout:
                continue
            except ConnectionResetError:
                continue  # Windows meldet so ein nicht erreichbares Ziel
            except OSError:
                if self._stop.is_set():
                    break
                log.exception("Fehler beim UDP-Empfang")
                continue
            self.empfangen += 1
            for ziel in self.ziele:
                try:
                    self._tx.sendto(data, ziel)
                    self.weitergeleitet += 1
                except OSError:
                    self.sendefehler += 1
            if self.on_packet:
                try:
                    self.on_packet(data)
                except Exception:  # Auswertung darf das Relay nie anhalten
                    log.exception("Fehler bei der Paketauswertung")
