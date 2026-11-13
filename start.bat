@echo off
rem Startet den Renningenieur. Zusaetzliche Angaben werden durchgereicht,
rem z. B.:  start.bat simulation   oder   start.bat geraete
cd /d "%~dp0"
if exist .venv\Scripts\activate.bat call .venv\Scripts\activate.bat
python -m renningenieur %*
if errorlevel 1 pause
