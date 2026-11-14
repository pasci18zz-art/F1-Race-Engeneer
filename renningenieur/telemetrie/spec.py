"""Paketformat der F1-25-UDP-Telemetrie (Formate 2025 und 2026).

Quelle: offizielle EA/Codemasters-Spezifikation "Data Output from F1 25"
(Format 2025) und "Data Output from F1 25: 2026 Season Pack" (Format 2026).
Die Feldreihenfolge wurde gegen zwei unabhaengige Umsetzungen der Spec
abgeglichen (PyPI "f1-packets" 2025.1.0 / 2026.1.1, das direkt aus dem
Spec-Dokument generiert wird, und npm "@deltazeroproduction/f1-udp-parser").
Die Paketgroessen unten stehen so in der Spec und werden in den Tests gegen
die hier definierten Strukturen geprueft.

Alle Werte sind Little Endian und ohne Fuellbytes gepackt.

Unterschiede 2026 gegenueber 2025 (Season Pack):
  * 24 statt 22 Fahrzeug-Plaetze in allen Fahrzeug-Arrays
  * ParticipantData: driverId, networkId, teamId sind uint16
  * CarStatusData: neues Feld ersHarvestLimitPerLap
  * CarTelemetryData: engineTemperature ist uint8
  * Motion: G-Kraefte als int16
  * Session: zusaetzliche Felder am Ende (Active Aero, DRS-Zonen, ...)
  * Collision-Event: zusaetzliches Feld severity
  * LapPositions: 50 x 24 statt 50 x 22
  * Neues Paket 16 (Car Telemetry 2)
"""

from __future__ import annotations

import struct

# --------------------------------------------------------------------------
# Paket-IDs
# --------------------------------------------------------------------------
MOTION = 0
SESSION = 1
LAP_DATA = 2
EVENT = 3
PARTICIPANTS = 4
CAR_SETUPS = 5
CAR_TELEMETRY = 6
CAR_STATUS = 7
FINAL_CLASSIFICATION = 8
LOBBY_INFO = 9
CAR_DAMAGE = 10
SESSION_HISTORY = 11
TYRE_SETS = 12
MOTION_EX = 13
TIME_TRIAL = 14
LAP_POSITIONS = 15
CAR_TELEMETRY_2 = 16

PACKET_NAMES = {
    MOTION: "Motion",
    SESSION: "Session",
    LAP_DATA: "Lap Data",
    EVENT: "Event",
    PARTICIPANTS: "Participants",
    CAR_SETUPS: "Car Setups",
    CAR_TELEMETRY: "Car Telemetry",
    CAR_STATUS: "Car Status",
    FINAL_CLASSIFICATION: "Final Classification",
    LOBBY_INFO: "Lobby Info",
    CAR_DAMAGE: "Car Damage",
    SESSION_HISTORY: "Session History",
    TYRE_SETS: "Tyre Sets",
    MOTION_EX: "Motion Ex",
    TIME_TRIAL: "Time Trial",
    LAP_POSITIONS: "Lap Positions",
    CAR_TELEMETRY_2: "Car Telemetry 2",
}

SUPPORTED_FORMATS = (2025, 2026)
NUM_CARS = {2025: 22, 2026: 24}

# Paketgroessen in Bytes laut Spec (inklusive 29 Byte Header).
PACKET_SIZES = {
    2025: {
        MOTION: 1349,
        SESSION: 753,
        LAP_DATA: 1285,
        EVENT: 45,
        PARTICIPANTS: 1284,
        CAR_SETUPS: 1133,
        CAR_TELEMETRY: 1352,
        CAR_STATUS: 1239,
        FINAL_CLASSIFICATION: 1042,
        LOBBY_INFO: 954,
        CAR_DAMAGE: 1041,
        SESSION_HISTORY: 1460,
        TYRE_SETS: 231,
        MOTION_EX: 273,
        TIME_TRIAL: 101,
        LAP_POSITIONS: 1131,
    },
    2026: {
        MOTION: 1325,
        SESSION: 926,
        LAP_DATA: 1399,
        EVENT: 45,
        PARTICIPANTS: 1470,
        CAR_SETUPS: 1233,
        CAR_TELEMETRY: 1448,
        CAR_STATUS: 1445,
        FINAL_CLASSIFICATION: 1134,
        LOBBY_INFO: 1062,
        CAR_DAMAGE: 1133,
        SESSION_HISTORY: 1460,
        TYRE_SETS: 231,
        MOTION_EX: 273,
        TIME_TRIAL: 104,
        LAP_POSITIONS: 1231,
        CAR_TELEMETRY_2: 269,
    },
}


