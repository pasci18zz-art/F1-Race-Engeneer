"""Paketformat: Groessen laut Spec, Hin- und Rueckwandlung, Fehlerfaelle."""

import unittest

from renningenieur.telemetrie import encoder, parser, spec

HDR = {"session_uid": 123456789, "session_time": 12.5, "frame_identifier": 7,
       "player_car_index": 3}


class TestGroessen(unittest.TestCase):
    def test_header_hat_29_bytes(self):
        self.assertEqual(spec.HEADER_SIZE, 29)

    def test_strukturen_ergeben_die_paketgroessen_der_spec(self):
        for fmt in spec.SUPPORTED_FORMATS:
            for pid, groesse in spec.PACKET_SIZES[fmt].items():
                with self.subTest(format=fmt, paket=spec.PACKET_NAMES[pid]):
                    self.assertEqual(spec.computed_packet_size(fmt, pid), groesse)

    def test_bekannte_groessen_format_2025(self):
        # Zahlen aus dem offiziellen Dokument "Data Output from F1 25"
        erwartet = {0: 1349, 1: 753, 2: 1285, 3: 45, 4: 1284, 5: 1133, 6: 1352, 7: 1239,
                    8: 1042, 9: 954, 10: 1041, 11: 1460, 12: 231, 13: 273, 14: 101, 15: 1131}
        self.assertEqual(spec.PACKET_SIZES[2025], erwartet)

    def test_strukturgroessen_je_auto(self):
        self.assertEqual(spec.LAP_DATA_CAR.size, 57)
        self.assertEqual(spec.PARTICIPANT[2025].size, 57)
        self.assertEqual(spec.PARTICIPANT[2026].size, 60)
        self.assertEqual(spec.CAR_STATUS_CAR[2025].size, 55)
        self.assertEqual(spec.CAR_STATUS_CAR[2026].size, 59)
        self.assertEqual(spec.CAR_DAMAGE_CAR.size, 46)
        self.assertEqual(spec.FINAL_CLASSIFICATION_CAR.size, 46)
        self.assertEqual(spec.LAP_HISTORY.size, 14)
        self.assertEqual(spec.WEATHER_FORECAST_SAMPLE.size, 8)
        self.assertEqual(spec.MARSHAL_ZONE.size, 5)
        self.assertEqual(spec.TYRE_SET.size, 10)


