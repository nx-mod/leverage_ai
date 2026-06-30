#!/usr/bin/env python3
"""Provider enable/disable state and runtime API key overrides.

Two concerns live here, both driven by the /providers panel:

1. Disabling a provider entirely (it's removed from every chain it
   would otherwise appear in, regardless of whether it has a key).
2. Overriding/setting an API key at runtime, without editing
   ~/.leverage_ai.env or restarting the process.

Key overrides are applied directly into os.environ so that
providers.py's existing os.getenv() lookups pick them up immediately -
no need to plumb a separate lookup path through every provider
function.
"""

import json
import logging
import os
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger("leverage_ai.provider_settings")

PROVIDER_SETTINGS_FILE = Path.home() / ".leverage_providers.json"

# provider display name -> env var name it reads its key from
PROVIDER_ENV_VARS = {
    "Groq": "GROQ_API_KEY",
    "Cloudflare": "CLOUDFLARE_API_KEY",
    "Charm Hyper": "HYPER_API_KEY",
    "OpenRouter": "OPENROUTER_API_KEY",
    "Qwen": "OPENROUTER_API_KEY",  # Qwen rides on OpenRouter's key
    "Gemini": "GOOGLE_API_KEY",
    "DeepSeek": "DEEPSEEK_API_KEY",
    "Mistral": "MISTRAL_API_KEY",
    "HuggingFace": "HUGGINGFACE_API_KEY",
}

# Cloudflare also needs an account id alongside its key - not a provider
# you'd "set a key" for the same way, but exposed so /providers can show it.
EXTRA_ENV_VARS = {
    "Cloudflare": [("Account ID", "CF_ACCOUNT_ID")],
}

ALL_PROVIDER_NAMES = list(PROVIDER_ENV_VARS.keys())


def _defaults() -> Dict[str, Any]:
    return {"disabled": [], "key_overrides": {}}


def load_provider_settings() -> Dict[str, Any]:
    """Load settings and apply any key overrides into os.environ immediately."""
    settings = _defaults()
    if PROVIDER_SETTINGS_FILE.exists():
        try:
            saved = json.loads(PROVIDER_SETTINGS_FILE.read_text())
            settings["disabled"] = saved.get("disabled", [])
            settings["key_overrides"] = saved.get("key_overrides", {})
        except Exception as e:
            logger.debug(f"Failed to load provider settings, using defaults: {e}")

    for env_var, value in settings["key_overrides"].items():
        if value:
            os.environ[env_var] = value

    return settings


def save_provider_settings(settings: Dict[str, Any]) -> None:
    try:
        PROVIDER_SETTINGS_FILE.write_text(json.dumps(settings, indent=2))
    except Exception as e:
        logger.debug(f"Failed to save provider settings: {e}")


def is_disabled(settings: Dict[str, Any], provider_name: str) -> bool:
    return provider_name in settings.get("disabled", [])


def toggle_provider(settings: Dict[str, Any], provider_name: str) -> bool:
    """Flip a provider's enabled/disabled state. Returns True if now enabled."""
    disabled = settings.setdefault("disabled", [])
    if provider_name in disabled:
        disabled.remove(provider_name)
        enabled = True
    else:
        disabled.append(provider_name)
        enabled = False
    save_provider_settings(settings)
    return enabled


def set_key(settings: Dict[str, Any], env_var: str, value: str) -> None:
    """Set/override an API key both in the settings store and the live env."""
    settings.setdefault("key_overrides", {})[env_var] = value
    os.environ[env_var] = value
    save_provider_settings(settings)


def clear_key(settings: Dict[str, Any], env_var: str) -> None:
    settings.get("key_overrides", {}).pop(env_var, None)
    # Don't unset os.environ here - if the var was set normally (not via
    # override) before the process started, we want it visible again
    # rather than blanked. Restarting fully clears overrides either way.
    save_provider_settings(settings)


def mask_key(value: Optional[str]) -> str:
    """Show only the last 4 characters of a key, for display."""
    if not value:
        return "(not set)"
    if len(value) <= 4:
        return "*" * len(value)
    return "*" * (len(value) - 4) + value[-4:]


def get_key_display(provider_name: str) -> str:
    env_var = PROVIDER_ENV_VARS.get(provider_name)
    if not env_var:
        return "(no key needed)"
    return mask_key(os.environ.get(env_var))


def has_configured_key(provider_name: str) -> bool:
    """Whether a provider currently has the credentials it needs to be called.

    Checked live (os.environ) rather than against the import-time
    CONFIGURED_PROVIDERS snapshot in config.py, so a key set via
    /providers takes effect immediately - no restart required.
    """
    env_var = PROVIDER_ENV_VARS.get(provider_name)
    if not env_var:
        return True  # no key needed (shouldn't happen given current providers)
    if not os.environ.get(env_var):
        return False
    if provider_name == "Cloudflare" and not os.environ.get("CF_ACCOUNT_ID"):
        return False
    return True
