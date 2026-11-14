"""Automatische Warnungen.

Jede Regel ist eine eigene Methode. Schwellen stehen in config.toml unter
[warnungen], die Saetze in texte.toml unter [warnung].

Grundsatz: Es wird nur etwas gesagt, wenn es etwas zu sagen gibt. Es gibt
keine Fuellsaetze wie "keine Probleme".

Alle Zeitabstaende (Pausen, Verzoegerungen) rechnen mit der Session-Zeit
des Spiels. Dadurch funktionieren die Regeln auch im Zeitraffer des
Simulators und pausieren, wenn das Spiel pausiert.
"""

from __future__ import annotations

import logging

from . import formulierung as f
from .auswertung import Ereignis
from .config import Texte
from .sprache.funk import HOCH, NORMAL, Funk
from .telemetrie import konstanten as k
from .zustand import Auto, Rennzustand

log = logging.getLogger(__name__)


class Regeln:
    def __init__(self, zustand: Rennzustand, cfg: dict, texte: Texte, funk: Funk):
        self.z = zustand
        self.cfg = cfg  # Abschnitt [warnungen]
        self.t = texte
        self.funk = funk
        self._neue_session()

    def _neue_session(self) -> None:
        self._verschleiss_stufe = 0  # Anzahl bereits gemeldeter Schwellen
        self._regen_gemeldet: float | None = None  # zuletzt gemeldete Restminuten
        self._trocken_gemeldet: float | None = None
        self._hinten_scharf = True
        self._hinten_idx = -1
        self._hinten_zeit = -1e9
        self._box_gemeldet: set[int] = set()  # Autos, deren Einfahrt angesagt wurde
        self._geplant: list[tuple[float, str, dict]] = []  # (Zeit, Aktion, Daten)
        self._restart_gemeldet = False
        self._rennstart_gemeldet = False
        self._letzte_runde_gemeldet = False
        self._ziel_gemeldet = False
        self._letzte_gelb = -1e9

    # ------------------------------------------------------------------
    def ereignis(self, e: Ereignis) -> None:
        """Wird fuer jedes Ereignis der Auswertung aufgerufen."""
        methode = getattr(self, "_bei_" + e.typ, None)
        if methode:
            with self.z.lock:
                methode(e)

    def _sag(self, schluessel: str, prioritaet: int = NORMAL, **werte) -> None:
        self.funk.sagen(self.t.sag(schluessel, **werte), prioritaet)

    # --- Session ------------------------------------------------------
    def _bei_session_start(self, e: Ereignis) -> None:
        self._neue_session()

    def _bei_flashback(self, e: Ereignis) -> None:
        # Nach einer Rueckblende alles neu bewerten
        self._letzte_gelb = -1e9
        self._geplant.clear()
        self._box_gemeldet.clear()
        self._hinten_scharf = True
        self._hinten_zeit = -1e9
        self._regen_gemeldet = None
        self._trocken_gemeldet = None
        self._letzte_runde_gemeldet = False

    def _bei_paket_fehler(self, e: Ereignis) -> None:
        self._sag("warnung.format_fehler", HOCH)

    # --- Takt: wird nach jedem Lap-Data-Paket aufgerufen ----------------
    def _bei_tick(self, e: Ereignis) -> None:
        z = self.z
        ich = z.spieler
        if ich is None or z.pausiert:
            return
        self._geplantes_ausfuehren()
        self._regel_regen()
        if not z.ist_rennen:
            return
        self._regel_rennstart(ich)
        if not ich.im_rennen or z.rote_flagge:
            return
        self._regel_reifenverschleiss(ich)
        self._regel_abstand_hinten(ich)
        self._regel_letzte_runde(ich)

    def _planen(self, verzoegerung: float, aktion: str, **daten) -> None:
        self._geplant.append((self.z.session_time + verzoegerung, aktion, daten))

    def _geplantes_ausfuehren(self) -> None:
        jetzt = self.z.session_time
        faellig = [g for g in self._geplant if g[0] <= jetzt]
        self._geplant = [g for g in self._geplant if g[0] > jetzt]
        for _, aktion, daten in faellig:
            getattr(self, "_aktion_" + aktion)(**daten)

    # --- Rennstart ----------------------------------------------------
    def _regel_rennstart(self, ich: Auto) -> None:
        z = self.z
        if self._rennstart_gemeldet or not self.cfg.get("rennstart_info", True):
            return
        if (z.rennen_gestartet or ich.runde > 1 or z.rote_flaggen_anzahl
                or ich.gesamtdistanz > 100):
            self._rennstart_gemeldet = True  # mitten im Rennen gestartet: nichts sagen
            return
        if not ich.status_bekannt or not z.runden_gesamt:
            return
        self._rennstart_gemeldet = True
        platz = ich.startplatz or ich.position
        self._sag(
            "warnung.rennstart",
            HOCH,
            strecke=z.strecke,
            runden=z.runden_gesamt,
            platz=platz,
            reifen_beschreibung=f.reifenbeschreibung(self.t, ich),
        )
        regen = z.minuten_bis_regen()
        if regen and not k.ist_regen(z.wetter):
            self._regen_ansagen(*regen)

    # --- Reifenverschleiss --------------------------------------------
    def _regel_reifenverschleiss(self, ich: Auto) -> None:
        schwellen = sorted(self.cfg.get("reifenverschleiss", []))
        if not schwellen or not ich.schaden_bekannt:
            return
        wert, position = f.staerkster_verschleiss(ich)
        stufe = sum(1 for s in schwellen if wert >= s)
        if stufe > self._verschleiss_stufe:
            self._sag("warnung.reifenverschleiss", prozent=int(wert), reifen_position=position)
        # Sinkt der Verschleiss (frische Reifen), zaehlen die Schwellen neu
        self._verschleiss_stufe = stufe

    # --- Regen --------------------------------------------------------
    def _regel_regen(self) -> None:
        z = self.z
        if not z.session_bekannt:
            return
        if k.ist_regen(z.wetter):
            self._regen_gemeldet = None
            self._regel_abtrocknen()
            return
        self._trocken_gemeldet = None
        regen = z.minuten_bis_regen()
        if regen is None:
            self._regen_gemeldet = None  # Prognose hat sich geaendert
            return
        minuten, probe = regen
        schwellen = sorted(self.cfg.get("regen_minuten", []), reverse=True)
        if not schwellen or minuten > schwellen[0]:
            return
        # Naechste Schwelle, die mit dieser Restzeit erreicht ist
        erreicht = min(s for s in schwellen if minuten <= s)
        if self._regen_gemeldet is not None and erreicht >= self._regen_gemeldet:
            return
        self._regen_gemeldet = erreicht
        self._regen_ansagen(minuten, probe)

    def _regen_ansagen(self, minuten: int, probe: dict) -> None:
        if self._regen_gemeldet is None:
            self._regen_gemeldet = minuten
        art = f.wetter_art(probe["weather"])
        if minuten <= 0:
            self._sag("warnung.regen_gleich", HOCH, art=art, prozent=probe["rain_percentage"])
        else:
            self._sag("warnung.regen_kommt", HOCH, minuten=minuten, art=art,
                      prozent=probe["rain_percentage"])

    def _regel_abtrocknen(self) -> None:
        z = self.z
        if not self.cfg.get("abtrocknen", True):
            return
        trocken = z.minuten_bis_trocken()
        if trocken is None:
            self._trocken_gemeldet = None
            return
        minuten, _ = trocken
        schwellen = sorted(self.cfg.get("regen_minuten", []), reverse=True)
        if minuten <= 0 or not schwellen or minuten > schwellen[0]:
            return
        erreicht = min(s for s in schwellen if minuten <= s)
        if self._trocken_gemeldet is not None and erreicht >= self._trocken_gemeldet:
            return
        self._trocken_gemeldet = erreicht
        self._sag("warnung.abtrocknen", minuten=minuten)

    def _bei_wetter_wechsel(self, e: Ereignis) -> None:
        alt, neu = e.daten["alt"], e.daten["neu"]
        art = f.wetter_art(neu)
        if k.ist_regen(neu) and not k.ist_regen(alt):
            self._sag("warnung.regen_beginnt", HOCH, art=art)
        elif not k.ist_regen(neu) and k.ist_regen(alt):
            self._sag("warnung.regen_vorbei", HOCH)
        elif k.ist_regen(neu) and neu > alt:
            self._sag("warnung.regen_staerker", art=art)
        elif k.ist_regen(neu) and neu < alt:
            self._sag("warnung.regen_schwaecher", art=art)
        # Wechsel zwischen klar/bewoelkt/bedeckt ist keine Meldung wert

    # --- Hintermann ---------------------------------------------------
    def _regel_abstand_hinten(self, ich: Auto) -> None:
        z, cfg = self.z, self.cfg
        grenze = cfg.get("abstand_hinten", 1.0)
        if not grenze or ich.in_box or z.safety_car != k.SC_KEINS:
            return
        if not z.rennen_gestartet and ich.runde <= 1 and z.session_time < 30:
            return
        if ich.runde < cfg.get("abstand_hinten_ab_runde", 2):
            return
        hinten = z.hintermann(ich)
        if hinten is None or not hinten.im_rennen or hinten.in_box:
            return
        abstand = hinten.delta_vorne_ms / 1000.0
        if abstand <= 0:
            return  # keine Daten
        if hinten.idx != self._hinten_idx:
            self._hinten_idx = hinten.idx
            self._hinten_scharf = True
        if abstand > cfg.get("abstand_hinten_entwarnung", 1.5):
            self._hinten_scharf = True
            return
        if abstand >= grenze or not self._hinten_scharf:
            return
        if z.session_time - self._hinten_zeit < cfg.get("abstand_hinten_pause", 45):
            return
        self._hinten_scharf = False
        self._hinten_zeit = z.session_time
        self._sag("warnung.abstand_hinten", name=hinten.anzeigename,
                  abstand=f.zeitspanne(self.t, hinten.delta_vorne_ms))

    # --- Letzte Runde / Ziel -------------------------------------------
    def _regel_letzte_runde(self, ich: Auto) -> None:
        z = self.z
        if self._letzte_runde_gemeldet or not self.cfg.get("letzte_runde", True):
            return
        if z.runden_gesamt > 1 and ich.runde == z.runden_gesamt:
            self._letzte_runde_gemeldet = True
            self._sag("warnung.letzte_runde")

    def _bei_klassifizierung(self, e: Ereignis) -> None:
        z = self.z
        if self._ziel_gemeldet or not z.ist_rennen or not z.klassifizierung:
            return
        for eintrag in z.klassifizierung:
            if eintrag["idx"] == z.spieler_idx:
                self._ziel_gemeldet = True
                self._sag("warnung.ziel", platz=eintrag["position"])

    # --- Boxenstopps der Gegner ----------------------------------------
    def _bei_box_einfahrt(self, e: Ereignis) -> None:
        # Kurz warten: Bei einer roten Flagge stehen ploetzlich alle in der
        # Boxengasse. Kommt die Flagge innerhalb dieser Sekunde, verfaellt die Ansage.
        if e.daten["idx"] != self.z.spieler_idx and self.cfg.get("box_gegner", True):
            self._planen(0.8, "box_ansage", idx=e.daten["idx"])

    def _aktion_box_ansage(self, idx: int) -> None:
        z, cfg = self.z, self.cfg
        ich = z.spieler
        auto = z.autos[idx]
        if ich is None or not ich.im_rennen or z.rote_flagge or not auto.in_box:
            return
        versatz = auto.position - ich.position
        if abs(versatz) > cfg.get("box_positionen", 1) or versatz == 0:
            return
        abstand_ms = abs(z.rueckstand_ms(auto, ich))
        max_abstand = cfg.get("box_max_abstand", 0)
        if max_abstand and abstand_ms > max_abstand * 1000:
            return
        werte = dict(name=auto.anzeigename, platz=auto.position,
                     abstand=f.zeitspanne(self.t, abstand_ms))
        if versatz == -1:
            self._sag("warnung.box_vorne", HOCH, **werte)
        elif versatz == 1:
            self._sag("warnung.box_hinten", HOCH, **werte)
        elif versatz < 0:
            self._sag("warnung.box_weiter_vorne", **werte)
        else:
            self._sag("warnung.box_weiter_hinten", **werte)
        self._box_gemeldet.add(auto.idx)

    def _bei_box_ausfahrt(self, e: Ereignis) -> None:
        z = self.z
        idx = e.daten["idx"]
        if idx == z.spieler_idx:
            # Zwei Sekunden warten, bis Position und Abstaende stimmen
            self._planen(2.0, "eigener_stopp")
        elif idx in self._box_gemeldet and self.cfg.get("box_ausfahrt", True):
            self._box_gemeldet.discard(idx)
            self._planen(2.0, "gegner_raus", idx=idx)

    def _aktion_gegner_raus(self, idx: int) -> None:
        z = self.z
        ich, auto = z.spieler, z.autos[idx]
        if ich is None or not auto.im_rennen or not ich.im_rennen:
            return
        abstand = f.abstand(self.t, z, ich, auto)
        if abstand is None:
            return
        schluessel = "box_raus_vor_dir" if auto.position < ich.position else "box_raus_hinter_dir"
        self._sag("warnung." + schluessel, name=auto.anzeigename, reifen=auto.reifen_name,
                  platz=auto.position, abstand=abstand)

    def _aktion_eigener_stopp(self) -> None:
        z = self.z
        ich = z.spieler
        if ich is None or not ich.im_rennen:
            return
        teile = [self.t.sag("warnung.eigener_stopp", platz=ich.position)]
        vorne, hinten = z.vordermann(ich), z.hintermann(ich)
        if vorne and vorne.im_rennen:
            abstand = f.abstand(self.t, z, ich, vorne)
            if abstand:
                teile.append(self.t.sag("warnung.eigener_stopp_vorne",
                                        vorne_name=vorne.anzeigename, vorne_abstand=abstand))
        if hinten and hinten.im_rennen:
            abstand = f.abstand(self.t, z, hinten, ich)
            if abstand:
                teile.append(self.t.sag("warnung.eigener_stopp_hinten",
                                        hinten_name=hinten.anzeigename, hinten_abstand=abstand))
        self.funk.sagen(" ".join(t for t in teile if t), NORMAL)
        # Frische Reifen: Hintermann-Warnung sofort wieder scharf
        self._hinten_scharf = True

    # --- Safety Car ---------------------------------------------------
    def _bei_safety_car(self, e: Ereignis) -> None:
        if not self.cfg.get("safety_car", True) or not self.z.ist_rennen:
            return
        alt, neu = e.daten["alt"], e.daten["neu"]
        if neu == k.SC_VOLL:
            self._sag("warnung.safety_car", HOCH)
        elif neu == k.SC_VIRTUELL:
            self._sag("warnung.virtuelles_safety_car", HOCH)
        elif neu == k.SC_KEINS and alt == k.SC_VOLL:
            self._sag("warnung.safety_car_ende", HOCH)
        elif neu == k.SC_KEINS and alt == k.SC_VIRTUELL:
            self._sag("warnung.virtuelles_safety_car_ende", HOCH)
        elif neu == k.SC_FORMATION and self.z.rote_flagge:
            self._restart_ansage()
        # Nach einer Neutralisation liegt das Feld dicht zusammen: die
        # Hintermann-Warnung macht erst nach der ueblichen Pause wieder Sinn.
        self._hinten_scharf = True
        self._hinten_zeit = self.z.session_time

    def _bei_safety_car_event(self, e: Ereignis) -> None:
        if not self.cfg.get("safety_car", True) or not self.z.ist_rennen:
            return
        # event_typ 1 = Safety Car kommt rein (nur beim echten Safety Car)
        if e.daten["event_typ"] == 1 and e.daten["sc_typ"] == k.SC_VOLL:
            self._sag("warnung.safety_car_kommt_rein", HOCH)

    # --- Rote Flagge und Restart ---------------------------------------
    def _bei_rote_flagge(self, e: Ereignis) -> None:
        z = self.z
        self._restart_gemeldet = False
        self._geplant.clear()
        if not self.cfg.get("rote_flagge", True):
            return
        ich = z.spieler
        if ich is None:
            return
        teile = [self.t.sag("warnung.rote_flagge", platz=ich.position)]
        if ich.status_bekannt and ich.schaden_bekannt:
            teile.append(self.t.sag(
                "warnung.rote_flagge_reifen",
                reifen_beschreibung=f.reifenbeschreibung(self.t, ich),
                prozent=int(ich.max_verschleiss),
            ))
        self.funk.sagen(" ".join(t for t in teile if t), HOCH)

    def _bei_ampel(self, e: Ereignis) -> None:
        # Erste Ampel nach roter Flagge: jetzt stehen Startplatz und Reifen fest
        if self.z.rote_flagge:
            self._restart_ansage()

    def _bei_restart(self, e: Ereignis) -> None:
        self._restart_ansage()  # falls vor dem Restart keine Ampel gemeldet wurde
        # Nach dem Restart alles neu bewerten (neue Reifen, neue Abstaende)
        self._hinten_scharf = True
        self._hinten_zeit = self.z.session_time  # kurze Ruhe direkt nach dem Start
        self._verschleiss_stufe = 0
        self._box_gemeldet.clear()

    def _restart_ansage(self) -> None:
        """Lagebericht zum Restart: nur Fakten, die jetzt wichtig sind."""
        z = self.z
        if self._restart_gemeldet or not self.cfg.get("rote_flagge", True):
            return
        ich = z.spieler
        if ich is None or not ich.gueltig:
            return
        self._restart_gemeldet = True
        teile = [self.t.sag("warnung.restart", platz=ich.position,
                            reifen_beschreibung=f.reifenbeschreibung(self.t, ich))]
        vorne, hinten = z.vordermann(ich), z.hintermann(ich)
        if vorne and vorne.im_rennen and vorne.status_bekannt:
            teile.append(self.t.sag("warnung.restart_vorne", name=vorne.anzeigename,
                                    reifen_beschreibung=f.reifenbeschreibung(self.t, vorne)))
        elif ich.position == 1:
            teile.append(self.t.sag("warnung.restart_fuehrung"))
        if hinten and hinten.im_rennen and hinten.status_bekannt:
            teile.append(self.t.sag("warnung.restart_hinten", name=hinten.anzeigename,
                                    reifen_beschreibung=f.reifenbeschreibung(self.t, hinten)))
        self.funk.sagen(" ".join(t for t in teile if t), HOCH)
        regen = z.minuten_bis_regen()
        if regen and not k.ist_regen(z.wetter):
            schwellen = self.cfg.get("regen_minuten", [])
            if schwellen and regen[0] <= max(schwellen):
                self._regen_gemeldet = None
                self._regen_ansagen(*regen)

    # --- Ausfaelle ----------------------------------------------------
    def _bei_ausfall(self, e: Ereignis) -> None:
        z = self.z
        if not self.cfg.get("ausfaelle", True) or not z.ist_rennen:
            return
        idx, grund, runde = e.daten["idx"], e.daten["grund"], e.daten["runde"]
        a = z.autos[idx]
        schluessel = k.AUSFALL_TEXT_SCHLUESSEL.get(grund)
        grund_text = self.t.sag(f"ausfall_grund.{schluessel}") if schluessel else ""
        werte = dict(name=a.anzeigename, runde=runde, platz=a.position, grund=grund_text)
        if idx == z.spieler_idx:
            text = "ausfall_du" if grund_text else "ausfall_du_ohne_grund"
        else:
            text = "ausfall" if grund_text else "ausfall_ohne_grund"
        self._sag("warnung." + text, NORMAL, **werte)

    # --- Gelbe Flagge -------------------------------------------------
    def _gelb_melden(self, schluessel: str, **werte) -> None:
        z = self.z
        if not self.cfg.get("gelbe_flagge", True) or z.session_typ in k.TRAINING_SESSIONS + (0, 18):
            return
        ich = z.spieler
        if ich is None or ich.in_box or z.rote_flagge or z.safety_car != k.SC_KEINS:
            return  # unter Safety Car und in der Box ist Gelb nichts Besonderes
        if z.session_time - self._letzte_gelb < 15:
            return  # nicht dauernd dieselbe Meldung
        self._letzte_gelb = z.session_time
        self._sag("warnung." + schluessel, HOCH, **werte)

    def _bei_gelbe_flagge(self, e: Ereignis) -> None:
        voraus = e.daten.get("voraus")
        if voraus is None or voraus > self.cfg.get("gelb_vorausschau", 0.35):
            return  # liegt hinter dir oder zu weit weg
        sektor = e.daten.get("sektor", 0)
        self._gelb_melden("gelbe_flagge" if sektor else "gelbe_flagge_ohne_sektor", sektor=sektor)

    def _bei_gelbe_flagge_eigene(self, e: Ereignis) -> None:
        self._gelb_melden("gelbe_flagge_eigene")

    # --- Strafen ------------------------------------------------------
    def _bei_strafe(self, e: Ereignis) -> None:
        z = self.z
        if not self.cfg.get("strafen", True) or not z.ist_rennen:
            return
        ich = z.spieler
        if ich is None:
            return
        idx, typ, sekunden = e.daten["idx"], e.daten["strafe_typ"], e.daten["sekunden"]
        if idx == ich.idx:
            if typ == 0:
                self._sag("warnung.strafe_durchfahrt", HOCH)
            elif typ == 1:
                self._sag("warnung.strafe_stop_go", HOCH)
            elif typ == 4 and 0 < sekunden < 255:
                self._sag("warnung.strafe_zeit", HOCH, sekunden=sekunden)
            return
        if typ != 4 or not 0 < sekunden < 255 or idx >= len(z.autos):
            return
        auto = z.autos[idx]
        if auto.position == ich.position - 1:
            self._sag("warnung.strafe_gegner_vorne", name=auto.anzeigename, sekunden=sekunden)
        elif auto.position == ich.position + 1:
            self._sag("warnung.strafe_gegner_hinten", name=auto.anzeigename, sekunden=sekunden)
