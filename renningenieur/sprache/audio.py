"""Aufbereitung von Mikrofonaufnahmen fuer die Spracherkennung.

Das Mikrofon der Bluetooth-Kopfhoerer ist unter Windows oft sehr leise und
nimmt das Rumpeln des Lenkrads mit auf. Beides verschlechtert die Erkennung
stark. Deshalb wird die Aufnahme vor der Erkennung

  1. vom Gleichspannungsanteil befreit,
  2. von tiefem Rumpeln (unter etwa 90 Hz) befreit und
  3. auf eine gute Lautstaerke angehoben (maximal um 30 dB).

Reines Rauschen wird nicht angehoben, sonst hoert die Erkennung Woerter,
die niemand gesagt hat.
"""

from __future__ import annotations

import math
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np

SPRACHRATE = 16000
HOCHPASS_HZ = 90.0
ZIEL_DB = -6.0  # so laut soll die Aufnahme (99,5-Prozent-Spitze) werden
MAX_VERSTAERKUNG_DB = 30.0
RAUSCHBODEN_DB = -60.0  # darunter ist nur Rauschen


def als_float(pcm: bytes) -> np.ndarray:
    """16-Bit-PCM (Mono) -> float32 im Bereich -1..1."""
    if len(pcm) % 2:
        pcm = pcm[:-1]
    return np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0


def als_pcm(x: np.ndarray) -> bytes:
    return (np.clip(x, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()


def _db(wert: float) -> float:
    return 20.0 * math.log10(max(float(wert), 1e-9))


@dataclass
class Pegel:
    dauer: float  # Sekunden
    spitze_db: float  # lauteste Stelle, 0 dB = Vollaussteuerung
    effektiv_db: float  # Durchschnitt
    uebersteuert: float  # Anteil der Werte an der Grenze (0..1)

    @property
    def urteil(self) -> str:
        """kurz, leer, leise, uebersteuert oder gut"""
        if self.dauer < 0.4:
            return "kurz"
        if self.spitze_db < -50:
            return "leer"
        if self.uebersteuert > 0.005:
            return "uebersteuert"
        if self.spitze_db < -26:
            return "leise"
        return "gut"

    def text(self) -> str:
        return (f"{self.dauer:.1f} s, Spitze {self.spitze_db:.0f} dB, "
                f"Durchschnitt {self.effektiv_db:.0f} dB")


def messen(pcm: bytes, rate: int) -> Pegel:
    x = als_float(pcm)
    if len(x) == 0:
        return Pegel(0.0, -120.0, -120.0, 0.0)
    return Pegel(
        dauer=len(x) / rate,
        spitze_db=_db(np.max(np.abs(x))),
        effektiv_db=_db(float(np.sqrt(np.mean(x * x)))),
        uebersteuert=float(np.mean(np.abs(x) >= 0.99)),
    )


def hochpass(x: np.ndarray, rate: int, grenze: float = HOCHPASS_HZ) -> np.ndarray:
    """Entfernt alles unter `grenze` Hz (weiche Rampe zwischen grenze/2 und grenze)."""
    if len(x) < 8:
        return x
    spektrum = np.fft.rfft(x)
    freq = np.fft.rfftfreq(len(x), 1.0 / rate)
    faktor = np.clip((freq - grenze / 2) / (grenze / 2), 0.0, 1.0)
    return np.fft.irfft(spektrum * faktor, len(x)).astype(np.float32)


def aufbereiten(pcm: bytes, rate: int) -> tuple[bytes, float]:
    """Gleichanteil und Rumpeln entfernen, Lautstaerke anheben.

    Gibt (aufbereitete Aufnahme, Verstaerkung in dB) zurueck. Ist die
    Aufnahme nur Rauschen, kommt sie unveraendert mit 0 dB zurueck.
    """
    x = als_float(pcm)
    if len(x) < 8:
        return pcm, 0.0
    x = x - float(np.mean(x))
    x = hochpass(x, rate)
    referenz = float(np.percentile(np.abs(x), 99.5))
    if _db(referenz) < RAUSCHBODEN_DB:
        return pcm, 0.0
    verstaerkung = min(ZIEL_DB - _db(referenz), MAX_VERSTAERKUNG_DB)
    if verstaerkung > 0:
        x = x * (10.0 ** (verstaerkung / 20.0))
    else:
        verstaerkung = 0.0
    return als_pcm(x), verstaerkung


def auf_16k(x: np.ndarray, rate: int) -> np.ndarray:
    """Auf 16 kHz umrechnen (Whisper erwartet genau diese Abtastrate)."""
    if rate == SPRACHRATE or len(x) == 0:
        return x.astype(np.float32)
    if rate > SPRACHRATE:  # Tiefpass gegen Verfaelschungen beim Verkleinern
        spektrum = np.fft.rfft(x)
        freq = np.fft.rfftfreq(len(x), 1.0 / rate)
        spektrum[freq > SPRACHRATE / 2 * 0.95] = 0
        x = np.fft.irfft(spektrum, len(x))
    n_neu = max(int(round(len(x) * SPRACHRATE / rate)), 1)
    return np.interp(np.linspace(0, len(x) - 1, n_neu), np.arange(len(x)), x).astype(np.float32)


def als_wav(pcm: bytes, rate: int, pfad: Path) -> None:
    with wave.open(str(pfad), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