class TestHinUndZurueck(unittest.TestCase):
    def test_lap_data(self):
        for fmt in spec.SUPPORTED_FORMATS:
            cars = [{"car_position": i + 1, "current_lap_num": 5, "pit_status": i % 3,
                     "delta_to_car_in_front_ms": 1234 + i, "delta_to_race_leader_ms": 61000 + i,
                     "last_lap_time_ms": 90123, "lap_distance": 1234.5, "result_status": 2}
                    for i in range(spec.NUM_CARS[fmt])]
            data = encoder.lap_data(fmt, HDR, cars)
            self.assertEqual(len(data), spec.PACKET_SIZES[fmt][spec.LAP_DATA])
            p = parser.parse(data)
            self.assertEqual(p["header"]["packet_format"], fmt)
            self.assertEqual(p["header"]["player_car_index"], 3)
            self.assertEqual(len(p["cars"]), spec.NUM_CARS[fmt])
            letztes = p["cars"][-1]
            n = spec.NUM_CARS[fmt] - 1
            self.assertEqual(letztes["car_position"], n + 1)
            self.assertEqual(letztes["delta_to_car_in_front_ms"], 1234 + n)
            self.assertEqual(letztes["delta_to_race_leader_ms"], 61000 + n)  # Minuten-Anteil
            self.assertAlmostEqual(letztes["lap_distance"], 1234.5)

    def test_session_mit_prognose(self):
        for fmt in spec.SUPPORTED_FORMATS:
            proben = [{"session_type": 15, "time_offset": m, "weather": 3, "rain_percentage": 70}
                      for m in (0, 5, 10)]
            data = encoder.session(fmt, HDR, {
                "weather": 2, "track_temperature": -3, "total_laps": 29, "track_length": 5793,
                "session_type": 15, "track_id": 11, "safety_car_status": 2,
                "weather_forecast_samples": proben, "season_link_identifier": 4_000_000_001,
                "pit_stop_window_ideal_lap": 12, "sector3_lap_distance_start": 4000.5})
            p = parser.parse(data)
            self.assertEqual(p["track_temperature"], -3)
            self.assertEqual(p["track_length"], 5793)
            self.assertEqual(p["safety_car_status"], 2)
            self.assertEqual(len(p["weather_forecast_samples"]), 3)
            self.assertEqual(p["weather_forecast_samples"][2]["time_offset"], 10)
            self.assertEqual(p["season_link_identifier"], 4_000_000_001)
            self.assertEqual(p["pit_stop_window_ideal_lap"], 12)
            self.assertAlmostEqual(p["sector3_lap_distance_start"], 4000.5)

    def test_participants(self):
        for fmt in spec.SUPPORTED_FORMATS:
            cars = [{"name": "HÜLKENBERG", "team_id": 9, "race_number": 27, "ai_controlled": 1,
                     "your_telemetry": 1, "livery_colours": [(1, 2, 3)]}] * 20
            p = parser.parse(encoder.participants(fmt, HDR, cars))
            self.assertEqual(p["num_active_cars"], 20)
            self.assertEqual(p["cars"][19]["name"], "HÜLKENBERG")
            self.assertEqual(p["cars"][19]["team_id"], 9)
            self.assertEqual(p["cars"][19]["livery_colours"], [(1, 2, 3)])
            self.assertEqual(p["cars"][20]["name"], "")

    def test_status_und_schaden(self):
        for fmt in spec.SUPPORTED_FORMATS:
            n = spec.NUM_CARS[fmt]
            status = [{"visual_tyre_compound": 17, "actual_tyre_compound": 19,
                       "tyres_age_laps": i, "fuel_remaining_laps": -0.5} for i in range(n)]
            p = parser.parse(encoder.car_status(fmt, HDR, status))
            self.assertEqual(p["cars"][n - 1]["tyres_age_laps"], n - 1)
            self.assertEqual(p["cars"][n - 1]["visual_tyre_compound"], 17)
            self.assertAlmostEqual(p["cars"][0]["fuel_remaining_laps"], -0.5)
            schaden = [{"tyres_wear": [1.5, 2.5, 3.5, 4.5], "rear_wing_damage": 40}] * n
            p = parser.parse(encoder.car_damage(fmt, HDR, schaden))
            self.assertEqual(p["cars"][n - 1]["tyres_wear"], [1.5, 2.5, 3.5, 4.5])
            self.assertEqual(p["cars"][n - 1]["rear_wing_damage"], 40)

    def test_events(self):
        for fmt in spec.SUPPORTED_FORMATS:
            p = parser.parse(encoder.event(fmt, HDR, "PENA", {
                "penalty_type": 4, "vehicle_idx": 7, "time": 5, "lap_num": 12}))
            self.assertEqual((p["code"], p["details"]["vehicle_idx"], p["details"]["time"]),
                             ("PENA", 7, 5))
            p = parser.parse(encoder.event(fmt, HDR, "FLBK", {"flashback_session_time": 99.5}))
            self.assertAlmostEqual(p["details"]["flashback_session_time"], 99.5)
            p = parser.parse(encoder.event(fmt, HDR, "RDFL"))
            self.assertEqual((p["code"], p["details"]), ("RDFL", {}))
            p = parser.parse(encoder.event(fmt, HDR, "FTLP", {"vehicle_idx": 2, "lap_time": 81.25}))
            self.assertAlmostEqual(p["details"]["lap_time"], 81.25)

    def test_session_history_und_klassifizierung(self):
        for fmt in spec.SUPPORTED_FORMATS:
            p = parser.parse(encoder.session_history(fmt, HDR, {
                "car_idx": 5,
                "laps": [{"lap_time_ms": 90000 + i, "sector1_ms": 61000, "valid": i != 1}
                         for i in range(3)],
                "tyre_stints": [{"end_lap": 2, "tyre_actual_compound": 19, "tyre_visual_compound": 17},
                                {"end_lap": 255, "tyre_actual_compound": 20, "tyre_visual_compound": 18}]}))
            self.assertEqual(p["car_idx"], 5)
            self.assertEqual([l["lap_time_ms"] for l in p["laps"]], [90000, 90001, 90002])
            self.assertEqual(p["laps"][0]["sector1_ms"], 61000)
            self.assertEqual([l["valid"] for l in p["laps"]], [True, False, True])
            self.assertEqual(p["tyre_stints"][1]["tyre_visual_compound"], 18)
            p = parser.parse(encoder.final_classification(fmt, HDR, [{
                "position": 1, "num_laps": 12, "points": 25, "best_lap_time_ms": 80123,
                "total_race_time": 1234.567, "num_tyre_stints": 2,
                "tyre_stints_visual": [16, 18], "tyre_stints_end_laps": [5, 12]}]))
            self.assertEqual(p["cars"][0]["points"], 25)
            self.assertAlmostEqual(p["cars"][0]["total_race_time"], 1234.567)
            self.assertEqual(p["cars"][0]["tyre_stints_visual"][:2], [16, 18])


class TestFehler(unittest.TestCase):
    def test_unbekanntes_format(self):
        data = bytearray(encoder.event(2025, HDR, "SSTA"))
        data[0:2] = (2024).to_bytes(2, "little")
        with self.assertRaises(parser.PaketFehler):
            parser.parse(bytes(data))

    def test_falsche_laenge(self):
        data = encoder.lap_data(2025, HDR, [])
        with self.assertRaises(parser.PaketFehler):
            parser.parse(data[:-1])
        # Ein 2025er-Paket mit 2026er-Kennung hat die falsche Laenge
        falsch = bytearray(data)
        falsch[0:2] = (2026).to_bytes(2, "little")
        with self.assertRaises(parser.PaketFehler):
            parser.parse(bytes(falsch))

    def test_zu_kurz(self):
        with self.assertRaises(parser.PaketFehler):
            parser.parse(b"\x00" * 10)

    def test_nicht_ausgewertete_pakete_geben_none(self):
        self.assertIsNone(parser.parse(encoder.leer(2025, spec.MOTION, HDR)))
        self.assertIsNone(parser.parse(encoder.leer(2026, spec.CAR_TELEMETRY_2, HDR)))


if __name__ == "__main__":
    unittest.main()