# --------------------------------------------------------------------------
# Kleine Hilfsklasse: benannte Felder <-> struct
# --------------------------------------------------------------------------
class Layout:
    """Beschreibt eine gepackte Struktur als Liste (Feldname, struct-Code).

    Codes wie "B", "f", "H" sind Einzelwerte, "4f" ein Array aus vier Floats
    (wird zu einer Liste), "32s" ein Byte-String fester Laenge.
    """

    def __init__(self, fields: list[tuple[str, str]]):
        self.fields = fields
        self.struct = struct.Struct("<" + "".join(code for _, code in fields))
        self.size = self.struct.size
        # (name, start, anzahl, ist_array)
        self._slots: list[tuple[str, int, int, bool]] = []
        pos = 0
        for name, code in fields:
            if code.endswith("s"):
                self._slots.append((name, pos, 1, False))
                pos += 1
            elif len(code) > 1:
                n = int(code[:-1])
                self._slots.append((name, pos, n, True))
                pos += n
            else:
                self._slots.append((name, pos, 1, False))
                pos += 1
        self._count = pos

    def unpack_from(self, buf: bytes, offset: int = 0) -> dict:
        values = self.struct.unpack_from(buf, offset)
        out = {}
        for name, start, n, is_array in self._slots:
            out[name] = list(values[start : start + n]) if is_array else values[start]
        return out

    def pack(self, data: dict | None = None) -> bytes:
        """Packt ein dict; fehlende Felder werden mit 0 gefuellt."""
        data = data or {}
        flat: list = []
        for (name, start, n, is_array), (_, code) in zip(self._slots, self.fields):
            if code.endswith("s"):
                value = data.get(name, b"")
                if isinstance(value, str):
                    value = value.encode("utf-8")
                flat.append(value)
            elif is_array:
                value = list(data.get(name, ()))
                value += [0] * (n - len(value))
                flat.extend(value[:n])
            else:
                flat.append(data.get(name, 0))
        return self.struct.pack(*flat)


# --------------------------------------------------------------------------
# Header (in 2025 und 2026 identisch, 29 Bytes)
# --------------------------------------------------------------------------
HEADER = Layout(
    [
        ("packet_format", "H"),  # 2025 oder 2026
        ("game_year", "B"),
        ("game_major_version", "B"),
        ("game_minor_version", "B"),
        ("packet_version", "B"),
        ("packet_id", "B"),
        ("session_uid", "Q"),
        ("session_time", "f"),
        ("frame_identifier", "I"),
        ("overall_frame_identifier", "I"),
        ("player_car_index", "B"),
        ("secondary_player_car_index", "B"),
    ]
)
HEADER_SIZE = HEADER.size  # 29


# --------------------------------------------------------------------------
# Session (Paket 1)
# --------------------------------------------------------------------------
MARSHAL_ZONE = Layout([("zone_start", "f"), ("zone_flag", "b")])
MAX_MARSHAL_ZONES = 21

WEATHER_FORECAST_SAMPLE = Layout(
    [
        ("session_type", "B"),
        ("time_offset", "B"),  # Minuten ab jetzt
        ("weather", "B"),
        ("track_temperature", "b"),
        ("track_temperature_change", "b"),
        ("air_temperature", "b"),
        ("air_temperature_change", "b"),
        ("rain_percentage", "B"),
    ]
)
MAX_FORECAST_SAMPLES = 64

