"""Ganze simulierte Rennen durch die komplette Kette: Pakete -> Auswertung ->
Regeln -> Sprache und Datenbank. Kein Netzwerk, kein Ton."""

import os
import tempfile
import unittest

from renningenieur.datenbank import Datenbank
from renningenieur.simulator import KUMPEL, SPIELER, Simulator
from renningenieur.telemetrie import encoder

from .hilfe import enthaelt, kern_erzeugen, rennen_fahren


class TestRennenAlles(unittest.TestCase):
    """Szenario 'alles': Stopps, Strafe, Safety Car, rote Flagge, Regen."""

    @classmethod
    def setUpClass(cls):
        cls.pfad = os.path.join(tempfile.mkdtemp(), "test.sqlite")
        cls.db = Datenbank(cls.pfad)
        cls.kern, cls.stimme = rennen_fahren("alles", datenbank=cls.db)
        cls.gesagt = cls.stimme.gesagt
        cls.z = cls.kern.zustand

    def test_rennstart_ansage(self):
        self.assertEqual(self.gesagt[0],
                         "Rennen in Monza, 12 Runden. Du startest von Platz 5 auf neuen Medium.")

    def test_keine_fuellsaetze(self):
        for satz in self.gesagt:
            self.assertNotIn("keine Probleme", satz.lower())
            self.assertTrue(satz.strip())

    def test_regenwarnungen_in_absteigender_folge(self):
        minuten = [int(s.split("etwa ")[1].split(" ")[0]) for s in self.gesagt
                   if s.startswith("Regen in etwa")]
        self.assertEqual(minuten[:3], [15, 10, 5])
        self.assertTrue(enthaelt(self.gesagt, "Es regnet jetzt: leichter Regen."))
        self.assertTrue(enthaelt(self.gesagt, "Der Regen wird stärker: starker Regen."))

    def test_gegner_in_der_box(self):
        self.assertTrue(any("vor dir" in s and "Box" in s for s in self.gesagt))
        self.assertTrue(any("hinter dir" in s and "Box" in s and "Undercut" in s
                            for s in self.gesagt))
        self.assertTrue(enthaelt(self.gesagt, "ist wieder draußen, auf"))

    def test_eigener_stopp(self):
        self.assertTrue(enthaelt(self.gesagt, "Du bist wieder draußen auf Platz"))

    def test_hintermann_warnung(self):
        treffer = [s for s in self.gesagt if "hinter dir" in s and "Sekunden" in s
                   and "Box" not in s and "draußen" not in s and "Zeitstrafe" not in s]
        self.assertTrue(treffer)
        for s in treffer:
            sekunden = float(s.split(" Sekunden")[0].split()[-1].replace(",", "."))
            self.assertLess(sekunden, 1.0, s)

    def test_strafe_des_vordermanns(self):
        self.assertTrue(enthaelt(self.gesagt, "vor dir hat 5 Sekunden Zeitstrafe"))

    def test_safety_car(self):
        i = self.gesagt.index("Safety Car ist draußen.")
        j = self.gesagt.index("Safety Car kommt in dieser Runde rein.")
        k = self.gesagt.index("Strecke ist wieder frei.")
        self.assertLess(i, j)
        self.assertLess(j, k)

    def test_rote_flagge_und_restart(self):
        rot = next(s for s in self.gesagt if s.startswith("Rote Flagge."))
        self.assertRegex(rot, r"Du bist auf Platz \d+\. Deine Reifen: Hard, .*Prozent Verschleiß\.")
        restart = next(s for s in self.gesagt if s.startswith("Restart."))
        # Der Spieler holt sich unter roter Flagge frische Soft
        self.assertRegex(restart, r"Du startest von Platz \d+ auf neuen Soft\.")
        self.assertRegex(restart, r"Vor dir \w+ auf ")
        self.assertRegex(restart, r"Hinter dir \w+ auf ")
        self.assertLess(self.gesagt.index(rot), self.gesagt.index(restart))
        self.assertEqual(sum(s.startswith("Restart.") for s in self.gesagt), 1)
        self.assertEqual(self.z.rote_flaggen_anzahl, 1)
        self.assertFalse(self.z.rote_flagge)

    def test_boxenstopps_unter_roter_flagge_zaehlen_nicht(self):
        for a in self.z.gueltige_autos():
            self.assertEqual(len(a.boxenstopps), a.boxenstopps_anzahl, a.name)

    def test_ziel(self):
        ich = self.z.spieler
        self.assertTrue(enthaelt(self.gesagt, "Letzte Runde."))
        self.assertEqual(self.gesagt[-1], f"Zielflagge. Platz {ich.position}.")
        self.assertTrue(self.z.beendet)

    def test_stints_des_spielers(self):
        ich = self.z.spieler
        self.assertEqual([s.visuell for s in ich.stints], [17, 18, 16, 7])  # M, H, S, Inter
        self.assertEqual(ich.stints[0].start_runde, 1)
        self.assertEqual(ich.stints[-1].end_runde, 12)
        for vorher, nachher in zip(ich.stints, ich.stints[1:]):
            self.assertGreaterEqual(nachher.start_runde, vorher.start_runde)

    def test_rundenzeiten_vollstaendig(self):
        for a in self.z.gueltige_autos():
            self.assertEqual(sorted(a.rundenzeiten), list(range(1, 13)), a.name)

    def test_wetterverlauf(self):
        self.assertEqual([w["wetter"] for w in self.z.wetter_log], [1, 2, 3, 4])

    # --- Datenbank ----------------------------------------------------
    def test_datenbank_session(self):
        sessions = self.db.sessions()
        self.assertEqual(len(sessions), 1)
        s = sessions[0]
        self.assertEqual((s["strecke"], s["ist_rennen"], s["beendet"], s["rote_flaggen"]),
                         ("Monza", 1, 1, 1))
        self.assertEqual(s["spieler_position"], self.z.spieler.position)
        self.assertEqual(s["spieler_startplatz"], 5)
        self.assertEqual([st["kurz"] for st in s["spieler_stints"]], ["M", "H", "S", "I"])
        self.assertTrue(s["nass"])
        self.assertEqual(s["saison_name"], "Saison 1")

    def test_datenbank_details(self):
        d = self.db.session(self.db.sessions()[0]["id"])
        self.assertEqual(len(d["autos"]), 20)
        self.assertEqual([a["position"] for a in d["autos"]], list(range(1, 21)))
        sieger = d["autos"][0]
        self.assertEqual(sieger["punkte"], 25)
        self.assertEqual(len(sieger["runden"]), 12)
        self.assertTrue(sieger["stints"])
        self.assertEqual(sieger["stints"][0]["start_runde"], 1)
        self.assertEqual(len(sieger["boxenstopps"]), sieger["boxenstopps_anzahl"])
        self.assertEqual([w["wetter"] for w in d["wetter_log"]], [1, 2, 3, 4])
        codes = {e["code"] for e in d["ereignisse"]}
        self.assertTrue({"BOX", "RDFL", "RESTART", "WETTER", "SC", "STRAFE"} <= codes)
        ich = next(a for a in d["autos"] if a["ist_spieler"])
        self.assertEqual(ich["name"], "Spieler")
        runde3 = ich["runden"][2]
        self.assertEqual(runde3["runde"], 3)
        self.assertGreater(runde3["zeit_ms"], 70000)
        self.assertEqual(runde3["reifen_visuell"], 17)

    def test_datenbank_umbenennen_und_loeschen(self):
        pfad = os.path.join(tempfile.mkdtemp(), "x.sqlite")
        db = Datenbank(pfad)
        rennen_fahren("trocken", datenbank=db, bis=200)
        s = db.sessions()[0]
        self.assertEqual(s["beendet"], 0)
        db.saison_umbenennen(s["saison_id"], "Karriere mit Tom")
        self.assertEqual(db.sessions()[0]["saison_name"], "Karriere mit Tom")
        db.session_loeschen(s["id"])
        self.assertEqual(db.sessions(), [])
        self.assertIsNone(db.session(s["id"]))


