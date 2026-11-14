"""Zerlegt rohe UDP-Pakete in einfache Python-Dictionaries.

Es werden nur die Pakete ausgewertet, die der Renningenieur braucht. Alles
andere (Motion, Telemetrie, Setups, ...) wird nur weitergeleitet.

    paket = parse(daten)
    if paket: paket["header"]["packet_id"], paket["cars"], ...
"""

from __future__ import annotations

from . import spec

AUSGEWERTETE_PAKETE = frozenset(
    {
        spec.SESSION,
        spec.LAP_DATA,
        spec.EVENT,
        spec.PARTICIPANTS,
        spec.CAR_TELEMETRY,
        spec.CAR_STATUS,
        spec.FINAL_CLASSIFICATION,
        spec.CAR_DAMAGE,
        spec.SESSION_HISTORY,
        spec.TYRE_SETS,
    }
)


class PaketFehler(ValueError):
    """Paket passt nicht zur Spec (falsches Format oder falsche Laenge)."""


def parse_header(data: bytes) -> dict:
    if len(data) < spec.HEADER_SIZE:
        raise PaketFehler(f"Paket zu kurz ({len(data)} Bytes)")
    return spec.HEADER.unpack_from(data, 0)


def parse(data: bytes, nur_header: bool = False) -> dict | None:
    """Gibt das ausgewertete Paket zurueck oder None, wenn es nicht gebraucht wird.

    Wirft PaketFehler bei unbekanntem Paketformat oder falscher Laenge.
    """
    header = parse_header(data)
    fmt = header["packet_format"]
    if fmt not in spec.SUPPORTED_FORMATS:
        raise PaketFehler(
            f"Unbekanntes UDP-Format {fmt}. Unterstützt: 2025 und 2026 "
            "(im Spiel unter Einstellungen > Telemetrie > UDP-Format)."
        )
    pid = header["packet_id"]
    erwartet = spec.PACKET_SIZES[fmt].get(pid)
    if erwartet is None:
        return None  # unbekannte Paket-ID: ignorieren, aber weiterleiten
    if len(data) != erwartet:
        raise PaketFehler(
            f"Paket {spec.PACKET_NAMES.get(pid, pid)} (Format {fmt}) hat "
            f"{len(data)} statt {erwartet} Bytes"
        )
    if nur_header or pid not in AUSGEWERTETE_PAKETE:
        return None
    out = _PARSER[pid](data, fmt)
    out["header"] = header
    return out


# --------------------------------------------------------------------------
def _cars(data: bytes, offset: int, layout: spec.Layout, fmt: int) -> list[dict]:
    return [
        layout.unpack_from(data, offset + i * layout.size)
        for i in range(spec.NUM_CARS[fmt])
    ]


def _parse_session(data: bytes, fmt: int) -> dict:
    off = spec.HEADER_SIZE
    out = spec.SESSION_PART1.unpack_from(data, off)
    off += spec.SESSION_PART1.size
    zonen = []
    for i in range(spec.MAX_MARSHAL_ZONES):
        zonen.append(spec.MARSHAL_ZONE.unpack_from(data, off))
        off += spec.MARSHAL_ZONE.size
    out["marshal_zones"] = zonen[: min(out["num_marshal_zones"], len(zonen))]
    out.update(spec.SESSION_PART2.unpack_from(data, off))
    off += spec.SESSION_PART2.size
    n = min(out["num_weather_forecast_samples"], spec.MAX_FORECAST_SAMPLES)
    out["weather_forecast_samples"] = [
        spec.WEATHER_FORECAST_SAMPLE.unpack_from(
            data, off + i * spec.WEATHER_FORECAST_SAMPLE.size
        )
        for i in range(n)
    ]
    off += spec.MAX_FORECAST_SAMPLES * spec.WEATHER_FORECAST_SAMPLE.size
    out.update(spec.SESSION_PART3.unpack_from(data, off))
    return out


def _parse_lap_data(data: bytes, fmt: int) -> dict:
    cars = _cars(data, spec.HEADER_SIZE, spec.LAP_DATA_CAR, fmt)
    for c in cars:
        c["delta_to_car_in_front_ms"] = (
            c["delta_to_car_in_front_minutes_part"] * 60000
            + c["delta_to_car_in_front_ms_part"]
        )
        c["delta_to_race_leader_ms"] = (
            c["delta_to_race_leader_minutes_part"] * 60000
            + c["delta_to_race_leader_ms_part"]
        )
    return {"cars": cars}


