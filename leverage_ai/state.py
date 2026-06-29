#!/usr/bin/env python3
"""State management for Leverage AI - usage tracking and persistence."""

import json
import time
from leverage_ai.config import STATE_FILE

def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except:
            pass
    return {"day": time.strftime("%Y-%m-%d"), "cf_req": 0, "tokens": {}, "depleted": []}

def save_state(s):
    STATE_FILE.write_text(json.dumps(s, indent=2))

def reset_daily(state):
    """Reset daily counters if day changed."""
    today = time.strftime("%Y-%m-%d")
    if state["day"] != today:
        state["day"] = today
        state["cf_req"] = 0
        state["tokens"] = {}
        state["depleted"] = [p for p in state.get("depleted", []) if p != "Cloudflare"]
        save_state(state)
    return state
