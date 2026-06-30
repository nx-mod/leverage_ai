#!/usr/bin/env python3
"""State management for Leverage AI - usage tracking and persistence."""

import json
import time
import fcntl
import logging
from leverage_ai.config import STATE_FILE

logger = logging.getLogger("leverage_ai.state")

def load_state():
    """Load state from disk with file locking."""
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, 'r') as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_SH)
                try:
                    state = json.load(f)
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                return state
        except Exception as e:
            logger.warning(f"Failed to load state: {e}")
    
    # Default state with new fields
    return {
        "day": time.strftime("%Y-%m-%d"),
        "cf_req": 0,
        "tokens": {},
        "depleted": [],
        "provider_latency": {},  # {"provider_name": [list of latencies (ms)]}
        "provider_backoff": {},  # {"provider_name": {"strikes": 0, "last_failure": timestamp, "retry_after": timestamp}}
    }

def save_state(s):
    """Save state to disk atomically with file locking."""
    try:
        temp_file = STATE_FILE.with_suffix(".tmp")
        
        # Write to temp file
        with open(temp_file, 'w') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                json.dump(s, f, indent=2)
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        
        # Atomic rename
        temp_file.replace(STATE_FILE)
        logger.debug("State saved atomically")
    except Exception as e:
        logger.error(f"Failed to save state atomically: {e}")
        # Fallback to non-atomic write
        try:
            STATE_FILE.write_text(json.dumps(s, indent=2))
            logger.warning("Fell back to non-atomic state write")
        except Exception as e2:
            logger.error(f"Fallback state write also failed: {e2}")

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

def record_latency(state, provider: str, latency_ms: float):
    """Record provider latency for decision-making."""
    if "provider_latency" not in state:
        state["provider_latency"] = {}
    
    if provider not in state["provider_latency"]:
        state["provider_latency"][provider] = []
    
    # Keep rolling window of last 50 measurements
    state["provider_latency"][provider].append(latency_ms)
    if len(state["provider_latency"][provider]) > 50:
        state["provider_latency"][provider].pop(0)

def get_provider_latency_stats(state, provider: str) -> dict:
    """Get latency statistics for a provider."""
    latencies = state.get("provider_latency", {}).get(provider, [])
    if not latencies:
        return {"p50": 0, "p95": 0, "avg": 0}
    
    sorted_latencies = sorted(latencies)
    return {
        "p50": sorted_latencies[len(sorted_latencies) // 2],
        "p95": sorted_latencies[int(len(sorted_latencies) * 0.95)],
        "avg": sum(latencies) / len(latencies),
        "count": len(latencies),
    }

def record_provider_failure(state, provider: str, reason: str, retry_after: int = 0):
    """Record provider failure with backoff state."""
    if "provider_backoff" not in state:
        state["provider_backoff"] = {}
    
    if provider not in state["provider_backoff"]:
        state["provider_backoff"][provider] = {"strikes": 0, "last_failure": 0, "retry_after": 0}
    
    backoff_state = state["provider_backoff"][provider]
    backoff_state["strikes"] = backoff_state.get("strikes", 0) + 1
    backoff_state["last_failure"] = int(time.time())
    backoff_state["reason"] = reason
    
    if retry_after > 0:
        backoff_state["retry_after"] = int(time.time()) + retry_after

def can_retry_provider(state, provider: str) -> bool:
    """Check if provider can be retried (backoff expired)."""
    backoff = state.get("provider_backoff", {}).get(provider, {})
    retry_after = backoff.get("retry_after", 0)
    
    if retry_after == 0:
        return True
    
    return int(time.time()) >= retry_after

def reset_provider_backoff(state, provider: str):
    """Reset backoff state for a provider (successful call)."""
    if "provider_backoff" not in state:
        state["provider_backoff"] = {}
    
    if provider in state["provider_backoff"]:
        state["provider_backoff"][provider] = {"strikes": 0, "last_failure": 0, "retry_after": 0}
