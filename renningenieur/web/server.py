"""Kleiner Webserver fuer das Tablet (nur Python-Standardbibliothek).

Er laeuft auf zwei Adressen mit derselben Seite:
    http://<PC>:8025    einfach, aber Chrome gibt hier das Mikrofon NICHT frei
    https://<PC>:8026   verschluesselt (eigenes Zertifikat), damit das Tablet
                        sein Mikrofon benutzen darf

Seiten und Schnittstellen:
    /                    die Webseite (web/static/index.html)
    /api/live            aktueller Stand als JSON (Live-Ansicht)
    /api/sessions        gespeicherte Sessions
    /api/session?id=3    eine gespeicherte Session
    /api/info            Einstellungen fuer die Mikrofon-Taste
    /api/wendepunkte     Reihenfolge bei Start, Safety Car, roter Flagge ... (Live)
    /api/bericht?id=3&format=txt|json[&download=1]   Bericht einer gespeicherten Session
    /api/bericht?live=1&format=txt|json[&download=1] Bericht der laufenden Session
    /ca.crt              Zertifizierungsstelle zum Installieren am Tablet
    POST /api/frage      {"text": "..."}  Frage stellen, Antwort wird auch gesprochen
    POST /api/sprache/start   Ingenieur schweigt kurz, waehrend das Tablet zuhoert
    POST /api/sprache/ende    Ingenieur darf wieder reden (Aufnahme abgebrochen)
    POST /api/sprache?rate=48000   Aufnahme (16 Bit, Mono) -> erkannter Text + Antwort
    GET  /api/befehle              eingebaute und eigene Befehle, Infos, Ziele
    POST /api/befehle/speichern    {"befehl": {...}}  eigenen Befehl anlegen oder aendern
    POST /api/befehle/loeschen     {"id": "..."}
    POST /api/befehle/pruefen      {"text": "...", "sprechen": false}  Frage ausprobieren
    POST /api/befehle/vorschau     {"befehl": {...}, "frage": "..."}  ungespeicherten Befehl ausprobieren
    POST /api/saison     {"saison_id": 1, "name": "..."}  Saison umbenennen
    POST /api/loeschen   {"id": 3}  gespeicherte Session loeschen
"""

from __future__ import annotations

import json
import logging
import socket
import ssl
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .. import befehle as bf
from .. import bericht
from ..schnappschuss import schnappschuss

log = logging.getLogger(__name__)
STATIC = Path(__file__).parent / "static"
TYPEN = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
         ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml",
         ".crt": "application/x-x509-ca-cert"}
MAX_AUFNAHME_BYTES = 4_000_000  # reicht fuer 20 s bei 96 kHz
MIN_RATE, MAX_RATE = 8000, 96000


