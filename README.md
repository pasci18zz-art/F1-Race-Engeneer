# Renningenieur für F1 25

Ein eigener Renningenieur für F1 25 am PC. Das Programm empfängt die UDP-Telemetrie
des Spiels, warnt von selbst (Sprache), beantwortet gesprochene Fragen und zeigt
auf dem Tablet eine Strategieübersicht. Alles läuft lokal auf dem PC: kein
Cloud-Dienst, kein LLM, keine laufenden Kosten.

```
Spiel ──UDP 20777──► Renningenieur ──► SimHub (Port 20778, unveränderte Kopie)
                         │
                         ├─► Warnungen und Antworten (Windows-Sprachausgabe)
                         ├─► Datenbank (SQLite)
                         └─► Webseite fürs Tablet (http://PC-IP:8025)
```

**Neu hier? Die Schritt-für-Schritt-Anleitung mit allen Klicks steht in [ANLEITUNG.md](ANLEITUNG.md).**

## Stand

| Teil | Zustand |
|---|---|
| UDP-Empfang, Relay an SimHub, Paketauswertung (Format 2025 und 2026) | fertig, mit simulierten Paketen getestet |
| Automatische Warnungen mit einstellbaren Schwellen und Sprüchen | fertig, getestet |
| Fragen per Stichwort (Wetter, Abstände, Rundenvergleich, Reifen, Box, …) | fertig, getestet |
| SQLite-Datenbank pro Saison und Rennen | fertig, getestet |
| Tablet-Seite: Live, Rückblick, Vergleich | fertig, im Browser geprüft |
| Windows-Sprachausgabe, Mikrofon, Funktaste, Vosk | geschrieben, **noch nicht auf Windows ausprobiert** |
| Lauf mit dem echten Spiel | **steht noch aus** (siehe „Erster Start mit dem Spiel“) |

Entwickelt und getestet wurde auf Linux mit dem eingebauten Simulator. Die Teile,
die Windows, ein Mikrofon oder ein Lenkrad brauchen, konnten dort nicht laufen.
Rechne beim ersten Start auf deinem PC damit, dass an diesen Stellen noch etwas
nachzustellen ist.

## Einrichtung

1. **Python 3.11 oder neuer** von python.org installieren, dabei „Add python.exe to PATH“ ankreuzen.
2. Diesen Ordner auf den PC kopieren und **`installieren.bat`** doppelklicken.
   Das legt eine eigene Python-Umgebung an, installiert Vosk, sounddevice und
   pygame-ce und lädt das deutsche Sprachmodell (ca. 45 MB) nach `modelle/`.
3. **`start.bat`** doppelklicken.

Beim ersten Start entstehen `config.toml` (Einstellungen) und `texte.toml`
(alle Sprüche). Beide sind zum Ändern gedacht; danach das Programm neu starten.

Ohne Schritt 2 laufen Empfang, Warnungen, Sprachausgabe, Datenbank und
Tablet-Seite trotzdem. Es fehlen dann nur Spracheingabe und Lenkradtaste;
Fragen kannst du im Programmfenster oder auf dem Tablet eintippen.

## Spiel und SimHub einstellen

**Im Spiel** (Einstellungen → Telemetrie):

| Einstellung | Wert |
|---|---|
| UDP-Telemetrie | An |
| UDP-Broadcast-Modus | Aus |
| UDP-IP-Adresse | 127.0.0.1 |
| UDP-Port | 20777 |
| UDP-Senderate | 20 Hz oder mehr |
| UDP-Format | 2025 oder 2026 (beides wird erkannt) |
| Ihre Telemetrie | Öffentlich (auch bei deinem Mitspieler, sonst fehlen sein Verschleiß und Schaden) |

**In SimHub:** Beim Spiel F1 25 in den Spieleinstellungen den UDP-Port von 20777
auf **20778** stellen. Der Renningenieur reicht jedes Paket unverändert dorthin
weiter. Die Ziele stehen in `config.toml` unter `[udp] weiterleiten` – dort
kannst du weitere Programme eintragen.

