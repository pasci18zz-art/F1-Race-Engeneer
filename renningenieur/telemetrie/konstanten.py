"""Nachschlagetabellen aus dem Anhang der UDP-Spec (deutsche Bezeichnungen)."""

from __future__ import annotations

# --- Wetter -----------------------------------------------------------------
WETTER = {
    0: "klar",
    1: "leicht bewölkt",
    2: "bedeckt",
    3: "leichter Regen",
    4: "starker Regen",
    5: "Gewitter",
}
WETTER_REGEN_AB = 3  # ab diesem Wert ist es nass


def ist_regen(weather: int) -> bool:
    return weather >= WETTER_REGEN_AB


# --- Session-Typen ----------------------------------------------------------
SESSION_TYP = {
    0: "Unbekannt",
    1: "Training 1",
    2: "Training 2",
    3: "Training 3",
    4: "Kurzes Training",
    5: "Qualifying 1",
    6: "Qualifying 2",
    7: "Qualifying 3",
    8: "Kurzes Qualifying",
    9: "Einzelrunden-Qualifying",
    10: "Sprint-Shootout 1",
    11: "Sprint-Shootout 2",
    12: "Sprint-Shootout 3",
    13: "Kurzes Sprint-Shootout",
    14: "Einzelrunden-Sprint-Shootout",
    15: "Rennen",
    16: "Rennen 2",
    17: "Rennen 3",
    18: "Zeitfahren",
}
RENN_SESSIONS = (15, 16, 17)


def ist_rennen(session_type: int) -> bool:
    return session_type in RENN_SESSIONS


# --- Reifen (visuelle Mischung) ---------------------------------------------
# name = fuer die Sprachausgabe, kurz = fuer Tabellen, farbe = fuer die Webseite
REIFEN_VISUELL = {
    16: {"name": "Soft", "kurz": "S", "farbe": "#e8002d"},
    17: {"name": "Medium", "kurz": "M", "farbe": "#ffd12e"},
    18: {"name": "Hard", "kurz": "H", "farbe": "#f0f0ec"},
    7: {"name": "Intermediate", "kurz": "I", "farbe": "#43b02a"},
    8: {"name": "Regenreifen", "kurz": "W", "farbe": "#0067ad"},
    # Klassische Autos
    9: {"name": "Trockenreifen", "kurz": "T", "farbe": "#e8002d"},
    10: {"name": "Regenreifen", "kurz": "W", "farbe": "#0067ad"},
    # Formel 2
    15: {"name": "Regenreifen", "kurz": "W", "farbe": "#0067ad"},
    19: {"name": "Supersoft", "kurz": "SS", "farbe": "#b14ba7"},
    20: {"name": "Soft", "kurz": "S", "farbe": "#e8002d"},
    21: {"name": "Medium", "kurz": "M", "farbe": "#ffd12e"},
    22: {"name": "Hard", "kurz": "H", "farbe": "#f0f0ec"},
}
REIFEN_UNBEKANNT = {"name": "unbekannte Reifen", "kurz": "?", "farbe": "#888888"}

# Tatsaechliche Mischung (C-Nummern)
REIFEN_TATSAECHLICH = {
    16: "C5",
    17: "C4",
    18: "C3",
    19: "C2",
    20: "C1",
    21: "C0",
    22: "C6",
    7: "Inter",
    8: "Wet",
    9: "Dry",
    10: "Wet",
    11: "Supersoft",
    12: "Soft",
    13: "Medium",
    14: "Hard",
    15: "Wet",
}

REGENREIFEN_VISUELL = (7, 8, 10, 15)


def reifen(visual: int) -> dict:
    return REIFEN_VISUELL.get(visual, REIFEN_UNBEKANNT)


# Reihenfolge der Reifen-Arrays in der Telemetrie
REIFEN_POSITIONEN = ("hinten links", "hinten rechts", "vorne links", "vorne rechts")


