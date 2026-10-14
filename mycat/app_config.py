"""Centralized config paths for mycat (single source of truth).

main.py, reminder.py and llm_prompt.py re-export these names so legacy
``mycat.main.CFG_FILE``-style imports keep working.
"""

import configparser
from pathlib import Path

from . import secret_store

APP_NAME = "mycat"
CFG_DIR = Path.home() / ".config" / APP_NAME
CFG_FILE = CFG_DIR / "config.ini"
HISTORY_FILE = CFG_DIR / "history.txt"


def secure_write_config(parser: configparser.ConfigParser) -> None:
    """Write ``parser`` to CFG_FILE with owner-only permissions."""
    CFG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CFG_FILE, "w") as handle:
        parser.write(handle)
    secret_store.secure_file(CFG_FILE)


__all__ = [
    "APP_NAME",
    "CFG_DIR",
    "CFG_FILE",
    "HISTORY_FILE",
    "secure_write_config",
]
