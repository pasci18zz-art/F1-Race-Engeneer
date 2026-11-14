"""Tablet-Mikrofon: Zertifikat, HTTPS, Aufnahme-Schnittstelle, Stummschaltung."""

import json
import socket
import ssl
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np

from renningenieur import config as konfig
from renningenieur.sprache import audio
from renningenieur.sprache.funk import Funk
from renningenieur.sprache.sprechfunk import Sprechfunk
from renningenieur.sprache.stimmen import StummeStimme
from renningenieur.web.server import Webserver

from .hilfe import kern_erzeugen, rennen_fahren

try:
    from renningenieur.web import zertifikat
    import cryptography  # noqa: F401
    HAT_CRYPTO = True
except ImportError:  # pragma: no cover
    HAT_CRYPTO = False


def freier_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class Erkennung:
    name = "Test"

    def __init__(self, text="wie ist das wetter"):
        self.text, self.gehoert = text, []

    def erkennen(self, pcm: bytes, rate: int) -> str:
        self.gehoert.append((len(pcm), rate))
        return self.text


def aufnahme(sekunden=2.0, rate=48000, db=-12.0) -> bytes:
    t = np.arange(int(sekunden * rate)) / rate
    return audio.als_pcm((10 ** (db / 20) * np.sin(2 * np.pi * 300 * t)).astype(np.float32))


@unittest.skipUnless(HAT_CRYPTO, "cryptography nicht installiert")
class TestZertifikat(unittest.TestCase):
    def test_client_mit_der_ca_vertraut_dem_server(self):
        ordner = Path(tempfile.mkdtemp())
        kette, schluessel, ca = zertifikat.zertifikate_bereitstellen(ordner, ["127.0.0.1", "192.168.1.50"])
        self.assertEqual(sorted(p.name for p in ordner.iterdir()),
                         ["adressen.txt", "ca.crt", "ca.key", "server.crt", "server.key"])
        server_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server_ctx.load_cert_chain(kette, schluessel)
        srv = socket.socket()
        srv.bind(("127.0.0.1", 0))
        srv.listen(5)

        def lauf():
            for _ in range(3):
                c, _ = srv.accept()
                try:
                    s = server_ctx.wrap_socket(c, server_side=True)
                    s.recv(2)
                    s.send(b"ok")
                    s.close()
                except OSError:
                    pass

        threading.Thread(target=lauf, daemon=True).start()
        port = srv.getsockname()[1]
        vertraut = ssl.create_default_context(cafile=str(ca))
        for host in ("localhost", "192.168.1.50"):
            with socket.create_connection(("127.0.0.1", port)) as r:
                with vertraut.wrap_socket(r, server_hostname=host) as s:
                    s.send(b"hi")
                    self.assertEqual(s.recv(2), b"ok")
        with socket.create_connection(("127.0.0.1", port)) as r:  # falscher Name
            with self.assertRaises(ssl.SSLCertVerificationError):
                vertraut.wrap_socket(r, server_hostname="192.168.1.99")
        srv.close()

    def test_erneuert_nur_bei_neuer_adresse(self):
        ordner = Path(tempfile.mkdtemp())
        zertifikat.zertifikate_bereitstellen(ordner, ["127.0.0.1", "10.0.0.5"])
        alt, ca_alt = (ordner / "server.crt").read_bytes(), (ordner / "ca.crt").read_bytes()
        zertifikat.zertifikate_bereitstellen(ordner, ["10.0.0.5", "127.0.0.1"])
        self.assertEqual((ordner / "server.crt").read_bytes(), alt)
        zertifikat.zertifikate_bereitstellen(ordner, ["127.0.0.1", "10.0.0.9"])
        self.assertNotEqual((ordner / "server.crt").read_bytes(), alt)
        self.assertEqual((ordner / "ca.crt").read_bytes(), ca_alt)  # die CA bleibt, das Tablet vertraut weiter

    def test_adressen_enthalten_localhost(self):
        self.assertIn("127.0.0.1", zertifikat.lokale_adressen())

    def test_nur_private_adressen_kommen_ins_zertifikat(self):
        ordner = Path(tempfile.mkdtemp())
        zertifikat.zertifikate_bereitstellen(
            ordner, ["192.168.1.20", "100.64.1.2", "8.8.8.8", "172.20.0.4", "169.254.3.3"])
        self.assertEqual((ordner / "adressen.txt").read_text().split(), ["172.20.0.4", "192.168.1.20"])

    def test_ca_kann_nichts_fuer_oeffentliche_adressen_ausstellen(self):
        ordner = Path(tempfile.mkdtemp())
        zertifikat.zertifikate_bereitstellen(ordner, ["127.0.0.1"])
        ca_zert, ca_schluessel = zertifikat._ca_laden(ordner)
        fremd = Path(tempfile.mkdtemp())
        zertifikat._server_erzeugen(fremd, ca_zert, ca_schluessel, ["8.8.8.8"])
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(fremd / "server.crt", fremd / "server.key")
        srv = socket.socket()
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)

        def lauf():
            try:
                c, _ = srv.accept()
                ctx.wrap_socket(c, server_side=True).recv(1)
            except OSError:
                pass

        threading.Thread(target=lauf, daemon=True).start()
        client = ssl.create_default_context(cafile=str(ordner / "ca.crt"))
        with socket.create_connection(("127.0.0.1", srv.getsockname()[1])) as r:
            with self.assertRaises(ssl.SSLCertVerificationError) as f:
                client.wrap_socket(r, server_hostname="8.8.8.8")
        self.assertIn("permitted subtree violation", str(f.exception))
        srv.close()

    def test_alte_ca_ohne_beschraenkung_wird_ersetzt(self):
        ordner = Path(tempfile.mkdtemp())
        zertifikat.zertifikate_bereitstellen(ordner, ["127.0.0.1"])
        # eine CA ohne NameConstraints einschmuggeln (so sahen die ersten Versionen aus)
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.x509.oid import NameOID

        schl = zertifikat._schluessel()
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "alt")])
        alt = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
               .public_key(schl.public_key()).serial_number(1)
               .not_valid_before(zertifikat._jetzt()).not_valid_after(zertifikat._jetzt()
               + __import__("datetime").timedelta(days=5))
               .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
               .sign(schl, hashes.SHA256()))
        (ordner / "ca.crt").write_bytes(alt.public_bytes(serialization.Encoding.PEM))
        (ordner / "ca.key").write_bytes(zertifikat._pem_schluessel(schl))
        zertifikat.zertifikate_bereitstellen(ordner, ["127.0.0.1"])
        neu = x509.load_pem_x509_certificate((ordner / "ca.crt").read_bytes())
        neu.extensions.get_extension_for_class(x509.NameConstraints)  # wirft, wenn sie fehlt


