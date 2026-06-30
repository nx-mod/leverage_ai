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

# Build list of ALL providers that should be attempted
# (includes ones without keys - they'll just fail gracefully)
ALL_PROVIDERS = ["Cloudflare", "Groq", "Charm Hyper", "OpenRouter", "Qwen",
                 "HuggingFace", "Gemini", "DeepSeek", "Mistral"]

# -- Provider Chains (ordered by reliability/speed for each task) --
# Each chain's first few entries are the original curated preferred
# order for that task type; the rest of ALL_PROVIDERS is appended after
# so every provider is a real, toggleable candidate via /models -
# previously DeepSeek/Mistral/Gemini/OpenRouter/Charm Hyper/Qwen weren't
# in ANY chain regardless of keys or settings, making them permanently
# unreachable through the normal pipeline. Provider availability (key
# presence, /providers enable state, /models per-chain toggle) is what
# actually decides who gets tried now - this list is just the candidate
# pool + tie-break order.
def _full_chain(preferred):
    rest = [p for p in ALL_PROVIDERS if p not in preferred]
    return preferred + rest


CHAIN_SPEC = _full_chain(["Groq", "Cloudflare", "HuggingFace"])
CHAIN_ARCH = _full_chain(["Groq", "Cloudflare", "HuggingFace"])
CHAIN_BUILD = _full_chain(["Groq", "HuggingFace", "Cloudflare"])
CHAIN_REVIEW = _full_chain(["Groq", "HuggingFace", "Cloudflare"])
CHAIN_DRAFT = _full_chain(["Groq", "HuggingFace", "Cloudflare"])
CHAIN_FINAL = _full_chain(["Groq", "HuggingFace", "Cloudflare"])
CHAIN_ANALYZE = _full_chain(["Groq", "HuggingFace", "Cloudflare"])
CHAIN_QUICK = _full_chain(["Groq", "Cloudflare", "HuggingFace"])
CHAIN_CHAT = _full_chain(["Groq", "HuggingFace", "Cloudflare"])

# NOTE: chains are intentionally left UNFILTERED by configured-key status
# here. Filtering by "does this provider currently have a key" now happens
# live in orchestrator.run_stage() (via provider_settings.has_configured_key),
# so that adding a key through the /providers panel makes a provider
# immediately usable without restarting - it doesn't get permanently
# excluded just because no key existed at process start.
#
# /models per-chain disables and the global /providers enable/disable
# toggle also apply live, against these same full chain lists, via
# config.CHAIN_REGISTRY below.

print(f"\n[config] Configured providers: {', '.join(CONFIGURED_PROVIDERS)}")

# -- Named chain registry --
# Maps a human-readable pipeline-stage name to the actual chain list
# object. Used by the /models panel and by orchestrator.run_stage() to
# look up + apply per-chain provider disables via identity (id()) match,
# without requiring every pipelines.py call site to pass a name string.
CHAIN_REGISTRY = {
    "spec": CHAIN_SPEC,
    "arch": CHAIN_ARCH,
    "build": CHAIN_BUILD,
    "review": CHAIN_REVIEW,
    "draft": CHAIN_DRAFT,
    "final": CHAIN_FINAL,
    "analyze": CHAIN_ANALYZE,
    "quick": CHAIN_QUICK,
    "chat": CHAIN_CHAT,
}
