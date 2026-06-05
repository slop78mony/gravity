import os
import json
from pathlib import Path

CONFIG_DIR = Path.home() / ".ipad_optimizer"
CONFIG_FILE = CONFIG_DIR / "config.json"
HISTORY_FILE = CONFIG_DIR / "history.json"

DEFAULTS = {
    "min_duplicate_size": 1024 * 10,  # 10 KB
    "large_file_threshold": 1024 * 1024 * 100,  # 100 MB
    "monitor_interval": 3600,  # seconds
    "alert_threshold_percent": 85,
    "cloud_provider": "google_drive",
    "extensions_to_skip": [".DS_Store", ".localized"],
    "temp_patterns": ["*.tmp", "*.temp", "*.cache", "*.log", "Thumbs.db"],
}


def load_config() -> dict:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            stored = json.load(f)
        return {**DEFAULTS, **stored}
    return DEFAULTS.copy()


def save_config(cfg: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)