SESSION_PART1 = Layout(
    [
        ("weather", "B"),
        ("track_temperature", "b"),
        ("air_temperature", "b"),
        ("total_laps", "B"),
        ("track_length", "H"),
        ("session_type", "B"),
        ("track_id", "b"),
        ("formula", "B"),
        ("session_time_left", "H"),
        ("session_duration", "H"),
        ("pit_speed_limit", "B"),
        ("game_paused", "B"),
        ("is_spectating", "B"),
        ("spectator_car_index", "B"),
        ("sli_pro_native_support", "B"),
        ("num_marshal_zones", "B"),
    ]
)
# ... danach 21 x MARSHAL_ZONE ...
SESSION_PART2 = Layout(
    [
        ("safety_car_status", "B"),
        ("network_game", "B"),
        ("num_weather_forecast_samples", "B"),
    ]
)
# ... danach 64 x WEATHER_FORECAST_SAMPLE ...
SESSION_PART3 = Layout(
    [
        ("forecast_accuracy", "B"),  # 0 = perfekt, 1 = ungefaehr
        ("ai_difficulty", "B"),
        ("season_link_identifier", "I"),
        ("weekend_link_identifier", "I"),
        ("session_link_identifier", "I"),
        ("pit_stop_window_ideal_lap", "B"),
        ("pit_stop_window_latest_lap", "B"),
        ("pit_stop_rejoin_position", "B"),
        ("steering_assist", "B"),
        ("braking_assist", "B"),
        ("gearbox_assist", "B"),
        ("pit_assist", "B"),
        ("pit_release_assist", "B"),
        ("ers_assist", "B"),
        ("drs_assist", "B"),
        ("dynamic_racing_line", "B"),
        ("dynamic_racing_line_type", "B"),
        ("game_mode", "B"),
        ("rule_set", "B"),
        ("time_of_day", "I"),
        ("session_length", "B"),
        ("speed_units_lead_player", "B"),
        ("temperature_units_lead_player", "B"),
        ("speed_units_secondary_player", "B"),
        ("temperature_units_secondary_player", "B"),
        ("num_safety_car_periods", "B"),
        ("num_virtual_safety_car_periods", "B"),
        ("num_red_flag_periods", "B"),
        ("equal_car_performance", "B"),
        ("recovery_mode", "B"),
        ("flashback_limit", "B"),
        ("surface_type", "B"),
        ("low_fuel_mode", "B"),
        ("race_starts", "B"),
        ("tyre_temperature", "B"),
        ("pit_lane_tyre_sim", "B"),
        ("car_damage", "B"),
        ("car_damage_rate", "B"),
        ("collisions", "B"),
        ("collisions_off_for_first_lap_only", "B"),
        ("mp_unsafe_pit_release", "B"),
        ("mp_off_for_griefing", "B"),
        ("corner_cutting_stringency", "B"),
        ("parc_ferme_rules", "B"),
        ("pit_stop_experience", "B"),
        ("safety_car", "B"),
        ("safety_car_experience", "B"),
        ("formation_lap", "B"),
        ("formation_lap_experience", "B"),
        ("red_flags", "B"),
        ("affects_licence_level_solo", "B"),
        ("affects_licence_level_mp", "B"),
        ("num_sessions_in_weekend", "B"),
        ("weekend_structure", "12B"),
        ("sector2_lap_distance_start", "f"),
        ("sector3_lap_distance_start", "f"),
    ]
)
# Nur Format 2026: Anhang hinter dem 2025er-Teil (hier nicht ausgewertet).
SESSION_TAIL_2026 = Layout(
    [
        ("active_aero_track_status", "B"),
        ("num_active_aero_zones_full", "B"),
        ("active_aero_zones_full", "16f"),  # 8 x (start, ende)
        ("num_active_aero_zones_partial", "B"),
        ("active_aero_zones_partial", "16f"),
        ("num_drs_zones", "B"),
        ("drs_zones", "8f"),  # 4 x (start, ende)
        ("start_reaction_time", "f"),
        ("anti_lock_brakes_assist", "B"),
        ("traction_control_assist", "B"),
        ("dynamic_racing_line_hi_vis", "B"),
        ("dynamic_racing_line_colour_blind", "B"),
        ("recurring_rewind_prompt", "B"),
    ]
)