def lokale_ip() -> str:
    """IP-Adresse dieses PCs im WLAN/LAN (es wird dabei nichts gesendet)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


class _TlsServer(ThreadingHTTPServer):
    """HTTP-Server mit TLS. Der Handshake laeuft im Thread der Verbindung."""

    ssl_context: ssl.SSLContext | None = None

    def get_request(self):
        sock, adresse = super().get_request()
        sock.settimeout(30)
        return self.ssl_context.wrap_socket(sock, server_side=True,
                                            do_handshake_on_connect=False), adresse

    def handle_error(self, request, client_address) -> None:
        # Das Tablet bricht ab, solange es dem Zertifikat noch nicht traut: normal
        log.debug("TLS-Verbindung von %s abgebrochen", client_address[0], exc_info=True)


class Webserver:
    def __init__(self, kern, host: str = "0.0.0.0", port: int = 8025, sprechfunk=None,
                 https_port: int = 0, zertifikat_ordner: Path | None = None,
                 tablet: dict | None = None):
        self.kern = kern
        self.host = host
        self.port = port
        self.sprechfunk = sprechfunk
        self.https_port = https_port
        self.zertifikat_ordner = zertifikat_ordner
        self.tablet = tablet or {}
        self.ca_datei: Path | None = None
        self._server: ThreadingHTTPServer | None = None
        self._https: _TlsServer | None = None

    # ------------------------------------------------------------------
    def mikrofon_bereit(self) -> bool:
        return bool(self.tablet.get("mikrofon", True) and self.sprechfunk is not None
                    and self.sprechfunk.erkennung is not None)

    def info(self) -> dict:
        t = self.tablet
        return {
            "mikrofon": self.mikrofon_bereit(),
            "https_port": self.https_port if self._https else 0,
            "stille_sekunden": float(t.get("stille_sekunden", 2.0)),
            "max_sekunden": float(t.get("max_sekunden", 8)),
            "feste_sekunden": float(t.get("feste_sekunden", 0)),
            "warten_sekunden": float(t.get("warten_sekunden", 5)),
            "ca": self.ca_datei is not None,
        }

    # --- Befehle ------------------------------------------------------
    def _fragen_und_daten(self):
        """Fragen-Objekt auf dem Live-Zustand oder, ohne Spiel, auf Beispieldaten."""
        kern = self.kern
        if kern.zustand.spieler is not None:
            return kern.fragen, "live"
        return kern.fragen.fuer_zustand(bf.demo_zustand()), "beispiel"

    def befehle_uebersicht(self) -> dict:
        from ..fragen import THEMEN

        fragen, daten = self._fragen_und_daten()
        z = fragen.z
        with z.lock:
            fahrer = [{"name": a.anzeigename, "position": a.position} for a in z.gueltige_autos()]
        return {
            "eingebaut": bf.katalog_eingebaut(THEMEN),
            "eigene": self.kern.eigene.liste(),
            "infos": bf.infos_katalog(),
            "ziele": bf.ZIELE,
            "fahrer_nennen": bf.FAHRER_NENNEN,
            "fahrer": fahrer,
            "daten": daten,
        }

    def befehl_pruefen(self, text: str, sprechen: bool) -> dict:
        fragen, daten = self._fragen_und_daten()
        antwort, (art, name) = fragen.antwort_mit_quelle(text)
        if sprechen and daten == "live":
            self.kern.funk.sagen(antwort, 2, haltbar=30)
        from ..fragen import THEMEN

        titel = {d["thema"]: d["titel"] for d in bf.katalog_eingebaut(THEMEN)}
        von = {"eigen": f"Eigener Befehl „{name}“", "eingebaut": f"Eingebaut: {titel.get(name, name)}",
               "keine": "Kein Befehl erkannt"}[art]
        return {"antwort": antwort, "von": von, "art": art, "daten": daten}

    def befehl_vorschau(self, befehl: dict, frage: str) -> dict:
        sauber, fehler = bf.validiere({**befehl, "name": befehl.get("name") or "Vorschau"})
        if sauber is None:
            return {"ok": False, "fehler": fehler}
        fragen, daten = self._fragen_und_daten()
        z = fragen.z
        with z.lock:
            ich = z.spieler
            if ich is None:
                return {"ok": False, "fehler": ["Keine Daten für die Vorschau."]}
            text = bf.norm(frage or sauber["ausloeser"][0])
            bezug, auto = fragen._bezug(text, text.split(), ich)
            antwort = bf.auswerten(sauber, fragen, ich, bezug, auto)
        return {"ok": True, "antwort": antwort, "daten": daten, "frage": frage or sauber["ausloeser"][0]}

    def _handler(self):
        web = self
        kern = self.kern

        class Handler(BaseHTTPRequestHandler):
            timeout = 30

            def setup(self) -> None:
                if isinstance(self.request, ssl.SSLSocket):
                    self.request.do_handshake()
                super().setup()

            def log_message(self, *args) -> None:  # keine Zeile pro Abruf
                pass

            def _json(self, daten, status: int = 200) -> None:
                body = json.dumps(daten, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def _bytes(self, body: bytes, typ: str, name: str | None = None) -> None:
                self.send_response(200)
                self.send_header("Content-Type", typ)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-cache")
                if name:
                    self.send_header("Content-Disposition", f'attachment; filename="{name}"')
                self.end_headers()
                self.wfile.write(body)

            def _datei(self, name: str) -> None:
                pfad = (STATIC / name).resolve()
                if STATIC.resolve() not in pfad.parents or not pfad.is_file():
                    self.send_error(404)
                    return
                self._bytes(pfad.read_bytes(), TYPEN.get(pfad.suffix, "application/octet-stream"))

            def _bericht(self, q: dict) -> None:
                if q.get("live"):
                    daten = schnappschuss(kern.zustand, mit_runden=True)
                    if not daten.get("aktiv"):
                        daten = None
                else:
                    db = kern.datenbank
                    try:
                        daten = db.session(int(q.get("id", ["0"])[0])) if db else None
                    except ValueError:
                        daten = None
                if not daten:
                    self._json({"ok": False, "fehler": "Keine Daten für den Bericht."}, 404)
                    return
                b = bericht.bericht_bauen(daten)
                json_format = q.get("format", ["txt"])[0] == "json"
                body = bericht.json_text(b) if json_format else bericht.bericht_text(b)
                endung = "json" if json_format else "txt"
                typ = "application/json" if json_format else "text/plain"
                name = bericht.dateiname(b, endung) if q.get("download") else None
                self._bytes(body.encode("utf-8"), f"{typ}; charset=utf-8", name)

            def do_GET(self) -> None:
                url = urlparse(self.path)
                q = parse_qs(url.query)
                try:
                    if url.path == "/":
                        self._datei("index.html")
                    elif url.path == "/api/live":
                        daten = schnappschuss(kern.zustand)
                        daten["funk"] = kern.funk.protokoll[-12:]
                        daten["letzter_export"] = kern.letzter_export
                        self._json(daten)
                    elif url.path == "/api/bericht":
                        self._bericht(q)
                    elif url.path == "/api/wendepunkte":
                        with kern.zustand.lock:
                            self._json({"anzahl": len(kern.zustand.momentaufnahmen),
                                        "momentaufnahmen": [dict(m) for m in kern.zustand.momentaufnahmen]})
                    elif url.path == "/api/info":
                        self._json(web.info())
                    elif url.path == "/api/befehle":
                        self._json(web.befehle_uebersicht())
                    elif url.path == "/ca.crt" and web.ca_datei:
                        self._bytes(web.ca_datei.read_bytes(), TYPEN[".crt"], "renningenieur-ca.crt")
                    elif url.path == "/api/sessions":
                        db = kern.datenbank
                        self._json(db.sessions() if db else [])
                    elif url.path == "/api/session":
                        db = kern.datenbank
                        daten = db.session(int(q.get("id", ["0"])[0])) if db else None
                        self._json(daten or {"aktiv": False}, 200 if daten else 404)
                    elif url.path.startswith("/api/"):
                        self.send_error(404)
                    else:
                        self._datei(url.path.lstrip("/"))
                except (BrokenPipeError, ConnectionError):
                    pass
                except Exception:
                    log.exception("Fehler bei %s", self.path)
                    self.send_error(500)

            def _aufnahme(self, q: dict) -> None:
                if not web.mikrofon_bereit():
                    self._json({"ok": False, "fehler": "Die Spracheingabe über das Tablet ist nicht "
                                "verfügbar. Siehe Fenster am PC."}, 503)
                    return
                laenge = int(self.headers.get("Content-Length", 0))
                rate = int(q.get("rate", ["16000"])[0])
                if not 0 < laenge <= MAX_AUFNAHME_BYTES or not MIN_RATE <= rate <= MAX_RATE:
                    self.send_error(400)
                    return
                daten = self.rfile.read(laenge)
                self._json(web.sprechfunk.tablet_frage(daten, rate))

            def do_POST(self) -> None:
                try:
                    url = urlparse(self.path)
                    pfad = url.path
                    if pfad == "/api/sprache":
                        self._aufnahme(parse_qs(url.query))
                        return
                    laenge = min(int(self.headers.get("Content-Length", 0)), 40_000)
                    daten = json.loads(self.rfile.read(laenge) or b"{}")
                    db = kern.datenbank
                    if pfad == "/api/sprache/start":
                        kern.funk.stumm_fuer(15)  # faellt von selbst ab, falls die Aufnahme abbricht
                        self._json({"ok": True})
                    elif pfad == "/api/sprache/ende":
                        kern.funk.stumm_fuer(0)
                        self._json({"ok": True})
                    elif pfad == "/api/frage":
                        text = str(daten.get("text", ""))[:200]
                        self._json({"frage": text, "antwort": kern.frage(text)})
                    elif pfad == "/api/befehle/speichern":
                        sauber, fehler = kern.eigene.speichern(daten.get("befehl") or {})
                        self._json({"ok": sauber is not None, "befehl": sauber, "fehler": fehler,
                                    "eigene": kern.eigene.liste()})
                    elif pfad == "/api/befehle/loeschen":
                        self._json({"ok": kern.eigene.loeschen(str(daten.get("id", ""))),
                                    "eigene": kern.eigene.liste()})
                    elif pfad == "/api/befehle/pruefen":
                        self._json(web.befehl_pruefen(str(daten.get("text", ""))[:200],
                                                      bool(daten.get("sprechen"))))
                    elif pfad == "/api/befehle/vorschau":
                        self._json(web.befehl_vorschau(daten.get("befehl") or {},
                                                       str(daten.get("frage", ""))[:200]))
                    elif pfad == "/api/saison" and db:
                        db.saison_umbenennen(int(daten["saison_id"]), str(daten.get("name", "")))
                        self._json({"ok": True})
                    elif pfad == "/api/loeschen" and db:
                        db.session_loeschen(int(daten["id"]))
                        self._json({"ok": True})
                    else:
                        self.send_error(404)
                except (BrokenPipeError, ConnectionError):
                    pass
                except (ValueError, KeyError, TypeError):
                    self.send_error(400)
                except Exception:
                    log.exception("Fehler bei %s", self.path)
                    self.send_error(500)

        return Handler

    # ------------------------------------------------------------------
    def start(self) -> None:
        handler = self._handler()
        try:
            self._server = ThreadingHTTPServer((self.host, self.port), handler)
        except OSError as e:
            raise RuntimeError(f"Web-Port {self.port} ist belegt ({e}). In config.toml unter "
                               f"[web] einen anderen Port eintragen.") from e
        self._server.daemon_threads = True
        self.port = self._server.server_address[1]
        threading.Thread(target=self._server.serve_forever, name="web", daemon=True).start()
        threading.Thread(target=bf.demo_zustand, name="beispieldaten", daemon=True).start()
        ip = lokale_ip()
        log.info("Tablet-Seite: http://%s:%s", ip, self.port)
        if self.https_port and self.tablet.get("mikrofon", True):
            self._https_starten(handler, ip)

    def _https_starten(self, handler, ip: str) -> None:
        try:
            from .zertifikat import zertifikate_bereitstellen

            kette, schluessel, ca = zertifikate_bereitstellen(
                self.zertifikat_ordner or Path("zertifikat"))
        except ImportError:
            log.warning("Tablet-Mikrofon aus: Das Paket 'cryptography' fehlt. "
                        "installieren.bat ausführen.")
            return
        except Exception as e:
            log.warning("Tablet-Mikrofon aus: Zertifikat konnte nicht erstellt werden (%s)", e)
            return
        self.ca_datei = ca
        try:
            kontext = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            kontext.minimum_version = ssl.TLSVersion.TLSv1_2
            kontext.load_cert_chain(str(kette), str(schluessel))
            server = _TlsServer((self.host, self.https_port), handler)
        except OSError as e:
            log.warning("Tablet-Mikrofon aus: HTTPS-Port %s ist belegt (%s). In config.toml "
                        "unter [web] https_port ändern.", self.https_port, e)
            return
        server.ssl_context = kontext
        server.daemon_threads = True
        self.https_port = server.server_address[1]
        self._https = server
        threading.Thread(target=server.serve_forever, name="web-https", daemon=True).start()
        log.info("Tablet-Seite mit Mikrofon: https://%s:%s", ip, self.https_port)
        from .zertifikat import ist_privat

        if not ist_privat(ip):
            log.warning("Die Adresse dieses PCs (%s) liegt nicht in einem üblichen Heimnetz-Bereich "
                        "(192.168.x.x, 10.x.x.x, 172.16-31.x.x). Das Zertifikat gilt dafür nicht, das "
                        "Tablet meldet dann einen Namensfehler.", ip)

    def stop(self) -> None:
        for server in (self._server, self._https):
            if server:
                server.shutdown()
                server.server_close()