Läuft der Renningenieur nicht, bekommt SimHub in diesem Aufbau keine Daten.
Wenn dich das stört, geht es auch andersherum: SimHub bleibt auf 20777 und
leitet per eigener UDP-Weiterleitung an Port 20778, und in `config.toml` steht
dann `port = 20778` und `weiterleiten = []`.

## Ohne Spiel ausprobieren

Zwei Fenster öffnen:

```
start.bat                          Fenster 1: der Renningenieur
simulation.bat                     Fenster 2: schickt ein simuliertes Rennen
```

Alle Befehle unten gibt es auch als Doppelklick-Datei: `simulation.bat`,
`pruefen.bat`, `geraete.bat`.

Der Simulator erzeugt echte F1-25-Pakete und schickt sie an Port 20777, also
durch die ganze Kette samt Weiterleitung. Du fährst „Spieler“ (Startplatz 5),
dein Mitspieler heißt „Kumpel“.

| Befehl | Was passiert |
|---|---|
| `start.bat simulation alles` | Stopps, Strafe, Safety Car, rote Flagge mit Restart, Regen (Standard) |
| `start.bat simulation trocken` | trockenes Rennen, Reifenverschleiß bis über 40 % |
| `start.bat simulation regen` | Regen kündigt sich an und kommt |
| `start.bat simulation rote_flagge` | rote Flagge mit Restart |
| `… --tempo 5` | fünffacher Zeitraffer |
| `… --format 2026` | Pakete im Format des 2026 Season Pack |
| `… --strecke 10 --wochenende 2 --saison 7` | anderes Rennen für die Datenbank |

Ein echtes Rennen mitschneiden und beliebig oft wieder abspielen:

```
start.bat --aufnahme monza.f1udp
start.bat abspielen monza.f1udp --tempo 4
```

## Erster Start mit dem Spiel

```
start.bat pruefen
```

Das hört 15 Sekunden mit und listet auf, welche Pakete in welcher Größe
ankommen und ob sie zur Spezifikation passen. Steht am Ende „Alle Pakete passen
zur Spec“, stimmt das Format. Die Weiterleitung an SimHub läuft dabei weiter.

## Mikrofon, Funktaste, Stimme

```
start.bat geraete
```

zeigt alle Mikrofone, die Windows-Stimmen und Ausgabegeräte und wartet dann
30 Sekunden auf einen Tastendruck am Lenkrad. Das Ergebnis trägst du in
`config.toml` ein:

```toml
[mikrofon]
geraet = "APEXEL"        # Teil des Namens oder die Nummer aus der Liste

[funktaste]
joystick = "Fanatec"     # Teil des Gerätenamens, leer = jedes Gerät
taste = 7                # Nummer aus "start.bat geraete"
tastatur = "f12"         # zusätzlich oder stattdessen
modus = "halten"         # oder "umschalten"

[sprachausgabe]
stimme = "Hedda"         # leer = erste deutsche Stimme
ausgabegeraet = ""       # leer = Windows-Standardgerät
```

- Das Mikrofon läuft dauerhaft mit und füllt einen Puffer von 0,5 Sekunden.
  Die Aufnahme beginnt mit diesem Puffer, der Satzanfang geht also nicht verloren.
- Die Erkennung rechnet erst nach dem Loslassen der Taste und nur über die
  wenigen Sekunden Aufnahme. Während der Fahrt kostet sie nichts.
- Solange du sprichst, schweigt der Ingenieur.
- Nach jeder Frage steht im Fenster `Verstanden: …`. Versteht Vosk einen
  Fahrernamen falsch, trag das Gehörte unter `[fahrer.aliase]` ein.
- Mit `wortliste = true` unter `[spracherkennung]` hört Vosk nur noch auf
  bekannte Wörter. Das hilft bei Nebengeräuschen, Namen müssen dann als Alias
  eingetragen sein.
- Die Windows-Sprachausgabe braucht eine deutsche Stimme (Windows-Einstellungen
  → Zeit und Sprache → Sprache → Deutsch → Sprachausgabe).

## Fragen

Erkannt wird am Stichwort, die genaue Formulierung ist egal.