# --------------------------------------------------------------------------
# Lap Data (Paket 2) - in 2025 und 2026 gleich (57 Bytes je Auto)
# --------------------------------------------------------------------------
LAP_DATA_CAR = Layout(
    [
        ("last_lap_time_ms", "I"),
        ("current_lap_time_ms", "I"),
        ("sector1_time_ms_part", "H"),
        ("sector1_time_minutes_part", "B"),
        ("sector2_time_ms_part", "H"),
        ("sector2_time_minutes_part", "B"),
        ("delta_to_car_in_front_ms_part", "H"),
        ("delta_to_car_in_front_minutes_part", "B"),
        ("delta_to_race_leader_ms_part", "H"),
        ("delta_to_race_leader_minutes_part", "B"),
        ("lap_distance", "f"),
        ("total_distance", "f"),
        ("safety_car_delta", "f"),
        ("car_position", "B"),
        ("current_lap_num", "B"),
        ("pit_status", "B"),  # 0 = nein, 1 = Boxengasse, 2 = in der Box
        ("num_pit_stops", "B"),
        ("sector", "B"),
        ("current_lap_invalid", "B"),
        ("penalties", "B"),  # Sekunden
        ("total_warnings", "B"),
        ("corner_cutting_warnings", "B"),
        ("num_unserved_drive_through_pens", "B"),
        ("num_unserved_stop_go_pens", "B"),
        ("grid_position", "B"),
        ("driver_status", "B"),
        ("result_status", "B"),
        ("pit_lane_timer_active", "B"),
        ("pit_lane_time_in_lane_ms", "H"),
        ("pit_stop_timer_ms", "H"),
        ("pit_stop_should_serve_pen", "B"),
        ("speed_trap_fastest_speed", "f"),
        ("speed_trap_fastest_lap", "B"),
    ]
)
LAP_DATA_TAIL = Layout(
    [("time_trial_pb_car_idx", "B"), ("time_trial_rival_car_idx", "B")]
)


# --------------------------------------------------------------------------
# Participants (Paket 4)
# --------------------------------------------------------------------------
_PARTICIPANT_COMMON_TAIL = [
    ("my_team", "B"),
    ("race_number", "B"),
    ("nationality", "B"),
    ("name", "32s"),  # UTF-8, nullterminiert
    ("your_telemetry", "B"),  # 0 = eingeschraenkt, 1 = oeffentlich
    ("show_online_names", "B"),
    ("tech_level", "H"),
    ("platform", "B"),
    ("num_colours", "B"),
    ("livery_colours", "12B"),  # 4 x (rot, gruen, blau)
]
PARTICIPANT = {
    2025: Layout(
        [
            ("ai_controlled", "B"),
            ("driver_id", "B"),
            ("network_id", "B"),
            ("team_id", "B"),
        ]
        + _PARTICIPANT_COMMON_TAIL
    ),
    2026: Layout(
        [
            ("ai_controlled", "B"),
            ("driver_id", "H"),
            ("network_id", "H"),
            ("team_id", "H"),
        ]
        + _PARTICIPANT_COMMON_TAIL
    ),
}


# --------------------------------------------------------------------------
# Car Status (Paket 7)
# --------------------------------------------------------------------------
_CAR_STATUS_HEAD = [
    ("traction_control", "B"),
    ("anti_lock_brakes", "B"),
    ("fuel_mix", "B"),
    ("front_brake_bias", "B"),
    ("pit_limiter_status", "B"),
    ("fuel_in_tank", "f"),
    ("fuel_capacity", "f"),
    ("fuel_remaining_laps", "f"),
    ("max_rpm", "H"),
    ("idle_rpm", "H"),
    ("max_gears", "B"),
    ("drs_allowed", "B"),
    ("drs_activation_distance", "H"),
    ("actual_tyre_compound", "B"),
    ("visual_tyre_compound", "B"),
    ("tyres_age_laps", "B"),
    ("vehicle_fia_flags", "b"),
    ("engine_power_ice", "f"),
    ("engine_power_mguk", "f"),
    ("ers_store_energy", "f"),
    ("ers_deploy_mode", "B"),
    ("ers_harvested_this_lap_mguk", "f"),
    ("ers_harvested_this_lap_mguh", "f"),
]
_CAR_STATUS_TAIL = [("ers_deployed_this_lap", "f"), ("network_paused", "B")]
CAR_STATUS_CAR = {
    2025: Layout(_CAR_STATUS_HEAD + _CAR_STATUS_TAIL),
    2026: Layout(
        _CAR_STATUS_HEAD + [("ers_harvest_limit_per_lap", "f")] + _CAR_STATUS_TAIL
    ),
}


