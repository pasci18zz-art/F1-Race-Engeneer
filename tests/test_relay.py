"""UDP-Relay: jedes Paket geht unveraendert an alle Ziele und an die Auswertung."""

import os
import socket
import tempfile
import threading
import time
import unittest

from renningenieur.telemetrie import aufnahme, encoder, spec
from renningenieur.telemetrie.relay import Relay


def _empfaenger() -> socket.socket:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", 0))
    s.settimeout(2)
    return s


class TestRelay(unittest.TestCase):
    def test_weiterleitung_an_zwei_ziele_und_auswertung(self):
        simhub, anderes = _empfaenger(), _empfaenger()
        erhalten = []
        fertig = threading.Event()

        def paket(data):
            erhalten.append(data)
            if len(erhalten) == 3:
                fertig.set()

        relay = Relay("127.0.0.1", 0, [simhub.getsockname(), anderes.getsockname()], paket)
        relay.start()
        try:
            pakete = [encoder.leer(2025, spec.MOTION, {"session_uid": 1, "frame_identifier": i})
                      for i in range(3)]
            sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            for p in pakete:
                sender.sendto(p, ("127.0.0.1", relay.port))
            sender.close()
            self.assertTrue(fertig.wait(2))
            for ziel in (simhub, anderes):
                self.assertEqual([ziel.recvfrom(4096)[0] for _ in range(3)], pakete)
            self.assertEqual(erhalten, pakete)
            self.assertEqual((relay.empfangen, relay.weitergeleitet), (3, 6))
        finally:
            relay.stop()
            simhub.close()
            anderes.close()

    def test_fehler_in_der_auswertung_haelt_die_weiterleitung_nicht_auf(self):
        simhub = _empfaenger()

        def kaputt(data):
            raise ValueError("Absicht")

        relay = Relay("127.0.0.1", 0, [simhub.getsockname()], kaputt)
        relay.start()
        try:
            sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            with self.assertLogs("renningenieur.telemetrie.relay", level="ERROR"):
                for i in range(2):
                    sender.sendto(bytes([i]) * 40, ("127.0.0.1", relay.port))
                    self.assertEqual(simhub.recvfrom(4096)[0], bytes([i]) * 40)
            sender.close()
        finally:
            relay.stop()
            simhub.close()

    def test_ziel_laeuft_nicht(self):
        tot = _empfaenger()
        adresse = tot.getsockname()
        tot.close()  # an diesem Port hoert niemand
        erhalten = []
        relay = Relay("127.0.0.1", 0, [adresse], erhalten.append)
        relay.start()
        try:
            sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            for i in range(5):
                sender.sendto(b"x" * 30, ("127.0.0.1", relay.port))
                time.sleep(0.02)
            sender.close()
            time.sleep(0.2)
            self.assertEqual(len(erhalten), 5)
        finally:
            relay.stop()

    def test_belegter_port_gibt_verstaendliche_meldung(self):
        blockiert = _empfaenger()
        try:
            with self.assertRaisesRegex(RuntimeError, "belegt"):
                Relay("127.0.0.1", blockiert.getsockname()[1]).start()
        finally:
            blockiert.close()


class TestAufnahme(unittest.TestCase):
    def test_aufnehmen_und_abspielen(self):
        pfad = os.path.join(tempfile.mkdtemp(), "test.f1udp")
        a = aufnahme.Aufnahme(pfad)
        pakete = [bytes([i]) * (30 + i) for i in range(5)]
        for p in pakete:
            a.schreiben(p)
        a.schliessen()
        self.assertEqual([p for _, p in aufnahme.lesen(pfad)], pakete)
        ziel = _empfaenger()
        try:
            self.assertEqual(aufnahme.abspielen(pfad, *ziel.getsockname(), tempo=1000), 5)
            self.assertEqual([ziel.recvfrom(4096)[0] for _ in range(5)], pakete)
        finally:
            ziel.close()


if __name__ == "__main__":
    unittest.main()
