"""UDP-Empfang und Weiterleitung (Relay).

Das Spiel schickt seine Telemetrie an einen Port (Standard 20777). Dieses
Modul empfaengt dort jedes Paket, schickt es unveraendert an alle Ziele
weiter (z. B. SimHub auf Port 20778) und gibt es danach an den
Renningenieur. Die Weiterleitung passiert zuerst, damit SimHub keine
Verzoegerung durch die Auswertung bekommt.

Pruefung der Ziele: Hoert an einem Ziel niemand zu, meldet das
Betriebssystem das beim naechsten Senden zurueck ("Port nicht erreichbar").
So kann das Programm sagen, dass z. B. SimHub nicht auf dem richtigen Port
lauscht, statt dass man bei SimHub einfach nur leere Anzeigen sieht.
"""

from __future__ import annotations

import logging
import socket
import threading
from typing import Callable

log = logging.getLogger(__name__)

NICHT_ERREICHT = (ConnectionRefusedError, ConnectionResetError)


class _Ziel:
    """Ein Weiterleitungsziel mit eigenem (verbundenem) Socket."""

    MIN_PAKETE = 30  # so viele Pakete braucht es fuer ein Urteil

    def __init__(self, adresse: tuple[str, int]):
        self.adresse = adresse
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setblocking(False)
        self.sock.connect(adresse)
        self.gesendet = 0
        self.abgelehnt = 0
        self.fehler = 0  # andere Sendefehler
        self._f_gesendet = 0
        self._f_abgelehnt = 0

    def senden(self, data: bytes) -> bool:
        try:
            self.sock.send(data)
            self.gesendet += 1
            self._f_gesendet += 1
        except NICHT_ERREICHT:
            self.abgelehnt += 1
            self._f_abgelehnt += 1
            return False
        except OSError:
            self.fehler += 1
            return False
        try:
            self.sock.recv(64)  # holt eine gemeldete "Port nicht erreichbar"-Antwort ab
        except NICHT_ERREICHT:
            self._f_abgelehnt += 1
        except OSError:
            pass  # nichts zu lesen: das ist der Normalfall
        return True

    def zustand(self, zuruecksetzen: bool = True) -> str:
        """"ok", "abgelehnt" oder "unbekannt" (zu wenige Pakete)."""
        if self._f_gesendet + self._f_abgelehnt < self.MIN_PAKETE:
            return "unbekannt"
        z = "abgelehnt" if self._f_abgelehnt * 4 >= self._f_gesendet else "ok"
        if zuruecksetzen:
            self._f_gesendet = self._f_abgelehnt = 0
        return z

    def schliessen(self) -> None:
        self.sock.close()


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
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._rx: socket.socket | None = None
        self._ziel_sockets: list[_Ziel] = []

    # Zaehler fuer die Anzeige und die Tests
    @property
    def weitergeleitet(self) -> int:
        return sum(z.gesendet for z in self._ziel_sockets)

    @property
    def sendefehler(self) -> int:
        return sum(z.abgelehnt + z.fehler for z in self._ziel_sockets)

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
        self.port = self._rx.getsockname()[1]
        self._ziel_sockets = [_Ziel(adresse) for adresse in self.ziele]
        self._thread = threading.Thread(target=self._run, name="udp-relay", daemon=True)
        self._thread.start()
        ziele = ", ".join(f"{h}:{p}" for h, p in self.ziele) or "keine"
        log.info("UDP-Empfang auf Port %s, Weiterleitung an: %s", self.port, ziele)

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        if self._rx:
            self._rx.close()
        for ziel in self._ziel_sockets:
            ziel.schliessen()

    def pruefe_ziele(self) -> list[tuple[tuple[str, int], str]]:
        """Zustand jedes Ziels seit dem letzten Aufruf: "ok", "abgelehnt", "unbekannt"."""
        return [(z.adresse, z.zustand()) for z in self._ziel_sockets]

    # ------------------------------------------------------------------
    def _run(self) -> None:
        assert self._rx
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
            for ziel in self._ziel_sockets:
                ziel.senden(data)
            if self.on_packet:
                try:
                    self.on_packet(data)
                except Exception:  # Auswertung darf das Relay nie anhalten
                    log.exception("Fehler bei der Paketauswertung")
