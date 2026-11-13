"""Simuliertes Rennen: erzeugt gueltige F1-25-UDP-Pakete ohne das Spiel.

    sim = Simulator(szenario="alles")
    for session_time, paket in sim.pakete():
        ...

Das Rennen ist stark vereinfacht (konstante Geschwindigkeiten, keine
Zweikaempfe), enthaelt aber alles, was der Renningenieur auswertet:
Abstaende, Boxenstopps, Reifenverschleiss, Wetterprognose und Regen, Safety
Car, rote Flagge mit Restart, Strafen und das Endergebnis.

Du faehrst das Auto "SPIELER" (startet von Platz 5), dein Mitspieler ist
"KUMPEL" (Platz 8).
"""

from __future__ import annotations

import random
import socket
import time
from dataclasses import dataclass, field
from typing import Iterator

from .telemetrie import encoder, spec

SOFT, MEDIUM, HARD, INTER, WET = 16, 17, 18, 7, 8
TATSAECHLICH = {SOFT: 18, MEDIUM: 19, HARD: 20, INTER: 7, WET: 8}  # C3/C2/C1
VERSCHLEISS_PRO_RUNDE = {SOFT: 7.5, MEDIUM: 5.5, HARD: 4.0, INTER: 5.0, WET: 4.0}
MISCHUNG_TEMPO = {SOFT: -0.6, MEDIUM: 0.0, HARD: 0.5, INTER: 6.0, WET: 9.0}

STRECKENLAENGE = 5000.0  # Meter
BASISZEIT = 80.0  # Sekunden pro Runde
BOX_DAUER = 22.0  # Sekunden in der Boxengasse
BOX_STRECKE = 500.0  # Meter, die dabei zurueckgelegt werden

FELD = [  # (Name, Team-ID, Startnummer, Tempo-Versatz in s/Runde)
    ("VERSTAPPEN", 2, 1, -0.50),
    ("NORRIS", 8, 4, -0.45),
    ("LECLERC", 1, 16, -0.35),
    ("PIASTRI", 8, 81, -0.30),
    ("SPIELER", 3, 23, -0.10),
    ("HAMILTON", 1, 44, -0.25),
    ("RUSSELL", 0, 63, -0.05),
    ("KUMPEL", 3, 55, 0.00),
    ("ALONSO", 4, 14, 0.15),
    ("GASLY", 5, 10, 0.20),
    ("ANTONELLI", 0, 12, 0.25),
    ("TSUNODA", 2, 22, 0.30),
    ("HÜLKENBERG", 9, 27, 0.35),
    ("OCON", 7, 31, 0.40),
    ("STROLL", 4, 18, 0.50),
    ("LAWSON", 6, 30, 0.55),
    ("BEARMAN", 7, 87, 0.60),
    ("HADJAR", 6, 6, 0.65),
    ("BORTOLETO", 9, 5, 0.70),
    ("COLAPINTO", 5, 43, 0.80),
]
SPIELER, KUMPEL = 4, 7  # Index im Feld = Fahrzeug-Index


@dataclass
class SimAuto:
    idx: int
    name: str
    team_id: int
    nummer: int
    tempo: float
    startplatz: int
    mischung: int = MEDIUM
    alter: int = 0
    verschleiss: float = 0.0
    distanz: float = 0.0  # Gesamtdistanz in Metern
    runde: int = 1
    runden_start: float = 0.0
    letzte_runde_ms: int = 0
    rundenzeiten: list[int] = field(default_factory=list)
    stints: list[list[int]] = field(default_factory=list)  # [ende, tatsaechlich, visuell]
    boxenplan: dict[int, int] = field(default_factory=dict)  # Runde -> neue Mischung
    pit_status: int = 0
    pit_bis: float = 0.0
    pit_wechsel: float = 0.0
    pit_neu: int = 0
    pit_start: float = 0.0
    stopps: int = 0
    fertig: bool = False
    zielzeit: float = 0.0
    position: int = 0
    strafe: int = 0
    rauschen: float = 0.0
    start_ab: float = 0.0


