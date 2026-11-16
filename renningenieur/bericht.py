"""Session-Bericht: alles Wichtige einer Session in einer Datei.

Der Bericht entsteht aus demselben Datensatz, den die Webseite und die
Datenbank benutzen (siehe schnappschuss.py / datenbank.py). Es gibt ihn in
zwei Formen:

* `bericht_bauen(daten)`  ->  Dictionary (wird als JSON gespeichert; Format
  siehe BERICHT_FORMAT.md, gedacht zum Einlesen in eine Manager-App)
* `bericht_text(bericht)` ->  gut lesbarer deutscher Text

`exportieren()` schreibt beides in einen Ordner.
"""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path

from .telemetrie import konstanten as k

SCHEMA = "renningenieur.bericht"
VERSION = 2


# --------------------------------------------------------------------------
# Kleine Formatierer
# --------------------------------------------------------------------------
def zeit_text(ms: int | float | None) -> str:
    """79118 -> 1:19.118"""
    if not ms or ms <= 0:
        return "-"
    ms = int(round(ms))
    m, rest = divmod(ms, 60000)
    return f"{m}:{rest // 1000:02d}.{rest % 1000:03d}"


def abstand_text(ms: int | float | None) -> str:
    """250 -> +0.250, 62300 -> +1:02.300"""
    if ms is None:
        return "-"
    ms = int(round(ms))
    if ms <= 0:
        return "-"
    if ms >= 60000:
        m, rest = divmod(ms, 60000)
        return f"+{m}:{rest // 1000:02d}.{rest % 1000:03d}"
    return f"+{ms // 1000}.{ms % 1000:03d}"


def gesamtzeit_text(sekunden: float | None) -> str:
    if not sekunden or sekunden <= 0:
        return "-"
    ms = int(round(sekunden * 1000))
    h, rest = divmod(ms, 3_600_000)
    m, rest = divmod(rest, 60000)
    return f"{h}:{m:02d}:{rest // 1000:02d}.{rest % 1000:03d}" if h else f"{m}:{rest // 1000:02d}.{rest % 1000:03d}"


def runden_text(n: int) -> str:
    return "1 Runde" if n == 1 else f"{n} Runden"


def _gueltig(runde: dict) -> bool:
    return runde.get("gueltig") is None or bool(runde["gueltig"])


# --------------------------------------------------------------------------
# Bericht als Dictionary
# --------------------------------------------------------------------------
def bericht_bauen(daten: dict, erstellt: str | None = None) -> dict:
    """Baut den Bericht aus dem Datensatz einer Session (live oder gespeichert)."""
    s = daten["session"]
    autos = daten.get("autos", [])
    ist_quali = bool(s.get("ist_quali"))
    ausfaelle = daten.get("ausfaelle", [])
    letzte_runde = max((r["runde"] for a in autos for r in a.get("runden", [])), default=0)

    fahrer = [_fahrer(a, letzte_runde, ist_quali) for a in autos]
    nach_idx = {f["idx"]: f for f in fahrer}
    if ist_quali:
        ergebnis = _ergebnis_quali(fahrer, s)
    else:
        ergebnis = _ergebnis_rennen(autos, nach_idx, ausfaelle)
    bericht = {
        "schema": SCHEMA,
        "version": VERSION,
        "erstellt": erstellt or datetime.now().isoformat(timespec="seconds"),
        "session": {
            "session_uid": str(s.get("session_uid", "")),
            "saison_id": s.get("saison_id"),
            "wochenende_id": s.get("wochenende_id"),
            "typ": s.get("session_typ"),
            "typ_name": s.get("typ_name"),
            "ist_rennen": bool(s.get("ist_rennen")),
            "ist_sprint": bool(s.get("ist_sprint")),
            "art": _art(s),
            "ist_quali": ist_quali,
            "quali_teil": s.get("quali_teil") or "",
            "strecke": s.get("strecke"),
            "runden_geplant": s.get("runden_gesamt"),
            "runden_gefahren": letzte_runde or s.get("runde"),
            "beendet": bool(s.get("beendet")),
            "rote_flaggen": s.get("rote_flaggen_anzahl", s.get("rote_flaggen", 0)),
            "begonnen": s.get("begonnen"),
            "spieler": next((a["name"] for a in autos if a.get("ist_spieler")), None),
        },
        "wetter": _wetter(daten.get("wetter_log", [])),
        "ergebnis": ergebnis,
        "schnellste_runde": _schnellste_runde(autos),
        "ausfaelle": [dict(e) for e in ausfaelle],
        "ereignisse": [
            {"zeit": e["zeit"], "runde": e["runde"], "art": e["code"], "fahrer": e.get("idx"),
             "text": e["text"]}
            for e in daten.get("ereignisse", [])
        ],
        "momentaufnahmen": [dict(m) for m in daten.get("momentaufnahmen", [])],
        "fahrer": fahrer,
    }
    if ist_quali:
        bericht["quali"] = {
            "ausscheidungslinie": s.get("ausscheidung"),
            "teil": s.get("quali_teil") or "",
        }
    else:
        bericht["positionsverlauf"] = _positionsverlauf(daten, fahrer)
    return bericht


