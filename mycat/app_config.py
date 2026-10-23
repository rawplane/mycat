"""Centralized config paths and operations for mycat (single source of truth).

main.py, reminder.py and llm_prompt.py re-export these names so legacy
``mycat.main.CFG_FILE``-style imports keep working.
"""

import configparser
import logging
from pathlib import Path

from . import secret_store

logger = logging.getLogger(__name__)

APP_NAME = "mycat"
CFG_DIR = Path.home() / ".config" / APP_NAME
CFG_FILE = CFG_DIR / "config.ini"
HISTORY_FILE = CFG_DIR / "history.txt"

# Window position settings
DEFAULT_POSITION_OFFSET_X = 10  # Offset from right edge of screen
DEFAULT_POSITION_OFFSET_Y = 10  # Offset from bottom edge of screen


def secure_write_config(parser: configparser.ConfigParser) -> None:
    """Write ``parser`` to CFG_FILE with owner-only permissions."""
    CFG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CFG_FILE, "w", encoding="utf-8") as handle:
        parser.write(handle)
    secret_store.secure_file(CFG_FILE)


def read_config() -> configparser.ConfigParser:
    """Read CFG_FILE with UTF-8 encoding and return ConfigParser instance."""
    parser = configparser.ConfigParser()
    if CFG_FILE.exists():
        try:
            parser.read(CFG_FILE, encoding="utf-8")
        except Exception as exc:
            logger.warning("Unable to parse %s: %s", CFG_FILE, exc)
    return parser


def load_config(screen_width: int, screen_height: int, window_width: int, window_height: int) -> dict:
    """Load configuration from INI file. Returns position for bottom-right corner."""
    default_x = screen_width - window_width - DEFAULT_POSITION_OFFSET_X
    default_y = screen_height - window_height - DEFAULT_POSITION_OFFSET_Y
    config_data = {"x": default_x, "y": default_y}

    if not CFG_FILE.exists():
        return config_data

    try:
        config = read_config()
        if "window" in config:
            if "x" in config["window"]:
                config_data["x"] = int(config["window"]["x"])
            if "y" in config["window"]:
                config_data["y"] = int(config["window"]["y"])
    except Exception as e:
        logger.error("Config load error: %s", e)

    return config_data


def save_config(config: dict) -> None:
    """Save configuration to INI file."""
    try:
        file_config = read_config()

        if not file_config.has_section("window"):
            file_config.add_section("window")

        if "x" in config:
            file_config["window"]["x"] = str(config["x"])
        if "y" in config:
            file_config["window"]["y"] = str(config["y"])

        secure_write_config(file_config)
    except Exception as e:
        logger.error("Config save error: %s", e)


def load_image_from_ini() -> str | None:
    """Load default image setting from INI file."""
    if not CFG_FILE.exists():
        logger.info("INI config not found, using default: cat")
        return None

    try:
        config = read_config()
        if "settings" in config and "default_image" in config["settings"]:
            image_name = config["settings"]["default_image"]
            logger.info("Loaded image from INI: %s", image_name)
            return image_name
        logger.info("INI config exists but no default_image setting found, using default: cat")
        return None
    except Exception as e:
        logger.error("Error reading INI file: %s, using default: cat", e)
        return None


def load_wait_time_from_ini(default_wait: float) -> float:
    """Load wait_time setting from INI file."""
    if not CFG_FILE.exists():
        return default_wait
    try:
        config = read_config()
        if "settings" in config and "wait_time" in config["settings"]:
            return float(config["settings"]["wait_time"])
    except Exception as e:
        logger.error("Error reading wait_time from INI: %s", e)
    return default_wait


def save_image_to_ini(image_name: str) -> None:
    """Save current image setting to INI file (skips writing if value is unchanged)."""
    try:
        config = read_config()

        if (
            config.has_section("settings")
            and config.get("settings", "default_image", fallback=None) == image_name
        ):
            return

        if not config.has_section("settings"):
            config.add_section("settings")

        config["settings"]["default_image"] = image_name
        secure_write_config(config)
        logger.info("Saved image setting to INI: %s", image_name)
    except Exception as e:
        logger.error("Error saving image to INI: %s", e)


__all__ = [
    "APP_NAME",
    "CFG_DIR",
    "CFG_FILE",
    "DEFAULT_POSITION_OFFSET_X",
    "DEFAULT_POSITION_OFFSET_Y",
    "HISTORY_FILE",
    "load_config",
    "load_image_from_ini",
    "load_wait_time_from_ini",
    "read_config",
    "save_config",
    "save_image_to_ini",
    "secure_write_config",
]
