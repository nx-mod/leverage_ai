#!/usr/bin/env python3
"""Configuration and constants for Leverage AI - SECURE VERSION (no hardcoded keys)."""

import os
import sys
import pathlib

try:
    from dotenv import load_dotenv
    ENV_FILE = pathlib.Path.home() / ".leverage_ai.env"
    if ENV_FILE.exists():
        load_dotenv(dotenv_path=ENV_FILE, override=False)
    if pathlib.Path(".env").exists():
        load_dotenv(override=False)
except ImportError:
    ENV_FILE = pathlib.Path.home() / ".leverage_ai.env"
    if ENV_FILE.exists():
        with open(ENV_FILE) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    if key not in os.environ:
                        os.environ[key] = val

# -- API Keys (from environment only, NO fallbacks) --
GROQ_KEY = os.getenv("GROQ_API_KEY")
CF_KEY = os.getenv("CLOUDFLARE_API_KEY")
CF_ACCT = os.getenv("CF_ACCOUNT_ID")
HYPER_KEY = os.getenv("HYPER_API_KEY")
OR_KEY = os.getenv("OPENROUTER_API_KEY")
GOOGLE_KEY = os.getenv("GOOGLE_API_KEY")
DS_KEY = os.getenv("DEEPSEEK_API_KEY")
MISTRAL_KEY = os.getenv("MISTRAL_API_KEY")
HF_KEY = os.getenv("HUGGINGFACE_API_KEY")

# Check at module load time that at least ONE key is set
AVAILABLE_KEYS = {
    "Groq": GROQ_KEY,
    "Cloudflare": CF_KEY,
    "Charm Hyper": HYPER_KEY,
    "OpenRouter": OR_KEY,
    "Gemini": GOOGLE_KEY,
    "DeepSeek": DS_KEY,
    "Mistral": MISTRAL_KEY,
    "HuggingFace": HF_KEY,
}

CONFIGURED_PROVIDERS = [name for name, key in AVAILABLE_KEYS.items() if key]

if not CONFIGURED_PROVIDERS:
    print("\n" + "!" * 60)
    print("ERROR: No API keys configured!")
    print("!" * 60)
    print("\nSet at least one API key as an environment variable.")
    print("Example: export GROQ_API_KEY=gsk_...")
    print("\nOr create ~/.leverage_ai.env with:")
    print("  GROQ_API_KEY=gsk_...")
    print("  CLOUDFLARE_API_KEY=...")
    print("  etc")
    print("\nConfigured keys currently: " + (", ".join(CONFIGURED_PROVIDERS) if CONFIGURED_PROVIDERS else "NONE"))
    print("!" * 60 + "\n")
    sys.exit(1)

# -- Timeouts --
TIMEOUT = (15, 60)
LONG_TIMEOUT = (15, 120)

# -- Paths --
STATE_FILE = pathlib.Path.home() / ".leverage_usage.json"
CACHE_DIR = pathlib.Path.home() / ".leverage_cache"
MEMORY_FILE = pathlib.Path.home() / ".leverage_memory.json"
CONVO_FILE = pathlib.Path.home() / ".leverage_convo.json"
AGENT_HISTORY_FILE = pathlib.Path.home() / ".leverage_agent_history.json"
WORK_DIR = pathlib.Path.home() / "ai_output"

# Create directories if they don't exist
CACHE_DIR.mkdir(parents=True, exist_ok=True)
WORK_DIR.mkdir(parents=True, exist_ok=True)

# -- Language Map --
LANG_MAP = {
    "python": {"ext": "py", "run": "python3 {path}"},
    "javascript": {"ext": "js", "run": "node {path}"},
    "typescript": {"ext": "ts", "run": "npx ts-node {path}"},
    "go": {"ext": "go", "run": "go run {path}"},
    "rust": {"ext": "rs", "run": "rustc {path} -o /tmp/_aout && /tmp/_aout"},
    "bash": {"ext": "sh", "run": "bash {path}"},
    "c": {"ext": "c", "run": "gcc {path} -o /tmp/_aout && /tmp/_aout"},
    "cpp": {"ext": "cpp", "run": "g++ {path} -o /tmp/_aout && /tmp/_aout"},
    "ruby": {"ext": "rb", "run": "ruby {path}"},
    "php": {"ext": "php", "run": "php {path}"},
    "r": {"ext": "r", "run": "Rscript {path}"},
}

