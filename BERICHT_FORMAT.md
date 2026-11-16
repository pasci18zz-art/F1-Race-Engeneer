# Format der Berichtsdatei (`.json`)

Nach jedem Rennen und Qualifying legt der Renningenieur im Ordner `exporte`
eine JSON-Datei ab (UTF-8). Dieselbe Datei gibt es am Tablet unter „Bericht →
Als JSON-Datei speichern“ und über die Adresse
`http://<PC>:8025/api/bericht?id=<Nummer>&format=json` bzw. `…?live=1&format=json`.
Daneben liegt eine gut lesbare `.txt` mit denselben Angaben.

Gedacht ist die Datei zum Einlesen in eine eigene Manager-App. Das Format ist
versioniert: `"schema": "renningenieur.bericht"`, `"version": 2`. Neue Felder
können in späteren Versionen **dazukommen**, bestehende ändern ihre Bedeutung
nicht, solange `version` gleich bleibt.

**Änderungen gegenüber Version 1:** `positionsverlauf` enthält jetzt je Runde die
komplette Reihenfolge mit Abstand und Reifen (vorher nur Namen); `session` hat
`ist_sprint` und `art`; für Qualifying gibt es zusätzlich die Datei
„Qualifying gesamt“ (siehe unten).

## Welche Dateien gibt es?

| Datei | Wann |
|---|---|
| `…_Rennen_<Strecke>.json/.txt` | nach jedem Rennen |
| `…_Sprintrennen_<Strecke>.json/.txt` | nach jedem Sprintrennen |
| `…_Qualifying_1_<Strecke>.json/.txt` (und 2, 3) | nach jedem Qualifying-Teil |
| `<Datum>_Qualifying_gesamt_<Strecke>.json/.txt` | nach jedem Qualifying-Teil aktualisiert, enthält Q1, Q2 und Q3 |
| `<Datum>_Sprint-Shootout_gesamt_<Strecke>.json/.txt` | dasselbe für das Sprint-Qualifying |

Für die Manager-App reicht beim Qualifying die „gesamt“-Datei.

## Konventionen

- Zeiten in **Millisekunden** (`…_ms`), Gesamtzeiten und Sessionzeit in
  **Sekunden** (`…_s`, `zeit`).
- `0` bei einer Rundenzeit heißt „keine Zeit“. Ungültige Runden sind mit
  `"gueltig": false` markiert und zählen nicht für Bestzeiten.
- Reifen: `kurz` ist `S` Soft, `M` Medium, `H` Hard, `I` Intermediate, `W` Regenreifen.
  `tatsaechlich` ist die C-Nummer des Spiels.
- Wetter: `wetter` 0 klar, 1 leicht bewölkt, 2 bedeckt, 3 leichter Regen,
  4 starker Regen, 5 Sturm (`wetter_name` ist der deutsche Text).
- Namen stehen in normaler Schreibweise („Verstappen“). `idx` ist die Nummer
  des Autos im Spiel und innerhalb einer Datei eindeutig; damit hängen
  `fahrer`, `ergebnis`, `ausfaelle` und `momentaufnahmen` zusammen.
- Alle Texte sind deutsch.

## Oberste Ebene

| Feld | Inhalt |
|---|---|
| `schema`, `version` | Kennung des Formats |
| `erstellt` | Zeitpunkt der Erstellung (ISO 8601, lokale Zeit) |
| `session` | Allgemeines zur Session |
| `wetter` | Wetterverlauf |
| `ergebnis` | Endergebnis (Rennen) bzw. Zeitenliste (Qualifying), nach Platz sortiert |
| `schnellste_runde` | schnellste gültige Runde der Session oder `null` |
| `ausfaelle` | wer wann warum ausgeschieden ist (nur Rennen) |
| `ereignisse` | Protokoll: Strafen, Safety Car, Flaggen, Wetterwechsel, Ausfälle, Boxeneinfahrten |
| `momentaufnahmen` | Reihenfolge zu wichtigen Zeitpunkten (nur Rennen) |
| `fahrer` | alle Fahrer mit Stints, Boxenstopps und allen Runden |
| `positionsverlauf` | komplette Reihenfolge nach jeder Runde (Rennen und Sprint) |
| `quali` | Qualifying-Angaben (nur Qualifying) |

