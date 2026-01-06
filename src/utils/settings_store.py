"""Simple JSON-based persistent storage for user settings."""

import json
import logging
import os
import tempfile
from pathlib import Path
from threading import Lock

logger = logging.getLogger(__name__)

# Default storage path (relative to project root)
DEFAULT_SETTINGS_FILE = Path(__file__).parent.parent.parent / "data" / "user_settings.json"

_settings: dict[int, dict] = {}
_lock = Lock()
_settings_file: Path = DEFAULT_SETTINGS_FILE


def init(settings_file: Path | None = None) -> None:
    """Initialize the settings store and load from disk."""
    global _settings_file, _settings

    if settings_file:
        _settings_file = settings_file

    # Ensure data directory exists
    _settings_file.parent.mkdir(parents=True, exist_ok=True)

    # Load existing settings
    if _settings_file.exists():
        try:
            with open(_settings_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Convert string keys back to int (JSON doesn't support int keys)
                _settings = {int(k): v for k, v in data.items()}
            logger.info(f"Loaded settings for {len(_settings)} users from {_settings_file}")
        except json.JSONDecodeError as e:
            # Backup corrupted file and start fresh
            backup_path = _settings_file.with_suffix(".json.bak")
            try:
                os.replace(_settings_file, backup_path)
                logger.warning(f"Settings file corrupted, backed up to {backup_path}: {e}")
            except OSError as backup_err:
                logger.error(f"Failed to backup corrupted settings: {backup_err}")
            _settings = {}
        except Exception as e:
            logger.error(f"Failed to load settings: {e}")
            _settings = {}
    else:
        _settings = {}
        logger.info(f"No existing settings file, starting fresh")


def _save() -> None:
    """Save settings to disk atomically.

    Uses write-to-temp-then-rename pattern to ensure atomicity.
    """
    try:
        # Write to temp file in same directory (ensures same filesystem for atomic rename)
        fd, tmp_path = tempfile.mkstemp(
            dir=_settings_file.parent,
            prefix=".user_settings_",
            suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(_settings, f, indent=2, ensure_ascii=False)
            # Atomic replace
            os.replace(tmp_path, _settings_file)
        except Exception:
            # Clean up temp file on error
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    except Exception as e:
        logger.error(f"Failed to save settings: {e}")


def get(chat_id: int, key: str | None = None, default=None):
    """Get settings for a chat ID.

    Args:
        chat_id: The chat ID
        key: Optional specific key to get. If None, returns entire settings dict.
        default: Default value if key not found

    Returns:
        The setting value or default
    """
    with _lock:
        user_data = _settings.get(chat_id, {})
        if key is None:
            return user_data.copy()
        return user_data.get(key, default)


def set(chat_id: int, key: str, value) -> None:
    """Set a setting for a chat ID and save to disk.

    Args:
        chat_id: The chat ID
        key: The setting key
        value: The setting value
    """
    with _lock:
        if chat_id not in _settings:
            _settings[chat_id] = {}
        _settings[chat_id][key] = value
        _save()


def get_all() -> dict[int, dict]:
    """Get a copy of all settings."""
    with _lock:
        return {k: v.copy() for k, v in _settings.items()}
