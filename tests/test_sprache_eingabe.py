"""Spracheingabe: Aufbereitung, Pegel, Mikrofontest, Whisper-Einrichtung, SimHub-Pruefung."""

import socket
import tempfile
import time
import tomllib
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from renningenieur import config as konfig
from renningenieur.sprache import audio, erkennung, mikrofon, mikrofontest, whisper_einrichtung
from renningenieur.sprache.sprechfunk import Sprechfunk
from renningenieur.telemetrie.relay import Relay, _Ziel

RATE = 16000


def sinus(hz: float, db: float, sekunden: float = 1.5, rate: int = RATE) -> np.ndarray:
    t = np.arange(int(sekunden * rate)) / rate
    return (10 ** (db / 20.0) * np.sin(2 * np.pi * hz * t)).astype(np.float32)


def pcm(x: np.ndarray) -> bytes:
    return audio.als_pcm(x)


class TestAudio(unittest.TestCase):
    def test_pegel(self):
        p = audio.messen(pcm(sinus(500, -20)), RATE)
        self.assertAlmostEqual(p.spitze_db, -20, delta=0.5)
        self.assertAlmostEqual(p.dauer, 1.5, delta=0.01)
        self.assertEqual(p.urteil, "gut")
        self.assertEqual(audio.messen(pcm(sinus(500, -40)), RATE).urteil, "leise")
        self.assertEqual(audio.messen(pcm(sinus(500, -70)), RATE).urteil, "leer")
        self.assertEqual(audio.messen(pcm(sinus(500, -20, 0.2)), RATE).urteil, "kurz")
        laut = np.clip(sinus(500, 6), -1, 1)
        self.assertEqual(audio.messen(pcm(laut), RATE).urteil, "uebersteuert")
        self.assertEqual(audio.messen(b"", RATE).dauer, 0.0)

    def test_leises_signal_wird_angehoben(self):
        leise = sinus(800, -45)
        neu, gain = audio.aufbereiten(pcm(leise), RATE)
        self.assertAlmostEqual(gain, 30.0, delta=0.5)  # Obergrenze der Verstaerkung
        mittel = sinus(800, -30)
        neu, gain = audio.aufbereiten(pcm(mittel), RATE)
        self.assertAlmostEqual(gain, 24.0, delta=1.0)
        self.assertAlmostEqual(audio.messen(neu, RATE).spitze_db, -6, delta=1.0)

    def test_laute_aufnahme_bleibt_unveraendert_laut(self):
        neu, gain = audio.aufbereiten(pcm(sinus(800, -3)), RATE)
        self.assertEqual(gain, 0.0)
        self.assertGreater(audio.messen(neu, RATE).spitze_db, -8)

    def test_rumpeln_und_gleichanteil_werden_entfernt(self):
        x = sinus(40, -12) + sinus(1000, -30) + 0.05
        neu = audio.als_float(audio.aufbereiten(pcm(x), RATE)[0])
        spektrum = np.abs(np.fft.rfft(neu))
        freq = np.fft.rfftfreq(len(neu), 1 / RATE)
        stark = spektrum[np.argmin(abs(freq - 1000))]
        self.assertLess(spektrum[np.argmin(abs(freq - 40))], stark / 20)
        self.assertLess(abs(float(np.mean(neu))), 0.001)

    def test_rauschen_wird_nicht_verstaerkt(self):
        rauschen = np.random.default_rng(1).normal(0, 10 ** (-72 / 20), RATE).astype(np.float32)
        daten = pcm(rauschen)
        neu, gain = audio.aufbereiten(daten, RATE)
        self.assertEqual(gain, 0.0)
        self.assertEqual(neu, daten)

    def test_umrechnen_auf_16k(self):
        for rate in (8000, 44100, 48000):
            x = sinus(1000, -10, 1.0, rate)
            y = audio.auf_16k(x, rate)
            self.assertEqual(len(y), 16000)
            spektrum = np.abs(np.fft.rfft(y))
            self.assertAlmostEqual(np.fft.rfftfreq(len(y), 1 / 16000)[np.argmax(spektrum)], 1000, delta=5)
        self.assertEqual(len(audio.auf_16k(sinus(1000, -10), 16000)), 24000)

    def test_wav_wird_geschrieben(self):
        pfad = Path(tempfile.mkdtemp()) / "a.wav"
        audio.als_wav(pcm(sinus(500, -10, 0.5)), RATE, pfad)
        import wave

        with wave.open(str(pfad)) as w:
            self.assertEqual((w.getnchannels(), w.getsampwidth(), w.getframerate()), (1, 2, RATE))
            self.assertEqual(w.getnframes(), 8000)


