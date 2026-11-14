"""Fragen: Themenerkennung, Zahlen, Bezuege auf Fahrer und die Antworten."""

import unittest

from renningenieur import fragen
from renningenieur.fragen import norm, ordnungszahl, zahl

from .hilfe import rennen_fahren


class TestSprache(unittest.TestCase):
    def test_norm(self):
        self.assertEqual(norm("Wie groß ist der Rückstand auf Hülkenberg?"),
                         "wie gross ist der ruckstand auf hulkenberg")

    def test_zahlen(self):
        for wort, n in {"funf": 5, "zwolf": 12, "zwanzig": 20, "einundzwanzig": 21,
                        "dreiunddreissig": 33, "7": 7, "eine": 1}.items():
            self.assertEqual(zahl(wort), n, wort)
        self.assertIsNone(zahl("runden"))
        self.assertIsNone(zahl("und"))

    def test_ordnungszahlen(self):
        for wort, n in {"dritten": 3, "erster": 1, "siebte": 7, "achten": 8, "zwolften": 12,
                        "zwanzigsten": 20}.items():
            self.assertEqual(ordnungszahl(wort), n, wort)
        for wort in ("letzten", "runden", "reifen", "acht", "eine", "meine", "vorne"):
            self.assertIsNone(ordnungszahl(wort), wort)

    def test_themen(self):
        f = fragen.Fragen.__new__(fragen.Fragen)
        erwartet = {
            "Kommt Regen": "wetter",
            "Wie ist das Wetter": "wetter",
            "Wann kommt Regen": "wetter",
            "Wie viele Sekunden zum Auto vor mir": "abstand",
            "Wie groß ist der Abstand nach hinten": "abstand",
            "Wie viel Rückstand habe ich auf den Führenden": "abstand",
            "Wie viel habe ich in den letzten fünf Runden auf Verstappen verloren": "entwicklung",
            "Wie viel habe ich in den letzten drei Runden gewonnen": "entwicklung",
            "Wie sind meine Reifen": "reifen",
            "Wie alt sind meine Reifen": "reifen",
            "Welche Mischung fährt wer": "reifen",
            "Wann ist ein sinnvolles Boxenfenster": "box",
            "Auf welchem Platz bin ich": "position",
            "Wie viele Runden noch": "runden",
            "Wie viel Sprit habe ich": "sprit",
            "Habe ich einen Schaden": "schaden",
            "Wie viele Sekunden Strafe habe ich": "strafen",
            "Erzähl mir einen Witz": None,
        }
        for frage, thema in erwartet.items():
            self.assertEqual(f.thema(frage), thema, frage)

    def test_alle_beispielfragen_werden_erkannt(self):
        f = fragen.Fragen.__new__(fragen.Fragen)
        for frage in fragen.BEISPIELE:
            self.assertIsNotNone(f.thema(frage), frage)

    def test_rundenzahl(self):
        r = fragen.Fragen._rundenzahl
        self.assertEqual(r(norm("in den letzten fünf Runden").split()), 5)
        self.assertEqual(r(norm("in den letzten 12 Runden").split()), 12)
        self.assertEqual(r(norm("in der letzten Runde").split()), 1)
        self.assertEqual(r(norm("in den letzten Runden").split()), 3)
        self.assertEqual(r(norm("auf Verstappen verloren").split()), 3)


