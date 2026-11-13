"""Lokale SQLite-Datenbank: jede Session mit Teilnehmern, Stints,
Boxenstopps, Wetterverlauf, Rundenzeiten und Ereignissen.

Gespeichert wird immer der komplette Stand einer Session (alte Zeilen der
Session werden ersetzt). Das passiert bei jeder Fuehrungsrunde, bei roter
Flagge und am Ende. Dadurch stimmen die Daten auch nach Rueckblenden.

Geschrieben wird in einem eigenen Thread, damit der UDP-Empfang nie auf
die Festplatte warten muss.

Tabellen: saisons, sessions, teilnehmer, stints, boxenstopps, wetter,
runden, ereignisse. Die Datei laesst sich mit jedem SQLite-Programm oeffnen
(z. B. "DB Browser for SQLite").
"""

from __future__ import annotations

import logging
import queue
import sqlite3
import threading
from datetime import datetime

from .auswertung import Ereignis
from .schnappschuss import schnappschuss
from .zustand import Rennzustand

log = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS saisons (
    saison_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_uid TEXT NOT NULL UNIQUE,
    saison_id INTEGER NOT NULL DEFAULT 0,
    wochenende_id INTEGER NOT NULL DEFAULT 0,
    session_link_id INTEGER NOT NULL DEFAULT 0,
    strecke_id INTEGER,
    strecke TEXT,
    session_typ INTEGER,
    typ_name TEXT,
    ist_rennen INTEGER NOT NULL DEFAULT 0,
    runden_gesamt INTEGER,
    runden_gefahren INTEGER,
    begonnen TEXT,
    aktualisiert TEXT,
    beendet INTEGER NOT NULL DEFAULT 0,
    spieler_idx INTEGER,
    rote_flaggen INTEGER NOT NULL DEFAULT 0,
    packet_format INTEGER,
    notiz TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS teilnehmer (
    session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    idx INTEGER NOT NULL,
    name TEXT, team_id INTEGER, team TEXT, farbe TEXT, startnummer INTEGER,
    ki INTEGER, ist_spieler INTEGER, startplatz INTEGER, position INTEGER,
    result_status INTEGER, status TEXT, punkte INTEGER, runden_gefahren INTEGER,
    beste_runde_ms INTEGER, gesamtzeit_s REAL, strafen_s INTEGER,
    boxenstopps_anzahl INTEGER, rueckstand_ms INTEGER,
    PRIMARY KEY (session_id, idx)
);
CREATE TABLE IF NOT EXISTS stints (
    session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    idx INTEGER NOT NULL, nr INTEGER NOT NULL,
    visuell INTEGER, tatsaechlich INTEGER, mischung TEXT, kurz TEXT, farbe TEXT,
    start_runde INTEGER, end_runde INTEGER, alter_start INTEGER,
    PRIMARY KEY (session_id, idx, nr)
);
CREATE TABLE IF NOT EXISTS boxenstopps (
    session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    idx INTEGER NOT NULL, nr INTEGER NOT NULL,
    runde INTEGER, zeit REAL, zeit_gasse_ms INTEGER, standzeit_ms INTEGER,
    PRIMARY KEY (session_id, idx, nr)
);
CREATE TABLE IF NOT EXISTS wetter (
    session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    nr INTEGER NOT NULL,
    zeit REAL, runde INTEGER, wetter INTEGER, wetter_name TEXT,
    streckentemperatur INTEGER, lufttemperatur INTEGER,
    PRIMARY KEY (session_id, nr)
);
CREATE TABLE IF NOT EXISTS runden (
    session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    idx INTEGER NOT NULL, runde INTEGER NOT NULL,
    zeit_ms INTEGER, position INTEGER, delta_fuehrender_ms INTEGER,
    reifen_visuell INTEGER, reifenalter INTEGER, verschleiss REAL,
    gueltig INTEGER, s1_ms INTEGER, s2_ms INTEGER, s3_ms INTEGER, box INTEGER,
    PRIMARY KEY (session_id, idx, runde)
);
CREATE TABLE IF NOT EXISTS ereignisse (
    session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    nr INTEGER NOT NULL,
    zeit REAL, runde INTEGER, code TEXT, idx INTEGER, text TEXT,
    PRIMARY KEY (session_id, nr)
);
CREATE INDEX IF NOT EXISTS sessions_saison ON sessions(saison_id, begonnen);
"""


def _verbinden(pfad: str) -> sqlite3.Connection:
    con = sqlite3.connect(pfad, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


class Datenbank:
    def __init__(self, pfad: str):
        self.pfad = pfad
        con = _verbinden(pfad)
        try:
            con.execute("PRAGMA journal_mode = WAL")
            con.executescript(SCHEMA)
            con.commit()
        finally:
            con.close()
        self._queue: queue.Queue = queue.Queue()
        self._thread: threading.Thread | None = None
        self._letzte_runde = -1

    # --- Schreiben ----------------------------------------------------
    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="datenbank", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._thread:
            self._queue.put(None)
            self._thread.join(timeout=10)
            self._thread = None

    def _run(self) -> None:
        while True:
            daten = self._queue.get()
            if daten is None:
                return
            try:
                self._speichern(daten)
            except Exception:
                log.exception("Speichern in der Datenbank fehlgeschlagen")

    def ereignis(self, e: Ereignis, z: Rennzustand) -> None:
        """Entscheidet, wann gespeichert wird."""
        if e.typ == "session_start":
            self._letzte_runde = -1
        speichern = e.typ in ("klassifizierung", "session_ende", "rote_flagge", "restart")
        if e.typ == "runde":
            runde = z.fuehrungsrunde()
            if runde != self._letzte_runde:
                self._letzte_runde = runde
                speichern = True
        if speichern:
            self.sichern(z)

    def sichern(self, z: Rennzustand) -> None:
        """Aktuellen Stand der Session zum Speichern einreihen."""
        daten = schnappschuss(z, mit_runden=True)
        if not daten.get("aktiv") or not daten["autos"]:
            return
        if self._thread is None:
            self._speichern(daten)  # Tests und Programmende: sofort schreiben
        else:
            self._queue.put(daten)

    def _speichern(self, d: dict) -> None:
        s = d["session"]
        jetzt = datetime.now().isoformat(timespec="seconds")
        con = _verbinden(self.pfad)
        try:
            with con:
                con.execute(
                    "INSERT OR IGNORE INTO saisons (saison_id, name) VALUES (?, ?)",
                    (s["saison_id"], _saison_name(con, s["saison_id"])),
                )
                zeile = con.execute(
                    "SELECT id FROM sessions WHERE session_uid = ?", (s["session_uid"],)
                ).fetchone()
                if zeile is None:
                    cur = con.execute(
                        "INSERT INTO sessions (session_uid, begonnen) VALUES (?, ?)",
                        (s["session_uid"], jetzt),
                    )
                    sid = cur.lastrowid
                else:
                    sid = zeile["id"]
                con.execute(
                    """UPDATE sessions SET saison_id=?, wochenende_id=?, session_link_id=?,
                       strecke_id=?, strecke=?, session_typ=?, typ_name=?, ist_rennen=?,
                       runden_gesamt=?, runden_gefahren=?, aktualisiert=?, beendet=?,
                       spieler_idx=?, rote_flaggen=?, packet_format=? WHERE id=?""",
                    (s["saison_id"], s["wochenende_id"], s["session_link_id"], s["strecke_id"],
                     s["strecke"], s["session_typ"], s["typ_name"], int(s["ist_rennen"]),
                     s["runden_gesamt"], s["runde"], jetzt, int(s["beendet"]), s["spieler_idx"],
                     s["rote_flaggen_anzahl"], s["packet_format"], sid),
                )
                for tabelle in ("teilnehmer", "stints", "boxenstopps", "wetter", "runden",
                                "ereignisse"):
                    con.execute(f"DELETE FROM {tabelle} WHERE session_id = ?", (sid,))
                for a in d["autos"]:
                    con.execute(
                        "INSERT INTO teilnehmer VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (sid, a["idx"], a["name"], a["team_id"], a["team"], a["farbe"],
                         a["startnummer"], int(a["ki"]), int(a["ist_spieler"]), a["startplatz"],
                         a["position"], a["result_status"], a["status"], a.get("punkte"),
                         a.get("runden_gefahren", len(a.get("runden", []))),
                         a["beste_runde_ms"], a.get("gesamtzeit_s"), a["strafen_s"],
                         a["boxenstopps_anzahl"], a["rueckstand_ms"]),
                    )
                    con.executemany(
                        "INSERT INTO stints VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                        [(sid, a["idx"], n, st["visuell"], st["tatsaechlich"], st["mischung"],
                          st["kurz"], st["farbe"], st["start_runde"], st["end_runde"],
                          st["alter_start"]) for n, st in enumerate(a["stints"], 1)],
                    )
                    con.executemany(
                        "INSERT INTO boxenstopps VALUES (?,?,?,?,?,?,?)",
                        [(sid, a["idx"], n, b["runde"], b["zeit"], b["zeit_gasse_ms"],
                          b["standzeit_ms"]) for n, b in enumerate(a["boxenstopps"], 1)],
                    )
                    con.executemany(
                        "INSERT INTO runden VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        [(sid, a["idx"], r["runde"], r["zeit_ms"], r.get("position"),
                          r.get("delta_fuehrender_ms"), r.get("reifen_visuell"),
                          r.get("reifenalter"), r.get("verschleiss"),
                          None if r.get("gueltig") is None else int(r["gueltig"]),
                          r.get("s1_ms"), r.get("s2_ms"), r.get("s3_ms"),
                          int(bool(r.get("box")))) for r in a.get("runden", [])],
                    )
                con.executemany(
                    "INSERT INTO wetter VALUES (?,?,?,?,?,?,?,?)",
                    [(sid, n, w["zeit"], w["runde"], w["wetter"], w["wetter_name"],
                      w["streckentemperatur"], w["lufttemperatur"])
                     for n, w in enumerate(d["wetter_log"], 1)],
                )
                con.executemany(
                    "INSERT INTO ereignisse VALUES (?,?,?,?,?,?,?)",
                    [(sid, n, e["zeit"], e["runde"], e["code"], e["idx"], e["text"])
                     for n, e in enumerate(d["ereignisse"], 1)],
                )
        finally:
            con.close()

    # --- Lesen (fuer die Webseite) -------------------------------------
    def sessions(self, nur_rennen: bool = False) -> list[dict]:
        con = _verbinden(self.pfad)
        try:
            zeilen = con.execute(
                """SELECT s.*, sa.name AS saison_name,
                          (SELECT position FROM teilnehmer t
                            WHERE t.session_id = s.id AND t.ist_spieler = 1) AS spieler_position,
                          (SELECT name FROM teilnehmer t
                            WHERE t.session_id = s.id AND t.position = 1) AS sieger
                   FROM sessions s LEFT JOIN saisons sa ON sa.saison_id = s.saison_id
                   WHERE (? = 0 OR s.ist_rennen = 1)
                   ORDER BY s.begonnen DESC, s.id DESC""",
                (int(nur_rennen),),
            ).fetchall()
            liste = []
            for zeile in zeilen:
                d = dict(zeile)
                spieler = con.execute(
                    "SELECT idx, startplatz, boxenstopps_anzahl, name FROM teilnehmer "
                    "WHERE session_id = ? AND ist_spieler = 1", (d["id"],)).fetchone()
                d["spieler_startplatz"] = spieler["startplatz"] if spieler else None
                d["spieler_stopps"] = spieler["boxenstopps_anzahl"] if spieler else None
                d["spieler_stints"] = [dict(st) for st in con.execute(
                    "SELECT mischung, kurz, farbe, start_runde, end_runde FROM stints "
                    "WHERE session_id = ? AND idx = ? ORDER BY nr",
                    (d["id"], spieler["idx"]))] if spieler else []
                wetter = [w["wetter"] for w in con.execute(
                    "SELECT wetter FROM wetter WHERE session_id = ? ORDER BY nr", (d["id"],))]
                d["wetter_folge"] = wetter
                d["nass"] = any(w >= 3 for w in wetter)
                liste.append(d)
            return liste
        finally:
            con.close()

    def session(self, sid: int) -> dict | None:
        """Eine gespeicherte Session im selben Format wie die Live-Ansicht."""
        con = _verbinden(self.pfad)
        try:
            s = con.execute(
                """SELECT s.*, sa.name AS saison_name FROM sessions s
                   LEFT JOIN saisons sa ON sa.saison_id = s.saison_id WHERE s.id = ?""",
                (sid,),
            ).fetchone()
            if s is None:
                return None

            def alle(tabelle: str, ordnung: str) -> list[dict]:
                return [dict(z) for z in con.execute(
                    f"SELECT * FROM {tabelle} WHERE session_id = ? ORDER BY {ordnung}", (sid,))]

            autos = alle("teilnehmer", "position")
            nach_idx = {a["idx"]: a for a in autos}
            for a in autos:
                a.update(stints=[], boxenstopps=[], runden=[],
                         ki=bool(a["ki"]), ist_spieler=bool(a["ist_spieler"]))
            for st in alle("stints", "idx, nr"):
                nach_idx[st["idx"]]["stints"].append(st)
            for b in alle("boxenstopps", "idx, nr"):
                nach_idx[b["idx"]]["boxenstopps"].append(b)
            for r in alle("runden", "idx, runde"):
                nach_idx[r["idx"]]["runden"].append(r)
            session = dict(s)
            session["runde"] = session["runden_gefahren"]
            session["ist_rennen"] = bool(session["ist_rennen"])
            session["beendet"] = bool(session["beendet"])
            return {
                "aktiv": True,
                "gespeichert": True,
                "session": session,
                "wetter_log": alle("wetter", "nr"),
                "ereignisse": alle("ereignisse", "nr"),
                "autos": autos,
            }
        finally:
            con.close()

    def saison_umbenennen(self, saison_id: int, name: str) -> None:
        con = _verbinden(self.pfad)
        try:
            with con:
                con.execute(
                    "INSERT INTO saisons (saison_id, name) VALUES (?, ?) "
                    "ON CONFLICT(saison_id) DO UPDATE SET name = excluded.name",
                    (saison_id, name.strip()[:60] or f"Saison {saison_id}"),
                )
        finally:
            con.close()

    def session_loeschen(self, sid: int) -> None:
        con = _verbinden(self.pfad)
        try:
            with con:
                con.execute("DELETE FROM sessions WHERE id = ?", (sid,))
        finally:
            con.close()


def _saison_name(con: sqlite3.Connection, saison_id: int) -> str:
    if not saison_id:
        return "Ohne Saison"
    anzahl = con.execute("SELECT COUNT(*) FROM saisons WHERE saison_id != 0").fetchone()[0]
    return f"Saison {anzahl + 1}"
