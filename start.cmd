@echo off
rem Start Crewboard (host/port from .env). Expects .venv created with: python -m venv .venv ^&^& .venv\Scripts\pip install -r requirements.txt
cd /d "%~dp0"
".venv\Scripts\python.exe" run.py