def _art(s: dict) -> str:
    """"rennen", "sprint", "qualifying", "sprint_shootout", "training" oder "sonstige"."""
    typ = s.get("session_typ") or 0
    if s.get("ist_sprint"):
        return "sprint"
    if s.get("ist_rennen"):
        return "rennen"
    if k.ist_shootout(typ):
        return "sprint_shootout"
    if k.ist_quali(typ):
        return "qualifying"
    return "training" if typ in k.TRAINING_SESSIONS else "sonstige"


def _wetter(log: list[dict]) -> dict:
    punkte = [{
        "zeit": w["zeit"], "runde": w["runde"], "wetter": w["wetter"],
        "wetter_name": w.get("wetter_name") or k.WETTER.get(w["wetter"], ""),
        "streckentemperatur": w["streckentemperatur"], "lufttemperatur": w["lufttemperatur"],
    } for w in log]
    return {
        "verlauf": punkte,
        "regen": any(p["wetter"] >= 3 for p in punkte),
        "streckentemperatur_min": min((p["streckentemperatur"] for p in punkte), default=None),
        "streckentemperatur_max": max((p["streckentemperatur"] for p in punkte), default=None),
    }


def _fahrer(a: dict, letzte_runde: int, ist_quali: bool = False) -> dict:
    runden = []
    for r in a.get("runden", []):
        runden.append({
            "runde": r["runde"], "zeit_ms": r["zeit_ms"], "gueltig": _gueltig(r),
            "position": r.get("position"), "rueckstand_fuehrender_ms": r.get("delta_fuehrender_ms"),
            "s1_ms": r.get("s1_ms"), "s2_ms": r.get("s2_ms"), "s3_ms": r.get("s3_ms"),
            "reifen": k.reifen(r["reifen_visuell"])["kurz"] if r.get("reifen_visuell") else None,
            "reifenalter": r.get("reifenalter"), "verschleiss": r.get("verschleiss"),
            "box": bool(r.get("box")),
        })
    gueltige = [r["zeit_ms"] for r in runden if r["gueltig"] and r["zeit_ms"] > 0]
    ende = max((r["runde"] for r in runden), default=letzte_runde)
    return {
        "idx": a["idx"], "name": a["name"], "team": a["team"], "startnummer": a["startnummer"],
        "ist_spieler": bool(a.get("ist_spieler")), "mensch": not a.get("ki", True),
        "startplatz": a.get("startplatz"), "position": a["position"],
        # Qualifying: die Bestzeit, die das Spiel meldet. Sonst: beste gueltige Runde.
        "beste_runde_ms": (a.get("beste_runde_ms") or 0) if ist_quali else (min(gueltige) if gueltige else 0),
        "boxenstopps": [dict(b) for b in a.get("boxenstopps", [])],
        "stints": _stints(a.get("stints", []), runden, ende),
        "runden": runden,
    }


