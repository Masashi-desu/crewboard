"""Crewboard runtime configuration (environment variables, optionally loaded from .env).

CREWBOARD_DATA_DIR   data directory (SQLite DB, uploaded avatars, local overrides). Default: ./data
CREWBOARD_HOST       bind host for `python run.py`. Default: 127.0.0.1
CREWBOARD_PORT       bind port for `python run.py`. Default: 8090
CREWBOARD_BASE_PATH  public sub-path when served behind a reverse proxy that strips it (e.g. /crewboard). Default: ""
CREWBOARD_MCP_TOKEN  bearer token required for the MCP endpoint (/mcp/). Required to use MCP.
CREWBOARD_RULES_FILE operating rules markdown. Default: <data dir>/rules.md if present, else ./rules.md
"""
import os
HERE = os.path.dirname(os.path.abspath(__file__))

def _load_dotenv(path):
    if not os.path.exists(path): return
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line: continue
        k, v = line.split("=", 1); k = k.strip(); v = v.strip().strip('"').strip("'")
        os.environ.setdefault(k, v)
_load_dotenv(os.path.join(HERE, ".env"))

def _abs(p): return p if os.path.isabs(p) else os.path.join(HERE, p)
DATA_DIR = _abs(os.environ.get("CREWBOARD_DATA_DIR") or "data")
HOST = os.environ.get("CREWBOARD_HOST") or "127.0.0.1"
PORT = int(os.environ.get("CREWBOARD_PORT") or 8090)
BASE_PATH = (os.environ.get("CREWBOARD_BASE_PATH") or "").rstrip("/")
if BASE_PATH and not BASE_PATH.startswith("/"): BASE_PATH = "/" + BASE_PATH
MCP_TOKEN = os.environ.get("CREWBOARD_MCP_TOKEN") or os.environ.get("JOB_BOARD_MCP_TOKEN") or ""
DB_PATH = os.path.join(DATA_DIR, "jobs.db")
AVATAR_DIR = os.path.join(DATA_DIR, "avatars")
def rules_path():
    p = os.environ.get("CREWBOARD_RULES_FILE")
    if p: return _abs(p)
    local = os.path.join(DATA_DIR, "rules.md")
    return local if os.path.exists(local) else os.path.join(HERE, "rules.md")
