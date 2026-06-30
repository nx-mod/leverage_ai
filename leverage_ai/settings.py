#!/usr/bin/env python3
"""User-configurable settings for Leverage AI.

Settings persist to ~/.leverage_settings.json and are toggled via the
/settings command in the interactive loop. Defaults are chosen to match
existing behavior exactly - nothing changes unless the user opts in.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger("leverage_ai.settings")

SETTINGS_FILE = Path.home() / ".leverage_settings.json"

# Each entry: key -> (default, label, description)
SETTINGS_SCHEMA = {
    "sandbox_code": (
        False,
        "Sandbox code execution",
        "Run AI-generated code in a restricted subprocess (no shell, limited "
        "CPU/memory, no network env vars) instead of subprocess.run(shell=True). "
        "Off by default to match existing behavior.",
    ),
    "auto_run_code": (
        False,
        "Auto-run generated code",
        "Skip the [run] y/N confirmation prompt and execute code automatically. "
        "Leave off unless you trust the model's output completely.",
    ),
    "semantic_cache": (
        True,
        "Semantic cache",
        "Use embedding-based fuzzy cache matching in addition to exact-match cache.",
    ),
    "debug_logging": (
        False,
        "Debug logging",
        "Equivalent to passing --debug at startup.",
    ),
}



def _defaults() -> Dict[str, Any]:
    return {key: val[0] for key, val in SETTINGS_SCHEMA.items()}


def load_settings() -> Dict[str, Any]:
    """Load settings, filling in any missing keys with defaults."""
    settings = _defaults()
    if SETTINGS_FILE.exists():
        try:
            saved = json.loads(SETTINGS_FILE.read_text())
            for key in SETTINGS_SCHEMA:
                if key in saved:
                    settings[key] = saved[key]
        except Exception as e:
            logger.debug(f"Failed to load settings, using defaults: {e}")
    return settings


def save_settings(settings: Dict[str, Any]) -> None:
    try:
        SETTINGS_FILE.write_text(json.dumps(settings, indent=2))
    except Exception as e:
        logger.debug(f"Failed to save settings: {e}")


def toggle_setting(settings: Dict[str, Any], key: str) -> bool:
    """Flip a boolean setting, save, and return the new value."""
    settings[key] = not settings.get(key, _defaults().get(key, False))
    save_settings(settings)
    return settings[key]


def set_setting(settings: Dict[str, Any], key: str, value: bool) -> None:
    settings[key] = value
    save_settings(settings)


def render_panel(settings: Dict[str, Any]) -> str:
    """Render the numbered /settings panel as a string."""
    from leverage_ai.colors import section, success, muted, info

    lines = []
    lines.append(f"\n{section('─' * 50)}")
    lines.append(f"{section('SETTINGS')}")
    lines.append(f"{section('─' * 50)}")
    for i, (key, (_, label, desc)) in enumerate(SETTINGS_SCHEMA.items(), start=1):
        value = settings.get(key, SETTINGS_SCHEMA[key][0])
        state_str = success("ON") if value else muted("OFF")
        lines.append(f"  {i}. {label:<26} [{state_str}]")
        lines.append(f"     {muted(desc)}")
    lines.append(f"{section('─' * 50)}")
    lines.append(info("  Type a number to toggle, or 'done' to exit settings."))
    return "\n".join(lines)


def key_for_index(i: int) -> str:
    """Map a 1-based menu index to a settings key."""
    keys = list(SETTINGS_SCHEMA.keys())
    if 1 <= i <= len(keys):
        return keys[i - 1]
    raise IndexError(f"No setting at index {i}")
