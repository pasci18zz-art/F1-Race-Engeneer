@echo off
cd /d "%~dp0"
rem Zeigt Mikrofone, Stimmen und Lenkradtasten an.
rem Python suchen: zuerst die eigene Umgebung, dann den Python-Starter, dann python
set PY=python
where py >nul 2>&1 && set PY=py -3
if exist .venv\Scripts\python.exe set PY=.venv\Scripts\python.exe
%PY% -m renningenieur geraete %*
pause
