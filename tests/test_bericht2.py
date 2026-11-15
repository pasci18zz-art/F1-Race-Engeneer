"""Rundenstaende, Sprintrennen, Qualifying gesamt (Q1+Q2+Q3) und Download."""

import json
import os
import tempfile
import unittest
import urllib.request
from pathlib import Path

from renningenieur import bericht
from renningenieur.config import config_laden, texte_laden
from renningenieur.datenbank import Datenbank
from renningenieur.kern import Kern
from renningenieur.schnappschuss import schnappschuss
from renningenieur.simulator import Simulator
from renningenieur.sprache.stimmen import StummeStimme
from renningenieur.web.server import Webserver

from .hilfe import enthaelt, kern_erzeugen, rennen_fahren


def fahre(kern, **sim):
    for _, paket in Simulator(**sim).pakete():
        kern.paket(paket)
    return kern


class TestRundenstaende(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kern, _ = rennen_fahren("trocken")
        cls.z = cls.kern.zustand

    def test_jede_runde_hat_eine_komplette_reihenfolge(self):
        self.assertEqual(sorted(self.z.rundenstaende), list(range(1, 13)))
        for nr, stand in self.z.rundenstaende.items():
            positionen = [e["position"] for e in stand["reihenfolge"]]
            self.assertEqual(positionen, list(range(1, 21)), f"Runde {nr}")
            self.assertEqual(len({e["idx"] for e in stand["reihenfolge"]}), 20)

    def test_enthaelt_abstand_reifen_und_status(self):
        zweiter = self.z.rundenstaende[3]["reihenfolge"][1]
        for feld in ("idx", "name", "team", "rueckstand_ms", "intervall_ms", "reifen",
                     "reifenalter", "in_box", "ausgefallen"):
            self.assertIn(feld, zweiter)
        self.assertGreater(zweiter["rueckstand_ms"], 0)

    def test_im_bericht_und_im_text(self):
        daten = schnappschuss(self.z, mit_runden=True)
        b = bericht.bericht_bauen(daten)
        self.assertEqual([v["runde"] for v in b["positionsverlauf"]], list(range(1, 13)))
        text = bericht.bericht_text(b)
        for nr in (1, 7, 12):
            self.assertIn(f"Runde {nr:>2}: 1.", text)
        self.assertIn("1.", text.split("Reihenfolge nach jeder Runde")[1])

    def test_lange_rennen_werden_nicht_ausgeduennt(self):
        kern, _ = rennen_fahren("trocken", runden=30)
        text = bericht.bericht_text(bericht.bericht_bauen(schnappschuss(kern.zustand, mit_runden=True)))
        for nr in range(1, 31):
            self.assertIn(f"Runde {nr:>2}: 1.", text)

    def test_datenbank_behaelt_die_staende(self):
        db = Datenbank(os.path.join(tempfile.mkdtemp(), "r.sqlite"))
        db.sichern(self.z)
        d = db.session(db.sessions()[0]["id"])
        self.assertEqual([r["runde"] for r in d["rundenstaende"]], list(range(1, 13)))
        self.assertEqual(len(d["rundenstaende"][4]["reihenfolge"]), 20)
        b = bericht.bericht_bauen(d)
        self.assertEqual(len(b["positionsverlauf"]), 12)

    def test_flashback_verwirft_spaetere_staende(self):
        kern, _ = rennen_fahren("trocken", bis=300)
        z = kern.zustand
        vorher = max(z.rundenstaende)
        kern.auswertung._nach_flashback(100.0)
        self.assertTrue(all(s["zeit"] <= 100.0 for s in z.rundenstaende.values()))
        self.assertLess(max(z.rundenstaende, default=0), vorher)

    def test_nicht_im_quali(self):
        kern, _ = rennen_fahren("qualifying", runden=3)
        self.assertEqual(kern.zustand.rundenstaende, {})

    def test_alte_session_ohne_staende_bekommt_verlauf_aus_den_runden(self):
        daten = schnappschuss(self.z, mit_runden=True)
        daten["rundenstaende"] = []
        b = bericht.bericht_bauen(daten)
        self.assertEqual(len(b["positionsverlauf"]), 12)
        self.assertEqual(b["positionsverlauf"][0]["reihenfolge"][0]["position"], 1)


class TestSprint(unittest.TestCase):
    def test_erstes_rennen_nach_dem_shootout_ist_der_sprint(self):
        kern, _ = kern_erzeugen()
        fahre(kern, szenario="qualifying", runden=2, session_typ=10, wochenende_id=5, seed=1)
        s = schnappschuss(fahre(kern, szenario="trocken", runden=2, wochenende_id=5, seed=2).zustand)["session"]
        self.assertEqual((s["typ_name"], s["ist_sprint"], s["ist_rennen"]), ("Sprintrennen", True, True))
        s = schnappschuss(fahre(kern, szenario="trocken", runden=2, wochenende_id=5, seed=3).zustand)["session"]
        self.assertEqual((s["typ_name"], s["ist_sprint"]), ("Rennen", False))

    def test_normales_wochenende_hat_keinen_sprint(self):
        kern, _ = kern_erzeugen()
        fahre(kern, szenario="qualifying", runden=2, session_typ=5, wochenende_id=6, seed=1)
        s = schnappschuss(fahre(kern, szenario="trocken", runden=2, wochenende_id=6, seed=2).zustand)["session"]
        self.assertEqual((s["typ_name"], s["ist_sprint"]), ("Rennen", False))

    def test_anderes_wochenende_beginnt_von_vorn(self):
        kern, _ = kern_erzeugen()
        fahre(kern, szenario="qualifying", runden=2, session_typ=10, wochenende_id=7, seed=1)
        fahre(kern, szenario="trocken", runden=2, wochenende_id=7, seed=2)
        s = schnappschuss(fahre(kern, szenario="trocken", runden=2, wochenende_id=8, seed=3).zustand)["session"]
        self.assertFalse(s["ist_sprint"])

    def test_ohne_wochenende_kein_sprint_raten(self):
        kern, _ = kern_erzeugen()
        s = schnappschuss(fahre(kern, szenario="trocken", runden=2, wochenende_id=0, seed=1).zustand)["session"]
        self.assertFalse(s["ist_sprint"])

    def test_rundenschwelle(self):
        kern, _ = kern_erzeugen()
        kern.auswertung.sprint_max_runden = 3
        s = schnappschuss(fahre(kern, szenario="trocken", runden=3, wochenende_id=1, seed=1).zustand)["session"]
        self.assertTrue(s["ist_sprint"])
        s = schnappschuss(fahre(kern, szenario="trocken", runden=4, wochenende_id=1, seed=2).zustand)["session"]
        self.assertFalse(s["ist_sprint"])

    def test_automatik_abschaltbar(self):
        cfg = config_laden()
        cfg["sprint"]["auto"] = False
        kern = Kern(cfg, texte_laden(), StummeStimme())
        fahre(kern, szenario="qualifying", runden=2, session_typ=10, wochenende_id=5, seed=1)
        s = schnappschuss(fahre(kern, szenario="trocken", runden=2, wochenende_id=5, seed=2).zustand)["session"]
        self.assertFalse(s["ist_sprint"])

    def test_nach_programmneustart_wird_in_der_datenbank_nachgeschlagen(self):
        pfad = os.path.join(tempfile.mkdtemp(), "s.sqlite")
        db = Datenbank(pfad)
        kern, _ = kern_erzeugen(datenbank=db)
        fahre(kern, szenario="qualifying", runden=2, session_typ=10, wochenende_id=5, seed=1)
        db.sichern(kern.zustand)
        # neues Programm, gleiche Datenbank: das Wochenende ist noch bekannt
        kern2, _ = kern_erzeugen(datenbank=Datenbank(pfad))
        s = schnappschuss(fahre(kern2, szenario="trocken", runden=2, wochenende_id=5, seed=2).zustand)["session"]
        self.assertTrue(s["ist_sprint"])

    def test_ansage_dateiname_datenbank_und_bericht(self):
        db = Datenbank(os.path.join(tempfile.mkdtemp(), "s.sqlite"))
        kern, stimme = kern_erzeugen(datenbank=db)
        fahre(kern, szenario="qualifying", runden=2, session_typ=10, wochenende_id=5, seed=1)
        fahre(kern, szenario="trocken", runden=3, wochenende_id=5, seed=2)
        self.assertTrue(enthaelt(stimme.gesagt, "Sprintrennen in Monza"))
        db.sichern(kern.zustand)
        eintrag = db.sessions()[0]
        self.assertEqual(eintrag["typ_name"], "Sprintrennen")
        d = db.session(eintrag["id"])
        self.assertTrue(d["session"]["ist_sprint"])
        b = bericht.bericht_bauen(d)
        self.assertEqual((b["session"]["typ_name"], b["session"]["art"], b["session"]["ist_sprint"]),
                         ("Sprintrennen", "sprint", True))
        self.assertIn("Sprintrennen_Monza", bericht.dateiname(b, "json"))
        self.assertTrue(bericht.bericht_text(b).startswith("SPRINTRENNEN - MONZA"))

    def test_art_der_sessions(self):
        art = lambda **s: bericht._art({"session_typ": 15, **s})  # noqa: E731
        self.assertEqual(art(ist_rennen=True), "rennen")
        self.assertEqual(art(ist_rennen=True, ist_sprint=True), "sprint")
        self.assertEqual(art(session_typ=6), "qualifying")
        self.assertEqual(art(session_typ=11), "sprint_shootout")
        self.assertEqual(art(session_typ=2), "training")


class TestQualiGesamt(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ordner = Path(tempfile.mkdtemp())
        cls.db = Datenbank(str(cls.ordner / "q.sqlite"))
        cls.kern = Kern(config_laden(), texte_laden(), StummeStimme(), cls.db, cls.ordner)
        cls.nach_teil = {}
        for i, typ in enumerate((5, 6, 7)):
            fahre(cls.kern, szenario="qualifying", runden=3, session_typ=typ, wochenende_id=9, seed=10 + i)
            cls.nach_teil[typ] = sorted(p.name for p in (cls.ordner / "exporte").iterdir())
        gesamt = cls.kern.letzter_export["gesamt"]
        cls.txt = Path(gesamt["txt"]).read_text(encoding="utf-8")
        cls.json = json.loads(Path(gesamt["json"]).read_text(encoding="utf-8"))

    def test_eine_gesamtdatei_die_nach_jedem_teil_aktualisiert_wird(self):
        for typ, dateien in self.nach_teil.items():
            self.assertEqual(sum("Qualifying_gesamt" in d for d in dateien), 2, typ)  # .txt und .json
        self.assertEqual(len([d for d in self.nach_teil[7] if "Qualifying_gesamt" in d]), 2)

    def test_kopf_der_gesamtdatei(self):
        self.assertTrue(self.txt.startswith("QUALIFYING GESAMT - MONZA"))
        self.assertIn("Teile: Q1, Q2, Q3\n", self.txt)
        self.assertNotIn("vorläufig", self.txt)
        s = self.json["session"]
        self.assertEqual((self.json["art"], s["typ_name"], s["teile"], s["abgeschlossen"]),
                         ("quali_gesamt", "Qualifying gesamt", ["Q1", "Q2", "Q3"], True))

    def test_startaufstellung(self):
        end = self.json["endergebnis"]
        self.assertEqual([e["position"] for e in end], list(range(1, 21)))
        self.assertEqual(len({e["idx"] for e in end}), 20)
        self.assertEqual([e["teil"] for e in end], ["Q3"] * 10 + ["Q2"] * 5 + ["Q1"] * 5)
        self.assertEqual([e["ausgeschieden_in"] for e in end], [""] * 10 + ["Q2"] * 5 + ["Q1"] * 5)
        q3 = [e["beste_runde_ms"] for e in end[:10]]
        self.assertEqual(q3, sorted(q3))
        q1 = {e["idx"] for e in self.json["teile"][0]["ergebnis"][-5:]}
        self.assertEqual({e["idx"] for e in end[-5:]}, q1)  # die letzten fuenf sind die aus Q1

    def test_alle_teile_stehen_unten_in_der_datei(self):
        self.assertEqual([t["session"]["quali_teil"] for t in self.json["teile"]], ["Q1", "Q2", "Q3"])
        for name in ("Qualifying 1", "Qualifying 2", "Qualifying 3"):
            self.assertIn(f"# {name}", self.txt)
        self.assertLess(self.txt.index("Endergebnis (Startaufstellung)"), self.txt.index("# Qualifying 1"))

    def test_vorlaeufig_nach_nur_einem_teil(self):
        ordner = Path(tempfile.mkdtemp())
        kern = Kern(config_laden(), texte_laden(), StummeStimme(), None, ordner)
        fahre(kern, szenario="qualifying", runden=3, session_typ=5, wochenende_id=3, seed=1)
        g = json.loads(Path(kern.letzter_export["gesamt"]["json"]).read_text(encoding="utf-8"))
        self.assertFalse(g["session"]["abgeschlossen"])
        self.assertEqual(len(g["endergebnis"]), 20)
        self.assertIn("vorläufiger Stand", Path(kern.letzter_export["gesamt"]["txt"]).read_text(encoding="utf-8"))

    def test_ohne_datenbank_reichen_die_teile_im_speicher(self):
        ordner = Path(tempfile.mkdtemp())
        kern = Kern(config_laden(), texte_laden(), StummeStimme(), None, ordner)
        for i, typ in enumerate((5, 6)):
            fahre(kern, szenario="qualifying", runden=3, session_typ=typ, wochenende_id=4, seed=20 + i)
        g = json.loads(Path(kern.letzter_export["gesamt"]["json"]).read_text(encoding="utf-8"))
        self.assertEqual(g["session"]["teile"], ["Q1", "Q2"])
        self.assertEqual(g["endergebnis"][0]["teil"], "Q2")
        self.assertEqual(g["endergebnis"][-1]["teil"], "Q1")

    def test_kurzes_qualifying_hat_keinen_gesamtbericht(self):
        ordner = Path(tempfile.mkdtemp())
        kern = Kern(config_laden(), texte_laden(), StummeStimme(), None, ordner)
        fahre(kern, szenario="qualifying", runden=3, session_typ=8, wochenende_id=2, seed=1)
        self.assertNotIn("gesamt", kern.letzter_export)
        self.assertIsNone(bericht.quali_gruppe(8))

    def test_sprint_shootout_gesamt(self):
        ordner = Path(tempfile.mkdtemp())
        kern = Kern(config_laden(), texte_laden(), StummeStimme(), None, ordner)
        for i, typ in enumerate((10, 11, 12)):
            fahre(kern, szenario="qualifying", runden=3, session_typ=typ, wochenende_id=12, seed=30 + i)
        g = json.loads(Path(kern.letzter_export["gesamt"]["json"]).read_text(encoding="utf-8"))
        self.assertEqual((g["session"]["typ_name"], g["session"]["teile"]),
                         ("Sprint-Shootout gesamt", ["SQ1", "SQ2", "SQ3"]))

    def test_gesamt_ueber_die_schnittstelle(self):
        web = Webserver(self.kern, "127.0.0.1", 0)
        web.start()
        try:
            basis = f"http://127.0.0.1:{web.port}"
            sid = self.db.wochenende_sessions(self.kern.zustand.saison_id, 9, (5,))[5]
            with urllib.request.urlopen(f"{basis}/api/bericht?id={sid}&format=json&gesamt=1&download=1") as r:
                self.assertIn("Qualifying_gesamt_Monza.json", r.headers["Content-Disposition"])
                g = json.loads(r.read())
            self.assertEqual(g["art"], "quali_gesamt")
            self.assertEqual(len(g["teile"]), 3)
            with urllib.request.urlopen(f"{basis}/api/bericht?id={sid}&format=json") as r:
                einzeln = json.loads(r.read())  # ohne gesamt=1 nur der eine Teil
            self.assertEqual(einzeln["session"]["quali_teil"], "Q1")
            with urllib.request.urlopen(f"{basis}/api/bericht?live=1&format=txt&gesamt=1") as r:
                self.assertTrue(r.read().decode().startswith("QUALIFYING GESAMT"))
        finally:
            web.stop()


class TestDownload(unittest.TestCase):
    def test_dateinamen_sind_ascii(self):
        b = {"erstellt": "2026-01-02T03:04:05", "session": {"begonnen": None, "typ_name": "Rennen",
                                                              "strecke": "Österreich / Spielberg"}}
        name = bericht.dateiname(b, "json")
        self.assertEqual(name, "2026-01-02_03-04-05_Rennen_Oesterreich_Spielberg.json")
        name.encode("ascii")

    def test_json_und_text_haben_passende_typen_und_dateinamen(self):
        kern, _ = rennen_fahren("trocken", runden=3)
        web = Webserver(kern, "127.0.0.1", 0)
        web.start()
        try:
            basis = f"http://127.0.0.1:{web.port}"
            for fmt, typ, endung in (("json", "application/json", ".json"), ("txt", "text/plain", ".txt")):
                with urllib.request.urlopen(f"{basis}/api/bericht?live=1&format={fmt}&download=1") as r:
                    self.assertIn(typ, r.headers["Content-Type"])
                    self.assertIn(endung, r.headers["Content-Disposition"])
                    self.assertTrue(r.read())
        finally:
            web.stop()


if __name__ == "__main__":
    unittest.main()
