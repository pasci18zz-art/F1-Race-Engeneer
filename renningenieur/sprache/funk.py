"""Der Funk: Warteschlange fuer alles, was gesprochen werden soll.

    funk = Funk(stimme)
    funk.sagen("Box, Box.", prioritaet=2)

Meldungen mit hoeherer Prioritaet kommen zuerst. Meldungen, die zu lange
warten mussten, verfallen (eine Abstandswarnung von vor 30 Sekunden hilft
niemandem). Die eigentliche Sprachausgabe steckt in einer "Stimme"
(siehe stimmen.py) und laesst sich austauschen.
"""

from __future__ import annotations

import itertools
import logging
import queue
import threading
import time
from typing import Protocol

log = logging.getLogger(__name__)

NIEDRIG, NORMAL, HOCH = 0, 1, 2


class Stimme(Protocol):
    def sprechen(self, text: str) -> None:
        """Spricht den Text und kehrt zurueck, wenn er fertig gesprochen ist."""

    def schliessen(self) -> None: ...


class Funk:
    def __init__(self, stimme: Stimme, max_wartezeit: float = 20.0):
        self.stimme = stimme
        self.max_wartezeit = max_wartezeit
        self.protokoll: list[str] = []  # die letzten Meldungen (fuer die Webseite)
        self.stumm = False  # z. B. waehrend der Fahrer selbst spricht
        self._queue: queue.PriorityQueue = queue.PriorityQueue()
        self._zaehler = itertools.count()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="funk", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._queue.put((99, 0, 0.0, None))
        if self._thread:
            self._thread.join(timeout=3)
        self.stimme.schliessen()

    def sagen(self, text: str, prioritaet: int = NORMAL, haltbar: float | None = None) -> None:
        """Reiht eine Meldung ein. Leerer Text wird ignoriert."""
        text = (text or "").strip()
        if not text:
            return
        verfall = time.monotonic() + (self.max_wartezeit if haltbar is None else haltbar)
        self.protokoll.append(text)
        del self.protokoll[:-50]
        log.info("FUNK: %s", text)
        if self._thread is None:
            # Ohne laufenden Thread (Tests, Simulation im Zeitraffer): direkt
            self.stimme.sprechen(text)
            return
        self._queue.put((-prioritaet, next(self._zaehler), verfall, text))

    def _run(self) -> None:
        while not self._stop.is_set():
            _, _, verfall, text = self._queue.get()
            if text is None:
                break
            while self.stumm and not self._stop.is_set():
                time.sleep(0.05)
            if time.monotonic() > verfall:
                log.debug("Meldung verfallen: %s", text)
                continue
            try:
                self.stimme.sprechen(text)
            except Exception:
                log.exception("Sprachausgabe fehlgeschlagen")
