@echo off
cd /d "%~dp0"
rem Schickt ein simuliertes Rennen an den laufenden Renningenieur (start.bat).
rem Tempo 2 = doppelte Geschwindigkeit, das Rennen dauert dann etwa 9 Minuten.
rem Python suchen: zuerst die eigene Umgebung, dann den Python-Starter, dann python
set PY=python
where py >nul 2>&1 && set PY=py -3
if exist .venv\Scripts\python.exe set PY=.venv\Scripts\python.exe
%PY% -m renningenieur simulation alles --tempo 2 %*
pause