## `session`

```json
{
  "session_uid": "5901211947180753897",
  "saison_id": 2025001, "wochenende_id": 1,
  "typ": 15, "typ_name": "Rennen", "art": "rennen",
  "ist_rennen": true, "ist_sprint": false, "ist_quali": false, "quali_teil": "",
  "strecke": "Monza",
  "runden_geplant": 12, "runden_gefahren": 12,
  "beendet": true, "rote_flaggen": 1,
  "begonnen": "2025-06-01T20:03:11",
  "spieler": "Spieler"
}
```

`typ` ist der Session-Typ des Spiels (5–7 Qualifying 1–3, 15 Rennen …).
`art` ist einer von `rennen`, `sprint`, `qualifying`, `sprint_shootout`, `training`, `sonstige`.
Ein **Sprintrennen** meldet das Spiel selbst nur als „Rennen“; das Programm erkennt es
(Wochenende mit Sprint-Shootout, erstes Rennen) und setzt dann `typ_name` auf
`"Sprintrennen"`, `art` auf `"sprint"` und `ist_sprint` auf `true`. `ist_rennen` bleibt `true`.
`quali_teil` ist `Q1`, `Q2`, `Q3` (beim Sprint `SQ1` …) oder leer. `begonnen`
fehlt (`null`), wenn der Bericht aus der laufenden Session erzeugt wurde.
`saison_id`/`wochenende_id` sind die Kennungen des Spiels; sie gruppieren
Sessions eines Rennwochenendes bzw. einer Saison.

## `ergebnis` – Rennen

```json
{
  "position": 2, "idx": 4, "name": "Spieler", "team": "Williams", "startnummer": 23,
  "ist_spieler": true, "mensch": true,
  "startplatz": 5, "plaetze_gewonnen": 3,
  "status": "im Ziel", "runden": 12,
  "gesamtzeit_s": 1087.5, "strafen_s": 0, "rueckstand_ms": 500,
  "beste_runde_ms": 80000, "punkte": 18, "boxenstopps": 2,
  "reifenfolge": ["M", "H", "S", "I"],
  "ausfall": null
}
```

`gesamtzeit_s` ist die Rennzeit ohne Strafen; `rueckstand_ms` auf den Sieger
inklusive Strafzeiten. Ein ausgeschiedener Fahrer hat statt `null`:
`"ausfall": {"runde": 5, "grund": "mechanisches Problem", "position_beim_ausfall": 1}`.
`mensch` ist `true` für dich und deinen Kumpel.

## `ergebnis` – Qualifying

```json
{
  "position": 4, "idx": 4, "name": "Spieler", "team": "Williams", "startnummer": 23,
  "ist_spieler": true, "mensch": true,
  "beste_runde_ms": 79385, "rueckstand_p1_ms": 267, "rueckstand_vordermann_ms": 153,
  "runden": 4, "gueltige_runden": 3, "ungueltige_runden": 1,
  "reifen": "S", "weiter": true
}
```

Platz und Bestzeit sind **die Wertung des Spiels** (Platzierung und Bestzeit am Ende des
Teils). `quelle` ist dann `"spiel"`. Nur wenn das Spiel keine brauchbaren Plätze liefert,
sortiert das Programm selbst nach der besten gültigen Runde (`quelle: "berechnet"`).
Wer keine Zeit hat, hat `beste_runde_ms: 0`. Strafen für die Startaufstellung (z. B.
Rückversetzungen) sind hier **nicht** eingerechnet; die tatsächliche Startposition steht im
Rennbericht bei `startplatz`.
`weiter` ist `true`/`false` in Q1 und Q2 (Ausscheidungslinie in
`quali.ausscheidungslinie`), sonst `null`.