# -- Provider Cost Estimates (per 1M tokens, USD) --
COSTS = {
    "Groq": 0.20,
    "Cloudflare": 0.00,
    "Charm Hyper": 0.00,
    "OpenRouter": 0.00,
    "Qwen": 0.00,
    "HuggingFace": 0.00,
    "Gemini": 0.00,
    "DeepSeek": 0.14,
    "Mistral": 0.15,
}

# -- Free Tier Limits --
LIMITS = {
    "Cloudflare": {"type": "requests", "limit": 10000},
    "Groq": {"type": "tokens", "limit": 500000},
    "Charm Hyper": {"type": "hypercredits", "limit": 100},
}

# -- Provider Chains (ordered by reliability/speed for each task) --
CHAIN_SPEC = ["Groq", "Cloudflare", "HuggingFace"]
CHAIN_ARCH = ["Groq", "Cloudflare", "HuggingFace"]
CHAIN_BUILD = ["Groq", "HuggingFace", "Cloudflare"]
CHAIN_REVIEW = ["Groq", "HuggingFace", "Cloudflare"]
CHAIN_DRAFT = ["Groq", "HuggingFace", "Cloudflare"]
CHAIN_FINAL = ["Groq", "HuggingFace", "Cloudflare"]
CHAIN_ANALYZE = ["Groq", "HuggingFace", "Cloudflare"]
CHAIN_QUICK = ["Groq", "Cloudflare", "HuggingFace"]
CHAIN_CHAT = ["Groq", "HuggingFace", "Cloudflare"]

# Build list of ALL providers that should be attempted
# (includes ones without keys - they'll just fail gracefully)
ALL_PROVIDERS = ["Cloudflare", "Groq", "Charm Hyper", "OpenRouter", "Qwen",
                 "HuggingFace", "Gemini", "DeepSeek", "Mistral"]

# Filter chains to only include providers with keys
def _filter_chain(chain):
    """Remove providers from chain that don't have API keys."""
    return [p for p in chain if p in CONFIGURED_PROVIDERS or p == "Qwen"]  # Qwen works through OpenRouter


CHAIN_SPEC = _filter_chain(CHAIN_SPEC)
CHAIN_ARCH = _filter_chain(CHAIN_ARCH)
CHAIN_BUILD = _filter_chain(CHAIN_BUILD)
CHAIN_REVIEW = _filter_chain(CHAIN_REVIEW)
CHAIN_DRAFT = _filter_chain(CHAIN_DRAFT)
CHAIN_FINAL = _filter_chain(CHAIN_FINAL)
CHAIN_ANALYZE = _filter_chain(CHAIN_ANALYZE)
CHAIN_QUICK = _filter_chain(CHAIN_QUICK)
CHAIN_CHAT = _filter_chain(CHAIN_CHAT)

# Fallback chains if filtering removed everything
def _ensure_nonempty(chain):
    """Ensure chain has at least one provider."""
    if not chain:
        return ["Groq", "HuggingFace", "Cloudflare"]
    return chain


CHAIN_SPEC = _ensure_nonempty(CHAIN_SPEC)
CHAIN_ARCH = _ensure_nonempty(CHAIN_ARCH)
CHAIN_BUILD = _ensure_nonempty(CHAIN_BUILD)
CHAIN_REVIEW = _ensure_nonempty(CHAIN_REVIEW)
CHAIN_DRAFT = _ensure_nonempty(CHAIN_DRAFT)
CHAIN_FINAL = _ensure_nonempty(CHAIN_FINAL)
CHAIN_ANALYZE = _ensure_nonempty(CHAIN_ANALYZE)
CHAIN_QUICK = _ensure_nonempty(CHAIN_QUICK)
CHAIN_CHAT = _ensure_nonempty(CHAIN_CHAT)

print(f"\n[config] Configured providers: {', '.join(CONFIGURED_PROVIDERS)}")