def _stints(stints: list[dict], runden: list[dict], letzte: int) -> list[dict]:
    """Je Reifensatz: Mischung, Runden und wie schnell er verschlissen ist (in Prozent)."""
    ergebnis = []
    for nr, st in enumerate(stints, start=1):
        start = st["start_runde"] or 1
        ende = st["end_runde"] or letzte
        ende = max(ende, start) if st["end_runde"] is not None else max(letzte, start)
        liste = [r for r in runden if start <= r["runde"] <= ende]
        werte = [r["verschleiss"] for r in liste if r.get("verschleiss") is not None]
        n = ende - start + 1
        verschleiss_ende = max(werte) if werte else None
        pro_runde = None
        if werte and verschleiss_ende is not None:
            if st.get("alter_start", 0) == 0:
                pro_runde = verschleiss_ende / max(len(liste), 1)
            elif len(werte) > 1:
                pro_runde = (verschleiss_ende - werte[0]) / (len(werte) - 1)
        zeiten = [r["zeit_ms"] for r in liste if r["gueltig"] and r["zeit_ms"] > 0]
        ergebnis.append({
            "nr": nr,
            "mischung": st["mischung"], "kurz": st["kurz"],
            "tatsaechlich": st.get("tatsaechlich"),
            "start_runde": start, "end_runde": ende, "runden": n,
            "alter_start": st.get("alter_start", 0),
            "verschleiss_ende": round(verschleiss_ende, 1) if verschleiss_ende is not None else None,
            "verschleiss_pro_runde": round(pro_runde, 2) if pro_runde is not None else None,
            "beste_runde_ms": min(zeiten) if zeiten else 0,
            "schnitt_runde_ms": int(sum(zeiten) / len(zeiten)) if zeiten else 0,
        })
    return ergebnis


def _ergebnis_rennen(autos: list[dict], nach_idx: dict, ausfaelle: list[dict]) -> list[dict]:
    ausfall_von = {e["idx"]: e for e in ausfaelle}
    sieger = next((a for a in autos if a["position"] == 1), None)
    liste = []
    for a in sorted(autos, key=lambda a: a["position"]):
        f = nach_idx[a["idx"]]
        ausfall = ausfall_von.get(a["idx"])
        im_ziel = a.get("result_status") == 3
        gesamt = a.get("gesamtzeit_s")
        rueckstand = None
        if im_ziel and gesamt and sieger and sieger.get("gesamtzeit_s"):
            rueckstand = int(round((gesamt + (a.get("strafen_s") or 0)
                                    - sieger["gesamtzeit_s"] - (sieger.get("strafen_s") or 0)) * 1000))
        elif not ausfall and not im_ziel:
            rueckstand = a.get("rueckstand_ms")
        startplatz = a.get("startplatz") or 0
        liste.append({
            "position": a["position"], "idx": a["idx"], "name": a["name"], "team": a["team"],
            "startnummer": a["startnummer"], "ist_spieler": bool(a.get("ist_spieler")),
            "mensch": not a.get("ki", True),
            "startplatz": startplatz or None,
            "plaetze_gewonnen": (startplatz - a["position"]) if startplatz else None,
            "status": a.get("status") or "",
            "runden": a.get("runden_gefahren") or len(f["runden"]),
            "gesamtzeit_s": gesamt, "strafen_s": a.get("strafen_s") or 0,
            "rueckstand_ms": rueckstand,
            "beste_runde_ms": f["beste_runde_ms"],
            "punkte": a.get("punkte"),
            "boxenstopps": a.get("boxenstopps_anzahl"),
            "reifenfolge": [st["kurz"] for st in f["stints"]],
            "ausfall": ({"runde": ausfall["runde"], "grund": ausfall["grund"],
                         "position_beim_ausfall": ausfall.get("position")} if ausfall else None),
        })
    return liste


def _ergebnis_quali(fahrer: list[dict], s: dict) -> list[dict]:
    """Qualifying-Ergebnis in der Reihenfolge des Spiels (Platz und Bestzeit kommen vom Spiel).

    Nur wenn das Spiel keine brauchbaren Plaetze liefert (fehlen oder doppelt), wird nach
    Bestzeit sortiert. Wer keine Zeit hat, steht hinten.
    """
    plaetze = [f.get("position") or 0 for f in fahrer]
    spiel_ok = bool(fahrer) and all(plaetze) and len(set(plaetze)) == len(plaetze)
    if spiel_ok:
        reihe = sorted(fahrer, key=lambda f: f["position"])
    else:
        mit = sorted((f for f in fahrer if f["beste_runde_ms"]), key=lambda f: f["beste_runde_ms"])
        reihe = mit + [f for f in fahrer if not f["beste_runde_ms"]]
    mit = [f for f in reihe if f["beste_runde_ms"]]
    linie = s.get("ausscheidung")
    bestzeit = mit[0]["beste_runde_ms"] if mit else 0
    liste = []
    davor = 0
    for pos, f in enumerate(reihe, start=1):
        zeit = f["beste_runde_ms"]
        gueltige = [r for r in f["runden"] if r["gueltig"]]
        liste.append({
            "position": pos, "idx": f["idx"], "name": f["name"], "team": f["team"],
            "startnummer": f["startnummer"], "ist_spieler": f["ist_spieler"], "mensch": f["mensch"],
            "beste_runde_ms": zeit,
            "rueckstand_p1_ms": max(zeit - bestzeit, 0) if zeit and pos > 1 else 0,
            "rueckstand_vordermann_ms": max(zeit - davor, 0) if zeit and pos > 1 else 0,
            "quelle": "spiel" if spiel_ok else "berechnet",
            "runden": len(f["runden"]), "gueltige_runden": len(gueltige),
            "ungueltige_runden": len(f["runden"]) - len(gueltige),
            "reifen": f["stints"][-1]["kurz"] if f["stints"] else None,
            "weiter": (pos <= linie) if linie else None,
        })
        if zeit:
            davor = zeit
    return liste


