"""Startprogramm und Befehle.

    python -m renningenieur                 Renningenieur starten
    python -m renningenieur simulation      simuliertes Rennen senden (zweites Fenster)
    python -m renningenieur geraete         Mikrofone, Stimmen, Lenkradtasten anzeigen
    python -m renningenieur modell          Sprachmodell herunterladen
    python -m renningenieur mikrofontest    Mikrofon und Spracherkennung ausprobieren
    python -m renningenieur whisper         genauere Spracherkennung installieren
    python -m renningenieur stimmen         natuerliche Stimmen anhoeren und auswaehlen
    python -m renningenieur abspielen X     aufgezeichnete Telemetrie abspielen
    python -m renningenieur pruefen         empfangene Pakete zaehlen und pruefen
"""

from __future__ import annotations

import argparse
import logging
import sys
import threading
import time
from pathlib import Path

from . import config as konfig

log = logging.getLogger("renningenieur")


def _logging(ausfuehrlich: bool = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if ausfuehrlich else logging.INFO,
        format="%(asctime)s  %(message)s",
        datefmt="%H:%M:%S",
    )


# --------------------------------------------------------------------------
def befehl_start(args) -> int:
    from .datenbank import Datenbank
    from .kern import Kern
    from .sprache.sprechfunk import Sprechfunk
    from .sprache.stimmen import stimme_erzeugen
    from .telemetrie.aufnahme import Aufnahme
    from .telemetrie.relay import Relay
    from .web.server import Webserver

    ordner = Path(args.ordner).resolve()
    ordner.mkdir(parents=True, exist_ok=True)
    cfg = konfig.config_laden(ordner, kopieren=True)
    texte = konfig.texte_laden(ordner, kopieren=True)
    if args.port:
        cfg["udp"]["port"] = args.port
    if args.stumm:
        cfg["sprachausgabe"]["engine"] = "konsole"
    if args.ohne_mikrofon:
        cfg["mikrofon"]["quelle"] = "tablet"  # kein PC-Mikrofon, die Tablet-Taste bleibt

    datenbank = None
    if cfg["datenbank"].get("aktiv", True):
        datenbank = Datenbank(str(ordner / cfg["datenbank"]["datei"]))
        datenbank.start()

    kern = Kern(cfg, texte, stimme_erzeugen(cfg["sprachausgabe"], ordner), datenbank, ordner)
    kern.funk.start()

    aufnahme = Aufnahme(args.aufnahme) if args.aufnahme else None

    def paket(data: bytes) -> None:
        if aufnahme:
            aufnahme.schreiben(data)
        kern.paket(data)

    relay = Relay(cfg["udp"].get("host", "0.0.0.0"), cfg["udp"]["port"],
                  konfig.adressen(cfg["udp"].get("weiterleiten", [])), paket)
    web = None
    sprechfunk = Sprechfunk(kern, cfg, ordner)
    try:
        relay.start()
        if cfg["web"].get("aktiv", True):
            web = Webserver(kern, cfg["web"].get("host", "0.0.0.0"), cfg["web"]["port"],
                            sprechfunk=sprechfunk, https_port=cfg["web"].get("https_port", 0),
                            zertifikat_ordner=ordner / "zertifikat", tablet=cfg.get("tablet", {}))
            web.start()
    except RuntimeError as e:
        log.error("%s", e)
        kern.funk.stop()
        return 1
    for host, port in relay.ziele:
        log.info("SimHub muss dafür auf Port %s hören (F1 25, Game config, UDP-Port).", port)
    sprechfunk.start()

    log.info("Bereit. Fragen kannst du auch hier eintippen. Beenden mit Strg+C.")
    threading.Thread(target=_tastatur_fragen, args=(kern,), daemon=True).start()
    try:
        gemeldet = 0
        format_gemeldet = False
        ziel_zustand: dict = {}
        while True:
            time.sleep(5)
            _ziele_pruefen(relay, ziel_zustand)
            if relay.empfangen == 0:
                gemeldet += 1
                if gemeldet in (3, 12):
                    log.info("Noch keine Telemetrie. Im Spiel: Einstellungen > Telemetrie > "
                             "UDP an, IP 127.0.0.1, Port %s.", relay.port)
            elif not format_gemeldet and kern.zustand.packet_format:
                format_gemeldet = True
                log.info("Telemetrie läuft (UDP-Format %s).", kern.zustand.packet_format)
    except KeyboardInterrupt:
        log.info("Beende ...")
    finally:
        sprechfunk.stop()
        relay.stop()
        if web:
            web.stop()
        if datenbank:
            datenbank.stop()
            datenbank.sichern(kern.zustand)  # letzter Stand
        if aufnahme:
            aufnahme.schliessen()
            log.info("%s Pakete aufgezeichnet in %s", aufnahme.anzahl, args.aufnahme)
        kern.funk.stop()
    return 0


