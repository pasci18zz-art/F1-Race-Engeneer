"""Auswertung: uebertraegt Pakete in den Rennzustand und meldet Ereignisse.

    auswertung = Auswertung(zustand)
    ereignisse = auswertung.verarbeite(udp_daten)

Ein Ereignis ist etwas, das gerade passiert ist (Auto faehrt in die Box,
rote Flagge, Runde beendet, ...). Regeln, Datenbank und Webseite reagieren
auf diese Ereignisse und muessen die Pakete selbst nicht kennen.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .telemetrie import konstanten as k
from .telemetrie import parser, spec
from .zustand import Auto, Boxenstopp, Rennzustand, Stint

log = logging.getLogger(__name__)


@dataclass
class Ereignis:
    typ: str
    zeit: float  # Session-Zeit in Sekunden
    daten: dict = field(default_factory=dict)


class Auswertung:
    def __init__(self, zustand: Rennzustand):
        self.z = zustand
        self._gesehen: set[int] = set()  # Autos, fuer die schon Lap Data kam
        self._gemeldete_fehler: set[str] = set()
        self._ereignisse: list[Ereignis] = []
        self.pakete = 0

    # ------------------------------------------------------------------
    def verarbeite(self, data: bytes) -> list[Ereignis]:
        self._ereignisse = []
        try:
            paket = parser.parse(data)
        except parser.PaketFehler as e:
            text = str(e)
            if text not in self._gemeldete_fehler:
                self._gemeldete_fehler.add(text)
                log.warning("%s", text)
                self._melde("paket_fehler", text=text)
            return self._ereignisse
        if paket is None:
            return self._ereignisse
        self.pakete += 1
        header = paket["header"]
        uid = header["session_uid"]
        if uid == 0:
            return self._ereignisse  # Menue
        z = self.z
        with z.lock:
            if uid != z.session_uid:
                if z.session_uid and z.session_bekannt and not z.beendet:
                    z.beendet = True
                    self._melde("session_ende")
                z.zuruecksetzen(uid)
                self._gesehen.clear()
            z.packet_format = header["packet_format"]
            z.spieler_idx = header["player_car_index"]
            t = header["session_time"]
            if t < z.session_time - 5.0:
                # Zeit springt zurueck, ohne dass ein Flashback gemeldet wurde
                self._nach_flashback(t)
            z.session_time = t
            _HANDLER[header["packet_id"]](self, paket)
        return self._ereignisse

    # ------------------------------------------------------------------
    def _melde(self, typ: str, **daten) -> None:
        self._ereignisse.append(Ereignis(typ, self.z.session_time, daten))

    def _protokoll(self, code: str, text: str, idx: int | None = None) -> None:
        z = self.z
        z.ereignis_log.append(
            {
                "zeit": z.session_time,
                "runde": z.fuehrungsrunde(),
                "code": code,
                "idx": idx,
                "text": text,
            }
        )

    # --- Session ------------------------------------------------------
    def _session(self, p: dict) -> None:
        z = self.z
        neu = not z.session_bekannt
        altes_wetter, altes_sc = z.wetter, z.safety_car
        z.wetter = p["weather"]
        z.streckentemperatur = p["track_temperature"]
        z.lufttemperatur = p["air_temperature"]
        z.runden_gesamt = p["total_laps"]
        z.streckenlaenge = p["track_length"]
        z.session_typ = p["session_type"]
        z.strecke_id = p["track_id"]
        z.formel = p["formula"]
        z.zeit_uebrig = p["session_time_left"]
        z.safety_car = p["safety_car_status"]
        z.netzwerkspiel = bool(p["network_game"])
        z.prognose = p["weather_forecast_samples"]
        z.prognose_genau = p["forecast_accuracy"] == 0
        z.saison_id = p["season_link_identifier"]
        z.wochenende_id = p["weekend_link_identifier"]
        z.session_link_id = p["session_link_identifier"]
        z.boxenfenster_ideal = p["pit_stop_window_ideal_lap"]
        z.boxenfenster_spaetestens = p["pit_stop_window_latest_lap"]
        z.boxen_rueckkehr_position = p["pit_stop_rejoin_position"]
        z.spielmodus = p["game_mode"]
        z.pausiert = bool(p["game_paused"])
        z.session_bekannt = True
        if neu:
            self._wetter_eintrag()
            self._melde("session_start")
            return
        if z.wetter != altes_wetter:
            self._wetter_eintrag()
            self._protokoll("WETTER", f"Wetter: {k.WETTER.get(z.wetter, z.wetter)}")
            self._melde("wetter_wechsel", alt=altes_wetter, neu=z.wetter)
        if z.safety_car != altes_sc:
            namen = {0: "Strecke frei", 1: "Safety Car", 2: "Virtuelles Safety Car",
                     3: "Einführungsrunde"}
            self._protokoll("SC", namen.get(z.safety_car, "Safety Car"))
            self._melde("safety_car", alt=altes_sc, neu=z.safety_car)

    def _wetter_eintrag(self) -> None:
        z = self.z
        z.wetter_log.append(
            {
                "zeit": z.session_time,
                "runde": z.fuehrungsrunde(),
                "wetter": z.wetter,
                "streckentemperatur": z.streckentemperatur,
                "lufttemperatur": z.lufttemperatur,
            }
        )

    # --- Teilnehmer ---------------------------------------------------
    def _participants(self, p: dict) -> None:
        z = self.z
        z.anzahl_aktiv = p["num_active_cars"]
        for i, c in enumerate(p["cars"]):
            a = z.autos[i]
            a.name = c["name"]
            a.team_id = c["team_id"]
            a.startnummer = c["race_number"]
            a.ki = bool(c["ai_controlled"])
            a.telemetrie_oeffentlich = bool(c["your_telemetry"]) or a.ki
            if c["livery_colours"]:
                r, g, b = c["livery_colours"][0]
                a.lackfarbe = f"#{r:02x}{g:02x}{b:02x}"

    # --- Lap Data -----------------------------------------------------
    def _lap_data(self, p: dict) -> None:
        z = self.z
        for i, c in enumerate(p["cars"]):
            a = z.autos[i]
            alte_runde, alter_pit, altes_ergebnis = a.runde, a.pit_status, a.result_status
            a.position = c["car_position"]
            a.runde = c["current_lap_num"]
            a.pit_status = c["pit_status"]
            a.boxenstopps_anzahl = c["num_pit_stops"]
            a.startplatz = c["grid_position"]
            a.driver_status = c["driver_status"]
            a.result_status = c["result_status"]
            a.letzte_runde_ms = c["last_lap_time_ms"]
            a.delta_vorne_ms = c["delta_to_car_in_front_ms"]
            a.delta_fuehrender_ms = c["delta_to_race_leader_ms"]
            a.rundendistanz = c["lap_distance"]
            a.gesamtdistanz = c["total_distance"]
            a.strafen_s = c["penalties"]
            a.offene_durchfahrt = c["num_unserved_drive_through_pens"]
            a.offene_stop_go = c["num_unserved_stop_go_pens"]
            a.verwarnungen = c["total_warnings"]
            a.track_limits = c["corner_cutting_warnings"]
            if not a.gueltig:
                continue
            if z.safety_car in (k.SC_VOLL, k.SC_VIRTUELL) or z.rote_flagge:
                a.neutral_runden.add(a.runde)
            if i not in self._gesehen:
                self._gesehen.add(i)
                continue  # erster Datensatz: nur merken, nichts melden

            # Runde zurueckgesprungen (Flashback): Verlauf kuerzen
            if a.runde < alte_runde:
                self._runden_kuerzen(a)

            # Runde beendet
            if alte_runde >= 1 and a.runde == alte_runde + 1 and a.letzte_runde_ms > 0:
                self._runde_fertig(a, alte_runde, a.letzte_runde_ms)
            # Zieldurchfahrt: letzte Runde nachtragen, falls noetig
            if altes_ergebnis == k.RESULT_AKTIV and a.result_status == 3:
                letzte = a.runde if a.runde not in a.rundenzeiten else None
                if letzte and letzte <= max(z.runden_gesamt, 1) and a.letzte_runde_ms > 0:
                    self._runde_fertig(a, letzte, a.letzte_runde_ms)

            # Boxenstopps (nicht waehrend roter Flagge: da stehen alle in der Gasse)
            if z.rote_flagge or not z.ist_rennen:
                continue
            if a.in_box and a.boxenstopps and not a.boxenstopps[-1].fertig:
                stopp = a.boxenstopps[-1]
                stopp.zeit_gasse_ms = max(stopp.zeit_gasse_ms, c["pit_lane_time_in_lane_ms"])
                stopp.standzeit_ms = max(stopp.standzeit_ms, c["pit_stop_timer_ms"])
            if alter_pit == k.PIT_NEIN and a.in_box and a.result_status == k.RESULT_AKTIV:
                a.boxenstopps.append(Boxenstopp(a.runde, z.session_time))
                self._protokoll("BOX", f"{a.anzeigename} fährt in die Box", a.idx)
                self._melde("box_einfahrt", idx=a.idx, runde=a.runde)
            elif alter_pit != k.PIT_NEIN and not a.in_box:
                if a.boxenstopps and not a.boxenstopps[-1].fertig:
                    stopp = a.boxenstopps[-1]
                    stopp.fertig = True
                    stopp.zeit_gasse_ms = max(
                        stopp.zeit_gasse_ms, c["pit_lane_time_in_lane_ms"]
                    )
                    stopp.standzeit_ms = max(stopp.standzeit_ms, c["pit_stop_timer_ms"])
                    self._melde("box_ausfahrt", idx=a.idx, runde=a.runde)
        self._melde("tick")

    def _runde_fertig(self, a: Auto, runde: int, zeit_ms: int) -> None:
        z = self.z
        a.rundenzeiten[runde] = zeit_ms
        if not a.beste_runde_ms or zeit_ms < a.beste_runde_ms:
            a.beste_runde_ms = zeit_ms
        a.runden_info[runde] = {
            "position": a.position,
            "delta_fuehrender_ms": a.delta_fuehrender_ms,
            "reifen_visuell": a.reifen_visuell,
            "reifenalter": a.reifenalter,
            "verschleiss": round(a.max_verschleiss, 1) if a.schaden_bekannt else None,
            "box": any(s.runde == runde for s in a.boxenstopps),
        }
        if z.rote_flagge and a.im_rennen and z.session_time - self._rote_flagge_zeit > 20:
            # Sicherheitsnetz, falls nach roter Flagge kein Ampel-Event kam
            z.rote_flagge = False
            self._melde("restart")
        self._melde("runde", idx=a.idx, runde=runde, zeit_ms=zeit_ms)

    _rote_flagge_zeit = 0.0

    def _runden_kuerzen(self, a: Auto) -> None:
        for runde in [r for r in a.rundenzeiten if r >= a.runde]:
            del a.rundenzeiten[runde]
        for runde in [r for r in a.runden_info if r >= a.runde]:
            del a.runden_info[runde]

    # --- Car Status ---------------------------------------------------
    def _car_status(self, p: dict) -> None:
        z = self.z
        for i, c in enumerate(p["cars"]):
            a = z.autos[i]
            altes_alter = a.reifenalter
            vis, act, alter = (
                c["visual_tyre_compound"],
                c["actual_tyre_compound"],
                c["tyres_age_laps"],
            )
            a.reifen_visuell, a.reifen_tatsaechlich, a.reifenalter = vis, act, alter
            a.sprit_runden = c["fuel_remaining_laps"]
            a.sprit_kg = c["fuel_in_tank"]
            a.flagge = c["vehicle_fia_flags"]
            a.ers_energie = c["ers_store_energy"]
            a.ers_modus = c["ers_deploy_mode"]
            if vis == 0 or not a.gueltig:
                continue
            erster = not a.status_bekannt
            a.status_bekannt = True
            if a.stints_aus_historie:
                self._alter_start_nachfuehren(a)
                continue
            # Stints selbst mitschreiben, solange keine Session History kommt
            if not a.stints:
                a.stints.append(Stint(vis, act, max(a.runde, 1), alter_start=alter))
                continue
            s = a.stints[-1]
            neuer_satz = alter < altes_alter and (
                a.in_box or z.rote_flagge or (alter <= 1 and altes_alter >= 3)
            )
            if not erster and (vis != s.visuell or act != s.tatsaechlich or neuer_satz):
                if a.boxenstopps and a.in_box:
                    ende = a.boxenstopps[-1].runde
                else:
                    ende = max(a.runde - 1, s.start_runde)
                s.end_runde = max(ende, s.start_runde)
                a.stints.append(Stint(vis, act, s.end_runde + 1, alter_start=alter))
                self._melde("reifenwechsel", idx=a.idx, visuell=vis)
            else:
                self._alter_start_nachfuehren(a)

    @staticmethod
    def _alter_start_nachfuehren(a: Auto) -> None:
        """Reifenalter beim Aufziehen = aktuelles Alter minus Runden im Stint."""
        if a.stints and not a.in_box:
            s = a.stints[-1]
            if s.end_runde is None and s.visuell == a.reifen_visuell:
                s.alter_start = max(a.reifenalter - max(a.runde - s.start_runde, 0), 0)

    # --- Car Telemetry ------------------------------------------------
    def _car_telemetry(self, p: dict) -> None:
        for i, c in enumerate(p["cars"]):
            a = self.z.autos[i]
            a.reifen_temp_innen = c["tyres_inner_temperature"]
            a.reifen_temp_oberflaeche = c["tyres_surface_temperature"]
            a.bremsen_temp = c["brakes_temperature"]
            a.motor_temp = c["engine_temperature"]
            a.telemetrie_bekannt = True

    # --- Car Damage ---------------------------------------------------
    def _car_damage(self, p: dict) -> None:
        for i, c in enumerate(p["cars"]):
            a = self.z.autos[i]
            a.reifenverschleiss = c["tyres_wear"]
            a.fluegel_vl = c["front_left_wing_damage"]
            a.fluegel_vr = c["front_right_wing_damage"]
            a.heckfluegel = c["rear_wing_damage"]
            a.unterboden = c["floor_damage"]
            a.diffusor = c["diffuser_damage"]
            a.seitenkasten = c["sidepod_damage"]
            a.schaden_bekannt = True

    # --- Session History ----------------------------------------------
    def _session_history(self, p: dict) -> None:
        z = self.z
        idx = p["car_idx"]
        if idx >= len(z.autos):
            return
        a = z.autos[idx]
        for nr, lap in enumerate(p["laps"], start=1):
            if lap["lap_time_ms"] > 0:
                a.rundenzeiten[nr] = lap["lap_time_ms"]
                info = a.runden_info.setdefault(nr, {})
                info["gueltig"] = lap["valid"]
                info["s1_ms"], info["s2_ms"], info["s3_ms"] = (
                    lap["sector1_ms"], lap["sector2_ms"], lap["sector3_ms"],
                )
        if a.rundenzeiten:
            a.beste_runde_ms = min(a.rundenzeiten.values())
        stints_roh = p["tyre_stints"]
        if not stints_roh:
            return
        letzter_laeuft = (stints_roh[-1]["end_lap"] in (0, 255)
                          or a.result_status == k.RESULT_AKTIV)
        neu = _stints_bauen(
            [(s["end_lap"], s["tyre_actual_compound"], s["tyre_visual_compound"])
             for s in stints_roh],
            a.stints, letzter_laeuft, max(a.gefahrene_runden, 1))
        if len(neu) > len(a.stints) and a.stints:
            self._melde("reifenwechsel", idx=a.idx, visuell=neu[-1].visuell)
        a.stints = neu
        a.stints_aus_historie = True

    # --- Final Classification -----------------------------------------
    def _final_classification(self, p: dict) -> None:
        z = self.z
        ergebnis = []
        for i, c in enumerate(p["cars"]):
            if c["position"] == 0:
                continue
            a = z.autos[i]
            n = min(c["num_tyre_stints"], 8)
            if n:
                a.stints = _stints_bauen(
                    [(c["tyre_stints_end_laps"][s], c["tyre_stints_actual"][s],
                      c["tyre_stints_visual"][s]) for s in range(n)],
                    a.stints, False, max(c["num_laps"], 1))
            if c["best_lap_time_ms"]:
                a.beste_runde_ms = c["best_lap_time_ms"]
            ergebnis.append({"idx": i, **c})
        z.klassifizierung = sorted(ergebnis, key=lambda e: e["position"])
        z.beendet = True
        self._melde("klassifizierung")

    # --- Reifensaetze (nur eigenes Auto, derzeit nur gespeichert) ------
    def _tyre_sets(self, p: dict) -> None:
        if p["car_idx"] == self.z.spieler_idx:
            self.z.reifensaetze = p["tyre_sets"]

    # --- Events -------------------------------------------------------
    def _event(self, p: dict) -> None:
        z = self.z
        code, d = p["code"], p["details"]

        def name(idx: int) -> str:
            return z.autos[idx].anzeigename if idx < len(z.autos) else "?"

        if code == "SEND":
            if not z.beendet:
                z.beendet = True
                self._melde("session_ende")
        elif code == "RDFL":
            z.rote_flagge = True
            z.rote_flaggen_anzahl += 1
            self._rote_flagge_zeit = z.session_time
            # Falls die Autos schon vor diesem Event in die Boxengasse gesetzt
            # wurden: diese "Boxeneinfahrten" der letzten Sekunden verwerfen.
            grenze = z.session_time - 3.0
            for a in z.autos:
                a.boxenstopps = [s for s in a.boxenstopps
                                 if s.fertig or s.session_time < grenze]
            z.ereignis_log = [e for e in z.ereignis_log
                              if not (e["code"] == "BOX" and e["zeit"] >= grenze)]
            self._protokoll("RDFL", "Rote Flagge")
            self._melde("rote_flagge")
        elif code == "STLG":
            self._melde("ampel", lichter=d["num_lights"])
        elif code == "LGOT":
            if z.rote_flagge:
                z.rote_flagge = False
                self._protokoll("RESTART", "Restart nach roter Flagge")
                self._melde("restart")
            else:
                self._melde("start")
            z.rennen_gestartet = True
        elif code == "CHQF":
            z.zielflagge = True
            self._melde("zielflagge")
        elif code == "FLBK":
            self._nach_flashback(d["flashback_session_time"])
        elif code == "FTLP":
            self._melde("schnellste_runde", idx=d["vehicle_idx"],
                        zeit_ms=int(d["lap_time"] * 1000))
        elif code == "RTMT":
            self._protokoll("AUSFALL", f"{name(d['vehicle_idx'])} ist ausgefallen",
                            d["vehicle_idx"])
            self._melde("ausfall", idx=d["vehicle_idx"])
        elif code == "PENA":
            self._protokoll("STRAFE", f"Strafe für {name(d['vehicle_idx'])}",
                            d["vehicle_idx"])
            self._melde("strafe", idx=d["vehicle_idx"], sekunden=d["time"],
                        strafe_typ=d["penalty_type"], vergehen=d["infringement_type"])
        elif code == "SCAR":
            self._melde("safety_car_event", sc_typ=d["safety_car_type"],
                        event_typ=d["event_type"])
        elif code == "RCWN":
            self._protokoll("SIEGER", f"{name(d['vehicle_idx'])} gewinnt", d["vehicle_idx"])
            self._melde("sieger", idx=d["vehicle_idx"])
        elif code == "COLL":
            self._melde("kollision", idx1=d["vehicle1_idx"], idx2=d["vehicle2_idx"])

    def _nach_flashback(self, t: float) -> None:
        """Rueckblende: alles verwerfen, was nach dem Zielzeitpunkt lag."""
        z = self.z
        for a in z.autos:
            a.boxenstopps = [s for s in a.boxenstopps if s.session_time <= t]
        z.wetter_log = [w for w in z.wetter_log if w["zeit"] <= t] or z.wetter_log[:1]
        z.ereignis_log = [e for e in z.ereignis_log if e["zeit"] <= t]
        z.session_time = t
        self._melde("flashback", ziel=t)


def _stints_bauen(roh: list[tuple[int, int, int]], alt: list[Stint], letzter_laeuft: bool,
                  letzte_runde: int) -> list[Stint]:
    """Baut die Stint-Liste aus (Endrunde, tatsaechlich, visuell) des Spiels.

    Ein Stint ohne volle Runde (z. B. Reifenwechsel unter roter Flagge) bekommt
    Start = Ende; der naechste Stint beginnt dann in derselben Runde.
    """
    neu: list[Stint] = []
    start = 1
    for n, (ende, tatsaechlich, visuell) in enumerate(roh):
        letzter = n == len(roh) - 1
        stint = Stint(visuell, tatsaechlich, start)
        if n < len(alt) and alt[n].visuell == visuell:
            stint.alter_start = alt[n].alter_start
        if letzter and letzter_laeuft:
            stint.end_runde = None
        elif letzter and ende in (0, 255):
            stint.end_runde = max(letzte_runde, start)
        elif ende < start:
            stint.end_runde = start
        else:
            stint.end_runde = ende
            start = ende + 1
        neu.append(stint)
    return neu


_HANDLER = {
    spec.SESSION: Auswertung._session,
    spec.LAP_DATA: Auswertung._lap_data,
    spec.EVENT: Auswertung._event,
    spec.PARTICIPANTS: Auswertung._participants,
    spec.CAR_TELEMETRY: Auswertung._car_telemetry,
    spec.CAR_STATUS: Auswertung._car_status,
    spec.FINAL_CLASSIFICATION: Auswertung._final_classification,
    spec.CAR_DAMAGE: Auswertung._car_damage,
    spec.SESSION_HISTORY: Auswertung._session_history,
    spec.TYRE_SETS: Auswertung._tyre_sets,
}