def _schnellste_runde(autos: list[dict]) -> dict | None:
    beste = None
    for a in autos:
        for r in a.get("runden", []):
            if r["zeit_ms"] > 0 and _gueltig(r) and (beste is None or r["zeit_ms"] < beste["zeit_ms"]):
                beste = {"name": a["name"], "team": a["team"], "idx": a["idx"],
                         "runde": r["runde"], "zeit_ms": r["zeit_ms"],
                         "reifen": k.reifen(r["reifen_visuell"])["kurz"] if r.get("reifen_visuell") else None}
    return beste


def _positionsverlauf(daten: dict, fahrer: list[dict]) -> list[dict]:
    """Je Runde die komplette Reihenfolge (wer liegt nach dieser Runde wo)."""
    staende = daten.get("rundenstaende") or []
    if staende:
        return [{"runde": r["runde"], "zeit": r.get("zeit"), "reihenfolge": r["reihenfolge"]}
                for r in sorted(staende, key=lambda r: r["runde"])]
    # Aeltere Sessions ohne Rundenstaende: aus den Rundendaten der einzelnen Fahrer
    runden = sorted({r["runde"] for f in fahrer for r in f["runden"]})
    verlauf = []
    for nr in runden:
        reihenfolge = []
        for f in fahrer:
            r = next((r for r in f["runden"] if r["runde"] == nr), None)
            if r and r.get("position"):
                reihenfolge.append({"position": r["position"], "idx": f["idx"], "name": f["name"],
                                    "rueckstand_ms": r.get("rueckstand_fuehrender_ms") or 0,
                                    "reifen": r.get("reifen"), "in_box": bool(r.get("box"))})
        reihenfolge.sort(key=lambda e: e["position"])
        verlauf.append({"runde": nr, "zeit": None, "reihenfolge": reihenfolge})
    return verlauf


def kuerzel(namen: list[str]) -> dict[str, str]:
    """Eindeutige Drei-Buchstaben-Kuerzel (bei gleichem Anfang laenger)."""
    ergebnis: dict[str, str] = {}
    for name in namen:
        laenge = 3
        while True:
            k_ = name[:laenge].upper()
            if k_ not in ergebnis.values() or laenge >= len(name):
                ergebnis[name] = k_
                break
            laenge += 1
    return ergebnis


# --------------------------------------------------------------------------
# Qualifying gesamt (Q1 + Q2 + Q3 in einer Datei)
# --------------------------------------------------------------------------
GRUPPEN = {
    "qualifying": {"typen": (5, 6, 7), "name": "Qualifying", "letzter": 7},
    "sprint_shootout": {"typen": (10, 11, 12), "name": "Sprint-Shootout", "letzter": 12},
}


def quali_gruppe(session_typ: int) -> str | None:
    """"qualifying" (Q1-Q3), "sprint_shootout" (SQ1-SQ3) oder None (kein mehrteiliges Qualifying)."""
    for name, g in GRUPPEN.items():
        if session_typ in g["typen"]:
            return name
    return None


