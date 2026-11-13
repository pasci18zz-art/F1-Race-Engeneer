"""Der aktuelle Rennzustand: alles, was aus der Telemetrie bekannt ist.

Dieses Modul enthaelt nur Daten und einfache Abfragen (wer ist vor mir, wie
gross ist der Abstand, ...). Befuellt wird es von auswertung.py.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

from .telemetrie import konstanten as k


@dataclass
class Stint:
    visuell: int  # visuelle Mischung (16 Soft, 17 Medium, 18 Hard, 7 Inter, 8 Wet)
    tatsaechlich: int  # C-Nummer
    start_runde: int
    end_runde: int | None = None  # None = laeuft noch
    alter_start: int = 0  # Reifenalter beim Aufziehen (gebrauchter Satz)

    def als_dict(self) -> dict:
        r = k.reifen(self.visuell)
        return {
            "visuell": self.visuell,
            "tatsaechlich": self.tatsaechlich,
            "mischung": r["name"],
            "kurz": r["kurz"],
            "farbe": r["farbe"],
            "start_runde": self.start_runde,
            "end_runde": self.end_runde,
            "alter_start": self.alter_start,
        }


@dataclass
class Boxenstopp:
    runde: int
    session_time: float
    zeit_gasse_ms: int = 0  # Zeit in der Boxengasse
    standzeit_ms: int = 0  # Standzeit
    fertig: bool = False


@dataclass
class Auto:
    idx: int
    # --- Teilnehmer ---
    name: str = ""
    team_id: int = 255
    startnummer: int = 0
    ki: bool = True
    telemetrie_oeffentlich: bool = True
    lackfarbe: str | None = None
    # --- Lap Data ---
    position: int = 0
    runde: int = 0  # aktuelle Rundennummer
    pit_status: int = 0
    boxenstopps_anzahl: int = 0
    startplatz: int = 0
    driver_status: int = 0
    result_status: int = 0
    letzte_runde_ms: int = 0
    delta_vorne_ms: int = 0
    delta_fuehrender_ms: int = 0
    rundendistanz: float = 0.0
    gesamtdistanz: float = 0.0
    strafen_s: int = 0
    # --- Car Status ---
    reifen_visuell: int = 0
    reifen_tatsaechlich: int = 0
    reifenalter: int = 0
    sprit_runden: float = 0.0
    sprit_kg: float = 0.0
    flagge: int = 0
    status_bekannt: bool = False
    # --- Car Damage ---
    reifenverschleiss: list[float] = field(default_factory=lambda: [0.0] * 4)
    fluegel_vl: int = 0
    fluegel_vr: int = 0
    heckfluegel: int = 0
    unterboden: int = 0
    diffusor: int = 0
    seitenkasten: int = 0
    schaden_bekannt: bool = False
    # --- Verlauf ---
    rundenzeiten: dict[int, int] = field(default_factory=dict)  # Runde -> ms
    runden_info: dict[int, dict] = field(default_factory=dict)  # Runde -> Details
    stints: list[Stint] = field(default_factory=list)
    stints_aus_historie: bool = False
    boxenstopps: list[Boxenstopp] = field(default_factory=list)
    beste_runde_ms: int = 0

    # ------------------------------------------------------------------
    @property
    def gueltig(self) -> bool:
        """Faehrt dieses Auto in der Session ueberhaupt mit?"""
        return self.position > 0 and self.result_status not in (0, 1)

    @property
    def im_rennen(self) -> bool:
        return self.position > 0 and self.result_status == k.RESULT_AKTIV

    @property
    def in_box(self) -> bool:
        return self.pit_status != k.PIT_NEIN

    @property
    def anzeigename(self) -> str:
        """Name in normaler Schreibweise (das Spiel liefert GROSSBUCHSTABEN)."""
        if not self.name:
            return f"Auto {self.startnummer or self.idx}"
        return self.name.title() if self.name.isupper() else self.name

    @property
    def team(self) -> str:
        return k.team(self.team_id)["name"]

    @property
    def farbe(self) -> str:
        if self.team_id in k.TEAMS:
            return k.TEAMS[self.team_id]["farbe"]
        return self.lackfarbe or k.TEAM_UNBEKANNT["farbe"]

    @property
    def reifen_name(self) -> str:
        return k.reifen(self.reifen_visuell)["name"]

    @property
    def max_verschleiss(self) -> float:
        return max(self.reifenverschleiss)

    @property
    def gefahrene_runden(self) -> int:
        return max(self.runde - 1, 0)


class Rennzustand:
    """Haelt alle Daten der laufenden Session. Zugriff immer mit `with z.lock:`."""

    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.zuruecksetzen(0)

    def zuruecksetzen(self, session_uid: int) -> None:
        self.session_uid = session_uid
        self.packet_format = 0
        self.spieler_idx = 255
        self.session_time = 0.0
        self.autos: list[Auto] = [Auto(i) for i in range(24)]
        self.anzahl_aktiv = 0
        # --- Session-Paket ---
        self.session_bekannt = False
        self.wetter = 0
        self.streckentemperatur = 0
        self.lufttemperatur = 0
        self.runden_gesamt = 0
        self.streckenlaenge = 0
        self.session_typ = 0
        self.strecke_id = -1
        self.formel = 0
        self.zeit_uebrig = 0
        self.safety_car = 0
        self.netzwerkspiel = False
        self.prognose: list[dict] = []
        self.prognose_genau = True
        self.saison_id = 0
        self.wochenende_id = 0
        self.session_link_id = 0
        self.boxenfenster_ideal = 0
        self.boxenfenster_spaetestens = 0
        self.boxen_rueckkehr_position = 0
        self.spielmodus = 0
        self.pausiert = False
        # --- Ablauf ---
        self.rote_flagge = False  # zwischen RDFL und Restart
        self.rote_flaggen_anzahl = 0
        self.rennen_gestartet = False  # Ampel aus
        self.zielflagge = False
        self.beendet = False
        self.wetter_log: list[dict] = []
        self.ereignis_log: list[dict] = []
        self.klassifizierung: list[dict] | None = None
        self.reifensaetze: list[dict] = []

    # ------------------------------------------------------------------
    @property
    def ist_rennen(self) -> bool:
        return k.ist_rennen(self.session_typ)

    @property
    def spieler(self) -> Auto | None:
        if 0 <= self.spieler_idx < len(self.autos):
            auto = self.autos[self.spieler_idx]
            return auto if auto.position > 0 else None
        return None

    @property
    def strecke(self) -> str:
        return k.strecke(self.strecke_id)

    def gueltige_autos(self) -> list[Auto]:
        return sorted((a for a in self.autos if a.gueltig), key=lambda a: a.position)

    def auto_auf_position(self, position: int) -> Auto | None:
        for a in self.autos:
            if a.gueltig and a.position == position:
                return a
        return None

    def vordermann(self, auto: Auto) -> Auto | None:
        return self.auto_auf_position(auto.position - 1) if auto.position > 1 else None

    def hintermann(self, auto: Auto) -> Auto | None:
        return self.auto_auf_position(auto.position + 1)

    def fuehrender(self) -> Auto | None:
        return self.auto_auf_position(1)

    def fuehrungsrunde(self) -> int:
        f = self.fuehrender()
        return f.runde if f else 0

    def rueckstand_ms(self, auto: Auto, auf: Auto) -> int:
        """Wie viele Millisekunden liegt `auto` hinter `auf`? Negativ = davor."""
        return auto.delta_fuehrender_ms - auf.delta_fuehrender_ms

    def menschliche_mitspieler(self) -> list[Auto]:
        return [
            a
            for a in self.autos
            if a.gueltig and not a.ki and a.idx != self.spieler_idx
        ]

    def teamkollege(self, auto: Auto) -> Auto | None:
        for a in self.autos:
            if a.gueltig and a.idx != auto.idx and a.team_id == auto.team_id:
                return a
        return None

    # --- Wetter -------------------------------------------------------
    def prognose_session(self) -> list[dict]:
        """Wetterprognose nur fuer die laufende Session, nach Zeit sortiert."""
        proben = [p for p in self.prognose if p["session_type"] == self.session_typ]
        return sorted(proben, key=lambda p: p["time_offset"])

    def minuten_bis_regen(self) -> tuple[int, dict] | None:
        """(Minuten, Probe) der ersten Prognose mit Regen - oder None."""
        for p in self.prognose_session():
            if k.ist_regen(p["weather"]):
                return p["time_offset"], p
        return None

    def minuten_bis_trocken(self) -> tuple[int, dict] | None:
        for p in self.prognose_session():
            if not k.ist_regen(p["weather"]):
                return p["time_offset"], p
        return None