class TestFunkStumm(unittest.TestCase):
    def test_ingenieur_schweigt_zeitweise(self):
        stimme = StummeStimme()
        funk = Funk(stimme)
        funk.start()
        try:
            funk.stumm_fuer(0.4)
            funk.sagen("Hallo")
            time.sleep(0.15)
            self.assertEqual(stimme.gesagt, [])
            time.sleep(0.5)
            self.assertEqual(stimme.gesagt, ["Hallo"])
            funk.stumm_fuer(30)
            funk.sagen("Zweites")
            time.sleep(0.15)
            self.assertEqual(stimme.gesagt, ["Hallo"])
            funk.stumm_fuer(0)  # Aufnahme beendet: sofort wieder reden
            time.sleep(0.2)
            self.assertEqual(stimme.gesagt, ["Hallo", "Zweites"])
        finally:
            funk.stop()


class TestTabletFrage(unittest.TestCase):
    def aufbau(self, text="wie ist das wetter"):
        kern, stimme = rennen_fahren("trocken", bis=300)
        funk = Sprechfunk(kern, konfig.config_laden(), Path(tempfile.mkdtemp()))
        funk.erkennung = Erkennung(text)
        return funk, kern, stimme

    def test_antwort_wird_gesprochen_und_zurueckgegeben(self):
        funk, kern, stimme = self.aufbau()
        d = funk.tablet_frage(aufnahme(), 48000)
        self.assertTrue(d["ok"])
        self.assertEqual(d["text"], "wie ist das wetter")
        self.assertTrue(d["antwort"].startswith("Aktuell leicht bewölkt"))
        self.assertEqual(stimme.gesagt[-1], d["antwort"])
        # auf 16 kHz umgerechnet an die Erkennung gegeben
        laenge, rate = funk.erkennung.gehoert[0]
        self.assertEqual(rate, 16000)
        self.assertAlmostEqual(laenge / 2 / rate, 2.0, delta=0.01)

    def test_nichts_verstanden(self):
        funk, kern, stimme = self.aufbau(text="")
        d = funk.tablet_frage(aufnahme(), 48000)
        self.assertTrue(d["ok"])
        self.assertEqual(d["text"], "")
        self.assertIn(d["antwort"], ("Ich habe nichts gehört.", "Bitte noch mal."))
        self.assertEqual(stimme.gesagt[-1], d["antwort"])

    def test_leise_aufnahme_bekommt_hinweis(self):
        funk, kern, stimme = self.aufbau()
        d = funk.tablet_frage(aufnahme(db=-40), 48000)
        self.assertIn("sehr leise", d["hinweis"])
        self.assertEqual(d["text"], "wie ist das wetter")

    def test_ohne_erkennung(self):
        funk, kern, stimme = self.aufbau()
        funk.erkennung = None
        d = funk.tablet_frage(aufnahme(), 48000)
        self.assertFalse(d["ok"])
        self.assertIn("Spracherkennung läuft nicht", d["fehler"])


class TestTabletServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kern, cls.stimme = rennen_fahren("trocken", bis=300)
        cls.funk = Sprechfunk(cls.kern, konfig.config_laden(), Path(tempfile.mkdtemp()))
        cls.funk.erkennung = Erkennung()
        cls.ordner = Path(tempfile.mkdtemp())
        cls.https = freier_port() if HAT_CRYPTO else 0
        cls.web = Webserver(cls.kern, "127.0.0.1", 0, sprechfunk=cls.funk, https_port=cls.https,
                            zertifikat_ordner=cls.ordner, tablet={"stille_sekunden": 1.5})
        cls.web.start()
        cls.http = f"http://127.0.0.1:{cls.web.port}"

    @classmethod
    def tearDownClass(cls):
        cls.web.stop()

    def post(self, pfad, daten=b"{}", url=None, kontext=None):
        anfrage = urllib.request.Request((url or self.http) + pfad, daten,
                                         {"Content-Type": "application/octet-stream"})
        with urllib.request.urlopen(anfrage, timeout=10, context=kontext) as r:
            return json.loads(r.read())

    def test_info(self):
        with urllib.request.urlopen(self.http + "/api/info") as r:
            d = json.loads(r.read())
        self.assertTrue(d["mikrofon"])
        self.assertEqual(d["stille_sekunden"], 1.5)
        self.assertEqual(d["max_sekunden"], 8.0)
        self.assertEqual(d["https_port"], self.https)
        self.assertEqual(d["ca"], HAT_CRYPTO)

    def test_aufnahme_ueber_http(self):
        d = self.post("/api/sprache?rate=48000", aufnahme())
        self.assertTrue(d["ok"])
        self.assertEqual(d["text"], "wie ist das wetter")
        self.assertIn("Aktuell", d["antwort"])

    def test_ungueltige_aufnahmen(self):
        for pfad, daten in (("/api/sprache?rate=100", aufnahme()), ("/api/sprache?rate=48000", b""),
                            ("/api/sprache?rate=abc", aufnahme()),
                            ("/api/sprache?rate=48000", b"\0" * 4_100_000)):
            # Zu grosse Aufnahmen werden sofort abgewiesen (Verbindung bricht ab)
            with self.assertRaises((urllib.error.HTTPError, urllib.error.URLError)):
                self.post(pfad, daten)

    def test_stumm_start_und_ende(self):
        self.post("/api/sprache/start")
        self.assertGreater(self.kern.funk.stumm_bis, time.monotonic() + 10)
        self.post("/api/sprache/ende")
        self.assertEqual(self.kern.funk.stumm_bis, 0.0)

    def test_ohne_erkennung_503(self):
        erk, self.funk.erkennung = self.funk.erkennung, None
        try:
            with self.assertRaises(urllib.error.HTTPError) as fehler:
                self.post("/api/sprache?rate=48000", aufnahme())
            self.assertEqual(fehler.exception.code, 503)
            with urllib.request.urlopen(self.http + "/api/info") as r:
                self.assertFalse(json.loads(r.read())["mikrofon"])
        finally:
            self.funk.erkennung = erk

    @unittest.skipUnless(HAT_CRYPTO, "cryptography nicht installiert")
    def test_https_mit_eigener_ca(self):
        ca = self.ordner / "ca.crt"
        vertraut = ssl.create_default_context(cafile=str(ca))
        url = f"https://localhost:{self.https}"
        with urllib.request.urlopen(url + "/", context=vertraut, timeout=10) as r:
            self.assertIn("Renningenieur", r.read().decode())
        d = self.post("/api/sprache?rate=48000", aufnahme(), url=url, kontext=vertraut)
        self.assertEqual(d["text"], "wie ist das wetter")
        # ohne die CA wird das Zertifikat abgelehnt (wie am Tablet ohne installierte CA)
        with self.assertRaises(urllib.error.URLError):
            urllib.request.urlopen(url + "/", timeout=10)

    @unittest.skipUnless(HAT_CRYPTO, "cryptography nicht installiert")
    def test_ca_download(self):
        with urllib.request.urlopen(self.http + "/ca.crt") as r:
            self.assertEqual(r.headers["Content-Type"], "application/x-x509-ca-cert")
            self.assertTrue(r.read().startswith(b"-----BEGIN CERTIFICATE-----"))

    def test_statische_dateien(self):
        for datei, teil in (("/mikro.js", "api/sprache"), ("/", 'id="mikro"')):
            with urllib.request.urlopen(self.http + datei) as r:
                self.assertIn(teil, r.read().decode())


if __name__ == "__main__":
    unittest.main()