class TestMikrofonEinstellung(unittest.TestCase):
    def test_nachlauf_hat_ein_minimum(self):
        self.assertEqual(mikrofon.Mikrofon(nachlauf=0.3).nachlauf, 0.4)
        self.assertEqual(mikrofon.Mikrofon(nachlauf=0.7).nachlauf, 0.7)

    def test_aufnahme_mit_vorlauf(self):
        m = mikrofon.Mikrofon(vorlauf=0.2, nachlauf=0.4)
        m.nachlauf = 0.0
        m._ring = __import__("collections").deque(maxlen=5)
        m._max_bytes = 10_000
        for i in range(8):
            m._callback(bytes([i]) * 100, 50, None, None)
        m.aufnahme_start()
        m._callback(b"\xaa" * 100, 50, None, None)
        daten = m.aufnahme_stopp()
        self.assertEqual(daten[:100], bytes([3]) * 100)  # die letzten 5 Bloecke vor dem Druck
        self.assertEqual(len(daten), 600)


class FalschesMikrofon:
    name = "Test-Mikrofon"
    samplerate = RATE

    def __init__(self, signal: np.ndarray):
        self.signal = signal
        self.gestartet = False

    def aufnahme_start(self):
        self.gestartet = True

    def aufnahme_stopp(self) -> bytes:
        return pcm(self.signal)

    def stop(self):
        pass


class FalscheErkennung:
    def __init__(self, name: str, text: str):
        self.name, self.text, self.gehoert = name, text, None

    def erkennen(self, daten: bytes, rate: int) -> str:
        self.gehoert = (len(daten), rate)
        return self.text


class TestSprechfunk(unittest.TestCase):
    def aufbau(self, signal, text="wie viele sekunden zum auto vor mir"):
        from tests.hilfe import kern_erzeugen

        kern, stimme = kern_erzeugen()
        cfg = konfig.config_laden()
        ordner = Path(tempfile.mkdtemp())
        funk = Sprechfunk(kern, cfg, ordner)
        funk.mikrofon = FalschesMikrofon(signal)
        funk.erkennung = FalscheErkennung("Test", text)
        return funk, kern, stimme, ordner

    def test_leise_aufnahme_wird_verstaerkt_gespeichert_und_erkannt(self):
        funk, kern, stimme, ordner = self.aufbau(sinus(700, -42))
        with self.assertLogs("renningenieur.sprache.sprechfunk", level="INFO") as log:
            text = funk.verstehen(pcm(sinus(700, -42)), RATE)
        self.assertEqual(text, "wie viele sekunden zum auto vor mir")
        meldungen = "\n".join(log.output)
        self.assertIn("Aufnahme: 1.5 s, Spitze -42 dB", meldungen)
        self.assertIn("sehr leise", meldungen)
        self.assertIn("Verstanden: wie viele sekunden zum auto vor mir  (Test", meldungen)
        self.assertIn("Verstärkung 30 dB", meldungen)
        self.assertTrue((ordner / "letzte_aufnahme.wav").is_file())
        # die Erkennung hat die aufbereitete (laute) Aufnahme bekommen
        self.assertEqual(funk.erkennung.gehoert, (len(pcm(sinus(700, -42))), RATE))

    def test_leere_und_kurze_aufnahme_geht_nicht_an_die_erkennung(self):
        for signal, hinweis in ((sinus(700, -80), "Fast nichts aufgenommen"),
                                (sinus(700, -10, 0.2), "zu kurz")):
            funk, *_ = self.aufbau(signal)
            with self.assertLogs("renningenieur.sprache.sprechfunk", level="WARNING") as log:
                self.assertEqual(funk.verstehen(pcm(signal), RATE), "")
            self.assertIn(hinweis, "\n".join(log.output))
            self.assertIsNone(funk.erkennung.gehoert)

    def test_ohne_ergebnis_sagt_der_ingenieur_es(self):
        funk, kern, stimme, _ = self.aufbau(sinus(700, -10), text="")
        funk._auswerten()
        self.assertEqual(stimme.gesagt[-1] in ("Ich habe nichts gehört.", "Bitte noch mal."), True)
        self.assertFalse(kern.funk.stumm)

    def test_aufnahme_speichern_abschaltbar(self):
        funk, kern, stimme, ordner = self.aufbau(sinus(700, -10))
        funk.cfg["mikrofon"]["aufnahme_speichern"] = False
        funk.verstehen(pcm(sinus(700, -10)), RATE)
        self.assertFalse((ordner / "letzte_aufnahme.wav").exists())