# --------------------------------------------------------------------------
# Car Damage (Paket 10) - in 2025 und 2026 gleich (46 Bytes je Auto)
# Reihenfolge der Reifen-Arrays: hinten links, hinten rechts, vorne links,
# vorne rechts.
# --------------------------------------------------------------------------
CAR_DAMAGE_CAR = Layout(
    [
        ("tyres_wear", "4f"),  # Prozent
        ("tyres_damage", "4B"),
        ("brakes_damage", "4B"),
        ("tyre_blisters", "4B"),
        ("front_left_wing_damage", "B"),
        ("front_right_wing_damage", "B"),
        ("rear_wing_damage", "B"),
        ("floor_damage", "B"),
        ("diffuser_damage", "B"),
        ("sidepod_damage", "B"),
        ("drs_fault", "B"),
        ("ers_fault", "B"),
        ("gear_box_damage", "B"),
        ("engine_damage", "B"),
        ("engine_mguh_wear", "B"),
        ("engine_es_wear", "B"),
        ("engine_ce_wear", "B"),
        ("engine_ice_wear", "B"),
        ("engine_mguk_wear", "B"),
        ("engine_tc_wear", "B"),
        ("engine_blown", "B"),
        ("engine_seized", "B"),
    ]
)


# --------------------------------------------------------------------------
# Final Classification (Paket 8) - 46 Bytes je Auto
# --------------------------------------------------------------------------
FINAL_CLASSIFICATION_CAR = Layout(
    [
        ("position", "B"),
        ("num_laps", "B"),
        ("grid_position", "B"),
        ("points", "B"),
        ("num_pit_stops", "B"),
        ("result_status", "B"),
        ("result_reason", "B"),
        ("best_lap_time_ms", "I"),
        ("total_race_time", "d"),  # Sekunden, ohne Strafen
        ("penalties_time", "B"),
        ("num_penalties", "B"),
        ("num_tyre_stints", "B"),
        ("tyre_stints_actual", "8B"),
        ("tyre_stints_visual", "8B"),
        ("tyre_stints_end_laps", "8B"),
    ]
)


# --------------------------------------------------------------------------
# Session History (Paket 11) - ein Auto pro Paket, reihum
# --------------------------------------------------------------------------
SESSION_HISTORY_HEAD = Layout(
    [
        ("car_idx", "B"),
        ("num_laps", "B"),
        ("num_tyre_stints", "B"),
        ("best_lap_time_lap_num", "B"),
        ("best_sector1_lap_num", "B"),
        ("best_sector2_lap_num", "B"),
        ("best_sector3_lap_num", "B"),
    ]
)
LAP_HISTORY = Layout(
    [
        ("lap_time_ms", "I"),
        ("sector1_time_ms_part", "H"),
        ("sector1_time_minutes_part", "B"),
        ("sector2_time_ms_part", "H"),
        ("sector2_time_minutes_part", "B"),
        ("sector3_time_ms_part", "H"),
        ("sector3_time_minutes_part", "B"),
        ("lap_valid_bit_flags", "B"),  # Bit 0 = Runde gueltig
    ]
)
MAX_LAP_HISTORY = 100
TYRE_STINT_HISTORY = Layout(
    [
        ("end_lap", "B"),  # 255 = laufender Stint
        ("tyre_actual_compound", "B"),
        ("tyre_visual_compound", "B"),
    ]
)
MAX_TYRE_STINTS = 8


