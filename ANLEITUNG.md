# Anleitung Schritt für Schritt

Du brauchst nichts zu programmieren und keine Befehle zu tippen. Alles läuft
über Doppelklicks auf Dateien im Programmordner und über zwei Textdateien, die
du mit dem Windows-Editor änderst.

**Die Reihenfolge:** erst Teil A bis C (alles einrichten und ohne Spiel
ausprobieren), dann D und E (Spiel und SimHub), danach F bis H (Mikrofon,
Lenkradtaste, Tablet).

---

## A. Python installieren (einmalig)

Python ist die Programmiersprache, in der der Renningenieur geschrieben ist.
Windows bringt sie nicht mit.

1. Im Browser **https://www.python.org/downloads/** öffnen.
2. Auf den gelben Knopf **„Download Python 3.…“** klicken. Die Datei landet im
   Ordner „Downloads“.
3. Die heruntergeladene Datei doppelklicken (sie heißt etwa
   `python-3.xx.x-amd64.exe`).
4. **Wichtig:** Im ersten Fenster ganz unten das Häkchen bei
   **„Add python.exe to PATH“** setzen.
5. Auf **„Install Now“** klicken, warten, am Ende **„Close“**.

## B. Das Programm auf den PC holen (einmalig)

1. Im Browser **https://github.com/pasci18zz-art/F1-Race-Engeneer** öffnen
   (bei GitHub angemeldet sein).
2. Auf den grünen Knopf **„Code“** klicken, dann unten auf **„Download ZIP“**.
3. Im Ordner „Downloads“ die ZIP-Datei mit der **rechten Maustaste** anklicken
   → **„Alle extrahieren…“** → **„Extrahieren“**.
4. Es entsteht ein Ordner `F1-Race-Engeneer-…`. Öffne ihn, bis du die Dateien
   `start.bat` und `installieren.bat` siehst. (Manchmal steckt darin noch ein
   Ordner mit dem gleichen Namen – dann den inneren nehmen.)
5. Diesen Ordner an einen festen Platz schieben, z. B. nach
   `C:\Renningenieur`. Dort bleibt er.

In diesem Ordner liegen ab jetzt alle Dateien, von denen unten die Rede ist:

| Datei | Wofür |
|---|---|
| `installieren.bat` | einmalig: installiert die Zusatzteile |
| `start.bat` | startet den Renningenieur (das benutzt du jedes Mal) |
| `simulation.bat` | Testrennen ohne Spiel |
| `geraete.bat` | zeigt Mikrofone und Lenkradtasten an |
| `stimmen.bat` | natürlichere Stimme auswählen (siehe K0) |
| `mikrofontest.bat` | Mikrofon und Spracherkennung ausprobieren (siehe N) |
| `whisper.bat` | genauere Spracherkennung installieren (siehe N) |
| `pruefen.bat` | prüft, ob die Daten des Spiels richtig ankommen |
| `config.toml` | deine Einstellungen (entsteht beim ersten Start) |
| `texte.toml` | alle Sprüche (entsteht beim ersten Start) |

## C. Installieren und ohne Spiel ausprobieren

### C1. Zusatzteile installieren (einmalig)

1. **`installieren.bat` doppelklicken.**
2. Falls ein blaues Fenster „Der Computer wurde durch Windows geschützt“
   kommt: auf **„Weitere Informationen“** klicken, dann **„Trotzdem
   ausführen“**. (Das kommt, weil die Datei aus dem Internet stammt.)
3. Ein schwarzes Fenster arbeitet ein paar Minuten. Es lädt die
   Spracherkennung, die Mikrofon- und Lenkrad-Anbindung und das deutsche
   Sprachmodell (ca. 45 MB).
4. Wenn **„Fertig. Jetzt start.bat doppelklicken.“** dasteht, eine beliebige
   Taste drücken. Das Fenster schließt sich.

