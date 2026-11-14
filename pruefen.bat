@echo off
cd /d "%~dp0"
if not exist renningenieur\app.py goto unvollstaendig
rem Hoert 15 Sekunden auf die Telemetrie des Spiels und prueft das Paketformat.
rem Vorher start.bat schliessen. Im Spiel muss man dabei auf der Strecke sein.
rem Python suchen: zuerst die eigene Umgebung, dann den Python-Starter, dann python
set PY=python
where py >nul 2>&1 && set PY=py -3
if exist .venv\Scripts\python.exe set PY=.venv\Scripts\python.exe
%PY% -m renningenieur pruefen %*
pause
exit /b 0
:unvollstaendig
echo.
echo In diesem Ordner fehlt der Unterordner "renningenieur".
echo Bitte den GANZEN entpackten Ordner hierher kopieren, nicht nur einzelne Dateien:
echo alle Dateien und Ordner markieren (Strg+A), kopieren und hier einfuegen.
pause
exit /b 1
