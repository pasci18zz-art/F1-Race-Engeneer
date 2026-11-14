@echo off
cd /d "%~dp0"
if not exist renningenieur\app.py goto unvollstaendig
rem Einmalig ausfuehren: legt eine eigene Python-Umgebung an und installiert alles.
set PY=python
where py >nul 2>&1 && set PY=py -3
%PY% --version >nul 2>&1
if errorlevel 1 goto keinpython
echo Lege Python-Umgebung an ...
if not exist .venv\Scripts\python.exe %PY% -m venv .venv
if not exist .venv\Scripts\python.exe goto keinpython
set PY=.venv\Scripts\python.exe
%PY% -m pip install --upgrade pip
echo.
echo Installiere Spracherkennung, Mikrofon- und Lenkrad-Anbindung ...
%PY% -m pip install vosk
if errorlevel 1 echo WARNUNG: vosk konnte nicht installiert werden - Spracheingabe fehlt dann.
%PY% -m pip install sounddevice
if errorlevel 1 echo WARNUNG: sounddevice konnte nicht installiert werden - Mikrofon fehlt dann.
%PY% -m pip install pygame-ce
if errorlevel 1 echo WARNUNG: pygame-ce konnte nicht installiert werden - Lenkradtaste fehlt dann.
echo.
echo Lade das deutsche Sprachmodell (ca. 45 MB) ...
%PY% -m renningenieur modell
echo.
echo Fertig. Jetzt start.bat doppelklicken.
pause
exit /b 0
:keinpython
echo.
echo Python wurde nicht gefunden.
echo Bitte Python von https://www.python.org/downloads/ installieren und im ersten
echo Fenster des Installers unten das Haekchen "Add python.exe to PATH" setzen.
echo Danach diese Datei noch einmal doppelklicken.
pause
exit /b 1
:unvollstaendig
echo.
echo In diesem Ordner fehlt der Unterordner "renningenieur".
echo Bitte den GANZEN entpackten Ordner hierher kopieren, nicht nur einzelne Dateien:
echo alle Dateien und Ordner markieren (Strg+A), kopieren und hier einfuegen.
pause
exit /b 1
