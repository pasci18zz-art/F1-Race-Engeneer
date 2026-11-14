"""Eigene Befehle: Pruefen, Speichern, Auswerten, Katalog und Schnittstellen."""

import json
import tempfile
import unittest
import urllib.request
from pathlib import Path

from renningenieur import befehle as bf
from renningenieur.fragen import THEMEN
from renningenieur.web.server import Webserver

from .hilfe import kern_erzeugen, rennen_fahren


def befehl(**kw):
    b = {"name": "Test", "ausloeser": ["steckbrief"], "ziel": {"art": "ich"},
         "infos": ["position"], "text": ""}
    b.update(kw)
    return b


class TestPruefen(unittest.TestCase):
    def fehler(self, **kw) -> str:
        sauber, fehler = bf.validiere(befehl(**kw))
        self.assertIsNone(sauber)
        return " ".join(fehler)

    def test_gueltiger_befehl(self):
        sauber, fehler = bf.validiere(befehl(ausloeser=[" reifen nachbar ", ""], infos=["reifen", "reifen"]))
        self.assertEqual(fehler, [])
        self.assertEqual(sauber["ausloeser"], ["reifen nachbar"])
        self.assertEqual(sauber["infos"], ["reifen"])
        self.assertTrue(sauber["aktiv"])
        self.assertEqual(len(sauber["id"]), 8)

    def test_fehlermeldungen(self):
        self.assertIn("Namen", self.fehler(name=" "))
        self.assertIn("höchstens 40", self.fehler(name="x" * 41))
        self.assertIn("mindestens einen Auslöser", self.fehler(ausloeser=[]))
        self.assertIn("drei Buchstaben", self.fehler(ausloeser=["ab de"]))
        self.assertIn("zu lang", self.fehler(ausloeser=["wort " * 20]))
        self.assertIn("mindestens eine Info", self.fehler(infos=[]))
        self.assertIn("gibt es nicht", self.fehler(infos=["quatsch"]))
        self.assertIn("Ziel wählen", self.fehler(ziel={"art": "keiner"}, infos=["position"]))
        self.assertIn("von welchem Fahrer", self.fehler(ziel={"art": "mars"}))
        self.assertIn("1 bis 24", self.fehler(ziel={"art": "platz", "platz": 99}))
        self.assertIn("Namen des festen Fahrers", self.fehler(ziel={"art": "name", "name": " "}))
        self.assertIn("1 bis 10", self.fehler(ziel={"art": "top", "n": 11}))
        self.assertIn("1 bis 5", self.fehler(ziel={"art": "um_mich", "n": 6}))
        self.assertIn("{foo}", self.fehler(text="{foo}"))
        self.assertIn("Wähle sie bei den Infos aus", self.fehler(text="{reifen}"))
        self.assertIn("Klammer", self.fehler(text="{name"))
        self.assertIn("300", self.fehler(text="x" * 301))

    def test_nur_allgemeine_infos_ohne_fahrer(self):
        sauber, fehler = bf.validiere(befehl(ziel={"art": "keiner"}, infos=["wetter"]))
        self.assertEqual(fehler, [])

    def test_auswahl_der_ausloeser(self):
        def trifft(a, frage):
            return bf.ausloeser_trifft(a, bf.norm(frage).split())

        self.assertTrue(trifft("reifen nachbar", "Wie sind die Reifen von meinen Nachbarn?"))
        self.assertTrue(trifft("nachbar reifen", "Wie sind die Reifen von meinen Nachbarn?"))  # Reihenfolge egal
        self.assertTrue(trifft("reif", "Reifenverschleiß"))  # Wortanfang
        self.assertFalse(trifft("reifen nachbar", "Wie sind meine Reifen?"))
        self.assertFalse(trifft("", "irgendwas"))
        self.assertTrue(trifft("Hülkenberg", "wie liegt hulkenberg"))  # Umlaute egal