class TestWeitereSzenarien(unittest.TestCase):
    def test_trocken_mit_reifenverschleiss(self):
        kern, stimme = rennen_fahren("trocken")
        warnungen = [s for s in stimme.gesagt if s.startswith("Reifenverschleiß bei")]
        self.assertEqual(len(warnungen), 1)  # nur die 40-Prozent-Schwelle wird erreicht
        self.assertRegex(warnungen[0], r"bei 4\d Prozent, vorne links am stärksten")
        self.assertFalse(any("Regen" in s for s in stimme.gesagt))
        self.assertFalse(any("Rote Flagge" in s for s in stimme.gesagt))
        self.assertEqual([s.visuell for s in kern.zustand.spieler.stints], [17, 16])

    def test_format_2026(self):
        kern25, stimme25 = rennen_fahren("alles", fmt=2025)
        kern26, stimme26 = rennen_fahren("alles", fmt=2026)
        self.assertEqual(kern26.zustand.packet_format, 2026)
        self.assertEqual(stimme25.gesagt, stimme26.gesagt)

    def test_zwei_rennen_nacheinander(self):
        pfad = os.path.join(tempfile.mkdtemp(), "x.sqlite")
        db = Datenbank(pfad)
        kern, stimme = kern_erzeugen(db)
        for nr, (szenario, strecke, saison) in enumerate(
                [("trocken", 10, 111), ("regen", 10, 222)], start=1):
            for _, paket in Simulator(szenario, strecke_id=strecke, saison_id=saison,
                                      wochenende_id=nr, seed=nr).pakete():
                kern.paket(paket)
        sessions = db.sessions()
        self.assertEqual(len(sessions), 2)
        self.assertEqual({s["saison_name"] for s in sessions}, {"Saison 1", "Saison 2"})
        self.assertEqual({s["strecke"] for s in sessions}, {"Spa"})
        self.assertEqual(sorted(s["nass"] for s in sessions), [False, True])
        # Jede Session hat ihre eigene Begruessung bekommen
        self.assertEqual(sum(s.startswith("Rennen in Spa") for s in stimme.gesagt), 2)