| Thema | Beispiele |
|---|---|
| Wetter | „Kommt Regen?“ · „Wie ist das Wetter?“ · „Wann wird es trocken?“ |
| Abstände | „Wie viele Sekunden zum Auto vor mir?“ · „Abstand nach hinten“ · „Rückstand auf den Führenden“ · „Wie weit ist Platz drei weg?“ · „Abstand zu Verstappen“ |
| Entwicklung | „Wie viel habe ich in den letzten fünf Runden auf den Vordermann verloren?“ · „… auf meinen Kumpel gewonnen?“ |
| Reifen | „Wie sind meine Reifen?“ · „Welche Reifen hat der Hintermann?“ · „Wie ist der Reifenverschleiß von Verstappen?“ · „Welche Mischung fährt wer?“ |
| Box | „Wann ist das Boxenfenster?“ (nennt vorerst das Fenster, das das Spiel berechnet) |
| Strategie anderer | „Wie ist die Strategie von Verstappen?“ · „War der Hintermann schon an der Box?“ · „Wer war noch nicht an der Box?“ |
| Positionen | „Wer ist auf Position siebzehn?“ · „Auf welchem Platz ist Leclerc?“ · „Wer führt?“ · „Wie ist die Reihenfolge?“ |
| Sonstiges | „Auf welchem Platz bin ich?“ · „Wie viele Runden noch?“ · „Wie viel Sprit habe ich?“ · „Habe ich einen Schaden?“ · „Habe ich Strafen?“ · „Wie war meine Rundenzeit?“ |

Einen Fahrer meinst du mit „vor mir“, „hinter mir“, „der Führende“, „Platz
vier“, „der Dritte“, „mein Teamkollege“, „mein Kumpel“, dem Namen oder dem Team.
„Kumpel“ ist automatisch der andere menschliche Fahrer; unter `[fahrer] kumpel`
kannst du ihn fest benennen.

## Warnungen

Alle Schwellen stehen in `config.toml` unter `[warnungen]`, alle Sätze in
`texte.toml`. Eine leere Liste `[]` in `texte.toml` schaltet einen Satz stumm.

| Warnung | Einstellung |
|---|---|
| Gegner vor/hinter dir fährt in die Box, und wo er wieder herauskommt | `box_gegner`, `box_positionen`, `box_max_abstand`, `box_ausfahrt` |
| Reifenverschleiß über Grenzwert | `reifenverschleiss = [40, 55, 70]` |
| Regen kommt in X Minuten, Regen beginnt, wird stärker, hört auf | `regen_minuten = [10, 5, 2]`, `abtrocknen` |
| Hintermann näher als X Sekunden | `abstand_hinten`, `…_entwarnung`, `…_pause`, `…_ab_runde` |
| Safety Car, virtuelles Safety Car | `safety_car` |
| Rote Flagge und Restart | `rote_flagge` |
| Strafen (eigene und die der direkten Gegner) | `strafen` |

Es gibt keine Füllsätze. Nach einer roten Flagge kommt ein Lagebericht aus
Fakten: dein Platz, deine Reifen mit Alter und Verschleiß, zum Restart die
Reifen von Vorder- und Hintermann und, falls angekündigt, der Regen.

Die Regenprognose des Spiels kommt in Schritten von 5 Minuten (danach 15).
„Regen in etwa 10 Minuten“ heißt deshalb: irgendwann in den nächsten 5 bis 10.

## Tablet

Beim Start steht im Fenster die Adresse, z. B. `http://192.168.178.20:8025`.
Die im Browser des Tablets öffnen (gleiches WLAN). Fragt die Windows-Firewall
beim ersten Start, Python für private Netzwerke zulassen.

- **Live:** Position, Wetter mit Prognose und Verlauf, Abstände, und für jedes
  Auto Reifen, Alter, Verschleiß, Stopps und alle Stints als Balken über die
  Runden. Dazu Funkprotokoll, Ereignisse und ein Feld zum Eintippen von Fragen.
- **Rückblick:** alle gespeicherten Sessions nach Saison. Ein Rennen antippen
  zeigt Startreifen, Stints aller Fahrer, Wetterwechsel und Ereignisse.
  Saisons lassen sich umbenennen.
- **Vergleich:** Tabelle Strecke × Saison mit deinem Ergebnis und deiner
  Reifenfolge, und zwei Rennen nebeneinander.

## Datenbank