Steht dort „Python wurde nicht gefunden“: Teil A wiederholen und auf das
Häkchen aus Schritt 4 achten.

### C2. Renningenieur starten

1. **`start.bat` doppelklicken.** Ein schwarzes Fenster bleibt offen – das ist
   das Programm. Solange es offen ist, läuft der Renningenieur.
2. Fragt die Windows-Firewall nach Python: Häkchen bei **„Private Netzwerke“**
   und **„Zugriff zulassen“**. (Nötig fürs Tablet.)
3. Im Fenster sollte stehen:
   ```
   UDP-Empfang auf Port 20777, Weiterleitung an: 127.0.0.1:20778
   Tablet-Seite: http://192.168.…:8025
   Bereit. …
   ```

Steht dort „UDP-Port 20777 ist belegt“, läuft SimHub noch auf diesem Port:
SimHub schließen oder erst Teil E machen.

### C3. Testrennen laufen lassen

1. Das Fenster von `start.bat` offen lassen.
2. **`simulation.bat` doppelklicken.** Ein zweites schwarzes Fenster schickt
   jetzt ein erfundenes Rennen (etwa 9 Minuten).
3. Du solltest nach ein paar Sekunden über deine Kopfhörer hören:
   *„Rennen in Monza, 12 Runden. Du startest von Platz 5 …“*
   Danach kommen Warnungen: Gegner in der Box, Regen, Safety Car, rote Flagge.
4. Im Browser am PC **http://localhost:8025** öffnen – das ist die Seite, die
   später auf dem Tablet läuft.
5. Eine Frage testen: auf der Seite unter „Funk“ z. B. `Kommt Regen?`
   eintippen und auf **„Fragen“** klicken. Die Antwort wird gesprochen.

**Klingt die Stimme englisch oder verwaschen?** Dann fehlt eine deutsche
Stimme: Windows-Einstellungen → Zeit und Sprache → Sprache und Region →
Deutsch → Sprachoptionen → Sprachausgabe herunterladen. Danach `start.bat` neu
starten.

**Kommt gar kein Ton, im Fenster stehen aber Zeilen mit „FUNK: …“?** Dann
klemmt die Sprachausgabe. Dieser Teil konnte vorab nicht auf Windows getestet
werden – bitte das Fenster fotografieren und mir schicken.

**Programm beenden:** das schwarze Fenster einfach schließen (X oben rechts).

> Tipp: Nicht mit der Maus in das schwarze Fenster klicken. Bei manchen
> Windows-Einstellungen hält ein Klick das Programm an (oben im Fenstertitel
> steht dann „Auswählen“). Mit der Taste **Esc** läuft es weiter.

## D. Das Spiel einstellen (einmalig)

In F1 25: **Einstellungen → Telemetrie-Einstellungen**

| Einstellung | Wert |
|---|---|
| UDP-Telemetrie | **An** |
| UDP-Broadcast-Modus | Aus |
| UDP-IP-Adresse | **127.0.0.1** |
| UDP-Port | **20777** |
| UDP-Senderate | 20 Hz (mehr geht auch) |
| UDP-Format | 2025 oder 2026 – beides funktioniert |
| Ihre Telemetrie | **Öffentlich** |

Dein Kumpel stellt bei sich ebenfalls „Ihre Telemetrie: Öffentlich“ ein. Sonst
sieht dein Renningenieur seinen Reifenverschleiß nicht.

## E. SimHub umstellen (einmalig)

Bisher hört SimHub direkt auf Port 20777. Ab jetzt hört der Renningenieur dort
und reicht alles an SimHub auf Port **20778** weiter.

1. SimHub öffnen, links das Spiel **F1 25** auswählen.
2. In den Einstellungen des Spiels (Knopf zur Spiel- bzw.
   Telemetrie-Konfiguration) das Feld **UDP-Port** von `20777` auf **`20778`**
   ändern und speichern.

