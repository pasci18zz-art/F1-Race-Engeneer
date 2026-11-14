"""Eigenes Zertifikat fuer die HTTPS-Adresse der Tablet-Seite.

Warum HTTPS? Chrome gibt das Mikrofon nur auf sicheren Seiten frei (HTTPS
oder localhost). Die Tablet-Seite laeuft aber unter der Adresse des PCs im
WLAN (z. B. 192.168.178.20), also muss sie per HTTPS erreichbar sein.

Das Programm erzeugt dafuer beim ersten Start
  * eine eigene kleine Zertifizierungsstelle ("Renningenieur Lokale CA") und
  * ein Zertifikat fuer die Adressen dieses PCs, von ihr unterschrieben.
Beides bleibt im Ordner zertifikat/ und wird neu ausgestellt, wenn sich die
Adresse des PCs aendert.

Sicherheit: Die CA ist technisch auf private Netzadressen (192.168.x.x,
10.x.x.x, 172.16-31.x.x, 127.x.x.x) und "localhost" beschraenkt. Selbst wenn
jemand ihren Schluessel (zertifikat/ca.key) in die Finger bekaeme, koennte
er damit kein Zertifikat fuer eine echte Webseite (bank.de o. ae.) ausstellen,
das das Tablet akzeptiert. Trotzdem: ca.key nicht weitergeben.

Am Tablet gibt es dann zwei Wege:
  1. Beim ersten Oeffnen die Warnung "Verbindung nicht privat" wegklicken
     (Erweitert, Weiter). Einfach, aber Chrome fragt dann evtl. jedes Mal
     neu nach dem Mikrofon.
  2. Einmalig ca.crt am Tablet als "CA-Zertifikat" installieren. Dann gibt es
     keine Warnung mehr. ca.crt liegt unter http://<PC>:8025/ca.crt.
"""

from __future__ import annotations

import datetime
import ipaddress
import logging
import socket
from pathlib import Path

log = logging.getLogger(__name__)

CA_DATEI = "ca.crt"
CA_SCHLUESSEL = "ca.key"
SERVER_DATEI = "server.crt"
SERVER_SCHLUESSEL = "server.key"
ADRESSEN_DATEI = "adressen.txt"
GUELTIG_TAGE = 365
ERNEUERN_VOR_TAGEN = 30


PRIVATE_NETZE = [ipaddress.ip_network(n) for n in
                 ("192.168.0.0/16", "10.0.0.0/8", "172.16.0.0/12", "127.0.0.0/8")]


def ist_privat(adresse: str) -> bool:
    try:
        ip = ipaddress.ip_address(adresse)
    except ValueError:
        return False
    return any(ip in netz for netz in PRIVATE_NETZE)


def lokale_adressen() -> list[str]:
    """Alle IPv4-Adressen dieses PCs, unter denen das Tablet ihn erreichen koennte."""
    adressen: set[str] = {"127.0.0.1"}
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))  # sendet nichts, waehlt nur die Route
        adressen.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        adressen.update(socket.gethostbyname_ex(socket.gethostname())[2])
    except OSError:
        pass
    return sorted(a for a in adressen if ist_privat(a))


def _jetzt() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _schluessel():
    from cryptography.hazmat.primitives.asymmetric import ec

    return ec.generate_private_key(ec.SECP256R1())


def _pem_schluessel(schluessel) -> bytes:
    from cryptography.hazmat.primitives import serialization

    return schluessel.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption())


