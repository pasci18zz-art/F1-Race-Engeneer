"""Natuerliche Stimme (Piper): Einrichtung, config.toml, Funk-Effekt, Rueckfall."""

import os
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest import mock

from renningenieur import config as konfig
from renningenieur.sprache import piper_stimme as ps
from renningenieur.sprache.stimmen import KonsolenStimme, StummeStimme, stimme_erzeugen


class TestUrl(unittest.TestCase):
    def test_url_der_offiziellen_liste(self):
        self.assertEqual(
            ps.url("de_DE-thorsten-high", ".onnx"),
            "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/de/de_DE/thorsten/high/"
            "de_DE-thorsten-high.onnx?download=true")
        self.assertIn("/eva_k/x_low/de_DE-eva_k-x_low.onnx.json",
                      ps.url("de_DE-eva_k-x_low", ".onnx.json"))


class TestConfigSetzen(unittest.TestCase):
    def test_nur_der_abschnitt_sprachausgabe_aendert_sich(self):
        ordner = Path(tempfile.mkdtemp())
        pfad = ordner / "config.toml"
        original = (konfig.STANDARD / "config.toml").read_text(encoding="utf-8")
        pfad.write_text(original.replace('tempo = 2', 'tempo = 5'), encoding="utf-8")
        ps.config_setzen(pfad, {"engine": "piper", "piper_stimme": "de_DE-kerstin-low",
                                "funkeffekt": True})
        cfg = konfig.config_laden(ordner)
        self.assertEqual(cfg["sprachausgabe"]["engine"], "piper")
        self.assertEqual(cfg["sprachausgabe"]["piper_stimme"], "de_DE-kerstin-low")
        self.assertIs(cfg["sprachausgabe"]["funkeffekt"], True)
        self.assertEqual(cfg["sprachausgabe"]["tempo"], 5)  # eigene Einstellung bleibt
        self.assertEqual(cfg["udp"]["port"], 20777)
        self.assertIn("# Teil des Gerätenamens", pfad.read_text(encoding="utf-8"))  # Kommentare bleiben

    def test_alte_config_ohne_neue_eintraege(self):
        pfad = Path(tempfile.mkdtemp()) / "config.toml"
        pfad.write_text('[udp]\nport = 20777\n\n[sprachausgabe]\nengine = "windows"\ntempo = 2\n\n'
                        '[mikrofon]\ngeraet = ""\n', encoding="utf-8")
        ps.config_setzen(pfad, {"engine": "piper", "funkeffekt": False})
        daten = tomllib.loads(pfad.read_text(encoding="utf-8"))
        self.assertEqual(daten["sprachausgabe"], {"engine": "piper", "funkeffekt": False, "tempo": 2})
        self.assertEqual(daten["mikrofon"], {"geraet": ""})

    def test_datei_ohne_abschnitt(self):
        pfad = Path(tempfile.mkdtemp()) / "config.toml"
        ps.config_setzen(pfad, {"engine": "piper"})
        self.assertEqual(tomllib.loads(pfad.read_text(encoding="utf-8")),
                         {"sprachausgabe": {"engine": "piper"}})


class TestFunkeffekt(unittest.TestCase):
    def test_bandpass_und_rauschen_am_ende(self):
        import numpy as np

        rate = 22050
        t = np.arange(rate) / rate
        tief = np.sin(2 * np.pi * 100 * t)    # Brummen, soll weg
        mitte = np.sin(2 * np.pi * 1000 * t)  # Sprache, soll bleiben
        aus = ps.funkeffekt((tief + mitte) / 2, rate)
        self.assertGreater(len(aus), rate)  # Rauschen hinten angehaengt
        self.assertLessEqual(np.max(np.abs(aus)), 1.5)
        spektrum = np.abs(np.fft.rfft(aus[:rate]))
        freq = np.fft.rfftfreq(rate, 1 / rate)
        self.assertLess(spektrum[np.argmin(abs(freq - 100))] * 20,
                        spektrum[np.argmin(abs(freq - 1000))])