def _ziele_pruefen(relay, bisher: dict) -> None:
    """Meldet, ob die Weiterleitungsziele (z. B. SimHub) die Pakete annehmen."""
    if relay.empfangen == 0:
        return
    for adresse, zustand in relay.pruefe_ziele():
        if zustand == "unbekannt" or bisher.get(adresse) == zustand:
            continue
        host, port = adresse
        if zustand == "abgelehnt":
            log.warning(
                "Weiterleitung an %s:%s: Dort hört niemand zu. SimHub zeigt deshalb keine Daten. "
                "In SimHub bei F1 25 unter Game config muss als UDP-Port %s stehen "
                "(danach SimHub neu starten).", host, port, port)
        elif adresse in bisher:
            log.info("Weiterleitung an %s:%s funktioniert wieder.", host, port)
        else:
            log.info("Weiterleitung an %s:%s funktioniert (SimHub empfängt).", host, port)
        bisher[adresse] = zustand


def _tastatur_fragen(kern) -> None:
    """Fragen im Programmfenster eintippen (zum Testen ohne Mikrofon)."""
    try:
        for zeile in sys.stdin:
            zeile = zeile.strip()
            if zeile:
                log.info("Antwort: %s", kern.frage(zeile))
    except (OSError, ValueError):
        pass


# --------------------------------------------------------------------------
def befehl_simulation(args) -> int:
    from .simulator import SZENARIEN, Simulator, senden

    if args.liste:
        print("Szenarien:", ", ".join(SZENARIEN))
        return 0
    runden = args.runden or (4 if args.szenario == "qualifying" else 12)
    sim = Simulator(args.szenario, fmt=args.format, runden=runden, seed=args.seed,
                    strecke_id=args.strecke, saison_id=args.saison, wochenende_id=args.wochenende)
    print(f"Simuliere Szenario '{args.szenario}' (UDP-Format {args.format}, {runden} Runden) "
          f"an {args.host}:{args.port}, Tempo {args.tempo}x. Abbrechen mit Strg+C.")
    try:
        anzahl = senden(sim, args.host, args.port, args.tempo)
    except KeyboardInterrupt:
        print("Abgebrochen.")
        return 0
    print(f"Fertig, {anzahl} Pakete gesendet.")
    return 0


def befehl_abspielen(args) -> int:
    from .telemetrie.aufnahme import abspielen

    print(f"Spiele {args.datei} an {args.host}:{args.port} ab (Tempo {args.tempo}x) ...")
    try:
        anzahl = abspielen(args.datei, args.host, args.port, args.tempo)
    except KeyboardInterrupt:
        print("Abgebrochen.")
        return 0
    print(f"Fertig, {anzahl} Pakete gesendet.")
    return 0


def befehl_pruefen(args) -> int:
    """Hoert auf dem UDP-Port und zeigt, welche Pakete ankommen und ob sie zur Spec passen."""
    import collections

    from .telemetrie import parser, spec
    from .telemetrie.relay import Relay

    cfg = konfig.config_laden(Path(args.ordner).resolve())
    zaehler: collections.Counter = collections.Counter()
    fehler: collections.Counter = collections.Counter()

    def paket(data: bytes) -> None:
        try:
            h = parser.parse_header(data)
            parser.parse(data)
            zaehler[(h["packet_format"], h["packet_id"], len(data))] += 1
        except parser.PaketFehler as e:
            fehler[str(e)] += 1

    relay = Relay(port=args.port or cfg["udp"]["port"],
                  ziele=konfig.adressen(cfg["udp"].get("weiterleiten", [])), on_packet=paket)
    try:
        relay.start()
    except RuntimeError as e:
        print(e)
        return 1
    print(f"Höre {args.sekunden} Sekunden auf Port {relay.port} (Weiterleitung bleibt aktiv) ...")
    try:
        time.sleep(args.sekunden)
    except KeyboardInterrupt:
        pass
    relay.stop()
    if not zaehler and not fehler:
        print("Nichts empfangen. Ist die UDP-Telemetrie im Spiel an und der Port richtig?")
        return 1
    print(f"{'Format':>6}  {'Paket':<22}{'Bytes':>6}{'Anzahl':>8}")
    for (fmt, pid, groesse), n in sorted(zaehler.items()):
        print(f"{fmt:>6}  {spec.PACKET_NAMES.get(pid, pid):<22}{groesse:>6}{n:>8}")
    for text, n in fehler.items():
        print(f"FEHLER ({n}x): {text}")
    if not fehler:
        print("Alle Pakete passen zur Spec.")
    return 1 if fehler else 0


