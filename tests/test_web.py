"""Webserver: Live-Daten, gespeicherte Sessions, Fragen, statische Dateien."""

import json
import os
import tempfile
import unittest
import urllib.error
import urllib.request

from renningenieur.datenbank import Datenbank
from renningenieur.web.server import Webserver

from .hilfe import rennen_fahren


class TestWeb(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = Datenbank(os.path.join(tempfile.mkdtemp(), "web.sqlite"))
        cls.kern, _ = rennen_fahren("trocken", datenbank=cls.db, bis=420)
        cls.web = Webserver(cls.kern, "127.0.0.1", 0)
        cls.web.start()
        cls.basis = f"http://127.0.0.1:{cls.web.port}"

    @classmethod
    def tearDownClass(cls):
        cls.web.stop()

    def hole(self, pfad: str):
        with urllib.request.urlopen(self.basis + pfad, timeout=5) as r:
            return r.status, r.headers.get("Content-Type"), r.read()

    def sende(self, pfad: str, daten: dict):
        anfrage = urllib.request.Request(self.basis + pfad, json.dumps(daten).encode(),
                                         {"Content-Type": "application/json"})
        with urllib.request.urlopen(anfrage, timeout=5) as r:
            return json.loads(r.read())

    def test_seite_und_dateien(self):
        status, typ, body = self.hole("/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", typ)
        self.assertIn("Renningenieur", body.decode())
        self.assertIn("javascript", self.hole("/app.js")[1])
        self.assertIn("css", self.hole("/style.css")[1])

    def test_keine_dateien_ausserhalb(self):
        for pfad in ("/../server.py", "/..%2Fserver.py", "/gibtsnicht.js", "/api/unbekannt"):
            with self.assertRaises(urllib.error.HTTPError) as fehler:
                self.hole(pfad)
            self.assertEqual(fehler.exception.code, 404, pfad)

    def test_live(self):
        d = json.loads(self.hole("/api/live")[2])
        self.assertTrue(d["aktiv"])
        self.assertEqual(d["session"]["strecke"], "Monza")
        self.assertEqual(len(d["autos"]), 20)
        ich = next(a for a in d["autos"] if a["ist_spieler"])
        self.assertEqual(ich["name"], "Spieler")
        self.assertEqual(ich["reifen"]["kurz"], "M")
        self.assertTrue(ich["stints"])
        self.assertTrue(d["prognose"])
        self.assertTrue(d["funk"])

    def test_gespeicherte_sessions(self):
        sessions = json.loads(self.hole("/api/sessions")[2])
        self.assertEqual(len(sessions), 1)
        d = json.loads(self.hole(f"/api/session?id={sessions[0]['id']}")[2])
        self.assertEqual(len(d["autos"]), 20)
        with self.assertRaises(urllib.error.HTTPError):
            self.hole("/api/session?id=999")

    def test_frage_und_saison(self):
        d = self.sende("/api/frage", {"text": "Auf welchem Platz bin ich?"})
        self.assertIn("Platz", d["antwort"])
        s = json.loads(self.hole("/api/sessions")[2])[0]
        self.sende("/api/saison", {"saison_id": s["saison_id"], "name": "Meine Saison"})
        self.assertEqual(json.loads(self.hole("/api/sessions")[2])[0]["saison_name"], "Meine Saison")


if __name__ == "__main__":
    unittest.main()