## `ausfaelle`

```json
{"idx": 0, "name": "Verstappen", "team": "Red Bull", "runde": 5, "zeit": 330.0,
 "code": 8, "grund": "mechanisches Problem", "position": 1}
```

`zeit` ist die Session-Zeit in Sekunden, `position` die Platzierung zum
Zeitpunkt des Ausfalls. `grund` ist einer von: „aufgegeben“, „schwerer
Schaden“, „inaktiv“, „schwarze Flagge“, „mechanisches Problem“ (`code`
1, 3, 4, 6, 8 – die Codes des Spiels).

## `ereignisse`

```json
{"zeit": 345.0, "runde": 5, "art": "GELB", "fahrer": null, "text": "Gelbe Flagge in Sektor 2"}
```

`art`: `WETTER`, `SC` (Safety Car / Virtuelles Safety Car / Strecke frei),
`RDFL` (rote Flagge), `RESTART`, `GELB`, `STRAFE`, `AUSFALL`, `SIEGER`, `BOX`,
`STAND` (eine Momentaufnahme wurde festgehalten). `fahrer` ist ein `idx` oder `null`.

## `momentaufnahmen`

Zeitpunkte: `start`, `safety_car`, `vsc`, `gruen` (Safety Car oder VSC beendet),
`rote_flagge`, `restart`, `zwischenstand` (alle 10 Runden bei grüner Flagge).

```json
{
  "zeit": 420.0, "runde": 6, "grund": "safety_car", "text": "Safety Car",
  "reihenfolge": [
    {"position": 1, "idx": 1, "name": "Norris", "team": "McLaren",
     "rueckstand_ms": 0, "intervall_ms": 0, "reifen": "M", "reifenalter": 5,
     "in_box": false, "ausgefallen": false}
  ]
}
```

## `fahrer`

Ein Eintrag je Fahrer (auch im Qualifying):

```json
{
  "idx": 4, "name": "Spieler", "team": "Williams", "startnummer": 23,
  "ist_spieler": true, "mensch": true, "startplatz": 5, "position": 2,
  "beste_runde_ms": 80000,
  "boxenstopps": [{"runde": 6, "zeit": 495.0, "zeit_gasse_ms": 22000, "standzeit_ms": 2400}],
  "stints": [{
    "nr": 1, "mischung": "Medium", "kurz": "M", "tatsaechlich": 19,
    "start_runde": 1, "end_runde": 6, "runden": 6, "alter_start": 0,
    "verschleiss_ende": 29.0, "verschleiss_pro_runde": 4.8,
    "beste_runde_ms": 80500, "schnitt_runde_ms": 86625
  }],
  "runden": [{
    "runde": 1, "zeit_ms": 82000, "gueltig": true, "position": 3,
    "rueckstand_fuehrender_ms": 3034,
    "s1_ms": 27333, "s2_ms": 27333, "s3_ms": 27334,
    "reifen": "M", "reifenalter": 0, "verschleiss": 5.4, "box": false
  }]
}
```

- `verschleiss_ende`: höchster Verschleiß (Prozent, schlechtester Reifen) im
  Stint. `verschleiss_pro_runde`: Durchschnitt je Runde; bei gebrauchten Sätzen
  (`alter_start` > 0) ab der ersten Runde des Stints gerechnet. `null`, wenn
  das Spiel die Werte nicht freigibt (Telemetrie des Fahrers „Eingeschränkt“).
- Ein Stint ohne volle Runde (Reifenwechsel unter roter Flagge) hat
  `start_runde` = `end_runde`.
- `runden[].verschleiss` und `…reifenalter` gelten am Ende der Runde.
- `schnitt_runde_ms` enthält nur gültige Runden und damit auch Runden unter
  Safety Car; sie sind nicht herausgerechnet.

## `positionsverlauf` (Rennen und Sprint)