`renningenieur.sqlite` im Programmordner. Gespeichert wird bei jeder
Führungsrunde, bei roter Flagge und am Ende – immer der komplette Stand der
Session, damit auch nach Rückblenden alles stimmt.

Tabellen: `saisons`, `sessions`, `teilnehmer`, `stints`, `boxenstopps`,
`wetter`, `runden`, `ereignisse`. Die Datei lässt sich mit jedem
SQLite-Programm öffnen (z. B. DB Browser for SQLite). Saison und Wochenende
kommen aus den Kennungen, die das Spiel mitschickt.

## Aufbau des Codes

Jedes Modul hat eine Aufgabe und lässt sich einzeln austauschen.

| Modul | Aufgabe |
|---|---|
| `telemetrie/spec.py` | Paketformat 2025/2026 als Tabellen, Paketgrößen laut Spec |
| `telemetrie/parser.py` | Bytes → Dictionary |
| `telemetrie/encoder.py` | Dictionary → Bytes (für Simulator und Tests) |
| `telemetrie/relay.py` | UDP-Empfang und Weiterleitung |
| `telemetrie/aufnahme.py` | Telemetrie mitschneiden und abspielen |
| `telemetrie/konstanten.py` | Wetter, Reifen, Teams, Strecken |
| `zustand.py` | aktueller Rennzustand (reine Daten und Abfragen) |
| `auswertung.py` | Pakete → Zustand und Ereignisse (Boxeneinfahrt, rote Flagge, …) |
| `regeln.py` | automatische Warnungen, eine Methode pro Regel |
| `fragen.py` | Fragen verstehen und beantworten |
| `formulierung.py` | Zahlen und Zustände in sprechbare Bausteine |
| `sprache/funk.py` | Warteschlange mit Priorität und Verfallszeit |
| `sprache/stimmen.py` | Sprachausgaben (Windows, Konsole, stumm) |
| `sprache/mikrofon.py` | Aufnahme mit Vorlauf |
| `sprache/funktaste.py` | Lenkrad- und Tastaturtaste |
| `sprache/erkennung.py` | Vosk |
| `datenbank.py` | SQLite schreiben und lesen |
| `schnappschuss.py` | Zustand als JSON für Web und Datenbank |
| `web/` | Webserver und Tablet-Seite |
| `simulator.py` | simuliertes Rennen |
| `kern.py`, `app.py` | Verdrahtung und Befehle |

Im Betrieb braucht nur die Spracheingabe Zusatzpakete. Alles andere kommt mit
der Python-Standardbibliothek aus.

## Tests

```
python -m unittest discover -s tests -t .
```

90 Tests: Paketgrößen und Feldreihenfolge beider Formate, Relay über echte
UDP-Sockets, jede Regel mit ihren Schwellen, die Fragen, komplette simulierte
Rennen von Paket bis Datenbank, Rückblenden, Webserver.

## Paketformat

Das Format wurde vor dem Programmieren geprüft, nicht aus dem Gedächtnis
übernommen. Die offizielle EA-Seite war aus der Entwicklungsumgebung nicht
erreichbar; verwendet wurden zwei unabhängige Umsetzungen der Spezifikation:

- PyPI `f1-packets` 2025.1.0 und 2026.1.1 (wird direkt aus dem Spec-Dokument erzeugt)
- npm `@deltazeroproduction/f1-udp-parser` 1.2.2 (Format 2025, mit den Paketgrößen der Spec)

Beide stimmen für Format 2025 in Feldreihenfolge und Größen überein. Für Format
2026 (2026 Season Pack: 24 Autos, einige breitere Felder, neues Paket 16) gab es
nur die eine vollständige Quelle; zwei Größen daraus bestätigen Berichte anderer
Entwickler mit echten Paketen. Sicherheit bringt `start.bat pruefen` mit dem
echten Spiel. Die offizielle Spezifikation steht im EA-Forum unter
„F1 25 UDP Specification“.

## Als Nächstes

- Lauf mit dem echten Spiel, danach Schwellen und Sprüche nachstellen
- Lenkradmodell eintragen und Funktaste testen
- Strategie: eigenes Boxenfenster aus Verschleißverlauf, Abständen und Stoppzeit
  berechnen statt den Wert des Spiels vorzulesen
