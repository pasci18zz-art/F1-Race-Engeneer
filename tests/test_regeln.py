"""Einzelne Warnregeln mit einem von Hand gebauten Rennzustand."""

import unittest

from renningenieur.auswertung import Ereignis

from .hilfe import kern_erzeugen


def aufbau(**warnungen):
    """Rennen, Runde 5, Spieler auf Platz 2 zwischen 'Vorne' und 'Hinten'."""
    kern, stimme = kern_erzeugen(**warnungen)
    z = kern.zustand
    z.session_uid = 1
    z.session_bekannt = True
    z.session_typ = 15
    z.runden_gesamt = 30
    z.streckenlaenge = 5000
    z.rennen_gestartet = True
    z.spieler_idx = 1
    for idx, (name, pos) in enumerate([("VORNE", 1), ("ICH", 2), ("HINTEN", 3), ("WEIT", 4)]):
        a = z.autos[idx]
        a.name, a.position, a.runde, a.result_status = name, pos, 5, 2
        a.reifen_visuell, a.status_bekannt, a.schaden_bekannt = 17, True, True
        a.delta_vorne_ms = 0 if pos == 1 else 3000
        a.delta_fuehrender_ms = 3000 * (pos - 1)
        a.gesamtdistanz = 25000 - 200 * pos
    kern.regeln._rennstart_gemeldet = True
    return kern, stimme, z


def tick(kern, zeit: float):
    kern.zustand.session_time = zeit
    kern.regeln.ereignis(Ereignis("tick", zeit))


class TestAbstandHinten(unittest.TestCase):
    def test_warnt_einmal_und_erst_nach_entwarnung_wieder(self):
        kern, stimme, z = aufbau()
        hinten = z.autos[2]
        tick(kern, 100)
        self.assertEqual(stimme.gesagt, [])
        hinten.delta_vorne_ms = 900
        tick(kern, 101)
        self.assertEqual(stimme.gesagt, ["Hinten ist 0,9 Sekunden hinter dir."])
        hinten.delta_vorne_ms = 700
        tick(kern, 200)  # immer noch dran: keine Wiederholung
        self.assertEqual(len(stimme.gesagt), 1)
        hinten.delta_vorne_ms = 1600  # Entwarnung
        tick(kern, 201)
        hinten.delta_vorne_ms = 800
        tick(kern, 202)
        self.assertEqual(len(stimme.gesagt), 2)

    def test_mindestpause(self):
        kern, stimme, z = aufbau()
        hinten = z.autos[2]
        hinten.delta_vorne_ms = 900
        tick(kern, 100)
        hinten.delta_vorne_ms = 2000
        tick(kern, 101)
        hinten.delta_vorne_ms = 900
        tick(kern, 110)  # nur 10 Sekunden spaeter
        self.assertEqual(len(stimme.gesagt), 1)
        tick(kern, 150)  # nach 45 Sekunden Pause
        self.assertEqual(len(stimme.gesagt), 2)

    def test_schwelle_einstellbar_und_abschaltbar(self):
        kern, stimme, z = aufbau(abstand_hinten=0.5)
        z.autos[2].delta_vorne_ms = 900
        tick(kern, 100)
        self.assertEqual(stimme.gesagt, [])
        z.autos[2].delta_vorne_ms = 400
        tick(kern, 101)
        self.assertEqual(len(stimme.gesagt), 1)
        kern, stimme, z = aufbau(abstand_hinten=0)
        z.autos[2].delta_vorne_ms = 100
        tick(kern, 100)
        self.assertEqual(stimme.gesagt, [])

    def test_nicht_unter_safety_car_in_der_box_oder_in_runde_1(self):
        for vorbereitung in ("sc", "box", "runde1", "hinten_in_box", "rote_flagge"):
            kern, stimme, z = aufbau()
            z.autos[2].delta_vorne_ms = 500
            if vorbereitung == "sc":
                z.safety_car = 1
            elif vorbereitung == "box":
                z.autos[1].pit_status = 1
            elif vorbereitung == "runde1":
                z.autos[1].runde = 1
            elif vorbereitung == "hinten_in_box":
                z.autos[2].pit_status = 1
            elif vorbereitung == "rote_flagge":
                z.rote_flagge = True
            tick(kern, 100)
            self.assertEqual(stimme.gesagt, [], vorbereitung)


