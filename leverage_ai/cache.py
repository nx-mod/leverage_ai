#!/usr/bin/env python3
"""Caching system with exact and semantic similarity matching."""

import json
import hashlib
import time
from difflib import SequenceMatcher
from leverage_ai.config import CACHE_DIR

def cache_key(prompt, max_tokens):
    """Generate cache key with semantic hashing."""
    normalized = ' '.join(prompt.lower().split())
    h = hashlib.md5(f"{normalized}:{max_tokens}".encode()).hexdigest()[:12]
    return CACHE_DIR / f"{h}.json"

def load_cache(prompt, max_tokens):
    """Load from exact cache or find similar cached responses."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # Try exact match first
    key = cache_key(prompt, max_tokens)
    if key.exists():
        try:
            data = json.loads(key.read_text())
            age = time.time() - data.get("timestamp", 0)
            if age < 86400 * 7:  # 7 day TTL
                return data["content"]
            else:
                key.unlink()
        except:
            pass

    # Try semantic similarity match (for short prompts)
    if len(prompt.split()) <= 20:
        normalized = ' '.join(prompt.lower().split())
        for cache_file in CACHE_DIR.glob("*.json"):
            try:
                data = json.loads(cache_file.read_text())
                cached_prompt = ' '.join(data["prompt"].lower().split())
                sim = SequenceMatcher(None, normalized, cached_prompt).ratio()
                if sim > 0.85 and len(cached_prompt.split()) <= 30:
                    print(f"  [semantic cache] {sim:.0%} match")
                    return data["content"]
            except:
                continue

    return None

def save_cache(prompt, max_tokens, content):
    """Save response to cache with cleanup."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    key = cache_key(prompt, max_tokens)
    data = {"prompt": prompt, "content": content, "timestamp": time.time()}
    key.write_text(json.dumps(data))

    # Clean old cache entries (keep under 100 files)
    cache_files = sorted(CACHE_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime)
    if len(cache_files) > 100:
        for old in cache_files[:-100]:
            old.unlink()
