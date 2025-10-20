
from pathlib import Path
import os, json

BASE = Path(__file__).parent
CFG = BASE / "config.json"

def appdata_dir() -> Path:
    # Windows: %APPDATA%\VeraLex
    ad = os.environ.get("APPDATA") or os.path.expanduser("~\\AppData\\Roaming")
    return Path(ad) / "VeraLex"

def get_data_dir() -> Path:
    try:
        cfg = json.loads(CFG.read_text(encoding="utf-8"))
    except Exception:
        cfg = {"data_dir_mode":"appdata"}
    mode = (cfg.get("data_dir_mode") or "appdata").lower()
    if mode == "portable":
        return BASE / "data"
    return appdata_dir()

def ensure_data_dir():
    d = get_data_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d