Die genaue Beschriftung in SimHub konnte ich nicht nachsehen. Wenn du das Feld
nicht findest, schick mir einen Screenshot der SimHub-Seite.

**Wichtig für den Alltag:** SimHub bekommt seine Daten jetzt nur, wenn
`start.bat` läuft.

### Prüfen, ob die Daten ankommen

1. `start.bat` schließen, falls es läuft.
2. Im Spiel auf die Strecke fahren (z. B. Zeitfahren).
3. **`pruefen.bat` doppelklicken.** Nach 15 Sekunden erscheint eine Liste.
4. Steht am Ende **„Alle Pakete passen zur Spec.“**, ist alles richtig.
   Steht dort „Nichts empfangen“, stimmt eine Einstellung aus Teil D nicht.
   Steht dort „FEHLER“, das Fenster fotografieren und mir schicken.

## F. Mikrofon einrichten

1. USB-Empfänger des Ansteckmikros einstecken.
2. **`geraete.bat` doppelklicken.** Oben erscheint die Liste der Mikrofone,
   z. B.:
   ```
   === Mikrofone ===
     1  Mikrofon (USB Audio Device)  [MME]
     2  Headset (WH-1000XM4)  [MME]
   ```
3. Im Programmordner **`config.toml`** mit der rechten Maustaste anklicken →
   **„Öffnen mit“** → **„Editor“**.
4. Den Abschnitt `[mikrofon]` suchen und zwischen die Anführungszeichen einen
   Teil des Namens deines Ansteckmikros schreiben:
   ```toml
   [mikrofon]
   geraet = "USB Audio"
   ```
5. Speichern (Strg+S), Editor schließen, `start.bat` neu starten.

Im Fenster steht dann `Mikrofon: …` mit dem gewählten Gerät. Steht dort das
Sony-Headset, ist der Name falsch geschrieben – das Sony-Mikro darf es nicht
sein, sonst wird der Ton dumpf.

## G. Funktaste einrichten

Ab Werk ist die Taste **F12** auf der Tastatur die Funktaste: gedrückt halten,
sprechen, loslassen. Damit kannst du sofort testen.

Für eine Taste am Lenkrad:

1. **`geraete.bat` doppelklicken.** Unten steht
   „Drücke jetzt die Taste, die du als Funktaste willst“.
2. Die gewünschte Taste am Lenkrad drücken. Es erscheint z. B.:
   ```
   -> "FANATEC Wheel": taste = 7
   ```
3. `config.toml` im Editor öffnen (wie in F3) und im Abschnitt `[funktaste]`
   eintragen:
   ```toml
   [funktaste]
   joystick = "FANATEC"
   taste = 7
   ```
4. Speichern, `start.bat` neu starten.

Die Taste darf im Spiel nicht belegt sein, sonst löst sie dort auch etwas aus.

**So fragst du:** Taste halten → „Wie viele Sekunden zum Auto vor mir?“ →
loslassen. Im Fenster steht danach `Verstanden: …` und die Antwort wird
gesprochen. Versteht das Programm einen Fahrernamen falsch, sag mir, was hinter
„Verstanden:“ stand – das lässt sich in `config.toml` eintragen.

## H. Tablet

1. Tablet ins gleiche WLAN wie den PC.
2. `start.bat` starten und im Fenster die Zeile
   `Tablet-Seite: http://192.168.…:8025` ablesen.
3. Genau diese Adresse im Browser des Tablets eingeben.
4. Im Browser-Menü „Zum Startbildschirm hinzufügen“ wählen, dann hast du ein
   Symbol dafür.

Lädt die Seite nicht: In C2 wurde die Firewall-Frage vermutlich abgelehnt.
Windows-Suche → „App durch die Windows-Firewall zulassen“ → bei „Python“ das
Häkchen unter „Privat“ setzen.

## I. Ablauf an einem Rennabend

1. SimHub starten.
2. `start.bat` doppelklicken.
3. Tablet-Seite öffnen.
4. F1 25 starten und fahren.
5. Danach das schwarze Fenster schließen.

