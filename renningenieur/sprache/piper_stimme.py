"""Natuerliche Sprachausgabe mit Piper (laeuft lokal, ohne Internet).

Piper ist eine kostenlose Sprachausgabe mit neuronalen Stimmen. Sie klingt
deutlich natuerlicher als die Windows-Stimmen und braucht pro Satz nur
Bruchteile einer Sekunde Rechenzeit auf dem Prozessor.

Die Stimmen (je 20 bis 110 MB) werden einmalig mit stimmen.bat
heruntergeladen und liegen danach in modelle/stimmen/.

Optional gibt es einen Funk-Effekt: Bandpass wie ein Funkgeraet, leichte
Verzerrung und ein kurzes Rauschen am Ende.
"""

from __future__ import annotations

import io
import logging
import re
import subprocess
import sys
import threading
import urllib.request
import wave
from pathlib import Path

log = logging.getLogger(__name__)

STIMMEN_ORDNER = Path("modelle") / "stimmen"

# (Dateiname, Beschreibung). Quelle: offizielle Liste der Piper-Stimmen.
STIMMEN = [
    ("de_DE-thorsten-high", "Thorsten, männlich, beste Qualität"),
    ("de_DE-thorsten-medium", "Thorsten, männlich, etwas schneller berechnet"),
    ("de_DE-karlsson-low", "Karlsson, männlich"),
    ("de_DE-pavoque-low", "Pavoque, männlich"),
    ("de_DE-kerstin-low", "Kerstin, weiblich"),
    ("de_DE-ramona-low", "Ramona, weiblich"),
    ("de_DE-eva_k-x_low", "Eva, weiblich"),
]
URL = ("https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/de/de_DE/"
       "{name}/{qualitaet}/{datei}{endung}?download=true")

PROBETEXT = "Hamilton hinter dir kommt an die Box. Undercut-Gefahr. Regen in etwa zehn Minuten."


def url(datei: str, endung: str) -> str:
    _, name, qualitaet = datei.split("-", 2)
    return URL.format(name=name, qualitaet=qualitaet, datei=datei, endung=endung)


# --------------------------------------------------------------------------
# Klang
# --------------------------------------------------------------------------
def funkeffekt(audio, rate: int):
    """Klang wie Boxenfunk: nur Mitten, leicht angezerrt, Rauschen am Ende."""
    import numpy as np

    x = audio.astype(np.float32)
    spektrum = np.fft.rfft(x)
    freq = np.fft.rfftfreq(len(x), 1.0 / rate)
    spektrum[(freq < 350) | (freq > 3200)] = 0
    x = np.fft.irfft(spektrum, len(x))
    x = x / (np.max(np.abs(x)) + 1e-9)
    x = np.tanh(x * 2.2) / np.tanh(2.2)
    zufall = np.random.default_rng(7)
    x = x * 0.85 + zufall.normal(0, 0.012, len(x))
    rauschen = zufall.normal(0, 0.18, int(rate * 0.09)) * np.linspace(1, 0, int(rate * 0.09))
    return np.concatenate([x, rauschen]).astype(np.float32)


def _ausgabegeraet(name: str):
    """Teil des Geraetenamens -> sounddevice-Nummer (None = Standard)."""
    if not name:
        return None
    import sounddevice as sd

    for i, d in enumerate(sd.query_devices()):
        if d["max_output_channels"] > 0 and name.lower() in d["name"].lower():
            return i
    log.warning("Ausgabegerät %r nicht gefunden - nehme das Standardgerät.", name)
    return None