# --- Teams ------------------------------------------------------------------
TEAMS = {
    0: {"name": "Mercedes", "farbe": "#27f4d2"},
    1: {"name": "Ferrari", "farbe": "#e8002d"},
    2: {"name": "Red Bull", "farbe": "#3671c6"},
    3: {"name": "Williams", "farbe": "#64c4ff"},
    4: {"name": "Aston Martin", "farbe": "#229971"},
    5: {"name": "Alpine", "farbe": "#ff87bc"},
    6: {"name": "Racing Bulls", "farbe": "#6692ff"},
    7: {"name": "Haas", "farbe": "#b6babd"},
    8: {"name": "McLaren", "farbe": "#ff8000"},
    9: {"name": "Sauber", "farbe": "#52e252"},
    41: {"name": "F1 Generic", "farbe": "#aaaaaa"},
    104: {"name": "Eigenes Team", "farbe": "#aaaaaa"},
    129: {"name": "Konnersport", "farbe": "#aaaaaa"},
    142: {"name": "APXGP", "farbe": "#c8a45c"},
    154: {"name": "APXGP", "farbe": "#c8a45c"},
    155: {"name": "Konnersport", "farbe": "#aaaaaa"},
}
TEAM_UNBEKANNT = {"name": "Team", "farbe": "#aaaaaa"}


def team(team_id: int) -> dict:
    return TEAMS.get(team_id, TEAM_UNBEKANNT)


# --- Strecken ---------------------------------------------------------------
STRECKEN = {
    0: "Melbourne",
    1: "Paul Ricard",
    2: "Shanghai",
    3: "Sakhir (Bahrain)",
    4: "Barcelona",
    5: "Monaco",
    6: "Montreal",
    7: "Silverstone",
    8: "Hockenheim",
    9: "Hungaroring",
    10: "Spa",
    11: "Monza",
    12: "Singapur",
    13: "Suzuka",
    14: "Abu Dhabi",
    15: "Austin",
    16: "Interlagos",
    17: "Spielberg",
    18: "Sotschi",
    19: "Mexiko",
    20: "Baku",
    21: "Sakhir kurz",
    22: "Silverstone kurz",
    23: "Austin kurz",
    24: "Suzuka kurz",
    25: "Hanoi",
    26: "Zandvoort",
    27: "Imola",
    28: "Portimão",
    29: "Dschidda",
    30: "Miami",
    31: "Las Vegas",
    32: "Losail (Katar)",
    39: "Silverstone (rückwärts)",
    40: "Spielberg (rückwärts)",
    41: "Zandvoort (rückwärts)",
    42: "Madrid",
}


def strecke(track_id: int) -> str:
    return STRECKEN.get(track_id, f"Strecke {track_id}")


# --- Status-Werte aus Lap Data ----------------------------------------------
PIT_NEIN, PIT_GASSE, PIT_BOX = 0, 1, 2

RESULT_STATUS = {
    0: "ungültig",
    1: "inaktiv",
    2: "aktiv",
    3: "im Ziel",
    4: "ausgefallen",
    5: "disqualifiziert",
    6: "nicht gewertet",
    7: "aufgegeben",
}
RESULT_AKTIV = 2

# --- Safety Car -------------------------------------------------------------
SC_KEINS, SC_VOLL, SC_VIRTUELL, SC_FORMATION = 0, 1, 2, 3


# --- Ausfaelle (Retirement-Event, Feld "reason") -------------------------------
# 0 ungueltig, 1 aufgegeben, 2 im Ziel, 3 schwerer Schaden, 4 inaktiv, 5 zu wenige
# Runden, 6 schwarze Flagge, 7 rote Flagge, 8 mechanisches Problem, 9 Session
# uebersprungen, 10 Session simuliert.
AUSFALL_ECHT = (1, 3, 4, 6, 8)  # nur diese sind ein echter Ausfall im Rennen
AUSFALL_GRUND = {
    0: "unbekannt", 1: "aufgegeben", 2: "im Ziel", 3: "schwerer Schaden", 4: "inaktiv",
    5: "zu wenige Runden", 6: "schwarze Flagge", 7: "rote Flagge", 8: "mechanisches Problem",
    9: "Session übersprungen", 10: "Session simuliert",
}
# Schluessel in texte.toml unter [ausfall_grund]
AUSFALL_TEXT_SCHLUESSEL = {1: "aufgegeben", 3: "schaden", 4: "inaktiv", 6: "schwarze_flagge",
                           8: "mechanisch"}

# --- Qualifying ------------------------------------------------------------------
# Session-Typen 5 bis 14: Q1-Q3, kurzes Q, Einzelrunden-Q und die Sprint-Shootouts
QUALI_SESSIONS = tuple(range(5, 15))
TRAINING_SESSIONS = (1, 2, 3, 4)


def ist_quali(session_type: int) -> bool:
    return session_type in QUALI_SESSIONS


