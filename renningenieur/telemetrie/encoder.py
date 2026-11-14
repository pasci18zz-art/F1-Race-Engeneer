"""Baut gueltige UDP-Pakete aus Dictionaries (Gegenstueck zum Parser).

Wird nur vom Simulator und von den Tests benutzt.
"""

from __future__ import annotations

from . import spec


def header(fmt: int, packet_id: int, **werte) -> bytes:
    daten = {
        "packet_format": fmt,
        "game_year": 25,
        "game_major_version": 1,
        "game_minor_version": 0,
        "packet_version": 1,
        "packet_id": packet_id,
        "secondary_player_car_index": 255,
    }
    daten.update(werte)
    return spec.HEADER.pack(daten)


def _pad(data: bytes, fmt: int, packet_id: int) -> bytes:
    size = spec.PACKET_SIZES[fmt][packet_id]
    if len(data) > size:
        raise ValueError(f"Paket {packet_id} zu lang: {len(data)} > {size}")
    return data + b"\x00" * (size - len(data))


def _cars(layout: spec.Layout, cars: list[dict], fmt: int) -> bytes:
    n = spec.NUM_CARS[fmt]
    cars = list(cars)[:n]
    return b"".join(layout.pack(c) for c in cars) + layout.pack() * (n - len(cars))


def session(fmt: int, hdr: dict, s: dict) -> bytes:
    zonen = list(s.get("marshal_zones", ()))
    samples = list(s.get("weather_forecast_samples", ()))
    s = dict(s)
    s.setdefault("num_marshal_zones", len(zonen))
    s.setdefault("num_weather_forecast_samples", len(samples))
    out = header(fmt, spec.SESSION, **hdr) + spec.SESSION_PART1.pack(s)
    for i in range(spec.MAX_MARSHAL_ZONES):
        out += spec.MARSHAL_ZONE.pack(zonen[i] if i < len(zonen) else None)
    out += spec.SESSION_PART2.pack(s)
    for i in range(spec.MAX_FORECAST_SAMPLES):
        out += spec.WEATHER_FORECAST_SAMPLE.pack(samples[i] if i < len(samples) else None)
    out += spec.SESSION_PART3.pack(s)
    return _pad(out, fmt, spec.SESSION)


def lap_data(fmt: int, hdr: dict, cars: list[dict]) -> bytes:
    fertig = []
    for c in cars:
        c = dict(c)
        for kurz in ("delta_to_car_in_front", "delta_to_race_leader"):
            ms = int(c.pop(kurz + "_ms", 0))
            c[kurz + "_minutes_part"] = min(ms // 60000, 255)
            c[kurz + "_ms_part"] = ms % 60000
        fertig.append(c)
    out = header(fmt, spec.LAP_DATA, **hdr) + _cars(spec.LAP_DATA_CAR, fertig, fmt)
    out += spec.LAP_DATA_TAIL.pack({"time_trial_pb_car_idx": 255, "time_trial_rival_car_idx": 255})
    return _pad(out, fmt, spec.LAP_DATA)


def event(fmt: int, hdr: dict, code: str, details: dict | None = None) -> bytes:
    out = header(fmt, spec.EVENT, **hdr) + code.encode("ascii")
    layout = spec.EVENT_DETAILS[fmt].get(code)
    if layout:
        out += layout.pack(details)
    return _pad(out, fmt, spec.EVENT)


def participants(fmt: int, hdr: dict, cars: list[dict], num_active: int | None = None) -> bytes:
    fertig = []
    for c in cars:
        c = dict(c)
        farben = c.get("livery_colours", [])
        c["num_colours"] = len(farben)
        c["livery_colours"] = [wert for farbe in farben for wert in farbe]
        fertig.append(c)
    out = header(fmt, spec.PARTICIPANTS, **hdr)
    out += bytes([len(cars) if num_active is None else num_active])
    out += _cars(spec.PARTICIPANT[fmt], fertig, fmt)
    return _pad(out, fmt, spec.PARTICIPANTS)


def car_status(fmt: int, hdr: dict, cars: list[dict]) -> bytes:
    out = header(fmt, spec.CAR_STATUS, **hdr) + _cars(spec.CAR_STATUS_CAR[fmt], cars, fmt)
    return _pad(out, fmt, spec.CAR_STATUS)


def car_telemetry(fmt: int, hdr: dict, cars: list[dict]) -> bytes:
    out = header(fmt, spec.CAR_TELEMETRY, **hdr) + _cars(spec.CAR_TELEMETRY_CAR[fmt], cars, fmt)
    out += spec.CAR_TELEMETRY_TAIL.pack({"mfd_panel_index": 255,
                                         "mfd_panel_index_secondary_player": 255})
    return _pad(out, fmt, spec.CAR_TELEMETRY)


def tyre_sets(fmt: int, hdr: dict, car_idx: int, sets: list[dict], fitted_idx: int) -> bytes:
    out = header(fmt, spec.TYRE_SETS, **hdr) + bytes([car_idx])
    for i in range(spec.NUM_TYRE_SETS):
        out += spec.TYRE_SET.pack(sets[i] if i < len(sets) else None)
    out += bytes([fitted_idx])
    return _pad(out, fmt, spec.TYRE_SETS)


def car_damage(fmt: int, hdr: dict, cars: list[dict]) -> bytes:
    out = header(fmt, spec.CAR_DAMAGE, **hdr) + _cars(spec.CAR_DAMAGE_CAR, cars, fmt)
    return _pad(out, fmt, spec.CAR_DAMAGE)


def final_classification(fmt: int, hdr: dict, cars: list[dict]) -> bytes:
    out = header(fmt, spec.FINAL_CLASSIFICATION, **hdr) + bytes([len(cars)])
    out += _cars(spec.FINAL_CLASSIFICATION_CAR, cars, fmt)
    return _pad(out, fmt, spec.FINAL_CLASSIFICATION)


def session_history(fmt: int, hdr: dict, h: dict) -> bytes:
    laps = []
    for lap in h.get("laps", ()):
        lap = dict(lap)
        for i in (1, 2, 3):
            ms = int(lap.pop(f"sector{i}_ms", 0))
            lap[f"sector{i}_time_minutes_part"] = ms // 60000
            lap[f"sector{i}_time_ms_part"] = ms % 60000
        if "valid" in lap:
            lap["lap_valid_bit_flags"] = 0x0F if lap.pop("valid") else 0x0E
        laps.append(lap)
    laps = laps[: spec.MAX_LAP_HISTORY]
    stints = list(h.get("tyre_stints", ()))[: spec.MAX_TYRE_STINTS]
    h = dict(h)
    h["num_laps"] = len(laps)
    h["num_tyre_stints"] = len(stints)
    out = header(fmt, spec.SESSION_HISTORY, **hdr) + spec.SESSION_HISTORY_HEAD.pack(h)
    for i in range(spec.MAX_LAP_HISTORY):
        out += spec.LAP_HISTORY.pack(laps[i] if i < len(laps) else None)
    for i in range(spec.MAX_TYRE_STINTS):
        out += spec.TYRE_STINT_HISTORY.pack(stints[i] if i < len(stints) else None)
    return _pad(out, fmt, spec.SESSION_HISTORY)


def leer(fmt: int, packet_id: int, hdr: dict) -> bytes:
    """Paket mit gueltigem Header und Nullen (z. B. Motion fuer Relay-Tests)."""
    return _pad(header(fmt, packet_id, **hdr), fmt, packet_id)