class TestMikrofontest(unittest.TestCase):
    def test_ablauf(self):
        ausgaben = []
        ordner = Path(tempfile.mkdtemp())
        mic = FalschesMikrofon(sinus(700, -40))
        vosk, whisper = FalscheErkennung("Vosk", "wie viele sekunden"), FalscheErkennung(
            "Whisper small", "Wie viele Sekunden zum Auto vor mir?")
        eingaben = iter(["", "q"])
        ergebnis = mikrofontest.testen(
            konfig.config_laden(), ordner, ausgabe=lambda *a, **k: ausgaben.append(" ".join(map(str, a))),
            eingabe=lambda _: next(eingaben), mikrofon=mic, erkennungen=[vosk, whisper],
            sekunden=0, warten=lambda s: None, pieps=lambda: None)
        text = "\n".join(ausgaben)
        self.assertEqual(ergebnis, 0)
        self.assertTrue(mic.gestartet)
        self.assertIn("Urteil: zu leise", text)
        self.assertIn("Windows-Eingabelautstärke auf 100", text)
        self.assertIn("Vosk", text)
        self.assertIn("Wie viele Sekunden zum Auto vor mir?", text)
        self.assertIn("Thema: abstand", text)
        self.assertTrue((ordner / "mikrofontest.wav").is_file())


class TestErkennungHilfen(unittest.TestCase):
    def test_erfundene_saetze_werden_verworfen(self):
        prompt = erkennung.whisper_prompt(["Verstappen", "Hamilton"])
        for text in ("", "Untertitel der Amara.org-Community", "Vielen Dank.",
                     "Funk an den Renningenieur in der Formel 1. Fragen zu Abstand, Reifen"):
            self.assertTrue(erkennung._erfunden(text, prompt), text)
        for text in ("Wie viele Sekunden zum Auto vor mir?", "Wie ist das Wetter",
                     "Funk Reifen Verschleiß von Verstappen"):
            self.assertFalse(erkennung._erfunden(text, prompt), text)

    def test_prompt_enthaelt_die_fahrernamen(self):
        self.assertIn("Verstappen, Hamilton", erkennung.whisper_prompt(["Verstappen", "Hamilton"]))

    def test_whisper_fehlt_faellt_auf_vosk_zurueck(self):
        vosk = mock.MagicMock(name="vosk")
        with mock.patch.object(erkennung, "WhisperErkennung", side_effect=ImportError("faster_whisper")), \
                mock.patch.object(erkennung, "Erkennung", vosk), \
                self.assertLogs("renningenieur.sprache.erkennung", level="WARNING") as log:
            e = erkennung.erkennung_erzeugen({"engine": "whisper"}, Path("."), None, ["Verstappen"])
        self.assertIs(e, vosk.return_value)
        self.assertIn("whisper.bat", "\n".join(log.output))

    def test_vosk_ist_standard(self):
        vosk = mock.MagicMock()
        with mock.patch.object(erkennung, "Erkennung", vosk):
            erkennung.erkennung_erzeugen({}, Path("/x"), None)
        self.assertEqual(vosk.call_args.args[0], str(Path("/x") / "modelle/vosk-model-small-de-0.15"))