def _ca_erzeugen(ordner: Path):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.x509.oid import NameOID

    schluessel = _schluessel()
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Renningenieur Lokale CA")])
    zert = (
        x509.CertificateBuilder()
        .subject_name(name).issuer_name(name).public_key(schluessel.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(_jetzt() - datetime.timedelta(days=1))
        .not_valid_after(_jetzt() + datetime.timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(x509.KeyUsage(
            digital_signature=True, key_cert_sign=True, crl_sign=True, content_commitment=False,
            key_encipherment=False, data_encipherment=False, key_agreement=False,
            encipher_only=False, decipher_only=False), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(schluessel.public_key()),
                       critical=False)
        .add_extension(x509.NameConstraints(
            permitted_subtrees=[x509.IPAddress(netz) for netz in PRIVATE_NETZE]
            + [x509.DNSName("localhost")], excluded_subtrees=None), critical=True)
        .sign(schluessel, hashes.SHA256())
    )
    (ordner / CA_DATEI).write_bytes(zert.public_bytes(serialization.Encoding.PEM))
    (ordner / CA_SCHLUESSEL).write_bytes(_pem_schluessel(schluessel))
    return zert, schluessel


def _ca_laden(ordner: Path):
    from cryptography import x509
    from cryptography.hazmat.primitives import serialization

    zert = x509.load_pem_x509_certificate((ordner / CA_DATEI).read_bytes())
    schluessel = serialization.load_pem_private_key((ordner / CA_SCHLUESSEL).read_bytes(), None)
    return zert, schluessel


def _server_erzeugen(ordner: Path, ca_zert, ca_schluessel, adressen: list[str]) -> None:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

    schluessel = _schluessel()
    san = [x509.DNSName("localhost")] + [x509.IPAddress(ipaddress.ip_address(a)) for a in adressen]
    zert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Renningenieur")]))
        .issuer_name(ca_zert.subject).public_key(schluessel.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(_jetzt() - datetime.timedelta(days=1))
        .not_valid_after(_jetzt() + datetime.timedelta(days=GUELTIG_TAGE))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.SubjectAlternativeName(san), critical=False)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.KeyUsage(
            digital_signature=True, key_encipherment=False, content_commitment=False,
            data_encipherment=False, key_agreement=False, key_cert_sign=False, crl_sign=False,
            encipher_only=False, decipher_only=False), critical=True)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_zert.public_key()),
                       critical=False)
        .sign(ca_schluessel, hashes.SHA256())
    )
    # Kette: Server-Zertifikat, dann CA
    (ordner / SERVER_DATEI).write_bytes(
        zert.public_bytes(serialization.Encoding.PEM) + ca_zert.public_bytes(serialization.Encoding.PEM))
    (ordner / SERVER_SCHLUESSEL).write_bytes(_pem_schluessel(schluessel))
    (ordner / ADRESSEN_DATEI).write_text("\n".join(adressen), encoding="utf-8")


def _server_noch_gut(ordner: Path, adressen: list[str]) -> bool:
    from cryptography import x509

    try:
        if (ordner / ADRESSEN_DATEI).read_text(encoding="utf-8").split() != adressen:
            return False
        zert = x509.load_pem_x509_certificate((ordner / SERVER_DATEI).read_bytes())
        rest = zert.not_valid_after_utc - _jetzt()
        return rest > datetime.timedelta(days=ERNEUERN_VOR_TAGEN) and (ordner / SERVER_SCHLUESSEL).is_file()
    except (OSError, ValueError):
        return False


def zertifikate_bereitstellen(ordner: Path, adressen: list[str] | None = None) -> tuple[Path, Path, Path]:
    """Legt CA und Server-Zertifikat an bzw. erneuert sie.

    Gibt (Zertifikatskette, Schluessel, CA-Datei zum Installieren am Tablet) zurueck.
    Wirft ImportError, wenn das Paket `cryptography` fehlt.
    """
    ordner.mkdir(parents=True, exist_ok=True)
    adressen = sorted(a for a in (adressen or lokale_adressen()) if ist_privat(a))
    try:
        ca_zert, ca_schluessel = _ca_laden(ordner)
        from cryptography import x509 as _x509

        ca_zert.extensions.get_extension_for_class(_x509.NameConstraints)
    except (OSError, ValueError, Exception):
        log.info("Erzeuge die lokale Zertifizierungsstelle (einmalig) ...")
        ca_zert, ca_schluessel = _ca_erzeugen(ordner)
        for datei in (SERVER_DATEI, SERVER_SCHLUESSEL, ADRESSEN_DATEI):
            (ordner / datei).unlink(missing_ok=True)
    if not _server_noch_gut(ordner, adressen):
        log.info("Stelle das HTTPS-Zertifikat für %s aus ...", ", ".join(adressen))
        _server_erzeugen(ordner, ca_zert, ca_schluessel, adressen)
    return ordner / SERVER_DATEI, ordner / SERVER_SCHLUESSEL, ordner / CA_DATEI