Die Rennen werden von selbst gespeichert und erscheinen auf dem Tablet unter
„Rückblick“.

## J. Schwellen und Sprüche ändern

Beides sind Textdateien im Programmordner; öffnen mit Rechtsklick → „Öffnen
mit“ → „Editor“. Nach dem Speichern `start.bat` neu starten.

- **`config.toml`**, Abschnitt `[warnungen]`: z. B.
  `reifenverschleiss = [40, 55, 70]` (bei diesen Prozentwerten wird gewarnt)
  oder `abstand_hinten = 1.0` (Warnung, wenn der Hintermann näher als eine
  Sekunde ist). Über jeder Zeile steht eine Erklärung.
- **`texte.toml`**: jeder Satz, den der Ingenieur sagt. Den Text zwischen den
  Anführungszeichen ändern; Wörter in `{Klammern}` stehen lassen, die ersetzt
  das Programm durch Namen und Zahlen.

Hast du dich vertippt und das Programm startet nicht mehr: die Datei löschen.
Beim nächsten Start wird sie neu mit den Standardwerten angelegt.

## K0. Andere Stimme (natürlicher, optional mit Funk-Klang)

Die Windows-Stimme klingt blechern. Besser klingt **Piper**: kostenlose,
natürliche Stimmen, die genauso komplett auf deinem PC laufen.

1. `start.bat` schließen.
2. **`stimmen.bat` doppelklicken.**
3. Beim ersten Mal installiert es Piper und lädt sieben deutsche Stimmen
   (zusammen etwa 400 MB, dauert ein paar Minuten).
4. Dann werden alle Stimmen nacheinander über deine Kopfhörer vorgespielt,
   im Fenster steht jeweils die Nummer dazu.
5. Die Nummer der Stimme eintippen, die dir gefällt, und **Enter** drücken.
   (Nur Enter = alle noch einmal anhören. 0 = Windows-Stimme behalten.)
6. Die gewählte Stimme kommt noch einmal **mit Funk-Effekt** – klingt wie
   Boxenfunk. `j` + Enter = mit Effekt, `n` + Enter = ohne.
7. Fertig. `start.bat` starten, ab jetzt spricht die neue Stimme.

Umentscheiden kannst du jederzeit: `stimmen.bat` noch einmal starten.
Sprechtempo und Lautstärke stehen in `config.toml` unter `[sprachausgabe]`
(`tempo` von -10 bis 10, `lautstaerke` von 0 bis 100).

## K. Was du fragen kannst

Die genaue Formulierung ist egal, es kommt auf die Stichwörter an.