def abspielen(audio, rate: int, geraet=None) -> None:
    """Spielt Audio (float -1..1) ab und wartet, bis es fertig ist."""
    import numpy as np

    # Kurze Stille vorne: Bluetooth-Kopfhoerer wachen sonst erst mitten im
    # ersten Wort auf.
    audio = np.concatenate([np.zeros(int(rate * 0.25), np.float32), audio])
    try:
        import sounddevice as sd

        sd.play(audio, rate, device=geraet, blocking=True)
        return
    except ImportError:
        pass
    if sys.platform == "win32":
        import winsound

        puffer = io.BytesIO()
        with wave.open(puffer, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes((np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes())
        winsound.PlaySound(puffer.getvalue(), winsound.SND_MEMORY)
    else:
        raise RuntimeError("Zum Abspielen fehlt sounddevice (pip install sounddevice).")


# --------------------------------------------------------------------------
class PiperStimme:
    def __init__(self, modell: Path, tempo: int = 0, lautstaerke: int = 100,
                 geraet: str = "", funk: bool = False, spieler=abspielen):
        from piper import PiperVoice, SynthesisConfig

        if not Path(modell).is_file():
            raise FileNotFoundError(f"Stimme nicht gefunden: {modell} (stimmen.bat ausführen)")
        self._stimme = PiperVoice.load(str(modell))
        # Tempo -10..10 wie bei Windows; kleinere length_scale = schneller
        self._config = SynthesisConfig(
            length_scale=min(max(1.0 - int(tempo) * 0.03, 0.6), 1.6),
            volume=max(min(int(lautstaerke), 100), 0) / 100.0,
        )
        self.rate = self._stimme.config.sample_rate
        self.funk = funk
        self._spieler = spieler
        self._geraet = _ausgabegeraet(geraet) if geraet and spieler is abspielen else None
        self._lock = threading.Lock()
        log.info("Stimme: Piper %s%s", Path(modell).stem, " mit Funk-Effekt" if funk else "")

    def berechnen(self, text: str):
        """Text -> Audio (float32, -1..1)."""
        import numpy as np

        teile = [c.audio_float_array for c in self._stimme.synthesize(text, self._config)]
        if not teile:
            return np.zeros(0, np.float32)
        pause = np.zeros(int(self.rate * 0.12), np.float32)
        audio = np.concatenate([x for t in teile for x in (t, pause)][:-1])
        return funkeffekt(audio, self.rate) if self.funk else audio

    def sprechen(self, text: str) -> None:
        with self._lock:
            audio = self.berechnen(text)
            if len(audio):
                self._spieler(audio, self.rate, self._geraet)

    def schliessen(self) -> None:
        pass


# --------------------------------------------------------------------------
# Einrichtung: herunterladen, anhoeren, auswaehlen (stimmen.bat)
# --------------------------------------------------------------------------
def _laden(datei_url: str, ziel: Path, ausgabe) -> None:
    teil = ziel.with_suffix(ziel.suffix + ".teil")
    with urllib.request.urlopen(datei_url, timeout=60) as antwort, open(teil, "wb") as f:
        gesamt = int(antwort.headers.get("Content-Length", 0))
        geladen = 0
        while True:
            block = antwort.read(1 << 20)
            if not block:
                break
            f.write(block)
            geladen += len(block)
            if gesamt:
                ausgabe(f"\r     {geladen >> 20} von {gesamt >> 20} MB", end="")
    if gesamt:
        ausgabe("")
    teil.replace(ziel)


def herunterladen(ordner: Path, ausgabe=print) -> list[str]:
    """Laedt alle deutschen Stimmen, die noch fehlen. Gibt die vorhandenen zurueck."""
    ordner.mkdir(parents=True, exist_ok=True)
    vorhanden = []
    for datei, beschreibung in STIMMEN:
        modell = ordner / f"{datei}.onnx"
        konfig = ordner / f"{datei}.onnx.json"
        if not (modell.is_file() and konfig.is_file()):
            ausgabe(f"  Lade {beschreibung} ...")
            try:
                _laden(url(datei, ".onnx.json"), konfig, ausgabe)
                _laden(url(datei, ".onnx"), modell, ausgabe)
            except Exception as e:
                ausgabe(f"     fehlgeschlagen ({e})")
                ausgabe(f"     Von Hand: {url(datei, '.onnx')}")
                ausgabe(f"     und {url(datei, '.onnx.json')}")
                ausgabe(f"     im Browser laden und nach {ordner} legen.")
                continue
        vorhanden.append(datei)
    return vorhanden


def piper_installieren(ausgabe=print) -> bool:
    try:
        import piper  # noqa: F401

        return True
    except ImportError:
        pass
    ausgabe("Installiere Piper (einmalig) ...")
    ergebnis = subprocess.run([sys.executable, "-m", "pip", "install", "piper-tts", "sounddevice"])
    if ergebnis.returncode != 0:
        ausgabe("Piper konnte nicht installiert werden.")
        return False
    import importlib

    importlib.invalidate_caches()
    return True


def config_setzen(pfad: Path, werte: dict) -> None:
    """Setzt Eintraege im Abschnitt [sprachausgabe] der config.toml, Rest bleibt."""
    from ..config import eintraege_setzen

    eintraege_setzen(pfad, "sprachausgabe", werte)


def einrichten(ordner: Path, cfg_sprache: dict, eingabe=input, ausgabe=print) -> int:
    """Stimmen laden, vorspielen, Auswahl in config.toml eintragen."""
    if not piper_installieren(ausgabe):
        return 1
    stimmen_ordner = ordner / STIMMEN_ORDNER
    ausgabe("Lade die deutschen Stimmen (einmalig, zusammen ca. 400 MB) ...")
    vorhanden = herunterladen(stimmen_ordner, ausgabe)
    if not vorhanden:
        ausgabe("Keine Stimme verfügbar.")
        return 1
    geraet = cfg_sprache.get("ausgabegeraet", "")
    tempo = cfg_sprache.get("tempo", 2)
    beschreibung = dict(STIMMEN)

    def vorspielen(datei: str, funk: bool = False) -> None:
        try:
            stimme = PiperStimme(stimmen_ordner / f"{datei}.onnx", tempo=tempo, geraet=geraet,
                                 funk=funk)
            stimme.sprechen(PROBETEXT)
        except Exception as e:
            ausgabe(f"     konnte nicht abgespielt werden: {e}")

    while True:
        ausgabe("\nDie Stimmen werden jetzt nacheinander vorgespielt:")
        for nr, datei in enumerate(vorhanden, start=1):
            ausgabe(f"  {nr}  {beschreibung[datei]}")
            vorspielen(datei)
        ausgabe("\n  0  Windows-Stimme behalten")
        wahl = eingabe("\nNummer eingeben und Enter drücken (nur Enter = noch einmal anhören): ").strip()
        if wahl == "":
            continue
        if wahl == "0":
            config_setzen(ordner / "config.toml", {"engine": "windows"})
            ausgabe("Es bleibt bei der Windows-Stimme.")
            return 0
        if wahl.isdigit() and 1 <= int(wahl) <= len(vorhanden):
            gewaehlt = vorhanden[int(wahl) - 1]
            break
        ausgabe("Diese Nummer gibt es nicht.")

    ausgabe(f"\nGewählt: {beschreibung[gewaehlt]}. Jetzt dieselbe Stimme mit Funk-Effekt:")
    vorspielen(gewaehlt, funk=True)
    funk = eingabe("Mit Funk-Effekt? (j = ja, n = nein): ").strip().lower().startswith("j")
    config_setzen(ordner / "config.toml",
                  {"engine": "piper", "piper_stimme": gewaehlt, "funkeffekt": funk})
    ausgabe("\nEingetragen in config.toml. Beim nächsten Start von start.bat spricht die neue Stimme.")
    return 0