Je Runde die **komplette Reihenfolge**, festgehalten in dem Moment, in dem der
Führende die Runde beendet (für jede Runde von 1 bis zum Ende):

```json
{"runde": 3, "zeit": 245.5, "reihenfolge": [
  {"position": 1, "idx": 0, "name": "Verstappen", "team": "Red Bull",
   "rueckstand_ms": 0, "intervall_ms": 0, "reifen": "M", "reifenalter": 3,
   "in_box": false, "ausgefallen": false},
  {"position": 2, "idx": 1, "name": "Norris", "team": "McLaren",
   "rueckstand_ms": 1250, "intervall_ms": 1250, "reifen": "S", "reifenalter": 3,
   "in_box": false, "ausgefallen": false}
]}
```

Ausgefallene Fahrer stehen am Ende der Liste (`ausgefallen: true`). Fehlen Runden
(Programm mitten im Rennen gestartet), fehlen auch diese Einträge. Bei älteren,
gespeicherten Sessions ohne diese Daten wird der Verlauf aus den Rundendaten der
Fahrer gebaut (dann ohne `team`, `intervall_ms` und `reifenalter`).

## `quali` (Qualifying)

```json
{"teil": "Q1", "ausscheidungslinie": 15}
```

`ausscheidungslinie` ist der letzte Platz, der weiterkommt (`null` ohne Ausscheiden).

## Datei „Qualifying gesamt“

Für Q1, Q2 und Q3 (bzw. SQ1 bis SQ3) gibt es zusätzlich eine gemeinsame Datei. Sie
wird nach **jedem** Teil neu geschrieben; `session.abgeschlossen` ist erst nach dem
letzten Teil `true` (vorher ist es ein vorläufiger Stand).

```json
{
  "schema": "renningenieur.bericht", "version": 2, "art": "quali_gesamt",
  "erstellt": "2025-06-01T15:40:12",
  "session": {"typ_name": "Qualifying gesamt", "art": "qualifying", "strecke": "Monza",
              "saison_id": 2025001, "wochenende_id": 9, "teile": ["Q1", "Q2", "Q3"],
              "abgeschlossen": true, "spieler": "Spieler",
              "ist_rennen": false, "ist_sprint": false, "ist_quali": true},
  "endergebnis": [
    {"position": 1, "idx": 1, "name": "Norris", "team": "McLaren", "startnummer": 4,
     "ist_spieler": false, "mensch": false,
     "teil": "Q3", "ausgeschieden_in": "",
     "beste_runde_ms": 79082, "rueckstand_im_teil_ms": 0}
  ],
  "teile": [ { ... voller Bericht von Q1 ... }, { ... Q2 ... }, { ... Q3 ... } ]
}
```

- `endergebnis` ist die **Startaufstellung**: erst die Fahrer aus Q3 nach ihrer
  Q3-Zeit, dann die in Q2 Ausgeschiedenen nach Q2, dann die in Q1 Ausgeschiedenen
  nach Q1. `teil` sagt, aus welchem Teil Zeit und Platz stammen,
  `ausgeschieden_in` ist leer bei den Q3-Fahrern.
- `rueckstand_im_teil_ms` ist der Abstand zu Platz 1 **desselben Teils**
  (Q1- und Q3-Zeiten sind wegen anderer Bedingungen nicht direkt vergleichbar).
- In `teile` steht je Teil ein normaler Bericht mit allen Angaben (Ergebnis,
  Rundenzeiten, ungültige Runden, Reifen).

## Hinweise zur Genauigkeit

- Alle Angaben stammen aus der UDP-Telemetrie des Spiels. Wo das Spiel etwas
  nicht liefert (z. B. Verschleiß fremder Fahrer bei „Eingeschränkt“), steht `null`.
- Wurde das Programm mitten in der Session gestartet, fehlen die Runden davor.
- Nach einer Rückblende (Flashback) werden Ausfälle, Momentaufnahmen und
  Ereignisse nach dem Zielzeitpunkt verworfen.