# --------------------------------------------------------------------------
# Tyre Sets (Paket 12) - ein Auto pro Paket
# --------------------------------------------------------------------------
TYRE_SET = Layout(
    [
        ("actual_tyre_compound", "B"),
        ("visual_tyre_compound", "B"),
        ("wear", "B"),
        ("available", "B"),
        ("recommended_session", "B"),
        ("life_span", "B"),
        ("usable_life", "B"),
        ("lap_delta_time", "h"),
        ("fitted", "B"),
    ]
)
NUM_TYRE_SETS = 20


# --------------------------------------------------------------------------
# Events (Paket 3): 4 Zeichen Code + Details (Union, max. 12 Bytes)
# --------------------------------------------------------------------------
EVENT_DETAILS_SIZE = 12
_COLLISION = {
    2025: Layout([("vehicle1_idx", "B"), ("vehicle2_idx", "B")]),
    2026: Layout([("vehicle1_idx", "B"), ("vehicle2_idx", "B"), ("severity", "B")]),
}
_EVENT_COMMON = {
    "FTLP": Layout([("vehicle_idx", "B"), ("lap_time", "f")]),
    "RTMT": Layout([("vehicle_idx", "B"), ("reason", "B")]),
    "DRSD": Layout([("reason", "B")]),
    "TMPT": Layout([("vehicle_idx", "B")]),
    "RCWN": Layout([("vehicle_idx", "B")]),
    "PENA": Layout(
        [
            ("penalty_type", "B"),
            ("infringement_type", "B"),
            ("vehicle_idx", "B"),
            ("other_vehicle_idx", "B"),
            ("time", "B"),
            ("lap_num", "B"),
            ("places_gained", "B"),
        ]
    ),
    "SPTP": Layout(
        [
            ("vehicle_idx", "B"),
            ("speed", "f"),
            ("is_overall_fastest_in_session", "B"),
            ("is_driver_fastest_in_session", "B"),
            ("fastest_vehicle_idx_in_session", "B"),
            ("fastest_speed_in_session", "f"),
        ]
    ),
    "STLG": Layout([("num_lights", "B")]),
    "DTSV": Layout([("vehicle_idx", "B")]),
    "SGSV": Layout([("vehicle_idx", "B"), ("stop_time", "f")]),
    "FLBK": Layout(
        [("flashback_frame_identifier", "I"), ("flashback_session_time", "f")]
    ),
    "BUTN": Layout([("button_status", "I")]),
    "OVTK": Layout(
        [("overtaking_vehicle_idx", "B"), ("being_overtaken_vehicle_idx", "B")]
    ),
    # safety_car_type: 0 keins, 1 voll, 2 virtuell, 3 Einfuehrungsrunde
    # event_type: 0 ausgerufen, 1 kommt rein, 2 ist drin, 3 Rennen laeuft weiter
    "SCAR": Layout([("safety_car_type", "B"), ("event_type", "B")]),
}
# Events ohne Details: SSTA, SEND, DRSE, CHQF, LGOT, RDFL
EVENT_DETAILS = {
    fmt: {**_EVENT_COMMON, "COLL": _COLLISION[fmt]} for fmt in SUPPORTED_FORMATS
}


# --------------------------------------------------------------------------
# Car Telemetry (Paket 6). Reifen-Arrays: hinten links, hinten rechts,
# vorne links, vorne rechts. 2026: Motortemperatur nur noch uint8.
# --------------------------------------------------------------------------
_CAR_TELEMETRY_HEAD = [
    ("speed", "H"),
    ("throttle", "f"),
    ("steer", "f"),
    ("brake", "f"),
    ("clutch", "B"),
    ("gear", "b"),
    ("engine_rpm", "H"),
    ("drs", "B"),
    ("rev_lights_percent", "B"),
    ("rev_lights_bit_value", "H"),
    ("brakes_temperature", "4H"),
    ("tyres_surface_temperature", "4B"),
    ("tyres_inner_temperature", "4B"),
]
_CAR_TELEMETRY_TAIL = [("tyres_pressure", "4f"), ("surface_type", "4B")]
CAR_TELEMETRY_CAR = {
    2025: Layout(_CAR_TELEMETRY_HEAD + [("engine_temperature", "H")] + _CAR_TELEMETRY_TAIL),
    2026: Layout(_CAR_TELEMETRY_HEAD + [("engine_temperature", "B")] + _CAR_TELEMETRY_TAIL),
}
CAR_TELEMETRY_TAIL = Layout(
    [("mfd_panel_index", "B"), ("mfd_panel_index_secondary_player", "B"), ("suggested_gear", "b")]
)


