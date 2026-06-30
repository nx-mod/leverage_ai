#!/usr/bin/env python3
"""Per-chain provider enable/disable state, driven by the /models panel.

Distinct from provider_settings.py's global enable/disable: this lets
you keep a provider enabled overall but exclude it from, say, the
"code" chain specifically (e.g. you don't trust HuggingFace's code
output, but still want it available for quick factual answers).
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, List

logger = logging.getLogger("leverage_ai.chain_settings")

CHAIN_SETTINGS_FILE = Path.home() / ".leverage_chains.json"


def _defaults() -> Dict[str, Any]:
    return {"chain_disabled": {}}  # chain_name -> [provider, ...]


def load_chain_settings() -> Dict[str, Any]:
    settings = _defaults()
    if CHAIN_SETTINGS_FILE.exists():
        try:
            saved = json.loads(CHAIN_SETTINGS_FILE.read_text())
            settings["chain_disabled"] = saved.get("chain_disabled", {})
        except Exception as e:
            logger.debug(f"Failed to load chain settings, using defaults: {e}")
    return settings


def save_chain_settings(settings: Dict[str, Any]) -> None:
    try:
        CHAIN_SETTINGS_FILE.write_text(json.dumps(settings, indent=2))
    except Exception as e:
        logger.debug(f"Failed to save chain settings: {e}")


def is_disabled_in_chain(settings: Dict[str, Any], chain_name: str, provider_name: str) -> bool:
    return provider_name in settings.get("chain_disabled", {}).get(chain_name, [])


def toggle_provider_in_chain(settings: Dict[str, Any], chain_name: str, provider_name: str) -> bool:
    """Flip a provider's enabled state within one named chain. Returns True if now enabled."""
    disabled_map = settings.setdefault("chain_disabled", {})
    disabled_list = disabled_map.setdefault(chain_name, [])
    if provider_name in disabled_list:
        disabled_list.remove(provider_name)
        enabled = True
    else:
        disabled_list.append(provider_name)
        enabled = False
    save_chain_settings(settings)
    return enabled


def filter_chain(settings: Dict[str, Any], chain_name: str, chain: List[str]) -> List[str]:
    """Return chain with any per-chain-disabled providers removed."""
    disabled = set(settings.get("chain_disabled", {}).get(chain_name, []))
    if not disabled:
        return chain
    filtered = [p for p in chain if p not in disabled]
    return filtered if filtered else chain  # never return an empty chain
