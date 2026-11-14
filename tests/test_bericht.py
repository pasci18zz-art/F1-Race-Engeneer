"""Ausfaelle, gelbe Flaggen, Qualifying, Momentaufnahmen, Datenbank und Bericht."""

import json
import os
import sqlite3
import tempfile
import unittest
import urllib.error
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

from .hilfe import enthaelt, rennen_fahren


class TestRenneneignisse(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kern, cls.stimme = rennen_fahren("alles")
        cls.z = cls.kern.zustand

    def test_ausfall_wird_mit_grund_angesagt(self):
        self.assertIn("Verstappen ist wegen eines mechanischen Problems ausgeschieden.",
                      self.stimme.gesagt)

    def test_ausfall_wird_gemerkt(self):
        self.assertEqual(len(self.z.ausfaelle), 1)
        e = self.z.ausfaelle[0]
        self.assertEqual((e["name"], e["runde"], e["grund"]), ("Verstappen", 5, "mechanisches Problem"))
        self.assertEqual(e["position"], 1)  # lag zum Zeitpunkt des Ausfalls vorn

    def test_ausfall_ist_letzter_platz(self):
        self.assertEqual(self.z.autos[0].position, 20)

    def test_gelbe_flagge_mit_sektor(self):
        self.assertTrue(enthaelt(self.stimme.gesagt, "Gelbe Flagge in Sektor 2."))
        texte = [e["text"] for e in self.z.ereignis_log if e["code"] == "GELB"]
        self.assertEqual(texte, ["Gelbe Flagge in Sektor 2", "Gelbe Flagge beendet"])

    def test_frage_nach_ausfaellen(self):
        antwort = self.kern.fragen.antwort("wer ist ausgefallen")
        self.assertIn("Verstappen", antwort)
        self.assertIn("Runde 5", antwort)
        self.assertIn("mechanisches Problem", antwort)

    def test_momentaufnahmen(self):
        gruende = [m["grund"] for m in self.z.momentaufnahmen]
        self.assertEqual(gruende, ["start", "safety_car", "gruen", "rote_flagge", "restart",
                                   "zwischenstand"])
        sc = self.z.momentaufnahmen[1]
        self.assertEqual(len(sc["reihenfolge"]), 20)
        self.assertTrue(sc["reihenfolge"][-1]["ausgefallen"])  # Verstappen steht hinten
        self.assertEqual([r["position"] for r in sc["reihenfolge"]], list(range(1, 21)))

    def test_ausfaelle_im_schnappschuss(self):
        d = schnappschuss(self.z)
        self.assertEqual(d["ausfaelle"][0]["name"], "Verstappen")
        self.assertNotIn("momentaufnahmen", d)  # gross: nur mit mit_runden
        self.assertEqual(d["momentaufnahmen_anzahl"], 6)
        verstappen = next(a for a in d["autos"] if a["idx"] == 0)
        self.assertEqual(verstappen["ausfall_grund"], "mechanisches Problem")
        self.assertEqual(verstappen["ausgefallen_runde"], 5)
        self.assertEqual(len(schnappschuss(self.z, mit_runden=True)["momentaufnahmen"]), 6)

    def test_keine_ansage_vor_dem_ausfall(self):
        kern, stimme = rennen_fahren("alles", bis=1)  # nur der Anfang
        self.assertFalse(enthaelt(stimme.gesagt, "ausgeschieden"))


class TestQualifying(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kern, cls.stimme = rennen_fahren("qualifying", runden=4)
        cls.z = cls.kern.zustand

    def auto(self, name):
        return next(a for a in self.z.autos if a.anzeigename == name)

    def test_session_ist_quali(self):
        self.assertTrue(self.z.ist_quali)
        self.assertFalse(self.z.ist_rennen)
        d = schnappschuss(self.z)["session"]
        self.assertEqual((d["ist_quali"], d["quali_teil"], d["ausscheidung"]), (True, "Q1", 15))

    def test_ungueltige_runde_zaehlt_nicht(self):
        spieler = self.auto("Spieler")
        self.assertFalse(spieler.runden_info[3]["gueltig"])
        self.assertEqual(spieler.beste_runde_ms, spieler.rundenzeiten[2])  # Runde 2 ist die beste gueltige
        self.assertLess(spieler.rundenzeiten[3], spieler.rundenzeiten[2] + 600)

    def test_ohne_gueltige_schnelle_runde(self):
        alonso = self.auto("Alonso")
        self.assertGreater(alonso.beste_runde_ms, 90000)  # nur die langsamen Aus-/Einfahrrunden

    def test_keine_ausfaelle_im_quali(self):
        self.assertEqual(self.z.ausfaelle, [])
        self.assertEqual(self.z.momentaufnahmen, [])

    def test_gelbe_flagge_im_quali_im_protokoll(self):
        self.assertTrue(any(e["code"] == "GELB" for e in self.z.ereignis_log))

    def test_bericht_quali(self):
        b = bericht.bericht_bauen(schnappschuss(self.z, mit_runden=True))
        self.assertTrue(b["session"]["ist_quali"])
        ergebnis = b["ergebnis"]
        self.assertEqual([e["position"] for e in ergebnis], list(range(1, 21)))
        zeiten = [e["beste_runde_ms"] for e in ergebnis]
        self.assertEqual(zeiten, sorted(zeiten))
        self.assertEqual(ergebnis[0]["rueckstand_p1_ms"], 0)
        self.assertEqual(ergebnis[1]["rueckstand_p1_ms"], zeiten[1] - zeiten[0])
        self.assertTrue(all(e["weiter"] for e in ergebnis[:15]))
        self.assertFalse(any(e["weiter"] for e in ergebnis[15:]))
        spieler = next(e for e in ergebnis if e["ist_spieler"])
        self.assertEqual(spieler["ungueltige_runden"], 1)
        text = bericht.bericht_text(b)
        self.assertIn("Ergebnis Q1", text)
        self.assertIn("Ausscheidungslinie", text)
        self.assertIn("ungültig", text)


class TestSimulatorSzenarien(unittest.TestCase):
    def test_alle_formate(self):
        for fmt in (2025, 2026):
            for szenario in ("qualifying", "alles"):
                n = sum(1 for _ in Simulator(szenario, fmt=fmt, runden=3).pakete())
                self.assertGreater(n, 100, (fmt, szenario))


class TestDatenbank(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.mkdtemp()
        self.pfad = os.path.join(self.ordner, "t.sqlite")

    def test_ausfall_und_wendepunkte_bleiben_erhalten(self):
        db = Datenbank(self.pfad)
        kern, _ = rennen_fahren("alles", datenbank=db)
        db.sichern(kern.zustand)
        sid = db.sessions()[0]["id"]
        d = db.session(sid)
        self.assertEqual(d["ausfaelle"][0]["name"], "Verstappen")
        self.assertEqual(d["ausfaelle"][0]["position"], 1)
        self.assertEqual(d["ausfaelle"][0]["grund"], "mechanisches Problem")
        self.assertEqual([m["grund"] for m in d["momentaufnahmen"]],
                         ["start", "safety_car", "gruen", "rote_flagge", "restart", "zwischenstand"])
        self.assertEqual(len(d["momentaufnahmen"][0]["reihenfolge"]), 20)
        self.assertFalse(d["session"]["ist_quali"])

    def test_quali_gespeichert(self):
        db = Datenbank(self.pfad)
        kern, _ = rennen_fahren("qualifying", datenbank=db, runden=4)
        db.sichern(kern.zustand)
        eintrag = db.sessions()[0]
        self.assertTrue(eintrag["ist_quali"])
        d = db.session(eintrag["id"])
        self.assertTrue(d["session"]["ist_quali"])
        self.assertEqual(d["session"]["quali_teil"], "Q1")
        self.assertEqual(d["session"]["ausscheidung"], 15)
        spieler = next(a for a in d["autos"] if a["ist_spieler"])
        gueltig = [r["zeit_ms"] for r in spieler["runden"] if r["gueltig"]]
        self.assertEqual(len(gueltig), 3)  # eine Runde war ungueltig
        self.assertEqual(spieler["beste_runde_ms"], min(gueltig))

    def test_alte_datenbank_wird_umgebaut(self):
        # Datei im alten Format ohne die neuen Spalten und Tabellen
        con = sqlite3.connect(self.pfad)
        con.executescript("""
            CREATE TABLE sessions (id INTEGER PRIMARY KEY AUTOINCREMENT, session_uid TEXT NOT NULL UNIQUE,
              saison_id INTEGER NOT NULL DEFAULT 0, wochenende_id INTEGER NOT NULL DEFAULT 0,
              session_link_id INTEGER NOT NULL DEFAULT 0, strecke_id INTEGER, strecke TEXT,
              session_typ INTEGER, typ_name TEXT, ist_rennen INTEGER NOT NULL DEFAULT 0,
              runden_gesamt INTEGER, runden_gefahren INTEGER, begonnen TEXT, aktualisiert TEXT,
              beendet INTEGER NOT NULL DEFAULT 0, spieler_idx INTEGER,
              rote_flaggen INTEGER NOT NULL DEFAULT 0, packet_format INTEGER, notiz TEXT NOT NULL DEFAULT '');
            CREATE TABLE teilnehmer (session_id INTEGER NOT NULL, idx INTEGER NOT NULL, name TEXT,
              team_id INTEGER, team TEXT, farbe TEXT, startnummer INTEGER, ki INTEGER, ist_spieler INTEGER,
              startplatz INTEGER, position INTEGER, result_status INTEGER, status TEXT, punkte INTEGER,
              runden_gefahren INTEGER, beste_runde_ms INTEGER, gesamtzeit_s REAL, strafen_s INTEGER,
              boxenstopps_anzahl INTEGER, rueckstand_ms INTEGER, PRIMARY KEY (session_id, idx));
            INSERT INTO sessions (session_uid, strecke, session_typ, typ_name, ist_rennen, begonnen)
              VALUES ('1', 'Monza', 15, 'Rennen', 1, '2025-01-01T10:00:00');
            INSERT INTO teilnehmer (session_id, idx, name, ist_spieler, position)
              VALUES (1, 0, 'Alt', 1, 3);
        """)
        con.commit()
        con.close()
        db = Datenbank(self.pfad)  # baut um
        con = sqlite3.connect(self.pfad)
        spalten = {r[1] for r in con.execute("PRAGMA table_info(teilnehmer)")}
        con.close()
        self.assertTrue({"ausfall_runde", "ausfall_grund", "ausfall_position"} <= spalten)
        d = db.session(1)
        self.assertEqual(d["autos"][0]["name"], "Alt")
        self.assertEqual(d["ausfaelle"], [])
        self.assertEqual(d["momentaufnahmen"], [])
        # und neu schreiben klappt auch
        kern, _ = rennen_fahren("alles", datenbank=db)
        db.sichern(kern.zustand)
        self.assertEqual(len(db.sessions()), 2)
        Datenbank(self.pfad)  # zweites Mal oeffnen darf nichts kaputt machen


class TestBericht(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kern, _ = rennen_fahren("alles")
        cls.daten = schnappschuss(cls.kern.zustand, mit_runden=True)
        cls.b = bericht.bericht_bauen(cls.daten)
        cls.text = bericht.bericht_text(cls.b)

    def test_kopf_und_schema(self):
        self.assertEqual((self.b["schema"], self.b["version"]), ("renningenieur.bericht", 1))
        s = self.b["session"]
        self.assertEqual((s["typ_name"], s["strecke"], s["ist_rennen"], s["runden_gefahren"]),
                         ("Rennen", "Monza", True, 12))
        json.loads(bericht.json_text(self.b))  # ist gueltiges JSON

    def test_ergebnis(self):
        erg = self.b["ergebnis"]
        self.assertEqual([e["position"] for e in erg], list(range(1, 21)))
        letzter = erg[-1]
        self.assertEqual(letzter["name"], "Verstappen")
        self.assertEqual(letzter["ausfall"]["runde"], 5)
        self.assertEqual(letzter["ausfall"]["grund"], "mechanisches Problem")
        sieger = erg[0]
        self.assertEqual(sieger["punkte"], 25)
        self.assertEqual(erg[1]["rueckstand_ms"],
                         round((erg[1]["gesamtzeit_s"] + erg[1]["strafen_s"]
                                - sieger["gesamtzeit_s"] - sieger["strafen_s"]) * 1000))
        spieler = next(e for e in erg if e["ist_spieler"])
        self.assertEqual(spieler["plaetze_gewonnen"], spieler["startplatz"] - spieler["position"])
        self.assertEqual(spieler["reifenfolge"], ["M", "H", "S", "I"])

    def test_schnellste_runde_ist_gueltig_und_minimal(self):
        sr = self.b["schnellste_runde"]
        alle = [r["zeit_ms"] for f in self.b["fahrer"] for r in f["runden"] if r["gueltig"] and r["zeit_ms"]]
        self.assertEqual(sr["zeit_ms"], min(alle))

    def test_stints_mit_verschleiss(self):
        spieler = next(f for f in self.b["fahrer"] if f["ist_spieler"])
        erster = spieler["stints"][0]
        self.assertEqual((erster["kurz"], erster["start_runde"]), ("M", 1))
        self.assertGreater(erster["verschleiss_ende"], 20)
        self.assertGreater(erster["verschleiss_pro_runde"], 3)
        self.assertEqual(len(spieler["boxenstopps"]), 2)

    def test_wetter_und_verlauf(self):
        self.assertTrue(self.b["wetter"]["regen"])
        self.assertEqual([w["wetter"] for w in self.b["wetter"]["verlauf"]], [1, 2, 3, 4])
        self.assertEqual(self.b["positionsverlauf"][0]["runde"], 1)
        self.assertEqual(len(self.b["positionsverlauf"][-1]["reihenfolge"]), 19)  # Verstappen fehlt

    def test_text_enthaelt_alles_wichtige(self):
        for teil in ("RENNEN - MONZA", "Wetter", "Endergebnis", "Schnellste Runde", "Ausfälle",
                     "Verstappen (Red Bull) - mechanisches Problem", "Gelbe Flagge in Sektor 2",
                     "Safety Car", "Rote Flagge", "Reihenfolge zu wichtigen Zeitpunkten",
                     "Positionen nach Runden", "Reifen und Verschleiß", "Rundenzeiten",
                     "starker Regen", "Zeitstrafe für Piastri"):
            self.assertIn(teil, self.text)

    def test_format_helfer(self):
        self.assertEqual(bericht.zeit_text(79118), "1:19.118")
        self.assertEqual(bericht.zeit_text(0), "-")
        self.assertEqual(bericht.abstand_text(250), "+0.250")
        self.assertEqual(bericht.abstand_text(62300), "+1:02.300")
        self.assertEqual(bericht.gesamtzeit_text(5432.5), "1:30:32.500")

    def test_export_schreibt_beide_dateien(self):
        ordner = Path(tempfile.mkdtemp()) / "exporte"
        pfade = bericht.exportieren(self.daten, ordner)
        self.assertTrue(pfade["txt"].endswith(".txt") and pfade["json"].endswith(".json"))
        self.assertIn("Endergebnis", Path(pfade["txt"]).read_text(encoding="utf-8"))
        self.assertEqual(json.loads(Path(pfade["json"]).read_text(encoding="utf-8"))["schema"],
                         "renningenieur.bericht")
        self.assertNotRegex(Path(pfade["txt"]).name, r"[ :/\\]")

    def test_auto_export_am_rennende(self):
        ordner = Path(tempfile.mkdtemp())
        kern = Kern(config_laden(), texte_laden(), StummeStimme(), None, ordner)
        for t, paket in Simulator("trocken", runden=3).pakete():
            kern.paket(paket)
        dateien = sorted(p.suffix for p in (ordner / "exporte").iterdir())
        self.assertEqual(dateien, [".json", ".txt"])
        self.assertEqual(set(kern.letzter_export), {"txt", "json"})

    def test_auto_export_abschaltbar_und_ohne_training(self):
        ordner = Path(tempfile.mkdtemp())
        cfg = config_laden()
        cfg["export"]["aktiv"] = False
        kern = Kern(cfg, texte_laden(), StummeStimme(), None, ordner)
        for t, paket in Simulator("trocken", runden=3).pakete():
            kern.paket(paket)
        self.assertFalse((ordner / "exporte").exists())
        self.assertIsNone(kern.letzter_export)


class TestBerichtWeb(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = Datenbank(os.path.join(tempfile.mkdtemp(), "b.sqlite"))
        cls.kern, _ = rennen_fahren("alles", datenbank=cls.db)
        cls.db.sichern(cls.kern.zustand)
        cls.web = Webserver(cls.kern, "127.0.0.1", 0)
        cls.web.start()
        cls.basis = f"http://127.0.0.1:{cls.web.port}"

    @classmethod
    def tearDownClass(cls):
        cls.web.stop()

    def hole(self, pfad):
        with urllib.request.urlopen(self.basis + pfad, timeout=10) as r:
            return r.status, r.headers, r.read()

    def test_live_text(self):
        status, kopf, body = self.hole("/api/bericht?live=1&format=txt")
        self.assertEqual(status, 200)
        self.assertIn("text/plain", kopf["Content-Type"])
        self.assertIn("Verstappen (Red Bull) - mechanisches Problem", body.decode())
        self.assertIsNone(kopf["Content-Disposition"])

    def test_gespeichert_json_als_download(self):
        sid = self.db.sessions()[0]["id"]
        status, kopf, body = self.hole(f"/api/bericht?id={sid}&format=json&download=1")
        self.assertIn("application/json", kopf["Content-Type"])
        self.assertIn(".json", kopf["Content-Disposition"])
        daten = json.loads(body)
        self.assertEqual(daten["ausfaelle"][0]["name"], "Verstappen")
        self.assertEqual(len(daten["momentaufnahmen"]), 6)

    def test_unbekannte_session(self):
        for pfad in ("/api/bericht?id=999", "/api/bericht?id=abc"):
            with self.assertRaises(urllib.error.HTTPError) as fehler:
                self.hole(pfad)
            self.assertEqual(fehler.exception.code, 404)

    def test_wendepunkte_und_live(self):
        _, _, body = self.hole("/api/wendepunkte")
        d = json.loads(body)
        self.assertEqual(d["anzahl"], 6)
        self.assertEqual(d["momentaufnahmen"][0]["grund"], "start")
        live = json.loads(self.hole("/api/live")[2])
        self.assertEqual(live["momentaufnahmen_anzahl"], 6)
        self.assertEqual(live["ausfaelle"][0]["name"], "Verstappen")
        self.assertNotIn("momentaufnahmen", live)

    def test_seite_enthaelt_neue_bereiche(self):
        html = self.hole("/")[2].decode()
        for kennung in ("quali-tabelle", "wendepunkte", "lb-anzeigen", "rb-txt"):
            self.assertIn(kennung, html)


if __name__ == "__main__":
    unittest.main()
