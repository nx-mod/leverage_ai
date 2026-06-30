#!/usr/bin/env python3
"""Semantic caching layer - DISABLED on this system."""

import logging
from typing import Optional

logger = logging.getLogger("leverage_ai.semantic_cache")
logger.warning("Semantic caching disabled (transformers incompatible with ARM64 Termux)")

HAS_EMBEDDINGS = False

def semantic_cache_lookup(prompt: str, max_tokens: int, threshold: float = 0.85) -> Optional[str]:
    """Disabled."""
    return None

def semantic_cache_store(prompt: str, max_tokens: int, response: str) -> None:
    """Disabled."""
    pass

def clear_semantic_cache() -> None:
    """Disabled."""
    pass

def semantic_cache_stats() -> dict:
    """Disabled."""
    return {"entries": 0, "file_size_kb": 0, "status": "disabled"}
