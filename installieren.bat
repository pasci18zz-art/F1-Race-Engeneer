@echo off
rem Einmalig ausfuehren: legt eine Python-Umgebung an und installiert alles.
cd /d "%~dp0"
python --version >nul 2>&1
if errorlevel 1 (
  echo Python wurde nicht gefunden. Bitte Python 3.11 oder neuer von python.org installieren
  echo und dabei "Add python.exe to PATH" ankreuzen.
  pause
  exit /b 1
)
if not exist .venv python -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m renningenieur modell
echo.
echo Fertig. Starten mit start.bat
pause
