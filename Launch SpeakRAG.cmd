@echo off
set "APP_DIR=%~dp0"
set "PYTHON=%APP_DIR%.venv\Scripts\pythonw.exe"

if not exist "%PYTHON%" (
    echo SpeakRAG is not set up yet.
    echo From this folder, run: py -3.11 -m venv .venv
    echo Then run: .venv\Scripts\python.exe -m pip install -r requirements.txt
    pause
    exit /b 1
)

start "" /D "%APP_DIR%" "%PYTHON%" "%APP_DIR%desktop_app.py"