# --------------------------------------------------------------------------
# Strukturen, die nur fuer den Groessen-Test und den Simulator gebraucht
# werden (Inhalt wird im Betrieb nicht ausgewertet, nur weitergeleitet).
# --------------------------------------------------------------------------
CAR_MOTION_SIZE = {2025: 60, 2026: 54}
CAR_SETUP_SIZE = 50
CAR_TELEMETRY_SIZE = {fmt: CAR_TELEMETRY_CAR[fmt].size for fmt in (2025, 2026)}
LOBBY_INFO_SIZE = {2025: 42, 2026: 43}
TIME_TRIAL_SET_SIZE = {2025: 24, 2026: 25}
CAR_TELEMETRY_2_SIZE = 10
LAP_POSITIONS_MAX_LAPS = 50


def computed_packet_size(fmt: int, packet_id: int) -> int:
    """Berechnet die Paketgroesse aus den Strukturen (fuer den Selbsttest)."""
    n = NUM_CARS[fmt]
    h = HEADER_SIZE
    if packet_id == MOTION:
        return h + n * CAR_MOTION_SIZE[fmt]
    if packet_id == SESSION:
        size = (
            h
            + SESSION_PART1.size
            + MAX_MARSHAL_ZONES * MARSHAL_ZONE.size
            + SESSION_PART2.size
            + MAX_FORECAST_SAMPLES * WEATHER_FORECAST_SAMPLE.size
            + SESSION_PART3.size
        )
        if fmt == 2026:
            size += SESSION_TAIL_2026.size
        return size
    if packet_id == LAP_DATA:
        return h + n * LAP_DATA_CAR.size + LAP_DATA_TAIL.size
    if packet_id == EVENT:
        return h + 4 + EVENT_DETAILS_SIZE
    if packet_id == PARTICIPANTS:
        return h + 1 + n * PARTICIPANT[fmt].size
    if packet_id == CAR_SETUPS:
        return h + n * CAR_SETUP_SIZE + 4
    if packet_id == CAR_TELEMETRY:
        return h + n * CAR_TELEMETRY_SIZE[fmt] + 3
    if packet_id == CAR_STATUS:
        return h + n * CAR_STATUS_CAR[fmt].size
    if packet_id == FINAL_CLASSIFICATION:
        return h + 1 + n * FINAL_CLASSIFICATION_CAR.size
    if packet_id == LOBBY_INFO:
        return h + 1 + n * LOBBY_INFO_SIZE[fmt]
    if packet_id == CAR_DAMAGE:
        return h + n * CAR_DAMAGE_CAR.size
    if packet_id == SESSION_HISTORY:
        return (
            h
            + SESSION_HISTORY_HEAD.size
            + MAX_LAP_HISTORY * LAP_HISTORY.size
            + MAX_TYRE_STINTS * TYRE_STINT_HISTORY.size
        )
    if packet_id == TYRE_SETS:
        return h + 1 + NUM_TYRE_SETS * TYRE_SET.size + 1
    if packet_id == MOTION_EX:
        return 273
    if packet_id == TIME_TRIAL:
        return h + 3 * TIME_TRIAL_SET_SIZE[fmt]
    if packet_id == LAP_POSITIONS:
        return h + 2 + LAP_POSITIONS_MAX_LAPS * n
    if packet_id == CAR_TELEMETRY_2 and fmt == 2026:
        return h + n * CAR_TELEMETRY_2_SIZE
    raise KeyError((fmt, packet_id))
