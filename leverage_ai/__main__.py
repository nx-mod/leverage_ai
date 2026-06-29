#!/usr/bin/env python3
"""Leverage AI v2.0 - Multi-Provider AI Orchestrator

Entry point. Run with: python -m leverage_ai
"""

import sys
import logging
from leverage_ai.config import ALL_PROVIDERS
from leverage_ai.state import load_state, save_state
from leverage_ai.memory import load_memory, load_conversation, add_to_conversation
from leverage_ai.orchestrator import classify, usage_log
from leverage_ai.pipelines import pipeline_chat, pipeline_quick, pipeline_code, pipeline_write, pipeline_analyze
from leverage_ai.commands import handle_memory_command
from leverage_ai.usage import banner, show_usage


def main():
    noexec = False
    debug = False

    for arg in sys.argv[1:]:
        if arg in ("--noexec", "-n"):
            noexec = True
        elif arg in ("--debug", "-d"):
            debug = True
        elif arg in ("--help", "-h"):
            print("Leverage AI v2.0 - Multi-Provider Assistant")
            print("\nUsage: python -m leverage_ai [options]")
            print("\nOptions:")
            print("  --noexec, -n   Skip running saved code files")
            print("  --debug, -d    Enable debug logging")
            print("  --help, -h     Show this help message")
            print("\nCommands (type in interactive mode):")
            print("  remember X     Store a fact or preference")
            print("  forget X       Remove mentions of X from memory")
            print("  show memory    Display all stored memories")
            print("  clear memory   Wipe all stored memories")
            print("  usage          Check API usage and limits")
            print("  quit/q         Exit")
            return

    # Configure logging
    log_level = logging.DEBUG if debug else logging.WARNING
    logging.basicConfig(
        level=log_level,
        format="%(name)s %(levelname)s: %(message)s"
    )

    state = load_state()
    mem = load_memory()
    convo = load_conversation()

    # Check for required API keys
    import os
    missing_keys = []
    for prov, keyname in [("Cloudflare", "CLOUDFLARE_API_KEY"), ("Groq", "GROQ_API_KEY"),
                          ("Charm Hyper", "HYPER_API_KEY"), ("OpenRouter", "OPENROUTER_API_KEY"),
                          ("Gemini", "GOOGLE_API_KEY"), ("DeepSeek", "DEEPSEEK_API_KEY"),
                          ("Mistral", "MISTRAL_API_KEY"), ("HuggingFace", "HUGGINGFACE_API_KEY")]:
        val = os.getenv(keyname)
        if not val:
            missing_keys.append(prov)

    providers_needing_keys = [p for p in ALL_PROVIDERS if p not in ("Qwen",)]
    if len(missing_keys) == len(providers_needing_keys):
        print("\n  [ERROR] No API keys configured!")
        print("  Copy .env.example to ~/.leverage_ai.env and fill in at least one key.")
        print("  Example: export GROQ_API_KEY=gsk_...")
        sys.exit(1)
    elif missing_keys:
        for prov in missing_keys:
            print(f"  [warn] {prov}: API key not set (will skip)")

    banner(state, noexec)

    # Show example queries on first run
    if not state.get("seen_welcome"):
        print("\n  Example queries:")
        print("    - explain how DNS works")
        print("    - build a Python web scraper")
        print("    - write a haiku about coding")
        print("    - what's the capital of France?")
        print()
        state["seen_welcome"] = True
        save_state(state)

    while True:
        try:
            idea = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\nGoodbye!")
            break
        if idea.lower() in ["quit", "q"]:
            print("\nGoodbye!")
            break
        if not idea:
            continue

        # Handle memory / special commands
        if handle_memory_command(idea, mem):
            continue

        usage_log.clear()
        kind = classify(idea)

        if kind == "memory":
            if handle_memory_command(idea, mem):
                continue

        print(f"  [{kind}]")

        if kind == "chat":
            pipeline_chat(idea, state, convo)
        elif kind == "quick":
            pipeline_quick(idea, state, convo)
        elif kind == "code":
            pipeline_code(idea, state, noexec, mem)
        elif kind == "write":
            pipeline_write(idea, state, mem)
        elif kind == "analyze":
            pipeline_analyze(idea, state, mem)

        # Track conversation
        if usage_log and usage_log[-1][0] != "Cache":
            add_to_conversation(convo, "user", idea)

        show_usage(state)


if __name__ == "__main__":
    main()