def _endergebnis(teile: list[dict]) -> list[dict]:
    """Startaufstellung aus allen Teilen: Q3-Fahrer vorn, dann die in Q2 und die in Q1 Ausgeschiedenen."""
    liste: list[dict] = []
    gesehen: set[int] = set()

    def aufnehmen(teil_bericht: dict, e: dict, ausgeschieden: bool) -> None:
        if e["idx"] in gesehen:
            return
        gesehen.add(e["idx"])
        bestzeit = teil_bericht["ergebnis"][0]["beste_runde_ms"] if teil_bericht["ergebnis"] else 0
        liste.append({
            "position": len(liste) + 1, "idx": e["idx"], "name": e["name"], "team": e["team"],
            "startnummer": e["startnummer"], "ist_spieler": e["ist_spieler"], "mensch": e["mensch"],
            "teil": teil_bericht["session"]["quali_teil"],
            "ausgeschieden_in": teil_bericht["session"]["quali_teil"] if ausgeschieden else "",
            "beste_runde_ms": e["beste_runde_ms"],
            "rueckstand_im_teil_ms": e["rueckstand_p1_ms"] if e["beste_runde_ms"] else 0,
        })

    # Wer durfte in welchem Teil mitfahren? (Q1: alle; danach nur, wer vorher "weiter" war.)
    zugelassen: list[set[int] | None] = [None]
    for t in teile[:-1]:
        vorher = zugelassen[-1]
        zugelassen.append({e["idx"] for e in t["ergebnis"]
                           if e.get("weiter") and (vorher is None or e["idx"] in vorher)})
    letzter = teile[-1]
    for e in letzter["ergebnis"]:
        if zugelassen[-1] is None or e["idx"] in zugelassen[-1]:
            aufnehmen(letzter, e, False)
    for i in range(len(teile) - 2, -1, -1):
        for e in teile[i]["ergebnis"]:
            if e.get("weiter") is False and (zugelassen[i] is None or e["idx"] in zugelassen[i]):
                aufnehmen(teile[i], e, True)
    # Fahrer, die in keinem Teil sauber zugeordnet werden konnten: hinten anhaengen
    for t in reversed(teile):
        for e in t["ergebnis"]:
            aufnehmen(t, e, t is not letzter)
    return liste


def gesamt_bauen(daten_teile: list[dict], erstellt: str | None = None) -> dict:
    """Ein Bericht fuer alle Qualifying-Teile (Daten je Teil wie bei `bericht_bauen`)."""
    teile = sorted((bericht_bauen(d, erstellt) for d in daten_teile),
                   key=lambda b: b["session"]["typ"])
    erster = teile[0]["session"]
    gruppe = quali_gruppe(erster["typ"]) or "qualifying"
    g = GRUPPEN[gruppe]
    return {
        "schema": SCHEMA,
        "version": VERSION,
        "art": "quali_gesamt",
        "erstellt": erstellt or datetime.now().isoformat(timespec="seconds"),
        "session": {
            "typ_name": f"{g['name']} gesamt",
            "art": gruppe,
            "ist_rennen": False, "ist_sprint": False, "ist_quali": True,
            "strecke": erster["strecke"], "saison_id": erster["saison_id"],
            "wochenende_id": erster["wochenende_id"],
            "teile": [t["session"]["quali_teil"] for t in teile],
            "abgeschlossen": teile[-1]["session"]["typ"] == g["letzter"] and teile[-1]["session"]["beendet"],
            "spieler": erster["spieler"],
        },
        "endergebnis": _endergebnis(teile),
        "teile": teile,
    }


def gesamt_text(g: dict) -> str:
    s = g["session"]
    z: list[str] = []
    kopf = f"{s['typ_name']} - {s['strecke']}"
    z.append(kopf.upper())
    z.append("=" * len(kopf))
    if s.get("spieler"):
        z.append(f"Fahrer: {s['spieler']}")
    z.append(f"Erstellt: {g['erstellt'].replace('T', ' ')}")
    z.append("Teile: " + ", ".join(s["teile"])
             + ("" if s["abgeschlossen"] else "  (noch nicht abgeschlossen, vorläufiger Stand)"))
    z.append("")
    z.append("Endergebnis (Startaufstellung)")
    z.append("------------------------------")
    z.append(f"  {'Pl':>2}  {'Fahrer':<14} {'Team':<14} {'Teil':<5} {'Zeit':<9} {'auf P1 im Teil':<14}")
    vorher = None
    for e in g["endergebnis"]:
        if vorher is not None and e["teil"] != vorher:
            z.append("  " + "- " * 22 + f"ab hier {e['teil']}")
        vorher = e["teil"]
        mark = "  <-- du" if e["ist_spieler"] else ("  <-- Mitspieler" if e["mensch"] else "")
        z.append(f"  {e['position']:>2}  {e['name']:<14} {e['team']:<14} {e['teil']:<5} "
                 f"{zeit_text(e['beste_runde_ms']):<9} "
                 f"{abstand_text(e['rueckstand_im_teil_ms']) if e['position'] > 1 and e['rueckstand_im_teil_ms'] else '':<14}{mark}")
    for teil in g["teile"]:
        z.append("")
        z.append("")
        z.append("#" * 72)
        z.append(f"# {teil['session']['typ_name']}")
        z.append("#" * 72)
        z.append(bericht_text(teil))
    return "\n".join(z)