def quali_teil(session_type: int) -> str:
    """"Q1", "Q2", "Q3" oder "" (kurzes Qualifying ohne Ausscheiden)."""
    return {5: "Q1", 6: "Q2", 7: "Q3", 10: "SQ1", 11: "SQ2", 12: "SQ3"}.get(session_type, "")


def ausscheidungslinie(session_type: int, anzahl_autos: int) -> int | None:
    """Letzter Platz, der weiterkommt (None = kein Ausscheiden).

    Q1 / SQ1: das hintere Viertel (20 Autos: 5, 22 Autos: 6) scheidet aus.
    Q2 / SQ2: es kommen die ersten 10 weiter.
    """
    if session_type in (5, 10):
        return max(anzahl_autos - round(anzahl_autos / 4), 1)
    if session_type in (6, 11):
        return 10
    return None


# --- Strafen (Penalty-Event) ---------------------------------------------------
STRAFARTEN = {
    0: "Durchfahrtsstrafe", 1: "Stop-and-Go", 2: "Startplatzstrafe", 3: "Strafen-Erinnerung",
    4: "Zeitstrafe", 5: "Verwarnung", 6: "Disqualifikation", 7: "Aus der Einführungsrunde genommen",
    8: "Zu lange geparkt", 9: "Reifenvorschrift", 10: "Runde ungültig",
    11: "Diese und nächste Runde ungültig", 12: "Runde ungültig", 13: "Diese und nächste Runde ungültig",
    14: "Diese und vorherige Runde ungültig", 15: "Diese und vorherige Runde ungültig",
    16: "Aufgegeben", 17: "Schwarze Flagge",
}
VERGEHEN = {
    0: "Blockieren durch langsames Fahren", 1: "Blockieren durch Falschfahren",
    2: "Rückwärts von der Startlinie", 3: "Schwere Kollision", 4: "Leichte Kollision",
    5: "Platz nach Kollision nicht zurückgegeben", 6: "Platz nach Kollision nicht zurückgegeben",
    7: "Abkürzen mit Zeitgewinn", 8: "Überholen durch Abkürzen", 9: "Überholen durch Abkürzen",
    10: "Boxenausfahrt überfahren", 11: "Blaue Flaggen ignoriert", 12: "Gelbe Flaggen ignoriert",
    13: "Durchfahrtsstrafe ignoriert", 14: "Zu viele Durchfahrtsstrafen",
    15: "Durchfahrtsstrafe bald abzusitzen", 16: "Durchfahrtsstrafe diese Runde abzusitzen",
    17: "Zu schnell in der Boxengasse", 18: "Zu lange geparkt", 19: "Reifenvorschrift missachtet",
    20: "Zu viele Strafen", 21: "Mehrere Verwarnungen", 22: "Disqualifikation droht",
    23: "Reifenvorschrift", 24: "Reifenvorschrift", 25: "Runde ungültig (Abkürzen)",
    26: "Runde ungültig (neben der Strecke)", 27: "Neben der Strecke mit kleinem Zeitgewinn",
    28: "Neben der Strecke mit deutlichem Zeitgewinn", 29: "Neben der Strecke mit extremem Zeitgewinn",
    30: "Runde ungültig (Wand berührt)", 31: "Runde ungültig (Flashback benutzt)",
    32: "Runde ungültig (auf die Strecke zurückgesetzt)", 33: "Boxengasse blockiert",
    34: "Fehlstart", 35: "Kollision mit dem Safety Car", 36: "Safety Car illegal überholt",
    37: "Safety-Car-Tempo überschritten", 38: "Virtual-Safety-Car-Tempo überschritten",
    39: "Einführungsrunde zu langsam", 40: "Einführungsrunde geparkt", 41: "Mechanischer Defekt",
    42: "Schwerer Schaden", 43: "Zu weit hinter dem Safety Car", 44: "Schwarze-Flagge-Zeit",
    45: "Stop-and-Go nicht abgesessen", 46: "Durchfahrtsstrafe nicht abgesessen",
    47: "Motorteil gewechselt", 48: "Getriebe gewechselt", 49: "Parc-Fermé-Änderung",
    50: "Ligastrafe", 51: "Wiederholungsstrafe", 52: "Unerlaubter Zeitgewinn",
    53: "Pflicht-Boxenstopp", 54: "Zugewiesen",
}


# Lap Data "driver_status": was das Auto gerade macht (vor allem im Qualifying wichtig)
FAHRERSTATUS = {0: "Garage", 1: "Fliegende Runde", 2: "Einfahrrunde", 3: "Ausfahrrunde", 4: "Auf der Strecke"}