class TestAntworten(unittest.TestCase):
    """Stand des Simulator-Rennens 'trocken' nach 260 Sekunden (Runde 4)."""

    @classmethod
    def setUpClass(cls):
        cls.kern, _ = rennen_fahren("trocken", bis=260)
        cls.z = cls.kern.zustand
        cls.ich = cls.z.spieler

    def frage(self, text: str) -> str:
        return self.kern.fragen.antwort(text)

    def test_abstand_vorne_und_hinten(self):
        vorne, hinten = self.z.vordermann(self.ich), self.z.hintermann(self.ich)
        a = self.frage("Wie viele Sekunden zum Auto vor mir?")
        self.assertIn(vorne.anzeigename, a)
        self.assertIn(f"{self.ich.delta_vorne_ms / 1000:.1f}".replace(".", ","), a)
        a = self.frage("Abstand nach hinten")
        self.assertIn(hinten.anzeigename, a)
        self.assertIn(f"{hinten.delta_vorne_ms / 1000:.1f}".replace(".", ","), a)

    def test_abstand_zum_fuehrenden(self):
        a = self.frage("Wie viel Rückstand habe ich auf den Führenden?")
        self.assertIn(self.z.fuehrender().anzeigename, a)
        self.assertIn(f"{self.ich.delta_fuehrender_ms / 1000:.1f}".replace(".", ","), a)

    def test_bezug_ueber_platz_name_alias_und_kumpel(self):
        p2 = self.z.auto_auf_position(2)
        self.assertIn(p2.anzeigename, self.frage("Wie weit ist Platz zwei weg"))
        self.assertIn(p2.anzeigename, self.frage("Abstand zum Zweiten"))
        self.assertIn("Alonso", self.frage("Abstand zu Alonso"))
        self.assertIn("Alonso", self.frage("Abstand zu Alonzo"))  # aehnlich geschrieben
        self.assertIn("Verstappen", self.frage("Abstand zu fair stappen"))  # Alias
        self.assertIn("Kumpel", self.frage("Wie weit ist mein Kumpel weg"))
        self.assertIn("Kumpel", self.frage("Abstand zum Teamkollegen"))
        ferraris = [a for a in self.z.gueltige_autos() if a.team == "Ferrari"]
        naechster = min(ferraris, key=lambda a: abs(a.position - self.ich.position))
        self.assertIn(naechster.anzeigename, self.frage("Wo ist der Ferrari"))

    def test_unbekannter_platz(self):
        self.assertEqual(self.frage("Abstand zu Platz dreißig"),
                         "Ich weiß nicht, welchen Fahrer du meinst.")

    def test_entwicklung(self):
        vorne = self.z.vordermann(self.ich)
        runden = sorted(set(self.ich.rundenzeiten) & set(vorne.rundenzeiten))[-2:]
        diff = sum(self.ich.rundenzeiten[r] - vorne.rundenzeiten[r] for r in runden)
        a = self.frage("Wie viel habe ich in den letzten zwei Runden auf den Vordermann verloren")
        self.assertIn(vorne.anzeigename, a)
        self.assertIn("2 Runden", a)
        self.assertIn("verloren" if diff > 0 else "gewonnen", a)
        self.assertIn(f"{max(abs(diff) / 1000, 0.1):.1f}".replace(".", ","), a)
        a = self.frage("Wie viel habe ich in den letzten zwanzig Runden auf Kumpel gewonnen")
        self.assertIn("3 Runden", a)  # es gibt erst drei gemeinsame Runden

    def test_reifen(self):
        a = self.frage("Wie sind meine Reifen")
        self.assertIn("Medium, 3 Runden alt", a)
        self.assertIn("Verschleiß vorne", a)
        hinten = self.z.hintermann(self.ich)
        a = self.frage("Welche Reifen hat der Hintermann")
        self.assertIn(hinten.anzeigename, a)
        self.assertIn(hinten.reifen_name, a)
        a = self.frage("Welche Mischung fährt wer")
        self.assertIn("Soft:", a)
        self.assertIn("Medium:", a)
        self.assertIn("Verstappen", a)

    def test_sonstige(self):
        self.assertIn(f"Platz {self.ich.position}", self.frage("Auf welchem Platz bin ich"))
        self.assertIn("Noch 8 Runden", self.frage("Wie viele Runden noch"))
        self.assertIn("Boxenfenster", self.frage("Wann ist das Boxenfenster"))
        self.assertIn("Kein Regen in Sicht", self.frage("Kommt Regen?"))
        self.assertIn("Sprit", self.frage("Wie viel Sprit habe ich"))
        self.assertEqual(self.frage("Habe ich einen Schaden"), "Kein Schaden am Auto.")
        self.assertEqual(self.frage("Habe ich Strafen"), "Du hast keine Strafen.")
        self.assertIn(self.frage("Erzähl mir einen Witz"),
                      ("Das habe ich nicht verstanden.", "Bitte noch mal."))

    def test_ohne_daten(self):
        from .hilfe import kern_erzeugen

        kern, _ = kern_erzeugen()
        self.assertEqual(kern.fragen.antwort("Wie ist das Wetter"),
                         "Dazu habe ich gerade keine Daten.")

    def test_wortliste_fuer_vosk(self):
        woerter = self.kern.fragen.wortliste()
        for wort in ("regen", "abstand", "fünf", "reifen", "verstappen", "kumpel"):
            self.assertIn(wort, woerter)


if __name__ == "__main__":
    unittest.main()