class TestSpeichern(unittest.TestCase):
    def test_ablage_und_neu_laden(self):
        pfad = Path(tempfile.mkdtemp()) / "eigene_befehle.json"
        e = bf.EigeneBefehle(pfad)
        gespeichert, fehler = e.speichern(befehl(name="Eins"))
        self.assertEqual(fehler, [])
        e.speichern(befehl(name="Zwei", ausloeser=["zweiter test"]))
        neu = bf.EigeneBefehle(pfad)  # wie nach einem Neustart
        self.assertEqual([b["name"] for b in neu.liste()], ["Eins", "Zwei"])
        self.assertEqual(neu.liste()[0]["id"], gespeichert["id"])
        # aendern ueber die id
        geaendert = dict(gespeichert, name="Eins neu", aktiv=False)
        e.speichern(geaendert)
        self.assertEqual([b["name"] for b in e.liste()], ["Eins neu", "Zwei"])
        self.assertFalse(e.liste()[0]["aktiv"])
        self.assertTrue(e.loeschen(gespeichert["id"]))
        self.assertFalse(e.loeschen("gibtsnicht"))
        self.assertEqual([b["name"] for b in bf.EigeneBefehle(pfad).liste()], ["Zwei"])

    def test_doppelter_name(self):
        e = bf.EigeneBefehle()
        e.speichern(befehl(name="Doppelt"))
        sauber, fehler = e.speichern(befehl(name="doppelt", ausloeser=["anderes wort"]))
        self.assertIsNone(sauber)
        self.assertIn("gibt es schon", fehler[0])

    def test_hoechstzahl(self):
        e = bf.EigeneBefehle()
        for i in range(bf.MAX_BEFEHLE):
            self.assertIsNotNone(e.speichern(befehl(name=f"B{i}"))[0])
        self.assertIn("höchstens", e.speichern(befehl(name="zu viel"))[1][0])

    def test_kaputte_datei_stuerzt_nicht_ab(self):
        pfad = Path(tempfile.mkdtemp()) / "eigene_befehle.json"
        pfad.write_text("{kaputt", encoding="utf-8")
        with self.assertLogs("renningenieur.befehle", level="WARNING"):
            self.assertEqual(bf.EigeneBefehle(pfad).liste(), [])
        pfad.write_text(json.dumps({"befehle": [befehl(name="Gut"), {"name": "", "infos": []}]}),
                        encoding="utf-8")
        with self.assertLogs("renningenieur.befehle", level="WARNING"):
            self.assertEqual([b["name"] for b in bf.EigeneBefehle(pfad).liste()], ["Gut"])