| Du willst wissen | Sag zum Beispiel |
|---|---|
| Wetter | „Kommt Regen?“ · „Wann wird es trocken?“ · „Wie warm ist die Strecke?“ |
| Abstand | „Wie viele Sekunden zum Auto vor mir?“ · „Abstand nach hinten“ · „Rückstand auf den Führenden“ · „Abstand zu Verstappen“ |
| Verloren oder gewonnen | „Wie viel habe ich in den letzten fünf Runden auf den Vordermann verloren?“ |
| Holt er auf? | „Holt der Hintermann auf?“ · „Wann habe ich den Vordermann eingeholt?“ |
| Tempo | „Wer ist gerade am schnellsten?“ · „Wie schnell war der Vordermann in der letzten Runde?“ · „Wie war meine Rundenzeit?“ |
| Sektoren | „In welchem Sektor verliere ich auf den Vordermann?“ · „Wie war mein erster Sektor?“ |
| Konstanz | „Wie konstant fahre ich?“ |
| Eigene Reifen | „Wie sind meine Reifen?“ · „Wie lange halten meine Reifen noch?“ · „Welche Reifensätze habe ich noch?“ |
| Reifen anderer | „Welche Reifen hat der Hintermann?“ · „Wie ist der Reifenverschleiß von Verstappen?“ · „Wie lange halten die Reifen vom Vordermann?“ |
| Reifen aller | „Welche Mischung fährt wer?“ · „Wer hat um mich herum die frischesten Reifen?“ |
| Boxenstopp | „Wann ist das Boxenfenster?“ · „Wo komme ich nach einem Stopp raus?“ · „Lohnt sich ein Undercut auf den Vordermann?“ · „Wie viel Zeit kostet hier ein Boxenstopp?“ |
| Strategie anderer | „Wie ist die Strategie von Verstappen?“ · „War der Hintermann schon an der Box?“ · „Wer war noch nicht an der Box?“ |
| Wer wo liegt | „Wer ist auf Position siebzehn?“ · „Auf welchem Platz ist Leclerc?“ · „Wer führt?“ · „Wie ist die Reihenfolge?“ |
| Eigene Lage | „Auf welchem Platz bin ich?“ · „Wie viele Plätze habe ich seit dem Start gutgemacht?“ · „Wie viele Runden noch?“ |
| Auto | „Wie warm sind meine Reifen?“ · „Wie warm sind meine Bremsen?“ · „Wie viel ERS habe ich?“ · „Wie viel Sprit habe ich?“ · „Habe ich einen Schaden?“ |
| Strafen | „Habe ich Strafen?“ · „Wer hat Strafen?“ · „Hat der Vordermann eine Strafe?“ · „Wie viele Verwarnungen für Track Limits habe ich?“ |
| Sonstiges | „Wer ist ausgefallen?“ · „Hat der Vordermann Schaden?“ |

**Schätzungen:** „Wo komme ich raus?“, „Lohnt sich ein Undercut?“, „Holt er
auf?“ und „Wie lange halten meine Reifen?“ rechnen mit den Rundenzeiten und
Boxenstopps des laufenden Rennens. Runden mit Safety Car, Boxenstopp oder
Dreher zählen dabei nicht. Am Anfang eines Rennens fehlen dafür noch Daten,
dann sagt der Ingenieur das. Zwei Werte kannst du in `config.toml` unter
`[strategie]` einstellen: den Boxenverlust, solange noch keiner gemessen ist,
und die Verschleißgrenze für „Wie lange halten meine Reifen?“.

Einen Fahrer meinst du mit seinem Namen, seinem Team, „Platz vier“, „der
Dritte“, „vor mir“, „hinter mir“, „der Führende“, „mein Teamkollege“ oder
„mein Kumpel“.

## L. Neue Version einspielen

1. `start.bat` schließen.
2. Auf GitHub wieder **„Code“ → „Download ZIP“**, entpacken.
3. Im entpackten Ordner alles markieren (Strg+A), kopieren (Strg+C).
4. In deinen Programmordner einfügen (Strg+V) → **„Dateien ersetzen“**.

Deine Einstellungen (`config.toml`), deine Sprüche (`texte.toml`), die
gespeicherten Rennen und das Sprachmodell bleiben dabei erhalten.
`installieren.bat` musst du nicht noch einmal ausführen.

## M. SimHub zeigt keine Daten mehr

Der Renningenieur reicht jedes Paket an SimHub weiter und prüft selbst, ob
dort jemand zuhört. Im Fenster von `start.bat` steht nach ein paar Sekunden
Spielbetrieb eine von zwei Zeilen:

- **„Weiterleitung an 127.0.0.1:20778 funktioniert (SimHub empfängt)."**
  Dann kommen die Daten bei SimHub an. Prüf in SimHub, ob F1 25 das gewählte
  Spiel ist und das Spiel läuft.
- **„Weiterleitung an 127.0.0.1:20778: Dort hört niemand zu. …"**
  Dann hört SimHub nicht auf Port 20778. So behebst du es:
  1. SimHub öffnen, **F1 25** wählen, **Game config** anklicken.
  2. Beim **Game telemetry UDP port** `20778` eintragen.
  3. **SimHub komplett schließen und neu starten.**
  4. Im Fenster von `start.bat` erscheint dann „… funktioniert wieder".

