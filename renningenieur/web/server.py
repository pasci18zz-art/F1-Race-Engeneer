"""Kleiner Webserver fuer das Tablet (nur Python-Standardbibliothek).

Seiten und Schnittstellen:
    /                    die Webseite (web/static/index.html)
    /api/live            aktueller Stand als JSON (Live-Ansicht)
    /api/sessions        gespeicherte Sessions
    /api/session?id=3    eine gespeicherte Session
    POST /api/frage      {"text": "..."}  Frage stellen, Antwort wird auch gesprochen
    POST /api/saison     {"saison_id": 1, "name": "..."}  Saison umbenennen
    POST /api/loeschen   {"id": 3}  gespeicherte Session loeschen
"""

from __future__ import annotations

import json
import logging
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from ..schnappschuss import schnappschuss

log = logging.getLogger(__name__)
STATIC = Path(__file__).parent / "static"
TYPEN = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
         ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml"}


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


class Webserver:
    def __init__(self, kern, host: str = "0.0.0.0", port: int = 8025):
        self.kern = kern
        self.host = host
        self.port = port
        self._server: ThreadingHTTPServer | None = None

    def start(self) -> None:
        kern = self.kern

        class Handler(BaseHTTPRequestHandler):
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

            def _datei(self, name: str) -> None:
                pfad = (STATIC / name).resolve()
                if STATIC.resolve() not in pfad.parents or not pfad.is_file():
                    self.send_error(404)
                    return
                body = pfad.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", TYPEN.get(pfad.suffix, "application/octet-stream"))
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self) -> None:
                url = urlparse(self.path)
                q = parse_qs(url.query)
                try:
                    if url.path == "/":
                        self._datei("index.html")
                    elif url.path == "/api/live":
                        daten = schnappschuss(kern.zustand)
                        daten["funk"] = kern.funk.protokoll[-12:]
                        self._json(daten)
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

            def do_POST(self) -> None:
                try:
                    laenge = min(int(self.headers.get("Content-Length", 0)), 10_000)
                    daten = json.loads(self.rfile.read(laenge) or b"{}")
                    pfad = urlparse(self.path).path
                    db = kern.datenbank
                    if pfad == "/api/frage":
                        text = str(daten.get("text", ""))[:200]
                        self._json({"frage": text, "antwort": kern.frage(text)})
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

        try:
            self._server = ThreadingHTTPServer((self.host, self.port), Handler)
        except OSError as e:
            raise RuntimeError(f"Web-Port {self.port} ist belegt ({e}). In config.toml unter "
                               f"[web] einen anderen Port eintragen.") from e
        self._server.daemon_threads = True
        self.port = self._server.server_address[1]
        threading.Thread(target=self._server.serve_forever, name="web", daemon=True).start()
        log.info("Tablet-Seite: http://%s:%s", lokale_ip(), self.port)

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()