class TestAuswerten(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kern, _ = rennen_fahren("trocken", bis=480)
        cls.z = cls.kern.zustand
        cls.ich = cls.z.spieler
        cls.fragen = cls.kern.fragen

    def antwort(self, frage: str, **kw) -> str:
        self.kern.eigene.loeschen("t")
        self.kern.eigene.speichern(befehl(id="t", **kw))
        try:
            return self.fragen.antwort(frage)
        finally:
            self.kern.eigene.loeschen("t")

    def test_ziele(self):
        z = self.z
        v, h, f_ = z.vordermann(self.ich), z.hintermann(self.ich), z.fuehrender()
        infos = ["position", "reifen"]
        self.assertEqual(self.antwort("steckbrief", ziel={"art": "ich"}, infos=infos),
                         f"Platz {self.ich.position}, Reifen Medium.")
        self.assertTrue(self.antwort("steckbrief", ziel={"art": "vordermann"}, infos=infos)
                        .startswith(f"{v.anzeigename}: Platz {v.position}"))
        self.assertTrue(self.antwort("steckbrief", ziel={"art": "hintermann"}, infos=infos)
                        .startswith(f"{h.anzeigename}: "))
        self.assertTrue(self.antwort("steckbrief", ziel={"art": "fuehrender"}, infos=infos)
                        .startswith(f"{f_.anzeigename}: Platz 1"))
        self.assertTrue(self.antwort("steckbrief", ziel={"art": "kumpel"}, infos=infos).startswith("Kumpel: "))
        self.assertTrue(self.antwort("steckbrief", ziel={"art": "platz", "platz": 7}, infos=infos)
                        .startswith(f"{z.auto_auf_position(7).anzeigename}: Platz 7"))
        self.assertTrue(self.antwort("steckbrief", ziel={"art": "name", "name": "alonso"}, infos=infos)
                        .startswith("Alonso: "))
        self.assertTrue(self.antwort("steckbrief", ziel={"art": "teamkollege"}, infos=infos)
                        .startswith("Kumpel: "))  # Spieler und Kumpel fahren beide fuer Williams

    def test_aus_der_frage(self):
        infos = ["position"]
        ziel = {"art": "aus_frage"}
        self.assertEqual(self.antwort("steckbrief", ziel=ziel, infos=infos), f"Platz {self.ich.position}.")
        self.assertEqual(self.antwort("steckbrief von verstappen", ziel=ziel, infos=infos), "Verstappen: Platz 1.")
        self.assertTrue(self.antwort("steckbrief hintermann", ziel=ziel, infos=infos)
                        .startswith(f"{self.z.hintermann(self.ich).anzeigename}: "))
        self.assertEqual(self.antwort("steckbrief platz zwölf", ziel=ziel, infos=infos),
                         f"{self.z.auto_auf_position(12).anzeigename}: Platz 12.")
        self.assertEqual(self.antwort("steckbrief platz 30", ziel=ziel, infos=infos),
                         "Ich weiß nicht, welchen Fahrer du meinst.")

    def test_listen(self):
        a = self.antwort("steckbrief", ziel={"art": "top", "n": 3}, infos=["position"])
        self.assertEqual(a.count("Platz"), 3)
        self.assertTrue(a.startswith("Verstappen: Platz 1. "))
        um = self.antwort("steckbrief", ziel={"art": "um_mich", "n": 1}, infos=["abstand_zu_mir"])
        self.assertIn("vor dir", um)
        self.assertIn("hinter dir", um)
        self.assertNotIn("Du:", um)

    def test_eigener_text_mit_platzhaltern(self):
        a = self.antwort("steckbrief von norris", ziel={"art": "aus_frage"}, infos=["position", "reifen"],
                         text="{name} liegt auf {position} mit {reifen}.")
        self.assertEqual(a, "Norris liegt auf Platz 2 mit Medium.")
        a = self.antwort("steckbrief", ziel={"art": "top", "n": 2}, infos=["reifen"], text="{name}: {reifen}")
        self.assertEqual(a, "Verstappen: Soft. Norris: Medium.")
        a = self.antwort("steckbrief", ziel={"art": "ich"}, infos=["position", "wetter"],
                         text="Du bist {position}, {wetter}.")
        self.assertEqual(a, "Du bist Platz 3, leicht bewölkt.")

    def test_allgemeine_infos(self):
        a = self.antwort("steckbrief", ziel={"art": "keiner"}, infos=["wetter", "regen", "runden_rest"])
        self.assertEqual(a, "Wetter leicht bewölkt, Strecke 31 Grad, Luft 24 Grad. Kein Regen in Sicht. Noch 6 Runden.")
        a = self.antwort("steckbrief", ziel={"art": "ich"}, infos=["position", "wetter"])
        self.assertTrue(a.startswith("Platz 3. Wetter leicht bewölkt"))

    def test_fehlende_daten_und_fahrer(self):
        self.assertEqual(self.antwort("steckbrief", ziel={"art": "name", "name": "Fantasiename"}, infos=["position"]),
                         "Fantasiename finde ich gerade nicht im Rennen.")
        self.assertEqual(self.antwort("steckbrief", ziel={"art": "platz", "platz": 24}, infos=["position"]),
                         "Auf Platz 24 liegt gerade niemand.")
        # Reifentemperatur eines Fahrers, dessen Telemetrie wir nicht haben: keine Daten
        for a in self.z.autos:
            a.telemetrie_bekannt = False
        try:
            self.assertEqual(self.antwort("steckbrief", ziel={"art": "ich"}, infos=["reifentemperatur"]),
                             "Dazu habe ich gerade keine Daten.")
        finally:
            for a in self.z.autos:
                a.telemetrie_bekannt = True

    def test_vorrang_und_aktiv(self):
        e = self.kern.eigene
        e.speichern(befehl(id="w", name="Mein Wetter", ausloeser=["wetter"], ziel={"art": "keiner"},
                           infos=["strecke"]))
        try:
            antwort, (art, name) = self.fragen.antwort_mit_quelle("wie ist das wetter")
            self.assertEqual((art, name), ("eigen", "Mein Wetter"))
            self.assertEqual(antwort, "Strecke Monza.")
            e.speichern(befehl(id="w", name="Mein Wetter", ausloeser=["wetter"], ziel={"art": "keiner"},
                               infos=["strecke"], aktiv=False))
            self.assertEqual(self.fragen.antwort_mit_quelle("wie ist das wetter")[1], ("eingebaut", "wetter"))
        finally:
            e.loeschen("w")

    def test_alle_infos_laufen_fuer_alle_fahrer(self):
        from renningenieur.befehle import INFOS, Ctx

        kern, _ = rennen_fahren("alles")  # komplettes Rennen mit Stopps, Regen, Strafe
        z, ich = kern.zustand, kern.zustand.spieler
        for a in z.gueltige_autos():
            for info in INFOS.values():
                erg = info.funktion(Ctx(z, a, ich, kern.texte))
                self.assertTrue(erg is None or (len(erg) == 2 and all(isinstance(x, str) and x for x in erg)),
                                (info.key, a.name, erg))

    def test_wortliste_fuer_vosk(self):
        e = self.kern.eigene
        e.speichern(befehl(id="v", ausloeser=["zauberwort nachbar"]))
        try:
            self.assertIn("zauberwort", self.fragen.wortliste())
        finally:
            e.loeschen("v")


class TestKatalog(unittest.TestCase):
    def test_jeder_eingebaute_befehl_hat_eine_beschreibung(self):
        themen = {t for t, _ in THEMEN}
        self.assertEqual(themen, set(bf.EINGEBAUT_DOKU), "Beschreibung fehlt oder ist übrig")
        for eintrag in bf.katalog_eingebaut(THEMEN):
            self.assertTrue(eintrag["beschreibung"] and eintrag["beispiele"], eintrag["thema"])
            self.assertTrue(eintrag["stichwoerter"])

    def test_beispiele_loesen_den_beschriebenen_befehl_aus(self):
        kern, _ = rennen_fahren("trocken", bis=480)
        for eintrag in bf.katalog_eingebaut(THEMEN):
            for beispiel in eintrag["beispiele"]:
                antwort, (art, name) = kern.fragen.antwort_mit_quelle(beispiel)
                self.assertEqual(art, "eingebaut", beispiel)
                self.assertNotIn("nicht verstanden", antwort, beispiel)

    def test_infos_und_ziele(self):
        keys = [i["key"] for i in bf.infos_katalog()]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertTrue({"position", "reifen", "wetter"} <= set(keys))
        self.assertEqual({z["art"] for z in bf.ZIELE}, bf.ZIEL_ARTEN)


class TestSchnittstellen(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kern, _ = kern_erzeugen()  # noch kein Spiel -> Beispieldaten
        cls.kern.eigene = bf.EigeneBefehle(Path(tempfile.mkdtemp()) / "b.json")
        cls.kern.fragen.eigene = cls.kern.eigene
        cls.web = Webserver(cls.kern, "127.0.0.1", 0)
        cls.web.start()
        cls.url = f"http://127.0.0.1:{cls.web.port}"

    @classmethod
    def tearDownClass(cls):
        cls.web.stop()

    def post(self, pfad, daten):
        r = urllib.request.urlopen(urllib.request.Request(
            self.url + pfad, json.dumps(daten).encode(), {"Content-Type": "application/json"}), timeout=30)
        return json.loads(r.read())

    def test_uebersicht_mit_beispieldaten(self):
        d = json.loads(urllib.request.urlopen(self.url + "/api/befehle", timeout=30).read())
        self.assertEqual(d["daten"], "beispiel")
        self.assertEqual(len(d["eingebaut"]), len(THEMEN))
        self.assertEqual(len(d["fahrer"]), 20)
        self.assertTrue(d["infos"] and d["ziele"] and d["fahrer_nennen"])

    def test_anlegen_ausprobieren_loeschen(self):
        b = befehl(name="Schnittstelle", ausloeser=["schnittstelle test"], ziel={"art": "aus_frage"},
                   infos=["position", "reifen"])
        v = self.post("/api/befehle/vorschau", {"befehl": b, "frage": "schnittstelle test verstappen"})
        self.assertEqual((v["ok"], v["antwort"]), (True, "Verstappen: Platz 1, Reifen Soft."))
        s = self.post("/api/befehle/speichern", {"befehl": b})
        self.assertTrue(s["ok"])
        p = self.post("/api/befehle/pruefen", {"text": "schnittstelle test verstappen"})
        self.assertEqual((p["art"], p["von"]), ("eigen", "Eigener Befehl „Schnittstelle“"))
        self.assertEqual(p["antwort"], "Verstappen: Platz 1, Reifen Soft.")
        self.assertEqual(p["daten"], "beispiel")
        l = self.post("/api/befehle/loeschen", {"id": s["befehl"]["id"]})
        self.assertTrue(l["ok"])
        self.assertEqual(l["eigene"], [])

    def test_fehler_werden_gemeldet(self):
        s = self.post("/api/befehle/speichern", {"befehl": {"name": "", "ausloeser": [], "infos": []}})
        self.assertFalse(s["ok"])
        self.assertGreaterEqual(len(s["fehler"]), 3)
        v = self.post("/api/befehle/vorschau", {"befehl": {"infos": []}, "frage": ""})
        self.assertFalse(v["ok"])

    def test_pruefen_ohne_sprechen_sagt_nichts(self):
        self.kern.funk.protokoll.clear()
        p = self.post("/api/befehle/pruefen", {"text": "wie ist das wetter", "sprechen": True})
        self.assertEqual(p["art"], "eingebaut")
        self.assertEqual(self.kern.funk.protokoll, [])  # Beispieldaten werden nie gesprochen

    def test_nicht_erkannt(self):
        p = self.post("/api/befehle/pruefen", {"text": "blubb blubb"})
        self.assertEqual((p["art"], p["von"]), ("keine", "Kein Befehl erkannt"))


class TestMitLaufendemSpiel(unittest.TestCase):
    def test_live_daten_und_sprechen(self):
        kern, stimme = rennen_fahren("trocken", bis=480)
        web = Webserver(kern, "127.0.0.1", 0)
        web.start()
        try:
            def post(pfad, daten):
                r = urllib.request.urlopen(urllib.request.Request(
                    f"http://127.0.0.1:{web.port}{pfad}", json.dumps(daten).encode(),
                    {"Content-Type": "application/json"}), timeout=30)
                return json.loads(r.read())

            p = post("/api/befehle/pruefen", {"text": "wie sind meine reifen", "sprechen": True})
            self.assertEqual(p["daten"], "live")
            self.assertEqual(stimme.gesagt[-1], p["antwort"])
        finally:
            web.stop()


if __name__ == "__main__":
    unittest.main()
