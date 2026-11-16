"""Aussprache der Namen, klangaehnliche Namenssuche, Whisper automatisch, Pause am Tablet."""

import tempfile
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

from renningenieur.config import config_laden
from renningenieur.fragen import klang
from renningenieur.sprache import erkennung
from renningenieur.sprache.stimmen import AusspracheStimme, StummeStimme, stimme_erzeugen
from renningenieur.web.server import Webserver

from .hilfe import rennen_fahren


class TestAussprache(unittest.TestCase):
    def setUp(self):
        self.stimme = StummeStimme()
        self.a = AusspracheStimme(self.stimme, config_laden()["aussprache"])

    def test_namen_werden_in_klangschrift_gesprochen(self):
        self.a.sprechen("Leclerc ist vor dir.")
        self.assertEqual(self.stimme.gesagt, ["Leklär ist vor dir."])

    def test_endung_gross_klein_und_mehrere_namen(self):
        self.assertEqual(self.a.umschreiben("Leclercs Reifen. LECLERC und hamilton."),
                         "Leklärs Reifen. Leklär und Hämmilten.")

    def test_mehrwortnamen_und_nur_ganze_woerter(self):
        self.assertEqual(self.a.umschreiben("Aston Martin führt."), "Äston Martin führt.")
        self.assertEqual(self.a.umschreiben("Russelle Rassler"), "Russelle Rassler")  # kein Wortteil

    def test_andere_namen_und_zahlen_bleiben(self):
        text = "Verstappen liegt 0,5 Sekunden vor dir."
        self.assertEqual(self.a.umschreiben(text), text)

    def test_eigene_eintraege_und_leere_liste(self):
        eigene = AusspracheStimme(self.stimme, {"Marco": "Markko"})
        self.assertEqual(eigene.umschreiben("Marco fährt."), "Markko fährt.")
        leer = AusspracheStimme(self.stimme, {})
        self.assertEqual(leer.umschreiben("Leclerc"), "Leclerc")

    def test_durchreichen_an_die_echte_stimme(self):
        self.a.schliessen()
        self.assertEqual(self.a.gesagt, [])

    def test_wird_nur_um_echte_stimmen_gelegt(self):
        # "aus" ist stumm: dort braucht es keine Umschreibung
        self.assertIsInstance(stimme_erzeugen({"engine": "aus"}, None, {"Leclerc": "Leklär"}), StummeStimme)

    def test_standard_enthaelt_die_wichtigen_namen(self):
        woerter = config_laden()["aussprache"]
        for name in ("Leclerc", "Hamilton", "Russell", "Gasly", "Ocon", "Lawson", "Hadjar"):
            self.assertIn(name, woerter)
        self.assertEqual(woerter["Leclerc"], "Leklär")


class TestKlangsuche(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kern, _ = rennen_fahren("trocken", bis=300)
        cls.f = cls.kern.fragen

    def test_klang_gleich_geschriebene_aussprachen(self):
        self.assertEqual(klang("Leckler"), klang("Lecler"))
        self.assertEqual(klang("fair stappen"), klang("verstappen"))
        self.assertEqual(klang("Rassel"), klang("Russell"))
        self.assertEqual(klang("Gasli"), klang("Gasly"))

    def test_verhoerer_werden_dem_richtigen_fahrer_zugeordnet(self):
        for frage, name in (("wie weit ist leckler vor mir", "Leclerc"),
                            ("wo ist le clerc", "Leclerc"),
                            ("abstand zu rassel", "Russell"),
                            ("was fährt fair stappen für reifen", "Verstappen"),
                            ("wie viel hat birman", "Bearman")):
            self.assertIn(name, self.f.antwort(frage), frage)

    def test_normale_woerter_werden_nicht_zu_fahrern(self):
        antwort = self.f.antwort("wie lange halten meine reifen")  # "halten" klingt nach "Hamilton"
        self.assertNotIn("Hamilton", antwort)
        self.assertIn("Verschleiß", antwort)


class TestWhisperAutomatisch(unittest.TestCase):
    def test_ohne_installation_bleibt_es_bei_vosk(self):
        ordner = Path(tempfile.mkdtemp())
        self.assertFalse(erkennung.whisper_vorhanden(ordner))
        with mock.patch.object(erkennung, "Erkennung") as vosk:
            erkennung.erkennung_erzeugen({"engine": "auto"}, ordner, None, ["Leclerc"])
        vosk.assert_called_once()

    def test_mit_installation_wird_whisper_genommen(self):
        ordner = Path(tempfile.mkdtemp())
        with mock.patch.object(erkennung, "whisper_vorhanden", return_value=True), \
                mock.patch.object(erkennung, "WhisperErkennung") as whisper:
            erkennung.erkennung_erzeugen({"engine": "auto", "whisper_modell": "small"}, ordner, None,
                                         ["Leclerc", "Norris"])
        args = whisper.call_args.args
        self.assertEqual(args[0], "small")
        self.assertIn("Leclerc", args[2])  # Hinweistext
        self.assertEqual(args[4], "Leclerc Norris")  # bevorzugte Woerter

    def test_vosk_bleibt_vosk(self):
        ordner = Path(tempfile.mkdtemp())
        with mock.patch.object(erkennung, "whisper_vorhanden", return_value=True), \
                mock.patch.object(erkennung, "WhisperErkennung") as whisper, \
                mock.patch.object(erkennung, "Erkennung") as vosk:
            erkennung.erkennung_erzeugen({"engine": "vosk"}, ordner, None, [])
        whisper.assert_not_called()
        vosk.assert_called_once()

    def test_standard_ist_auto(self):
        self.assertEqual(config_laden()["spracherkennung"]["engine"], "auto")


class TestPauseAmTablet(unittest.TestCase):
    def test_standard_ist_eine_sekunde_und_die_seite_hat_die_auswahl(self):
        self.assertEqual(config_laden()["tablet"]["stille_sekunden"], 1.0)
        kern, _ = rennen_fahren("trocken", bis=10)
        web = Webserver(kern, "127.0.0.1", 0)
        web.start()
        try:
            basis = f"http://127.0.0.1:{web.port}"
            import json
            with urllib.request.urlopen(basis + "/api/info") as r:
                self.assertEqual(json.loads(r.read())["stille_sekunden"], 1.0)
            with urllib.request.urlopen(basis + "/") as r:
                self.assertIn('id="stille-wahl"', r.read().decode())
            with urllib.request.urlopen(basis + "/mikro.js") as r:
                js = r.read().decode()
            self.assertIn("stilleSekunden()", js)
            self.assertIn("renningenieur.stille", js)
        finally:
            web.stop()


if __name__ == "__main__":
    unittest.main()