class TestFragenZuAnderenFahrern(unittest.TestCase):
    """Stand des Simulator-Rennens 'trocken' nach 520 Sekunden (Runde 7)."""

    @classmethod
    def setUpClass(cls):
        cls.kern, _ = rennen_fahren("trocken", bis=520)
        cls.z = cls.kern.zustand
        cls.ich = cls.z.spieler

    def frage(self, text: str) -> str:
        return self.kern.fragen.antwort(text)

    def test_wer_ist_auf_position(self):
        p17 = self.z.auto_auf_position(17)
        for text in ("Wer ist auf Position siebzehn", "Wer ist auf Platz 17", "Position siebzehn",
                     "Wer ist Siebzehnter"):
            a = self.frage(text)
            self.assertIn(p17.anzeigename, a, text)
            self.assertIn("Platz 17", a, text)

    def test_platz_eines_fahrers(self):
        alonso = next(a for a in self.z.gueltige_autos() if a.name == "ALONSO")
        a = self.frage("Auf welchem Platz ist Alonso")
        self.assertIn(f"Alonso liegt auf Platz {alonso.position}", a)

    def test_eigener_platz_bleibt(self):
        self.assertEqual(self.frage("Auf welchem Platz bin ich"),
                         f"Du bist auf Platz {self.ich.position}.")
        self.assertEqual(self.frage("Wer ist auf Platz dreißig"),
                         "Ich weiß nicht, welchen Fahrer du meinst.")

    def test_wer_fuehrt_und_reihenfolge(self):
        erster = self.z.fuehrender()
        self.assertIn(erster.anzeigename, self.frage("Wer führt"))
        a = self.frage("Wie ist die Reihenfolge")
        self.assertTrue(a.startswith(f"Platz 1 {erster.anzeigename}, Platz 2 "))
        self.assertIn("Platz 5 ", a)
        self.assertNotIn("Platz 6 ", a.split(". ")[0])

    def test_strategie_eines_fahrers(self):
        # Piastri (Index 3) startet auf Soft und wechselt in Runde 3 auf Hard
        a = self.frage("Wie ist die Strategie von Piastri")
        self.assertEqual(a, "Piastri ist auf Soft gestartet. In Runde 3 Wechsel auf Hard. "
                            "Bisher ein Stopp. Jetzt auf Hard, 4 Runden alt.")
        # Der Spieler selbst stoppt in diesem Szenario erst in Runde 9
        ohne = next(x for x in self.z.gueltige_autos()
                    if x.boxenstopps_anzahl == 0 and x.idx != self.ich.idx)
        a = self.frage(f"War {ohne.anzeigename} schon an der Box")
        self.assertIn("gestartet", a)
        self.assertIn("noch nicht an der Box", a)

    def test_wer_war_noch_nicht_an_der_box(self):
        a = self.frage("Wer war noch nicht an der Box")
        self.assertTrue(a.startswith("Noch ohne Stopp: "))
        self.assertIn("Spieler", a)
        self.assertNotIn("Piastri", a)

    def test_eigene_strategie_bleibt_boxenfenster(self):
        self.assertIn("Boxenfenster", self.frage("Wie ist meine Strategie"))

    def test_reifenverschleiss_eines_fahrers(self):
        a = self.frage("Wie ist der Reifenverschleiß von Verstappen")
        self.assertRegex(a, r"Verstappen fährt \w+, .*Verschleiß bis zu \d+ Prozent\.")
        vorne = self.z.vordermann(self.ich)
        self.assertIn(vorne.anzeigename, self.frage("Wie ist der Verschleiß beim Vordermann"))