def befehl_geraete(args) -> int:
    from .sprache.stimmen import geraete_auflisten

    print("=== Mikrofone ===")
    try:
        from .sprache.mikrofon import eingabegeraete

        for nummer, name, treiber in eingabegeraete():
            print(f"  {nummer:>3}  {name}  [{treiber}]")
        print('  -> In config.toml unter [mikrofon] geraet = "Teil des Namens" oder die Nummer.')
    except Exception as e:
        print(f"  Nicht verfügbar ({e}). Installieren mit: pip install -r requirements.txt")
    print("\n=== Windows-Sprachausgabe ===")
    print(geraete_auflisten())
    print("\n=== Lenkräder und Controller ===")
    from .sprache.funktaste import tasten_finden

    tasten_finden(dauer=args.sekunden)
    return 0


def befehl_stimmen(args) -> int:
    from .sprache.piper_stimme import einrichten

    ordner = Path(args.ordner).resolve()
    cfg = konfig.config_laden(ordner, kopieren=True)
    return einrichten(ordner, cfg["sprachausgabe"])


def befehl_mikrofontest(args) -> int:
    from .sprache.mikrofontest import testen

    ordner = Path(args.ordner).resolve()
    cfg = konfig.config_laden(ordner, kopieren=True)
    return testen(cfg, ordner, sekunden=args.sekunden)


def befehl_whisper(args) -> int:
    from .sprache import whisper_einrichtung

    ordner = Path(args.ordner).resolve()
    cfg = konfig.config_laden(ordner, kopieren=True)
    return whisper_einrichtung.einrichten(ordner, cfg, args.modell)


def befehl_modell(args) -> int:
    from .sprache.erkennung import modell_laden

    try:
        modell_laden(Path(args.ordner).resolve() / "modelle")
    except Exception as e:
        print(f"Download fehlgeschlagen: {e}")
        return 1
    return 0


# --------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="renningenieur",
                                description="Eigener Renningenieur für F1 25 (läuft komplett lokal).")
    p.add_argument("--ordner", default=".", help="Ordner für config.toml, texte.toml, Datenbank")
    p.add_argument("--ausfuehrlich", action="store_true", help="mehr Meldungen im Fenster")
    sub = p.add_subparsers(dest="befehl")

    s = sub.add_parser("start", help="Renningenieur starten (Standard)")
    for parser in (p, s):
        parser.add_argument("--port", type=int, default=0, help="UDP-Port (statt config.toml)")
        parser.add_argument("--stumm", action="store_true", help="nur Text, keine Sprachausgabe")
        parser.add_argument("--ohne-mikrofon", action="store_true", help="PC-Mikrofon nicht öffnen")
        parser.add_argument("--aufnahme", metavar="DATEI", help="Telemetrie in Datei mitschneiden")

    s = sub.add_parser("simulation", help="simuliertes Rennen per UDP senden")
    s.add_argument("szenario", nargs="?", default="alles")
    s.add_argument("--liste", action="store_true", help="Szenarien anzeigen")
    s.add_argument("--tempo", type=float, default=1.0, help="Zeitraffer, z. B. 5")
    s.add_argument("--format", type=int, default=2025, choices=(2025, 2026))
    s.add_argument("--runden", type=int, default=0, help="Rennrunden (Standard 12, Qualifying 4)")
    s.add_argument("--seed", type=int, default=1)
    s.add_argument("--strecke", type=int, default=11, help="Strecken-ID (11 = Monza)")
    s.add_argument("--saison", type=int, default=2025001)
    s.add_argument("--wochenende", type=int, default=1)
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=20777)

    s = sub.add_parser("abspielen", help="aufgezeichnete Telemetrie abspielen")
    s.add_argument("datei")
    s.add_argument("--tempo", type=float, default=1.0)
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=20777)

    s = sub.add_parser("pruefen", help="empfangene Pakete gegen die Spec prüfen")
    s.add_argument("--sekunden", type=float, default=15)
    s.add_argument("--port", type=int, default=0)

    s = sub.add_parser("geraete", help="Mikrofone, Stimmen und Lenkradtasten anzeigen")
    s.add_argument("--sekunden", type=float, default=30)

    sub.add_parser("modell", help="Sprachmodell für die Erkennung herunterladen")
    sub.add_parser("stimmen", help="natürliche Stimmen laden, anhören und auswählen")

    s = sub.add_parser("mikrofontest", help="Mikrofon und Spracherkennung ausprobieren")
    s.add_argument("--sekunden", type=float, default=5)

    s = sub.add_parser("whisper", help="genauere Spracherkennung (Whisper) installieren")
    s.add_argument("modell", nargs="?", default="", help="tiny, base, small oder medium")

    args = p.parse_args(argv)
    _logging(args.ausfuehrlich)
    befehle = {
        None: befehl_start, "start": befehl_start, "simulation": befehl_simulation,
        "abspielen": befehl_abspielen, "pruefen": befehl_pruefen,
        "geraete": befehl_geraete, "modell": befehl_modell, "stimmen": befehl_stimmen,
        "mikrofontest": befehl_mikrofontest, "whisper": befehl_whisper,
    }
    return befehle[args.befehl](args)