class Simulator:
    def __init__(self, szenario: str = "alles", fmt: int = 2025, runden: int = 12,
                 seed: int = 1, dt: float = 0.25, session_uid: int | None = None,
                 strecke_id: int = 11, saison_id: int = 2025001, wochenende_id: int = 1):
        if szenario not in SZENARIEN:
            raise ValueError(f"Unbekanntes Szenario {szenario!r}. Es gibt: {', '.join(SZENARIEN)}")
        self.fmt = fmt
        self.dt = dt
        self.runden = runden
        self.zufall = random.Random(seed)
        self.session_uid = session_uid or (0x51E5510000000000 + seed * 1000 + wochenende_id)
        self.strecke_id = strecke_id
        self.saison_id = saison_id
        self.wochenende_id = wochenende_id
        self.t = 0.0
        self.frame = 0
        self.sc_status = 0
        self.rote_flaggen = 0
        self.sc_phasen = 0
        self.gestartet = False
        self.rot_bis = 0.0  # > 0: rote Flagge bis zu diesem Zeitpunkt
        plan = SZENARIEN[szenario]
        self.wetterplan: list[tuple[float, int]] = plan["wetter"]
        self.ereignisplan: list[tuple[float, str]] = sorted(plan.get("ereignisse", []))
        self.autos = [
            SimAuto(i, name, team, nr, tempo, startplatz=i + 1)
            for i, (name, team, nr, tempo) in enumerate(FELD)
        ]
        for a in self.autos:
            a.mischung = MEDIUM if a.idx % 3 else SOFT
            a.distanz = -8.0 * a.idx
            a.position = a.idx + 1
            a.boxenplan = dict(plan.get("boxen", {}).get(a.idx, {}))
            a.stints = [[255, TATSAECHLICH[a.mischung], a.mischung]]
        self.autos[SPIELER].mischung = MEDIUM
        self.autos[SPIELER].stints = [[255, TATSAECHLICH[MEDIUM], MEDIUM]]
        # Hintermann des Spielers ist anfangs schneller und rueckt auf
        self.autos[SPIELER + 1].tempo = -0.45

    # ------------------------------------------------------------------
    def _hdr(self) -> dict:
        return {
            "session_uid": self.session_uid,
            "session_time": self.t,
            "frame_identifier": self.frame,
            "overall_frame_identifier": self.frame,
            "player_car_index": SPIELER,
        }

    def wetter(self, t: float | None = None) -> int:
        t = self.t if t is None else t
        aktuell = self.wetterplan[0][1]
        for ab, w in self.wetterplan:
            if t >= ab:
                aktuell = w
        return aktuell

    def _nass(self) -> bool:
        return self.wetter() >= 3

    # ------------------------------------------------------------------
    def pakete(self) -> Iterator[tuple[float, bytes]]:
        """Erzeugt das ganze Rennen als Folge (Session-Zeit, Paket)."""
        f = self.fmt
        yield self.t, encoder.event(f, self._hdr(), "SSTA")
        yield self.t, self._participants()
        yield self.t, self._session()
        yield self.t, self._car_status()
        yield self.t, self._car_damage()
        yield self.t, self._lap_data()
        # Startampel
        for licht in range(1, 6):
            yield from self._schritt(1.0)
            yield self.t, encoder.event(f, self._hdr(), "STLG", {"num_lights": licht})
        yield from self._schritt(1.0)
        yield self.t, encoder.event(f, self._hdr(), "LGOT")
        self.gestartet = True
        for a in self.autos:
            a.runden_start = self.t
            a.start_ab = self.t + 0.9 * a.idx  # Feld zieht sich am Start auseinander

        schritt_nr = 0
        ende_ab = None
        while True:
            schritt_nr += 1
            # Geplante Ereignisse
            while self.ereignisplan and self.ereignisplan[0][0] <= self.t:
                _, name = self.ereignisplan.pop(0)
                yield from self._ereignis(name)
            if self.rot_bis:
                yield from self._rote_flagge_ablauf()
                continue
            self._bewegen(self.dt)
            self.t += self.dt
            self.frame += 1
            yield self.t, self._lap_data()
            if schritt_nr % 4 == 0:
                yield self.t, self._car_status()
                yield self.t, self._car_damage()
                yield self.t, self._session()
            if schritt_nr % 40 == 0:
                yield self.t, self._participants()
            yield self.t, self._session_history(self.autos[schritt_nr % len(self.autos)])
            # Ein Motion-Paket pro Schritt (wird nur weitergeleitet)
            yield self.t, encoder.leer(f, spec.MOTION, self._hdr())
            if ende_ab is None and any(a.fertig for a in self.autos):
                ende_ab = self.t
                yield self.t, encoder.event(f, self._hdr(), "CHQF")
            if all(a.fertig for a in self.autos) or (ende_ab and self.t - ende_ab > 120):
                break
        for a in self.autos:
            yield self.t, self._session_history(a)
        yield self.t, self._lap_data()
        yield self.t, self._final_classification()
        yield self.t, encoder.event(f, self._hdr(), "SEND")

    def _schritt(self, dauer: float) -> Iterator[tuple[float, bytes]]:
        """Zeit vergeht, ohne dass sich Autos bewegen."""
        schritte = max(int(dauer / self.dt), 1)
        for n in range(schritte):
            self.t += dauer / schritte
            self.frame += 1
            yield self.t, self._lap_data()
            if n % 4 == 0:
                yield self.t, self._session()
                yield self.t, self._car_status()

    # ------------------------------------------------------------------
    def _rundenzeit(self, a: SimAuto) -> float:
        zeit = BASISZEIT + a.tempo + MISCHUNG_TEMPO[a.mischung] + a.verschleiss * 0.03 + a.rauschen
        nass = self._nass()
        if nass and a.mischung not in (INTER, WET):
            zeit += 14.0
        elif nass:
            zeit += 2.0  # Regenreifen im Regen: 6 + 2 = 8 s langsamer als trocken
        if self.sc_status == 1:
            zeit *= 1.5
        elif self.sc_status == 2:
            zeit *= 1.3
        return zeit

    def _bewegen(self, dt: float) -> None:
        for a in self.autos:
            if a.fertig or self.t < a.start_ab:
                continue
            if a.pit_status:
                a.distanz += BOX_STRECKE / BOX_DAUER * dt
                if a.pit_neu and self.t >= a.pit_wechsel:
                    self._reifen_wechseln(a, a.pit_neu, a.runde - (1 if a.distanz % STRECKENLAENGE < 1000 else 0))
                    a.pit_neu = 0
                    a.stopps += 1
                a.pit_status = 2 if abs(self.t - a.pit_wechsel) < 1.5 else 1
                if self.t >= a.pit_bis:
                    a.pit_status = 0
            else:
                a.distanz += STRECKENLAENGE / self._rundenzeit(a) * dt
                # Boxeneinfahrt kurz vor Start/Ziel
                if a.runde in a.boxenplan and a.distanz % STRECKENLAENGE > STRECKENLAENGE - 250:
                    a.pit_neu = a.boxenplan.pop(a.runde)
                    a.pit_status = 1
                    a.pit_start = self.t
                    a.pit_wechsel = self.t + 9.0
                    a.pit_bis = self.t + BOX_DAUER
            # Start/Ziel ueberquert?
            if a.distanz >= a.runde * STRECKENLAENGE:
                a.letzte_runde_ms = int((self.t + dt - a.runden_start) * 1000)
                a.rundenzeiten.append(a.letzte_runde_ms)
                a.runden_start = self.t + dt
                a.alter += 1
                a.verschleiss += VERSCHLEISS_PRO_RUNDE[a.mischung] * (1 + 0.1 * self.zufall.random())
                a.rauschen = self.zufall.uniform(-0.15, 0.15)
                if a.runde >= self.runden:
                    a.fertig = True
                    a.zielzeit = self.t + dt
                else:
                    a.runde += 1
        self._positionen()

    def _positionen(self) -> None:
        def schluessel(a: SimAuto):
            # Im Ziel zaehlt die Zielzeit, sonst die Distanz
            return (0, a.zielzeit) if a.fertig else (1, -a.distanz)

        for pos, a in enumerate(sorted(self.autos, key=schluessel), start=1):
            a.position = pos

    def _reifen_wechseln(self, a: SimAuto, mischung: int, ende_runde: int) -> None:
        a.stints[-1][0] = max(ende_runde, 1)
        a.mischung, a.alter, a.verschleiss = mischung, 0, 0.0
        a.stints.append([255, TATSAECHLICH[mischung], mischung])

    # ------------------------------------------------------------------
    def _ereignis(self, name: str) -> Iterator[tuple[float, bytes]]:
        f = self.fmt
        if name == "sc":
            self.sc_status, self.sc_phasen = 1, self.sc_phasen + 1
            yield self.t, encoder.event(f, self._hdr(), "SCAR", {"safety_car_type": 1, "event_type": 0})
        elif name == "sc_rein":
            yield self.t, encoder.event(f, self._hdr(), "SCAR", {"safety_car_type": 1, "event_type": 1})
        elif name == "sc_ende":
            self.sc_status = 0
            yield self.t, encoder.event(f, self._hdr(), "SCAR", {"safety_car_type": 1, "event_type": 3})
        elif name == "vsc":
            self.sc_status = 2
            yield self.t, encoder.event(f, self._hdr(), "SCAR", {"safety_car_type": 2, "event_type": 0})
        elif name == "vsc_ende":
            self.sc_status = 0
            yield self.t, encoder.event(f, self._hdr(), "SCAR", {"safety_car_type": 2, "event_type": 3})
        elif name == "rote_flagge":
            self.rote_flaggen += 1
            self.sc_status = 0
            self.rot_bis = self.t + 40.0
            yield self.t, encoder.event(f, self._hdr(), "RDFL")
        elif name == "strafe_vordermann":
            ich = self.autos[SPIELER]
            vorne = next((a for a in self.autos if a.position == ich.position - 1), None)
            if vorne:
                vorne.strafe += 5
                yield self.t, encoder.event(f, self._hdr(), "PENA", {
                    "penalty_type": 4, "infringement_type": 7, "vehicle_idx": vorne.idx,
                    "other_vehicle_idx": 255, "time": 5, "lap_num": vorne.runde,
                })
        yield self.t, self._session()

    def _rote_flagge_ablauf(self) -> Iterator[tuple[float, bytes]]:
        """Alle stehen in der Boxengasse, einige wechseln Reifen, dann Restart."""
        f = self.fmt
        start = self.t
        for a in self.autos:
            if not a.fertig:
                a.pit_status = 1
                a.pit_start = self.t
        gewechselt = False
        ampel = 0
        while self.t < self.rot_bis:
            self.t += self.dt
            self.frame += 1
            if not gewechselt and self.t - start > 10:
                gewechselt = True
                # Spieler und jeder zweite Fahrer holen sich frische Reifen
                for a in self.autos:
                    if a.fertig:
                        continue
                    if a.idx == SPIELER:
                        self._reifen_wechseln(a, SOFT, a.runde - 1)
                    elif a.idx % 2 == 0:
                        self._reifen_wechseln(a, MEDIUM if a.mischung != MEDIUM else HARD, a.runde - 1)
            rest = self.rot_bis - self.t
            if rest < 5.5 and ampel < 5 and rest < 5.5 - ampel:
                ampel += 1
                yield self.t, encoder.event(f, self._hdr(), "STLG", {"num_lights": ampel})
            yield self.t, self._lap_data()
            yield self.t, self._car_status()
            yield self.t, self._car_damage()
            yield self.t, self._session()
            yield self.t, self._session_history(self.autos[self.frame % len(self.autos)])
        # Restart: Aufstellung nach Position, 8 Meter Abstand
        self.rot_bis = 0.0
        reihenfolge = sorted((a for a in self.autos if not a.fertig), key=lambda a: a.position)
        if reihenfolge:
            spitze = reihenfolge[0].distanz
            for n, a in enumerate(reihenfolge):
                a.distanz = max(spitze - 8.0 * n, (a.runde - 1) * STRECKENLAENGE + 1.0)
                a.pit_status = 0
        yield self.t, encoder.event(f, self._hdr(), "LGOT")

    # ------------------------------------------------------------------
    def _session(self) -> bytes:
        proben = []
        for minuten in (0, 5, 10, 15, 30, 45, 60):
            w = self.wetter(self.t + minuten * 60)
            proben.append({
                "session_type": 15, "time_offset": minuten, "weather": w,
                "track_temperature": 31 if w < 3 else 24, "air_temperature": 24 if w < 3 else 19,
                "rain_percentage": {0: 2, 1: 5, 2: 20, 3: 70, 4: 95, 5: 100}[w],
            })
        nass = self._nass()
        ich = self.autos[SPIELER]
        return encoder.session(self.fmt, self._hdr(), {
            "weather": self.wetter(),
            "track_temperature": 24 if nass else 31,
            "air_temperature": 19 if nass else 24,
            "total_laps": self.runden,
            "track_length": int(STRECKENLAENGE),
            "session_type": 15,
            "track_id": self.strecke_id,
            "formula": 0,
            "session_time_left": 7200,
            "session_duration": 7200,
            "pit_speed_limit": 80,
            "safety_car_status": self.sc_status,
            "network_game": 1,
            "weather_forecast_samples": proben,
            "forecast_accuracy": 0,
            "ai_difficulty": 90,
            "season_link_identifier": self.saison_id,
            "weekend_link_identifier": self.wochenende_id,
            "session_link_identifier": self.wochenende_id * 10 + 5,
            "pit_stop_window_ideal_lap": 0 if ich.stopps else max(self.runden // 2 - 1, 1),
            "pit_stop_window_latest_lap": 0 if ich.stopps else max(self.runden // 2 + 1, 2),
            "pit_stop_rejoin_position": min(ich.position + 6, len(self.autos)),
            "game_mode": 28,
            "num_safety_car_periods": self.sc_phasen,
            "num_red_flag_periods": self.rote_flaggen,
            "marshal_zones": [{"zone_start": i / 10, "zone_flag": 0} for i in range(10)],
        })

    def _lap_data(self) -> bytes:
        nach_pos = sorted(self.autos, key=lambda a: a.position)
        spitze = nach_pos[0]
        cars = []
        for a in self.autos:
            if a.position > 1:
                davor = nach_pos[a.position - 2]
                tempo = STRECKENLAENGE / BASISZEIT
                if a.fertig and davor.fertig:
                    d_vorne = (a.zielzeit - davor.zielzeit) * 1000
                    d_spitze = (a.zielzeit - spitze.zielzeit) * 1000
                else:
                    d_vorne = max(davor.distanz - a.distanz, 0) / tempo * 1000
                    d_spitze = max(spitze.distanz - a.distanz, 0) / tempo * 1000
                if not self.gestartet:
                    d_vorne = d_spitze = 0
            else:
                d_vorne = d_spitze = 0
            cars.append({
                "last_lap_time_ms": a.letzte_runde_ms,
                "current_lap_time_ms": int(max(self.t - a.runden_start, 0) * 1000),
                "delta_to_car_in_front_ms": d_vorne,
                "delta_to_race_leader_ms": d_spitze,
                "lap_distance": a.distanz % STRECKENLAENGE if a.distanz >= 0 else a.distanz,
                "total_distance": a.distanz,
                "car_position": a.position,
                "current_lap_num": a.runde,
                "pit_status": a.pit_status,
                "num_pit_stops": a.stopps,
                "sector": 0,
                "penalties": a.strafe,
                "grid_position": a.startplatz,
                "driver_status": 0 if a.pit_status == 2 else 4,
                "result_status": 3 if a.fertig else 2,
                "pit_lane_timer_active": 1 if a.pit_status else 0,
                "pit_lane_time_in_lane_ms": min(int((self.t - a.pit_start) * 1000), 65535) if a.pit_status else 0,
                "pit_stop_timer_ms": 2400 if a.pit_status and self.t > a.pit_wechsel else 0,
            })
        return encoder.lap_data(self.fmt, self._hdr(), cars)

    def _participants(self) -> bytes:
        cars = [{
            "ai_controlled": 0 if a.idx in (SPIELER, KUMPEL) else 1,
            "driver_id": 255 if a.idx in (SPIELER, KUMPEL) else a.idx,
            "network_id": a.idx,
            "team_id": a.team_id,
            "race_number": a.nummer,
            "nationality": 29,
            "name": a.name,
            "your_telemetry": 1,
            "show_online_names": 1,
            "platform": 1,
            "livery_colours": [(200, 30, 30)],
        } for a in self.autos]
        return encoder.participants(self.fmt, self._hdr(), cars)

    def _car_status(self) -> bytes:
        cars = [{
            "fuel_mix": 1,
            "front_brake_bias": 56,
            "fuel_in_tank": max(40 - a.distanz / STRECKENLAENGE * 2.2, 1.0),
            "fuel_capacity": 110.0,
            "fuel_remaining_laps": 0.8 - a.idx * 0.02,
            "max_rpm": 13000,
            "idle_rpm": 3500,
            "max_gears": 9,
            "actual_tyre_compound": TATSAECHLICH[a.mischung],
            "visual_tyre_compound": a.mischung,
            "tyres_age_laps": a.alter,
            "ers_store_energy": 2_000_000.0,
        } for a in self.autos]
        return encoder.car_status(self.fmt, self._hdr(), cars)

    def _car_damage(self) -> bytes:
        cars = []
        for a in self.autos:
            # Anteil der laufenden Runde mitrechnen, vorne links am staerksten
            teil = (a.distanz % STRECKENLAENGE) / STRECKENLAENGE if a.distanz > 0 else 0
            v = a.verschleiss + teil * VERSCHLEISS_PRO_RUNDE[a.mischung]
            cars.append({
                "tyres_wear": [v * 0.85, v * 0.82, v, v * 0.93],
                "front_left_wing_damage": 12 if a.idx == SPIELER and self.rote_flaggen else 0,
            })
        return encoder.car_damage(self.fmt, self._hdr(), cars)

    def _session_history(self, a: SimAuto) -> bytes:
        laps = [{
            "lap_time_ms": ms, "sector1_ms": ms // 3, "sector2_ms": ms // 3,
            "sector3_ms": ms - 2 * (ms // 3), "valid": True,
        } for ms in a.rundenzeiten]
        beste = a.rundenzeiten.index(min(a.rundenzeiten)) + 1 if a.rundenzeiten else 0
        return encoder.session_history(self.fmt, self._hdr(), {
            "car_idx": a.idx,
            "best_lap_time_lap_num": beste,
            "laps": laps,
            "tyre_stints": [{"end_lap": e, "tyre_actual_compound": t, "tyre_visual_compound": v}
                            for e, t, v in a.stints],
        })

    def _final_classification(self) -> bytes:
        punkte = [25, 18, 15, 12, 10, 8, 6, 4, 2, 1]
        cars = []
        for a in self.autos:
            stints = a.stints[:8]
            cars.append({
                "position": a.position,
                "num_laps": len(a.rundenzeiten),
                "grid_position": a.startplatz,
                "points": punkte[a.position - 1] if a.position <= 10 else 0,
                "num_pit_stops": a.stopps,
                "result_status": 3,
                "best_lap_time_ms": min(a.rundenzeiten) if a.rundenzeiten else 0,
                "total_race_time": sum(a.rundenzeiten) / 1000.0,
                "penalties_time": a.strafe,
                "num_penalties": 1 if a.strafe else 0,
                "num_tyre_stints": len(stints),
                "tyre_stints_actual": [s[1] for s in stints],
                "tyre_stints_visual": [s[2] for s in stints],
                "tyre_stints_end_laps": [s[0] if s[0] != 255 else len(a.rundenzeiten) for s in stints],
            })
        return encoder.final_classification(self.fmt, self._hdr(), cars)


# --------------------------------------------------------------------------
# Szenarien. Zeiten in Sekunden Session-Zeit, Runden als Rundennummer.
# boxen: Fahrzeug-Index -> {Runde der Einfahrt: neue Mischung}
# --------------------------------------------------------------------------
_BOXEN_TROCKEN = {
    SPIELER - 1: {3: HARD},  # Vordermann stoppt frueh
    SPIELER + 1: {4: HARD},  # Hintermann versucht den Undercut
    SPIELER: {6: HARD},
    KUMPEL: {7: MEDIUM},
    0: {6: HARD}, 1: {7: HARD}, 2: {5: HARD}, 6: {5: MEDIUM}, 8: {6: HARD},
    9: {4: HARD}, 10: {7: SOFT}, 11: {5: HARD}, 12: {6: MEDIUM},
}
_BOXEN_REGEN = {i: {9 + i % 2: INTER} for i in range(len(FELD))}

SZENARIEN = {
    # Trockenes Rennen mit Boxenstopps rund um den Spieler
    "trocken": {"wetter": [(0, 1)], "boxen": {**_BOXEN_TROCKEN, SPIELER: {9: SOFT}}},
    # Regen kuendigt sich an und kommt nach ca. 11 Minuten
    "regen": {
        "wetter": [(0, 2), (640, 3), (800, 4)],
        "boxen": {i: {**_BOXEN_TROCKEN.get(i, {}), **_BOXEN_REGEN[i]} for i in range(len(FELD))},
    },
    # Rote Flagge mit Restart
    "rote_flagge": {
        "wetter": [(0, 0)],
        "boxen": _BOXEN_TROCKEN,
        "ereignisse": [(200, "rote_flagge")],
    },
    # Alles zusammen
    "alles": {
        "wetter": [(0, 1), (300, 2), (700, 3), (860, 4)],
        "boxen": {i: {**_BOXEN_TROCKEN.get(i, {}), **{k + 1: v for k, v in _BOXEN_REGEN[i].items()}}
                  for i in range(len(FELD))},
        "ereignisse": [
            (150, "strafe_vordermann"),
            (420, "sc"), (470, "sc_rein"), (500, "sc_ende"),
            (560, "rote_flagge"),
        ],
    },
}


def senden(sim: Simulator, host: str = "127.0.0.1", port: int = 20777, tempo: float = 1.0,
           ausgabe=print) -> int:
    """Schickt das simulierte Rennen per UDP an host:port."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    start = time.monotonic()
    anzahl = 0
    letzte_meldung = 0.0
    try:
        for t, paket in sim.pakete():
            warten = t / tempo - (time.monotonic() - start)
            if warten > 0:
                time.sleep(warten)
            sock.sendto(paket, (host, port))
            anzahl += 1
            if t - letzte_meldung >= 60:
                letzte_meldung = t
                ich = sim.autos[SPIELER]
                ausgabe(f"  Simulation: Minute {int(t // 60)}, Runde {ich.runde}/{sim.runden}, "
                        f"Platz {ich.position}")
    finally:
        sock.close()
    return anzahl