Zusätzlich muss im Spiel weiter Port **20777** stehen. Bietet SimHub an,
das Spiel automatisch zu konfigurieren, bestätige das nicht, sonst sendet
das Spiel wieder direkt an SimHub.

Die Prüfung läuft auf dem PC. Auch wenn sie „funktioniert" meldet, kann
SimHub selbst noch etwas ablehnen, zum Beispiel wenn dort ein anderes Spiel
gewählt ist.

## N. Spracherkennung verbessern

**Schritt 1: Herausfinden, woran es liegt.** `start.bat` schließen,
**`mikrofontest.bat`** doppelklicken. Mit Enter startest du eine Aufnahme von
fünf Sekunden: nach dem Piepton einen Satz sprechen, zum Beispiel „Wie viele
Sekunden zum Auto vor mir?". Danach siehst du:

- **Pegel und Urteil:** „gut", „zu leise", „fast leer" oder „übersteuert",
  mit einem Hinweis, was zu tun ist.
- **Was jede Erkennung daraus macht** und mit welcher Frage das Programm es
  verbindet („Thema: abstand").
- Die Aufnahme als `mikrofontest.wav` im Programmordner. Hör sie dir an. Hörst
  du dort selbst schlecht, liegt es am Mikrofon, nicht an der Erkennung.

Bei „zu leise": In den Windows-Soundeinstellungen unter Eingabe die
Lautstärke des Mikrofons auf 100 stellen und näher ran. Die Buds sind unter
Windows oft sehr leise.

**Schritt 2: Die genauere Erkennung installieren.** **`whisper.bat`**
doppelklicken. Es installiert Whisper, lädt das Modell (beim ersten Mal etwa
500 MB, dafür muss der PC im Internet sein), misst, wie lange eine Erkennung
auf deinem PC dauert, und stellt `config.toml` um. Danach mit
`mikrofontest.bat` vergleichen: Dort steht Vosk neben Whisper.

- Dauert Whisper zu lange, wähle ein kleineres Modell: `whisper.bat base`.
- Zurück zu Vosk: in `config.toml` bei `[spracherkennung]` `engine = "vosk"`.

**Kleine Tricks, die immer helfen:**
- Die Lenkradtaste halten, bis der Satz **ganz zu Ende** ist, erst dann loslassen.
- Kurze, klare Fragen. „Abstand nach hinten" statt langer Sätze.
- Nach jeder Frage steht im Fenster `Aufnahme: …` und `Verstanden: …`. Die
  Aufnahme liegt als `letzte_aufnahme.wav` im Programmordner.
- Bei Vosk hilft eventuell `wortliste = true` bei `[spracherkennung]`: Dann hört
  Vosk nur auf Wörter, die das Programm kennt.

## Wenn etwas nicht klappt

| Was du siehst | Was zu tun ist |
|---|---|
| „Python wurde nicht gefunden“ | Teil A wiederholen, Häkchen „Add python.exe to PATH“ setzen |
| „UDP-Port 20777 ist belegt“ | SimHub hört noch auf 20777 → Teil E |
| „Noch keine Telemetrie“ | Einstellungen im Spiel prüfen → Teil D |
| Zeilen mit „FUNK:“, aber kein Ton | Fenster fotografieren und schicken (siehe C3) |
| „Spracheingabe aus: …“ | `installieren.bat` noch einmal laufen lassen |
| SimHub zeigt nichts mehr an | Zeile „Weiterleitung an …“ im Fenster lesen, siehe M |
| „Fehler in config.toml“ | Tippfehler in der Datei → Datei löschen, sie wird neu angelegt |

Kommst du an einer Stelle nicht weiter: das schwarze Fenster fotografieren und
schicken, dann sehe ich, woran es liegt.
