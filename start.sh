#!/usr/bin/env bash
# Start Crewboard (host/port from .env). Creates the venv on first run.
cd "$(dirname "$0")"
[ -x .venv/bin/python ] || { python3 -m venv .venv && .venv/bin/pip install -r requirements.txt; }
exec .venv/bin/python run.py