def gesamt_dateiname(g: dict, endung: str) -> str:
    s = g["session"]
    datum = g["erstellt"][:10]
    name = f"{datum}_{s['typ_name']}_{s['strecke'] or ''}"
    for alt, neu in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("Ä", "Ae"), ("Ö", "Oe"), ("Ü", "Ue"), ("ß", "ss")):
        name = name.replace(alt, neu)
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^A-Za-z0-9\-]+", "_", name).strip("_") + "." + endung


# --------------------------------------------------------------------------
# Bericht als Text
# --------------------------------------------------------------------------
def bericht_text(b: dict) -> str:
    s = b["session"]
    z: list[str] = []

    def titel(text: str) -> None:
        z.extend(["", text, "-" * len(text)])

    kopf = f"{s['typ_name'] or 'Session'}"
    if s.get("strecke"):
        kopf += f" - {s['strecke']}"
    z.append(kopf.upper())
    z.append("=" * len(kopf))
    if s.get("spieler"):
        z.append(f"Fahrer: {s['spieler']}")
    z.append(f"Erstellt: {b['erstellt'].replace('T', ' ')}")
    if s["ist_rennen"]:
        z.append(f"Runden: {s['runden_gefahren']} von {s['runden_geplant']}"
                 + ("" if s["beendet"] else "  (Rennen noch nicht beendet)"))
        if s.get("rote_flaggen"):
            z.append(f"Rote Flaggen: {s['rote_flaggen']}")
    else:
        z.append("Session beendet" if s["beendet"] else "Session läuft noch")

    # --- Wetter
    w = b["wetter"]
    if w["verlauf"]:
        titel("Wetter")
        for p in w["verlauf"]:
            wann = "Start" if p["zeit"] <= 1 and p is w["verlauf"][0] else _minute(p)
            z.append(f"  {wann:<18} {p['wetter_name']:<16} Strecke {p['streckentemperatur']} °C, "
                     f"Luft {p['lufttemperatur']} °C")

    # --- Ergebnis
    if s["ist_quali"]:
        _text_quali(b, titel, z)
    else:
        _text_rennen(b, titel, z)

    # --- Schnellste Runde
    sr = b.get("schnellste_runde")
    if sr:
        titel("Schnellste Runde")
        z.append(f"  {sr['name']} ({sr['team']}) - {zeit_text(sr['zeit_ms'])} in Runde {sr['runde']}"
                 + (f" auf {sr['reifen']}" if sr.get("reifen") else ""))

    # --- Ausfaelle
    if b["ausfaelle"]:
        titel("Ausfälle")
        for e in b["ausfaelle"]:
            z.append(f"  Runde {e['runde']:>2}: {e['name']} ({e['team']}) - {e['grund']}, "
                     f"lag auf Platz {e['position']}")

    # --- Verlauf
    wichtig = [e for e in b["ereignisse"] if e["art"] in ("SC", "RDFL", "RESTART", "GELB", "STRAFE", "SIEGER")]
    if wichtig:
        titel("Ereignisse")
        for e in wichtig:
            z.append(f"  Runde {e['runde']:>2} ({_minute(e)}): {e['text']}")

    if b["momentaufnahmen"]:
        titel("Reihenfolge zu wichtigen Zeitpunkten")
        for m in b["momentaufnahmen"]:
            z.append("")
            z.append(f"  {m['text']} - Runde {m['runde']}, {_minute(m)}")
            for r in m["reihenfolge"]:
                if r["ausgefallen"]:
                    zusatz = "ausgefallen"
                else:
                    if r["position"] == 1:
                        zusatz = "Spitze"
                    else:
                        zusatz = abstand_text(r["rueckstand_ms"]) if r["rueckstand_ms"] else ""
                    alter = "neu" if not r["reifenalter"] else f"{runden_text(r['reifenalter'])} alt"
                    zusatz = f"{zusatz:<10} {r['reifen']} ({alter})"
                    if r["in_box"]:
                        zusatz += "  in der Box"
                z.append(f"    {r['position']:>2}. {r['name']:<14} {zusatz}")

    if b.get("positionsverlauf") is not None and not s["ist_quali"]:
        _text_verlauf(b, titel, z)

    # --- Reifen
    titel("Reifen und Verschleiß")
    z.append("  (Verschleiß in Prozent am Ende des Reifensatzes; Prozent pro Runde im Schnitt)")
    for f in sorted(b["fahrer"], key=lambda f: (not f["ist_spieler"], not f["mensch"], f["position"])):
        if not f["stints"]:
            continue
        if s["ist_quali"] and not (f["mensch"] or f["ist_spieler"]):
            continue  # im Qualifying zaehlen nur die eigenen Reifen
        z.append("")
        z.append(f"  {f['name']} ({f['team']})")
        for st in f["stints"]:
            teile = [f"Runde {st['start_runde']}-{st['end_runde']}", f"{st['kurz']} {st['mischung']}"]
            if st["alter_start"]:
                teile.append(f"gebraucht ({runden_text(st['alter_start'])} alt)")
            if st["verschleiss_ende"] is not None:
                teile.append(f"Verschleiß {st['verschleiss_ende']:.0f} %")
            if st["verschleiss_pro_runde"] is not None:
                teile.append(f"{st['verschleiss_pro_runde']:.1f} % pro Runde")
            if st["schnitt_runde_ms"]:
                teile.append(f"Schnitt {zeit_text(st['schnitt_runde_ms'])}")
            z.append("    " + ", ".join(teile))
        for bs in f["boxenstopps"]:
            teile = [f"Boxenstopp in Runde {bs['runde']}"]
            if bs.get("standzeit_ms"):
                teile.append(f"Standzeit {bs['standzeit_ms'] / 1000:.1f} s")
            if bs.get("zeit_gasse_ms"):
                teile.append(f"Boxengasse {bs['zeit_gasse_ms'] / 1000:.1f} s")
            z.append("    " + ", ".join(teile))

    # --- Rundenzeiten der Menschen
    menschen = [f for f in b["fahrer"] if f["mensch"] or f["ist_spieler"]]
    if menschen:
        titel("Rundenzeiten")
        for f in menschen:
            z.append("")
            z.append(f"  {f['name']}")
            beste = f["beste_runde_ms"]
            for r in f["runden"]:
                marke = ""
                if not r["gueltig"]:
                    marke = "  ungültig"
                elif beste and r["zeit_ms"] == beste:
                    marke = "  beste"
                if r["box"]:
                    marke += "  Box"
                pos = f"P{r['position']}" if r.get("position") else ""
                z.append(f"    Runde {r['runde']:>2}: {zeit_text(r['zeit_ms'])}  {pos:<4} "
                         f"{r.get('reifen') or '':<3}{marke}")
    z.append("")
    return "\n".join(z)