class TestWhisperEinrichtung(unittest.TestCase):
    def test_ablauf_traegt_config_ein(self):
        ordner = Path(tempfile.mkdtemp())
        (ordner / "config.toml").write_text(
            '[spracherkennung]\naktiv = true\nwortliste = false\n\n[funktaste]\ntaste = 8\n', encoding="utf-8")
        ausgaben = []
        ergebnis = whisper_einrichtung.einrichten(
            ordner, konfig.config_laden(), "", eingabe=lambda _: "3",
            ausgabe=lambda *a, **k: ausgaben.append(" ".join(map(str, a))),
            installieren=lambda ausgabe: True, messfunktion=lambda m, o, t: 1.7)
        self.assertEqual(ergebnis, 0)
        daten = tomllib.loads((ordner / "config.toml").read_text(encoding="utf-8"))
        self.assertEqual(daten["spracherkennung"]["engine"], "whisper")
        self.assertEqual(daten["spracherkennung"]["whisper_modell"], "small")
        self.assertEqual(daten["spracherkennung"]["aktiv"], True)
        self.assertEqual(daten["funktaste"]["taste"], 8)
        self.assertIn("etwa 1.7 Sekunden", "\n".join(ausgaben))

    def test_modell_per_argument_und_langsamer_pc(self):
        ordner = Path(tempfile.mkdtemp())
        ausgaben = []
        whisper_einrichtung.einrichten(
            ordner, konfig.config_laden(), "base", ausgabe=lambda *a, **k: ausgaben.append(" ".join(map(str, a))),
            installieren=lambda ausgabe: True, messfunktion=lambda m, o, t: 6.0)
        self.assertIn("whisper.bat base", "\n".join(ausgaben))
        self.assertEqual(tomllib.loads((ordner / "config.toml").read_text(encoding="utf-8"))
                         ["spracherkennung"]["whisper_modell"], "base")

    def test_installation_fehlgeschlagen(self):
        self.assertEqual(whisper_einrichtung.einrichten(
            Path(tempfile.mkdtemp()), {}, "small", ausgabe=lambda *a, **k: None,
            installieren=lambda ausgabe: False), 1)

    def test_download_fehlgeschlagen(self):
        def kaputt(*a):
            raise OSError("kein Internet")

        self.assertEqual(whisper_einrichtung.einrichten(
            Path(tempfile.mkdtemp()), {}, "small", ausgabe=lambda *a, **k: None,
            installieren=lambda ausgabe: True, messfunktion=kaputt), 1)

    def test_eintraege_setzen_in_neuer_datei(self):
        pfad = Path(tempfile.mkdtemp()) / "config.toml"
        konfig.eintraege_setzen(pfad, "spracherkennung", {"engine": "whisper", "whisper_threads": 3})
        self.assertEqual(tomllib.loads(pfad.read_text(encoding="utf-8")),
                         {"spracherkennung": {"engine": "whisper", "whisper_threads": 3}})


class TestSimHubPruefung(unittest.TestCase):
    @staticmethod
    def senden(ziel: _Ziel, anzahl: int = 80):
        for _ in range(anzahl):
            ziel.senden(b"x" * 40)
            time.sleep(0.001)

    def test_ziel_ohne_zuhoerer_wird_erkannt(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.bind(("127.0.0.1", 0))
        adresse = s.getsockname()
        s.close()
        ziel = _Ziel(adresse)
        self.assertEqual(ziel.zustand(), "unbekannt")
        self.senden(ziel)
        self.assertEqual(ziel.zustand(), "abgelehnt")
        ziel.schliessen()

    def test_ziel_mit_zuhoerer_ist_ok(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.bind(("127.0.0.1", 0))
        ziel = _Ziel(s.getsockname())
        self.senden(ziel)
        self.assertEqual(ziel.zustand(), "ok")
        ziel.schliessen()
        s.close()

    def test_relay_meldet_den_zustand_der_ziele(self):
        offen = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        offen.bind(("127.0.0.1", 0))
        zu = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        zu.bind(("127.0.0.1", 0))
        zu_adresse = zu.getsockname()
        zu.close()
        relay = Relay("127.0.0.1", 0, [offen.getsockname(), zu_adresse])
        relay.start()
        try:
            sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            for _ in range(80):
                sender.sendto(b"y" * 40, ("127.0.0.1", relay.port))
                time.sleep(0.003)
            time.sleep(0.2)
            zustaende = dict(relay.pruefe_ziele())
            self.assertEqual(zustaende[offen.getsockname()], "ok")
            self.assertEqual(zustaende[zu_adresse], "abgelehnt")
            sender.close()
        finally:
            relay.stop()
            offen.close()

    def test_meldung_im_fenster(self):
        from renningenieur import app

        class Relay_:
            empfangen = 100
            ablauf = iter([[(("127.0.0.1", 20778), "abgelehnt")], [(("127.0.0.1", 20778), "abgelehnt")],
                           [(("127.0.0.1", 20778), "ok")]])

            def pruefe_ziele(self):
                return next(self.ablauf)

        bisher: dict = {}
        with self.assertLogs("renningenieur", level="INFO") as log:
            for _ in range(3):
                app._ziele_pruefen(Relay_(), bisher)
        meldungen = log.output
        self.assertEqual(len(meldungen), 2)  # nur bei Aenderungen
        self.assertIn("Dort hört niemand zu", meldungen[0])
        self.assertIn("UDP-Port 20778", meldungen[0])
        self.assertIn("funktioniert wieder", meldungen[1])


if __name__ == "__main__":
    unittest.main()