class TestNeueFragen(unittest.TestCase):
    """Die 20 Fragen aus der zweiten Runde, im Rennen 'trocken' nach 480 Sekunden."""

    @classmethod
    def setUpClass(cls):
        cls.kern, _ = rennen_fahren("trocken", bis=480)
        cls.z = cls.kern.zustand
        cls.ich = cls.z.spieler

    def frage(self, text: str) -> str:
        return self.kern.fragen.antwort(text)

    def test_themen(self):
        f = self.kern.fragen
        erwartet = {
            "Holt der Hintermann auf": "trend",
            "Wann habe ich den Vordermann eingeholt": "trend",
            "Wer ist gerade am schnellsten": "schnellste",
            "Wie schnell war der Vordermann": "rundenzeit",
            "In welchem Sektor verliere ich auf den Vordermann": "sektor",
            "Wer ist ausgefallen": "ausfall",
            "Wer hat Strafen": "strafen",
            "Hat der Vordermann Schaden": "schaden",
            "Wer hat die frischesten Reifen": "frisch",
            "Wie viele Plätze habe ich gutgemacht": "plaetze",
            "Wo komme ich nach einem Stopp raus": "rueckkehr",
            "Lohnt sich ein Undercut": "undercut",
            "Wie lange halten meine Reifen noch": "haltbarkeit",
            "Reichen die Reifen bis ins Ziel": "haltbarkeit",
            "Welche Reifensätze habe ich noch": "reifensaetze",
            "Wie viel Zeit kostet ein Boxenstopp": "stoppzeit",
            "Wie warm sind meine Reifen": "temperatur",
            "Wie heiß sind die Bremsen": "temperatur",
            "Wie viel ERS habe ich": "ers",
            "Wie voll ist die Batterie": "ers",
            "Wie viele Verwarnungen habe ich": "verwarnungen",
            "Wie konstant fahre ich": "konstanz",
            # alte Fragen duerfen nicht umgeleitet werden
            "Wer ist auf Platz drei": "position",
            "Wer führt": "position",
            "Abstand zum Ersten": "abstand",
            "Reicht der Sprit": "sprit",
            "Wie viel habe ich auf den Vordermann verloren": "entwicklung",
        }
        for frage, thema in erwartet.items():
            self.assertEqual(f.thema(frage), thema, frage)

    def test_trend(self):
        a = self.frage("Holt der Hintermann auf")
        hinten = self.z.hintermann(self.ich)
        self.assertIn(hinten.anzeigename, a)
        a = self.frage("Wann habe ich den Vordermann eingeholt")
        self.assertIn(self.z.vordermann(self.ich).anzeigename, a)

    def test_trend_mit_hochrechnung(self):
        from renningenieur.zustand import Auto

        kern, _ = rennen_fahren("trocken", bis=100)
        z = kern.zustand
        ich, vorne = z.autos[0], z.autos[1]
        z.spieler_idx, z.runden_gesamt, z.session_typ = 0, 30, 15
        for a, pos, zeit in ((ich, 2, 80000), (vorne, 1, 80500)):
            a.position, a.runde, a.result_status, a.boxenstopps, a.stints = pos, 6, 2, [], []
            a.rundenzeiten = {r: zeit for r in range(1, 6)}
            a.neutral_runden = set()
        ich.delta_fuehrender_ms, vorne.delta_fuehrender_ms = 2000, 0
        self.assertEqual(kern.fragen.antwort("Wann habe ich den Vordermann eingeholt"),
                         f"Du holst etwa 0,5 Sekunden pro Runde auf {vorne.anzeigename} auf. "
                         "Bei 2,0 Sekunden Abstand bist du in etwa 4 Runden dran.")
        z.runden_gesamt = 8
        self.assertTrue(kern.fragen.antwort("Wann bin ich dran am Vordermann").endswith(
            "Bis ins Ziel sind es aber nur noch 2 Runden."))
        self.assertIsInstance(ich, Auto)

    def test_schnellste_und_rundenzeit(self):
        a = self.frage("Wer ist gerade am schnellsten")
        self.assertIn("schnellste letzte Runde", a)
        self.assertIn("schnellste Runde des Rennens", a)
        vorne = self.z.vordermann(self.ich)
        a = self.frage("Wie schnell war der Vordermann in der letzten Runde")
        self.assertTrue(a.startswith(f"{vorne.anzeigename} fuhr zuletzt"))
        self.assertTrue(self.frage("Wie war meine schnellste Runde").startswith("Letzte Runde"))

    def test_sektor(self):
        a = self.frage("In welchem Sektor verliere ich auf den Vordermann")
        self.assertIn("Sektor 1", a)
        self.assertIn("Sektor 3", a)
        self.assertTrue(self.frage("Wie war mein erster Sektor").startswith(
            "Deine letzte Runde gegen deine besten Sektoren"))

    def test_ausfall_strafen_schaden(self):
        self.assertEqual(self.frage("Wer ist ausgefallen"), "Bisher ist niemand ausgefallen.")
        self.assertEqual(self.frage("Wer hat Strafen"), "Niemand hat eine Strafe.")
        vorne = self.z.vordermann(self.ich)
        self.assertEqual(self.frage("Hat der Vordermann Schaden"),
                         f"{vorne.anzeigename} hat keinen Schaden.")
        # von Hand: ein Ausfall, eine Strafe, ein Schaden
        kern, _ = rennen_fahren("trocken", bis=200)
        z = kern.zustand
        z.autos[15].result_status = 4
        z.autos[3].strafen_s = 5
        z.autos[2].offene_durchfahrt = 1
        z.autos[0].fluegel_vl = 30
        self.assertEqual(kern.fragen.antwort("Wer ist ausgefallen"), "Ausgefallen: Lawson.")
        a = kern.fragen.antwort("Wer hat Strafen")  # nach Position sortiert
        self.assertTrue(a.startswith("Strafen: "))
        self.assertIn("Piastri 5 Sekunden Strafe", a)
        self.assertIn("Leclerc eine offene Durchfahrtsstrafe", a)
        self.assertEqual(kern.fragen.antwort("Hat Verstappen einen Schaden"),
                         "Verstappen hat Schaden: Frontflügel links 30 Prozent.")
        self.assertEqual(kern.fragen.antwort("Hat Piastri eine Strafe"),
                         "Piastri hat 5 Sekunden Strafe.")

    def test_frisch_und_plaetze(self):
        a = self.frage("Wer hat um mich herum die frischesten Reifen")
        self.assertTrue(a.startswith(("Die frischesten Reifen", "Du hast die frischesten")))
        self.assertEqual(self.frage("Wie viele Plätze habe ich seit dem Start gutgemacht"),
                         f"Von Platz 5 auf Platz {self.ich.position}, du hast "
                         f"{5 - self.ich.position} Plätze gutgemacht.")

    def test_boxenstopp_rechnungen(self):
        a = self.frage("Wie viel Zeit kostet hier ein Boxenstopp")
        # Simulator: 22 s in der Gasse, davon 8 s normale Fahrzeit -> etwa 14 s Verlust
        verlust = float(a.split("etwa ")[1].split(" Sekunden")[0].replace(",", "."))
        self.assertAlmostEqual(verlust, 14.0, delta=1.5)
        self.assertIn("Standzeit", a)
        a = self.frage("Wo komme ich nach einem Stopp raus")
        self.assertRegex(a, r"etwa auf Platz \d+ raus")
        self.assertIn("gemessen an", a)
        a = self.frage("Lohnt sich ein Undercut auf den Vordermann")
        self.assertIn(self.z.vordermann(self.ich).anzeigename, a)
        self.assertRegex(a, r"(klappen|knapp|Eher nicht)")

    def test_boxenverlust_ohne_messung(self):
        kern, _ = rennen_fahren("trocken", bis=150)
        self.assertEqual(kern.fragen.antwort("Wie viel kostet ein Boxenstopp"),
                         "Gerechnet mit 22,0 Sekunden pro Stopp, gemessen ist noch keiner.")

    def test_haltbarkeit(self):
        a = self.frage("Wie lange halten meine Reifen noch")
        self.assertRegex(a, r"Verschleiß \d+ Prozent, etwa \d+,\d Prozent pro Runde\. "
                            r"Bis 70 Prozent noch etwa \d+ Runden\.")
        vorne = self.z.vordermann(self.ich)
        self.assertTrue(self.frage("Wie lange halten die Reifen vom Vordermann").startswith(
            vorne.anzeigename))

    def test_reifensaetze(self):
        self.assertEqual(self.frage("Welche Reifensätze habe ich noch"),
                         "Noch verfügbar: Soft: 1 neu, 1 gebraucht mit 18 Prozent. "
                         "Medium: 2 neu. Hard: 2 neu.")

    def test_temperaturen_ers_verwarnungen(self):
        self.assertRegex(self.frage("Wie warm sind meine Reifen"),
                         r"Reifen innen: vorne \d+ und \d+, hinten \d+ und \d+ Grad\.")
        self.assertEqual(self.frage("Wie warm sind meine Bremsen"),
                         "Bremsen vorne 610 und 620, hinten 480 und 470 Grad.")
        self.assertEqual(self.frage("Wie heiß ist der Motor"), "Motor 105 Grad.")
        self.assertEqual(self.frage("Wie warm ist die Strecke"), "Strecke 31 Grad, Luft 24 Grad.")
        self.assertRegex(self.frage("Wie viel ERS habe ich"), r"ERS bei \d+ Prozent, Modus Mittel\.")
        self.assertEqual(self.frage("Wie viele Verwarnungen für Track Limits habe ich"),
                         "Du hast 2 Verwarnungen für Track Limits, insgesamt 2.")
        self.assertEqual(self.frage("Wie viele Verwarnungen hat der Vordermann"),
                         f"{self.z.vordermann(self.ich).anzeigename} hat keine Verwarnungen.")

    def test_konstanz(self):
        a = self.frage("Wie konstant fahre ich")
        self.assertRegex(a, r"Schnitt der letzten \d Runden 1 Minute \d+,\d, Streuung \d+,\d Sekunden\.")
        self.assertTrue(a.endswith(("Sehr konstant.", "Ordentlich konstant.",
                                    "Die Zeiten schwanken noch deutlich.")))
