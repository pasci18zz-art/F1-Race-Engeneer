@echo off
cd /d "%~dp0"
if not exist renningenieur\app.py goto unvollstaendig
rem Spricht alle Namen aus config.toml [aussprache] mit deiner Stimme, damit du die Aussprache pruefen kannst.
rem Einzelne Namen: aussprache.bat Leclerc Hamilton
set PY=python
where py >nul 2>&1 && set PY=py -3
if exist .venv\Scripts\python.exe set PY=.venv\Scripts\python.exe
%PY% -m renningenieur aussprache %*
pause
exit /b 0
:unvollstaendig
echo.
echo In diesem Ordner fehlt der Unterordner "renningenieur".
echo Bitte den GANZEN entpackten Ordner hierher kopieren, nicht nur einzelne Dateien:
echo alle Dateien und Ordner markieren (Strg+A), kopieren und hier einfuegen.
pause
exit /b 1