def _parse_event(data: bytes, fmt: int) -> dict:
    off = spec.HEADER_SIZE
    code = data[off : off + 4].decode("ascii", errors="replace")
    layout = spec.EVENT_DETAILS[fmt].get(code)
    details = layout.unpack_from(data, off + 4) if layout else {}
    return {"code": code, "details": details}


def _parse_participants(data: bytes, fmt: int) -> dict:
    off = spec.HEADER_SIZE
    num_active = data[off]
    cars = _cars(data, off + 1, spec.PARTICIPANT[fmt], fmt)
    for c in cars:
        c["name"] = c["name"].split(b"\x00", 1)[0].decode("utf-8", errors="replace")
        farben = c.pop("livery_colours")
        c["livery_colours"] = [
            tuple(farben[i * 3 : i * 3 + 3]) for i in range(min(c["num_colours"], 4))
        ]
    return {"num_active_cars": num_active, "cars": cars}


def _parse_car_telemetry(data: bytes, fmt: int) -> dict:
    return {"cars": _cars(data, spec.HEADER_SIZE, spec.CAR_TELEMETRY_CAR[fmt], fmt)}


def _parse_car_status(data: bytes, fmt: int) -> dict:
    return {"cars": _cars(data, spec.HEADER_SIZE, spec.CAR_STATUS_CAR[fmt], fmt)}


def _parse_car_damage(data: bytes, fmt: int) -> dict:
    return {"cars": _cars(data, spec.HEADER_SIZE, spec.CAR_DAMAGE_CAR, fmt)}


def _parse_final_classification(data: bytes, fmt: int) -> dict:
    off = spec.HEADER_SIZE
    num_cars = data[off]
    cars = _cars(data, off + 1, spec.FINAL_CLASSIFICATION_CAR, fmt)
    return {"num_cars": num_cars, "cars": cars}


def _parse_session_history(data: bytes, fmt: int) -> dict:
    off = spec.HEADER_SIZE
    out = spec.SESSION_HISTORY_HEAD.unpack_from(data, off)
    off += spec.SESSION_HISTORY_HEAD.size
    laps = []
    for i in range(min(out["num_laps"], spec.MAX_LAP_HISTORY)):
        lap = spec.LAP_HISTORY.unpack_from(data, off + i * spec.LAP_HISTORY.size)
        lap["sector1_ms"] = (
            lap["sector1_time_minutes_part"] * 60000 + lap["sector1_time_ms_part"]
        )
        lap["sector2_ms"] = (
            lap["sector2_time_minutes_part"] * 60000 + lap["sector2_time_ms_part"]
        )
        lap["sector3_ms"] = (
            lap["sector3_time_minutes_part"] * 60000 + lap["sector3_time_ms_part"]
        )
        lap["valid"] = bool(lap["lap_valid_bit_flags"] & 0x01)
        laps.append(lap)
    off += spec.MAX_LAP_HISTORY * spec.LAP_HISTORY.size
    stints = [
        spec.TYRE_STINT_HISTORY.unpack_from(data, off + i * spec.TYRE_STINT_HISTORY.size)
        for i in range(min(out["num_tyre_stints"], spec.MAX_TYRE_STINTS))
    ]
    out["laps"] = laps
    out["tyre_stints"] = stints
    return out


def _parse_tyre_sets(data: bytes, fmt: int) -> dict:
    off = spec.HEADER_SIZE
    car_idx = data[off]
    off += 1
    sets = [
        spec.TYRE_SET.unpack_from(data, off + i * spec.TYRE_SET.size)
        for i in range(spec.NUM_TYRE_SETS)
    ]
    fitted_idx = data[off + spec.NUM_TYRE_SETS * spec.TYRE_SET.size]
    return {"car_idx": car_idx, "tyre_sets": sets, "fitted_idx": fitted_idx}


_PARSER = {
    spec.SESSION: _parse_session,
    spec.LAP_DATA: _parse_lap_data,
    spec.EVENT: _parse_event,
    spec.PARTICIPANTS: _parse_participants,
    spec.CAR_TELEMETRY: _parse_car_telemetry,
    spec.CAR_STATUS: _parse_car_status,
    spec.FINAL_CLASSIFICATION: _parse_final_classification,
    spec.CAR_DAMAGE: _parse_car_damage,
    spec.SESSION_HISTORY: _parse_session_history,
    spec.TYRE_SETS: _parse_tyre_sets,
}
