"""Macht aus dem Rennzustand ein einfaches Dictionary (JSON-tauglich).

Dasselbe Format benutzen die Live-Ansicht der Webseite und die Datenbank.
"""

from __future__ import annotations

from .telemetrie import konstanten as k
from .zustand import Auto, Rennzustand


def auto_dict(z: Rennzustand, a: Auto) -> dict:
    r = k.reifen(a.reifen_visuell)
    fuehrender = z.fuehrender()
    runden_zurueck = 0
    if fuehrender and z.streckenlaenge > 0:
        runden_zurueck = max(int((fuehrender.gesamtdistanz - a.gesamtdistanz) // z.streckenlaenge), 0)
    return {
        "idx": a.idx,
        "position": a.position,
        "name": a.anzeigename,
        "team_id": a.team_id,
        "team": a.team,
        "farbe": a.farbe,
        "startnummer": a.startnummer,
        "ki": a.ki,
        "ist_spieler": a.idx == z.spieler_idx,
        "startplatz": a.startplatz,
        "runde": a.runde,
        "rueckstand_ms": a.delta_fuehrender_ms,
        "intervall_ms": a.delta_vorne_ms,
        "runden_zurueck": runden_zurueck,
        "in_box": a.in_box,
        "result_status": a.result_status,
        "status": k.RESULT_STATUS.get(a.result_status, ""),
        "reifen": {"visuell": a.reifen_visuell, "name": r["name"], "kurz": r["kurz"],
                   "farbe": r["farbe"]},
        "reifenalter": a.reifenalter,
        "verschleiss": (round(a.max_verschleiss, 1)
                        if a.schaden_bekannt and a.telemetrie_oeffentlich else None),
        "boxenstopps_anzahl": a.boxenstopps_anzahl,
        "letzte_runde_ms": a.letzte_runde_ms,
        "beste_runde_ms": a.beste_runde_ms,
        "strafen_s": a.strafen_s,
        "aktuelle_runde_ms": a.aktuelle_runde_ms,
        "beste_runde_nr": a.beste_runde_nr,
        "fahrerstatus": a.driver_status,
        "fahrerstatus_text": k.FAHRERSTATUS.get(a.driver_status, ""),
        "ausgefallen_runde": a.ausgefallen_runde,
        "ausfall_code": a.ausfall_grund if a.ausgefallen_runde else None,
        "ausfall_grund": k.AUSFALL_GRUND.get(a.ausfall_grund, "unbekannt") if a.ausgefallen_runde else "",
        "ausfall_zeit": round(a.ausfall_zeit, 1) if a.ausgefallen_runde else None,
        "stints": [s.als_dict() for s in a.stints],
        "boxenstopps": [
            {"runde": s.runde, "zeit": round(s.session_time, 1),
             "zeit_gasse_ms": s.zeit_gasse_ms, "standzeit_ms": s.standzeit_ms}
            for s in a.boxenstopps
        ],
    }


def schnappschuss(z: Rennzustand, mit_runden: bool = False) -> dict:
    """Vollstaendiger Stand der laufenden Session."""
    with z.lock:
        if not z.session_bekannt:
            return {"aktiv": False}
        autos = [auto_dict(z, a) for a in z.gueltige_autos()]
        if z.klassifizierung:
            ergebnis = {e["idx"]: e for e in z.klassifizierung}
            for a in autos:
                e = ergebnis.get(a["idx"])
                if e:
                    a["position"] = e["position"]
                    a["punkte"] = e["points"]
                    a["gesamtzeit_s"] = round(e["total_race_time"], 3)
                    a["strafen_s"] = e["penalties_time"]
                    a["boxenstopps_anzahl"] = e["num_pit_stops"]
                    a["result_status"] = e["result_status"]
                    a["status"] = k.RESULT_STATUS.get(e["result_status"], "")
                    a["runden_gefahren"] = e["num_laps"]
                    if z.ist_quali:
                        a["beste_runde_ms"] = e["best_lap_time_ms"]  # Wertung des Spiels
            autos.sort(key=lambda a: a["position"])
        if mit_runden:
            for a in autos:
                auto = z.autos[a["idx"]]
                a["runden"] = [
                    {"runde": nr, "zeit_ms": ms, **auto.runden_info.get(nr, {})}
                    for nr, ms in sorted(auto.rundenzeiten.items())
                ]
        return {
            "aktiv": True,
            "session": {
                "session_uid": str(z.session_uid),
                "saison_id": z.saison_id,
                "wochenende_id": z.wochenende_id,
                "session_link_id": z.session_link_id,
                "strecke_id": z.strecke_id,
                "strecke": z.strecke,
                "session_typ": z.session_typ,
                "typ_name": "Sprintrennen" if z.sprint else k.SESSION_TYP.get(z.session_typ, "Session"),
                "ist_sprint": z.sprint,
                "ist_rennen": z.ist_rennen,
                "ist_quali": z.ist_quali,
                "klassifiziert": bool(z.klassifizierung),
                "quali_teil": k.quali_teil(z.session_typ),
                "zeit_uebrig": z.zeit_uebrig,
                "ausscheidung": (k.ausscheidungslinie(z.session_typ, max(len(autos), z.anzahl_aktiv))
                                 if z.ist_quali else None),
                "gelb_sektoren": z.gelb_sektoren(),
                "runden_gesamt": z.runden_gesamt,
                "runde": z.fuehrungsrunde(),
                "zeit": round(z.session_time, 1),
                "wetter": z.wetter,
                "wetter_name": k.WETTER.get(z.wetter, ""),
                "streckentemperatur": z.streckentemperatur,
                "lufttemperatur": z.lufttemperatur,
                "safety_car": z.safety_car,
                "rote_flagge": z.rote_flagge,
                "rote_flaggen_anzahl": z.rote_flaggen_anzahl,
                "beendet": z.beendet,
                "spieler_idx": z.spieler_idx,
                "packet_format": z.packet_format,
                "formel": z.formel,
                "spielmodus": z.spielmodus,
                "netzwerkspiel": z.netzwerkspiel,
                "boxenfenster_ideal": z.boxenfenster_ideal,
                "boxenfenster_spaetestens": z.boxenfenster_spaetestens,
            },
            "prognose": [
                {"minuten": p["time_offset"], "wetter": p["weather"],
                 "wetter_name": k.WETTER.get(p["weather"], ""),
                 "regen_prozent": p["rain_percentage"],
                 "streckentemperatur": p["track_temperature"]}
                for p in z.prognose_session()
            ],
            "prognose_genau": z.prognose_genau,
            "wetter_log": [dict(w, wetter_name=k.WETTER.get(w["wetter"], "")) for w in z.wetter_log],
            "ereignisse": list(z.ereignis_log),
            "ausfaelle": [dict(e) for e in z.ausfaelle],
            # Die Reihenfolgen sind gross: die Live-Abfrage (jede Sekunde) nennt nur die Anzahl,
            # die Seite holt die Liste bei Bedarf ueber /api/wendepunkte.
            "momentaufnahmen_anzahl": len(z.momentaufnahmen),
            **({"momentaufnahmen": [dict(m) for m in z.momentaufnahmen],
                "rundenstaende": [z.rundenstaende[n] for n in sorted(z.rundenstaende)]}
               if mit_runden else {}),
            "autos": autos,
        }