def _minute(e: dict) -> str:
    sek = int(e["zeit"])
    return f"{sek // 60}:{sek % 60:02d} min"


def _text_rennen(b: dict, titel, z: list[str]) -> None:
    titel("Endergebnis" if b["session"]["beendet"] else "Zwischenstand")
    z.append(f"  {'Pl':>2}  {'Fahrer':<14} {'Team':<14} {'Start':>5} {'Zeit/Rückstand':<30} "
             f"{'Beste':<9} {'Pkt':>3}  Reifen")
    for e in b["ergebnis"]:
        if e["ausfall"]:
            zeit = f"Runde {e['ausfall']['runde']}: {e['ausfall']['grund']}"
        elif e["position"] == 1 and e["gesamtzeit_s"]:
            zeit = gesamtzeit_text(e["gesamtzeit_s"] + e["strafen_s"])
        elif e["rueckstand_ms"]:
            zeit = abstand_text(e["rueckstand_ms"])
        else:
            zeit = "-"
        mark = "  <-- du" if e["ist_spieler"] else ("  <-- Mitspieler" if e["mensch"] else "")
        start = str(e["startplatz"]) if e["startplatz"] else "-"
        z.append(f"  {e['position']:>2}  {e['name']:<14} {e['team']:<14} {start:>5} {zeit:<30} "
                 f"{zeit_text(e['beste_runde_ms']):<9} {e['punkte'] if e['punkte'] is not None else '-':>3}  "
                 f"{'-'.join(e['reifenfolge'])}{mark}")
        if e["strafen_s"]:
            z.append(f"      (inkl. {e['strafen_s']} s Zeitstrafe)")