class TestEinrichten(unittest.TestCase):
    def test_ablauf_mit_auswahl_und_funkeffekt(self):
        ordner = Path(tempfile.mkdtemp())
        (ordner / "config.toml").write_text(
            (konfig.STANDARD / "config.toml").read_text(encoding="utf-8"), encoding="utf-8")
        gesprochen = []

        class FalscheStimme:
            def __init__(self, modell, tempo=0, geraet="", funk=False, **_):
                self.name, self.funk = Path(modell).stem, funk

            def sprechen(self, text):
                gesprochen.append((self.name, self.funk))

        eingaben = iter(["", "2", "j"])  # erst noch mal anhoeren, dann Stimme 2, mit Funk
        with mock.patch.object(ps, "piper_installieren", return_value=True), \
                mock.patch.object(ps, "herunterladen",
                                  return_value=["de_DE-thorsten-high", "de_DE-kerstin-low"]), \
                mock.patch.object(ps, "PiperStimme", FalscheStimme):
            ergebnis = ps.einrichten(ordner, {"tempo": 2}, eingabe=lambda _: next(eingaben),
                                     ausgabe=lambda *a, **k: None)
        self.assertEqual(ergebnis, 0)
        self.assertEqual(gesprochen, [("de_DE-thorsten-high", False), ("de_DE-kerstin-low", False)] * 2
                         + [("de_DE-kerstin-low", True)])
        cfg = konfig.config_laden(ordner)["sprachausgabe"]
        self.assertEqual((cfg["engine"], cfg["piper_stimme"], cfg["funkeffekt"]),
                         ("piper", "de_DE-kerstin-low", True))

    def test_windows_stimme_behalten(self):
        ordner = Path(tempfile.mkdtemp())
        with mock.patch.object(ps, "piper_installieren", return_value=True), \
                mock.patch.object(ps, "herunterladen", return_value=["de_DE-ramona-low"]), \
                mock.patch.object(ps, "PiperStimme", mock.MagicMock()):
            ps.einrichten(ordner, {}, eingabe=lambda _: "0", ausgabe=lambda *a, **k: None)
        self.assertEqual(konfig.config_laden(ordner)["sprachausgabe"]["engine"], "windows")


class TestRueckfall(unittest.TestCase):
    def test_fehlende_stimme_faellt_auf_windows_bzw_text_zurueck(self):
        with self.assertLogs("renningenieur.sprache.stimmen", level="ERROR"):
            stimme = stimme_erzeugen({"engine": "piper", "piper_stimme": "gibts-nicht"},
                                     Path(tempfile.mkdtemp()))
        self.assertIsInstance(stimme, KonsolenStimme)  # unter Windows: Windows-Stimme

    def test_aus(self):
        self.assertIsInstance(stimme_erzeugen({"engine": "aus"}), StummeStimme)


@unittest.skipUnless(os.environ.get("PIPER_TESTSTIMME"), "PIPER_TESTSTIMME nicht gesetzt")
class TestEchtePiperStimme(unittest.TestCase):
    """Nur mit installiertem Piper und einer Stimme: PIPER_TESTSTIMME=pfad/zur/stimme.onnx"""

    def test_sprechen(self):
        abgespielt = []
        stimme = ps.PiperStimme(Path(os.environ["PIPER_TESTSTIMME"]), tempo=2,
                                spieler=lambda audio, rate, geraet: abgespielt.append((len(audio), rate)))
        stimme.sprechen("Hülkenberg hinter dir kommt an die Box. Undercut-Gefahr.")
        laenge, rate = abgespielt[0]
        self.assertGreater(laenge / rate, 1.5)
        stimme.funk = True
        stimme.sprechen("Box, Box.")
        self.assertEqual(len(abgespielt), 2)


if __name__ == "__main__":
    unittest.main()