class TestReifenverschleiss(unittest.TestCase):
    def test_jede_schwelle_einmal_und_neu_nach_reifenwechsel(self):
        kern, stimme, z = aufbau()
        ich = z.autos[1]
        for wert, erwartet in [(39, 0), (41, 1), (45, 1), (56, 2), (69, 2), (71, 3), (90, 3)]:
            ich.reifenverschleiss = [wert - 5, wert - 6, wert, wert - 2]
            tick(kern, 100 + wert)
            self.assertEqual(len(stimme.gesagt), erwartet, wert)
        self.assertEqual(stimme.gesagt[0],
                         "Reifenverschleiß bei 41 Prozent, vorne links am stärksten.")
        ich.reifenverschleiss = [0.0] * 4  # frische Reifen
        tick(kern, 300)
        ich.reifenverschleiss = [42, 10, 10, 10]
        tick(kern, 301)
        self.assertEqual(stimme.gesagt[-1],
                         "Reifenverschleiß bei 42 Prozent, hinten links am stärksten.")

    def test_sprung_ueber_mehrere_schwellen_gibt_eine_meldung(self):
        kern, stimme, z = aufbau()
        z.autos[1].reifenverschleiss = [60, 60, 60, 60]
        tick(kern, 100)
        self.assertEqual(len(stimme.gesagt), 1)

    def test_eigene_schwellen(self):
        kern, stimme, z = aufbau(reifenverschleiss=[25])
        z.autos[1].reifenverschleiss = [26, 0, 0, 0]
        tick(kern, 100)
        self.assertEqual(len(stimme.gesagt), 1)


class TestRegen(unittest.TestCase):
    @staticmethod
    def prognose(z, regen_ab: int | None, wetter_jetzt: int = 1):
        z.wetter = wetter_jetzt
        z.prognose = [{"session_type": 15, "time_offset": m, "rain_percentage": 80,
                       "weather": 3 if regen_ab is not None and m >= regen_ab else 1}
                      for m in (0, 5, 10, 15, 30)]

    def test_schwellen(self):
        kern, stimme, z = aufbau()
        self.prognose(z, 30)
        tick(kern, 10)
        self.assertEqual(stimme.gesagt, [])  # 30 Minuten: noch zu frueh
        self.prognose(z, 10)
        tick(kern, 20)
        tick(kern, 21)
        self.assertEqual(stimme.gesagt, ["Regen in etwa 10 Minuten. Erwartet wird leichter Regen."])
        self.prognose(z, 5)
        tick(kern, 30)
        self.assertEqual(len(stimme.gesagt), 2)
        self.assertIn("5 Minuten", stimme.gesagt[1])
        self.prognose(z, 0)
        tick(kern, 40)
        self.assertEqual(stimme.gesagt[2], "Regen setzt jeden Moment ein. Erwartet wird leichter Regen.")
        tick(kern, 41)
        self.assertEqual(len(stimme.gesagt), 3)

    def test_prognose_aendert_sich(self):
        kern, stimme, z = aufbau()
        self.prognose(z, 5)
        tick(kern, 10)
        self.prognose(z, None)  # Regen verschwindet aus der Prognose
        tick(kern, 20)
        self.prognose(z, 5)  # ... und kommt wieder
        tick(kern, 30)
        self.assertEqual(len(stimme.gesagt), 2)

    def test_prognose_anderer_sessions_wird_ignoriert(self):
        kern, stimme, z = aufbau()
        z.prognose = [{"session_type": 8, "time_offset": 5, "weather": 4, "rain_percentage": 90}]
        tick(kern, 10)
        self.assertEqual(stimme.gesagt, [])

    def test_abtrocknen(self):
        kern, stimme, z = aufbau()
        z.wetter = 3
        z.prognose = [{"session_type": 15, "time_offset": m, "rain_percentage": 10,
                       "weather": 3 if m < 10 else 1} for m in (0, 5, 10, 15)]
        tick(kern, 10)
        self.assertEqual(stimme.gesagt, ["In etwa 10 Minuten hört der Regen auf."])

    def test_wetterwechsel(self):
        kern, stimme, z = aufbau()
        for alt, neu, erwartet in [(1, 3, "Es regnet jetzt: leichter Regen."),
                                   (3, 4, "Der Regen wird stärker: starker Regen."),
                                   (4, 3, "Der Regen lässt nach: leichter Regen."),
                                   (3, 2, "Der Regen hat aufgehört.")]:
            kern.regeln.ereignis(Ereignis("wetter_wechsel", 0, {"alt": alt, "neu": neu}))
            self.assertEqual(stimme.gesagt[-1], erwartet)
        kern.regeln.ereignis(Ereignis("wetter_wechsel", 0, {"alt": 0, "neu": 2}))
        self.assertEqual(len(stimme.gesagt), 4)  # klar -> bedeckt: keine Meldung