def _text_quali(b: dict, titel, z: list[str]) -> None:
    q = b["quali"]
    name = b["session"]["quali_teil"] or "Qualifying"
    titel(f"Ergebnis {name}")
    if q["ausscheidungslinie"]:
        z.append(f"  Bis Platz {q['ausscheidungslinie']} kommen weiter.")
    z.append(f"  {'Pl':>2}  {'Fahrer':<14} {'Team':<14} {'Zeit':<9} {'auf P1':<9} {'Vordermann':<10} "
             f"{'Runden':>6} {'ungült.':>7}  Reifen")
    for e in b["ergebnis"]:
        mark = "  <-- du" if e["ist_spieler"] else ("  <-- Mitspieler" if e["mensch"] else "")
        if e["weiter"] is False and not (e["position"] > 1 and b["ergebnis"][e["position"] - 2]["weiter"] is False):
            z.append("  " + "- " * 28 + "Ausscheidungslinie")
        z.append(f"  {e['position']:>2}  {e['name']:<14} {e['team']:<14} {zeit_text(e['beste_runde_ms']):<9} "
                 f"{abstand_text(e['rueckstand_p1_ms']) if e['position'] > 1 else '':<9} "
                 f"{abstand_text(e['rueckstand_vordermann_ms']) if e['position'] > 1 else '':<10} "
                 f"{e['runden']:>6} {e['ungueltige_runden']:>7}  {e['reifen'] or '-'}{mark}")


def _text_verlauf(b: dict, titel, z: list[str]) -> None:
    verlauf = b["positionsverlauf"]
    if not verlauf:
        return
    namen = []
    for v in verlauf:
        for e in v["reihenfolge"]:
            if e["name"] not in namen:
                namen.append(e["name"])
    kurz = kuerzel(namen)
    titel("Reihenfolge nach jeder Runde")
    z.append("  (Platz Kürzel, von vorn nach hinten; * = in der Box)")
    z.append("  " + ", ".join(f"{kurz[n]} = {n}" for n in namen))
    for v in verlauf:
        zeile = " ".join(
            f"{e['position']}.{kurz[e['name']]}{'*' if e.get('in_box') else ''}"
            + ("(aus)" if e.get("ausgefallen") else "")
            for e in v["reihenfolge"])
        z.append("")
        z.append(f"  Runde {v['runde']:>2}: {zeile}")


# --------------------------------------------------------------------------
# Dateien
# --------------------------------------------------------------------------
def dateiname(b: dict, endung: str) -> str:
    s = b["session"]
    stempel = (s.get("begonnen") or b["erstellt"])[:19].replace("T", "_").replace(":", "-")
    teile = [stempel, s.get("typ_name") or "Session", s.get("strecke") or ""]
    name = "_".join(t for t in teile if t)
    for alt, neu in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("Ä", "Ae"), ("Ö", "Oe"), ("Ü", "Ue"), ("ß", "ss")):
        name = name.replace(alt, neu)
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    name = re.sub(r"[^A-Za-z0-9\-]+", "_", name).strip("_")
    return f"{name}.{endung}"


def json_text(b: dict) -> str:
    return json.dumps(b, ensure_ascii=False, indent=1)


def exportieren_gesamt(daten_teile: list[dict], ordner: Path | str) -> dict[str, str]:
    """Schreibt den Gesamtbericht (alle Qualifying-Teile) als Text und JSON."""
    g = gesamt_bauen(daten_teile)
    ordner = Path(ordner)
    ordner.mkdir(parents=True, exist_ok=True)
    pfade = {}
    for endung, inhalt in (("txt", gesamt_text(g)), ("json", json_text(g))):
        pfad = ordner / gesamt_dateiname(g, endung)
        pfad.write_text(inhalt, encoding="utf-8")
        pfade[endung] = str(pfad)
    return pfade


def exportieren(daten: dict, ordner: Path | str) -> dict[str, str]:
    """Schreibt Text- und JSON-Bericht in den Ordner und gibt die Dateipfade zurueck."""
    b = bericht_bauen(daten)
    ordner = Path(ordner)
    ordner.mkdir(parents=True, exist_ok=True)
    pfade = {}
    for endung, inhalt in (("txt", bericht_text(b)), ("json", json_text(b))):
        pfad = ordner / dateiname(b, endung)
        pfad.write_text(inhalt, encoding="utf-8")
        pfade[endung] = str(pfad)
    return pfade
