@echo off
cd /d "%~dp0"
if not exist renningenieur\app.py goto unvollstaendig
rem Schickt ein simuliertes Rennen an den laufenden Renningenieur (start.bat).
rem Tempo 2 = doppelte Geschwindigkeit, das Rennen dauert dann etwa 9 Minuten.
rem Python suchen: zuerst die eigene Umgebung, dann den Python-Starter, dann python
set PY=python
where py >nul 2>&1 && set PY=py -3
if exist .venv\Scripts\python.exe set PY=.venv\Scripts\python.exe
%PY% -m renningenieur simulation alles --tempo 2 %*
pause
exit /b 0
:unvollstaendig
echo.
echo In diesem Ordner fehlt der Unterordner "renningenieur".
echo Bitte den GANZEN entpackten Ordner hierher kopieren, nicht nur einzelne Dateien:
echo alle Dateien und Ordner markieren (Strg+A), kopieren und hier einfuegen.
pause
exit /b 1
