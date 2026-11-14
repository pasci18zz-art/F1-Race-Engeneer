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