class TestFlashback(unittest.TestCase):
    def test_rueckblende_verwirft_spaetere_daten(self):
        kern, stimme = kern_erzeugen()
        sim = Simulator("trocken")
        letzte = 0.0
        for t, paket in sim.pakete():
            if t > 300:
                break
            kern.paket(paket)
            letzte = t
        z = kern.zustand
        stopps_vorher = sum(len(a.boxenstopps) for a in z.autos)
        ereignisse_vorher = len(z.ereignis_log)
        self.assertGreater(stopps_vorher, 0)
        hdr = {"session_uid": sim.session_uid, "session_time": letzte,
               "player_car_index": SPIELER}
        kern.paket(encoder.event(2025, hdr, "FLBK", {"flashback_session_time": 100.0}))
        self.assertEqual(sum(len(a.boxenstopps) for a in z.autos), 0)
        self.assertLess(len(z.ereignis_log), ereignisse_vorher)
        self.assertEqual(z.session_time, 100.0)

    def test_runde_zurueck_kuerzt_rundenzeiten(self):
        kern, _ = rennen_fahren("trocken", bis=260)
        z = kern.zustand
        ich = z.spieler
        self.assertEqual(sorted(ich.rundenzeiten), [1, 2, 3])
        # Lap Data, in dem alle wieder in Runde 2 sind
        cars = [{"car_position": a.position, "current_lap_num": 2, "result_status": 2,
                 "last_lap_time_ms": a.rundenzeiten.get(1, 0)} for a in z.autos[:20]]
        hdr = {"session_uid": z.session_uid, "session_time": 120.0, "player_car_index": SPIELER}
        kern.paket(encoder.lap_data(2025, hdr, cars))
        self.assertEqual(sorted(ich.rundenzeiten), [1])


class TestFalschesFormat(unittest.TestCase):
    def test_einmalige_warnung(self):
        kern, stimme = kern_erzeugen()
        paket = bytearray(encoder.event(2025, {"session_uid": 5}, "SSTA"))
        paket[0:2] = (2024).to_bytes(2, "little")
        with self.assertLogs("renningenieur.auswertung", level="WARNING"):
            for _ in range(5):
                kern.paket(bytes(paket))
        self.assertEqual(len(stimme.gesagt), 1)
        self.assertIn("Telemetrie-Format", stimme.gesagt[0])


class TestMitspieler(unittest.TestCase):
    def test_kumpel_wird_erkannt(self):
        kern, _ = rennen_fahren("trocken", bis=100)
        mitspieler = kern.zustand.menschliche_mitspieler()
        self.assertEqual([a.idx for a in mitspieler], [KUMPEL])
        self.assertEqual(kern.zustand.teamkollege(kern.zustand.spieler).idx, KUMPEL)


if __name__ == "__main__":
    unittest.main()
