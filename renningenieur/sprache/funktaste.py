"""Funktaste (Push-to-talk): Lenkrad-/Controllertaste und/oder Tastatur.

Die Tasten werden abgefragt, auch wenn das Spiel im Vordergrund ist:
  * Lenkrad/Controller ueber pygame (jedes Geraet, das Windows als
    Gamecontroller kennt).
  * Tastatur ueber die Windows-Funktion GetAsyncKeyState (kein Zusatzpaket).

    taste = Funktaste(cfg, bei_druck, bei_loslassen)
    taste.start()
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
from typing import Callable

log = logging.getLogger(__name__)

# Namen fuer [funktaste] tastatur = "..." -> Windows Virtual-Key-Code
_VK = {
    "leertaste": 0x20, "space": 0x20, "tab": 0x09, "enter": 0x0D, "pause": 0x13,
    "rollen": 0x91, "einfg": 0x2D, "entf": 0x2E, "pos1": 0x24, "ende": 0x23,
    "bildauf": 0x21, "bildab": 0x22, "strg": 0x11, "ctrl": 0x11, "alt": 0x12,
    "shift": 0x10, "umschalt": 0x10, "strg_rechts": 0xA3, "alt_gr": 0xA5,
    "links": 0x25, "hoch": 0x26, "rechts": 0x27, "runter": 0x28,
}
_VK.update({f"f{n}": 0x6F + n for n in range(1, 25)})
_VK.update({f"num{n}": 0x60 + n for n in range(10)})
_VK.update({chr(c).lower(): c for c in range(ord("A"), ord("Z") + 1)})
_VK.update({str(n): 0x30 + n for n in range(10)})


def pygame_laden():
    """Laedt pygame so, dass Tasten auch ohne eigenes Fenster ankommen."""
    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    os.environ.setdefault("SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS", "1")
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    import pygame

    pygame.display.init()
    pygame.joystick.init()
    return pygame


class Tastatur:
    def __init__(self, name: str):
        self.vk = _VK.get(name.strip().lower())
        self._user32 = None
        if not name:
            return
        if self.vk is None:
            log.warning("Tastatur-Taste %r kenne ich nicht (z. B. f12, leertaste, y).", name)
        elif sys.platform != "win32":
            log.info("Tastatur-Funktaste gibt es nur unter Windows.")
        else:
            import ctypes

            self._user32 = ctypes.windll.user32

    def gedrueckt(self) -> bool:
        if self._user32 is None or self.vk is None:
            return False
        return bool(self._user32.GetAsyncKeyState(self.vk) & 0x8000)


class Lenkrad:
    def __init__(self, name: str, taste: int):
        self.name = name.strip().lower()
        self.taste = taste
        self._pygame = None
        self._geraete: list = []
        self._anzahl = -1
        if taste < 0:
            return
        try:
            self._pygame = pygame_laden()
        except Exception as e:
            log.warning("Lenkradtaste nicht verfügbar (pygame fehlt? %s). "
                        "Installieren mit: pip install pygame-ce", e)

    def _suchen(self) -> None:
        pg = self._pygame
        anzahl = pg.joystick.get_count()
        if anzahl == self._anzahl:
            return
        self._anzahl = anzahl
        self._geraete = []
        for i in range(anzahl):
            js = pg.joystick.Joystick(i)
            js.init()
            if self.name in js.get_name().lower() and js.get_numbuttons() > self.taste:
                self._geraete.append(js)
                log.info("Funktaste: %s, Taste %s", js.get_name(), self.taste)
        if not self._geraete:
            log.warning("Kein passendes Lenkrad/Controller für die Funktaste gefunden.")

    def gedrueckt(self) -> bool:
        if self._pygame is None:
            return False
        try:
            self._pygame.event.pump()
            self._suchen()
            return any(js.get_button(self.taste) for js in self._geraete)
        except Exception:
            self._anzahl = -1  # Geraet abgezogen: neu suchen
            return False


class Funktaste:
    def __init__(self, cfg: dict, bei_druck: Callable[[], None],
                 bei_loslassen: Callable[[], None]):
        self.cfg = cfg
        self.bei_druck = bei_druck
        self.bei_loslassen = bei_loslassen
        self.umschalten = cfg.get("modus", "halten") == "umschalten"
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="funktaste", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        # pygame muss in dem Thread initialisiert werden, der es abfragt
        tastatur = Tastatur(self.cfg.get("tastatur", ""))
        lenkrad = Lenkrad(self.cfg.get("joystick", ""), int(self.cfg.get("taste", -1)))
        war = False
        aktiv = False
        while not self._stop.is_set():
            ist = tastatur.gedrueckt() or lenkrad.gedrueckt()
            if self.umschalten:
                if ist and not war:
                    aktiv = not aktiv
                    (self.bei_druck if aktiv else self.bei_loslassen)()
            elif ist != war:
                (self.bei_druck if ist else self.bei_loslassen)()
            war = ist
            time.sleep(0.01)


def tasten_finden(ausgabe=print, dauer: float = 30.0) -> None:
    """Zeigt an, welche Lenkrad-/Controllertaste gerade gedrueckt wird."""
    try:
        pg = pygame_laden()
    except Exception as e:
        ausgabe(f"pygame ist nicht installiert ({e}). Installieren mit: pip install pygame-ce")
        return
    geraete = []
    for i in range(pg.joystick.get_count()):
        js = pg.joystick.Joystick(i)
        js.init()
        geraete.append(js)
        ausgabe(f"  Gerät {i}: {js.get_name()}  ({js.get_numbuttons()} Tasten)")
    if not geraete:
        ausgabe("  Kein Lenkrad oder Controller gefunden.")
        return
    ausgabe(f"\nDrücke jetzt die Taste, die du als Funktaste willst ({int(dauer)} Sekunden Zeit) ...")
    ende = time.monotonic() + dauer
    gemeldet: set[tuple[int, int]] = set()
    while time.monotonic() < ende:
        pg.event.pump()
        for i, js in enumerate(geraete):
            for b in range(js.get_numbuttons()):
                if js.get_button(b) and (i, b) not in gemeldet:
                    gemeldet.add((i, b))
                    ausgabe(f'  -> "{js.get_name()}": taste = {b}')
        time.sleep(0.02)
    if gemeldet:
        ausgabe("\nTrage Gerätename (ein Teil reicht) und Tastennummer in config.toml unter "
                "[funktaste] ein.")
