#!/usr/bin/env python3
"""Semantic caching layer using FastEmbed (ONNX runtime, no torch).

Why FastEmbed instead of sentence-transformers:
- sentence-transformers pulls in torch, which has no usable ARM64 wheels
  in Termux/proot -> hard-disabled on this system.
- FastEmbed runs on onnxruntime, which ships ARM64 Linux wheels, and the
  default model (BAAI/bge-small-en-v1.5) is ~120MB quantized, CPU-only.

Falls back to disabled mode gracefully if fastembed isn't importable,
exactly like the old implementation did for sentence-transformers.
"""

import json
import logging
import time
from pathlib import Path
from typing import Optional

from leverage_ai.config import CACHE_DIR

logger = logging.getLogger("leverage_ai.semantic_cache")

SEMANTIC_CACHE_FILE = CACHE_DIR / "semantic_cache.json"
MAX_ENTRIES = 1000
DEFAULT_THRESHOLD = 0.85

_model = None
HAS_EMBEDDINGS = True

try:
    from fastembed import TextEmbedding
except ImportError:
    HAS_EMBEDDINGS = False
    logger.warning("Semantic caching disabled (fastembed not installed)")


def get_model():
    """Lazy-load the FastEmbed model. Returns None if unavailable."""
    global _model, HAS_EMBEDDINGS
    if not HAS_EMBEDDINGS:
        return None
    if _model is None:
        try:
            # BAAI/bge-small-en-v1.5: ~120MB quantized ONNX, 384-dim embeddings
            _model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
        except Exception as e:
            logger.warning(f"Failed to load FastEmbed model: {e}")
            HAS_EMBEDDINGS = False
            return None
    return _model


def _embed(text: str):
    """Return a single embedding vector (list of floats) or None."""
    model = get_model()
    if model is None:
        return None
    try:
        # fastembed's .embed() returns a generator of numpy arrays
        vec = next(model.embed([text]))
        return vec.tolist()
    except Exception as e:
        logger.debug(f"Embedding failed: {e}")
        return None


def compute_similarity(embedding1, embedding2) -> float:
    """Cosine similarity between two embedding vectors, computed locally."""
    if not embedding1 or not embedding2:
        return 0.0
    dot = sum(a * b for a, b in zip(embedding1, embedding2))
    norm1 = sum(a * a for a in embedding1) ** 0.5
    norm2 = sum(b * b for b in embedding2) ** 0.5
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)


def _load_cache() -> dict:
    if SEMANTIC_CACHE_FILE.exists():
        try:
            return json.loads(SEMANTIC_CACHE_FILE.read_text())
        except Exception:
            logger.debug("Semantic cache file corrupt, starting fresh")
    return {}


def _save_cache(cache: dict) -> None:
    try:
        SEMANTIC_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        SEMANTIC_CACHE_FILE.write_text(json.dumps(cache))
    except Exception as e:
        logger.debug(f"Failed to save semantic cache: {e}")


def semantic_cache_lookup(prompt: str, max_tokens: int, threshold: float = DEFAULT_THRESHOLD) -> Optional[str]:
    """Find a cached response for a semantically similar prompt at the same max_tokens."""
    if not HAS_EMBEDDINGS:
        return None

    query_emb = _embed(prompt)
    if query_emb is None:
        return None

    cache = _load_cache()
    best_score = 0.0
    best_response = None

    for entry in cache.values():
        if entry.get("max_tokens") != max_tokens:
            continue
        score = compute_similarity(query_emb, entry.get("embedding"))
        if score > best_score:
            best_score = score
            best_response = entry.get("response")

    if best_score >= threshold:
        logger.debug(f"Semantic cache hit at {best_score:.2f} similarity")
        return best_response
    return None


def semantic_cache_store(prompt: str, max_tokens: int, response: str) -> None:
    """Store a prompt/response pair with its embedding."""
    if not HAS_EMBEDDINGS:
        return

    emb = _embed(prompt)
    if emb is None:
        return

    cache = _load_cache()
    key = f"{int(time.time() * 1000)}"
    cache[key] = {
        "prompt": prompt,
        "max_tokens": max_tokens,
        "response": response,
        "embedding": emb,
        "timestamp": time.time(),
    }

    # Rolling window: keep only the most recent MAX_ENTRIES
    if len(cache) > MAX_ENTRIES:
        sorted_keys = sorted(cache.keys(), key=lambda k: cache[k].get("timestamp", 0))
        for old_key in sorted_keys[: len(cache) - MAX_ENTRIES]:
            del cache[old_key]

    _save_cache(cache)


def clear_semantic_cache() -> None:
    if SEMANTIC_CACHE_FILE.exists():
        SEMANTIC_CACHE_FILE.unlink()


def semantic_cache_stats() -> dict:
    if not HAS_EMBEDDINGS:
        return {"entries": 0, "file_size_kb": 0, "status": "disabled"}
    cache = _load_cache()
    size_kb = SEMANTIC_CACHE_FILE.stat().st_size / 1024 if SEMANTIC_CACHE_FILE.exists() else 0
    return {"entries": len(cache), "file_size_kb": round(size_kb, 1), "status": "enabled"}