class TestBox(unittest.TestCase):
    @staticmethod
    def einfahrt(kern, idx: int, zeit: float = 100.0):
        kern.zustand.autos[idx].pit_status = 1
        kern.zustand.session_time = zeit
        kern.regeln.ereignis(Ereignis("box_einfahrt", zeit, {"idx": idx, "runde": 5}))
        tick(kern, zeit + 1)

    def test_vorne_hinten_und_weiter_weg(self):
        kern, stimme, z = aufbau()
        self.einfahrt(kern, 0)
        self.assertIn("Vorne vor dir", stimme.gesagt[-1])
        z.autos[0].pit_status = 0
        self.einfahrt(kern, 2, 200)
        self.assertIn("Hinten hinter dir", stimme.gesagt[-1])
        self.assertIn("Undercut", stimme.gesagt[-1])
        self.einfahrt(kern, 3, 300)
        self.assertEqual(len(stimme.gesagt), 2)  # Platz 4 ist nicht direkter Gegner

    def test_mehr_positionen_und_abstandsgrenze(self):
        kern, stimme, z = aufbau(box_positionen=2)
        self.einfahrt(kern, 3)
        self.assertEqual(stimme.gesagt, ["Weit auf Platz 4 kommt an die Box."])
        kern, stimme, z = aufbau(box_max_abstand=2)
        self.einfahrt(kern, 2)
        self.assertEqual(stimme.gesagt, [])  # 3 Sekunden entfernt, Grenze 2

    def test_abschaltbar(self):
        kern, stimme, z = aufbau(box_gegner=False)
        self.einfahrt(kern, 0)
        self.assertEqual(stimme.gesagt, [])

    def test_rote_flagge_direkt_danach_unterdrueckt_die_ansage(self):
        kern, stimme, z = aufbau()
        z.autos[0].pit_status = 1
        z.session_time = 100.0
        kern.regeln.ereignis(Ereignis("box_einfahrt", 100.0, {"idx": 0, "runde": 5}))
        z.rote_flagge = True
        kern.regeln.ereignis(Ereignis("rote_flagge", 100.2))
        tick(kern, 102)
        self.assertEqual(len(stimme.gesagt), 1)
        self.assertTrue(stimme.gesagt[0].startswith("Rote Flagge."))


class TestRestart(unittest.TestCase):
    def test_restart_als_fuehrender_ohne_hintermann_daten(self):
        kern, stimme, z = aufbau()
        z.spieler_idx = 0
        z.autos[1].status_bekannt = False
        z.rote_flagge = True
        kern.regeln.ereignis(Ereignis("ampel", 0, {"lichter": 1}))
        kern.regeln.ereignis(Ereignis("ampel", 0, {"lichter": 2}))
        self.assertEqual(stimme.gesagt,
                         ["Restart. Du startest von Platz 1 auf neuen Medium. Du führst das Rennen an."])

    def test_ampel_ohne_rote_flagge_sagt_nichts(self):
        kern, stimme, z = aufbau()
        kern.regeln.ereignis(Ereignis("ampel", 0, {"lichter": 1}))
        self.assertEqual(stimme.gesagt, [])

    def test_stummgeschalteter_text(self):
        kern, stimme, z = aufbau()
        kern.texte._daten["warnung"]["safety_car"] = []
        kern.regeln.ereignis(Ereignis("safety_car", 0, {"alt": 0, "neu": 1}))
        self.assertEqual(stimme.gesagt, [])


if __name__ == "__main__":
    unittest.main()
